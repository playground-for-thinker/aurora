"""Copyright (c) Microsoft Corporation. Licensed under the MIT license.

Build a JupyterGIS story map (`.jGIS`) from `storymap_data.js`, for notebook.link.

    python build_storymap_jgis.py                       # writes storymap/ next to this script
    python build_storymap_jgis.py --story-type guided        # step-through side panel instead of scrolling

The output folder is self-contained and has no dependency on Claude or on any other hosted
service: two `.jGIS` documents (Korean and English) share the GeoJSON layers written to
`storymap/data/`, and `environment.yml` / `nblink-lock.json` / `jupyter-lite.json` make the folder
"notebook.link ready". Open a document with JupyterGIS in JupyterLab, JupyterLite or notebook.link
and start the story from the Story panel; the Specta view of notebook.link plays it full screen.

The `.jGIS` files are plain JSON following the JupyterGIS project schema (schemaVersion 0.6.0, the
version shipped by `jupytergis-lite` 0.16.x on emscripten-forge). The default story type is "Vertical
Scroll" in a split-screen layout: the map fills the left two thirds and each scene's text is a
slightly translucent card in the right third; the text comes from `storyboard_scenes.py` as HTML so
its type size is under control. Story stops are
`StorySegmentLayer` entries: each one carries an extent, markdown and a list of layer-visibility
overrides, which is how the AQI tile, wind, probability and marker layers are switched per scene.
"""

from __future__ import annotations

import argparse
import json
import math
import uuid
from datetime import datetime, timedelta
from pathlib import Path

from build_storyboard_slides import make_figure, png_data_uri, setup_fonts
from storyboard_scenes import scenes, text

HERE = Path(__file__).resolve().parent
NS = uuid.UUID("5a0c4f3e-2d9b-4b7e-9c1a-7d6e5f4a3b2c")  # namespace for reproducible ids

# CPCB categories with the colours used by storymap.html (light theme).
CATS = [
    (50, "Good", "좋음", "#2e8b57"),
    (100, "Satisfactory", "양호", "#7fb241"),
    (200, "Moderate", "보통", "#d4a72c"),
    (300, "Poor", "나쁨", "#e0782a"),
    (400, "Very Poor", "매우 나쁨", "#c84a3b"),
    (10**9, "Severe", "위험", "#7f1d2d"),
]
ACCENT = "#0b6e8f"
# name, lat, lon (same as storymap.html)
SITES = [
    ("Anand Vihar", 28.647, 77.316),
    ("ITO", 28.629, 77.241),
    ("Punjabi Bagh", 28.674, 77.131),
    ("Rohini", 28.733, 77.120),
    ("Jahangirpuri", 28.733, 77.171),
    ("R K Puram", 28.563, 77.187),
    ("Dwarka Sector 8", 28.571, 77.072),
    ("Okhla Phase 2", 28.531, 77.271),
    ("Noida Sector 62", 28.625, 77.358),
    ("Gurugram Vikas Sadan", 28.450, 77.026),
]
# Scene extents as (min lon, min lat, max lon, max lat).
VIEWS = {
    "world": (-170.0, -50.0, 190.0, 72.0),
    "india": (60.0, 4.0, 100.0, 38.0),
    "tile": (74.5, 26.5, 81.5, 32.5),
    "delhi": (76.65, 28.2, 77.65, 29.05),
    "hotspot": (77.15, 28.5, 77.47, 28.76),
}
STEPS = {"h00": 0, "h08": 8, "h35": 35, "h44": 44}  # forecast hours shown in the story
WIND_STEPS = ("h08", "h35", "h44")
HOTSPOT = "Anand Vihar"


# --------------------------------------------------------------------------------------- helpers
def uid(*parts: str) -> str:
    return str(uuid.uuid5(NS, "/".join(parts)))


def merc(lon: float, lat: float) -> list[float]:
    r = 6378137.0
    lat = max(-85.05, min(85.05, lat))
    return [
        round(r * math.radians(lon), 2),
        round(r * math.log(math.tan(math.pi / 4 + math.radians(lat) / 2)), 2),
    ]


CARD_WIDTH = "40vw"  # viewport-relative: a % width resolves against a narrower story container


def widen(view: str) -> tuple[float, float]:
    """Longitude span of the widened extent: 2.5x the view, with the view centred 30% across, i.e.
    in the middle of the map area left of the 40%-wide text card."""
    x0, _, x1, _ = VIEWS[view]
    if view == "world":
        return -40.0, 320.0
    w = x1 - x0
    cx = (x0 + x1) / 2
    return cx - 0.75 * w, cx + 1.75 * w


