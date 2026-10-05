"""ktff.org fikstür sayfalarını okur.

Sayfa yapısı (2026-27 sezonu):
  /ligler/<lig>/fikstur?hafta=N  -> tarih başlıkları ("04 Ekim 2026, Pazar") ve
  her maç için /maclar/<MaçNo> linki. Link metni:
  "Ev Ev 15:30 1 - 1 Maç No: 25352 Deplasman Deplasman"  (oynanmamışsa skor yerine "vs")

Parser HTML sınıflarına değil metne ve link sırasına dayanır; tasarım değişikliklerine
dayanıklı olması için bilinçli olarak böyle.
"""

from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import asdict, dataclass, field

import requests
from bs4 import BeautifulSoup, NavigableString, Tag

from . import config

log = logging.getLogger(__name__)

MONTHS = {
    "ocak": 1, "şubat": 2, "mart": 3, "nisan": 4, "mayıs": 5, "haziran": 6,
    "temmuz": 7, "ağustos": 8, "eylül": 9, "ekim": 10, "kasım": 11, "aralık": 12,
}
DATE_RE = re.compile(
    r"(\d{1,2})\s+(Ocak|Şubat|Mart|Nisan|Mayıs|Haziran|Temmuz|Ağustos|Eylül|Ekim|Kasım|Aralık)\s+(\d{4})",
    re.IGNORECASE,
)
MATCH_HREF_RE = re.compile(r"/maclar/(\d+)")
WEEK_HREF_RE = re.compile(r"[?&]hafta=(\d+)")
WEEK_TITLE_RE = re.compile(r"(\d{1,2})\.\s*Hafta", re.IGNORECASE)
MATCH_NO_RE = re.compile(r"Maç\s*No\s*:?\s*(\d+)", re.IGNORECASE)
TIME_RE = re.compile(r"\b(\d{1,2})[:.](\d{2})\b")
SCORE_RE = re.compile(r"^(\d{1,2})\s*[-–]\s*(\d{1,2})$")
VENUE_RE = re.compile(r"(Stad[ıi]|Stadyumu|Sahas[ıi]|Tesisleri|Stadium)\b", re.IGNORECASE)
# Canlı sitede tarihi/saati açıklanmamış maçlar için yer tutucu metinler
PENDING_DATE_RE = re.compile(r"Tarih\s+bekleniyor", re.IGNORECASE)
PENDING_RE = re.compile(r"\b(Saat|Tarih)\s+bekleniyor\b", re.IGNORECASE)


@dataclass
class Match:
    match_no: int
    league: str
    week: int
    home: str
    away: str
    date: str  # YYYY-MM-DD
    time: str | None = None  # HH:MM (yerel)
    home_score: int | None = None
    away_score: int | None = None
    status: str | None = None  # skor/vs dışında bir şey yazıyorsa (Ertelendi vb.)
    venue: str | None = None
    rev: int = 0
    extra: dict = field(default_factory=dict)

    @property
    def url(self) -> str:
        return f"{config.BASE_URL}/maclar/{self.match_no}"

    @property
    def played(self) -> bool:
        return self.home_score is not None and self.away_score is not None

    def content_key(self) -> tuple:
        """Takvimde görünen her şey; değişince rev artar."""
        return (self.home, self.away, self.date, self.time, self.home_score,
                self.away_score, self.status, self.venue, self.week)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Match":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


def _dedupe_name(s: str) -> str:
    """'Mesarya SK Mesarya SK' -> 'Mesarya SK' (sitede isim logo alt + metin olarak iki kez geçiyor)."""
    s = " ".join(s.split())
    n = len(s)
    if n >= 3 and n % 2 == 1:
        k = n // 2
        if s[:k] == s[k + 1:] and s[k] == " ":
            return s[:k]
    return s


def parse_date(text: str) -> str | None:
    m = DATE_RE.search(text)
    if not m:
        return None
    day, month_name, year = m.groups()
    month = MONTHS.get(month_name.lower().replace("i̇", "i"))
    if not month:
        return None
    return f"{int(year):04d}-{month:02d}-{int(day):02d}"


