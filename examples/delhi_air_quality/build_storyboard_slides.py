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
def esc(s: str) -> str:
    return s.replace("~", "–").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def ul(items: list[str]) -> str:
    return (
        "<ul style='margin:0 0 10px 22px; padding:0;'>"
        + "".join(f"<li style='margin:0 0 7px 0;'>{i}</li>" for i in items)
        + "</ul>"
    )


def sys_box(lang: str, body: str) -> str:
    return (f"<div style='background:#e6f3f7; border-left:6px solid {TEAL}; padding:9px 14px; border-radius:8px; margin:10px 0; font-size:18px;'>"
            f"<b style='color:{TEAL};'>{text(lang, '현 시스템이 보여주는 것', 'What this system shows')}</b> · {body}</div>")  # fmt: skip


def gov_box(lang: str, body: str) -> str:
    return (f"<div style='background:#fff4e0; border-left:6px solid {AMBER}; padding:9px 14px; border-radius:8px; margin:10px 0; font-size:18px;'>"
            f"<b style='color:{AMBER};'>{text(lang, '정부·시가 할 일', 'Government and city')}</b> · {body}</div>")  # fmt: skip


def phone(label: str, body: str, dark: bool = True) -> str:
    bg, fg = ("#0f172a", "#f8fafc") if dark else ("#e2e8f0", INK)
    return (f"<div style='background:{bg}; color:{fg}; padding:10px 16px; border-radius:16px; margin:10px 0; font-size:17px; line-height:1.4;'>"
            f"<div style='font-size:12px; opacity:.7; margin-bottom:3px;'>📱 {label}</div>{esc(body)}</div>")  # fmt: skip


def table(header: list[str], rows: list[list[str]], size: int = 16) -> str:
    th = "".join(
        f"<th style='text-align:left; padding:5px 8px; border-bottom:2px solid #cbd5e1; color:{MUTED}; font-size:{size - 2}px;'>{h}</th>"
        for h in header
    )
    trs = "".join(
        "<tr>"
        + "".join(
            f"<td style='padding:5px 8px; border-bottom:1px solid #e2e8f0;'>{c}</td>" for c in r
        )
        + "</tr>"
        for r in rows
    )
    return f"<table style='border-collapse:collapse; width:100%; font-size:{size}px; margin:6px 0;'><thead><tr>{th}</tr></thead><tbody>{trs}</tbody></table>"


def slide_html(
    lang: str, n: int, total: int, eyebrow: str, title: str, img_uri: str, body: str
) -> str:
    other = "en" if lang == "ko" else "ko"
    switch = text(lang, "English ▸", "한국어 ▸")
    return f"""<div style="position:relative; width:100%; text-align:left; color:{INK};">
<div style="position:absolute; top:-6px; right:0;"><a href="{NBLINK}/specta/?path=storyboard_{other}.ipynb" style="font-size:14px; background:{TEAL}; color:#fff; padding:4px 14px; border-radius:999px; text-decoration:none; font-weight:600;">{switch}</a></div>
<div style="display:flex; gap:26px; align-items:flex-start; width:100%;">
<div style="flex:0 0 48%; max-width:48%;"><img src="{img_uri}" alt="{esc(title)}" style="width:100%; border-radius:10px; box-shadow:0 2px 12px rgba(15,23,42,.18);"></div>
<div style="flex:1 1 52%; font-size:20px; line-height:1.45;">
<div style="font-size:13px; color:{MUTED}; letter-spacing:.05em;">{n} / {total} · {eyebrow}</div>
<h2 style="font-size:29px; margin:4px 0 12px; color:{TEAL}; line-height:1.2;">{title}</h2>
{body}
</div></div></div>"""


