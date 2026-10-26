"""Copyright (c) Microsoft Corporation. Licensed under the MIT license.

Build the storyboard as a Specta slide deck for notebook.link (no code cells, no kernel needed).

    python build_storyboard_slides.py          # writes storymap/storyboard_{ko,en}.ipynb + storymap/img/

Every slide is one markdown cell: the left half is a figure rendered here with matplotlib (and
embedded as a data URI, so it renders in any Jupyter front end), the right half is the narration
for a general audience. Boxes distinguish what *this system* already produces (teal) from what a
*government or city* has to own when the service goes live (amber); messages are shown as phone
bubbles. The Korean and English decks are separate notebooks that link to each other from the
top-right pill on every slide. All numbers come from `storymap_data.js`, the same run as the
story map.
"""

from __future__ import annotations

import argparse
import base64
import io
import json
import math
from datetime import datetime, timedelta
from pathlib import Path

import matplotlib
import matplotlib.pyplot as plt
import numpy as np
from matplotlib import font_manager
from matplotlib.colors import BoundaryNorm, ListedColormap
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch, Rectangle
from storyboard_scenes import scenes

matplotlib.use("Agg")

HERE = Path(__file__).resolve().parent
NBLINK = "https://notebook.link/github/playground-for-thinker/aurora/tree/storymap"
TEAL, AMBER, INK, MUTED, PAPER = "#0b6e8f", "#b7791f", "#1e293b", "#64748b", "#f8fafc"
CATS = [  # upper bound, en, ko, colour (CPCB categories, colours shared with the story map)
    (50, "Good", "좋음", "#2e8b57"),
    (100, "Satisfactory", "양호", "#7fb241"),
    (200, "Moderate", "보통", "#d4a72c"),
    (300, "Poor", "나쁨", "#e0782a"),
    (400, "Very Poor", "매우 나쁨", "#c84a3b"),
    (10**9, "Severe", "위험", "#7f1d2d"),
]
SITES = [  # name, lat, lon, label offset (points), label anchor
    ("Anand Vihar", 28.647, 77.316, (6, 7), "left"), ("ITO", 28.629, 77.241, (-6, -11), "right"),
    ("Punjabi Bagh", 28.674, 77.131, (-6, -11), "right"), ("Rohini", 28.733, 77.120, (-6, -11), "right"),
    ("Jahangirpuri", 28.733, 77.171, (6, -11), "left"), ("R K Puram", 28.563, 77.187, (6, 7), "left"),
    ("Dwarka Sector 8", 28.571, 77.072, (-6, -11), "right"), ("Okhla Phase 2", 28.531, 77.271, (6, -13), "left"),
    ("Noida Sector 62", 28.625, 77.358, (6, -15), "left"), ("Gurugram Vikas Sadan", 28.450, 77.026, (6, -11), "left"),
]  # fmt: skip
VIEWS = {"tile": (75.6, 26.9, 80.4, 32.1), "delhi": (76.75, 28.25, 77.6, 28.95)}
FONT_DIR = Path("/usr/share/fonts/truetype/nanum")


# ------------------------------------------------------------------------------------ helpers
def load_data(path: Path) -> dict:
    js = path.read_text(encoding="utf-8")
    return json.loads(js[js.index("=") + 1 :].rstrip().rstrip(";"))


def cat(aqi: float) -> tuple:
    for c in CATS:
        if aqi <= c[0]:
            return c
    return CATS[-1]


def ist(times: list[str], i: int, lang: str) -> str:
    t = datetime.fromisoformat(times[i]) + timedelta(hours=5, minutes=30)
    return f"{t.month}월 {t.day}일 {t:%H:%M}" if lang == "ko" else f"{t.day} {t:%b} {t:%H:%M}"


def setup_fonts(lang: str) -> None:
    if lang == "ko" and (FONT_DIR / "NanumBarunGothic.ttf").exists():
        for f in ("NanumBarunGothic.ttf", "NanumBarunGothicBold.ttf"):
            font_manager.fontManager.addfont(str(FONT_DIR / f))
        plt.rcParams["font.family"] = "NanumBarunGothic"
    else:
        plt.rcParams["font.family"] = "DejaVu Sans"
    plt.rcParams["axes.unicode_minus"] = False
    plt.rcParams["figure.facecolor"] = "white"


