"""Google Calendar katmanı.

Her lig ve takım için service account'a ait PUBLIC bir Google takvimi oluşturur ve maçları
doğrudan yazar. Böylece Google kullanıcıları ICS'nin 8-24 saatlik yenileme gecikmesini yaşamaz:
abone oldukları takvim, değişiklik yazıldığı anda güncellenir.

Durum dosyası data/gcal_state.json:
  {"calendars": {"takim/x": "<calendarId>"}, "events": {"<calendarId>": {"ktff25352": "<hash>"}}}
Sadece içeriği değişen etkinlikler API'ye gider (kota dostu).

Ortam değişkenleri:
  GCP_SA_KEY       service account JSON anahtarının tamamı (GitHub secret)
  CAL_OWNER_EMAIL  (opsiyonel) takvimlerin sahiplik yetkisi verilecek Google hesabı
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import time
from datetime import date, datetime
from pathlib import Path

from . import config
from .events import CalendarSpec, event_for
from .scrape import Match

log = logging.getLogger(__name__)
STATE_PATH = config.DATA_DIR / "gcal_state.json"
SCOPES = ["https://www.googleapis.com/auth/calendar"]


def service_from_env():
    key = os.environ.get("GCP_SA_KEY", "").strip()
    if not key:
        return None
    from google.oauth2 import service_account
    from googleapiclient.discovery import build

    creds = service_account.Credentials.from_service_account_info(json.loads(key), scopes=SCOPES)
    return build("calendar", "v3", credentials=creds, cache_discovery=False)


def load_state(path: Path = STATE_PATH) -> dict:
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {"calendars": {}, "events": {}}


def save_state(state: dict, path: Path = STATE_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8")


def event_id(m: Match) -> str:
    # Google event id: base32hex karakterleri (a-v, 0-9), 5-1024 uzunluk.
    return f"ktff{m.match_no}"


def event_body(m: Match) -> dict:
    ev = event_for(m)
    if isinstance(ev.start, datetime):
        start = {"dateTime": ev.start.isoformat(), "timeZone": config.TIMEZONE}
        end = {"dateTime": ev.end.isoformat(), "timeZone": config.TIMEZONE}
    else:
        assert isinstance(ev.start, date)
        start, end = {"date": ev.start.isoformat()}, {"date": ev.end.isoformat()}
    body = {
        "id": event_id(m),
        "summary": ev.summary,
        "description": ev.description,
        "start": start,
        "end": end,
        "status": "confirmed",
        "transparency": "transparent",
        "source": {"title": "KTFF", "url": ev.url},
    }
    if ev.location:
        body["location"] = ev.location
    return body


def _hash(body: dict) -> str:
    return hashlib.sha1(json.dumps(body, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:16]


def _call(req, *, retries: int = 5):
    from googleapiclient.errors import HttpError

    for attempt in range(retries):
        try:
            return req.execute()
        except HttpError as e:
            status = e.resp.status
            reason = ""
            try:
                reason = json.loads(e.content)["error"]["errors"][0]["reason"]
            except Exception:
                pass
            retryable = status in (429, 500, 502, 503) or (
                status == 403 and reason in ("rateLimitExceeded", "userRateLimitExceeded"))
            if not retryable or attempt == retries - 1:
                raise
            time.sleep(min(2 ** attempt + 0.5, 30))


class Syncer:
    def __init__(self, svc, state: dict, owner_email: str | None = None):
        self.svc = svc
        self.state = state
        self.owner = owner_email
        self.stats = {"created_cal": 0, "insert": 0, "update": 0, "delete": 0, "skip": 0, "error": 0}

    def ensure_calendar(self, spec: CalendarSpec) -> str | None:
        cid = self.state["calendars"].get(spec.key)
        if cid:
            return cid
        from googleapiclient.errors import HttpError

        try:
            cal = _call(self.svc.calendars().insert(body={
                "summary": spec.name, "description": spec.description, "timeZone": config.TIMEZONE}))
            cid = cal["id"]
            _call(self.svc.acl().insert(calendarId=cid, body={"role": "reader", "scope": {"type": "default"}}))
            if self.owner:
                _call(self.svc.acl().insert(calendarId=cid, sendNotifications=False, body={
                    "role": "owner", "scope": {"type": "user", "value": self.owner}}))
        except HttpError as e:
            # Google kısa sürede çok takvim oluşturmayı sınırlar; kalanlar sonraki çalıştırmada.
            log.error("Takvim oluşturulamadı (%s): %s", spec.key, e)
            self.stats["error"] += 1
            return None
        self.state["calendars"][spec.key] = cid
        self.state["events"].setdefault(cid, {})
        self.stats["created_cal"] += 1
        log.info("Takvim oluşturuldu: %s -> %s", spec.key, cid)
        return cid

    def prune(self, specs: list[CalendarSpec]) -> None:
        """Artık hiç maçı olmayan takvimlerin etkinliklerini temizler (takvimi silmez; aboneler kopmasın)."""
        live = {s.key for s in specs}
        for key in [k for k in self.state["calendars"] if k not in live]:
            empty = CalendarSpec(key=key, name="", description="", league=None, team=None, matches=[])
            self.sync_calendar(empty)

    def sync_calendar(self, spec: CalendarSpec) -> None:
        from googleapiclient.errors import HttpError

        cid = self.ensure_calendar(spec)
        if not cid:
            return
        known: dict = self.state["events"].setdefault(cid, {})
        wanted = {}
        for m in spec.matches:
            body = event_body(m)
            wanted[body["id"]] = body

        for eid, body in wanted.items():
            h = _hash(body)
            if known.get(eid) == h:
                self.stats["skip"] += 1
                continue
            try:
                if eid in known:
                    _call(self.svc.events().update(calendarId=cid, eventId=eid, body=body))
                    self.stats["update"] += 1
                else:
                    try:
                        _call(self.svc.events().insert(calendarId=cid, body=body))
                        self.stats["insert"] += 1
                    except HttpError as e:
                        if e.resp.status != 409:  # 409: id zaten var (silinmiş olabilir) -> update
                            raise
                        _call(self.svc.events().update(calendarId=cid, eventId=eid, body=body))
                        self.stats["update"] += 1
                known[eid] = h
            except HttpError as e:
                log.error("Etkinlik yazılamadı %s/%s: %s", spec.key, eid, e)
                self.stats["error"] += 1

        for eid in [e for e in known if e not in wanted]:
            try:
                _call(self.svc.events().delete(calendarId=cid, eventId=eid))
            except HttpError as e:
                if e.resp.status not in (404, 410):
                    log.error("Etkinlik silinemedi %s/%s: %s", spec.key, eid, e)
                    self.stats["error"] += 1
                    continue
            known.pop(eid, None)
            self.stats["delete"] += 1


def sync(specs: list[CalendarSpec], state: dict) -> dict | None:
    svc = service_from_env()
    if svc is None:
        log.info("GCP_SA_KEY yok, Google Calendar senkronu atlandı.")
        return None
    syncer = Syncer(svc, state, os.environ.get("CAL_OWNER_EMAIL") or None)
    for spec in specs:
        syncer.sync_calendar(spec)
        save_state(state)  # yarıda kesilirse ilerleme kaybolmasın
    syncer.prune(specs)
    log.info("Google Calendar: %s", syncer.stats)
    return syncer.stats


def subscribe_url(calendar_id: str) -> str:
    from urllib.parse import quote

    return f"https://calendar.google.com/calendar/render?cid={quote(calendar_id)}"