def extent(view: str) -> list[float]:
    """Web-mercator extent of a scene.

    The text card covers the right 40% of the map, so each extent is widened (see `widen`): OpenLayers
    fits the widened extent to the full width and the region of interest ends up in the visible map
    area on the left.
    """
    x0, y0, x1, y1 = VIEWS[view]
    x0, x1 = widen(view)
    a, b = merc(x0, y0), merc(x1, y1)
    return [a[0], a[1], b[0], b[1]]


def initial_view(view: str) -> dict:
    """Document-level centre and zoom matching the widened extent of a scene (used instead of
    `useExtent`, which made the map re-fit to the document extent after every scene change)."""
    x0, y0, x1, y1 = VIEWS[view]
    x0, x1 = widen(view)
    return {"longitude": round((x0 + x1) / 2, 4), "latitude": round((y0 + y1) / 2, 4),
            "zoom": round(math.log2(360.0 * 1000.0 / ((x1 - x0) * 256.0)), 2)}  # fmt: skip


def zoom(view: str) -> float:
    """Approximate web-mercator zoom at which the extent fills a 1000 px wide map."""
    x0, _, x1, _ = VIEWS[view]
    return round(math.log2(360.0 * 1000.0 / ((x1 - x0) * 256.0)), 2)


def hex_rgba(h: str, a: float = 1.0) -> list[float]:
    h = h.lstrip("#")
    return [int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16), a]


def cat(aqi: float) -> tuple[int, str, str, str]:
    for c in CATS:
        if aqi <= c[0]:
            return c
    return CATS[-1]


def ist(times: list[str], i: int, lang: str) -> str:
    t = datetime.fromisoformat(times[i]) + timedelta(hours=5, minutes=30)
    return (
        f"{t.month}월 {t.day}일 {t:%H:%M} IST" if lang == "ko" else f"{t.day} {t:%b} {t:%H:%M} IST"
    )


def load_data(path: Path) -> dict:
    js = path.read_text(encoding="utf-8")
    return json.loads(js[js.index("=") + 1 :].rstrip().rstrip(";"))


def feature(geom_type: str, coords, props: dict) -> dict:
    return {
        "type": "Feature",
        "geometry": {"type": geom_type, "coordinates": coords},
        "properties": props,
    }


def collection(features: list[dict]) -> dict:
    return {"type": "FeatureCollection", "features": features}


def cell_polygon(lat: float, lon: float, half: float) -> list:
    return [
        [
            [lon - half, lat - half],
            [lon + half, lat - half],
            [lon + half, lat + half],
            [lon - half, lat + half],
            [lon - half, lat - half],
        ]
    ]