def png_data_uri(fig, path: Path) -> str:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=160, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    path.write_bytes(buf.getvalue())
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode("ascii")


def text(lang: str, ko: str, en: str) -> str:
    return ko if lang == "ko" else en


# ------------------------------------------------------------------------------------ figures
def draw_map(
    ax,
    D: dict,
    step: int,
    view: str,
    lang: str,
    wind: bool = False,
    prob: bool = False,
    coarse: bool = False,
    grid: bool = False,
    labels: bool = True,
    title: str = "",
) -> None:
    lats, lons = np.array(D["lats"]), np.array(D["lons"])
    n = len(lons)
    lat_e = np.append(lats + 0.125, lats[-1] - 0.125)
    lon_e = np.append(lons - 0.125, lons[-1] + 0.125)
    ax.set_facecolor("#eef2f5")
    for r in D["states"]:
        xy = np.array(r)
        ax.plot(xy[:, 0], xy[:, 1], color="#b8c0c8", lw=0.6, zorder=1)
    if prob and D.get("ensemble"):
        p = np.array(D["ensemble"]["p_cell"][min(step, len(D["ensemble"]["p_cell"]) - 1)]).reshape(
            len(lats), n
        )
        ax.pcolormesh(lon_e, lat_e, p, cmap="Blues", vmin=0, vmax=1, alpha=0.9, zorder=2)
    else:
        a = np.array(D["aqi"][step]).reshape(len(lats), n)
        cmap = ListedColormap([c[3] for c in CATS])
        norm = BoundaryNorm([0, 50.5, 100.5, 200.5, 300.5, 400.5, 10**6], 6)
        ax.pcolormesh(lon_e, lat_e, a, cmap=cmap, norm=norm, alpha=0.78, zorder=2,
                      edgecolors="#ffffff" if grid else "none", linewidth=0.4 if grid else 0)  # fmt: skip
    if wind:
        w = np.array(D["wind"][step]).reshape(len(lats), n)
        d = np.radians(np.array(D["wdir"][step]).reshape(len(lats), n))
        ax.quiver(
            lons,
            lats,
            np.cos(d) * w,
            np.sin(d) * w,
            color="#1e293b",
            alpha=0.85,
            scale=160,
            width=0.004,
            zorder=5,
        )
    if coarse:
        ax.add_patch(
            Rectangle(
                (76.8, 28.4),
                0.4,
                0.4,
                fill=True,
                facecolor="#fde68a",
                alpha=0.35,
                edgecolor=INK,
                lw=2,
                ls="--",
                zorder=4,
            )
        )
        ax.text(
            77.0,
            28.405,
            text(lang, "0.4° 셀 1개", "one 0.4° cell"),
            ha="center",
            va="bottom",
            fontsize=11,
            color=INK,
            zorder=6,
            fontweight="bold",
        )
    delhi = np.array(D["delhi"] + [D["delhi"][0]])
    ax.plot(delhi[:, 0], delhi[:, 1], color=INK, lw=1.8, zorder=5)
    x0, y0, x1, y1 = VIEWS[view]
    if view == "tile":
        ax.add_patch(Rectangle((76, 27.5), 4, 4, fill=False, edgecolor=TEAL, lw=2, zorder=5))
        ax.text(
            77.33,
            28.95,
            text(lang, "델리", "Delhi"),
            fontsize=11,
            color=INK,
            fontweight="bold",
            zorder=6,
        )
    else:
        for name, la, lo, off, ha in SITES:
            aqi_site = D["sites"].get(name, {}).get("aqi", [None])[step]
            fc = cat(aqi_site)[3] if aqi_site is not None else INK
            ax.scatter([lo], [la], s=90, c=[fc], edgecolors="white", linewidths=1.5, zorder=7)
            if labels:
                ax.annotate(name, (lo, la), xytext=off, textcoords="offset points", ha=ha, fontsize=9, color=INK, zorder=8,
                            bbox=dict(boxstyle="round,pad=0.15", fc="white", ec="none", alpha=0.75))  # fmt: skip
    ax.set_xlim(x0, x1)
    ax.set_ylim(y0, y1)
    ax.set_aspect(1 / math.cos(math.radians(28.6)))
    ax.set_xticks([])
    ax.set_yticks([])
    for s in ax.spines.values():
        s.set_edgecolor("#cbd5e1")
    if title:
        ax.set_title(title, fontsize=13, color=INK, loc="left", fontweight="bold")


