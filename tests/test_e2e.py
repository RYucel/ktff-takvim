"""Uçtan uca: sahte KTFF sunucusu ile full + quick çalıştırma, ICS'lerin geçerliliği."""
from pathlib import Path

import icalendar

from ktff_cal import __main__ as cli, config, gcal, site, store
from ktff_cal.scrape import Client

FX = Path(__file__).parent / "fixtures"
EMPTY = "<html><body><h3>9. Hafta</h3></body></html>"


def fake_get(self, url, params=None):
    if "/maclar/" in url:
        return (FX / "match.html").read_text(encoding="utf-8")
    if "aksa-super-lig" in url and (params is None or params.get("hafta") == 4):
        return (FX / "week4.html").read_text(encoding="utf-8")
    return EMPTY


def test_run(tmp_path, monkeypatch):
    monkeypatch.setattr(Client, "get", fake_get)
    monkeypatch.setattr(store, "PATH", tmp_path / "data/matches.json")
    monkeypatch.setattr(gcal, "STATE_PATH", tmp_path / "data/gcal_state.json")
    monkeypatch.setattr(config, "SITE_DIR", tmp_path / "docs")
    monkeypatch.setattr(site.build, "__defaults__", (tmp_path / "docs",))
    monkeypatch.setattr(store.load, "__defaults__", (tmp_path / "data/matches.json",))
    monkeypatch.setattr(store.save, "__defaults__", (tmp_path / "data/matches.json",))
    monkeypatch.setattr(gcal.load_state, "__defaults__", (tmp_path / "data/gcal_state.json",))
    monkeypatch.setattr(gcal.save_state, "__defaults__", (tmp_path / "data/gcal_state.json",))
    monkeypatch.delenv("GCP_SA_KEY", raising=False)
    monkeypatch.setenv("SITE_URL", "https://example.github.io/ktff-takvim")

    assert cli.main(["--mode", "full"]) == 0
    docs = tmp_path / "docs"
    files = sorted(p.relative_to(docs).as_posix() for p in docs.rglob("*.ics"))
    assert "lig/super-lig.ics" in files and "takim/magusa-turk-gucu.ics" in files
    for f in docs.rglob("*.ics"):
        cal = icalendar.Calendar.from_ical(f.read_bytes())
        assert len(cal.walk("VEVENT")) >= 1
    ev = [e for e in icalendar.Calendar.from_ical((docs / "lig/super-lig.ics").read_bytes()).walk("VEVENT")
          if str(e["UID"]).startswith("ktff-25350")][0]
    assert str(ev["LOCATION"]) == "Gazimağusa Dr. Fazıl Küçük Stadı"
    assert "Mağusa Türk Gücü" in (docs / "index.html").read_text(encoding="utf-8")

    # İkinci çalıştırma: değişiklik yoksa hiçbir dosya değişmemeli (gereksiz commit olmasın)
    before = {p: p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    assert cli.main(["--mode", "quick"]) == 0
    after = {p: p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    assert before == after