# --------------------------------------------------------------------------------------- GeoJSON
def build_geojson(D: dict) -> dict[str, dict]:
    """Return {relative path: FeatureCollection} for every data layer."""
    lats, lons, times = D["lats"], D["lons"], D["times"]
    n_lon = len(lons)
    out: dict[str, dict] = {}

    for key, step in STEPS.items():
        feats = []
        for i, lat in enumerate(lats):
            for j, lon in enumerate(lons):
                k = i * n_lon + j
                a = D["aqi"][step][k]
                c = cat(a)
                feats.append(feature("Polygon", cell_polygon(lat, lon, 0.125), {
                    "lat": lat, "lon": lon, "aqi": a, "category": c[1], "category_ko": c[2],
                    "wind_kmh": D["wind"][step][k], "wind_dir_deg": D["wdir"][step][k],
                    "time_utc": times[step], "time_ist": ist(times, step, "en"),
                }))  # fmt: skip
        out[f"data/aqi_{key}.geojson"] = collection(feats)

    for key in WIND_STEPS:
        step = STEPS[key]
        feats = []
        for i, lat in enumerate(lats):
            for j, lon in enumerate(lons):
                k = i * n_lon + j
                w, d = D["wind"][step][k], D["wdir"][step][k]
                length = min(0.11, 0.02 + 0.006 * w)  # degrees; stays inside the 0.25° cell
                # wind_dir is atan2(v, u): the direction the air moves, counter-clockwise from east.
                ang = math.radians(d)
                tip = [
                    round(lon + math.cos(ang) * length, 4),
                    round(lat + math.sin(ang) * length, 4),
                ]
                feats.append(
                    feature(
                        "LineString",
                        [[lon, lat], tip],
                        {"wind_kmh": w, "wind_dir_deg": d, "time_ist": ist(times, step, "en")},
                    )
                )
        out[f"data/wind_{key}.geojson"] = collection(feats)

    ens = D.get("ensemble")
    if ens:
        step = STEPS["h35"]
        pc = ens["p_cell"][min(step, len(ens["p_cell"]) - 1)]
        feats = []
        for i, lat in enumerate(lats):
            for j, lon in enumerate(lons):
                k = i * n_lon + j
                feats.append(
                    feature(
                        "Polygon",
                        cell_polygon(lat, lon, 0.125),
                        {"lat": lat, "lon": lon, "p_stagnant": pc[k], "members": ens["members"]},
                    )
                )
        out["data/stagnation_probability_h35.geojson"] = collection(feats)

    summary = {r[0]: r for r in D.get("summary", [])}
    feats = []
    for name, lat, lon in SITES:
        r = summary.get(name)
        ser = D["sites"].get(name, {})
        props: dict = {"site": name}
        if r:
            props.update({
                "aqi_now": r[1], "aqi_peak": r[2], "category_peak": r[3], "dominant": r[4], "grap_stage": r[5],
                "stagnant_hours": r[6], "stagnant_night_hours": r[7], "min_blh_m": r[8], "peak_time_ist": r[9],
            })  # fmt: skip
        for key, step in STEPS.items():
            if ser:
                props[f"aqi_{key}"] = ser["aqi"][step]
                props[f"blh_m_{key}"] = ser["blh"][step]
        if ens and name in ens["sites"]:
            props["p_stagnant_h35"] = ens["sites"][name]["p"][STEPS["h35"]]
        feats.append(feature("Point", [lon, lat], props))
    out["data/sites.geojson"] = collection(feats)
    by_name = {f["properties"]["site"]: f for f in feats}
    out["data/alert_sites_evening.geojson"] = collection(
        [by_name[n] for n in ("Anand Vihar", "ITO", "Gurugram Vikas Sadan") if n in by_name]
    )
    out["data/alert_sites_peak.geojson"] = collection(
        [f for f in feats if f["properties"].get("aqi_h35", 0) >= 450]
    )

    out["data/delhi_nct.geojson"] = collection(
        [
            feature(
                "Polygon",
                [D["delhi"] + [D["delhi"][0]]],
                {"name": "Delhi NCT", "source": "geoBoundaries (CC BY 2.5 IN)"},
            )
        ]
    )
    out["data/ncr_tile.geojson"] = collection(
        [
            feature(
                "Polygon",
                [[[76, 27.5], [80, 27.5], [80, 31.5], [76, 31.5], [76, 27.5]]],
                {"name": "Delhi-NCR tile", "resolution_deg": 0.25},
            )
        ]
    )
    out["data/coarse_cell.geojson"] = collection(
        [
            feature(
                "Polygon",
                [[[76.8, 28.4], [77.2, 28.4], [77.2, 28.8], [76.8, 28.8], [76.8, 28.4]]],
                {"name": "one 0.4° cell of Aurora Air Pollution", "resolution_deg": 0.4},
            )
        ]
    )
    return out


# --------------------------------------------------------------------------------------- symbology
def rgba_rule(
    rid: str,
    fill: list[float] | None = None,
    stroke: list[float] | None = None,
    width: float | None = None,
    circle: bool = False,
) -> dict:
    maps = []
    if fill is not None:
        maps.append(
            {
                "scale": {"scheme": "constant_rgba", "params": {"value": fill}},
                "encodings": ["circle-fill-color" if circle else "fill-color"],
            }
        )
    if stroke is not None:
        maps.append(
            {
                "scale": {"scheme": "constant_rgba", "params": {"value": stroke}},
                "encodings": ["circle-stroke-color" if circle else "stroke-color"],
            }
        )
    if width is not None:
        maps.append(
            {
                "scale": {"scheme": "constant_num", "params": {"value": width}},
                "encodings": ["circle-stroke-width" if circle else "stroke-width"],
            }
        )
    return {"id": rid, "mappings": maps}


def categorical_rule(
    rid: str, field: str, stops: list[tuple[str, list[float]]], fallback: list[float], encoding: str
) -> dict:
    scale = {
        "scheme": "categorical",
        "params": {
            "colorRamp": "viridis",
            "fallback": fallback,
            "colorStops": [{"stop": s, "color": c} for s, c in stops],
        },
    }
    return {"id": rid, "fields": [field], "mappings": [{"scale": scale, "encodings": [encoding]}]}


def colormap_rule(
    rid: str,
    field: str,
    stops: list[tuple[float, list[float]]],
    fallback: list[float],
    encoding: str,
) -> dict:
    scale = {"scheme": "colorMap", "params": {"name": "Blues", "nShades": 5, "mode": "equal interval", "reverse": False, "fallback": fallback,
                                               "domain": [stops[0][0], stops[-1][0]], "colorStops": [{"stop": s, "color": c} for s, c in stops]}}  # fmt: skip
    return {"id": rid, "fields": [field], "mappings": [{"scale": scale, "encodings": [encoding]}]}


def grammar(layer_id: str, rules: list[dict]) -> dict:
    return {"layers": [{"id": uid(layer_id, "grammar"), "rules": rules}]}


