"""Copyright (c) Microsoft Corporation. Licensed under the MIT license.

Build an interactive web story map (`storymap/index.html` + `storymap/web_data.js`).

    python build_storymap_web.py

Same 12 scenes and figures as the slides and the JupyterGIS story map (`storyboard_scenes.py`),
but in a plain Leaflet page so the reader can work the map:

- map in the left two thirds, scene text in the right third, with a draggable divider;
- a layer panel with a checkbox per Aurora variable (AQI, 10 m wind, stagnation probability),
  grids, boundaries, sites, alert sites and labels, plus a slider over the 48 forecast hours;
- click any cell or site for its values at the selected hour;
- scrolling the text moves the map and sets the layers and hour for that scene (the reader can
  change them afterwards); KO/EN and light/dark switches in the top bar.

The page is static: open `index.html` directly or serve the `storymap/` folder (GitHub Pages).
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from build_storymap_jgis import SITES, STEPS, VIEWS, load_data
from storyboard_scenes import scenes

HERE = Path(__file__).resolve().parent
CITIES_NCR = [
    ("Sonipat", 28.99, 77.02), ("Meerut", 28.98, 77.71), ("Panipat", 29.39, 76.97), ("Rohtak", 28.90, 76.61),
    ("Karnal", 29.69, 76.99), ("Alwar", 27.55, 76.60), ("Mathura", 27.49, 77.67), ("Aligarh", 27.88, 78.08),
    ("Chandigarh", 30.73, 76.78), ("Dehradun", 30.32, 78.03), ("Agra", 27.18, 78.01), ("Gurugram", 28.46, 77.03),
    ("Noida", 28.54, 77.39), ("Ghaziabad", 28.67, 77.45), ("Faridabad", 28.41, 77.32),
]  # fmt: skip


def scene_payload(D: dict, lang: str) -> list[dict]:
    out = []
    for i, sc in enumerate(scenes(D, lang), 1):
        m = sc["map"]
        hour = 35 if m["prob"] else STEPS.get(m["aqi"] or "", None)
        img = f"img/{lang}/{i:02d}_{sc['key']}.png" if sc["fig"][0] != "map" else ""
        out.append({
            "key": sc["key"], "title": f"{i}. {sc['title']}", "eyebrow": sc["eyebrow"], "body": sc["body"], "img": img,
            "bounds": [[VIEWS[m["view"]][1], VIEWS[m["view"]][0]], [VIEWS[m["view"]][3], VIEWS[m["view"]][2]]],
            "hour": hour,
            "layers": {"aqi": bool(m["aqi"]), "wind": bool(m["wind"]), "prob": bool(m["prob"]), "grid": bool(m["grid"]),
                       "coarse": bool(m["coarse"]), "sites": m["view"] in ("delhi", "hotspot", "tile"),
                       "alerts": sc["key"] in ("evening", "peak", "message"), "labels": True},
        })  # fmt: skip
    return out


def build_data(D: dict) -> dict:
    ens = D.get("ensemble") or {}
    return {
        "times": D["times"], "lats": D["lats"], "lons": D["lons"], "aqi": D["aqi"], "wind": D["wind"], "wdir": D["wdir"],
        "prob": ens.get("p_cell"), "members": ens.get("members"),
        "sites": [{"name": n, "lat": la, "lon": lo, **D["sites"].get(n, {}),
                   "p": (ens.get("sites", {}).get(n) or {}).get("p")} for n, la, lo, *_ in SITES],
        "summary": D.get("summary", []), "delhi": D["delhi"], "cities": D["cities"], "towns": CITIES_NCR,
        "provenance": D.get("provenance", {}), "attribution": D.get("attribution", ""),
        "scenes": {"ko": scene_payload(D, "ko"), "en": scene_payload(D, "en")},
    }  # fmt: skip


PAGE = r"""<!doctype html>
<html lang="ko" data-theme="light">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Delhi Smog Story Map</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css">
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<style>
:root { --bg:#f8fafc; --panel:#ffffff; --fg:#1e293b; --muted:#64748b; --line:#cbd5e1; --accent:#1d8fb5; --ctl:rgba(255,255,255,.94); }
:root[data-theme="dark"] { --bg:#0b1220; --panel:#111a2b; --fg:#e2e8f0; --muted:#94a3b8; --line:#334155; --accent:#4cb6d8; --ctl:rgba(17,26,43,.94); }
* { box-sizing:border-box; }
html, body { margin:0; height:100%; background:var(--bg); color:var(--fg); font-family:"Noto Sans KR","Apple SD Gothic Neo","Malgun Gothic",system-ui,sans-serif; }
.bar { height:48px; display:flex; align-items:center; gap:12px; padding:0 14px; border-bottom:1px solid var(--line); background:var(--panel); }
.bar h1 { font-size:17px; margin:0; flex:1; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
.bar button { font:inherit; font-size:14px; border:1px solid var(--line); background:transparent; color:var(--fg); border-radius:999px; padding:4px 12px; cursor:pointer; }
.bar button[aria-pressed="true"] { background:var(--accent); border-color:var(--accent); color:#fff; }
.app { display:grid; grid-template-columns: var(--mapw, 66.6%) 8px 1fr; height:calc(100% - 48px); }
#map { height:100%; }
.divider { cursor:col-resize; background:var(--line); }
.divider:hover, .divider.drag { background:var(--accent); }
.story { overflow-y:auto; padding:0 26px 40vh; background:var(--panel); font-size:18px; line-height:1.6; }
.scene { min-height:85vh; padding:28px 0 18px; border-bottom:1px solid var(--line); opacity:.45; transition:opacity .3s; }
.scene.active { opacity:1; }
.scene .eyebrow { font-size:13px; letter-spacing:.06em; text-transform:uppercase; color:var(--muted); }
.scene h2 { font-size:26px; line-height:1.25; margin:6px 0 14px; color:var(--accent); }
.scene img { width:100%; border-radius:10px; margin:4px 0 12px; box-shadow:0 1px 8px rgba(0,0,0,.15); background:#fff; }
.scene a { color:var(--accent); }
.ctl { max-height:calc(100vh - 90px); overflow:auto; background:var(--ctl); color:var(--fg); border:1px solid var(--line); border-radius:10px; padding:10px 12px; font-size:14px; line-height:1.5; min-width:230px; box-shadow:0 2px 10px rgba(0,0,0,.2); }
.ctl b { display:block; margin:6px 0 2px; font-size:13px; color:var(--muted); }
.ctl label { display:flex; gap:7px; align-items:center; cursor:pointer; }
.ctl input[type=range] { width:100%; accent-color:var(--accent); }
.ctl .when { font-weight:600; }
.legend i { display:inline-block; width:12px; height:12px; border-radius:2px; margin-right:4px; vertical-align:-1px; }
.legend span { display:inline-block; margin-right:8px; font-size:12px; white-space:nowrap; }
.leaflet-popup-content { font-size:14px; line-height:1.5; }
.leaflet-container { background:var(--bg); font:inherit; }
.site-label { background:rgba(255,255,255,.85); border:0; box-shadow:none; font-weight:600; font-size:12px; color:#1e293b; padding:0 4px; }
.city-label { background:transparent; border:0; box-shadow:none; font-weight:700; font-size:13px; color:#1e293b; text-shadow:0 0 3px #fff, 0 0 3px #fff; }
.leaflet-tooltip.site-label::before, .leaflet-tooltip.city-label::before { display:none; }
@media (max-width: 800px) { .app { grid-template-columns:1fr; grid-template-rows:50% 0 50%; } .divider { display:none; } }
</style>
</head>
<body>
<div class="bar">
  <h1 id="title"></h1>
  <button type="button" data-lang="ko">한국어</button><button type="button" data-lang="en">English</button>
  <button type="button" id="theme">◐</button>
</div>
<div class="app" id="app">
  <div id="map"></div>
  <div class="divider" id="divider" title="drag"></div>
  <main class="story" id="story"></main>
</div>
<script src="web_data.js"></script>
<script>
(function () {
  var D = window.WEB_DATA, lang = "ko", hour = 0, cur = 0, folded = false;
  var CATS = [[50,"Good","좋음","#2e8b57"],[100,"Satisfactory","양호","#7fb241"],[200,"Moderate","보통","#d4a72c"],[300,"Poor","나쁨","#e0782a"],[400,"Very Poor","매우 나쁨","#c84a3b"],[1e9,"Severe","위험","#7f1d2d"]];
  function cat(a) { for (var i = 0; i < CATS.length; i++) if (a <= CATS[i][0]) return CATS[i]; return CATS[5]; }
  function T(ko, en) { return lang === "ko" ? ko : en; }
  function ist(i) { var t = new Date(new Date(D.times[i] + "Z").getTime() + 330 * 60000); var p = function (n) { return (n < 10 ? "0" : "") + n; };
    return lang === "ko" ? (t.getUTCMonth() + 1) + "월 " + t.getUTCDate() + "일 " + p(t.getUTCHours()) + ":" + p(t.getUTCMinutes()) + " IST" : t.getUTCDate() + " Nov " + p(t.getUTCHours()) + ":" + p(t.getUTCMinutes()) + " IST"; }

  // ---- map and base layers
  var map = L.map("map", { zoomSnap: 0.25, worldCopyJump: true }).setView([22, 79], 4);
  var light = L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", { maxZoom: 18, attribution: "© OpenStreetMap contributors · " + D.attribution });
  var dark = L.tileLayer("https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Dark_Gray_Base/MapServer/tile/{z}/{y}/{x}", { maxZoom: 16, attribution: "Tiles © Esri · " + D.attribution });
  light.addTo(map);

  var nLat = D.lats.length, nLon = D.lons.length;
  var G = { aqi: L.layerGroup(), prob: L.layerGroup(), wind: L.layerGroup(), grid: L.layerGroup(), coarse: L.layerGroup(),
            bounds: L.layerGroup(), sites: L.layerGroup(), alerts: L.layerGroup(), labels: L.layerGroup() };
  var cells = [], probCells = [];
  function cellPopup(k) {
    var a = D.aqi[hour][k], c = cat(a), p = D.prob ? D.prob[Math.min(hour, D.prob.length - 1)][k] : null;
    return "<b>" + D.lats[Math.floor(k / nLon)].toFixed(2) + "°N " + D.lons[k % nLon].toFixed(2) + "°E</b><br>" + ist(hour) +
      "<br>AQI <b>" + a + "</b> (" + T(c[2], c[1]) + ")<br>" + T("10 m 풍속 ", "10 m wind ") + D.wind[hour][k] + " km/h · " + D.wdir[hour][k] + "°" +
      (p != null ? "<br>" + T("정체 확률 ", "P(stagnant) ") + Math.round(p * 100) + "% (" + D.members + T("개 멤버", " members") + ")" : "") +
      "<br><small>" + T("출처: Aurora 1.5 기상 · 농도는 ", "Source: Aurora 1.5 weather · pollutants ") + D.provenance.pollutants + "</small>";
  }
  for (var i = 0; i < nLat; i++) for (var j = 0; j < nLon; j++) (function (k, la, lo) {
    var b = [[la - 0.125, lo - 0.125], [la + 0.125, lo + 0.125]];
    var r = L.rectangle(b, { weight: 0.4, color: "#fff", fillOpacity: 0.62 }).bindPopup(function () { return cellPopup(k); });
    cells.push(r); G.aqi.addLayer(r);
    var pr = L.rectangle(b, { weight: 0, fillColor: "#1d8fb5", fillOpacity: 0 }).bindPopup(function () { return cellPopup(k); });
    probCells.push(pr); G.prob.addLayer(pr);
    G.grid.addLayer(L.rectangle(b, { weight: 0.6, color: "#475569", fill: false, interactive: false }));
  })(i * nLon + j, D.lats[i], D.lons[j]);
  G.coarse.addLayer(L.rectangle([[28.4, 76.8], [28.8, 77.2]], { weight: 2, dashArray: "6 4", color: "#1e293b", fillColor: "#fde68a", fillOpacity: 0.3, interactive: false }));
  G.bounds.addLayer(L.polygon(D.delhi.map(function (p) { return [p[1], p[0]]; }), { weight: 2.2, color: "#1e293b", fill: false, interactive: false }));
  G.bounds.addLayer(L.rectangle([[27.5, 76], [31.5, 80]], { weight: 2, color: "#1d8fb5", fill: false, interactive: false }));

  function sitePopup(s) {
    var a = s.aqi[hour], c = cat(a);
    return "<b>" + s.name + "</b><br>" + ist(hour) + "<br>AQI <b>" + a + "</b> (" + T(c[2], c[1]) + ")<br>PM2.5 " + s.pm25[hour] + " µg/m³" +
      "<br>" + T("혼합층 ", "Mixing height ") + s.blh[hour] + " m · " + T("풍속 ", "wind ") + s.wind[hour] + " km/h" +
      "<br>" + (s.stag[hour] ? T("<b>정체</b> (바람 &lt; 10 km/h, 혼합층 &lt; 500 m)", "<b>Stagnant</b> (wind &lt; 10 km/h, mixing &lt; 500 m)") : T("정체 아님", "not stagnant")) +
      (s.p ? "<br>" + T("정체 확률 ", "P(stagnant) ") + Math.round(s.p[hour] * 100) + "%" : "");
  }
  var siteMarkers = D.sites.map(function (s) {
    var m = L.circleMarker([s.lat, s.lon], { radius: 8, weight: 2, color: "#fff", fillOpacity: 1 }).bindPopup(function () { return sitePopup(s); });
    G.sites.addLayer(m); return m;
  });
  var siteLabels = D.sites.map(function (s) { var t = L.tooltip({ permanent: true, direction: "right", offset: [8, 0], className: "site-label" }).setLatLng([s.lat, s.lon]); G.labels.addLayer(t); return t; });
  D.cities.concat(D.towns.map(function (t) { return [t[0], t[1], t[2]]; })).forEach(function (c) {
    G.labels.addLayer(L.tooltip({ permanent: true, direction: "right", offset: [4, 0], className: "city-label" }).setLatLng([c[1], c[2]]).setContent(c[0]));
  });
  var alertRings = D.sites.map(function (s) { var r = L.circleMarker([s.lat, s.lon], { radius: 16, weight: 3, color: "#1d8fb5", fillOpacity: 0.12, interactive: false }); return r; });

  function redraw() {
    var a = D.aqi[hour];
    cells.forEach(function (r, k) { r.setStyle({ fillColor: cat(a[k])[3] }); });
    if (D.prob) { var pc = D.prob[Math.min(hour, D.prob.length - 1)]; probCells.forEach(function (r, k) { r.setStyle({ fillOpacity: 0.05 + 0.8 * pc[k] }); }); }
    G.wind.clearLayers();
    var w = D.wind[hour], wd = D.wdir[hour];
    for (var i = 0; i < nLat; i++) for (var j = 0; j < nLon; j++) {
      var k = i * nLon + j, la = D.lats[i], lo = D.lons[j], len = Math.min(0.11, 0.02 + 0.006 * w[k]), ang = wd[k] * Math.PI / 180;
      var tip = [la + Math.sin(ang) * len, lo + Math.cos(ang) * len];
      G.wind.addLayer(L.polyline([[la, lo], tip], { weight: 2, color: "#111827", opacity: 0.8, interactive: false }));
      G.wind.addLayer(L.circleMarker(tip, { radius: 2, weight: 0, fillColor: "#111827", fillOpacity: 0.8, interactive: false }));
    }
    siteMarkers.forEach(function (m, k) { m.setStyle({ fillColor: cat(D.sites[k].aqi[hour])[3] }); });
    siteLabels.forEach(function (t, k) { var s = D.sites[k]; t.setContent(s.name + " · " + (state.prob && s.p ? T("정체 ", "P ") + Math.round(s.p[hour] * 100) + "%" : "AQI " + s.aqi[hour])); });
    G.alerts.clearLayers();
    D.sites.forEach(function (s, k) { if (s.aqi[hour] >= 450) G.alerts.addLayer(alertRings[k]); });
    document.getElementById("when").textContent = ist(hour) + " · +" + (hour + 1) + " h";
  }

  // ---- layer panel (checkbox per variable, hour slider, legend)
  var state = { aqi: true, wind: false, prob: false, grid: false, coarse: false, bounds: true, sites: true, alerts: false, labels: true };
  var NAMES = { aqi: ["AQI (Aurora 기반 예측)", "AQI (Aurora-based forecast)"], wind: ["10 m 바람 (Aurora 1.5)", "10 m wind (Aurora 1.5)"],
                prob: ["정체 확률 (Aurora 1.5 앙상블)", "Stagnation probability (Aurora 1.5 ensemble)"], grid: ["0.25° 격자 (Aurora 1.5 칸)", "0.25° grid (Aurora 1.5 cells)"],
                coarse: ["0.4° 칸 (대기오염 모델)", "0.4° cell (air-pollution model)"], bounds: ["델리 경계 · 수도권 타일", "Delhi boundary · NCR tile"],
                sites: ["대표 지점 10곳", "Ten reporting sites"], alerts: ["경보 지점 (AQI ≥ 450)", "Alert sites (AQI ≥ 450)"], labels: ["지명·값 라벨", "Names and values"] };
  var ctl = L.control({ position: "topright" });
  ctl.onAdd = function () { var d = L.DomUtil.create("div", "ctl"); L.DomEvent.disableClickPropagation(d); L.DomEvent.disableScrollPropagation(d); d.id = "ctl"; return d; };
  ctl.addTo(map);
  function renderCtl() {
    var d = document.getElementById("ctl");
    var h = "<div style='display:flex; justify-content:space-between; align-items:center; gap:8px;'><b style='margin:0'>" + T("지도 레이어", "Map layers") +
      "</b><button type='button' id='fold' style='font:inherit; font-size:12px; border:1px solid var(--line); background:transparent; color:var(--fg); border-radius:6px; cursor:pointer;'>" + (folded ? "▸" : "▾") + "</button></div>";
    if (folded) { d.innerHTML = h + "<div class='when' id='when'></div>"; document.getElementById("fold").onclick = function () { folded = false; renderCtl(); redraw(); }; return; }
    Object.keys(NAMES).forEach(function (k) { h += "<label><input type='checkbox' data-k='" + k + "'" + (state[k] ? " checked" : "") + "> " + T(NAMES[k][0], NAMES[k][1]) + "</label>"; });
    h += "<b>" + T("예측 시각", "Forecast hour") + "</b><div class='when' id='when'></div><input type='range' id='hour' min='0' max='47' value='" + hour + "'>";
    h += "<div class='legend'>" + CATS.map(function (c) { return "<span><i style='background:" + c[3] + "'></i>" + T(c[2], c[1]) + "</span>"; }).join("") + "</div>";
    h += "<div style='font-size:12px; color:var(--muted)'>" + T("지도를 클릭하면 값이 보입니다", "Click the map for values") + "</div>";
    d.innerHTML = h;
    document.getElementById("fold").onclick = function () { folded = true; renderCtl(); redraw(); };
    d.querySelectorAll("input[type=checkbox]").forEach(function (x) { x.addEventListener("change", function () { state[x.dataset.k] = x.checked; apply(); }); });
    document.getElementById("hour").addEventListener("input", function (e) { hour = +e.target.value; redraw(); });
  }
  function apply() {
    Object.keys(state).forEach(function (k) { if (state[k]) G[k].addTo(map); else map.removeLayer(G[k]); });
    redraw();
  }

  // ---- story (right pane), scroll-driven scenes
  var story = document.getElementById("story");
  function renderStory(keep) {
    var S = D.scenes[lang];
    document.getElementById("title").textContent = T("델리 스모그 스토리 맵 · Aurora", "Delhi Smog Story Map · Aurora");
    story.innerHTML = S.map(function (s, i) {
      return "<section class='scene' data-i='" + i + "'><div class='eyebrow'>" + s.eyebrow + "</div><h2>" + s.title + "</h2>" +
        (s.img ? "<img src='" + s.img + "' alt=''>" : "") + s.body + "</section>";
    }).join("");
    story.querySelectorAll(".scene").forEach(function (el) { io.observe(el); });
    document.documentElement.lang = lang;
    document.querySelectorAll("[data-lang]").forEach(function (b) { b.setAttribute("aria-pressed", String(b.dataset.lang === lang)); });
    renderCtl(); apply(); activate(cur, false, keep);
  }
  function activate(i, fly, keep) {
    var s = D.scenes[lang][i]; if (!s) return; cur = i;
    story.querySelectorAll(".scene").forEach(function (el) { el.classList.toggle("active", +el.dataset.i === i); });
    if (!keep) {
      Object.keys(s.layers).forEach(function (k) { state[k] = s.layers[k]; });
      state.bounds = true;
      if (s.hour != null) hour = s.hour;
    }
    renderCtl(); apply();
    if (fly) map.flyToBounds(s.bounds, { duration: 1.4, padding: [20, 20] }); else map.fitBounds(s.bounds, { padding: [20, 20] });
  }
  var io = new IntersectionObserver(function (entries) {
    entries.forEach(function (e) { if (e.isIntersecting) { var i = +e.target.dataset.i; if (i !== cur) activate(i, true); } });
  }, { root: story, rootMargin: "-30% 0px -60% 0px" });

  // ---- language, theme, divider
  document.querySelectorAll("[data-lang]").forEach(function (b) { b.addEventListener("click", function () { lang = b.dataset.lang; renderStory(true); }); });
  document.getElementById("theme").addEventListener("click", function () {
    var dk = document.documentElement.dataset.theme !== "dark"; document.documentElement.dataset.theme = dk ? "dark" : "light";
    if (dk) { map.removeLayer(light); dark.addTo(map); } else { map.removeLayer(dark); light.addTo(map); }
  });
  var dv = document.getElementById("divider"), app = document.getElementById("app");
  dv.addEventListener("pointerdown", function (e) {
    dv.classList.add("drag"); dv.setPointerCapture(e.pointerId);
    function mv(ev) { var r = app.getBoundingClientRect(); var p = Math.min(85, Math.max(30, 100 * (ev.clientX - r.left) / r.width)); app.style.setProperty("--mapw", p + "%"); map.invalidateSize(); }
    function up() { dv.classList.remove("drag"); dv.removeEventListener("pointermove", mv); dv.removeEventListener("pointerup", up); }
    dv.addEventListener("pointermove", mv); dv.addEventListener("pointerup", up);
  });
  var q = (location.hash || "").replace("#", ""); if (q === "en" || q === "ko") lang = q;
  if (window.matchMedia && matchMedia("(prefers-color-scheme: dark)").matches) document.getElementById("theme").click();
  renderStory();
})();
</script>
</body>
</html>
"""


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[2])
    ap.add_argument("--data", type=Path, default=HERE / "storymap_data.js")
    ap.add_argument("--out", type=Path, default=HERE / "storymap")
    a = ap.parse_args()
    D = load_data(a.data)
    a.out.mkdir(parents=True, exist_ok=True)
    (a.out / "web_data.js").write_text(
        "window.WEB_DATA="
        + json.dumps(build_data(D), ensure_ascii=False, separators=(",", ":"))
        + ";\n",
        encoding="utf-8",
    )
    (a.out / "index.html").write_text(PAGE, encoding="utf-8")
    print(
        f"wrote {a.out / 'index.html'} and {a.out / 'web_data.js'} ({(a.out / 'web_data.js').stat().st_size // 1024} KB)"
    )


if __name__ == "__main__":
    main()
