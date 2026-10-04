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


def build(specs: list[CalendarSpec], gcal_state: dict | None, out: Path = config.SITE_DIR) -> int:
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
    items = []
    for s in specs:
        items.append({
            "key": s.key, "name": s.name.replace(" Fikstürü", ""),
            "type": "team" if s.team else "league",
            "league": s.league, "leagueName": LEAGUE_NAMES.get(s.league or "", ""),
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
<meta name="description" content="KKTC Süper Lig ve 1. Lig fikstürlerini Google Takvim, Apple Takvim ve Outlook'a ücretsiz ekle. Saat değişiklikleri ve skorlar otomatik güncellenir.">
<style>
:root{--bg:#f6f4f0;--card:#fff;--ink:#16181d;--mute:#626873;--line:#e3dfd7;--acc:#c8102e;--acc-ink:#fff;--chip:#efebe4}
@media (prefers-color-scheme:dark){:root{--bg:#121315;--card:#1b1d21;--ink:#eceae6;--mute:#9a9fa8;--line:#2b2e34;--acc:#ff4d5e;--acc-ink:#140a0b;--chip:#25282d}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font:16px/1.5 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}
.wrap{max-width:880px;margin:0 auto;padding:28px 16px 64px}
header h1{font-size:clamp(28px,6vw,44px);line-height:1.05;margin:0 0 8px;letter-spacing:-.02em}
header h1 span{color:var(--acc)}
header p{margin:0;color:var(--mute);max-width:56ch}
.bar{display:flex;flex-wrap:wrap;gap:8px;margin:24px 0 16px;align-items:center}
.bar button{border:1px solid var(--line);background:var(--card);color:var(--ink);padding:7px 14px;border-radius:999px;font:inherit;font-size:14px;cursor:pointer}
.bar button[aria-pressed=true]{background:var(--ink);color:var(--bg);border-color:var(--ink)}
.bar input{flex:1 1 180px;min-width:0;border:1px solid var(--line);background:var(--card);color:var(--ink);padding:8px 14px;border-radius:999px;font:inherit;font-size:14px}
.list{display:grid;gap:10px}
.card{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:14px 16px;display:grid;gap:10px}
.top{display:flex;justify-content:space-between;gap:12px;align-items:baseline}
.name{font-weight:650;font-size:17px}
.meta{color:var(--mute);font-size:13px;white-space:nowrap}
.next{font-size:14px;color:var(--mute)}
.next b{color:var(--ink);font-weight:600}
.acts{display:flex;flex-wrap:wrap;gap:8px}
.acts a,.acts button{display:inline-flex;align-items:center;gap:6px;text-decoration:none;font:inherit;font-size:14px;padding:7px 12px;border-radius:9px;border:1px solid var(--line);background:var(--chip);color:var(--ink);cursor:pointer}
.acts a.pri{background:var(--acc);border-color:var(--acc);color:var(--acc-ink);font-weight:600}
.league .name::before{content:"Lig · ";color:var(--acc)}
h2{font-size:13px;text-transform:uppercase;letter-spacing:.08em;color:var(--mute);margin:26px 0 10px}
footer{margin-top:40px;color:var(--mute);font-size:13px}
footer a{color:inherit}
.toast{position:fixed;left:50%;bottom:20px;transform:translateX(-50%);background:var(--ink);color:var(--bg);padding:8px 14px;border-radius:8px;font-size:14px;opacity:0;transition:opacity .2s;pointer-events:none}
.toast.on{opacity:1}
</style>
</head>
<body>
<div class="wrap">
<header>
<h1>KKTC futbolu <span>takviminde.</span></h1>
<p>Takımını seç, tek tıkla takvimine ekle. Maç saatleri, ertelemeler ve skorlar kendiliğinden güncellenir. Hesap gerekmez.</p>
</header>
<div class="bar" id="bar"><input id="q" type="search" placeholder="Takım ara…" aria-label="Takım ara"></div>
<div id="out"></div>
<footer>
<p><b>Google Takvim</b> butonu doğrudan güncellenen bir Google takvimine abone yapar. <b>Apple / Outlook</b> butonu ICS aboneliğidir; uygulamanın yenileme aralığına göre güncellenir. Android'de Google Takvim'i kullan.</p>
<p>Veriler <a href="https://ktff.org">ktff.org</a> fikstürlerinden otomatik alınır. Bu site KTFF ile bağlantılı değildir; kesin bilgi için federasyonun duyurularına bakın.</p>
</footer>
</div>
<div class="toast" id="toast">Link kopyalandı</div>
<script>
const D=__DATA__;
const base=D.base||location.href.replace(/\/[^\/]*$/,"");
const ab=p=>base+"/"+p;
const webcal=u=>u.replace(/^https?:/,"webcal:");
const fmt=n=>{if(!n)return"";const d=new Date(n.date+"T12:00:00");const s=d.toLocaleDateString("tr-TR",{day:"numeric",month:"long",weekday:"short"});return s+(n.time?" "+n.time:"")};
const esc=s=>String(s).replace(/[&<>"]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
let league="all";
const bar=document.getElementById("bar"),q=document.getElementById("q");
const mk=(k,l)=>{const b=document.createElement("button");b.textContent=l;b.dataset.k=k;b.setAttribute("aria-pressed",k===league);b.onclick=()=>{league=k;bar.querySelectorAll("button").forEach(x=>x.setAttribute("aria-pressed",x.dataset.k===k));render()};bar.insertBefore(b,q);};
mk("all","Tümü");D.leagues.forEach(l=>mk(l.key,l.name.replace("AKSA ","")));
function card(i){
  const url=ab(i.ics),out=encodeURIComponent(webcal(url));
  const n=i.next?`<div class="next">Sıradaki: <b>${esc(i.next.summary)}</b> · ${esc(fmt(i.next))}${i.next.venue?" · "+esc(i.next.venue):""}</div>`:"";
  return `<div class="card ${i.type}"><div class="top"><span class="name">${esc(i.name)}</span><span class="meta">${i.type==="team"?esc(i.leagueName.replace("AKSA ",""))+" · ":""}${i.count} maç</span></div>${n}
  <div class="acts">${i.google?`<a class="pri" href="${esc(i.google)}" target="_blank" rel="noopener">Google Takvim</a>`:`<a class="pri" href="https://calendar.google.com/calendar/r?cid=${encodeURIComponent(webcal(url))}" target="_blank" rel="noopener">Google Takvim</a>`}
  <a href="${esc(webcal(url))}">Apple / Outlook</a>
  <a href="https://outlook.live.com/owa/?rru=addsubscription&url=${out}&name=${encodeURIComponent(i.name)}" target="_blank" rel="noopener">Outlook.com</a>
  <button data-u="${esc(url)}">Linki kopyala</button></div></div>`;
}
function render(){
  const t=q.value.trim().toLocaleLowerCase("tr");
  const f=D.items.filter(i=>(league==="all"||i.league===league)&&(!t||i.name.toLocaleLowerCase("tr").includes(t)));
  const L=f.filter(i=>i.type==="league"),T=f.filter(i=>i.type==="team");
  document.getElementById("out").innerHTML=(L.length?"<h2>Ligler</h2><div class=list>"+L.map(card).join("")+"</div>":"")+(T.length?"<h2>Takımlar</h2><div class=list>"+T.map(card).join("")+"</div>":"")||"<p>Sonuç yok.</p>";
}
document.getElementById("out").addEventListener("click",e=>{const b=e.target.closest("button[data-u]");if(!b)return;navigator.clipboard.writeText(b.dataset.u).then(()=>{const t=document.getElementById("toast");t.classList.add("on");setTimeout(()=>t.classList.remove("on"),1400)})});
q.addEventListener("input",render);render();
</script>
</body>
</html>
"""
