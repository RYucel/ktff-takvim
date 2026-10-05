"""docs/ altına ICS dosyalarını ve abone olma sayfasını (index.html) yazar."""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path

from . import config, ics
from .events import TZ, CalendarSpec, LEAGUE_NAMES, event_for
from .gcal import subscribe_url
from .scrape import Match


def site_url() -> str:
    return os.environ.get("SITE_URL", "").rstrip("/")


def _write_if_changed(path: Path, content: str) -> bool:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.read_text(encoding="utf-8") == content:
        return False
    path.write_text(content, encoding="utf-8", newline="")
    return True


def _next_match(ms: list[Match], now: datetime) -> dict | None:
    today = now.date().isoformat()
    for m in ms:
        if not m.played and m.date >= today:
            ev = event_for(m)
            return {"date": m.date, "time": m.time, "summary": ev.summary, "venue": m.venue}
    return None


def build(specs: list[CalendarSpec], gcal_state: dict | None, team_logos: dict[str, str] | None = None, out: Path = config.SITE_DIR) -> int:
    changed = 0
    keep = set()
    for spec in specs:
        p = out / spec.file
        keep.add(p)
        changed += _write_if_changed(p, ics.build(spec))
    # Artık olmayan takımların eski ICS dosyalarını temizle
    for old in out.glob("*/*.ics"):
        if old not in keep:
            old.unlink()
            changed += 1

    now = datetime.now(TZ)
    cals = (gcal_state or {}).get("calendars", {})
    logos = team_logos or {}
    items = []
    for s in specs:
        team_name = s.team or s.name.replace(" Fikstürü", "")
        logo = logos.get(team_name) if s.team else None
        items.append({
            "key": s.key, "name": s.name.replace(" Fikstürü", ""),
            "type": "team" if s.team else "league",
            "league": s.league, "leagueName": LEAGUE_NAMES.get(s.league or "", ""),
            "logo": logo,
            "ics": s.file, "google": subscribe_url(cals[s.key]) if s.key in cals else None,
            "count": len(s.matches), "next": _next_match(s.matches, now),
        })
    leagues = [{"key": lg["key"], "name": lg["name"]} for lg in config.LEAGUES
               if any(i["league"] == lg["key"] for i in items)]
    page = TEMPLATE.replace("__DATA__", json.dumps(
        {"items": items, "leagues": leagues, "base": site_url()}, ensure_ascii=False).replace("</", "<\\/"))
    changed += _write_if_changed(out / "index.html", page)
    changed += _write_if_changed(out / ".nojekyll", "")
    return changed