def legend_cats(ax, lang: str, loc: str = "lower left") -> None:
    handles = [Rectangle((0, 0), 1, 1, fc=c[3], alpha=0.85) for c in CATS]
    labels = [
        f"{c[2] if lang == 'ko' else c[1]} ({'0' if i == 0 else CATS[i - 1][0] + 1}–{c[0] if c[0] < 10**6 else '500+'})"
        for i, c in enumerate(CATS)
    ]
    ax.legend(
        handles,
        labels,
        loc=loc,
        fontsize=8,
        frameon=True,
        framealpha=0.9,
        title=text(lang, "AQI (CPCB)", "AQI (CPCB)"),
        title_fontsize=9,
    )


def fig_map(D: dict, step: int, view: str, lang: str, title: str, **kw):
    fig, ax = plt.subplots(figsize=(7, 5.6))
    draw_map(ax, D, step, view, lang, title=title, **kw)
    if not kw.get("prob"):
        legend_cats(ax, lang)
    else:
        sm = plt.cm.ScalarMappable(cmap="Blues", norm=plt.Normalize(0, 1))
        cb = fig.colorbar(sm, ax=ax, fraction=0.04, pad=0.02)
        cb.set_label(
            text(lang, "정체 확률 (멤버 비율)", "stagnation probability (share of members)"),
            fontsize=9,
        )
        cb.ax.tick_params(labelsize=8)
    fig.text(0.01, 0.01, D.get("attribution", ""), fontsize=7, color=MUTED)
    return fig


def fig_mixing_layer(lang: str):
    fig, axes = plt.subplots(1, 2, figsize=(7, 4.6))
    rng = np.random.default_rng(3)
    for ax, (blh, label, n_dots) in zip(axes, [
        (1000, text(lang, "낮 · 혼합층 약 1,000 m · 바람 10 km/h 이상", "Day · mixing layer ≈ 1,000 m · wind > 10 km/h"), 120),
        (150, text(lang, "밤 · 혼합층 100–300 m · 바람 약함", "Night · mixing layer 100–300 m · light wind"), 120),
    ]):  # fmt: skip
        ax.set_xlim(0, 10)
        ax.set_ylim(0, 1300)
        ax.set_facecolor("#dbeafe" if blh > 500 else "#1e293b")
        ax.axhspan(
            0, blh, color="#9ca3af" if blh > 500 else "#6b7280", alpha=0.25 if blh > 500 else 0.6
        )
        ax.axhline(blh, color=TEAL if blh > 500 else "#fbbf24", lw=2, ls="--")
        ax.text(
            0.3,
            blh + 30,
            text(lang, "혼합층 높이", "mixing-layer height"),
            fontsize=9,
            color=TEAL if blh > 500 else "#fbbf24",
        )
        ys = rng.uniform(20, blh * 0.95, n_dots)
        xs = rng.uniform(0.5, 9.5, n_dots)
        ax.scatter(
            xs, ys, s=18, c="#7f1d2d" if blh < 500 else "#c84a3b", alpha=0.75 if blh < 500 else 0.45
        )
        for x, h in [(1, 180), (2.2, 320), (3.6, 240), (5.4, 420), (6.9, 260), (8.3, 360)]:
            ax.add_patch(Rectangle((x, 0), 0.8, h / 4, color="#334155" if blh > 500 else "#0f172a"))
        ax.set_yticks([0, 300, 600, 900, 1200])
        ax.set_ylabel("m", fontsize=9)
        ax.set_xticks([])
        ax.tick_params(labelsize=8)
        ax.set_title(label, fontsize=10, color=INK, fontweight="bold")
    fig.suptitle(
        text(
            lang,
            "같은 배출량이라도 섞일 공기가 얇으면 지표 농도가 오른다",
            "Same emissions, thinner layer of air to mix into: higher concentrations at the surface",
        ),
        fontsize=11,
        color=INK,
    )
    fig.tight_layout()
    return fig