def aqi_symbology(layer_id: str, alpha: float = 0.72) -> dict:
    stops = [(c[1], hex_rgba(c[3], alpha)) for c in CATS]
    return grammar(layer_id, [
        categorical_rule(uid(layer_id, "fill"), "category", stops, [200, 200, 200, 0.4], "fill-color"),
        rgba_rule(uid(layer_id, "stroke"), stroke=[255, 255, 255, 0.35], width=0.5),
    ])  # fmt: skip


def sites_symbology(layer_id: str) -> dict:
    stops = [(c[1], hex_rgba(c[3], 1.0)) for c in CATS]
    return grammar(layer_id, [
        categorical_rule(uid(layer_id, "fill"), "category_peak", stops, [60, 60, 60, 1], "circle-fill-color"),
        rgba_rule(uid(layer_id, "stroke"), stroke=[255, 255, 255, 1], width=1.5, circle=True),
        {"id": uid(layer_id, "radius"), "mappings": [{"scale": {"scheme": "constant_num", "params": {"value": 7}}, "encodings": ["circle-radius"]}]},
    ])  # fmt: skip


def ring_symbology(layer_id: str) -> dict:
    """Large accent ring around a site: where an alert or message is issued in the current scene."""
    return grammar(layer_id, [
        rgba_rule(uid(layer_id, "ring"), fill=[11, 110, 143, 0.15], stroke=hex_rgba(ACCENT, 1.0), width=3.0, circle=True),
        {"id": uid(layer_id, "radius"), "mappings": [{"scale": {"scheme": "constant_num", "params": {"value": 14}}, "encodings": ["circle-radius"]}]},
    ])  # fmt: skip


def outline_symbology(
    layer_id: str, stroke: list[float], width: float, fill: list[float] | None = None
) -> dict:
    return grammar(
        layer_id,
        [rgba_rule(uid(layer_id, "style"), fill=fill or [0, 0, 0, 0], stroke=stroke, width=width)],
    )


def probability_symbology(layer_id: str) -> dict:
    stops = [(0.0, hex_rgba(ACCENT, 0.0)), (1.0, hex_rgba(ACCENT, 0.85))]
    return grammar(
        layer_id,
        [colormap_rule(uid(layer_id, "fill"), "p_stagnant", stops, [0, 0, 0, 0], "fill-color")],
    )


# --------------------------------------------------------------------------------------- text
# --------------------------------------------------------------------------------------- scenes
# The scene text is shared with the storyboard slides (storyboard_scenes.py) and written for a
# general audience. It is HTML with sizes in em; the wrapper below sets the base size for the story
# panel. The panel renders markdown with JupyterLab's rendermime, which keeps inline styles.
BODY_STYLE = "font-size:18px; line-height:1.55; min-height:84vh;"
MUTED = "#64748b"


def legend_html(m: dict, lang: str) -> str:
    """What the map shows in this scene: AQI colours, probability ramp, wind, rings, labels."""

    def sw(c: str) -> str:
        return f"<span style='display:inline-block; width:.9em; height:.9em; background:{c}; border-radius:2px; vertical-align:-.1em; margin-right:.25em;'></span>"

    parts = []
    if m["prob"]:
        parts.append("<span style='display:inline-block; width:5em; height:.8em; background:linear-gradient(to right, rgba(11,110,143,.05), rgba(11,110,143,.85)); vertical-align:-.05em; margin-right:.3em;'></span>"
                     + text(lang, "정체 확률 0 → 100%", "stagnation probability 0 → 100%"))  # fmt: skip
    elif m["aqi"]:
        parts.append(" ".join(f"{sw(c[3])}{c[2] if lang == 'ko' else c[1]}" for c in CATS))
    if m["wind"]:
        parts.append(
            text(
                lang,
                "검은 선 = 10 m 바람 (방향·세기)",
                "black lines = 10 m wind (direction, strength)",
            )
        )
    if m["grid"]:
        parts.append(
            text(
                lang,
                "가는 격자 = Aurora 1.5 계산 칸 (0.25°)",
                "thin grid = Aurora 1.5 cells (0.25°)",
            )
        )
    if m["coarse"]:
        parts.append(
            text(
                lang,
                "점선 사각형 = 대기오염 모델 칸 하나 (0.4°)",
                "dashed square = one air-pollution model cell (0.4°)",
            )
        )
    if m["view"] in ("delhi", "hotspot"):
        parts.append(
            text(
                lang,
                "점 = 대표 지점 10곳, 이름 옆 숫자 = Aurora 예측값",
                "dots = ten sites, number next to the name = Aurora forecast",
            )
        )
    if not parts:
        return ""
    body = "".join(f"<div style='margin:.15em 0;'>{x}</div>" for x in parts)
    return (f"<div style='margin-top:.8em; padding:.5em .7em; border:1px solid rgba(100,116,139,.35); border-radius:8px; font-size:.78em;'>"
            f"<b style='color:{MUTED};'>{text(lang, '지도 보기', 'On the map')}</b>{body}</div>")  # fmt: skip


