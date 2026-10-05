"""RFC 5545 iCalendar üretimi (bağımlılık yok). Saatler UTC yazılır, VTIMEZONE gerekmez."""

from __future__ import annotations

from datetime import date, datetime, timezone

from .events import CalendarSpec, event_for

PRODID = "-//ktff-takvim//TR"


def _esc(s: str) -> str:
    return (s.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,")
             .replace("\r\n", "\\n").replace("\n", "\\n"))


def _fold(line: str) -> str:
    """75 oktet sınırında katla (UTF-8 karakterlerini bölmeden)."""
    out, cur, size = [], "", 0
    for ch in line:
        b = len(ch.encode("utf-8"))
        if size + b > 75:
            out.append(cur)
            cur, size = " ", 1
        cur += ch
        size += b
    out.append(cur)
    return "\r\n".join(out)


def _dt(v: datetime | date) -> str:
    if isinstance(v, datetime):
        return ":" + v.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return ";VALUE=DATE:" + v.strftime("%Y%m%d")


def build(spec: CalendarSpec, stamp: datetime | None = None) -> str:
    stamp = stamp or datetime.now(timezone.utc)
    st = stamp.strftime("%Y%m%dT%H%M%SZ")
    lines = [
        "BEGIN:VCALENDAR", "VERSION:2.0", f"PRODID:{PRODID}", "CALSCALE:GREGORIAN", "METHOD:PUBLISH",
        f"X-WR-CALNAME:{_esc(spec.name)}", f"X-WR-CALDESC:{_esc(spec.description)}",
        "X-WR-TIMEZONE:Europe/Nicosia",
        "REFRESH-INTERVAL;VALUE=DURATION:PT1H", "X-PUBLISHED-TTL:PT1H",
    ]
    for m in spec.matches:
        ev = event_for(m)
        lines += [
            "BEGIN:VEVENT",
            f"UID:{ev.uid}",
            f"DTSTAMP:{m.extra.get('stamp', st)}",
            f"SEQUENCE:{m.rev}",
            f"DTSTART{_dt(ev.start)}",
            f"DTEND{_dt(ev.end)}",
            f"SUMMARY:{_esc(ev.summary)}",
            f"DESCRIPTION:{_esc(ev.description)}",
            f"URL:{ev.url}",
            "TRANSP:TRANSPARENT",
            "STATUS:CONFIRMED",
        ]
        if ev.location:
            lines.append(f"LOCATION:{_esc(ev.location)}")
        # Bildirim alarmları: Maçtan 2 saat önce ve 15 dakika önce
        lines += [
            "BEGIN:VALARM",
            "ACTION:DISPLAY",
            f"DESCRIPTION:⚽ Maç Hatırlatması: {_esc(ev.summary)}",
            "TRIGGER:-PT2H",
            "END:VALARM",
            "BEGIN:VALARM",
            "ACTION:DISPLAY",
            f"DESCRIPTION:⏱️ Maç 15 dk sonra başlıyor! {_esc(ev.summary)}",
            "TRIGGER:-PT15M",
            "END:VALARM",
        ]
        lines.append("END:VEVENT")
    lines.append("END:VCALENDAR")
    return "\r\n".join(_fold(l) for l in lines) + "\r\n"