def box(ax, x, y, w, h, title, body, fc, ec, fs=9.5, title_fs=11):
    ax.add_patch(
        FancyBboxPatch(
            (x, y), w, h, boxstyle="round,pad=0.02,rounding_size=0.03", fc=fc, ec=ec, lw=1.6
        )
    )
    ax.text(
        x + w / 2,
        y + h - 0.06,
        title,
        ha="center",
        va="top",
        fontsize=title_fs,
        fontweight="bold",
        color=INK,
    )
    ax.text(
        x + w / 2,
        y + h / 2 - 0.05,
        body,
        ha="center",
        va="center",
        fontsize=fs,
        color=INK,
        linespacing=1.35,
    )


def arrow(ax, p, q, color=INK):
    ax.add_patch(
        FancyArrowPatch(
            p, q, arrowstyle="-|>", mutation_scale=16, color=color, lw=1.6, shrinkA=2, shrinkB=2
        )
    )


def fig_system_flow(lang: str):
    fig, ax = plt.subplots(figsize=(7, 5.2))
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 10)
    ax.axis("off")
    ax.add_patch(
        FancyBboxPatch(
            (0.2, 0.1),
            9.6,
            7.75,
            boxstyle="round,pad=0.02,rounding_size=0.1",
            fc="#e6f3f7",
            ec=TEAL,
            lw=1.2,
            ls="--",
        )
    )
    ax.text(
        0.45,
        0.32,
        text(
            lang,
            "현 시스템 (이 예제가 지금 계산하는 것)",
            "This system (what the example computes today)",
        ),
        fontsize=10,
        color=TEAL,
        ha="left",
        fontweight="bold",
    )
    box(ax, 0.5, 8.0, 9.0, 1.6, text(lang, "입력: 전지구 대기 분석 자료", "Input: global atmospheric analyses"),
        text(lang, "오염 농도 분석 (CAMS, 0.4°)  ·  기상 분석 (ERA5 / IFS, 0.25°)\n하루 두 번 (00 / 12 UTC) 공개되는 공공 데이터", "Pollutant analysis (CAMS, 0.4°)  ·  weather analysis (ERA5 / IFS, 0.25°)\npublic data released twice a day (00 / 12 UTC)"), "#f1f5f9", "#94a3b8")  # fmt: skip
    box(
        ax,
        0.5,
        5.2,
        4.3,
        2.0,
        "Aurora Air Pollution",
        text(
            lang,
            "오염 농도 예측\nPM2.5 · PM10 · NO2 · O3\n12시간 간격, +48시간",
            "Pollutant forecast\nPM2.5 · PM10 · NO2 · O3\nevery 12 h, +48 h",
        ),
        "#ffffff",
        TEAL,
    )
    box(
        ax,
        5.2,
        5.2,
        4.3,
        2.0,
        "Aurora 1.5",
        text(
            lang,
            "시간별 기상 예측\n혼합층 높이 · 바람 · 기온\n1시간 간격, +48시간",
            "Hourly weather forecast\nmixing height · wind · temperature\nevery hour, +48 h",
        ),
        "#ffffff",
        TEAL,
    )
    box(ax, 0.5, 2.75, 9.0, 1.9, text(lang, "델리 후처리", "Delhi post-processing"),
        text(lang, "10개 지점으로 보간 → CPCB AQI → GRAP 해당 수준\n→ 정체 시간 판정 (바람 < 10 km/h, 혼합층 < 500 m)", "Interpolate to 10 sites → CPCB AQI → corresponding GRAP level\n→ stagnant hours (wind < 10 km/h, mixing height < 500 m)"), "#ffffff", TEAL)  # fmt: skip
    box(ax, 0.5, 0.75, 9.0, 1.6, text(lang, "메시지 초안 (힌디어 · 영어 · 한국어)", "Draft messages (Hindi · English · Korean)"),
        text(lang, "시민용 한 줄  ·  민감군용 상세\n운영자 브리핑  ·  지도·그래프", "one line for citizens  ·  detail for sensitive groups\noperator briefing  ·  maps and charts"), "#ffffff", TEAL)  # fmt: skip
    arrow(ax, (2.65, 8.0), (2.65, 7.2))
    arrow(ax, (5.9, 8.0), (5.9, 7.2))
    arrow(ax, (2.65, 5.2), (2.65, 4.65))
    arrow(ax, (7.35, 5.2), (7.35, 4.65))
    arrow(ax, (5.0, 2.75), (5.0, 2.35))
    return fig