def scene_html(sc: dict, lang: str) -> str:
    return (f"<div style='{BODY_STYLE}'><div style='font-size:.8em; color:{MUTED}; letter-spacing:.03em; margin:0 0 .5em;'>{sc['eyebrow']}</div>"
            f"{sc['body']}{legend_html(sc['map'], lang)}</div>")  # fmt: skip


def chapters(D: dict, lang: str) -> list[dict]:
    out = []
    for sc in scenes(D, lang):
        m = sc["map"]
        out.append({"key": sc["key"], "title": sc["title"], "html": scene_html(sc, lang), "fig": sc["fig"], "view": m["view"], "aqi": m["aqi"], "wind": m["wind"],
                    "grid": m["grid"], "coarse": m["coarse"], "prob": m["prob"], "marker": m["marker"]})  # fmt: skip
    return out


# --------------------------------------------------------------------------------------- labels
TOWNS = [  # NCR towns for the tile view
    # towns adjoining Delhi (Gurugram, Noida, Ghaziabad, Faridabad) are left out: they crowd the New Delhi label
    ("Sonipat", 28.99, 77.02), ("Meerut", 28.98, 77.71), ("Panipat", 29.39, 76.97), ("Rohtak", 28.90, 76.61),
    ("Karnal", 29.69, 76.99), ("Alwar", 27.55, 76.60), ("Mathura", 27.49, 77.67), ("Aligarh", 27.88, 78.08),
    ("Chandigarh", 30.73, 76.78), ("Dehradun", 30.32, 78.03), ("Agra", 27.18, 78.01),
]  # fmt: skip
LABEL_BOXES = {  # lon0, lat0, lon1, lat1 covered by each label image
    "world": (40.0, -5.0, 120.0, 50.0), "india": (60.0, 4.0, 100.0, 38.0), "tile": (74.5, 26.5, 81.5, 32.5),
    "delhi": (76.65, 28.2, 77.65, 29.05), "hotspot": (77.15, 28.5, 77.47, 28.76),
}  # fmt: skip
LABEL_PLACE = {  # site -> (dx, dy) in view widths, horizontal anchor; keeps neighbouring labels apart
    "Anand Vihar": (0.02, 0.045, "left"), "ITO": (-0.02, 0.0, "right"), "Punjabi Bagh": (-0.02, 0.0, "right"),
    "Rohini": (-0.02, 0.0, "right"), "Jahangirpuri": (0.02, 0.0, "left"), "R K Puram": (0.0, -0.04, "center"),
    "Dwarka Sector 8": (-0.02, 0.0, "right"), "Okhla Phase 2": (0.02, -0.01, "left"),
    "Noida Sector 62": (0.02, -0.03, "left"), "Gurugram Vikas Sadan": (0.02, 0.0, "left"),
}  # fmt: skip
LABEL_PX_PER_DEG = {
    "world": 12,
    "india": 40,
    "tile": 230,
    "delhi": 1600,
    "hotspot": 5000,
}  # ~2x screen scale


def _merc_y(lat: float) -> float:
    return math.degrees(math.log(math.tan(math.pi / 4 + math.radians(lat) / 2)))


