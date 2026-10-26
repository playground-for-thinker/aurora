"""Copyright (c) Microsoft Corporation. Licensed under the MIT license.

Build the storyboard as Jupyter notebooks for notebook.link (Specta article view).

    python build_storyboard_notebooks.py          # writes storymap/storyboard_{ko,en}.ipynb

`STORYBOARD_kor.md` and `STORYBOARD.md` are split into one markdown cell per section, and two
code cells are inserted after the demo-output section: a matplotlib chart of the 48-hour series
at Anand Vihar and the per-site summary table. Both read small JSON files written next to the
notebooks (`storymap/data/`) from `storymap_data.js`, so the notebooks run entirely in the
browser on notebook.link (xeus-python + matplotlib) and need no Claude or other hosted service.

Specta settings are stored as notebook / cell metadata under the `specta` key (article layout,
top-bar title, hidden code cells) exactly as the Specta "App Config" / "Cell Config" forms would.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = "https://github.com/playground-for-thinker/aurora"
NBLINK = "https://notebook.link/github/playground-for-thinker/aurora/tree/storymap"
HOTSPOT = "Anand Vihar"


def load_data(path: Path) -> dict:
    js = path.read_text(encoding="utf-8")
    return json.loads(js[js.index("=") + 1 :].rstrip().rstrip(";"))


def md_cell(src: str, meta: dict | None = None) -> dict:
    return {"cell_type": "markdown", "metadata": meta or {}, "source": src.strip() + "\n"}


def code_cell(src: str, show_source: bool = False, size: str = "Big") -> dict:
    return {
        "cell_type": "code",
        "execution_count": None,
        "metadata": {"specta": {"showSource": "Yes" if show_source else "No", "outputSize": size}},
        "outputs": [],
        "source": src.strip() + "\n",
    }


def split_sections(md: str) -> list[str]:
    """Split a markdown document into chunks at every `## ` heading (the H1 block comes first)."""
    parts, cur = [], []
    for line in md.splitlines():
        if line.startswith("## ") and cur:
            parts.append("\n".join(cur))
            cur = []
        cur.append(line)
    parts.append("\n".join(cur))
    return parts


def write_data(D: dict, out: Path) -> None:
    av = D["sites"][HOTSPOT]
    series = {
        "site": HOTSPOT,
        "times_utc": D["times"],
        "aqi": av["aqi"], "pm25": av["pm25"], "blh_m": av["blh"], "wind_kmh": av["wind"], "stagnant": av["stag"],
        "provenance": D.get("provenance", {}),
    }  # fmt: skip
    (out / "data" / "anand_vihar_hourly.json").write_text(
        json.dumps(series, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    cols = [
        "site",
        "aqi_now",
        "aqi_peak",
        "category_peak",
        "dominant",
        "grap_stage",
        "stagnant_hours",
        "stagnant_night_hours",
        "min_blh_m",
        "peak_time_ist",
    ]
    rows = [dict(zip(cols, r)) for r in D.get("summary", [])]
    (out / "data" / "summary_by_site.json").write_text(
        json.dumps(rows, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
    )


# The browser build of matplotlib ships DejaVu only (no Hangul glyphs), so the chart labels are
# English in both notebooks; the surrounding markdown carries the Korean explanation.
CHART_SRC = """import json
from datetime import datetime, timedelta
from pathlib import Path

import matplotlib.pyplot as plt

d = json.loads(Path("data/anand_vihar_hourly.json").read_text(encoding="utf-8"))
ist = [datetime.fromisoformat(t) + timedelta(hours=5, minutes=30) for t in d["times_utc"]]
stag = d["stagnant"]

fig, axes = plt.subplots(3, 1, figsize=(9, 7.5), sharex=True)
panels = [("pm25", "PM2.5 (µg/m³)", "#c84a3b", 250), ("blh_m", "Boundary-layer height (m)", "#0b6e8f", 500), ("wind_kmh", "10 m wind (km/h)", "#5a5a5a", 10)]
for ax, (key, label, color, thr) in zip(axes, panels):
    ax.plot(ist, d[key], color=color, lw=2)
    ax.axhline(thr, color="#999", lw=0.8, ls="--")
    for i, s in enumerate(stag):
        if s:
            ax.axvspan(ist[i] - timedelta(minutes=30), ist[i] + timedelta(minutes=30), color="#0b6e8f", alpha=0.08, lw=0)
    ax.set_ylabel(label)
    ax.grid(alpha=0.25)
axes[0].set_title(f"{d['site']} · 48-hour forecast (IST) · blue shading = stagnant hours (wind < 10 km/h, mixing height < 500 m)")
axes[-1].set_xlabel("IST")
fig.autofmt_xdate()
prov = d.get("provenance", {})
fig.text(0.01, 0.005, f"Weather: {prov.get('meteorology', 'synthetic')} · Pollutants: {prov.get('pollutants', 'synthetic')}", fontsize=8, color="#666")
plt.tight_layout()
plt.show()
"""


TABLE_SRC = {
    "ko": """import json
from pathlib import Path

from IPython.display import Markdown, display

rows = json.loads(Path("data/summary_by_site.json").read_text(encoding="utf-8"))
cat_ko = {"Good": "좋음", "Satisfactory": "양호", "Moderate": "보통", "Poor": "나쁨", "Very Poor": "매우 나쁨", "Severe": "위험"}
lines = ["| 지점 | 현재 AQI | 최고 AQI | 범주 | 주 오염물질 | GRAP | 정체 h (야간) | 최저 혼합층 m | 정점 (IST) |", "| --- | ---: | ---: | --- | --- | ---: | ---: | ---: | --- |"]
for r in rows:
    lines.append(f"| {r['site']} | {r['aqi_now']} | {r['aqi_peak']} | {cat_ko.get(r['category_peak'], r['category_peak'])} | {r['dominant']} | {r['grap_stage']} | {r['stagnant_hours']} ({r['stagnant_night_hours']}) | {r['min_blh_m']} | {r['peak_time_ist']} |")