def fig_timeline(D: dict, lang: str):
    times = D["times"]
    av = D["sites"]["Anand Vihar"]
    t = [datetime.fromisoformat(x) + timedelta(hours=5, minutes=30) for x in times]
    fig, axes = plt.subplots(2, 1, figsize=(7, 5.4), sharex=True)
    for ax, key, label, color, thr in [
        (axes[0], "aqi", "AQI", "#c84a3b", 400),
        (axes[1], "blh", text(lang, "혼합층 높이 (m)", "Mixing-layer height (m)"), TEAL, 500),
    ]:
        ax.plot(t, av[key], color=color, lw=2.2)
        ax.axhline(thr, color="#94a3b8", lw=0.9, ls="--")
        for i, s in enumerate(av["stag"]):
            if s:
                ax.axvspan(
                    t[i] - timedelta(minutes=30),
                    t[i] + timedelta(minutes=30),
                    color=TEAL,
                    alpha=0.08,
                    lw=0,
                )
        ax.set_ylabel(label, fontsize=10)
        ax.grid(alpha=0.25)
        ax.tick_params(labelsize=9)
    scenes = [
        (0, text(lang, "저녁 경보", "evening alert")),
        (8, text(lang, "정체 시작", "stagnation")),
        (35, text(lang, "정점", "peak")),
        (44, text(lang, "오후 숨 고르기", "afternoon breather")),
    ]
    for i, lbl in scenes:
        axes[0].axvline(t[i], color=INK, lw=0.9, alpha=0.6)
        last = i == scenes[-1][0]
        axes[0].annotate(
            f"{lbl}\n{t[i]:%H:%M}",
            (t[i], max(av["aqi"]) * 1.0),
            xytext=(-4 if last else 4, -2),
            textcoords="offset points",
            fontsize=8.5,
            color=INK,
            va="top",
            ha="right" if last else "left",
        )
    axes[0].set_title(
        text(
            lang,
            "Anand Vihar · 48시간 예측 · 파란 띠 = 정체 시간",
            "Anand Vihar · 48-hour forecast · blue bands = stagnant hours",
        ),
        fontsize=12,
        color=INK,
        loc="left",
        fontweight="bold",
    )
    axes[1].set_xlabel("IST", fontsize=9)
    fig.autofmt_xdate()
    fig.tight_layout()
    return fig


def fig_site_peaks(D: dict, lang: str):
    rows = sorted(D["summary"], key=lambda r: r[2])
    fig, ax = plt.subplots(figsize=(7, 5.2))
    names = [r[0] for r in rows]
    peaks = [r[2] for r in rows]
    ax.barh(names, peaks, color=[cat(p)[3] for p in peaks], alpha=0.9)
    for i, r in enumerate(rows):
        ax.text(r[2] + 4, i, f"{r[2]}  · GRAP {r[5]}", va="center", fontsize=9, color=INK)
    for x, c in [(300, "#e0782a"), (400, "#c84a3b")]:
        ax.axvline(x, color=c, lw=1, ls="--")
    ax.set_xlim(0, 600)
    ax.set_xlabel(text(lang, "최고 AQI (48시간 내)", "Peak AQI within 48 h"), fontsize=10)
    ax.tick_params(labelsize=9)
    ax.set_title(
        text(
            lang,
            f"지점별 최고 AQI · 정점 {ist(D['times'], 35, lang)} IST 전후",
            f"Peak AQI by site · around {ist(D['times'], 35, lang)} IST",
        ),
        fontsize=12,
        color=INK,
        loc="left",
        fontweight="bold",
    )
    ax.grid(axis="x", alpha=0.25)
    fig.tight_layout()
    return fig