def render_labels(D: dict, lang: str, out_dir: Path) -> dict[str, tuple[str, list]]:
    """Draw place names (and, for sites, Aurora values) on transparent PNGs in Web Mercator space.

    Returns {key: (path relative to the .jGIS, corner coordinates)} for ImageSource layers."""
    import matplotlib.pyplot as plt
    from matplotlib import patheffects

    out_dir.mkdir(parents=True, exist_ok=True)
    halo = [patheffects.withStroke(linewidth=7, foreground="white")]
    res: dict[str, tuple[str, list]] = {}
    summary = {r[0]: r for r in D.get("summary", [])}
    ens = D.get("ensemble") or {}

    def canvas(view: str):
        x0, y0, x1, y1 = LABEL_BOXES[view]
        k = LABEL_PX_PER_DEG[view]
        wpx, hpx = (x1 - x0) * k, (_merc_y(y1) - _merc_y(y0)) * k
        fig = plt.figure(figsize=(wpx / 100, hpx / 100), dpi=100)
        ax = fig.add_axes([0, 0, 1, 1])
        ax.set_xlim(x0, x1)
        ax.set_ylim(_merc_y(y0), _merc_y(y1))
        ax.axis("off")
        fig.patch.set_alpha(0)
        return fig, ax

    def save(key: str, view: str, fig) -> None:
        rel = f"labels/{lang}/{key}.png"
        fig.savefig(out_dir / f"{key}.png", transparent=True, dpi=100)
        plt.close(fig)
        x0, y0, x1, y1 = LABEL_BOXES[view]
        res[key] = (rel, [[x0, y1], [x1, y1], [x1, y0], [x0, y0]])

    def put(ax, lon, lat, label, size, dot=None, dx=0.0, weight="bold", ha="left", dy=0.0):
        if dot:
            ax.scatter(
                [lon],
                [_merc_y(lat)],
                s=dot,
                c="#1e293b",
                edgecolors="white",
                linewidths=2,
                zorder=3,
            )
        ax.text(lon + dx, _merc_y(lat + dy), label, fontsize=size, fontweight=weight, color="#1e293b",
                ha=ha, va="center", path_effects=halo, zorder=4)  # fmt: skip

    # world: India and Delhi
    fig, ax = canvas("world")
    put(ax, 79.0, 22.0, text(lang, "인도", "India"), 34, ha="center")
    put(ax, 77.21, 28.61, text(lang, "뉴델리", "New Delhi"), 28, dot=200, dx=1.8)
    save("world", "world", fig)
    # india: major cities
    fig, ax = canvas("india")
    for name, la, lo in D["cities"]:
        put(
            ax,
            lo,
            la,
            name,
            30 if name == "New Delhi" else 24,
            dot=300 if name == "New Delhi" else 170,
            dx=0.55,
        )
    save("india", "india", fig)
    # tile: NCR towns
    fig, ax = canvas("tile")
    put(ax, 77.21, 28.61, text(lang, "뉴델리", "New Delhi"), 32, dot=360, dx=0.08)
    for name, la, lo in TOWNS:
        put(ax, lo, la, name, 24, dot=150, dx=0.06, weight="normal")
    save("tile", "tile", fig)
    # sites with Aurora values per scene
    for view in ("delhi", "hotspot"):
        k = 1.0 if view == "delhi" else 0.32
        for step_key in ("h00", "h08", "h35", "prob"):
            if view == "hotspot" and step_key != "h35":
                continue
            fig, ax = canvas(view)
            for name, la, lo in [(s[0], s[1], s[2]) for s in SITES]:
                ser = D["sites"].get(name, {})
                if step_key == "prob":
                    pv = (ens.get("sites", {}).get(name) or {}).get("p")
                    val = f"{text(lang, '정체', 'P(stag.)')} {round(100 * pv[35])}%" if pv else ""
                else:
                    a = ser.get("aqi", [None] * 48)[STEPS[step_key]]
                    val = f"AQI {a}" if a is not None else ""
                big = name == HOTSPOT or view == "hotspot"
                pdx, pdy, ha = LABEL_PLACE.get(name, (0.02, 0.0, "left"))
                put(ax, lo, la, f"{name}\n{val}", 30 if big else 24, dx=pdx * k, dy=pdy * k, ha=ha)
            save(f"sites_{view}_{step_key}", view, fig)
    _ = summary
    return res


def label_key(view: str, ch: dict) -> str:
    if view in ("world", "india", "tile"):
        return view
    if view == "hotspot":
        return "sites_hotspot_h35"
    if ch["prob"]:
        return "sites_delhi_prob"
    return f"sites_delhi_{ch['aqi'] if ch['aqi'] in ('h00', 'h08') else 'h35'}"


