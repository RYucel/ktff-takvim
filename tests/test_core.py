from datetime import datetime, timezone
from pathlib import Path

from ktff_cal import ics, store
from ktff_cal.events import calendar_specs, slugify
from ktff_cal.gcal import event_body
from ktff_cal.scrape import parse_fixture_page, parse_match_text, parse_venue

FX = Path(__file__).parent / "fixtures"


def page():
    return parse_fixture_page((FX / "week4.html").read_text(encoding="utf-8"), "super-lig", 4)


def test_parse_page():
    ms, meta = page()
    by = {m.match_no: m for m in ms}
    assert set(by) == {25352, 25350, 25351, 25399}
    assert meta["weeks"] == [1, 2, 3, 4, 15] and meta["shown_week"] == 4
    a = by[25352]
    assert (a.home, a.away, a.date, a.time, a.home_score, a.away_score) == (
        "Doğan Türk Birliği", "China Bazaar Gençlik Gücü TSK", "2026-10-02", "19:00", 1, 1)
    b = by[25350]
    assert (b.home, b.away, b.date, b.time, b.played) == ("Mağusa Türk Gücü", "Yenicami AK", "2026-10-04", "15:30", False)
    assert by[25351].time is None and by[25351].home == "Çetinkaya TSK"
    assert by[25399].status == "Ertelendi"


def test_text_variants():
    t = parse_match_text("Mesarya SK Mesarya SK 15:30 3 - 3 Maç No: 25348 Küçük Kaymaklı TSK Küçük Kaymaklı TSK")
    assert t["home"] == "Mesarya SK" and t["away"] == "Küçük Kaymaklı TSK" and (t["home_score"], t["away_score"]) == (3, 3)
    t = parse_match_text("Karşıyaka SK 3 - 0 Maç No: 1 Değirmenlik SK")
    assert t["time"] is None and t["home"] == "Karşıyaka SK" and t["home_score"] == 3
    assert parse_match_text("Haberler") is None


def test_venue():
    assert parse_venue((FX / "match.html").read_text(encoding="utf-8")) == "Gazimağusa Dr. Fazıl Küçük Stadı"


def test_merge_rev():
    s = {}
    ms, _ = page()
    assert len(store.merge(s, ms, "super-lig", {4})) == 4
    ms2, _ = page()
    assert store.merge(s, ms2, "super-lig", {4}) == []
    ms3, _ = page()
    ms3 = [m for m in ms3 if m.match_no != 25351]
    for m in ms3:
        if m.match_no == 25350:
            m.time = "18:00"
    ch = store.merge(s, ms3, "super-lig", {4})
    assert [m.match_no for m in ch] == [25350] and s[25350].rev == 1 and 25351 not in s


def test_ics_and_gcal():
    s = {}
    store.merge(s, page()[0], "super-lig", {4})
    specs = calendar_specs(s)
    keys = [x.key for x in specs]
    assert "lig/super-lig" in keys and "takim/magusa-turk-gucu" in keys and "takim/cetinkaya-tsk" in keys
    txt = ics.build(next(x for x in specs if x.key == "takim/magusa-turk-gucu"))
    assert "DTSTART:20261004T123000Z" in txt  # 15:30 EEST = 12:30 UTC
    assert all(len(l.encode()) <= 75 for l in txt.split("\r\n"))
    allday = ics.build(next(x for x in specs if x.key == "takim/cetinkaya-tsk"))
    assert "DTSTART;VALUE=DATE:20261004" in allday and "DTEND;VALUE=DATE:20261005" in allday
    b = event_body(s[25350])
    assert b["id"] == "ktff25350" and b["start"]["dateTime"].startswith("2026-10-04T15:30:00+03:00")


def test_slug():
    assert slugify("Çetinkaya TSK") == "cetinkaya-tsk"
    assert slugify("Değirmenlik SK") == "degirmenlik-sk"
    assert slugify("Küçük Kaymaklı TSK") == "kucuk-kaymakli-tsk"