def fig_message_anatomy(D: dict, lang: str):
    M = D.get("messages") or {}
    long = (M.get(lang) or {}).get("long", "")
    lines = [ln for ln in long.split("\n") if ln.strip()][:6]
    fig, ax = plt.subplots(figsize=(7, 5.6))
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 10)
    ax.axis("off")
    ax.add_patch(
        FancyBboxPatch(
            (0.4, 0.4),
            5.4,
            9.2,
            boxstyle="round,pad=0.02,rounding_size=0.35",
            fc="#0f172a",
            ec="#0f172a",
        )
    )
    ax.add_patch(
        FancyBboxPatch(
            (0.7, 0.9),
            4.8,
            8.2,
            boxstyle="round,pad=0.02,rounding_size=0.2",
            fc="#ffffff",
            ec="#ffffff",
        )
    )
    y = 8.7
    import textwrap

    for ln in lines:
        for w in textwrap.wrap(ln, 27 if lang == "ko" else 36)[:3]:
            ax.text(0.95, y, w, fontsize=7.6, color=INK, va="top")
            y -= 0.36
        y -= 0.2
    callouts = [
        (text(lang, "무엇: 수치 + CPCB 범주", "What: value + CPCB category"), 8.6),
        (text(lang, "언제: IST 정점 시각", "When: peak time in IST"), 7.3),
        (text(lang, "어디: 지점 이름", "Where: site name"), 6.0),
        (text(lang, "왜: 기상 근거 한 문장", "Why: one sentence of weather"), 4.7),
        (text(lang, "어떻게: 행동 1–2개", "How: one or two actions"), 3.4),
        (
            text(
                lang,
                'GRAP: "해당 수준"만 (발령은 CAQM)',
                'GRAP: "corresponding level" only; CAQM decides',
            ),
            2.1,
        ),
        (
            text(
                lang,
                "면책: AI 참고용 · 공식 경보는 CPCB/CAQM",
                "Disclaimer: AI guidance · official alerts: CPCB/CAQM",
            ),
            0.9,
        ),
    ]
    for txt, yy in callouts:
        ax.add_patch(
            FancyBboxPatch(
                (6.0, yy - 0.3),
                3.95,
                0.75,
                boxstyle="round,pad=0.02,rounding_size=0.1",
                fc="#e6f3f7",
                ec=TEAL,
                lw=1.2,
            )
        )
        ax.text(6.15, yy + 0.07, txt, fontsize=7.8, color=INK, va="center")
        arrow(ax, (6.0, yy + 0.07), (5.6, yy + 0.07), color=TEAL)
    ax.set_title(
        text(
            lang,
            "160자 안에 무엇·언제·어디·왜·어떻게",
            "What, when, where, why and how in 160 characters",
        ),
        fontsize=12,
        color=INK,
        loc="left",
        fontweight="bold",
    )
    return fig


def fig_roles(lang: str):
    fig, ax = plt.subplots(figsize=(7, 4.9))
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 10)
    ax.axis("off")
    sys_items = text(lang,
        "• 48시간 오염 농도·기상 예측 (Aurora)\n• 10개 지점 AQI, GRAP 해당 수준\n• 정체 시간대와 확률 (앙상블)\n• 메시지 초안 hi / en / ko\n• 운영자 브리핑, 지도, 그래프\n• 00 / 12 UTC마다 자동 재발행\n• 발송 로그 (dry run, 큐 상태)",
        "• 48-hour pollutant and weather forecast (Aurora)\n• AQI and corresponding GRAP level at 10 sites\n• Stagnant hours and their probability (ensemble)\n• Draft messages hi / en / ko\n• Operator briefing, maps, charts\n• Automatic re-issue at 00 / 12 UTC\n• Delivery log (dry run, queued)")  # fmt: skip
    gov_items = text(lang,
        "• 공식 관측망(CPCB/DPCC) 연결과 검증\n• 지점별 편향 보정, 지역 자료로 파인튜닝\n• GRAP 발령·집행 (CAQM 권한)\n• 구독자 등록, 우편번호 → 지점 매핑\n• 공식 채널 발송 (SMS · WhatsApp · 앱)\n• 보건 문구 검수, 취약계층 지원\n• 시민 홍보·교육, 민원 대응",
        "• Connect and verify the official monitors (CPCB/DPCC)\n• Per-site bias correction, fine-tuning on regional data\n• Invoke and enforce GRAP (CAQM's authority)\n• Subscriber registry, postal code → site mapping\n• Official channels (SMS · WhatsApp · app)\n• Health wording review, support for vulnerable groups\n• Public communication and education")  # fmt: skip
    for x, title, body, fc, ec in [
        (
            0.3,
            text(lang, "현 시스템이 보여주는 것", "What this system shows"),
            sys_items,
            "#e6f3f7",
            TEAL,
        ),
        (
            5.2,
            text(lang, "정부·시가 맡아야 할 것", "What government and city must own"),
            gov_items,
            "#fff4e0",
            AMBER,
        ),
    ]:
        ax.add_patch(
            FancyBboxPatch(
                (x, 0.4), 4.5, 9.0, boxstyle="round,pad=0.02,rounding_size=0.15", fc=fc, ec=ec, lw=2
            )
        )
        ax.text(
            x + 2.25,
            9.0,
            title,
            ha="center",
            va="center",
            fontsize=11.5,
            fontweight="bold",
            color=ec,
        )
        ax.text(x + 0.25, 8.3, body, ha="left", va="top", fontsize=9.3, color=INK, linespacing=1.6)
    arrow(ax, (4.8, 5.0), (5.2, 5.0), color=INK)
    ax.text(5.0, 5.35, text(lang, "인계", "hand-off"), ha="center", fontsize=8, color=INK)
    return fig


