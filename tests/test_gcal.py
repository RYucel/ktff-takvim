"""Google Calendar katmanını sahte bir servisle test eder (ağ yok)."""
import json

from googleapiclient.errors import HttpError

from ktff_cal import store
from ktff_cal.events import calendar_specs
from ktff_cal.gcal import Syncer
from tests.test_core import page


class Resp(dict):
    def __init__(self, status):
        super().__init__(status=str(status)); self.status = status; self.reason = ""


class Req:
    def __init__(self, fn): self.fn = fn
    def execute(self): return self.fn()


class FakeSvc:
    def __init__(self):
        self.cals, self.acls, self.calls = {}, [], []
    def calendars(self): return self
    def acl(self): return self
    def events(self): return self
    def insert(self, calendarId=None, body=None, sendNotifications=None):
        def run():
            if calendarId is None:  # calendars().insert
                cid = f"cal{len(self.cals)}@group.calendar.google.com"
                self.cals[cid] = {}
                return {"id": cid}
            if "scope" in body:  # acl
                self.acls.append((calendarId, body["role"], body["scope"]["type"])); return {}
            if body["id"] in self.cals[calendarId]:
                raise HttpError(Resp(409), b'{"error":{"errors":[{"reason":"duplicate"}]}}')
            self.calls.append(("insert", body["id"])); self.cals[calendarId][body["id"]] = body; return body
        return Req(run)
    def update(self, calendarId, eventId, body):
        def run():
            self.calls.append(("update", eventId)); self.cals[calendarId][eventId] = body; return body
        return Req(run)
    def delete(self, calendarId, eventId):
        def run():
            self.calls.append(("delete", eventId)); self.cals[calendarId].pop(eventId, None); return {}
        return Req(run)


def test_sync_cycle():
    s = {}; store.merge(s, page()[0], "super-lig", {4})
    svc, state = FakeSvc(), {"calendars": {}, "events": {}}
    sy = Syncer(svc, state, "owner@example.com")
    for sp in calendar_specs(s): sy.sync_calendar(sp)
    n_cal = len(calendar_specs(s))
    assert sy.stats["created_cal"] == n_cal and len(svc.cals) == n_cal
    assert sum(1 for a in svc.acls if a[2] == "default") == n_cal
    assert sum(1 for a in svc.acls if a[1] == "owner") == n_cal
    first = len(svc.calls)

    # Değişiklik yoksa API çağrısı yok
    sy2 = Syncer(svc, state)
    for sp in calendar_specs(s): sy2.sync_calendar(sp)
    assert len(svc.calls) == first and sy2.stats["insert"] == sy2.stats["update"] == 0

    # Saat değişince sadece o maçın olduğu takvimler güncellenir; kaldırılan maç silinir
    ms = page()[0]
    ms = [m for m in ms if m.match_no != 25351]
    for m in ms:
        if m.match_no == 25350: m.time = "18:00"
    store.merge(s, ms, "super-lig", {4})
    sy3 = Syncer(svc, state)
    specs = calendar_specs(s)
    for sp in specs: sy3.sync_calendar(sp)
    sy3.prune(specs)
    assert sy3.stats["update"] == 3  # lig + 2 takım
    assert sy3.stats["delete"] == 3  # 25351: lig + Çetinkaya + Dumlupınar
    assert sy3.stats["created_cal"] == 0
    lig = state["calendars"]["lig/super-lig"]
    assert svc.cals[lig]["ktff25350"]["start"]["dateTime"].startswith("2026-10-04T18:00")
