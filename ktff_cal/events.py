"""Maçtan takvim etkinliğine dönüşüm (ICS ve Google Calendar ortak kullanır) + takvim listesi."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from . import config
from .scrape import Match

TZ = ZoneInfo(config.TIMEZONE)
LEAGUE_NAMES = {lg["key"]: lg["name"] for lg in config.LEAGUES}

_TR = str.maketrans("çğıöşüÇĞİÖŞÜâîû", "cgiosucgiosuaiu")


def slugify(name: str) -> str:
    s = name.translate(_TR)
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


@dataclass
class EventView:
    uid: str
    summary: str
    description: str
    location: str | None
    start: datetime | date  # datetime -> yerel saat (tz-aware), date -> tüm gün
    end: datetime | date
    url: str


def event_for(m: Match) -> EventView:
    lig = LEAGUE_NAMES.get(m.league, m.league)
    if m.played:
        summary = f"{m.home} {m.home_score}–{m.away_score} {m.away}"
    else:
        summary = f"{m.home} – {m.away}"
    if m.status:
        summary += f" ({m.status})"

    lines = [f"{lig} · {m.week}. Hafta", f"Maç No: {m.match_no}"]
    if not m.time:
        lines.append("Saat henüz açıklanmadı.")
    lines.append(m.url)

    d = date.fromisoformat(m.date)
    if m.time:
        hh, mm = map(int, m.time.split(":"))
        start = datetime(d.year, d.month, d.day, hh, mm, tzinfo=TZ)
        end = start + timedelta(minutes=config.MATCH_DURATION_MIN)
    else:
        start, end = d, d + timedelta(days=1)
    return EventView(uid=f"ktff-{m.match_no}@ktff-takvim", summary=summary,
                     description="\n".join(lines), location=m.venue,
                     start=start, end=end, url=m.url)


@dataclass
class CalendarSpec:
    key: str  # "lig/super-lig" veya "takim/magusa-turk-gucu"
    name: str
    description: str
    league: str | None  # takım takvimlerinde takımın (en son) ligi
    team: str | None
    matches: list[Match]

    @property
    def file(self) -> str:
        return f"{self.key}.ics"


def calendar_specs(matches: dict[int, Match]) -> list[CalendarSpec]:
    specs: list[CalendarSpec] = []
    by_league: dict[str, list[Match]] = {}
    by_team: dict[str, list[Match]] = {}
    for m in sorted(matches.values(), key=lambda x: (x.date, x.time or "", x.match_no)):
        by_league.setdefault(m.league, []).append(m)
        by_team.setdefault(m.home, []).append(m)
        by_team.setdefault(m.away, []).append(m)

    for lg in config.LEAGUES:
        ms = by_league.get(lg["key"])
        if ms:
            specs.append(CalendarSpec(
                key=f"lig/{lg['key']}", name=f"{lg['name']} Fikstürü",
                description=f"{lg['name']} tüm maçları. Kaynak: ktff.org",
                league=lg["key"], team=None, matches=ms))
    for team in sorted(by_team, key=lambda t: slugify(t)):
        ms = by_team[team]
        specs.append(CalendarSpec(
            key=f"takim/{slugify(team)}", name=f"{team} Fikstürü",
            description=f"{team} maçları. Kaynak: ktff.org",
            league=ms[-1].league, team=team, matches=ms))
    return specs