def fig_roadmap(D: dict, lang: str):
    fig, ax = plt.subplots(figsize=(7, 5.4))
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 10)
    ax.axis("off")
    ft = (D.get("finetune") or {}).get("status", "not_run")
    done = [
        (
            text(
                lang,
                "불확실성: 앙상블로 정체 확률",
                "Uncertainty: stagnation probability from an ensemble",
            ),
            text(lang, "Aurora 1.5 Ensemble 3 멤버", "Aurora 1.5 Ensemble, 3 members"),
        ),
        (
            text(lang, "관측 보정 절차", "Observation-correction procedure"),
            text(
                lang,
                "지점별 선형 보정 (합성 관측으로 시연)",
                "per-site linear fit (demonstrated on synthetic observations)",
            ),
        ),
        (
            text(lang, "학습 루프 점검", "Training loop check"),
            text(
                lang,
                "스타터 스모크 테스트 " + ("통과" if ft == "passed" else ft),
                "starter smoke test " + ("passed" if ft == "passed" else ft),
            ),
        ),
        (
            text(lang, "발송 어댑터", "Delivery adapter"),
            text(
                lang, "우편번호 → 지점 → 메시지, dry run", "postal code → site → message, dry run"
            ),
        ),
        (
            text(lang, "자동화", "Automation"),
            text(lang, "00 / 12 UTC 크론 스크립트", "cron script at 00 / 12 UTC"),
        ),
    ]
    todo = [
        (
            text(lang, "실제 CPCB 관측 연결", "Connect real CPCB observations"),
            text(lang, "공식 데이터 제공 필요", "needs an official data feed"),
        ),
        (
            text(lang, "지역 자료로 파인튜닝", "Fine-tune on regional data"),
            text(
                lang,
                "격자화된 관측 또는 지역 재분석",
                "gridded observations or a regional reanalysis",
            ),
        ),
        (
            text(lang, "오염 농도까지 Aurora로", "Pollutants from Aurora too"),
            text(
                lang,
                "CAMS 계정 연계 (이 실행은 합성 농도)",
                "CAMS account (this run used synthetic concentrations)",
            ),
        ),
    ]
    y = 9.3
    ax.text(
        0.3,
        y,
        text(lang, "이 예제에서 실행해 본 것", "Demonstrated in this example"),
        fontsize=11.5,
        fontweight="bold",
        color=TEAL,
    )
    y -= 0.75
    for t1, t2 in done:
        ax.scatter([0.55], [y], s=110, c=TEAL, marker="o", zorder=3)
        ax.text(
            0.55,
            y,
            "✓",
            fontsize=8,
            color="white",
            ha="center",
            va="center",
            zorder=4,
            fontfamily="DejaVu Sans",
        )
        ax.text(0.95, y, t1, fontsize=10, color=INK, va="center", fontweight="bold")
        ax.text(0.95, y - 0.42, t2, fontsize=8.5, color=MUTED, va="center")
        y -= 1.05
    y -= 0.3
    ax.text(
        0.3,
        y,
        text(
            lang,
            "실제 운영 전에 남은 것 (정부·시와 함께)",
            "Still to do before going live (with government and city)",
        ),
        fontsize=11.5,
        fontweight="bold",
        color=AMBER,
    )
    y -= 0.75
    for t1, t2 in todo:
        ax.scatter(
            [0.55],
            [y],
            s=110,
            facecolors="white",
            edgecolors=AMBER,
            linewidths=2,
            marker="o",
            zorder=3,
        )
        ax.text(0.95, y, t1, fontsize=10, color=INK, va="center", fontweight="bold")
        ax.text(0.95, y - 0.42, t2, fontsize=8.5, color=MUTED, va="center")
        y -= 1.05
    return fig