TEMPLATE = r"""<!doctype html>
<html lang="tr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>KKTC Futbol Takvimi</title>
<meta name="description" content="KKTC Süper Lig ve 1. Lig fikstürlerini Google Takvim, Apple Takvim ve Outlook'a ücretsiz ekle. Logolar, saatler ve skorlar anında güncellenir.">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&display=swap" rel="stylesheet">
<style>
:root {
  --bg: #0f1115;
  --surface: #181a20;
  --surface-hover: #22252d;
  --surface-active: #2a2e38;
  --card: #14161b;
  --card-border: #262933;
  --ink: #f3f4f6;
  --ink-secondary: #9ca3af;
  --mute: #6b7280;
  --acc: #e11d48;
  --acc-glow: rgba(225, 29, 72, 0.25);
  --acc-ink: #ffffff;
  --chip: #1e2129;
  --google: #4285f4;
  --apple: #9ca3af;
  --outlook: #0078d4;
  --radius-lg: 18px;
  --radius-md: 12px;
  --radius-sm: 8px;
}
@media (prefers-color-scheme: light) {
  :root {
    --bg: #f8fafc;
    --surface: #ffffff;
    --surface-hover: #f1f5f9;
    --surface-active: #e2e8f0;
    --card: #ffffff;
    --card-border: #e2e8f0;
    --ink: #0f172a;
    --ink-secondary: #475569;
    --mute: #94a3b8;
    --acc: #e11d48;
    --acc-glow: rgba(225, 29, 72, 0.15);
    --acc-ink: #ffffff;
    --chip: #f1f5f9;
    --google: #2563eb;
    --apple: #334155;
    --outlook: #0284c7;
  }
}
* { box-sizing: border-box; }
body {
  margin: 0;
  background: var(--bg);
  color: var(--ink);
  font-family: 'Plus Jakarta Sans', system-ui, -apple-system, sans-serif;
  -webkit-font-smoothing: antialiased;
  min-height: 100vh;
}
.wrap {
  max-width: 920px;
  margin: 0 auto;
  padding: 40px 20px 80px;
}
header {
  margin-bottom: 32px;
}
.badge-hero {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 6px 14px;
  background: var(--surface);
  border: 1px solid var(--card-border);
  border-radius: 999px;
  font-size: 13px;
  font-weight: 600;
  color: var(--acc);
  margin-bottom: 16px;
  box-shadow: 0 2px 8px rgba(0,0,0,0.05);
}
header h1 {
  font-size: clamp(32px, 6vw, 48px);
  font-weight: 800;
  line-height: 1.1;
  margin: 0 0 12px;
  letter-spacing: -0.03em;
}
header h1 span {
  background: linear-gradient(135deg, var(--acc) 0%, #ff6b81 100%);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
}
header p {
  margin: 0;
  color: var(--ink-secondary);
  font-size: 16px;
  line-height: 1.6;
  max-width: 60ch;
}
.controls {
  display: flex;
  flex-direction: column;
  gap: 16px;
  margin: 32px 0 24px;
  background: var(--surface);
  border: 1px solid var(--card-border);
  border-radius: var(--radius-lg);
  padding: 16px 20px;
  box-shadow: 0 4px 20px rgba(0,0,0,0.08);
}
.filters-row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 14px;
}
.league-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
.league-chips button {
  border: 1px solid var(--card-border);
  background: var(--chip);
  color: var(--ink-secondary);
  padding: 8px 18px;
  border-radius: 999px;
  font-family: inherit;
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s ease;
}
.league-chips button:hover {
  background: var(--surface-hover);
  color: var(--ink);
}
.league-chips button[aria-pressed=true] {
  background: var(--acc);
  color: var(--acc-ink);
  border-color: var(--acc);
  box-shadow: 0 4px 12px var(--acc-glow);
}
.select-wrapper {
  position: relative;
  flex: 1 1 260px;
  max-width: 380px;
}
.team-select {
  width: 100%;
  appearance: none;
  background: var(--chip);
  color: var(--ink);
  border: 1px solid var(--card-border);
  border-radius: var(--radius-md);
  padding: 11px 40px 11px 16px;
  font-family: inherit;
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
  outline: none;
  transition: border-color 0.2s, box-shadow 0.2s;
}
.team-select:focus {
  border-color: var(--acc);
  box-shadow: 0 0 0 3px var(--acc-glow);
}
.select-arrow {
  position: absolute;
  right: 14px;
  top: 50%;
  transform: translateY(-50%);
  pointer-events: none;
  color: var(--mute);
  font-size: 12px;
}
.section-title {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 13px;
  text-transform: uppercase;
  letter-spacing: 0.1em;
  font-weight: 700;
  color: var(--mute);
  margin: 32px 0 16px;
}
.section-title::after {
  content: "";
  flex: 1;
  height: 1px;
  background: var(--card-border);
}
.list {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 14px;
}
.card {
  background: var(--card);
  border: 1px solid var(--card-border);
  border-radius: var(--radius-lg);
  padding: 18px 20px;
  display: flex;
  flex-direction: column;
  gap: 14px;
  transition: transform 0.2s ease, border-color 0.2s ease, box-shadow 0.2s ease;
}
.card:hover {
  transform: translateY(-2px);
  border-color: rgba(225, 29, 72, 0.4);
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.12);
}
.card.league {
  grid-column: 1 / -1;
  background: linear-gradient(135deg, var(--card) 0%, var(--surface) 100%);
  border-left: 4px solid var(--acc);
}
.top {
  display: flex;
  align-items: center;
  gap: 14px;
}
.team-logo {
  width: 44px;
  height: 44px;
  object-fit: contain;
  border-radius: var(--radius-sm);
  background: #ffffff;
  padding: 3px;
  box-shadow: 0 2px 6px rgba(0,0,0,0.1);
  flex-shrink: 0;
}
.league-icon {
  width: 44px;
  height: 44px;
  border-radius: var(--radius-sm);
  background: var(--surface-hover);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 20px;
  flex-shrink: 0;
}
.card-header-text {
  flex: 1;
  min-width: 0;
}
.name {
  font-weight: 700;
  font-size: 16px;
  color: var(--ink);
  line-height: 1.3;
  margin-bottom: 2px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.meta {
  color: var(--ink-secondary);
  font-size: 12px;
  font-weight: 500;
}
.next {
  background: var(--surface);
  border: 1px solid var(--card-border);
  border-radius: var(--radius-md);
  padding: 10px 12px;
  font-size: 13px;
  color: var(--ink-secondary);
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.next-title {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 11px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--acc);
}
.next-match {
  color: var(--ink);
  font-weight: 600;
  line-height: 1.4;
}
.next-details {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  font-size: 12px;
  color: var(--mute);
}
.acts {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px;
  margin-top: auto;
}
.acts a, .acts button {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  text-decoration: none;
  font-family: inherit;
  font-size: 13px;
  font-weight: 600;
  padding: 9px 12px;
  border-radius: var(--radius-sm);
  border: 1px solid var(--card-border);
  background: var(--chip);
  color: var(--ink);
  cursor: pointer;
  transition: all 0.15s ease;
}
.acts a:hover, .acts button:hover {
  background: var(--surface-hover);
  border-color: var(--mute);
}
.acts a.pri {
  grid-column: 1 / -1;
  background: linear-gradient(135deg, #1a73e8 0%, #1557b0 100%);
  border-color: #1a73e8;
  color: #ffffff;
  box-shadow: 0 4px 10px rgba(26, 115, 232, 0.25);
}
.acts a.pri:hover {
  background: linear-gradient(135deg, #1557b0 0%, #0d47a1 100%);
  box-shadow: 0 6px 14px rgba(26, 115, 232, 0.35);
  transform: translateY(-1px);
}
.acts button.copy-btn {
  grid-column: 1 / -1;
  background: transparent;
  color: var(--ink-secondary);
  border-style: dashed;
}
.acts button.copy-btn:hover {
  color: var(--ink);
  border-style: solid;
}
footer {
  margin-top: 56px;
  padding-top: 28px;
  border-top: 1px solid var(--card-border);
  color: var(--mute);
  font-size: 13px;
  line-height: 1.7;
}
footer a {
  color: var(--acc);
  text-decoration: none;
}
footer a:hover {
  text-decoration: underline;
}
.toast {
  position: fixed;
  left: 50%;
  bottom: 28px;
  transform: translateX(-50%) translateY(20px);
  background: var(--ink);
  color: var(--bg);
  padding: 10px 20px;
  border-radius: 999px;
  font-size: 14px;
  font-weight: 600;
  box-shadow: 0 10px 30px rgba(0,0,0,0.3);
  opacity: 0;
  transition: all 0.25s cubic-bezier(0.16, 1, 0.3, 1);
  pointer-events: none;
  z-index: 1000;
}
.toast.on {
  opacity: 1;
  transform: translateX(-50%) translateY(0);
}
</style>
</head>
<body>
<div class="wrap">
  <header>
    <div class="badge-hero">⚽ KKTC Resmi Fikstür Takvimi</div>
    <h1>KKTC futbolu <span>takviminde.</span></h1>
    <p>Takımını seç, tek tıkla takvimine abone ol. Karşılaşma saatleri, stadyumlar, ertelemeler ve skorlar otomatik güncellenir.</p>
  </header>

  <div class="controls">
    <div class="filters-row">
      <div class="league-chips" id="leagueChips"></div>
      <div class="select-wrapper">
        <select id="teamSelect" class="team-select" aria-label="Takım seçin">
          <option value="all">Tüm Takımları Göster</option>
        </select>
        <span class="select-arrow">▼</span>
      </div>
    </div>
  </div>

  <div id="out"></div>

  <footer>
    <p><b>Google Takvim</b> butonu doğrudan güncellenen bir Google takvimine abone yapar. <b>Apple / Outlook</b> butonu ICS aboneliğidir; uygulamanın yenileme aralığına göre otomatik güncellenir. Android kullanıcıları için Google Takvim önerilir.</p>
    <p>Veriler <a href="https://ktff.org" target="_blank" rel="noopener">ktff.org</a> üzerinden otomatik senkronize edilir. Bu proje bağımsız bir açık kaynak hizmetidir; resmi bildirimler için federasyon duyurularını takip ediniz.</p>
  </footer>
</div>

<div class="toast" id="toast">Takvim linki kopyalandı!</div>

<script>
const D = __DATA__;
const base = D.base || location.href.replace(/\/[^\/]*$/, "");
const ab = p => base + "/" + p;
const webcal = u => u.replace(/^https?:/, "webcal:");
const fmt = n => {
  if (!n) return "";
  const d = new Date(n.date + "T12:00:00");
  const s = d.toLocaleDateString("tr-TR", { day: "numeric", month: "long", weekday: "short" });
  return s + (n.time ? " " + n.time : "");
};
const esc = s => String(s || "").replace(/[&<>"]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));

let currentLeague = "all";
let selectedTeamKey = "all";

const leagueChips = document.getElementById("leagueChips");
const teamSelect = document.getElementById("teamSelect");

function populateTeamSelect() {
  const teams = D.items.filter(i => i.type === "team" && (currentLeague === "all" || i.league === currentLeague));
  teams.sort((a, b) => a.name.localeCompare(b.name, "tr"));
  
  teamSelect.innerHTML = `<option value="all">🎯 ${currentLeague === "all" ? "Tüm Takımlardan Seç…" : "Bu Ligdeki Takımlardan Seç…"}</option>`;
  teams.forEach(t => {
    const opt = document.createElement("option");
    opt.value = t.key;
    opt.textContent = t.name;
    if (t.key === selectedTeamKey) opt.selected = true;
    teamSelect.appendChild(opt);
  });
}

function mkLeagueBtn(key, label) {
  const b = document.createElement("button");
  b.textContent = label;
  b.dataset.key = key;
  b.setAttribute("aria-pressed", key === currentLeague);
  b.onclick = () => {
    currentLeague = key;
    selectedTeamKey = "all";
    leagueChips.querySelectorAll("button").forEach(x => x.setAttribute("aria-pressed", x.dataset.key === key));
    populateTeamSelect();
    render();
  };
  leagueChips.appendChild(b);
}

mkLeagueBtn("all", "Tümü");
D.leagues.forEach(l => mkLeagueBtn(l.key, l.name.replace("AKSA ", "")));
populateTeamSelect();

teamSelect.onchange = () => {
  selectedTeamKey = teamSelect.value;
  render();
};

function card(i) {
  const url = ab(i.ics);
  const outCal = encodeURIComponent(webcal(url));
  const logoHtml = i.logo 
    ? `<img class="team-logo" src="${esc(i.logo)}" alt="${esc(i.name)}" loading="lazy" onerror="this.style.display='none'">`
    : `<div class="league-icon">${i.type === 'league' ? '🏆' : '⚽'}</div>`;

  let nextHtml = "";
  if (i.next) {
    nextHtml = `
      <div class="next">
        <span class="next-title">⏱️ Sıradaki Karşılaşma</span>
        <span class="next-match">${esc(i.next.summary)}</span>
        <div class="next-details">
          <span>📅 ${esc(fmt(i.next))}</span>
          ${i.next.venue ? `<span>📍 ${esc(i.next.venue)}</span>` : ""}
        </div>
      </div>
    `;
  }

  const googleUrl = i.google 
    ? i.google 
    : `https://calendar.google.com/calendar/r?cid=${encodeURIComponent(webcal(url))}`;

  return `
    <div class="card ${i.type}">
      <div class="top">
        ${logoHtml}
        <div class="card-header-text">
          <div class="name">${esc(i.name)}</div>
          <div class="meta">${i.type === "team" ? esc(i.leagueName.replace("AKSA ", "")) + " · " : ""}${i.count} maç</div>
        </div>
      </div>
      ${nextHtml}
      <div class="acts">
        <a class="pri" href="${esc(googleUrl)}" target="_blank" rel="noopener">
          📅 Google Takvim
        </a>
        <a href="${esc(webcal(url))}">
          🍎 Apple Takvim
        </a>
        <a href="https://outlook.live.com/owa/?rru=addsubscription&url=${outCal}&name=${encodeURIComponent(i.name)}" target="_blank" rel="noopener">
          📧 Outlook.com
        </a>
        <button class="copy-btn" data-url="${esc(url)}">
          🔗 Takvim Linkini Kopyala
        </button>
      </div>
    </div>
  `;
}

function render() {
  let filtered = D.items.filter(i => {
    const matchLeague = currentLeague === "all" || i.league === currentLeague;
    const matchTeam = selectedTeamKey === "all" || i.key === selectedTeamKey || (selectedTeamKey.startsWith("lig/") && i.key === selectedTeamKey);
    return matchLeague && matchTeam;
  });

  const leagues = filtered.filter(i => i.type === "league");
  const teams = filtered.filter(i => i.type === "team");

  let html = "";
  if (selectedTeamKey === "all") {
    if (leagues.length) html += `<div class="section-title">🏆 Lig Fikstürleri</div><div class="list">${leagues.map(card).join("")}</div>`;
    if (teams.length) html += `<div class="section-title">⚽ Takım Fikstürleri (${teams.length})</div><div class="list">${teams.map(card).join("")}</div>`;
  } else {
    html = `<div class="list">${filtered.map(card).join("")}</div>`;
  }

  document.getElementById("out").innerHTML = html || "<p style='color:var(--mute);text-align:center;padding:40px;'>Eşleşen fikstür bulunamadı.</p>";
}

document.getElementById("out").addEventListener("click", e => {
  const b = e.target.closest("button[data-url]");
  if (!b) return;
  navigator.clipboard.writeText(b.dataset.url).then(() => {
    const t = document.getElementById("toast");
    t.classList.add("on");
    setTimeout(() => t.classList.remove("on"), 2000);
  });
});

render();
</script>
</body>
</html>
"""