display(Markdown("\\n".join(lines)))
""",
    "en": """import json
from pathlib import Path

from IPython.display import Markdown, display

rows = json.loads(Path("data/summary_by_site.json").read_text(encoding="utf-8"))
lines = ["| Site | AQI now | AQI peak | Category | Dominant | GRAP | Stagnant h (night) | Min BLH m | Peak (IST) |", "| --- | ---: | ---: | --- | --- | ---: | ---: | ---: | --- |"]
for r in rows:
    lines.append(f"| {r['site']} | {r['aqi_now']} | {r['aqi_peak']} | {r['category_peak']} | {r['dominant']} | {r['grap_stage']} | {r['stagnant_hours']} ({r['stagnant_night_hours']}) | {r['min_blh_m']} | {r['peak_time_ist']} |")
display(Markdown("\\n".join(lines)))
""",
}


def build_notebook(md: str, lang: str) -> dict:
    ko = lang == "ko"
    switch = (
        f"[English version]({NBLINK}/specta/?path=storyboard_en.ipynb) · "
        f"[스토리 맵 (JupyterGIS)]({NBLINK}/specta/?path=delhi_aq_storymap_ko.jGIS) · "
        f"[소스 (GitHub)]({REPO}/tree/main/examples/delhi_air_quality)"
        if ko
        else f"[한국어 버전]({NBLINK}/specta/?path=storyboard_ko.ipynb) · "
        f"[Story map (JupyterGIS)]({NBLINK}/specta/?path=delhi_aq_storymap_en.jGIS) · "
        f"[Source (GitHub)]({REPO}/tree/main/examples/delhi_air_quality)"
    )
    # File names mentioned in the text become links to the repository / the other notebook.
    md = md.replace(
        "`STORYBOARD_kor.md`", f"[`STORYBOARD_kor.md`]({NBLINK}/specta/?path=storyboard_ko.ipynb)"
    )
    md = md.replace(
        "`STORYBOARD.md`", f"[`STORYBOARD.md`]({NBLINK}/specta/?path=storyboard_en.ipynb)"
    )
    md = re.sub(r"`(delhi_aq\.py|example_delhi_air_quality\.ipynb|README_kor\.md|storyboard\.html|storymap\.html)`",
                lambda m: f"[`{m.group(1)}`]({REPO}/blob/main/examples/delhi_air_quality/{m.group(1)})", md)  # fmt: skip
    md = md.replace(
        "`storymap/`", f"[`storymap/`]({REPO}/tree/main/examples/delhi_air_quality/storymap)"
    )

    sections = split_sections(md)
    cells: list[dict] = []
    head = sections[0].split("\n", 1)
    cells.append(md_cell(head[0] + "\n\n" + switch + "\n" + (head[1] if len(head) > 1 else "")))
    demo_re = re.compile(r"^## 5\. ")
    for sec in sections[1:]:
        cells.append(md_cell(sec))
        if demo_re.match(sec):
            cells.append(md_cell(
                "### " + ("Anand Vihar 48시간 시계열과 지점별 요약 (브라우저에서 계산)" if ko else "Anand Vihar 48-hour series and per-site summary (computed in the browser)") + "\n\n" +
                ("아래 두 셀은 이 노트북 옆의 `data/anand_vihar_hourly.json`, `data/summary_by_site.json`(스토리 맵과 같은 실행 결과)을 읽어 notebook.link의 WebAssembly Python 커널에서 그립니다. 코드는 Specta 설정으로 숨겨져 있으며 JupyterLab 보기에서 볼 수 있습니다."
                 if ko else
                 "The two cells below read `data/anand_vihar_hourly.json` and `data/summary_by_site.json` next to this notebook (the same run as the story map) and draw them in notebook.link's WebAssembly Python kernel. The code is hidden by the Specta cell settings and visible in the JupyterLab view.")
            ))  # fmt: skip
            cells.append(code_cell(CHART_SRC, size="Big"))
            cells.append(code_cell(TABLE_SRC[lang], size="Big"))
    title = (
        "스토리보드: Aurora 기반 뉴델리 대기질 조기경보"
        if ko
        else "Storyboard: Aurora-based air-quality early warning for New Delhi"
    )
    return {
        "cells": cells,
        "metadata": {
            "kernelspec": {
                "display_name": "Python (XPython)",
                "language": "python",
                "name": "python",
            },
            "language_info": {"name": "python"},
            "specta": {
                "defaultLayout": "article",
                "topbarTitle": title,
                "topbarThemeToggle": "Yes",
            },
        },
        "nbformat": 4,
        "nbformat_minor": 5,
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[2])
    ap.add_argument("--data", type=Path, default=HERE / "storymap_data.js")
    ap.add_argument("--out", type=Path, default=HERE / "storymap")
    a = ap.parse_args()
    (a.out / "data").mkdir(parents=True, exist_ok=True)
    write_data(load_data(a.data), a.out)
    for lang, src in (("ko", "STORYBOARD_kor.md"), ("en", "STORYBOARD.md")):
        nb = build_notebook((HERE / src).read_text(encoding="utf-8"), lang)
        target = a.out / f"storyboard_{lang}.ipynb"
        target.write_text(json.dumps(nb, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        print(f"wrote {target} ({len(nb['cells'])} cells)")


if __name__ == "__main__":
    main()
