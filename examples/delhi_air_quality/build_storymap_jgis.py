"""Copyright (c) Microsoft Corporation. Licensed under the MIT license.

Build a JupyterGIS story map (`.jGIS`) from `storymap_data.js`, for notebook.link.

    python build_storymap_jgis.py                       # writes storymap/ next to this script
    python build_storymap_jgis.py --story-type "Vertical Scroll"

The output folder is self-contained and has no dependency on Claude or on any other hosted
service: two `.jGIS` documents (Korean and English) share the GeoJSON layers written to
`storymap/data/`, and `environment.yml` / `nblink-lock.json` / `jupyter-lite.json` make the folder
"notebook.link ready". Open a document with JupyterGIS in JupyterLab, JupyterLite or notebook.link
and start the story from the Story panel; the Specta view of notebook.link plays it full screen.

The `.jGIS` files are plain JSON following the JupyterGIS project schema (schemaVersion 0.6.0, the
version shipped by `jupytergis-lite` 0.16.x on emscripten-forge). Story stops are
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
    "world": (-170.0, -58.0, 190.0, 78.0),
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


def extent(view: str) -> list[float]:
    x0, y0, x1, y1 = VIEWS[view]
    a, b = merc(x0, y0), merc(x1, y1)
    return [a[0], a[1], b[0], b[1]]


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
def derived(D: dict, lang: str) -> dict:
    """Numbers and strings that storymap.html fills in at run time."""
    PV = D.get("provenance") or {}
    met_real = "Aurora" in (PV.get("meteorology") or "")
    pm_real = "Aurora" in (PV.get("pollutants") or "")
    ens_real = "Aurora" in (PV.get("ensemble") or "")
    ko = lang == "ko"
    tags = {
        "met": ("기상: Aurora 1.5" if ko else "Weather: Aurora 1.5")
        if met_real
        else ("기상: 합성" if ko else "Weather: synthetic"),
        "pm": ("농도: Aurora Air Pollution" if ko else "Pollutants: Aurora Air Pollution")
        if pm_real
        else (
            "농도: 합성 (CAMS 계정 필요)" if ko else "Pollutants: synthetic (CAMS needs an account)"
        ),
        "ens": ("앙상블: Aurora 1.5 Ensemble" if ko else "Ensemble: Aurora 1.5 Ensemble")
        if ens_real
        else ("앙상블: 시뮬레이션" if ko else "Ensemble: simulated"),
        "method": "추가 분석 (다른 방법)" if ko else "Additional method",
        "synthobs": "합성 관측" if ko else "Synthetic observations",
    }
    av = D["sites"].get(HOTSPOT)
    night = av["blh"][3:14] if av else []
    winds = sorted(av["wind"][3:14]) if av else []
    mins = [r[8] for r in D.get("summary", [])]
    ens = D.get("ensemble")
    return {
        "PV": PV, "met_real": met_real, "pm_real": pm_real, "ens_real": ens_real, "tags": tags,
        "night_blh_min": min(night) if night else None,
        "night_wind_med": winds[len(winds) // 2] if winds else None,
        "blh_range": f"{min(mins)}–{max(mins)}" if mins else "",
        "members": ens["members"] if ens else None,
        "init": PV["init_time"].replace("T", " ") + " UTC" if PV.get("init_time") else "",
    }  # fmt: skip


def md_table(header: list[str], rows: list[list], align: str | None = None) -> str:
    sep = (
        "|"
        + "|".join(
            " --- " if (align or "l" * len(header))[i] == "l" else " ---: "
            for i in range(len(header))
        )
        + "|"
    )
    body = ["| " + " | ".join(str(c) for c in r) + " |" for r in rows]
    return "\n".join(["| " + " | ".join(header) + " |", sep] + body)


GLOSS = [
    (
        "AQI",
        "Air Quality Index",
        "대기질 지수",
        "0~500 척도. 인도 CPCB 기준으로 좋음·양호·보통·나쁨·매우 나쁨·위험 6단계",
        "0–500 scale with six CPCB categories from Good to Severe",
    ),
    (
        "CPCB",
        "Central Pollution Control Board",
        "인도 중앙오염관리위원회",
        "인도 환경부 산하 기관. 국가 AQI 기준과 전국 관측망을 운영",
        "India's national pollution regulator; runs the national AQI and monitoring network",
    ),
    (
        "GRAP",
        "Graded Response Action Plan",
        "단계별 대응 조치 계획",
        "AQI 구간별로 미리 정한 조치(1~4단계: 건설 제한, 차량 제한, 원격수업, 재택근무 등)",
        "Pre-agreed measures by AQI band (Stages I–IV: construction limits, vehicle restrictions, online classes, work-from-home)",
    ),
    (
        "CAQM",
        "Commission for Air Quality Management in NCR and Adjoining Areas",
        "수도권 대기질관리위원회",
        "델리 수도권의 대기질 정책 기구. GRAP 단계 발동 권한을 가짐",
        "The statutory body for air quality in Delhi-NCR; it invokes GRAP stages",
    ),
    (
        "DPCC",
        "Delhi Pollution Control Committee",
        "델리 오염관리위원회",
        "델리 정부의 오염 관리 기관. 시내 관측소를 운영",
        "Delhi government's pollution agency; operates the city's monitoring stations",
    ),
    (
        "NCR",
        "National Capital Region",
        "델리 수도권",
        "델리와 인접한 하리아나·우타르프라데시·라자스탄의 도시(구루그람, 노이다 등)를 묶은 권역",
        "Delhi plus neighbouring cities in Haryana, Uttar Pradesh and Rajasthan (Gurugram, Noida and others)",
    ),
    (
        "NCT",
        "National Capital Territory of Delhi",
        "델리 수도직할지",
        "델리의 행정 단위. 지도의 굵은 외곽선",
        "Delhi's administrative territory; the bold outline on the map",
    ),
    (
        "PM2.5",
        "particulate matter smaller than 2.5 micrometres",
        "초미세먼지",
        "지름 2.5 µm 이하 입자. 단위 µg/m³",
        "Particles up to 2.5 µm across, in µg/m³",
    ),
    (
        "PM10",
        "particulate matter smaller than 10 micrometres",
        "미세먼지",
        "지름 10 µm 이하 입자. 단위 µg/m³",
        "Particles up to 10 µm across, in µg/m³",
    ),
    (
        "CAMS",
        "Copernicus Atmosphere Monitoring Service",
        "코페르니쿠스 대기 모니터링 서비스",
        "EU의 전지구 대기 조성 분석·예보 서비스. Air Pollution 모델의 입력",
        "The EU's global atmospheric-composition analysis and forecast service; input to the Air Pollution model",
    ),
    (
        "ERA5",
        "ECMWF Reanalysis, 5th generation",
        "유럽중기예보센터 5세대 재분석 자료",
        "과거 기상을 격자로 재구성한 자료. 이 예제에서 Aurora 1.5의 입력",
        "A gridded reconstruction of past weather; the Aurora 1.5 input in this example",
    ),
    (
        "IFS HRES T0",
        "Integrated Forecasting System, high resolution, analysis at lead time 0",
        "ECMWF 통합예보시스템 고해상도 초기 분석장",
        "Aurora 1.5가 파인튜닝된 실시간 입력 자료",
        "The real-time input Aurora 1.5 was fine-tuned on",
    ),
    ("IST", "Indian Standard Time", "인도 표준시", "UTC+5:30", "UTC+5:30"),
    (
        "BLH",
        "boundary-layer height",
        "대기경계층 높이(혼합층 높이)",
        "오염이 섞이는 하층 대기의 두께. 낮을수록 지표 농도가 오름",
        "Depth of the lower atmosphere in which pollution mixes; lower means higher surface concentrations",
    ),
]


def chapters(D: dict, lang: str) -> list[dict]:
    """Scene list mirroring storymap.html. Each scene: title, markdown, view, map/markdown mode and layers."""
    ko = lang == "ko"
    X = derived(D, lang)
    T = X["tags"]
    M = D.get("messages") or {}
    times = D["times"]
    ens = D.get("ensemble")

    def t(a: str, b: str) -> str:
        return a if ko else b

    def tagline(eyebrow: str, *keys: str) -> str:
        parts = [eyebrow] + [T[k] for k in keys]
        return "*" + " · ".join(parts) + "*\n\n"

    def msg(lg: str, field: str, drop_first: bool = False) -> str:
        v = (M.get(lg) or {}).get(field)
        if not v:
            return ""
        if drop_first:
            v = "\n".join(v.split("\n")[1:])
        return "```text\n" + v.strip() + "\n```\n"

    S: list[dict] = []

    def add(
        key: str,
        title: str,
        md: str,
        view: str,
        mode: str = "map",
        aqi: str | None = None,
        wind: str | None = None,
        grid: bool = False,
        coarse: bool = False,
        prob: bool = False,
        marker: bool = False,
    ) -> None:
        S.append({"key": key, "title": title, "md": md.strip() + "\n", "view": view, "mode": mode, "aqi": aqi, "wind": wind,
                  "grid": grid, "coarse": coarse, "prob": prob, "marker": marker})  # fmt: skip

    prov_rows = [
        [t("초기 시각", "Initial time"), X["init"]],
        [
            t("기상 (혼합층·바람·기온)", "Weather (mixing height, wind, temperature)"),
            (X["PV"].get("meteorology", "") + t(" — Aurora 직접 분석", " — Aurora direct"))
            if X["met_real"]
            else t("합성 (데모)", "synthetic (demo)"),
        ],
        [
            t("오염 농도 (PM2.5, PM10, …)", "Pollutants (PM2.5, PM10, …)"),
            (X["PV"].get("pollutants", "") + t(" — Aurora 직접 분석", " — Aurora direct"))
            if X["pm_real"]
            else t(
                "합성 — CAMS 자료는 Atmosphere Data Store 계정이 필요해 이 실행에서는 대체값 사용",
                "synthetic — CAMS data needs an Atmosphere Data Store account, so stand-in values were used",
            ),
        ],
        [
            t("앙상블", "Ensemble"),
            (X["PV"].get("ensemble") or "none")
            + (t(" — Aurora 직접 분석", " — Aurora direct") if X["ens_real"] else ""),
        ],
        [
            t(
                "AQI·GRAP·정체 판정·보정·발송·자동화",
                "AQI, GRAP, stagnation rule, correction, delivery, scheduling",
            ),
            t(
                "추가 분석 (CPCB 공식, 규칙, 최소제곱, 소프트웨어)",
                "additional methods (CPCB formula, rules, least squares, software)",
            ),
        ],
    ]
    add(
        "intro",
        t(
            "시민에게 닿는 한 줄의 대기질 경보",
            "One line of air-quality warning that reaches a citizen",
        ),
        tagline(
            t(
                "Aurora 1.5 + Aurora Air Pollution · 스토리 맵",
                "Aurora 1.5 + Aurora Air Pollution · story map",
            )
        )
        + t(
            "Aurora는 Microsoft Research의 지구 시스템 파운데이션 모델입니다. 이 이야기는 그 모델로 인도 뉴델리의 48시간 대기질을 예측하고, 인도 CPCB 기준 AQI와 GRAP 단계로 바꿔 힌디어·영어·한국어 메시지를 만들기까지를 장면별로 따라갑니다. 지도는 세계에서 시작해 인도, 델리 수도권, 델리, 그리고 가장 심각한 지점으로 내려갑니다.",
            "Aurora is Microsoft Research's foundation model for the Earth system. This story follows it from a 48-hour forecast for New Delhi to a CPCB AQI, a GRAP stage and a message in Hindi, English and Korean. The map starts at the world and descends to India, the capital region, Delhi and the worst-hit site.",
        )
        + "\n\n### "
        + t("표기 구분", "How results are labelled")
        + "\n\n"
        + t(
            "- **Aurora 직접 분석** — Aurora 모델이 실제 초기장으로 계산한 결과\n- **추가 분석 (다른 방법)** — Aurora 출력 위에 통계·규칙·소프트웨어로 더한 분석(AQI 환산, 정체 판정, 편향 보정, 발송, 자동화)\n- **합성·시뮬레이션** — 모델을 돌리지 않고 만든 예시 값(데모 모드, 계정이 필요한 자료의 대체)",
            "- **Aurora direct** — computed by an Aurora model from a real initial condition\n- **Additional method** — analysis added on top of Aurora output by statistics, rules or software (AQI conversion, stagnation rule, bias correction, delivery, scheduling)\n- **Synthetic** — example values produced without running the model (demo mode, stand-ins for data that needs an account)",
        )
        + "\n\n"
        + md_table([t("항목", "Item"), t("출처", "Source")], prov_rows)
        + "\n\n"
        + t(
            "▶ 버튼으로 다음 장면으로 넘어가면 지도가 따라 움직입니다. 지도 장면에서는 ⓘ(Identify)로 셀과 지점의 값을 클릭해 볼 수 있습니다.",
            "Use the ▶ button to move to the next scene; the map follows. In map scenes the ⓘ (Identify) button lets you click cells and sites for their values.",
        ),
        "world",
    )

    add(
        "glossary",
        t("이 이야기에 나오는 약어", "Abbreviations used in this story"),
        tagline(t("용어 풀이", "Glossary"))
        + md_table(
            [t("약어", "Abbr."), t("영어 전체 이름", "Full name")]
            + ([t("한국어 명칭", "")] if ko else [])
            + [t("설명", "Meaning")],
            [
                [f"**{g[0]}**", g[1]] + ([g[2]] if ko else []) + [g[3] if ko else g[4]]
                for g in GLOSS
            ],
        ),
        "world",
        mode="markdown",
    )

    add(
        "background",
        t("왜 뉴델리이고, 왜 11월인가", "Why Delhi, why November"),
        tagline("0 · " + t("배경", "Background"))
        + t(
            "- 델리 NCR(수도권)은 매년 10월 말~1월에 세계 최악 수준의 미세먼지 에피소드를 겪습니다. 인접 주(펀자브, 하리아나)의 볏짚 소각, 디왈리 폭죽, 교통·건설·발전 배출이 겹치고, 겨울철 **낮은 혼합층(100~300 m)과 약한 바람**이 오염을 지표 근처에 가둡니다.\n"
            "- 인도 정부는 국가 AQI(CPCB 기준)와 단계별 대응계획 **GRAP**(CAQM 주관)을 운영합니다. AQI 구간별로 건설 중단, 차량 제한, 원격수업, 재택근무가 정해져 있어 **예보 → 단계 → 조치**의 연결이 제도적으로 존재합니다.\n"
            '- 핵심 질문은 "얼마나 나빠질지"가 아니라 **"언제, 어느 지역에서, 어떤 기상 조건 때문에 나빠지며, 시민은 무엇을 해야 하는가"**를 12~48시간 앞서 전달하는 것입니다.\n\n'
            "지도의 사각형이 이 예제가 다루는 델리 NCR 타일(27.5~31.5°N, 76~80°E)입니다.",
            "- Delhi-NCR suffers some of the world's worst particulate episodes from late October to January. Stubble burning in Punjab and Haryana, Diwali fireworks and traffic, construction and power emissions coincide with winter's **shallow mixing layer (100–300 m) and weak winds**, which trap pollution near the ground.\n"
            "- India runs a national AQI (CPCB scale) and a staged response plan, **GRAP** (run by CAQM). AQI bands map to construction bans, vehicle restrictions, online classes and work-from-home, so **forecast → stage → action** already exists.\n"
            '- The question is not "how bad" but **"when, where, because of which weather, and what should citizens do"**, 12 to 48 hours ahead.\n\n'
            "The square on the map is the Delhi-NCR tile this example covers (27.5–31.5°N, 76–80°E).",
        ),
        "india",
    )

    add(
        "system",
        t("Aurora가 두 번 등장한다", "Aurora appears twice"),
        tagline("2 · " + t("시스템 구성", "System"), "met", "pm")
        + t(
            "1. **입력** · CAMS 전지구 분석 0.4° (PM, NO2, SO2, O3, CO + 기상) · ERA5 또는 IFS HRES T0 0.25° (26개 표면 변수, 13개 기압면)\n"
            '2. **Aurora 0.4° Air Pollution** · 12시간 × 4 = 48 h. 로컬 GPU 또는 Foundry "Aurora" 엔드포인트\n'
            "3. **Aurora 1.5** · 6시간 × 8 + 시간별 서브스텝 = 48개 시간별 기상장 (경계층 높이, 10 m 풍속, 기온, 이슬점, 강수, 돌풍)\n"
            "4. **델리 후처리** · 10개 지점 보간 → CPCB AQI → GRAP 단계 → 정체 진단(풍속 < 10 km/h, 혼합층 < 500 m) → hi/en/ko 메시지 → 푸시·SMS·WhatsApp·앱\n\n"
            '**왜 두 모델인가.** Aurora 1.5는 기상 전용이라 오염물질을 예측하지 않습니다. 대신 **시간 단위**로 확산 조건을 줍니다. Air Pollution 모델은 농도를 직접 예측하지만 12시간 간격·0.4°입니다. 둘을 합치면 "농도는 어느 수준인가"와 "밤 몇 시부터 정체가 시작되는가"를 함께 말할 수 있습니다.\n\n'
            '**"고해상도"의 의미.** (1) 시간: 1.5의 `fine_lead_times=[1,…,6]`으로 1시간 간격. (2) 공간: 지도의 가는 격자가 1.5의 0.25° 셀이고, 이를 10개 지점으로 양선형 보간합니다. 격자 자체는 도시 내부 차이를 해소하지 못합니다(§6).\n\n'
            '**연계.** 저장소의 `msresearch-aurora/`(microsoft/vibe-kit의 Aurora 스킬)에서 React 지도 프런트엔드, 검증 유틸리티, 파인튠 스타터를 가져옵니다. 체크포인트는 HuggingFace `microsoft/aurora`에서 받고, GPU가 없으면 `--mode foundry`로 Azure AI Foundry의 "Aurora"/"Aurora-1.5" 엔드포인트에 작업을 보냅니다.',
            "1. **Inputs** · CAMS global analysis 0.4° (PM, NO2, SO2, O3, CO + meteorology) · ERA5 or IFS HRES T0 0.25° (26 surface variables, 13 levels)\n"
            '2. **Aurora 0.4° Air Pollution** · 12 h × 4 = 48 h. Local GPU or the Foundry "Aurora" endpoint\n'
            "3. **Aurora 1.5** · 6 h × 8 + hourly sub-steps = 48 hourly fields (boundary-layer height, 10 m wind, temperature, dew point, rain, gusts)\n"
            "4. **Delhi post-processing** · 10-site interpolation → CPCB AQI → GRAP stage → stagnation (wind < 10 km/h, mixing height < 500 m) → hi/en/ko messages → push, SMS, WhatsApp, app\n\n"
            '**Why two models.** Aurora 1.5 is weather-only and predicts no pollutants, but gives **hourly** dispersion conditions. The Air Pollution model predicts concentrations directly, at 12-hour steps and 0.4°. Together they answer "how high" and "from what hour tonight".\n\n'
            '**What "high resolution" means.** (1) Time: hourly from 1.5 with `fine_lead_times=[1,…,6]`. (2) Space: the thin grid on the map is 1.5\'s 0.25° cells, bilinearly interpolated to ten sites. The grid itself cannot resolve intra-city differences (§6).\n\n'
            '**Linkages.** The repository\'s `msresearch-aurora/` (the Aurora skill from microsoft/vibe-kit) supplies a React map frontend, validation utilities and a fine-tuning starter. Checkpoints come from HuggingFace `microsoft/aurora`; without a GPU, `--mode foundry` submits to the Azure AI Foundry "Aurora" and "Aurora-1.5" endpoints.',
        ),
        "tile",
        aqi="h00",
        grid=True,
    )

    add(
        "cast",
        t("누가 무엇을 받는가", "Who receives what"),
        tagline("1 · " + t("등장인물", "Cast"), "pm")
        + md_table(
            [t("역할", "Role"), t("원하는 것", "Wants"), t("산출물", "Output")],
            [
                [
                    t("일반 시민", "General public"),
                    t(
                        "오늘 밤/내일 아침 주의사항 한 줄",
                        "One line for tonight or tomorrow morning",
                    ),
                    "`short`",
                ],
                [
                    t("민감군과 보호자", "Sensitive groups, carers"),
                    t("구체적 행동과 시간대", "Concrete actions and time windows"),
                    "`long`",
                ],
                [
                    t("운영자 (DPCC/CAQM)", "Operators (DPCC/CAQM)"),
                    t("정점 시각, GRAP 근거, 추세", "Peak time, GRAP basis, trend"),
                    "`summary_by_site.csv`, `bulletin_*.md`",
                ],
                [
                    t("데이터/ML 엔지니어", "Data/ML engineers"),
                    t("재현 가능한 파이프라인", "Reproducible pipeline"),
                    "`--mode local|foundry`",
                ],
            ],
        )
        + "\n\n"
        + t(
            f"지도: 첫 예측 시각({ist(times, 0, lang)})의 AQI 타일. 색이 CPCB 범주입니다.",
            f"Map: the AQI tile at the first forecast hour ({ist(times, 0, lang)}). Colors are CPCB categories.",
        ),
        "tile",
        aqi="h00",
    )

    add(
        "s1s2",
        t(
            "11월 5일 17:30 IST, 초기장과 예측 실행",
            "5 Nov 17:30 IST, initial conditions and the forecast run",
        ),
        tagline("3 · S1 · S2", "met", "pm")
        + t(
            "12 UTC(= 17:30 IST)의 CAMS 00/12 UTC 분석과 ERA5 06/12 UTC로 `Batch` 두 개를 만들고 정적 변수 pickle을 읽습니다. Air Pollution 4스텝(+12/24/36/48 h), Aurora 1.5 8스텝 × 6 서브스텝(+1…+48 h)을 GPU 한 장 또는 Foundry에서 돌립니다. 10분 뒤 10개 지점으로 보간하고 12시간 농도를 시간별로 선형 보간한 뒤, 1.5의 시간별 혼합층·풍속으로 정체 시간대를 표시합니다.",
            "At 12 UTC (17:30 IST) two `Batch` objects are built from the CAMS 00/12 UTC analysis and ERA5 06/12 UTC, plus the static pickles. Air Pollution runs 4 steps (+12/24/36/48 h); Aurora 1.5 runs 8 steps × 6 sub-steps (+1…+48 h) on one GPU or on Foundry. Ten minutes later the fields are interpolated to ten sites, the 12-hourly concentrations to hourly, and stagnant hours are flagged from 1.5's hourly mixing height and wind.",
        ),
        "tile",
        aqi="h00",
        grid=True,
    )

    add(
        "evening",
        t("18:30 IST, 저녁 경보", "18:30 IST, the evening alert"),
        tagline("3 · S3 · S4", "pm", "method")
        + t(
            '첫 예측 시각. 델리 전체가 이미 "매우 나쁨" 이상이고, 교통 지점(Anand Vihar, ITO, Gurugram)이 가장 높습니다. 지점별 AQI와 GRAP 단계를 계산해 푸시/SMS용 한 줄 메시지를 내보냅니다. 운영자에게는 도시 헤드라인과 지점별 상세가 담긴 브리핑이 갑니다.',
            'The first forecast hour. All of Delhi is already "Very Poor" or worse, with traffic sites (Anand Vihar, ITO, Gurugram) highest. Per-site AQI and GRAP stage are computed and the one-line push/SMS message goes out; operators get a briefing with the city headline and per-site detail.',
        )
        + "\n\n**"
        + t("시민용 short · 힌디어", "Citizen short message · Hindi")
        + "**\n\n"
        + msg("hi", "short")
        + "\n**"
        + t("도시 헤드라인", "City headline")
        + "**\n\n"
        + msg(lang, "city"),
        "delhi",
        aqi="h00",
    )

    add(
        "night",
        t("11월 6일 02:30 IST, 정체가 시작된다", "6 Nov 02:30 IST, stagnation sets in"),
        tagline("3 · S6", "met", "method")
        + t(
            f"Aurora 1.5가 예측한 첫째 밤(11월 5일 22시~6일 08시) Anand Vihar의 혼합층은 최저 {X['night_blh_min']} m, 풍속 중앙값은 {X['night_wind_med']:.1f} km/h입니다. 지도의 짧은 선이 그 바람(셀 중심에서 바람이 불어가는 방향, 길이는 풍속)입니다. 배출이 같아도 섞일 공기가 얇아지면 지표 농도가 오릅니다. 메시지에는 \"밤~아침에 오염이 지표 근처에 쌓이기 쉽습니다\"로 들어가고, 민감군에게는 창문 닫기·새벽 운동 자제 리마인더를 보낼 수 있습니다.",
            f"For the first night (5 Nov 22:00 to 6 Nov 08:00) Aurora 1.5 puts Anand Vihar's mixing layer as low as {X['night_blh_min']} m with a median wind of {X['night_wind_med']:.1f} km/h; the short lines on the map are that wind (from the cell centre toward where the air moves, length by speed). With the same emissions and a thinner layer of air to mix into, surface concentrations rise. The message says \"pollution will tend to pool near the surface from night to morning\", and sensitive groups can get a reminder to close windows and skip early exercise.",
        ),
        "delhi",
        aqi="h08",
        wind="h08",
    )

    add(
        "peak",
        t("11월 7일 05:30 IST, 가장 심각한 곳", "7 Nov 05:30 IST, the worst-hit site"),
        tagline("3 · S7", "met", "pm", "method")
        + t(
            '두 번째 새벽. 동부 델리의 Anand Vihar(주간 버스터미널과 간선도로가 모인 교통 지점)가 AQI 500(위험)에 닿고, 인접한 ITO·Noida·Okhla도 450을 넘습니다. 이 시각이 지점별 요약표의 "정점 시각"이 되고, 06:00 IST 아침 업데이트는 등교·출근 전에 "오전 7~9시 최고치, 마스크 착용"을 보냅니다.',
            'The second pre-dawn. Anand Vihar in east Delhi (a traffic site where an interstate bus terminal meets arterial roads) reaches AQI 500 (Severe); neighbouring ITO, Noida and Okhla exceed 450. This hour becomes the "peak time" in the per-site summary, and the 06:00 IST morning update sends "peak 07:00–09:00, wear a mask" before school and commute.',
        )
        + "\n\n**"
        + t("운영자용 long · Anand Vihar", "Operator long message · Anand Vihar")
        + "**\n\n"
        + msg(lang, "long", drop_first=True),
        "hotspot",
        aqi="h35",
        wind="h35",
        marker=True,
    )

    add(
        "afternoon",
        t("11월 7일 14:30 IST, 낮의 숨 고르기", "7 Nov 14:30 IST, the afternoon breather"),
        tagline("3 · S6 · " + t("오후", "afternoon"), "met", "pm")
        + t(
            '혼합층이 1,000 m 가까이 올라가고 바람이 10 km/h를 넘는 몇 시간 동안 AQI가 400 아래로 내려갑니다. 그래도 "매우 나쁨"입니다. 이 구간이 민감군이 환기나 외출을 할 수 있는 창이고, 메시지는 그 시간대를 명시합니다. 사후(S8)에는 CPCB/DPCC 관측과 비교해 지점별 편향 보정 계수를 구합니다.',
            'For a few hours the mixing layer climbs toward 1,000 m, winds exceed 10 km/h and the AQI dips below 400. It is still "Very Poor". This is the window in which sensitive groups can ventilate or go out, and the message names it. Afterwards (S8) per-site predictions are compared with CPCB/DPCC observations to derive bias corrections.',
        ),
        "tile",
        aqi="h44",
        wind="h44",
    )

    add(
        "design",
        t("160자 안에 무엇·언제·어디·어떻게", "What, when, where and how in 160 characters"),
        tagline("4 · " + t("메시지 설계 원칙", "Message design principles"), "method")
        + t(
            "1. **무엇(수치+범주)·언제(IST 정점 시각)·어디(지점)·어떻게(행동 1~2개)**. `short`는 SMS/푸시, `long`은 앱 상세·브리핑용.\n"
            "2. **범주는 CPCB 용어 그대로**(좋음/양호/보통/나쁨/매우 나쁨/위험). 뉴스·공식 앱과 일치해야 혼란이 없다.\n"
            "3. **민감군을 먼저** 호명한다(어린이·노인·임산부·호흡기 질환자).\n"
            '4. **GRAP 단계는 "해당 수준"으로만**. 발효는 CAQM 권한이므로 "시행될 수 있습니다"로 쓰고 공식 공지를 안내한다.\n'
            '5. **기상 근거 한 문장**. 시민이 "왜 밤에 더 나쁜가"를 이해하면 행동 순응도가 올라간다.\n'
            '6. **면책 문구 고정**: "AI 모델(Aurora) 기반 참고 정보이며 공식 경보는 CPCB/CAQM을 따르세요."\n'
            "7. 힌디어(1차), 영어(2차), 운영팀용 한국어. 템플릿은 `HEALTH_ADVICE`, `GRAP_ADVICE`, `CATEGORY_NAMES`에 모여 있어 보건 전문가가 코드 없이 검수한다.",
            "1. **What (value and category), when (IST peak), where (site), how (one or two actions)**. `short` for SMS/push, `long` for app detail and briefings.\n"
            "2. **CPCB category names verbatim** (Good / Satisfactory / Moderate / Poor / Very Poor / Severe), matching the news and the official app.\n"
            "3. **Name sensitive groups first** (children, older adults, pregnant women, respiratory patients).\n"
            '4. **GRAP as "corresponding level" only**; enforcement is CAQM\'s call, so "may be enforced" plus a pointer to official notices.\n'
            "5. **One sentence of meteorological reasoning**; people who understand why nights are worse comply better.\n"
            '6. **A fixed disclaimer**: "AI-model (Aurora) guidance for information only; follow official CPCB/CAQM alerts."\n'
            "7. Hindi first, English second, Korean for the operating team. Templates live in `HEALTH_ADVICE`, `GRAP_ADVICE` and `CATEGORY_NAMES` so health experts can review wording without code.",
        ),
        "delhi",
        mode="markdown",
        aqi="h35",
    )

    mode_note = (
        t(
            "이 실행에서 혼합층·바람·기온은 Aurora 1.5가 ARCO-ERA5 초기장으로 계산한 값이고, 오염 농도는 합성 예시입니다(CAMS 계정 필요). 따라서 AQI 값 자체는 예시이지만 정체 시간대는 실제 모델 결과입니다.",
            "In this run mixing height, wind and temperature come from Aurora 1.5 initialised with ARCO-ERA5; pollutant concentrations are synthetic (CAMS needs an account). The AQI values are therefore illustrative, while the stagnation hours are real model output.",
        )
        if X["met_real"]
        else t(
            "데모 모드 실행: 기상과 농도 모두 합성 예시입니다.",
            "Demo-mode run: both weather and concentrations are synthetic examples.",
        )
    )
    cat_ko = {c[1]: c[2] for c in CATS}
    add(
        "summary",
        t("지점별 요약", "Per-site summary"),
        tagline("5 · " + t("산출물", "Output"), "pm", "met", "method")
        + mode_note
        + "\n\n"
        + md_table(
            [
                t("지점", "Site"),
                t("현재", "Now"),
                t("최고", "Peak"),
                t("범주", "Category"),
                t("주 오염물질", "Dominant"),
                "GRAP",
                t("정체 h", "Stagnant h"),
            ],
            [
                [r[0], r[1], r[2], cat_ko.get(r[3], r[3]) if ko else r[3], r[4], r[5], r[6]]
                for r in D.get("summary", [])
            ],
            align="lrrllrr",
        )
        + "\n\n"
        + t(
            f"정점은 모든 지점에서 {ist(times, 35, lang)} 전후(최저 혼합층 {X['blh_range']} m). 지도의 지점 색은 정점 범주이고, ⓘ로 지점·셀을 클릭하면 값이 뜹니다. 산출 파일: `pollutants_12h.csv`, `meteorology_hourly.csv`, `fused_hourly.csv`, `summary_by_site.csv`, `messages_{{ko,en,hi}}.json`, `bulletin_*.md`, `frontend/*.json`.",
            f"All sites peak around {ist(times, 35, lang)} (minimum mixing height {X['blh_range']} m). Site colours on the map are the peak category; use ⓘ to click sites and cells for values. Output files: `pollutants_12h.csv`, `meteorology_hourly.csv`, `fused_hourly.csv`, `summary_by_site.csv`, `messages_{{ko,en,hi}}.json`, `bulletin_*.md`, `frontend/*.json`.",
        ),
        "delhi",
        aqi="h35",
    )

    add(
        "limits",
        t("해상도의 진실", "The truth about resolution"),
        tagline("6 · " + t("한계와 책임 있는 사용", "Limits and responsible use"), "pm")
        + t(
            "지도에 겹친 큰 사각형이 Air Pollution 모델의 0.4° 셀 하나입니다. 델리 NCT 전체가 두세 개 셀에 들어갑니다.\n\n"
            "- **공간 해상도**: 지점 간 차이는 보간 결과이며 도로변 농도가 아니다. 실제 서비스에는 관측소별 편향 보정이나 CPCB 데이터로의 파인튜닝이 필요하다.\n"
            "- **시간 해상도**: 시간별 농도 곡선은 12시간 예측의 선형 보간이다. 시간별 구조의 근거는 1.5의 기상 변수이며 메시지에도 그렇게 표기한다.\n"
            "- **입력 데이터**: 1.5는 IFS HRES T0로 파인튜닝되었고 이 예제는 ERA5를 쓴다. Air Pollution 모델은 CAMS 분석 전용이다.\n"
            "- **1000 hPa 가스**: NO2/SO2/O3/CO는 1000 hPa 혼합비를 밀도로 환산한 근사치. AQI는 사실상 PM2.5/PM10이 주도한다.\n"
            "- **운영 결정**: Aurora는 연구용 모델이며 전문가 검토 없는 운영 의사결정에 쓰여서는 안 된다.",
            "The large square on the map is one 0.4° cell of the Air Pollution model. All of Delhi NCT fits in two or three cells.\n\n"
            "- **Spatial resolution**: site differences are interpolation, not roadside values. A real service needs per-station bias correction or fine-tuning on CPCB data.\n"
            "- **Temporal resolution**: the hourly curve is a linear interpolation of 12-hour forecasts; the hourly structure comes from 1.5's meteorology and the messages say so.\n"
            "- **Input data**: 1.5 was fine-tuned on IFS HRES T0; this example uses ERA5. The Air Pollution model is for CAMS analysis only.\n"
            "- **Gases at 1000 hPa**: NO2/SO2/O3/CO are converted mixing ratios, an approximation; PM2.5/PM10 dominate the AQI.\n"
            "- **Operational decisions**: Aurora is a research model and must not drive operational decisions without expert review.",
        ),
        "delhi",
        aqi="h35",
        coarse=True,
    )

    if ens:
        n = X["members"]
        ens_text = (
            t(
                f"Aurora 1.5 Ensemble을 서로 다른 시드로 {n}번 실행해(멤버당 48시간, 시간별) 각 멤버의 혼합층과 바람으로 정체 여부를 판정하고, 정체인 멤버의 비율을 확률로 썼습니다. 모델이 실제로 계산한 불확실성입니다.",
                f"Aurora 1.5 Ensemble was run {n} times with different seeds (48 hourly steps each); each member's mixing height and wind decide stagnation, and the share of stagnant members is the probability. This is uncertainty the model computed.",
            )
            if X["ens_real"]
            else t(
                f"데모 모드에서는 Aurora 앙상블 대신 합성 기상장을 {n}번 교란(혼합층 ±25 %, 풍속 ±20 % 로그정규)해 같은 절차를 돌렸습니다. 절차 시연이며 모델이 계산한 불확실성이 아닙니다.",
                f"In demo mode the synthetic weather was perturbed {n} times (mixing height ±25 %, wind ±20 %, log-normal) instead of running the Aurora ensemble. A procedure demonstration, not model-computed uncertainty.",
            )
        )

        def win(p: list[float], a: int, b: int) -> str:
            s = p[a : b + 1]
            return f"{round(100 * sum(s) / len(s))}%" if s else "0%"

        # Hourly index i is IST 18:30 + i h on 5 Nov. Night 1: 22:00–08:00 -> 3..13; day: 14..27; night 2: 28..37.
        rows = [
            [
                name,
                win(e["p"], 3, 13),
                win(e["p"], 14, 27),
                win(e["p"], 28, 37),
                f"{e['blh_p10'][35]}–{e['blh_p90'][35]}",
            ]
            for name, e in ens["sites"].items()
        ]
        add(
            "ensemble",
            t("앙상블로 본 정체 확률", "Stagnation probability from the ensemble"),
            tagline(t("로드맵 실행 1 · 불확실성", "Roadmap run 1 · uncertainty"), "ens", "method")
            + ens_text
            + "\n\n"
            + t(
                f"지도의 파란 농담이 {ist(times, 35, lang)} 셀별 정체 확률(멤버 중 풍속 10 km/h 미만·혼합층 500 m 미만인 비율)입니다. 표는 지점별로 첫째 밤(11월 5일 22시~6일 08시), 낮(6일 08~22시), 둘째 밤(6일 22시~7일 08시)의 평균 확률과 정점 시각의 혼합층 10~90퍼센타일입니다.",
                f"The blue shading on the map is the per-cell stagnation probability at {ist(times, 35, lang)} (share of members with wind below 10 km/h and mixing height below 500 m). The table gives each site's mean probability for the first night (5 Nov 22:00 to 6 Nov 08:00), the day (6 Nov 08:00–22:00) and the second night, plus the 10th–90th percentile mixing height at the peak hour.",
            )
            + "\n\n"
            + md_table(
                [
                    t("지점", "Site"),
                    t("밤 1", "Night 1"),
                    t("낮", "Day"),
                    t("밤 2", "Night 2"),
                    t("정점 BLH p10–p90 (m)", "Peak BLH p10–p90 (m)"),
                ],
                rows,
                align="lrrrr",
            ),
            "delhi",
            prob=True,
        )

    if D.get("bias"):
        add(
            "bias",
            t("지점별 선형 편향 보정", "Per-site linear bias correction"),
            tagline(
                t("로드맵 실행 2 · 관측 보정", "Roadmap run 2 · observation correction"),
                "method",
                "synthobs",
            )
            + t(
                "관측 = a + b × 예측 형태의 직선을 지점별로 최소제곱으로 맞추고, 보정 전후의 RMSE(평균 제곱근 오차)를 비교합니다. 실제 CPCB 관측은 공개 API가 없어 포털에서 긁어와야 하므로, 여기서는 **합성 관측**(교통 지점은 모델이 15% 낮게, 주거 지점은 8% 높게 읽는다고 가정하고 잡음을 더한 값)으로 절차만 실행했습니다. 표본이 12시간 간격 5개뿐이라 계수는 예시 수준입니다.",
                "A straight line obs = a + b × pred is fitted per site by least squares and the RMSE before and after correction compared. Real CPCB observations have no public API and must be scraped, so the procedure runs on **synthetic observations** (the model assumed to read 15% low at traffic sites and 8% high at residential sites, plus noise). With only five 12-hourly samples the coefficients are illustrative.",
            )
            + "\n\n"
            + md_table(
                [
                    t("지점", "Site"),
                    "a",
                    "b",
                    "n",
                    t("RMSE 전", "RMSE before"),
                    t("RMSE 후", "RMSE after"),
                ],
                [list(r) for r in D["bias"]],
                align="lrrrrr",
            ),
            "delhi",
            aqi="h35",
        )

    ft = D.get("finetune") or {"status": "not_run", "detail": ""}
    ft_txt = {
        "passed": t("스모크 테스트 통과 — ", "Smoke test passed — ") + ft.get("detail", ""),
        "failed": t("스모크 테스트 실패:\n", "Smoke test failed:\n") + ft.get("detail", ""),
        "running": t("실행 중", "running"), "not_run": t("실행하지 않음", "not run"),
    }.get(ft.get("status", "not_run"), "")  # fmt: skip
    if ft.get("loss"):
        ft_txt += "\n" + "  ".join(f"{a} {b}" for a, b in ft["loss"])
    add(
        "finetune",
        t(
            "msresearch-aurora 스타터로 학습 루프 점검",
            "Checking the training loop with the msresearch-aurora starter",
        ),
        tagline(t("로드맵 실행 3 · 파인튜닝", "Roadmap run 3 · fine-tuning"), "method")
        + t(
            "인도 지역 학습 자료(격자화한 CPCB 관측이나 지역 CAMS 재분석)는 아직 없으므로 본 파인튜닝은 실행하지 않았습니다. 대신 스타터 코드의 스모크 테스트(`test_finetuning_2t_var_pretrained`: 번들된 미국 서부 ERA5 7일 자료로 사전학습 Aurora의 2 m 기온을 1 에포크 학습)를 돌려 학습 루프·체크포인트·옵티마이저가 이 환경에서 동작하는지 확인했습니다.",
            "There is no regional training set yet (gridded CPCB observations or regional CAMS reanalysis), so the real fine-tuning was not run. Instead the starter's smoke test (`test_finetuning_2t_var_pretrained`: one epoch of 2 m temperature on the bundled seven-day western-USA ERA5 slice from the pretrained Aurora) was run to confirm the training loop, checkpointing and optimiser work in this environment.",
        )
        + "\n\n**"
        + t("결과", "Result")
        + "**\n\n```text\n"
        + ft_txt
        + "\n```",
        "tile",
        mode="markdown",
        aqi="h35",
    )

    dv = D.get("delivery")
    if dv:
        sample = "\n".join(
            f"{i['subscriber']} · PIN {i['pincode']} · {i['site']} · {i['lang']} · {i['status']} · {i['chars']} chars\n  {i['payload']}"
            for i in dv["sample"]
        )
        add(
            "delivery",
            t("우편번호 → 지점 → 메시지", "Postal code → site → message"),
            tagline(t("로드맵 실행 4 · 발송 어댑터", "Roadmap run 4 · delivery adapter"), "method")
            + t(
                '구독자의 우편번호(PIN)를 가장 가까운 지점에 매핑하고 언어별 `short` 메시지를 payload로 만들어 발송 로그를 남깁니다. 이번 실행은 dry run이라 실제 전송 대신 "queued" 상태로 기록되며, 실제 어댑터는 이 자리에서 WhatsApp Business API나 SMS 게이트웨이에 POST합니다.',
                'Each subscriber\'s postal code is mapped to the nearest site, the per-language `short` message becomes the payload and a delivery log is written. This run is a dry run, so items are logged as "queued"; a real adapter would POST to the WhatsApp Business API or an SMS gateway here.',
            )
            + "\n\n"
            + md_table(
                [t("항목", "Item"), t("값", "Value")],
                [
                    [t("건수", "Items"), dv["count"]],
                    [t("채널", "Channel"), dv["channel"]],
                    [t("언어", "Languages"), ", ".join(dv["langs"])],
                ],
            )
            + "\n\n**"
            + t("로그 예시", "Log sample")
            + "**\n\n```text\n"
            + sample
            + "\n```",
            "delhi",
            aqi="h00",
        )

    add(
        "cron",
        t("00/12 UTC마다 다시 발행", "Re-issue at 00 and 12 UTC"),
        tagline(t("로드맵 실행 5 · 자동화", "Roadmap run 5 · automation"), "method")
        + t(
            "파이프라인이 자동으로 생성한 크론 스크립트입니다. 분석장이 도착한 뒤인 02:30/14:30 UTC(08:00/20:00 IST)에 실행되어 날짜별 폴더에 산출물을 남깁니다. 이 스토리 맵의 데이터 자체가 그 스크립트와 같은 명령(`delhi_aq.py`)의 실행 결과입니다.",
            "The cron script generated by the pipeline. It runs at 02:30 and 14:30 UTC (08:00 and 20:00 IST), after the analyses arrive, and writes outputs to a dated folder. The data in this story map are themselves the result of the same command (`delhi_aq.py`).",
        )
        + "\n\n```bash\n"
        + (D.get("cron") or "").strip()
        + "\n```",
        "tile",
        mode="markdown",
        aqi="h00",
    )

    repo = "https://github.com/playground-for-thinker/aurora"
    nblink = (
        "https://notebook.link/github/playground-for-thinker/aurora/tree/storymap/specta/?path="
    )
    add(
        "done",
        t("실행한 것과 남은 것", "Done and still to do"),
        tagline("7 · " + t("남은 과제 · 직접 실행", "What remains · run it"))
        + t(
            "로드맵 다섯 항목은 위 장면에서 실행했습니다. 남은 것은 실제 CPCB 관측 연결, 인도 지역 자료로의 본 파인튜닝, 그리고 CAMS 계정을 붙여 오염 농도까지 Aurora로 계산하는 일입니다.\n\n"
            '1. **불확실성**: `AuroraV1p5Ensemble` + `rollout_ensemble`로 "정체 확률 80%" 식의 표현.\n'
            "2. **CPCB 관측 보정**: 지점별 관측-예측 잔차 학습(선형/분위 매핑부터).\n"
            "3. **파인튜닝**: `msresearch-aurora/starter-code/`의 학습 루프로 Air Pollution 모델을 인도 지역 자료에 적응. 모델 측 요구사항은 `docs/finetuning.md`.\n"
            "4. **채널 연계**: `messages_hi.json`을 WhatsApp Business API, SMS, 델리 정부 앱으로. 거주 지역(핀코드)을 가장 가까운 지점에 매핑.\n"
            "5. **자동화**: 00/12 UTC마다 `delhi_aq.py --mode foundry --plot`을 크론으로.\n\n"
            "### 직접 실행하기\n\n"
            "demo 모드는 GPU와 데이터 없이 돌아갑니다.\n\n",
            "The five roadmap items were run in the scenes above. What remains: connecting real CPCB observations, the actual fine-tuning on regional data, and attaching a CAMS account so pollutant concentrations also come from Aurora.\n\n"
            '1. **Uncertainty**: `AuroraV1p5Ensemble` with `rollout_ensemble` for "80% chance of stagnation".\n'
            "2. **CPCB correction**: learn per-site residuals (linear or quantile mapping first).\n"
            "3. **Fine-tuning**: adapt the Air Pollution model to regional data with the loop in `msresearch-aurora/starter-code/`; model-side requirements in `docs/finetuning.md`.\n"
            "4. **Channels**: push `messages_hi.json` to the WhatsApp Business API, SMS or the Delhi government app; map users to the nearest site by pin code.\n"
            "5. **Automation**: cron `delhi_aq.py --mode foundry --plot` at 00 and 12 UTC.\n\n"
            "### Run it yourself\n\n"
            "Demo mode needs no GPU or data.\n\n",
        )
        + "```bash\ngit clone "
        + repo
        + ".git && cd aurora\npip install -e . && pip install matplotlib\n"
        "python examples/delhi_air_quality/delhi_aq.py --mode demo --date 2025-11-05 --plot --out outputs\n```\n\n"
        + t(
            f"- 노트북: [Colab](https://colab.research.google.com/github/playground-for-thinker/aurora/blob/main/examples/delhi_air_quality/example_delhi_air_quality.ipynb) · [Binder](https://mybinder.org/v2/gh/playground-for-thinker/aurora/main?labpath=examples%2Fdelhi_air_quality%2Fexample_delhi_air_quality.ipynb)\n"
            f"- 스토리보드(장면별 설명 + 그래프, notebook.link 노트북): [한국어]({nblink}storyboard_ko.ipynb) · [English]({nblink}storyboard_en.ipynb)\n"
            f"- 코드: [GitHub]({repo}/tree/main/examples/delhi_air_quality)\n\n"
            "이 스토리 맵은 JupyterGIS 문서(`.jGIS`)입니다. notebook.link의 JupyterLab 보기에서 레이어와 장면을 직접 편집할 수 있고, `build_storymap_jgis.py`로 파이프라인 산출물에서 다시 생성할 수 있습니다.",
            f"- Notebook: [Colab](https://colab.research.google.com/github/playground-for-thinker/aurora/blob/main/examples/delhi_air_quality/example_delhi_air_quality.ipynb) · [Binder](https://mybinder.org/v2/gh/playground-for-thinker/aurora/main?labpath=examples%2Fdelhi_air_quality%2Fexample_delhi_air_quality.ipynb)\n"
            f"- Storyboard (scene-by-scene document with charts, notebook.link): [English]({nblink}storyboard_en.ipynb) · [Korean]({nblink}storyboard_ko.ipynb)\n"
            f"- Code: [GitHub]({repo}/tree/main/examples/delhi_air_quality)\n\n"
            "This story map is a JupyterGIS document (`.jGIS`). Open it in notebook.link's JupyterLab view to edit layers and scenes, or rebuild it from pipeline outputs with `build_storymap_jgis.py`.",
        ),
        "tile",
        mode="markdown",
        aqi="h35",
    )
    return S


# --------------------------------------------------------------------------------------- document
def build_document(D: dict, lang: str, geo: dict[str, dict], story_type: str) -> dict:
    ko = lang == "ko"
    times = D["times"]

    def t(a: str, b: str) -> str:
        return a if ko else b

    sources: dict[str, dict] = {}
    layers: dict[str, dict] = {}
    tree: list[str] = []
    names: dict[str, str] = {}  # logical key -> layer name (layerOverride targets layers by name)

    def add_source(key: str, stype: str, name: str, params: dict) -> str:
        sid = uid(lang, "source", key)
        sources[sid] = {"type": stype, "name": name, "parameters": params}
        return sid

    def add_layer(key: str, ltype: str, name: str, params: dict, visible: bool) -> str:
        lid = uid(lang, "layer", key)
        layers[lid] = {"type": ltype, "name": name, "visible": visible, "parameters": params}
        tree.append(lid)
        names[key] = name
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

    toggles = [k for k in names if k != "basemap"]
    segments: list[str] = []
    for i, ch in enumerate(chapters(D, lang)):
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
        if ch["view"] in ("world", "india"):
            on -= {"sites", "delhi"}
        params = {
            "zoom": zoom(ch["view"]), "extent": extent(ch["view"]),
            "enableIdentify": ch["mode"] == "map",
            "content": {"contentMode": ch["mode"], "markdown": ch["md"], "image": "", "imageCaption": ""},
            "transition": {"type": "smooth", "time": 2.0},
            "layerOverride": [{"targetLayer": names[k], "visible": k in on} for k in toggles],
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
            "latitude": 28.64,
            "longitude": 77.12,
            "zoom": zoom("delhi"),
            "bearing": 0.0,
            "pitch": 0.0,
            "projection": "EPSG:3857",
            "extent": extent("delhi"),
            "useExtent": False,
        },  # fmt: skip
        "stories": {
            story_id: {
                "title": t("델리 스모그 스토리 맵", "Delhi Smog Story Map"),
                "storyType": story_type,
                "storySegments": segments,
                "showGradient": True,
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
        default="guided",
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