def build_document(D: dict, lang: str, geo: dict[str, dict], story_type: str) -> dict:
    ko = lang == "ko"
    times = D["times"]

    def t(a: str, b: str) -> str:
        return a if ko else b

    sources: dict[str, dict] = {}
    layers: dict[str, dict] = {}
    tree: list[str] = []
    names: dict[str, str] = {}  # logical key -> layer name
    ids: dict[
        str, str
    ] = {}  # logical key -> layer id (layerOverride.targetLayer is compared with the id)

    def add_source(key: str, stype: str, name: str, params: dict) -> str:
        sid = uid(lang, "source", key)
        sources[sid] = {"type": stype, "name": name, "parameters": params}
        return sid

    def add_layer(key: str, ltype: str, name: str, params: dict, visible: bool) -> str:
        lid = uid(lang, "layer", key)
        layers[lid] = {"type": ltype, "name": name, "visible": visible, "parameters": params}
        tree.append(lid)
        names[key] = name
        ids[key] = lid
        return lid

    def geojson_layer(
        key: str,
        path: str,
        name: str,
        symbology,
        visible: bool = False,
        opacity: float = 1.0,
        source_key: str | None = None,
    ) -> str:
        if source_key is None:
            sid = add_source(key, "GeoJSONSource", f"{name} Source", {"path": path})
        else:
            sid = uid(lang, "source", source_key)
        lid = uid(lang, "layer", key)
        return add_layer(
            key,
            "VectorLayer",
            name,
            {"source": sid, "opacity": opacity, "symbologyState": symbology(lid)},
            visible,
        )

    osm = add_source("osm", "RasterSource", "OpenStreetMap.Mapnik", {
        "url": "https://tile.openstreetmap.org/{z}/{x}/{y}.png", "minZoom": 0, "maxZoom": 19, "attribution": "(C) OpenStreetMap contributors",
        "htmlAttribution": "", "provider": "OpenStreetMap", "bounds": [], "urlParameters": {}, "interpolate": False,
    })  # fmt: skip
    add_layer("basemap", "RasterLayer", "OpenStreetMap", {"source": osm, "opacity": 1.0}, True)

    for key, step in STEPS.items():
        geojson_layer(
            f"aqi_{key}",
            f"data/aqi_{key}.geojson",
            t(f"AQI {ist(times, step, 'ko')}", f"AQI {ist(times, step, 'en')}"),
            aqi_symbology,
            visible=(key == "h35"),
        )
    if "data/stagnation_probability_h35.geojson" in geo:
        geojson_layer(
            "prob_h35",
            "data/stagnation_probability_h35.geojson",
            t(f"정체 확률 {ist(times, 35, 'ko')}", f"P(stagnant) {ist(times, 35, 'en')}"),
            probability_symbology,
        )
    geojson_layer(
        "grid",
        "data/aqi_h00.geojson",
        t("0.25° 격자 (Aurora 1.5)", "0.25° grid (Aurora 1.5)"),
        lambda lid: outline_symbology(lid, [90, 90, 90, 0.6], 0.6),
        source_key="aqi_h00",
    )
    geojson_layer(
        "coarse",
        "data/coarse_cell.geojson",
        t("0.4° 셀 1개 (Aurora Air Pollution)", "One 0.4° cell (Aurora Air Pollution)"),
        lambda lid: outline_symbology(lid, [40, 40, 40, 1], 1.5, fill=[120, 110, 90, 0.35]),
    )
    for key in WIND_STEPS:
        step = STEPS[key]
        geojson_layer(
            f"wind_{key}",
            f"data/wind_{key}.geojson",
            t(f"10 m 바람 {ist(times, step, 'ko')}", f"10 m wind {ist(times, step, 'en')}"),
            lambda lid: outline_symbology(lid, [30, 30, 30, 0.8], 1.5),
        )
    geojson_layer(
        "tile",
        "data/ncr_tile.geojson",
        t("델리 NCR 타일 (27.5–31.5°N, 76–80°E)", "Delhi-NCR tile (27.5–31.5°N, 76–80°E)"),
        lambda lid: outline_symbology(lid, hex_rgba(ACCENT, 1.0), 2.0),
        visible=True,
    )
    geojson_layer(
        "delhi",
        "data/delhi_nct.geojson",
        t("델리 NCT 경계", "Delhi NCT boundary"),
        lambda lid: outline_symbology(lid, [30, 30, 30, 0.9], 2.0),
        visible=True,
    )
    geojson_layer(
        "sites",
        "data/sites.geojson",
        t("대표 지점 10곳 (색: 정점 범주)", "Ten reporting sites (colour: peak category)"),
        sites_symbology,
        visible=True,
    )
    geojson_layer(
        "alert_evening",
        "data/alert_sites_evening.geojson",
        t("저녁 경보 대상 지점 (교통)", "Evening alert sites (traffic)"),
        ring_symbology,
    )
    geojson_layer(
        "alert_peak",
        "data/alert_sites_peak.geojson",
        t("정점 AQI 450 이상 지점", "Sites at or above AQI 450 at the peak"),
        ring_symbology,
    )
    hs = next(s for s in SITES if s[0] == HOTSPOT)
    marker_src = add_source(
        "marker",
        "MarkerSource",
        f"{HOTSPOT} Marker",
        {"color": ACCENT, "feature": {"coords": merc(hs[2], hs[1])}},
    )
    add_layer(
        "marker",
        "VectorLayer",
        HOTSPOT,
        {"source": marker_src, "opacity": 1.0, "symbologyState": {}},
        False,
    )

    for key, (rel, coords) in render_labels(D, lang, HERE / "storymap" / "labels" / lang).items():
        sid = add_source(
            f"labels_{key}", "ImageSource", f"labels {key}", {"path": rel, "coordinates": coords}
        )
        add_layer(
            f"labels_{key}",
            "ImageLayer",
            t("지명·값 라벨 ", "Labels ") + key,
            {"source": sid, "opacity": 1.0},
            False,
        )
    toggles = [k for k in names if k != "basemap"]
    chs = chapters(D, lang)
    # The non-map figures of the storyboard slides (schematics, charts, diagrams) are shown at the
    # top of the matching scene card; scenes whose slide figure is a map use the live map instead.
    setup_fonts(lang)
    img_dir = HERE / "storymap" / "img" / lang
    img_dir.mkdir(parents=True, exist_ok=True)
    first_view = chs[0]["view"]
    segments: list[str] = []
    for i, ch in enumerate(chs):
        image, caption = "", ""
        if ch["fig"][0] != "map":
            image = png_data_uri(
                make_figure(D, lang, ch["fig"]), img_dir / f"{i + 1:02d}_{ch['key']}.png"
            )
            caption = text(lang, "그림 · ", "Figure · ") + ch["title"]
        on = {"tile", "delhi", "sites"}
        if ch["aqi"]:
            on.add(f"aqi_{ch['aqi']}")
        if ch["wind"]:
            on.add(f"wind_{ch['wind']}")
        if ch["grid"]:
            on.add("grid")
        if ch["coarse"]:
            on.add("coarse")
        if ch["prob"] and "prob_h35" in names:
            on.add("prob_h35")
        if ch["marker"]:
            on.add("marker")
        if ch["key"] == "evening":
            on.add("alert_evening")
        if ch["key"] in ("peak", "message"):
            on.add("alert_peak")
        if ch["view"] in ("world", "india"):
            on -= {"sites", "delhi"}
        on.add("labels_" + label_key(ch["view"], ch))
        params = {
            "zoom": zoom(ch["view"]), "extent": extent(ch["view"]),
            "enableIdentify": True,
            "content": {
                "contentMode": "map",
                "markdown": ch["html"],
                "image": image,
                "imageCaption": caption,
                "paneAlignment": "end",
                "panelWidth": CARD_WIDTH,
            },
            "transition": {"type": "linear", "time": 1.5},
            "layerOverride": [{"targetLayer": ids[k], "visible": k in on} for k in toggles],
        }  # fmt: skip
        segments.append(
            add_layer(
                f"segment_{i:02d}_{ch['key']}",
                "StorySegmentLayer",
                f"{i + 1}. {ch['title']}",
                params,
                True,
            )
        )

    story_id = uid(lang, "story")
    doc = {
        "schemaVersion": "0.6.0",
        "sources": sources,
        "layers": layers,
        "layerTree": tree,
        "options": {
            **initial_view(first_view),
            "bearing": 0.0,
            "pitch": 0.0,
            "projection": "EPSG:3857",
            "extent": extent(first_view),
            "useExtent": False,
        },  # fmt: skip
        "stories": {
            story_id: {
                "title": t("델리 스모그 스토리 맵", "Delhi Smog Story Map"),
                "storyType": story_type,
                "storySegments": segments,
                "showGradient": True,
                "storyPanelOpacity": 0.86,
                "overlayContentWidth": "100%",
            }
        },
        "viewState": {},
        "annotations": {},
        "presets": {},
        "metadata": {
            "generator": "examples/delhi_air_quality/build_storymap_jgis.py",
            "language": lang,
            "attribution": D.get("attribution", ""),
            "provenance": json.dumps(D.get("provenance") or {}, ensure_ascii=False),
        },
    }
    return doc


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[2])
    ap.add_argument(
        "--data",
        type=Path,
        default=HERE / "storymap_data.js",
        help="storymap_data.js from build_storymap_data.py",
    )
    ap.add_argument(
        "--out",
        type=Path,
        default=HERE / "storymap",
        help="output folder (default: storymap/ next to this script)",
    )
    ap.add_argument(
        "--story-type",
        choices=["guided", "Vertical Scroll"],
        default="Vertical Scroll",
        help="JupyterGIS story type",
    )
    ap.add_argument("--langs", default="ko,en", help="comma-separated languages to build (ko, en)")
    a = ap.parse_args()

    D = load_data(a.data)
    geo = build_geojson(D)
    (a.out / "data").mkdir(parents=True, exist_ok=True)
    for rel, fc in geo.items():
        (a.out / rel).write_text(
            json.dumps(fc, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8"
        )
    for lang in a.langs.split(","):
        doc = build_document(D, lang, geo, a.story_type)
        target = a.out / f"delhi_aq_storymap_{lang}.jGIS"
        target.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        n_seg = len(next(iter(doc["stories"].values()))["storySegments"])
        print(
            f"wrote {target} ({target.stat().st_size // 1024} KB, {n_seg} segments, {len(doc['layers']) - n_seg} layers)"
        )
    print(f"wrote {len(geo)} GeoJSON files to {a.out / 'data'}")


if __name__ == "__main__":
    main()
