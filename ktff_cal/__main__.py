"""Kullanım:
  python -m ktff_cal --mode quick   # güncel hafta ±; cron-job.org her 15 dk tetikler
  python -m ktff_cal --mode full    # tüm sezon; günde 1 kez
  python -m ktff_cal --offline      # siteye gitmeden, kayıtlı veriden ICS/sayfa üret
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime, timezone

from . import config, gcal, site, store
from .events import calendar_specs
from .scrape import Client, scrape_league

log = logging.getLogger("ktff_cal")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="ktff_cal")
    ap.add_argument("--mode", choices=["quick", "full"], default="quick")
    ap.add_argument("--offline", action="store_true", help="scrape etme, kayıtlı veriyi kullan")
    ap.add_argument("--no-gcal", action="store_true", help="Google Calendar senkronunu atla")
    ap.add_argument("--venue-limit", type=int, default=None,
                    help="tek çalıştırmada en fazla kaç saha sorgusu (varsayılan quick=15, full=500)")
    ap.add_argument("-v", "--verbose", action="store_true")
    a = ap.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if a.verbose else logging.INFO,
                        format="%(levelname)s %(name)s: %(message)s")

    matches = store.load()
    team_logos = store.load_logos()
    failures = 0
    if not a.offline:
        client = Client()
        for lg in [l for l in config.LEAGUES if l["enabled"]]:
            try:
                fresh, weeks, logos = scrape_league(client, lg, a.mode)
                team_logos.update(logos)
            except Exception as e:  # bir lig patlarsa diğerleri yine güncellensin
                log.error("%s taranamadı: %s", lg["key"], e)
                failures += 1
                continue
            if not fresh and matches:
                log.warning("%s boş döndü, kayıt korunuyor.", lg["key"])
                continue
            changed = store.merge(matches, fresh, lg["key"], weeks)
            log.info("%s: %d değişiklik", lg["key"], len(changed))
        store.save_logos(team_logos)

        # Saha bilgisi: sadece bilinmeyenler için, önce yaklaşan maçlar
        today = datetime.now(timezone.utc).date().isoformat()
        limit = a.venue_limit if a.venue_limit is not None else (15 if a.mode == "quick" else 500)
        todo = sorted((m for m in matches.values()
                       if not m.venue and m.extra.get("venue_tries", 0) < 3),
                      key=lambda m: (m.date < today, m.date))[:limit]
        for m in todo:
            m.extra["venue_tries"] = m.extra.get("venue_tries", 0) + 1
            try:
                v = client.venue(m.match_no)
            except Exception as e:
                log.warning("Saha alınamadı %s: %s", m.match_no, e)
                continue
            if v:
                m.venue = v
                m.rev += 1
                m.extra["stamp"] = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        store.save(matches)

    if not matches:
        log.error("Hiç maç yok; çıkılıyor.")
        return 1

    specs = calendar_specs(matches)
    state = gcal.load_state()
    if not a.no_gcal:
        if gcal.sync(specs, state) is not None:
            gcal.save_state(state)
    n = site.build(specs, state, team_logos=team_logos)
    log.info("%d takvim, %d maç; %d dosya değişti.", len(specs), len(matches), n)
    if failures:
        log.warning("%d lig taranamadı, mevcut takvim ve maç verileri aynen korundu.", failures)
    return 0


if __name__ == "__main__":
    sys.exit(main())