def build_slides(D: dict, lang: str, img_dir: Path) -> list[dict]:
    setup_fonts(lang)
    times = D["times"]
    M = D.get("messages") or {}
    PV = D.get("provenance") or {}
    met_real = "Aurora" in (PV.get("meteorology") or "")
    pm_real = "Aurora" in (PV.get("pollutants") or "")
    av = D["sites"]["Anand Vihar"]
    night_blh = min(av["blh"][3:14])
    night_wind = sorted(av["wind"][3:14])[5]
    ens = D.get("ensemble")
    t = lambda a, b: text(lang, a, b)  # noqa: E731
    tag_met = (
        t("기상: Aurora 1.5", "Weather: Aurora 1.5")
        if met_real
        else t("기상: 합성", "Weather: synthetic")
    )
    tag_pm = (
        t("농도: Aurora Air Pollution", "Pollutants: Aurora Air Pollution")
        if pm_real
        else t("농도: 합성 예시", "Pollutants: synthetic example")
    )
    img_dir.mkdir(parents=True, exist_ok=True)

    def img(name: str, fig) -> str:
        return png_data_uri(fig, img_dir / f"{name}.png")

    S: list[tuple[str, str, str, str]] = []  # eyebrow, title, image uri, body

    S.append(
        (
            t(
                "Aurora 기상 AI · 델리 대기질 경보",
                "Aurora Earth-system AI · Delhi air-quality alerts",
            ),
            t(
                "시민에게 닿는 한 줄의 대기질 경보",
                "One line of air-quality warning that reaches a citizen",
            ),
            img(
                "01_cover",
                fig_map(
                    D,
                    35,
                    "delhi",
                    lang,
                    t(
                        f"예측 AQI · {ist(times, 35, lang)} IST (가장 심한 시각)",
                        f"Forecast AQI · {ist(times, 35, lang)} IST (worst hour)",
                    ),
                ),
            ),
            phone(
                t(
                    "시민에게 가는 한 줄 (예측 결과로 자동 생성)",
                    "The line a citizen receives (generated from the forecast)",
                ),
                (M.get(lang) or {}).get("short", ""),
            )
            + ul(
                [
                    t(
                        "Microsoft Research의 지구시스템 AI <b>Aurora</b>로 델리의 48시간 대기질을 예측합니다.",
                        "The 48-hour air quality of Delhi is forecast with <b>Aurora</b>, Microsoft Research's Earth-system AI.",
                    ),
                    t(
                        "예측을 인도 공식 기준(CPCB AQI, GRAP 단계)으로 바꿔 힌디어·영어·한국어 메시지로 만듭니다.",
                        "The forecast becomes India's official scale (CPCB AQI, GRAP stages) and messages in Hindi, English and Korean.",
                    ),
                    t(
                        "이 발표: 왜 델리인가 → Aurora가 무엇을 계산하는가 → 시민에게 어떻게 닿는가 → 시스템과 정부의 역할.",
                        "This talk: why Delhi → what Aurora computes → how it reaches citizens → what the system does and what government must own.",
                    ),
                ]
            )
            + f"<div style='font-size:14px; color:{MUTED};'>{tag_met} · {tag_pm} · {t('초기 시각', 'initial time')} {PV.get('init_time', '').replace('T', ' ')} UTC</div>",
        )
    )

    S.append(
        (
            t("1 · 배경", "1 · Background"),
            t("왜 델리이고, 왜 11월인가", "Why Delhi, why November"),
            img("02_background", fig_mixing_layer(lang)),
            ul(
                [
                    t(
                        "델리 수도권은 매년 10월 말–1월에 세계 최악 수준의 미세먼지를 겪습니다. 볏짚 소각, 디왈리 폭죽, 교통·건설·발전 배출이 겹칩니다.",
                        "Delhi-NCR suffers some of the world's worst particulate pollution from late October to January: stubble burning, Diwali fireworks, traffic, construction and power plants.",
                    ),
                    t(
                        "겨울밤에는 <b>혼합층이 100–300 m로 낮아지고 바람이 약해져</b> 오염이 지표 근처에 갇힙니다. 같은 배출량이라도 밤이 더 나쁩니다.",
                        "On winter nights the <b>mixing layer drops to 100–300 m and winds die down</b>, trapping pollution near the ground. Same emissions, worse nights.",
                    ),
                    t(
                        "인도에는 이미 제도가 있습니다: 국가 AQI(CPCB)와 단계별 조치 GRAP(건설 중단, 차량 제한, 원격수업…).",
                        "India already has the institutions: a national AQI (CPCB) and the staged GRAP measures (construction bans, vehicle limits, online classes…).",
                    ),
                ]
            )
            + f"<div style='background:{PAPER}; border:1px solid #cbd5e1; padding:9px 14px; border-radius:8px; font-size:18px;'>"
            + t(
                '핵심 질문은 "얼마나 나빠질까"가 아니라 <b>"언제, 어디서, 왜 나빠지고, 시민은 무엇을 해야 하는가"</b>를 12–48시간 앞서 전하는 것입니다.',
                'The question is not "how bad" but <b>"when, where, why, and what should citizens do"</b>, 12 to 48 hours ahead.',
            )
            + "</div>",
        )
    )

    S.append(
        (
            t("2 · 시스템", "2 · System") + f" · {tag_met} · {tag_pm}",
            t("Aurora가 두 번 등장한다", "Aurora appears twice"),
            img("03_system", fig_system_flow(lang)),
            ul(
                [
                    t(
                        "<b>Aurora</b>는 위성·관측 기반 분석 자료를 입력받아 지구의 날씨와 대기 성분을 예측하는 파운데이션 모델입니다. GPU 한 장이면 수 분 안에 48시간을 예측합니다.",
                        "<b>Aurora</b> is a foundation model that takes global analyses and forecasts the Earth's weather and atmospheric composition. One GPU gives 48 hours in minutes.",
                    ),
                    t(
                        "<b>Air Pollution 모델</b>은 농도를 직접 예측하지만 12시간 간격입니다. <b>Aurora 1.5</b>는 오염을 예측하지 않지만 시간별 바람과 혼합층을 줍니다.",
                        "The <b>Air Pollution model</b> predicts concentrations directly but every 12 hours. <b>Aurora 1.5</b> predicts no pollutants but gives hourly wind and mixing height.",
                    ),
                    t(
                        '둘을 합치면 "얼마나 높아질지"와 "오늘 밤 몇 시부터 정체가 시작되는지"를 함께 말할 수 있습니다.',
                        'Together they answer "how high" and "from what hour tonight stagnation sets in".',
                    ),
                ]
            )
            + sys_box(
                lang,
                t(
                    "두 모델 실행 → 10개 지점 AQI·GRAP 수준·정체 시간 → 메시지 초안까지 자동. 체크포인트는 공개(HuggingFace), 클라우드 엔드포인트(Azure AI Foundry)로도 실행 가능.",
                    "both models → AQI, GRAP level and stagnant hours at 10 sites → draft messages, all automatic. Checkpoints are public (HuggingFace); the same runs on an Azure AI Foundry endpoint.",
                ),
            ),
        )
    )

    S.append(
        (
            t("3 · 하루의 흐름", "3 · One day"),
            t(
                "48시간 타임라인: 저녁 경보에서 아침 업데이트까지",
                "48-hour timeline: from the evening alert to the morning update",
            ),
            img("04_timeline", fig_timeline(D, lang)),
            table(
                [
                    t("시각 (IST)", "Time (IST)"),
                    t("장면", "Scene"),
                    t("무슨 일이 일어나는가", "What happens"),
                ],
                [
                    [
                        "17:30",
                        t("초기장·예측", "Analyses, forecast"),
                        t(
                            "12 UTC 분석 자료 확보, 두 모델 실행 (약 10분)",
                            "12 UTC analyses arrive, both models run (about 10 min)",
                        ),
                    ],
                    [
                        "18:00",
                        t("저녁 경보", "Evening alert"),
                        t(
                            "지점별 한 줄 메시지, 운영자 브리핑",
                            "one line per site, operator briefing",
                        ),
                    ],
                    [
                        "22:00–08:00",
                        t("정체 구간", "Stagnation"),
                        t(
                            "혼합층 하강, 지표에 축적 → 민감군 리마인더",
                            "mixing layer falls, pollution pools → reminder for sensitive groups",
                        ),
                    ],
                    [
                        "05:30",
                        t("정점", "Peak"),
                        t("가장 심한 시각, 교통 지점 최고", "worst hour, traffic sites highest"),
                    ],
                    [
                        "06:00",
                        t("아침 업데이트", "Morning update"),
                        t(
                            "00 UTC 자료로 재실행, 등교·출근 전 발송",
                            "re-run on 00 UTC data, sent before school and commute",
                        ),
                    ],
                    [
                        "14:30",
                        t("오후 숨 고르기", "Afternoon breather"),
                        t(
                            "혼합층 상승, 환기·외출 가능한 창",
                            "mixing layer rises, a window to ventilate",
                        ),
                    ],
                    [
                        t("사후", "Afterwards"),
                        t("검증", "Verification"),
                        t(
                            "공식 관측과 비교, 지점별 보정",
                            "compare with official monitors, correct per site",
                        ),
                    ],
                ],
                size=15,
            )
            + f"<div style='font-size:15px; color:{MUTED};'>{t('그래프: Anand Vihar의 AQI와 혼합층. 파란 띠가 정체 시간(바람 < 10 km/h, 혼합층 < 500 m).', 'Chart: AQI and mixing height at Anand Vihar; blue bands are stagnant hours (wind < 10 km/h, mixing height < 500 m).')}</div>",
        )
    )

    S.append(
        (
            t("4 · 장면 S3·S4", "4 · Scenes S3·S4") + f" · {tag_pm}",
            t(
                f"{ist(times, 0, lang)} IST, 저녁 경보",
                f"{ist(times, 0, lang)} IST, the evening alert",
            ),
            img(
                "05_evening",
                fig_map(
                    D,
                    0,
                    "delhi",
                    lang,
                    t(
                        f"예측 AQI · {ist(times, 0, lang)} IST",
                        f"Forecast AQI · {ist(times, 0, lang)} IST",
                    ),
                ),
            ),
            ul(
                [
                    t(
                        '첫 예측 시각. 델리 전체가 이미 "매우 나쁨" 이상이고, 교통 지점(Anand Vihar, ITO, Gurugram)이 가장 높습니다.',
                        'The first forecast hour. All of Delhi is already "Very Poor" or worse; traffic sites (Anand Vihar, ITO, Gurugram) are highest.',
                    ),
                    t(
                        "지점별 AQI와 GRAP 해당 수준을 계산하고, 시민용 한 줄과 운영자 브리핑을 만듭니다.",
                        "Per-site AQI and the corresponding GRAP level are computed; a one-liner for citizens and a briefing for operators are drafted.",
                    ),
                ]
            )
            + phone(
                t("시민용 · 힌디어 (1차 언어)", "Citizens · Hindi (first language)"),
                (M.get("hi") or {}).get("short", ""),
            )
            + phone(
                t("도시 헤드라인 · 운영자용", "City headline · for operators"),
                (M.get(lang) or {}).get("city", ""),
                dark=False,
            )
            + gov_box(
                lang,
                t(
                    "경보의 공식 발령과 채널(SMS·앱·방송)은 CAQM/델리 정부의 몫. 시스템은 초안과 근거를 제공합니다.",
                    "official issuance and channels (SMS, app, broadcast) belong to CAQM and the Delhi government; the system provides the draft and the evidence.",
                ),
            ),
        )
    )

    S.append(
        (
            t("5 · 장면 S6", "5 · Scene S6") + f" · {tag_met}",
            t(
                f"{ist(times, 8, lang)} IST, 정체가 시작된다",
                f"{ist(times, 8, lang)} IST, stagnation sets in",
            ),
            img(
                "06_night",
                fig_map(
                    D,
                    8,
                    "delhi",
                    lang,
                    t(
                        f"AQI와 10 m 바람 · {ist(times, 8, lang)} IST",
                        f"AQI and 10 m wind · {ist(times, 8, lang)} IST",
                    ),
                    wind=True,
                    labels=False,
                ),
            ),
            ul(
                [
                    t(
                        f"Aurora 1.5가 예측한 첫째 밤 Anand Vihar의 혼합층은 최저 <b>{night_blh} m</b>, 풍속 중앙값 <b>{night_wind:.1f} km/h</b>. 화살표가 그 바람입니다.",
                        f"For the first night Aurora 1.5 puts Anand Vihar's mixing layer as low as <b>{night_blh} m</b> with a median wind of <b>{night_wind:.1f} km/h</b>; the arrows are that wind.",
                    ),
                    t(
                        '배출이 같아도 섞일 공기가 얇아지면 지표 농도가 오릅니다. 이것이 "밤에 더 나쁜 이유"입니다.',
                        "With the same emissions and a thinner layer of air to mix into, surface concentrations rise. That is why nights are worse.",
                    ),
                ]
            )
            + phone(
                t("메시지에 추가되는 문장", "Sentence added to the message"),
                t(
                    "밤부터 아침까지 오염이 지표 근처에 쌓이기 쉽습니다. 창문을 닫고 새벽 운동은 피하세요.",
                    "From night to morning pollution will tend to pool near the surface. Keep windows closed and skip early-morning exercise.",
                ),
            )
            + sys_box(
                lang,
                t(
                    "시간별 정체 판정은 Aurora 1.5의 실제 계산 결과(ARCO-ERA5 초기장).",
                    "the hourly stagnation flags are real Aurora 1.5 output (ARCO-ERA5 initial condition).",
                ),
            ),
        )
    )

    S.append(
        (
            t("6 · 장면 S7", "6 · Scene S7") + f" · {tag_pm}",
            t(
                f"{ist(times, 35, lang)} IST, 가장 심각한 곳",
                f"{ist(times, 35, lang)} IST, the worst-hit site",
            ),
            img("07_peak", fig_site_peaks(D, lang)),
            ul(
                [
                    t(
                        "두 번째 새벽. 동부 델리의 Anand Vihar(버스터미널과 간선도로가 모인 교통 지점)가 AQI 500에 닿고, ITO·Noida·Okhla도 450을 넘습니다.",
                        "The second pre-dawn. Anand Vihar in east Delhi (a traffic site at a bus terminal and arterial roads) reaches AQI 500; ITO, Noida and Okhla exceed 450.",
                    ),
                    t(
                        '06:00 아침 업데이트는 등교·출근 전에 "오전 7–9시 최고치, 마스크 착용"을 보냅니다.',
                        'The 06:00 morning update sends "peak 07:00–09:00, wear a mask" before school and commute.',
                    ),
                ]
            )
            + phone(
                t(
                    "민감군·운영자용 상세 (일부)",
                    "Detail for sensitive groups and operators (excerpt)",
                ),
                "\n".join(
                    [ln for ln in ((M.get(lang) or {}).get("long", "")).split("\n") if ln.strip()][
                        1:4
                    ]
                ),
                dark=False,
            )
            + gov_box(
                lang,
                t(
                    "정점 시각과 GRAP 근거는 시가 조치를 결정할 재료. 집행(차량 제한, 공사 중단, 휴교)은 당국의 결정입니다.",
                    "peak time and the GRAP basis are the material for the city's decision; enforcement (vehicle limits, construction halts, school closures) is the authority's call.",
                ),
            ),
        )
    )

    if ens:
        n = ens["members"]

        def win(p, a, b):
            s = p[a : b + 1]
            return f"{round(100 * sum(s) / len(s))}%"

        rows = [
            [name, win(e["p"], 3, 13), win(e["p"], 14, 27), win(e["p"], 28, 37)]
            for name, e in list(ens["sites"].items())[:5]
        ]
        S.append(
            (
                t("7 · 불확실성", "7 · Uncertainty")
                + " · "
                + (
                    t("앙상블: Aurora 1.5 Ensemble", "Ensemble: Aurora 1.5 Ensemble")
                    if "Aurora" in (PV.get("ensemble") or "")
                    else t("앙상블: 시뮬레이션", "Ensemble: simulated")
                ),
                t('"정체 확률 80%"로 말하기', 'Saying "80% chance of stagnation"'),
                img(
                    "08_probability",
                    fig_map(
                        D,
                        35,
                        "delhi",
                        lang,
                        t(
                            f"정체 확률 · {ist(times, 35, lang)} IST (진할수록 높음)",
                            f"Stagnation probability · {ist(times, 35, lang)} IST (darker = higher)",
                        ),
                        prob=True,
                    ),
                ),
                ul(
                    [
                        t(
                            f"같은 모델을 서로 다른 시드로 <b>{n}번</b> 실행해 각 멤버의 혼합층과 바람으로 정체 여부를 판정하고, 정체인 멤버의 비율을 확률로 씁니다.",
                            f"The same model is run <b>{n} times</b> with different seeds; each member's mixing height and wind decide stagnation, and the share of stagnant members is the probability.",
                        ),
                        t(
                            '시민에게는 "확실히" 대신 "높은 확률로"를 말할 수 있고, 운영자는 낮은 확률의 밤에 과잉 조치를 피할 수 있습니다.',
                            'Citizens can be told "very likely" instead of "certainly", and operators can avoid over-reacting on low-probability nights.',
                        ),
                    ]
                )
                + table(
                    [t("지점", "Site"), t("밤 1", "Night 1"), t("낮", "Day"), t("밤 2", "Night 2")],
                    rows,
                    size=15,
                )
                + sys_box(
                    lang,
                    t(
                        "앙상블 실행과 확률 계산까지 자동. 확률을 문구로 바꾸는 기준은 보건 당국과 정해야 합니다.",
                        "the ensemble run and the probabilities are automatic; the thresholds that turn them into wording are agreed with health authorities.",
                    ),
                ),
            )
        )

    S.append(
        (
            t("8 · 메시지 설계", "8 · Message design"),
            t(
                "160자 안에 무엇·언제·어디·왜·어떻게",
                "What, when, where, why and how in 160 characters",
            ),
            img("09_message", fig_message_anatomy(D, lang)),
            ul(
                [
                    t(
                        "<b>무엇</b>(수치+CPCB 범주) · <b>언제</b>(IST 정점) · <b>어디</b>(지점) · <b>어떻게</b>(행동 1–2개). 짧은 문장은 SMS·푸시, 긴 문장은 앱·브리핑용.",
                        "<b>What</b> (value + CPCB category) · <b>when</b> (IST peak) · <b>where</b> (site) · <b>how</b> (one or two actions). Short for SMS/push, long for the app and briefings.",
                    ),
                    t(
                        "범주는 CPCB 용어 그대로. 뉴스·공식 앱과 같은 말을 써야 혼란이 없습니다.",
                        "Category names exactly as CPCB uses them, so they match the news and the official app.",
                    ),
                    t(
                        '<b>민감군을 먼저</b> 호명하고, 기상 근거를 한 문장 넣습니다. "왜 밤에 나쁜가"를 알면 행동 순응도가 올라갑니다.',
                        "<b>Name sensitive groups first</b> and add one sentence of weather reasoning; people who understand why nights are worse comply better.",
                    ),
                    t(
                        'GRAP는 "해당 수준"으로만. 발령은 CAQM 권한. 면책 문구는 고정: "AI 참고 정보, 공식 경보는 CPCB/CAQM".',
                        'GRAP as "corresponding level" only; invoking it is CAQM\'s authority. A fixed disclaimer: "AI guidance; follow official CPCB/CAQM alerts".',
                    ),
                ]
            )
            + gov_box(
                lang,
                t(
                    "문구 템플릿은 코드 밖에 있어 보건 전문가가 검수·수정할 수 있습니다. 최종 문안의 책임은 발령 기관에 있습니다.",
                    "the wording templates live outside the code so health experts can review and edit them; the issuing authority owns the final text.",
                ),
            ),
        )
    )

    S.append(
        (
            t("9 · 역할 구분", "9 · Who does what"),
            t(
                "시스템이 보여주는 것과 정부·시가 맡아야 할 것",
                "What the system shows and what government and city must own",
            ),
            img("10_roles", fig_roles(lang)),
            sys_box(
                lang,
                t(
                    "예측 → AQI·GRAP 수준 → 정체 시간·확률 → 메시지 초안·브리핑·지도. 12시간마다 자동 재발행. 발송 어댑터는 우편번호→지점 매핑까지 시연(dry run).",
                    "forecast → AQI and GRAP level → stagnant hours and probability → draft messages, briefing, maps. Automatic re-issue every 12 h. The delivery adapter demonstrates postal code → site mapping (dry run).",
                ),
            )
            + gov_box(
                lang,
                t(
                    "공식 관측망 연결·검증과 보정, GRAP 발령·집행, 구독자 등록과 개인별 발송 채널(SMS·WhatsApp·앱), 보건 문구 검수, 취약계층 지원, 시민 교육.",
                    "connecting and verifying the official monitors, bias correction, invoking and enforcing GRAP, the subscriber registry and personal channels (SMS, WhatsApp, app), health wording review, support for vulnerable groups, public education.",
                ),
            )
            + ul(
                [
                    t(
                        "인계 지점은 명확합니다: 시스템은 <b>근거와 초안</b>을 12시간마다 만들고, 당국은 <b>판단·발령·전달</b>을 맡습니다.",
                        "The hand-off is clear: the system produces <b>evidence and drafts</b> every 12 hours; the authority owns <b>judgement, issuance and delivery</b>.",
                    ),
                    t(
                        "개인별 메시지(우편번호 → 가장 가까운 지점)는 구독자 정보가 있는 정부 채널에서만 완성됩니다.",
                        "Personal messages (postal code → nearest site) are only completed inside a government channel that holds subscriber data.",
                    ),
                ]
            ),
        )
    )

    S.append(
        (
            t("10 · 한계와 책임", "10 · Limits and responsibility") + f" · {tag_pm}",
            t(
                "해상도의 진실, 그리고 책임 있는 사용",
                "The truth about resolution, and responsible use",
            ),
            img(
                "11_limits",
                fig_map(
                    D,
                    35,
                    "delhi",
                    lang,
                    t(
                        "Air Pollution 모델의 0.4° 셀 하나와 10개 지점",
                        "One 0.4° cell of the Air Pollution model and the ten sites",
                    ),
                    coarse=True,
                    grid=True,
                ),
            ),
            ul(
                [
                    t(
                        "큰 사각형이 Air Pollution 모델의 셀 하나. 델리 대부분이 두세 개 셀에 들어갑니다. <b>지점 간 차이는 보간 결과</b>이지 도로변 측정값이 아닙니다.",
                        "The large square is one cell of the Air Pollution model; most of Delhi fits in two or three. <b>Differences between sites are interpolation</b>, not roadside measurements.",
                    ),
                    t(
                        "시간별 농도 곡선은 12시간 예측을 이은 것이고, 시간별 구조의 근거는 Aurora 1.5의 기상입니다. 메시지에도 그렇게 적습니다.",
                        "The hourly concentration curve joins 12-hour forecasts; the hourly structure comes from Aurora 1.5's weather, and the messages say so.",
                    ),
                    t(
                        "이 실행에서 농도는 <b>합성 예시</b>입니다(CAMS 자료는 계정 필요). 정체 시간대는 실제 모델 결과입니다.",
                        "In this run the concentrations are a <b>synthetic example</b> (CAMS data needs an account); the stagnant hours are real model output.",
                    ),
                    t(
                        "Aurora는 연구용 모델입니다. 전문가 검토 없는 운영 결정에 쓰여서는 안 됩니다.",
                        "Aurora is a research model. It must not drive operational decisions without expert review.",
                    ),
                ]
            )
            + gov_box(
                lang,
                t(
                    "실제 서비스에는 관측소별 보정이나 지역 자료로의 파인튜닝이 필요하며, 이는 공식 관측 데이터 제공이 전제입니다.",
                    "a real service needs per-station correction or fine-tuning on regional data, which presupposes access to the official observations.",
                ),
            ),
        )
    )

    S.append(
        (
            t("11 · 다음 단계", "11 · Next steps"),
            t("실행해 본 것과 남은 것", "Done, and still to do"),
            img("12_roadmap", fig_roadmap(D, lang)),
            ul(
                [
                    t(
                        "불확실성(앙상블), 관측 보정 절차, 학습 루프 점검, 발송 어댑터, 자동화의 다섯 항목은 이 예제에서 실행해 봤습니다.",
                        "Five items were run in this example: ensemble uncertainty, the correction procedure, a training-loop check, the delivery adapter and automation.",
                    ),
                    t(
                        "남은 것은 모두 <b>정부·시와의 협력</b>이 전제입니다: 공식 관측 연결, 지역 자료 파인튜닝, 농도 자료(CAMS) 연계.",
                        "Everything that remains presupposes <b>cooperation with government and city</b>: official observations, regional fine-tuning, pollutant data (CAMS).",
                    ),
                    t(
                        '한 줄 요약: Aurora는 "언제, 어디서, 왜"를 12–48시간 앞서 계산해 주고, 그것을 시민의 행동으로 바꾸는 마지막 구간은 제도와 채널의 몫입니다.',
                        'In one line: Aurora computes "when, where and why" 12 to 48 hours ahead; turning that into citizens\' actions is the job of institutions and channels.',
                    ),
                ]
            )
            + f"<div style='background:{PAPER}; border:1px solid #cbd5e1; padding:9px 14px; border-radius:8px; font-size:17px;'>"
            + t(
                f"지도 위에서 장면별로 보기: <a href='{NBLINK}/specta/?path=delhi_aq_storymap_ko.jGIS'>스토리 맵 (JupyterGIS)</a> · 영어 발표: <a href='{NBLINK}/specta/?path=storyboard_en.ipynb'>English deck</a>",
                f"Scene by scene on a map: <a href='{NBLINK}/specta/?path=delhi_aq_storymap_en.jGIS'>story map (JupyterGIS)</a> · Korean deck: <a href='{NBLINK}/specta/?path=storyboard_ko.ipynb'>한국어</a>",
            )
            + "</div>",
        )
    )

    total = len(S)
    cells = []
    for i, (eyebrow, title, uri, body) in enumerate(S, 1):
        cells.append({"cell_type": "markdown", "metadata": {"slideshow": {"slide_type": "slide"}},
                      "source": slide_html(lang, i, total, eyebrow, title, uri, body)})  # fmt: skip
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
