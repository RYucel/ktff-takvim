"""data/matches.json: tüm maçların kalıcı kaydı (repo içinde commit'lenir)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from . import config
from .scrape import Match

PATH = config.DATA_DIR / "matches.json"


def load(path: Path = PATH) -> dict[int, Match]:
    if not path.exists():
        return {}
    raw = json.loads(path.read_text(encoding="utf-8"))
    return {int(k): Match.from_dict(v) for k, v in raw.items()}


def save(matches: dict[int, Match], path: Path = PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {str(k): matches[k].to_dict() for k in sorted(matches)}
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


def merge(store: dict[int, Match], fresh: list[Match], league: str, weeks_scraped: set[int]) -> list[Match]:
    """Taze veriyi kayda işler; değişen maçların rev'ini artırır. Değişenleri döner.

    Taranan haftalarda artık görünmeyen maçlar silinir (fikstürden kaldırılmış demektir).
    Venue sadece detay sayfasından gelir, liste sayfası onu ezmemeli.
    """
    now = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    changed: list[Match] = []
    fresh_nos = {m.match_no for m in fresh}
    for m in fresh:
        old = store.get(m.match_no)
        if old:
            m.venue = m.venue or old.venue
            m.rev = old.rev
            m.extra = old.extra
            if old.content_key() != m.content_key():
                m.rev += 1
                m.extra["stamp"] = now
                changed.append(m)
        else:
            m.extra["stamp"] = now
            changed.append(m)
        store[m.match_no] = m
    for no in [n for n, m in store.items()
               if m.league == league and m.week in weeks_scraped and n not in fresh_nos]:
        del store[no]
    return changed