def parse_match_text(text: str) -> dict | None:
    """Link metnini parçalar. None dönerse metin maç satırı değildir."""
    text = " ".join(PENDING_RE.sub(" ", text).split())
    m = MATCH_NO_RE.search(text)
    if not m:
        return None
    left, away = text[: m.start()].strip(), text[m.end():].strip()
    out: dict = {"match_no": int(m.group(1)), "away": _dedupe_name(away),
                 "time": None, "home_score": None, "away_score": None, "status": None}

    tm = None
    for cand in TIME_RE.finditer(left):
        tm = cand  # skordan önce gelen ilk saat
        break
    if tm:
        out["time"] = f"{int(tm.group(1)):02d}:{tm.group(2)}"
        home, mid = left[: tm.start()], left[tm.end():]
    else:
        # Saat yoksa ortadaki ifade (skor / vs) sondadır
        mm = re.search(r"(\d{1,2}\s*[-–]\s*\d{1,2}|\bvs\.?|\bv\b|-)\s*$", left)
        if mm:
            home, mid = left[: mm.start()], mm.group(0)
        else:
            home, mid = left, ""
    out["home"] = _dedupe_name(home)

    mid = mid.strip()
    sm = SCORE_RE.match(mid)
    if sm:
        out["home_score"], out["away_score"] = int(sm.group(1)), int(sm.group(2))
    elif mid and mid.lower().rstrip(".") not in ("vs", "v", "-"):
        out["status"] = mid
    if not out["home"] or not out["away"]:
        return None
    return out


def parse_fixture_page(html: str, league_key: str, week: int | None = None) -> tuple[list[Match], dict]:
    """Bir fikstür sayfasını okur. (maçlar, meta) döner; meta = {'weeks': [...], 'shown_week': N}."""
    soup = BeautifulSoup(html, "html.parser")
    meta: dict = {"weeks": set(), "shown_week": None}

    for a in soup.find_all("a", href=True):
        wm = WEEK_HREF_RE.search(a["href"])
        if wm and "fikstur" in a["href"]:
            meta["weeks"].add(int(wm.group(1)))
    for s in soup.find_all(string=WEEK_TITLE_RE):
        if s.find_parent("a") is None:
            meta["shown_week"] = int(WEEK_TITLE_RE.search(s).group(1))
            break
    meta["weeks"] = sorted(meta["weeks"])
    # Sitenin gerçekten gösterdiği hafta esas: geçersiz ?hafta=N istenirse site varsayılan haftayı döner.
    page_week = meta["shown_week"] or week or 0

    matches: list[Match] = []
    seen: set[int] = set()
    undated = 0
    logos: dict[str, str] = {}
    current_date: str | None = None
    for node in soup.descendants:
        if isinstance(node, NavigableString):
            if node.find_parent("a") is not None:
                continue
            d = parse_date(str(node))
            if d:
                current_date = d
            elif PENDING_DATE_RE.search(str(node)):
                current_date = None  # sonraki maçlar önceki günün tarihini almasın
        elif isinstance(node, Tag) and node.name == "a" and MATCH_HREF_RE.search(node.get("href", "")):
            info = parse_match_text(node.get_text(" ", strip=True))
            if not info:
                continue
            no = int(MATCH_HREF_RE.search(node["href"]).group(1))
            if no in seen:
                continue
            seen.add(no)

            # Takım logolarını topla
            teams_el = node.find_all(class_="league-fixture-team")
            if len(teams_el) >= 2:
                for el, k in [(teams_el[0], info.get("home")), (teams_el[1], info.get("away"))]:
                    img = el.find("img")
                    if img and img.get("src") and k and k not in logos:
                        logos[k] = img["src"]
            else:
                imgs = node.find_all("img")
                if len(imgs) >= 2 and info.get("home") and info.get("away"):
                    if imgs[0].get("src") and info["home"] not in logos:
                        logos[info["home"]] = imgs[0]["src"]
                    if imgs[1].get("src") and info["away"] not in logos:
                        logos[info["away"]] = imgs[1]["src"]

            if current_date is None:
                undated += 1  # tarih açıklanınca takvime girer
                continue
            info["match_no"] = no
            matches.append(Match(league=league_key, week=page_week, date=current_date, **info))
    meta["undated"] = undated
    meta["logos"] = logos
    if undated:
        log.debug("%s %d. hafta: %d maçın tarihi henüz açıklanmadı", league_key, page_week, undated)
    return matches, meta


def _jsonld_venue(soup: BeautifulSoup) -> str | None:
    """Maç sayfasındaki schema.org SportsEvent -> location.name."""
    for tag in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(tag.string or "")
        except ValueError:
            continue
        stack = [data]
        while stack:
            d = stack.pop()
            if isinstance(d, list):
                stack.extend(d)
            elif isinstance(d, dict):
                loc = d.get("location")
                if isinstance(loc, dict) and isinstance(loc.get("name"), str) and loc["name"].strip():
                    return " ".join(loc["name"].split())
                stack.extend(v for v in d.values() if isinstance(v, (dict, list)))
    return None


