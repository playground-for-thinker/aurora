"""Copyright (c) Microsoft Corporation. Licensed under the MIT license.

Build `storymap_data.js` for `storymap.html` from a `delhi_aq.py` output directory.

    python build_storymap_data.py outputs/ --finetune-log path/to/finetune_smoke.log

The world / India / state outlines are reused from the existing `storymap_data.js` next to this
script (they were derived from Natural Earth and geoBoundaries once); everything else comes from
the output directory: the map tile, per-site hourly series, ensemble stagnation probability,
bias-correction fit, delivery log, cron script and provenance.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent


def load_existing_geometry(path: Path) -> dict:
    js = path.read_text(encoding="utf-8")
    data = json.loads(js[js.index("=") + 1 :].rstrip().rstrip(";"))
    return {k: data[k] for k in ("world", "india", "states", "delhi", "borders", "cities", "attribution") if k in data}


def tile_from_frontend(out_dir: Path) -> dict:
    d = json.loads((out_dir / "frontend" / "auroraForecastPredictions.json").read_text(encoding="utf-8"))
    lats = sorted({c["latitude"] for c in d["steps"][0]["cells"]}, reverse=True)
    lons = sorted({c["longitude"] for c in d["steps"][0]["cells"]})
    aqi, wind, wdir = [], [], []
    for st in d["steps"]:
        m = {(c["latitude"], c["longitude"]): c for c in st["cells"]}
        aqi.append([int(round(m[(la, lo)]["aqi"])) for la in lats for lo in lons])
        wind.append([round(m[(la, lo)]["windSpeed"] * 3.6, 1) for la in lats for lo in lons])
        wdir.append([int(round(m[(la, lo)]["windDirection"])) for la in lats for lo in lons])
    return {"times": [st["timestamp"] for st in d["steps"]], "lats": lats, "lons": lons, "aqi": aqi, "wind": wind, "wdir": wdir}


def site_series(out_dir: Path) -> dict:
    f = pd.read_csv(out_dir / "fused_hourly.csv")
    sites = {}
    for s, g in f.groupby("site", sort=False):
        g = g.sort_values("time")
        sites[s] = {
            "aqi": g.aqi.round(0).astype(int).tolist(), "pm25": g.pm2p5.round(0).astype(int).tolist(),
            "blh": g.blh_m.round(0).astype(int).tolist(), "wind": (g.wind10_ms * 3.6).round(1).tolist(),
            "stag": g.stagnant.astype(int).tolist(),
        }  # fmt: skip
    summ = pd.read_csv(out_dir / "summary_by_site.csv")
    rows = [
        [r.site, int(round(r.aqi_now)), int(round(r.aqi_peak)), r.category_peak, {"pm2p5": "PM2.5", "pm10": "PM10"}.get(r.dominant, r.dominant),
         int(r.grap_stage), int(r.stagnant_hours), int(r.stagnant_night_hours), int(round(r.min_blh_m)), str(r.peak_time_ist)[:16]]
        for r in summ.itertuples()
    ]  # fmt: skip
    return {"sites": sites, "summary": rows}


def ensemble(out_dir: Path) -> dict | None:
    p = out_dir / "ensemble_stagnation_sites.csv"
    if not p.exists():
        return None
    e = pd.read_csv(p)
    z = np.load(out_dir / "ensemble_stagnation_tile.npz")
    per_site = {}
    for s, g in e.groupby("site", sort=False):
        g = g.sort_values("time")
        per_site[s] = {"p": g.p_stagnant.round(2).tolist(), "blh_p10": g.blh_p10.round(0).astype(int).tolist(),
                       "blh_p50": g.blh_p50.round(0).astype(int).tolist(), "blh_p90": g.blh_p90.round(0).astype(int).tolist()}  # fmt: skip
    return {"members": int(e["members"].iloc[0]), "sites": per_site, "p_cell": np.round(z["p"], 2).reshape(z["p"].shape[0], -1).tolist()}


def bias(out_dir: Path) -> list | None:
    p = out_dir / "bias_correction.csv"
    if not p.exists():
        return None
    b = pd.read_csv(p)
    return [[r.site, round(r.a, 1), round(r.b, 2), int(r.n), round(r.rmse_before, 1), round(r.rmse_after, 1)] for r in b.itertuples()]


def delivery(out_dir: Path) -> dict | None:
    p = out_dir / "delivery_log.json"
    if not p.exists():
        return None
    d = json.loads(p.read_text(encoding="utf-8"))
    return {"count": d["count"], "channel": d["channel"], "langs": sorted({i["lang"] for i in d["items"]}),
            "sample": [{k: i[k] for k in ("subscriber", "pincode", "site", "lang", "status", "chars", "payload")} for i in d["items"][:3]]}  # fmt: skip


def finetune(log: Path | None) -> dict:
    if log is None or not log.exists():
        return {"status": "not_run", "detail": ""}
    txt = log.read_text(encoding="utf-8", errors="replace")
    m = re.search(r"(\d+) passed.*?in ([\d.]+)s", txt)
    if m:
        loss = re.findall(r"(train_loss|val_loss)[=:\s]+([\d.eE+-]+)", txt)
        return {"status": "passed", "detail": f"{m.group(1)} test(s) passed in {float(m.group(2)):.0f} s", "loss": loss[-4:]}
    if "failed" in txt or "Error" in txt:
        tail = "\n".join(txt.strip().splitlines()[-3:])
        return {"status": "failed", "detail": tail[:400]}
    return {"status": "running", "detail": ""}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[2])
    ap.add_argument("out_dir", type=Path)
    ap.add_argument("--existing", type=Path, default=HERE / "storymap_data.js")
    ap.add_argument("--target", type=Path, default=HERE / "storymap_data.js")
    ap.add_argument("--finetune-log", type=Path, default=None)
    a = ap.parse_args()

    data = load_existing_geometry(a.existing)
    data.update(tile_from_frontend(a.out_dir))
    data.update(site_series(a.out_dir))
    data["ensemble"] = ensemble(a.out_dir)
    data["bias"] = bias(a.out_dir)
    data["delivery"] = delivery(a.out_dir)
    cron = a.out_dir / "run_delhi_aq_cron.sh"
    data["cron"] = cron.read_text(encoding="utf-8") if cron.exists() else ""
    prov = a.out_dir / "provenance.json"
    data["provenance"] = json.loads(prov.read_text(encoding="utf-8")) if prov.exists() else {}
    data["finetune"] = finetune(a.finetune_log)
    msgs = {}
    for lang in ("ko", "en", "hi"):
        p = a.out_dir / f"messages_{lang}.json"
        if p.exists():
            m = json.loads(p.read_text(encoding="utf-8"))
            worst = max(m["sites"], key=lambda x: x["aqi_peak"])
            msgs[lang] = {"city": m["city"], "short": worst["short"], "long": worst["long"], "site": worst["site"]}
    data["messages"] = msgs
    a.target.write_text("window.SM_DATA=" + json.dumps(data, separators=(",", ":"), ensure_ascii=False) + ";", encoding="utf-8")
    print(f"wrote {a.target} ({a.target.stat().st_size // 1024} KB); provenance={data['provenance']}")


if __name__ == "__main__":
    main()