# ------------------------------------------------------------------------------------ slides
def slide_html(
    lang: str, n: int, total: int, eyebrow: str, title: str, img_uri: str, body: str
) -> str:
    other = "en" if lang == "ko" else "ko"
    switch = text(lang, "English ▸", "한국어 ▸")
    return f"""<div style="position:relative; width:100%; text-align:left; color:{INK}; font-size:20px; line-height:1.45;">
<div style="position:absolute; top:-6px; right:0;"><a href="{NBLINK}/specta/?path=storyboard_{other}.ipynb" style="font-size:14px; background:{TEAL}; color:#fff; padding:4px 14px; border-radius:999px; text-decoration:none; font-weight:600;">{switch}</a></div>
<div style="display:flex; gap:26px; align-items:flex-start; width:100%;">
<div style="flex:0 0 48%; max-width:48%;"><img src="{img_uri}" alt="{title}" style="width:100%; border-radius:10px; box-shadow:0 2px 12px rgba(15,23,42,.18);"></div>
<div style="flex:1 1 52%;">
<div style="font-size:13px; color:{MUTED}; letter-spacing:.05em;">{n} / {total} · {eyebrow}</div>
<h2 style="font-size:29px; margin:4px 0 12px; color:{TEAL}; line-height:1.2;">{title}</h2>
{body}
</div></div></div>"""


def make_figure(D: dict, lang: str, fig: tuple):
    kind, kw = fig
    if kind == "map":
        extra = {k: v for k, v in kw.items() if k in ("wind", "prob", "coarse", "grid", "labels")}
        return fig_map(D, kw["step"], kw["view"], lang, kw["title"], **extra)
    return {
        "mixing": lambda: fig_mixing_layer(lang),
        "system": lambda: fig_system_flow(lang),
        "timeline": lambda: fig_timeline(D, lang),
        "peaks": lambda: fig_site_peaks(D, lang),
        "message": lambda: fig_message_anatomy(D, lang),
        "roles": lambda: fig_roles(lang),
        "roadmap": lambda: fig_roadmap(D, lang),
    }[kind]()


def build_slides(D: dict, lang: str, img_dir: Path) -> list[dict]:
    setup_fonts(lang)
    img_dir.mkdir(parents=True, exist_ok=True)
    for old in img_dir.glob("*.png"):
        old.unlink()
    S = scenes(D, lang)
    cells = []
    for i, sc in enumerate(S, 1):
        uri = png_data_uri(make_figure(D, lang, sc["fig"]), img_dir / f"{i:02d}_{sc['key']}.png")
        cells.append({"cell_type": "markdown", "metadata": {"slideshow": {"slide_type": "slide"}},
                      "source": slide_html(lang, i, len(S), sc["eyebrow"], sc["title"], uri, sc["body"])})  # fmt: skip
    return cells


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[2])
    ap.add_argument("--data", type=Path, default=HERE / "storymap_data.js")
    ap.add_argument("--out", type=Path, default=HERE / "storymap")
    a = ap.parse_args()
    D = load_data(a.data)
    for lang in ("ko", "en"):
        cells = build_slides(D, lang, a.out / "img" / lang)
        title = (
            "스토리보드: Aurora 기반 뉴델리 대기질 조기경보"
            if lang == "ko"
            else "Storyboard: Aurora-based air-quality early warning for New Delhi"
        )
        nb = {
            "cells": cells,
            "metadata": {
                "kernelspec": {
                    "display_name": "Python (XPython)",
                    "language": "python",
                    "name": "python",
                },
                "language_info": {"name": "python"},
                "specta": {
                    "defaultLayout": "slides",
                    "slidesTheme": "white",
                    "topbarTitle": title,
                    "topbarThemeToggle": "No",
                },
            },
            "nbformat": 4,
            "nbformat_minor": 5,
        }
        target = a.out / f"storyboard_{lang}.ipynb"
        target.write_text(json.dumps(nb, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        print(f"wrote {target} ({len(cells)} slides, {target.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