def parse_venue(html: str) -> str | None:
    soup = BeautifulSoup(html, "html.parser")
    v = _jsonld_venue(soup)
    if v:
        return v
    for s in soup.find_all(string=VENUE_RE):
        if s.parent is not None and s.parent.name in ("script", "style"):
            continue
        t = " ".join(str(s).split()).strip(" \"'")
        if 4 < len(t) < 90:
            return t
    return None


class Client:
    def __init__(self, delay: float = config.REQUEST_DELAY_S):
        self.s = requests.Session()
        self.s.headers.update({
            "User-Agent": config.USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
            "Accept-Language": "tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7",
            "Sec-Ch-Ua": '"Chromium";v="128", "Not;A=Brand";v="24", "Google Chrome";v="128"',
            "Sec-Ch-Ua-Mobile": "?0",
            "Sec-Ch-Ua-Platform": '"Windows"',
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-User": "?1",
            "Upgrade-Insecure-Requests": "1",
        })
        self.delay = delay
        self._last = 0.0

    def get(self, url: str, params: dict | None = None) -> str:
        for attempt in range(4):
            wait = self.delay - (time.monotonic() - self._last)
            if wait > 0:
                time.sleep(wait)
            self._last = time.monotonic()
            try:
                r = self.s.get(url, params=params, timeout=20)
                if r.status_code in (429, 500, 502, 503, 504):
                    raise requests.HTTPError(f"HTTP {r.status_code}")
                r.raise_for_status()
                return r.text
            except requests.RequestException as e:
                if attempt == 3:
                    raise
                log.warning("Tekrar deneniyor (%s): %s", e, url)
                time.sleep(2 ** attempt)
        raise RuntimeError("unreachable")

    def fixture(self, league: dict, week: int | None = None) -> tuple[list[Match], dict]:
        url = f"{config.BASE_URL}/ligler/{league['path']}/fikstur"
        html = self.get(url, {"hafta": week} if week else None)
        return parse_fixture_page(html, league["key"], week)

    def venue(self, match_no: int) -> str | None:
        return parse_venue(self.get(f"{config.BASE_URL}/maclar/{match_no}"))


def scrape_league(client: Client, league: dict, mode: str) -> tuple[list[Match], set[int]]:
    """(maçlar, tam taranan haftalar) döner.

    full : tüm haftalar (sayfadaki hafta linkleri + boş sayfa gelene kadar ileri)
    quick: sitenin varsayılan gösterdiği güncel hafta ve çevresi (-1..+2)
    """
    first, meta = client.fixture(league)
    shown = meta["shown_week"]
    if mode == "quick" and shown:
        weeks = [w for w in range(shown - 1, shown + 3) if w >= 1]
    else:
        known = set(meta["weeks"]) or {1}
        weeks = list(range(1, max(known) + 1))

    out: dict[int, Match] = {}
    done: set[int] = set()
    logos: dict[str, str] = {}
    undated = 0

    def fetch(w: int) -> bool:
        """Haftayı tarar; hafta sitede yoksa (site varsayılan haftaya düşerse) False."""
        nonlocal undated
        ms, meta = client.fixture(league, w)
        if meta["shown_week"] is not None and meta["shown_week"] != w:
            log.debug("%s: %d. hafta yok (site %s. haftayı gösterdi)", league["key"], w, meta["shown_week"])
            return False
        done.add(w)
        undated += meta.get("undated", 0)
        logos.update(meta.get("logos", {}))
        for m in ms:
            out[m.match_no] = m
        return bool(ms) or meta.get("undated", 0) > 0

    for w in weeks:
        fetch(w)
    if mode != "quick":
        # 2. devre linkleri ilk sayfada görünmeyebilir: hafta bulunamayana kadar devam
        w, empty = max(weeks) + 1 if weeks else 1, 0
        while w <= config.MAX_WEEKS and empty < 2:
            empty = 0 if fetch(w) else empty + 1
            w += 1
    log.info("%s: %d maç, %d hafta (%s)%s", league["key"], len(out), len(done), mode,
             f", tarihi açıklanmamış {undated} maç atlandı" if undated else "")
    return list(out.values()), done, logos
