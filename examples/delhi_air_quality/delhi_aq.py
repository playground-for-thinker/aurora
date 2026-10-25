"""Copyright (c) Microsoft Corporation. Licensed under the MIT license.

Delhi air-quality early-warning example built on Aurora.

This module chains two Aurora models into one citizen-facing product:

* ``AuroraAirPollution`` (0.4 deg, 12-hourly) forecasts pollutant concentrations (PM2.5, PM10,
  NO2, SO2, O3, CO) from CAMS analysis.
* ``AuroraV1p5`` (0.25 deg, hourly via ``fine_lead_times``) forecasts the meteorology that controls
  dispersion over Delhi: boundary-layer height, 10 m wind, temperature, humidity, precipitation.

Both models can run locally on a GPU or on Azure AI Foundry through ``aurora.foundry.submit``.
The forecasts are interpolated to a set of Delhi-NCR locations, converted to the Indian national
AQI (CPCB) and GRAP stage, combined with hourly "stagnation" diagnostics, and turned into
Korean / English / Hindi alert messages.

Run ``python delhi_aq.py --mode demo`` to exercise the full downstream pipeline on synthetic data
without downloading anything, or ``--mode local`` / ``--mode foundry`` for real forecasts.
See ``STORYBOARD_kor.md`` and ``README_kor.md`` next to this file.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import logging
import math
import os
import pickle
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Literal, Optional, Sequence

import numpy as np
import pandas as pd
import torch

from aurora import Batch, Metadata

logger = logging.getLogger("delhi_aq")

Backend = Literal["local", "foundry"]

# ----------------------------------------------------------------------------------------------
# Configuration
# ----------------------------------------------------------------------------------------------

IST = timezone(timedelta(hours=5, minutes=30))
"""Indian Standard Time."""

LEVELS: tuple[int, ...] = (50, 100, 150, 200, 250, 300, 400, 500, 600, 700, 850, 925, 1000)
"""Pressure levels (hPa) required by all Aurora variants used here."""


@dataclasses.dataclass(frozen=True)
class Site:
    """A reporting location in Delhi-NCR.

    Coordinates are approximate and chosen to be close to well-known CPCB/DPCC monitoring
    stations so that forecasts can later be validated against observations.
    """

    name: str
    lat: float
    lon: float
    kind: str  # "traffic", "residential", "industrial", "background"


DELHI_SITES: tuple[Site, ...] = (
    Site("Anand Vihar", 28.647, 77.316, "traffic"),
    Site("ITO", 28.629, 77.241, "traffic"),
    Site("Punjabi Bagh", 28.674, 77.131, "residential"),
    Site("Rohini", 28.733, 77.120, "residential"),
    Site("Jahangirpuri", 28.733, 77.171, "industrial"),
    Site("R K Puram", 28.563, 77.187, "residential"),
    Site("Dwarka Sector 8", 28.571, 77.072, "residential"),
    Site("Okhla Phase 2", 28.531, 77.271, "industrial"),
    Site("Noida Sector 62", 28.625, 77.358, "residential"),
    Site("Gurugram Vikas Sadan", 28.450, 77.026, "traffic"),
)

DELHI_BBOX: tuple[float, float, float, float] = (28.3, 29.0, 76.7, 77.6)
"""(lat_min, lat_max, lon_min, lon_max) used for map plots."""

# CAMS NetCDF short name -> Aurora name (Aurora 0.4 Air Pollution).
AP_SURF_MAP: dict[str, str] = {
    "t2m": "2t",
    "u10": "10u",
    "v10": "10v",
    "msl": "msl",
    "pm1": "pm1",
    "pm2p5": "pm2p5",
    "pm10": "pm10",
    "tcco": "tcco",
    "tc_no": "tc_no",
    "tcno2": "tcno2",
    "gtco3": "gtco3",
    "tcso2": "tcso2",
}
AP_ATMOS_MAP: dict[str, str] = {
    "t": "t",
    "u": "u",
    "v": "v",
    "q": "q",
    "z": "z",
    "co": "co",
    "no": "no",
    "no2": "no2",
    "go3": "go3",
    "so2": "so2",
}

# CDS (ERA5 / HRES) NetCDF short name -> Aurora name (Aurora 1.5).
V15_SURF_MAP: dict[str, str] = {
    "t2m": "2t",
    "u10": "10u",
    "v10": "10v",
    "msl": "msl",
    "d2m": "2d",
    "tcwv": "tcwv",
    "tcc": "tcc",
    "u100": "100u",
    "v100": "100v",
    "sp": "sp",
    "lcc": "lcc",
    "mcc": "mcc",
    "hcc": "hcc",
    "skt": "skt",
    "stl1": "stl1",
    "swvl1": "swvl1",
    "siconc": "ci",
    "sd": "scaled_sd",
}
V15_ATMOS_MAP: dict[str, str] = {"t": "t", "u": "u", "v": "v", "q": "q", "z": "z"}

V15_MET_OUTPUTS: tuple[str, ...] = (
    ("2t", "2d", "10u", "10v", "msl", "sp", "blh", "i10fg", "scaled_tp_1h")
)
"""Aurora 1.5 surface outputs we keep for dispersion diagnostics and the map export."""

FRONTEND_BBOX: tuple[float, float, float, float] = (27.5, 31.5, 76.0, 80.0)
"""(lat_min, lat_max, lon_min, lon_max) of the map tile exported for the msresearch-aurora
frontend. 4 deg x 4 deg = 16 x 16 cells at 0.25 deg, matching `setup_region.py`'s grid rule."""

# ----------------------------------------------------------------------------------------------
# Indian national AQI (CPCB, 2014) and GRAP stages
# ----------------------------------------------------------------------------------------------

# Breakpoints: (conc_lo, conc_hi, index_lo, index_hi). Units: PM2.5/PM10/NO2/SO2/O3 in ug/m3,
# CO in mg/m3. The last segment is open-ended and extrapolated linearly.
CPCB_BREAKPOINTS: dict[str, list[tuple[float, float, int, int]]] = {
    "pm2p5": [(0, 30, 0, 50), (30, 60, 51, 100), (60, 90, 101, 200), (90, 120, 201, 300),
              (120, 250, 301, 400), (250, 380, 401, 500)],
    "pm10": [(0, 50, 0, 50), (50, 100, 51, 100), (100, 250, 101, 200), (250, 350, 201, 300),
             (350, 430, 301, 400), (430, 510, 401, 500)],
    "no2": [(0, 40, 0, 50), (40, 80, 51, 100), (80, 180, 101, 200), (180, 280, 201, 300),
            (280, 400, 301, 400), (400, 520, 401, 500)],
    "so2": [(0, 40, 0, 50), (40, 80, 51, 100), (80, 380, 101, 200), (380, 800, 201, 300),
            (800, 1600, 301, 400), (1600, 2400, 401, 500)],
    "o3": [(0, 50, 0, 50), (50, 100, 51, 100), (100, 168, 101, 200), (168, 208, 201, 300),
           (208, 748, 301, 400), (748, 1288, 401, 500)],
    "co": [(0, 1, 0, 50), (1, 2, 51, 100), (2, 10, 101, 200), (10, 17, 201, 300),
           (17, 34, 301, 400), (34, 51, 401, 500)],
}  # fmt: skip

AQI_CATEGORIES: tuple[tuple[int, int, str], ...] = (
    (0, 50, "Good"),
    (51, 100, "Satisfactory"),
    (101, 200, "Moderate"),
    (201, 300, "Poor"),
    (301, 400, "Very Poor"),
    (401, 10_000, "Severe"),
)

POLLUTANT_LABELS: dict[str, str] = {
    "pm2p5": "PM2.5",
    "pm10": "PM10",
    "no2": "NO2",
    "so2": "SO2",
    "o3": "O3",
    "co": "CO",
}


def cpcb_sub_index_array(pollutant: str, conc: np.ndarray) -> np.ndarray:
    """Vectorised CPCB sub-index. Values beyond the last breakpoint are capped at 500 ("500+")."""
    segments = CPCB_BREAKPOINTS[pollutant]
    xp = [segments[0][0]] + [seg[1] for seg in segments]
    fp = [segments[0][2]] + [seg[3] for seg in segments]
    conc = np.asarray(conc, dtype=np.float64)
    out = np.interp(np.clip(conc, 0, None), xp, fp)
    return np.where(np.isfinite(conc), out, np.nan)


def cpcb_sub_index(pollutant: str, conc: float) -> float:
    """Compute the CPCB sub-index for one pollutant concentration."""
    if conc is None or not np.isfinite(conc) or conc < 0:
        return float("nan")
    return float(cpcb_sub_index_array(pollutant, np.array([conc]))[0])


def cpcb_aqi(concs: dict[str, float]) -> tuple[float, str]:
    """Compute the overall CPCB AQI and the dominant pollutant.

    CPCB requires at least three pollutants, one of which must be PM2.5 or PM10. We relax this to
    "whatever is available" but always include PM when present.
    """
    subs = {p: cpcb_sub_index(p, c) for p, c in concs.items() if p in CPCB_BREAKPOINTS}
    subs = {p: s for p, s in subs.items() if np.isfinite(s)}
    if not subs:
        return float("nan"), ""
    dominant = max(subs, key=subs.get)  # type: ignore[arg-type]
    return float(subs[dominant]), dominant


def aqi_category(aqi: float) -> str:
    if not np.isfinite(aqi):
        return "Unknown"
    for lo, hi, name in AQI_CATEGORIES:
        if lo <= round(aqi) <= hi:
            return name
    return "Severe"


def grap_stage(aqi: float) -> int:
    """Graded Response Action Plan stage for Delhi-NCR (0 = no stage)."""
    if not np.isfinite(aqi) or aqi <= 200:
        return 0
    if aqi <= 300:
        return 1  # Poor
    if aqi <= 400:
        return 2  # Very Poor
    if aqi <= 450:
        return 3  # Severe
    return 4  # Severe+


# ----------------------------------------------------------------------------------------------
# Dispersion diagnostics
# ----------------------------------------------------------------------------------------------

STAGNANT_WIND_MS = 10 / 3.6
"""Wind speed below which dispersion is considered poor (10 km/h, as used in GRAP forecasts)."""

STAGNANT_BLH_M = 500.0
"""Boundary-layer height below which dispersion is considered poor."""


def ventilation_coefficient(blh_m: float, wind_ms: float) -> float:
    """Ventilation coefficient in m^2/s: boundary-layer height times wind speed."""
    return blh_m * wind_ms


def is_stagnant(blh_m: float, wind_ms: float) -> bool:
    return bool(blh_m < STAGNANT_BLH_M and wind_ms < STAGNANT_WIND_MS)


def relative_humidity(t_k: np.ndarray, td_k: np.ndarray) -> np.ndarray:
    """Relative humidity in percent from temperature and dew point (Magnus formula)."""
    t = t_k - 273.15
    td = td_k - 273.15
    e = 6.112 * np.exp(17.62 * td / (243.12 + td))
    es = 6.112 * np.exp(17.62 * t / (243.12 + t))
    return np.clip(100 * e / es, 0, 100)


# ----------------------------------------------------------------------------------------------
# Data download
# ----------------------------------------------------------------------------------------------


def _cds_client(url: str, key_env: str):
    import cdsapi  # Optional dependency.

    key = os.environ.get(key_env)
    if key:
        return cdsapi.Client(url=url, key=key)
    # Fall back to ~/.cdsapirc. Beware: ADS and CDS need different URLs in that file.
    return cdsapi.Client()


def download_cams(date: datetime, out_dir: Path) -> tuple[Path, Path]:
    """Download CAMS global analysis (0.4 deg) for 00 and 12 UTC of `date`.

    Requires an Atmosphere Data Store account. Set `ADS_API_KEY` or configure `~/.cdsapirc`
    with `url: https://ads.atmosphere.copernicus.eu/api`.

    Returns:
        Paths to the surface-level and pressure-level NetCDF files.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = date.strftime("%Y-%m-%d") + "-cams"
    surf_path = out_dir / f"{stem}-surface-level.nc"
    atmos_path = out_dir / f"{stem}-atmospheric.nc"
    if surf_path.exists() and atmos_path.exists():
        return surf_path, atmos_path

    zip_path = out_dir / f"{stem}.nc.zip"
    if not zip_path.exists():
        c = _cds_client("https://ads.atmosphere.copernicus.eu/api", "ADS_API_KEY")
        c.retrieve(
            "cams-global-atmospheric-composition-forecasts",
            {
                "type": "forecast",
                "leadtime_hour": "0",
                "variable": [
                    "10m_u_component_of_wind",
                    "10m_v_component_of_wind",
                    "2m_temperature",
                    "mean_sea_level_pressure",
                    "particulate_matter_1um",
                    "particulate_matter_2.5um",
                    "particulate_matter_10um",
                    "total_column_carbon_monoxide",
                    "total_column_nitrogen_monoxide",
                    "total_column_nitrogen_dioxide",
                    "total_column_ozone",
                    "total_column_sulphur_dioxide",
                    "u_component_of_wind",
                    "v_component_of_wind",
                    "temperature",
                    "geopotential",
                    "specific_humidity",
                    "carbon_monoxide",
                    "nitrogen_dioxide",
                    "nitrogen_monoxide",
                    "ozone",
                    "sulphur_dioxide",
                ],
                "pressure_level": [str(p) for p in LEVELS],
                "date": date.strftime("%Y-%m-%d"),
                "time": ["00:00", "12:00"],
                "format": "netcdf_zip",
            },
            str(zip_path),
        )

    import xarray as xr

    with zipfile.ZipFile(zip_path) as zf:
        members = zf.namelist()
        zf.extractall(out_dir / f"{stem}-unzipped")
    for member in members:
        p = out_dir / f"{stem}-unzipped" / member
        with xr.open_dataset(p, engine="netcdf4") as ds:
            is_plev = "pressure_level" in ds.dims or "level" in ds.dims
        p.rename(atmos_path if is_plev else surf_path)
    return surf_path, atmos_path


def download_era5_for_v15(date: datetime, out_dir: Path) -> tuple[Path, Path]:
    """Download ERA5 (0.25 deg) at 06 and 12 UTC of `date` with the Aurora 1.5 input set.

    Aurora 1.5 was fine-tuned on IFS HRES T0; ERA5 is used here for convenience, as in the
    official Aurora 1.5 example, so accuracy is not guaranteed. Requires a Climate Data Store
    account. Set `CDS_API_KEY` or configure `~/.cdsapirc` with
    `url: https://cds.climate.copernicus.eu/api`.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = date.strftime("%Y-%m-%d") + "-era5"
    surf_path = out_dir / f"{stem}-surface-level.nc"
    atmos_path = out_dir / f"{stem}-atmospheric.nc"
    ymd = {"year": date.strftime("%Y"), "month": date.strftime("%m"), "day": date.strftime("%d")}
    times = ["06:00", "12:00"]

    if not surf_path.exists():
        c = _cds_client("https://cds.climate.copernicus.eu/api", "CDS_API_KEY")
        c.retrieve(
            "reanalysis-era5-single-levels",
            {
                "product_type": "reanalysis",
                "variable": [
                    "2m_temperature",
                    "10m_u_component_of_wind",
                    "10m_v_component_of_wind",
                    "mean_sea_level_pressure",
                    "2m_dewpoint_temperature",
                    "total_column_water_vapour",
                    "total_cloud_cover",
                    "100m_u_component_of_wind",
                    "100m_v_component_of_wind",
                    "surface_pressure",
                    "low_cloud_cover",
                    "medium_cloud_cover",
                    "high_cloud_cover",
                    "skin_temperature",
                    "soil_temperature_level_1",
                    "volumetric_soil_water_layer_1",
                    "sea_ice_cover",
                    "snow_depth",
                ],
                **ymd,
                "time": times,
                "data_format": "netcdf",
            },
            str(surf_path),
        )
    if not atmos_path.exists():
        c = _cds_client("https://cds.climate.copernicus.eu/api", "CDS_API_KEY")
        c.retrieve(
            "reanalysis-era5-pressure-levels",
            {
                "product_type": "reanalysis",
                "variable": [
                    "temperature",
                    "u_component_of_wind",
                    "v_component_of_wind",
                    "specific_humidity",
                    "geopotential",
                ],
                "pressure_level": [str(p) for p in LEVELS],
                **ymd,
                "time": times,
                "data_format": "netcdf",
            },
            str(atmos_path),
        )
    return surf_path, atmos_path


def load_static(filename: str) -> dict[str, torch.Tensor]:
    """Load one of the static-variable pickles from the `microsoft/aurora` HuggingFace repo."""
    from huggingface_hub import hf_hub_download

    path = hf_hub_download(repo_id="microsoft/aurora", filename=filename)
    with open(path, "rb") as f:
        raw = pickle.load(f)
    return {k: torch.from_numpy(np.asarray(v, dtype=np.float32)) for k, v in raw.items()}


# ----------------------------------------------------------------------------------------------
# Batch construction
# ----------------------------------------------------------------------------------------------


def _open_global(path: Path):
    """Open a NetCDF file and make longitude conform to Aurora's [0, 360) increasing grid."""
    import xarray as xr

    ds = xr.open_dataset(path, engine="netcdf4", decode_timedelta=True)
    if "forecast_period" in ds.dims:  # CAMS forecast files.
        ds = ds.isel(forecast_period=0)
    if "level" in ds.dims and "pressure_level" not in ds.dims:
        ds = ds.rename({"level": "pressure_level"})
    lon = ds["longitude"].values
    if lon.min() < 0:
        ds = ds.assign_coords(longitude=(lon % 360)).sortby("longitude")
    return ds


def _time_dim(ds) -> str:
    for name in ("valid_time", "time", "forecast_reference_time"):
        if name in ds.dims:
            return name
    raise KeyError(f"No time dimension in {list(ds.dims)}")


def _stack_times(ds, name: str, n_hist: int = 2) -> np.ndarray:
    """Take the last `n_hist` time steps of variable `name`, as float32 with a batch dim."""
    tdim = _time_dim(ds)
    data = ds[name].isel({tdim: slice(-n_hist, None)}).values
    return np.nan_to_num(data, nan=0.0).astype(np.float32)[None]


def build_air_pollution_batch(
    surf_nc: Path, atmos_nc: Path, static_vars: dict[str, torch.Tensor]
) -> Batch:
    """Build the Aurora 0.4 Air Pollution input batch from CAMS files with 00 and 12 UTC."""
    surf = _open_global(surf_nc)
    atmos = _open_global(atmos_nc)
    tdim = _time_dim(surf)
    times = pd.to_datetime(surf[tdim].values[-2:]).to_pydatetime()

    surf_vars = {a: torch.from_numpy(_stack_times(surf, c)) for c, a in AP_SURF_MAP.items()}
    atmos_vars = {}
    for c, a in AP_ATMOS_MAP.items():
        arr = atmos[c].sel(pressure_level=list(LEVELS))
        atmos_vars[a] = torch.from_numpy(
            np.nan_to_num(arr.isel({_time_dim(atmos): slice(-2, None)}).values, nan=0.0)
            .astype(np.float32)[None]
        )
    return Batch(
        surf_vars=surf_vars,
        static_vars=static_vars,
        atmos_vars=atmos_vars,
        metadata=Metadata(
            lat=torch.from_numpy(surf["latitude"].values.astype(np.float32)),
            lon=torch.from_numpy(surf["longitude"].values.astype(np.float32)),
            time=(times[-1].replace(tzinfo=None),),
            atmos_levels=LEVELS,
        ),
    )


def build_v15_batch(surf_nc: Path, atmos_nc: Path, static_vars: dict[str, torch.Tensor]) -> Batch:
    """Build the Aurora 1.5 input batch from ERA5/HRES files with 06 and 12 UTC."""
    from aurora.insolation import insolation

    surf = _open_global(surf_nc)
    atmos = _open_global(atmos_nc)
    tdim = _time_dim(surf)
    times = [t.replace(tzinfo=None) for t in pd.to_datetime(surf[tdim].values[-2:]).to_pydatetime()]

    surf_vars = {a: torch.from_numpy(_stack_times(surf, c)) for c, a in V15_SURF_MAP.items()}

    lat = surf["latitude"].values.astype(np.float32)
    lon = surf["longitude"].values.astype(np.float32)
    sol = np.stack([insolation([t], lat, lon, enforce_2d=True)[0] for t in times], axis=0)
    surf_vars["insolation"] = torch.from_numpy(sol[None].astype(np.float32))

    atmos_vars = {}
    for c, a in V15_ATMOS_MAP.items():
        arr = atmos[c].sel(pressure_level=list(LEVELS))
        atmos_vars[a] = torch.from_numpy(
            np.nan_to_num(arr.isel({_time_dim(atmos): slice(-2, None)}).values, nan=0.0)
            .astype(np.float32)[None]
        )
    return Batch(
        surf_vars=surf_vars,
        static_vars=static_vars,
        atmos_vars=atmos_vars,
        metadata=Metadata(
            lat=torch.from_numpy(lat),
            lon=torch.from_numpy(lon),
            time=(times[-1],),
            atmos_levels=LEVELS,
        ),
    )


# ----------------------------------------------------------------------------------------------
# Running the models (locally or on Azure AI Foundry)
# ----------------------------------------------------------------------------------------------


def _foundry_submit(batch: Batch, model_name: str, num_steps: int, suffix: str, **kw) -> list[Batch]:
    """Submit to Azure AI Foundry.

    The "Aurora" and "Aurora-1.5" Foundry models are separate endpoints. Set
    `FOUNDRY_ENDPOINT_<suffix>` / `FOUNDRY_TOKEN_<suffix>` (suffix `AP` or `V15`), falling back
    to `FOUNDRY_ENDPOINT` / `FOUNDRY_TOKEN`. `BLOB_URL_WITH_SAS` must point to a blob folder with
    a read+write SAS token.
    """
    from aurora.foundry import BlobStorageChannel, FoundryClient, submit

    endpoint = os.environ.get(f"FOUNDRY_ENDPOINT_{suffix}") or os.environ["FOUNDRY_ENDPOINT"]
    token = os.environ.get(f"FOUNDRY_TOKEN_{suffix}") or os.environ["FOUNDRY_TOKEN"]
    client = FoundryClient(endpoint=endpoint, token=token)
    channel = BlobStorageChannel(os.environ["BLOB_URL_WITH_SAS"])
    return list(
        submit(
            batch,
            model_name=model_name,
            num_steps=num_steps,
            channel=channel,
            foundry_client=client,
            **kw,
        )
    )


def run_air_pollution(
    batch: Batch, steps: int, backend: Backend = "local", device: str = "cuda"
) -> list[Batch]:
    """Roll out Aurora 0.4 Air Pollution for `steps` 12-hour steps."""
    if backend == "foundry":
        return _foundry_submit(batch, "aurora-0.4-air-pollution", steps, "AP")

    from aurora import AuroraAirPollution, rollout

    model = AuroraAirPollution()
    model.load_checkpoint()
    model.eval()
    model = model.to(device)
    with torch.inference_mode():
        preds = [p.to("cpu") for p in rollout(model, batch, steps=steps)]
    del model
    if device.startswith("cuda"):
        torch.cuda.empty_cache()
    return preds


def slim_v15_prediction(pred: Batch) -> Batch:
    """Keep only the surface outputs needed downstream and move them to the CPU.

    A full 0.25 deg Aurora 1.5 prediction is several hundred MB; 48 hourly predictions would not
    fit in host memory. `Batch` requires at least one atmospheric variable, so we keep a single
    level of temperature as a placeholder.
    """
    lvl = list(pred.metadata.atmos_levels).index(1000) if 1000 in pred.metadata.atmos_levels else -1
    return dataclasses.replace(
        pred,
        surf_vars={k: v.cpu() for k, v in pred.surf_vars.items() if k in V15_MET_OUTPUTS},
        atmos_vars={"t": pred.atmos_vars["t"][:, :, lvl : lvl + 1].cpu()},
        static_vars={},
        metadata=dataclasses.replace(
            pred.metadata, atmos_levels=(pred.metadata.atmos_levels[lvl],)
        ),
    )


def run_v15(
    batch: Batch,
    steps: int,
    fine_lead_times: Sequence[float] = (1.0, 2.0, 3.0, 4.0, 5.0, 6.0),
    backend: Backend = "local",
    device: str = "cuda",
) -> list[Batch]:
    """Roll out Aurora 1.5 for `steps` 6-hour steps with hourly sub-steps."""
    if backend == "foundry":
        return _foundry_submit(
            batch,
            "aurora-0.25-v1.5",
            steps,
            "V15",
            fine_lead_times=list(fine_lead_times),
            saved_surf_vars=V15_MET_OUTPUTS,
            saved_atmos_vars=(),
            saved_static_vars=(),
            async_upload_workers=4,
        )

    from aurora import AuroraV1p5, rollout

    model = AuroraV1p5()
    model.load_checkpoint()
    model.eval()
    model = model.to(device)
    preds = []
    with torch.inference_mode():
        for p in rollout(model, batch, steps=steps, fine_lead_times=list(fine_lead_times)):
            preds.append(slim_v15_prediction(p))
    del model
    if device.startswith("cuda"):
        torch.cuda.empty_cache()
    return preds


# ----------------------------------------------------------------------------------------------
# Extraction at Delhi sites
# ----------------------------------------------------------------------------------------------


def sample_points(
    field: np.ndarray, lat: np.ndarray, lon: np.ndarray, sites: Sequence[Site]
) -> np.ndarray:
    """Bilinearly interpolate a global `(H, W)` field to the site locations."""
    from scipy.interpolate import RegularGridInterpolator

    # Aurora grids have decreasing latitude; RegularGridInterpolator wants ascending axes.
    rgi = RegularGridInterpolator(
        (lat[::-1], lon), np.asarray(field, dtype=np.float64)[::-1], bounds_error=False
    )
    pts = np.array([(s.lat, s.lon % 360) for s in sites])
    return rgi(pts)


R_DRY_AIR = 287.05  # J kg^-1 K^-1


def extract_pollutants(
    batches: Sequence[Batch], sites: Sequence[Site] = DELHI_SITES
) -> pd.DataFrame:
    """Extract pollutant concentrations at `sites` from Air Pollution batches.

    The last history index is used, so this works for the input batch (analysis at t0) and for
    predictions alike. Particulate matter is a surface mass concentration (kg/m^3 -> ug/m^3).
    Gases are mass mixing ratios at 1000 hPa converted to ug/m^3 (CO: mg/m^3) with the ideal-gas
    density at that level. Delhi (~216 m) lies slightly above the 1000 hPa surface, so these gas
    values are an approximation of near-surface air.
    """
    rows = []
    for b in batches:
        lat = b.metadata.lat.numpy()
        lon = b.metadata.lon.numpy()
        t = b.metadata.time[0]
        lvl = list(b.metadata.atmos_levels).index(1000)
        t_1000 = sample_points(b.atmos_vars["t"][0, -1, lvl].numpy(), lat, lon, sites)
        rho = 100_000.0 / (R_DRY_AIR * t_1000)  # kg/m^3

        vals = {
            "pm2p5": sample_points(b.surf_vars["pm2p5"][0, -1].numpy(), lat, lon, sites) * 1e9,
            "pm10": sample_points(b.surf_vars["pm10"][0, -1].numpy(), lat, lon, sites) * 1e9,
        }
        for gas, key, scale in (("no2", "no2", 1e9), ("so2", "so2", 1e9), ("o3", "go3", 1e9),
                                ("co", "co", 1e6)):  # fmt: skip
            mmr = sample_points(b.atmos_vars[key][0, -1, lvl].numpy(), lat, lon, sites)
            vals[gas] = mmr * rho * scale
        for i, s in enumerate(sites):
            rows.append({"time": t, "site": s.name, **{k: float(v[i]) for k, v in vals.items()}})
    df = pd.DataFrame(rows)
    df["time"] = pd.to_datetime(df["time"])
    return df.sort_values(["site", "time"]).reset_index(drop=True)


def extract_meteorology(
    batches: Sequence[Batch], sites: Sequence[Site] = DELHI_SITES
) -> pd.DataFrame:
    """Extract hourly dispersion meteorology at `sites` from Aurora 1.5 predictions."""
    rows = []
    for b in batches:
        lat = b.metadata.lat.numpy()
        lon = b.metadata.lon.numpy()
        t = b.metadata.time[0]

        def pick(name: str) -> np.ndarray:
            return sample_points(b.surf_vars[name][0, -1].numpy(), lat, lon, sites)

        u, v = pick("10u"), pick("10v")
        t2m, d2m = pick("2t"), pick("2d")
        blh = pick("blh") if "blh" in b.surf_vars else np.full(len(sites), np.nan)
        gust = pick("i10fg") if "i10fg" in b.surf_vars else np.full(len(sites), np.nan)
        tp = pick("scaled_tp_1h") if "scaled_tp_1h" in b.surf_vars else np.zeros(len(sites))
        rh = relative_humidity(t2m, d2m)
        for i, s in enumerate(sites):
            rows.append(
                {
                    "time": t,
                    "site": s.name,
                    "wind10_ms": float(math.hypot(u[i], v[i])),
                    "gust_ms": float(gust[i]),
                    "blh_m": float(max(blh[i], 0.0)),
                    "t2m_c": float(t2m[i] - 273.15),
                    "rh_pct": float(rh[i]),
                    # Precipitation is assumed to be in metres per hour as in ERA5.
                    "tp_1h_mm": float(max(tp[i], 0.0) * 1000.0),
                }
            )
    df = pd.DataFrame(rows)
    df["time"] = pd.to_datetime(df["time"])
    return df.sort_values(["site", "time"]).reset_index(drop=True)


# ----------------------------------------------------------------------------------------------
# Fusion: hourly AQI + dispersion per site
# ----------------------------------------------------------------------------------------------


def fuse(pollutants: pd.DataFrame, met: pd.DataFrame) -> pd.DataFrame:
    """Interpolate 12-hourly pollutant forecasts onto the hourly meteorology and compute AQI.

    The hourly pollutant values are a *linear interpolation* of the 12-hourly Air Pollution model
    output and must be communicated as such; the hourly structure in the result comes from the
    Aurora 1.5 dispersion diagnostics (boundary-layer height, wind).
    """
    out = []
    for site, m in met.groupby("site", sort=False):
        p = pollutants[pollutants["site"] == site].set_index("time").sort_index()
        m = m.set_index("time").sort_index()
        idx = p.index.union(m.index)
        p_hourly = (
            p[list(POLLUTANT_LABELS)]
            .reindex(idx)
            .interpolate(method="time")
            .bfill()
            .ffill()
            .reindex(m.index)
        )
        f = m.join(p_hourly)
        aqi_dom = [cpcb_aqi(row[list(POLLUTANT_LABELS)].to_dict()) for _, row in f.iterrows()]
        f["aqi"] = [a for a, _ in aqi_dom]
        f["dominant"] = [d for _, d in aqi_dom]
        f["category"] = f["aqi"].map(aqi_category)
        f["grap_stage"] = f["aqi"].map(grap_stage)
        f["ventilation_m2s"] = f["blh_m"] * f["wind10_ms"]
        f["stagnant"] = [is_stagnant(b, w) for b, w in zip(f["blh_m"], f["wind10_ms"])]
        f["site"] = site
        out.append(f.reset_index().rename(columns={"index": "time"}))
    fused = pd.concat(out, ignore_index=True)
    fused["time_ist"] = fused["time"].dt.tz_localize("UTC").dt.tz_convert(IST)
    return fused


def summarise(fused: pd.DataFrame, sites: Sequence[Site] = DELHI_SITES) -> pd.DataFrame:
    """One row per site: peak AQI, dominant pollutant, stagnation hours, trend, GRAP stage."""
    kinds = {s.name: s.kind for s in sites}
    rows = []
    for site, f in fused.groupby("site", sort=False):
        f = f.sort_values("time")
        peak = f.loc[f["aqi"].idxmax()]
        n = len(f)
        first = f["pm2p5"].iloc[: max(1, n // 4)].mean()
        last = f["pm2p5"].iloc[-max(1, n // 4) :].mean()
        trend = "worsening" if last > first * 1.10 else "improving" if last < first * 0.90 else "steady"
        night = f[(f["time_ist"].dt.hour >= 22) | (f["time_ist"].dt.hour < 8)]
        rows.append(
            {
                "site": site,
                "kind": kinds.get(site, ""),
                "aqi_now": float(f["aqi"].iloc[0]),
                "aqi_peak": float(peak["aqi"]),
                "category_peak": aqi_category(float(peak["aqi"])),
                "peak_time_ist": peak["time_ist"],
                "dominant": peak["dominant"],
                "pm2p5_peak": float(f["pm2p5"].max()),
                "pm10_peak": float(f["pm10"].max()),
                "grap_stage": int(grap_stage(float(peak["aqi"]))),
                "stagnant_hours": int(f["stagnant"].sum()),
                "stagnant_night_hours": int(night["stagnant"].sum()),
                "min_blh_m": float(f["blh_m"].min()),
                "mean_wind_ms": float(f["wind10_ms"].mean()),
                "rain_mm": float(f["tp_1h_mm"].sum()),
                "trend": trend,
                "horizon_start_ist": f["time_ist"].iloc[0],
                "horizon_end_ist": f["time_ist"].iloc[-1],
            }
        )
    return pd.DataFrame(rows)


# ----------------------------------------------------------------------------------------------
# Messaging (ko / en / hi)
# ----------------------------------------------------------------------------------------------

Lang = Literal["ko", "en", "hi"]

CATEGORY_NAMES: dict[str, dict[str, str]] = {
    "ko": {"Good": "좋음", "Satisfactory": "양호", "Moderate": "보통", "Poor": "나쁨",
           "Very Poor": "매우 나쁨", "Severe": "위험", "Unknown": "정보 없음"},
    "en": {k: k for k in ("Good", "Satisfactory", "Moderate", "Poor", "Very Poor", "Severe", "Unknown")},
    "hi": {"Good": "अच्छा", "Satisfactory": "संतोषजनक", "Moderate": "मध्यम", "Poor": "खराब",
           "Very Poor": "बहुत खराब", "Severe": "गंभीर", "Unknown": "जानकारी नहीं"},
}  # fmt: skip

TREND_NAMES: dict[str, dict[str, str]] = {
    "ko": {"worsening": "악화 추세", "improving": "개선 추세", "steady": "비슷한 수준 유지"},
    "en": {"worsening": "worsening", "improving": "improving", "steady": "roughly steady"},
    "hi": {"worsening": "बिगड़ने की संभावना", "improving": "सुधार की संभावना", "steady": "लगभग स्थिर"},
}  # fmt: skip

HEALTH_ADVICE: dict[str, dict[str, str]] = {
    "ko": {
        "Good": "야외 활동에 제약이 없습니다.",
        "Satisfactory": "민감한 분은 가벼운 호흡 불편을 느낄 수 있습니다.",
        "Moderate": "어린이, 노인, 호흡기·심장 질환자는 장시간 격한 야외 활동을 줄이세요.",
        "Poor": "장시간 야외 활동 시 대부분이 호흡 불편을 느낍니다. 야외 운동을 줄이고 외출 시 N95 마스크를 쓰세요.",
        "Very Poor": "장시간 노출 시 호흡기 질환 위험이 커집니다. 야외 운동을 피하고, 창문을 닫고, 외출 시 N95 마스크를 쓰세요. 어린이·노인·임산부·호흡기 질환자는 실내에 머무르세요.",
        "Severe": "건강한 사람도 영향을 받습니다. 가능한 한 실내에 머무르고, 어린이·노인·호흡기·심장 질환자는 외출을 피하세요. 공기청정기를 사용하고 증상이 있으면 의료기관을 찾으세요.",
    },
    "en": {
        "Good": "No restrictions on outdoor activity.",
        "Satisfactory": "Sensitive people may feel minor breathing discomfort.",
        "Moderate": "Children, older adults and people with lung or heart disease should limit prolonged, intense outdoor exertion.",
        "Poor": "Most people feel breathing discomfort on prolonged exposure. Cut back on outdoor exercise and wear an N95 mask outdoors.",
        "Very Poor": "Prolonged exposure raises the risk of respiratory illness. Avoid outdoor exercise, keep windows closed and wear an N95 mask outdoors. Children, older adults, pregnant women and people with respiratory disease should stay indoors.",
        "Severe": "Even healthy people are affected. Stay indoors as much as possible; children, older adults and people with lung or heart disease should avoid going out. Use an air purifier and seek medical care if symptoms appear.",
    },
    "hi": {
        "Good": "बाहरी गतिविधियों पर कोई रोक नहीं।",
        "Satisfactory": "संवेदनशील लोगों को हल्की साँस की तकलीफ़ हो सकती है।",
        "Moderate": "बच्चे, बुज़ुर्ग और फेफड़े/हृदय रोगी लंबे समय तक बाहर कड़ी मेहनत न करें।",
        "Poor": "लंबे समय बाहर रहने पर अधिकतर लोगों को साँस में तकलीफ़। बाहर व्यायाम कम करें और N95 मास्क पहनें।",
        "Very Poor": "लंबे समय संपर्क से साँस की बीमारी का खतरा। बाहर व्यायाम न करें, खिड़कियाँ बंद रखें, बाहर N95 मास्क पहनें। बच्चे, बुज़ुर्ग, गर्भवती महिलाएँ और साँस के रोगी घर में रहें।",
        "Severe": "स्वस्थ लोग भी प्रभावित। जितना हो सके घर में रहें; बच्चे, बुज़ुर्ग और फेफड़े/हृदय रोगी बाहर न निकलें। एयर प्यूरीफ़ायर चलाएँ, लक्षण हों तो डॉक्टर से मिलें।",
    },
}  # fmt: skip

GRAP_ADVICE: dict[str, dict[int, str]] = {
    "ko": {
        0: "",
        1: "GRAP 1단계(나쁨) 수준: 쓰레기·낙엽 소각 금지, 건설현장 비산먼지 관리, 가능하면 대중교통·카풀을 이용하세요.",
        2: "GRAP 2단계(매우 나쁨) 수준: 디젤 발전기 사용 자제, 대중교통 이용 권고, 민감군 야외 활동 자제가 요청될 수 있습니다.",
        3: "GRAP 3단계(위험) 수준: 비필수 건설·철거 중단, 노후 경유·휘발유 차량 운행 제한, 초등학교 원격수업 전환 등이 시행될 수 있습니다.",
        4: "GRAP 4단계(위험+) 수준: 트럭 진입 제한, 재택근무 확대, 학교 원격수업 전환 등 강력한 조치가 시행될 수 있습니다. 당국 공지를 확인하세요.",
    },
    "en": {
        0: "",
        1: "GRAP Stage I (Poor) level: no open burning of waste or leaves, dust control at construction sites, prefer public transport or carpooling.",
        2: "GRAP Stage II (Very Poor) level: avoid diesel generators, use public transport, sensitive groups may be asked to limit outdoor activity.",
        3: "GRAP Stage III (Severe) level: non-essential construction and demolition may be halted, older diesel/petrol vehicles restricted, primary schools may move online.",
        4: "GRAP Stage IV (Severe+) level: truck entry restrictions, expanded work-from-home and online classes may be enforced. Follow official notices.",
    },
    "hi": {
        0: "",
        1: "GRAP चरण I (खराब): कचरा/पत्ते न जलाएँ, निर्माण स्थलों पर धूल नियंत्रण, सार्वजनिक परिवहन या कारपूल का उपयोग करें।",
        2: "GRAP चरण II (बहुत खराब): डीज़ल जनरेटर से बचें, सार्वजनिक परिवहन का उपयोग करें; संवेदनशील लोग बाहर कम निकलें।",
        3: "GRAP चरण III (गंभीर): गैर-ज़रूरी निर्माण/तोड़फोड़ रुक सकती है, पुराने डीज़ल/पेट्रोल वाहनों पर रोक, प्राथमिक स्कूल ऑनलाइन हो सकते हैं।",
        4: "GRAP चरण IV (गंभीर+): ट्रकों के प्रवेश पर रोक, घर से काम और ऑनलाइन कक्षाएँ लागू हो सकती हैं। आधिकारिक सूचनाएँ देखें।",
    },
}  # fmt: skip


def _fmt_ist(ts: pd.Timestamp, lang: str) -> str:
    if lang == "ko":
        return ts.strftime("%m월 %d일 %H시").replace("월 0", "월 ").lstrip("0")
    return ts.strftime("%d %b %H:%M IST")


def _stagnation_sentence(row: pd.Series, lang: str) -> str:
    h = int(row["stagnant_hours"])
    hn = int(row["stagnant_night_hours"])
    blh = int(round(row["min_blh_m"]))
    if h == 0:
        return {
            "ko": "바람과 혼합층 높이가 확산에 유리해 정체는 예상되지 않습니다.",
            "en": "Winds and mixing height favour dispersion; no stagnation expected.",
            "hi": "हवा और मिक्सिंग ऊँचाई अनुकूल; ठहराव की संभावना नहीं।",
        }[lang]
    return {
        "ko": f"향후 예측기간 중 {h}시간(야간·새벽 {hn}시간) 동안 풍속 10 km/h 미만, 혼합층 {STAGNANT_BLH_M:.0f} m 미만의 정체 조건이 예상됩니다(최저 혼합층 약 {blh} m). 밤~아침에 오염이 지표 근처에 쌓이기 쉽습니다.",
        "en": f"Stagnant conditions (wind below 10 km/h, mixing height below {STAGNANT_BLH_M:.0f} m) are expected for {h} h, {hn} h of them overnight (minimum mixing height about {blh} m). Pollution will tend to pool near the surface from night to morning.",
        "hi": f"{h} घंटे (रात/सुबह {hn} घंटे) हवा 10 किमी/घं से कम और मिक्सिंग ऊँचाई {STAGNANT_BLH_M:.0f} मी से कम रहने की संभावना (न्यूनतम लगभग {blh} मी)। रात से सुबह तक प्रदूषण ज़मीन के पास जमा होगा।",
    }[lang]


def build_messages(summary: pd.DataFrame, lang: Lang = "ko") -> list[dict]:
    """Turn the per-site summary into short (push/SMS) and long (bulletin) messages."""
    cat = CATEGORY_NAMES[lang]
    msgs = []
    for _, r in summary.iterrows():
        category = r["category_peak"]
        aqi = int(round(r["aqi_peak"]))
        peak = _fmt_ist(r["peak_time_ist"], lang)
        dom = POLLUTANT_LABELS.get(r["dominant"], r["dominant"])
        trend = TREND_NAMES[lang][r["trend"]]
        pm = int(round(r["pm2p5_peak"]))
        stage = int(r["grap_stage"])
        site = r["site"]

        if lang == "ko":
            short = (
                f"[대기질 경보] {site}: 최고 AQI {aqi} ({cat[category]}), {peak} 전후 정점 예상. "
                f"주 오염물질 {dom}, PM2.5 최대 {pm}㎍/㎥. {HEALTH_ADVICE[lang][category].split('.')[0]}."
            )
            long = "\n".join(
                [
                    f"■ {site} 대기질 예보 ({_fmt_ist(r['horizon_start_ist'], lang)} ~ {_fmt_ist(r['horizon_end_ist'], lang)})",
                    f"- 현재 AQI {int(round(r['aqi_now']))} → 최고 AQI {aqi} ({cat[category]}), 정점 {peak} 전후. 추세: {trend}.",
                    f"- 주 오염물질: {dom}. PM2.5 최대 {pm}㎍/㎥, PM10 최대 {int(round(r['pm10_peak']))}㎍/㎥.",
                    f"- 확산 조건: {_stagnation_sentence(r, lang)}",
                    f"- 건강 권고: {HEALTH_ADVICE[lang][category]}",
                ]
                + ([f"- 행정 조치 안내: {GRAP_ADVICE[lang][stage]}"] if stage else [])
                + ["- 이 예보는 AI 모델(Aurora) 기반 참고 정보이며, 공식 경보는 CPCB/CAQM 발표를 따르세요."]
            )
        elif lang == "en":
            short = (
                f"[Air quality alert] {site}: peak AQI {aqi} ({category}) expected around {peak}. "
                f"Main pollutant {dom}, PM2.5 up to {pm} ug/m3. {HEALTH_ADVICE[lang][category].split('.')[0]}."
            )
            long = "\n".join(
                [
                    f"■ {site} air-quality outlook ({_fmt_ist(r['horizon_start_ist'], lang)} to {_fmt_ist(r['horizon_end_ist'], lang)})",
                    f"- AQI now {int(round(r['aqi_now']))}, peaking at {aqi} ({category}) around {peak}. Trend: {trend}.",
                    f"- Main pollutant: {dom}. PM2.5 up to {pm} ug/m3, PM10 up to {int(round(r['pm10_peak']))} ug/m3.",
                    f"- Dispersion: {_stagnation_sentence(r, lang)}",
                    f"- Health advice: {HEALTH_ADVICE[lang][category]}",
                ]
                + ([f"- Measures: {GRAP_ADVICE[lang][stage]}"] if stage else [])
                + ["- This is AI-model (Aurora) guidance for information only; follow official CPCB/CAQM alerts."]
            )
        else:
            short = (
                f"[वायु गुणवत्ता चेतावनी] {site}: अधिकतम AQI {aqi} ({cat[category]}), {peak} के आसपास। "
                f"मुख्य प्रदूषक {dom}, PM2.5 अधिकतम {pm} µg/m³। {HEALTH_ADVICE[lang][category].split('।')[0]}।"
            )
            long = "\n".join(
                [
                    f"■ {site} वायु गुणवत्ता पूर्वानुमान ({_fmt_ist(r['horizon_start_ist'], lang)} से {_fmt_ist(r['horizon_end_ist'], lang)})",
                    f"- अभी AQI {int(round(r['aqi_now']))}, अधिकतम {aqi} ({cat[category]}) {peak} के आसपास। रुझान: {trend}।",
                    f"- मुख्य प्रदूषक: {dom}। PM2.5 अधिकतम {pm} µg/m³, PM10 अधिकतम {int(round(r['pm10_peak']))} µg/m³।",
                    f"- फैलाव: {_stagnation_sentence(r, lang)}",
                    f"- स्वास्थ्य सलाह: {HEALTH_ADVICE[lang][category]}",
                ]
                + ([f"- उपाय: {GRAP_ADVICE[lang][stage]}"] if stage else [])
                + ["- यह AI मॉडल (Aurora) पर आधारित जानकारी है; आधिकारिक चेतावनी के लिए CPCB/CAQM देखें।"]
            )
        msgs.append(
            {
                "site": site,
                "lang": lang,
                "category": category,
                "aqi_peak": aqi,
                "grap_stage": stage,
                "peak_time_ist": r["peak_time_ist"].isoformat(),
                "short": short,
                "long": long,
            }
        )
    return msgs


def city_message(summary: pd.DataFrame, lang: Lang = "ko") -> str:
    """One city-wide headline."""
    worst = summary.loc[summary["aqi_peak"].idxmax()]
    median = float(summary["aqi_peak"].median())
    cat = CATEGORY_NAMES[lang][aqi_category(median)]
    worst_cat = CATEGORY_NAMES[lang][worst["category_peak"]]
    stage = int(summary["grap_stage"].max())
    peak = _fmt_ist(worst["peak_time_ist"], lang)
    if lang == "ko":
        s = (
            f"델리 NCR 대기질 전망: 지역 중간값 최고 AQI {median:.0f} ({cat}), "
            f"최악 지점 {worst['site']} AQI {worst['aqi_peak']:.0f} ({worst_cat}), {peak} 전후."
        )
        if stage:
            s += f" GRAP {stage}단계 수준에 해당합니다."
        return s
    if lang == "en":
        s = (
            f"Delhi-NCR outlook: median peak AQI {median:.0f} ({cat}); worst site {worst['site']} "
            f"at AQI {worst['aqi_peak']:.0f} ({worst_cat}) around {peak}."
        )
        if stage:
            s += f" Corresponds to GRAP Stage {stage}."
        return s
    s = (
        f"दिल्ली-NCR पूर्वानुमान: माध्यिका अधिकतम AQI {median:.0f} ({cat}); सबसे खराब {worst['site']} "
        f"AQI {worst['aqi_peak']:.0f} ({worst_cat}) {peak} के आसपास।"
    )
    if stage:
        s += f" GRAP चरण {stage} के बराबर।"
    return s


# ----------------------------------------------------------------------------------------------
# Gridded tile for the msresearch-aurora map frontend
# ----------------------------------------------------------------------------------------------


@dataclasses.dataclass
class GridForecast:
    """Hourly fields on a regular lat/lon tile. `fields[name]` has shape `(T, H, W)`.

    `times[0]` may be the initial condition (analysis) when `has_analysis` is `True`; the
    remaining entries are forecasts.
    """

    times: list[datetime]
    lat: np.ndarray
    lon: np.ndarray
    fields: dict[str, np.ndarray]
    has_analysis: bool = False


def _crop_indices(lat: np.ndarray, lon: np.ndarray, bbox: tuple[float, float, float, float]):
    lat_min, lat_max, lon_min, lon_max = bbox
    ii = np.where((lat >= lat_min - 1e-6) & (lat <= lat_max + 1e-6))[0]
    jj = np.where((lon >= lon_min % 360 - 1e-6) & (lon <= lon_max % 360 + 1e-6))[0]
    return ii, jj


def _regrid_to(field: np.ndarray, lat: np.ndarray, lon: np.ndarray, lat_new: np.ndarray,
               lon_new: np.ndarray) -> np.ndarray:  # fmt: skip
    from scipy.interpolate import RegularGridInterpolator

    rgi = RegularGridInterpolator(
        (lat[::-1], lon), np.asarray(field, dtype=np.float64)[::-1], bounds_error=False
    )
    gl, gn = np.meshgrid(lat_new, lon_new % 360, indexing="ij")
    return rgi(np.stack([gl.ravel(), gn.ravel()], axis=1)).reshape(gl.shape)


def _add_aqi_fields(fields: dict[str, np.ndarray]) -> None:
    sub25 = cpcb_sub_index_array("pm2p5", fields["pm2p5"])
    sub10 = cpcb_sub_index_array("pm10", fields["pm10"])
    fields["aqi"] = np.fmax(sub25, sub10)


def build_grid_forecast(
    v15_preds: Sequence[Batch],
    ap_batches: Sequence[Batch],
    v15_input: Optional[Batch] = None,
    bbox: tuple[float, float, float, float] = FRONTEND_BBOX,
) -> GridForecast:
    """Crop Aurora 1.5 hourly fields to `bbox` and overlay time-interpolated PM from the Air
    Pollution model (`ap_batches` should include the t0 analysis batch first)."""
    ref = v15_preds[0]
    lat_g, lon_g = ref.metadata.lat.numpy(), ref.metadata.lon.numpy()
    ii, jj = _crop_indices(lat_g, lon_g, bbox)
    lat, lon = lat_g[ii], lon_g[jj]

    steps: list[tuple[datetime, dict[str, np.ndarray]]] = []
    if v15_input is not None:
        steps.append((v15_input.metadata.time[0], {
            k: v15_input.surf_vars[k][0, -1].numpy()[np.ix_(ii, jj)] for k in ("2t", "10u", "10v", "msl")
        }))  # fmt: skip
    for p in v15_preds:
        steps.append((p.metadata.time[0], {
            k: p.surf_vars[k][0, -1].numpy()[np.ix_(ii, jj)] for k in ("2t", "10u", "10v", "msl")
        }))  # fmt: skip

    times = [t for t, _ in steps]
    fields: dict[str, np.ndarray] = {
        "wind_ms": np.stack([np.hypot(f["10u"], f["10v"]) for _, f in steps]),
        "wind_dir": np.stack([(np.degrees(np.arctan2(f["10v"], f["10u"])) + 360) % 360 for _, f in steps]),
        "t2m_c": np.stack([f["2t"] - 273.15 for _, f in steps]),
        "msl_hpa": np.stack([f["msl"] / 100.0 for _, f in steps]),
    }  # fmt: skip

    # PM fields: regrid each 12-hourly AP batch onto the tile, then interpolate in time.
    ap_times = np.array([pd.Timestamp(b.metadata.time[0]).value for b in ap_batches], dtype=np.float64)
    for name in ("pm2p5", "pm10"):
        stack = np.stack([
            _regrid_to(b.surf_vars[name][0, -1].numpy() * 1e9, b.metadata.lat.numpy(),
                       b.metadata.lon.numpy(), lat, lon)
            for b in ap_batches
        ])  # fmt: skip
        tq = np.array([pd.Timestamp(t).value for t in times], dtype=np.float64)
        out = np.empty((len(times), *stack.shape[1:]))
        flat = stack.reshape(len(ap_batches), -1)
        for c in range(flat.shape[1]):
            out[:, c // stack.shape[2], c % stack.shape[2]] = np.interp(tq, ap_times, flat[:, c])
        fields[name] = out
    _add_aqi_fields(fields)
    return GridForecast(times, lat, lon, fields, has_analysis=v15_input is not None)


def demo_grid_forecast(
    pollutants: pd.DataFrame,
    met: pd.DataFrame,
    sites: Sequence[Site] = DELHI_SITES,
    bbox: tuple[float, float, float, float] = FRONTEND_BBOX,
    res: float = 0.25,
) -> GridForecast:
    """Synthetic tile for demo mode: inverse-distance weighting of the site series onto a grid,
    with a gentle north-west to south-east gradient so the map is not flat."""
    lat_min, lat_max, lon_min, lon_max = bbox
    lat = np.arange(lat_max, lat_min - 1e-9, -res)
    lon = np.arange(lon_min, lon_max + 1e-9, res)
    gl, gn = np.meshgrid(lat, lon, indexing="ij")
    site_xy = np.array([(s.lat, s.lon) for s in sites])
    d2 = (gl[..., None] - site_xy[:, 0]) ** 2 + (gn[..., None] - site_xy[:, 1]) ** 2
    w = 1.0 / (d2 + 0.05)
    w /= w.sum(axis=-1, keepdims=True)
    decay = np.exp(-np.sqrt(d2.min(axis=-1)) / 0.8)  # Fade towards the regional background.
    gradient = 1 + 0.15 * ((gl - gl.mean()) / 2 - (gn - gn.mean()) / 2)

    times = sorted(met["time"].unique())
    fields = {k: np.zeros((len(times), *gl.shape)) for k in
              ("wind_ms", "wind_dir", "t2m_c", "msl_hpa", "pm2p5", "pm10")}  # fmt: skip
    p_by_site = {s: g.set_index("time").sort_index() for s, g in pollutants.groupby("site")}
    m_by_site = {s: g.set_index("time").sort_index() for s, g in met.groupby("site")}
    # Use nanosecond integers on both sides: pandas may store the frames at a coarser resolution.
    p_ns = {s: np.array([pd.Timestamp(x).value for x in g.index], dtype=np.float64)
            for s, g in p_by_site.items()}  # fmt: skip
    for ti, t in enumerate(times):
        t_ns = float(pd.Timestamp(t).value)
        pm25 = np.array([np.interp(t_ns, p_ns[s.name], p_by_site[s.name]["pm2p5"]) for s in sites])
        pm10 = np.array([np.interp(t_ns, p_ns[s.name], p_by_site[s.name]["pm10"]) for s in sites])
        m = np.array([m_by_site[s.name].loc[t, ["wind10_ms", "t2m_c"]].to_numpy(dtype=float) for s in sites])
        bg25, bg10 = 0.55 * pm25.mean(), 0.55 * pm10.mean()
        fields["pm2p5"][ti] = (decay * (w @ pm25) + (1 - decay) * bg25) * gradient
        fields["pm10"][ti] = (decay * (w @ pm10) + (1 - decay) * bg10) * gradient
        fields["wind_ms"][ti] = (w @ m[:, 0]) * (2 - gradient)
        fields["wind_dir"][ti] = 300.0 + 10 * np.sin(ti / 6)
        fields["t2m_c"][ti] = w @ m[:, 1] - 0.3 * (gl - gl.mean())
        fields["msl_hpa"][ti] = 1016 - 0.4 * (gl - gl.mean()) + 0.1 * np.cos(ti / 12)
    _add_aqi_fields(fields)
    return GridForecast([pd.Timestamp(t).to_pydatetime() for t in times], lat, lon, fields)


def export_frontend_json(
    grid: GridForecast, out_dir: Path, region_name: str = "Delhi NCR", max_steps: Optional[int] = None
) -> list[Path]:
    """Write the two JSON files read by the msresearch-aurora Norway-style React frontend.

    `auroraForecast.json` (the "observations" toggle) receives the analysis step when available,
    otherwise the first forecast hour; `auroraForecastPredictions.json` receives the forecast
    steps. Cells carry the frontend's native keys (`windSpeed`, `windDirection`, `temperature`,
    `pressure`) plus `pm25`, `pm10` and `aqi` for a patched frontend (see README_kor.md).
    """

    def _payload(indices: Sequence[int], name: str) -> dict:
        f = grid.fields
        steps = []
        for ti in indices:
            cells = []
            for i, la in enumerate(grid.lat):
                for j, lo in enumerate(grid.lon):
                    cells.append({
                        "id": f"{ti}-{i}-{j}",
                        "latitude": float(la),
                        "longitude": float(lo if lo <= 180 else lo - 360),
                        "windSpeed": round(float(f["wind_ms"][ti, i, j]), 2),
                        "windDirection": round(float(f["wind_dir"][ti, i, j]), 1),
                        "temperature": round(float(f["t2m_c"][ti, i, j]), 2),
                        "pressure": round(float(f["msl_hpa"][ti, i, j]), 1),
                        "pm25": round(float(f["pm2p5"][ti, i, j]), 1),
                        "pm10": round(float(f["pm10"][ti, i, j]), 1),
                        "aqi": round(float(f["aqi"][ti, i, j]), 0),
                    })  # fmt: skip
            summary = (
                f"Mean wind {f['wind_ms'][ti].mean():.1f} m/s with gusts to {f['wind_ms'][ti].max():.1f} m/s. "
                f"Average temperature {f['t2m_c'][ti].mean():+.1f} \u00b0C. "
                f"Sea-level pressure spans {f['msl_hpa'][ti].min():.0f}\u2013{f['msl_hpa'][ti].max():.0f} hPa. "
                f"PM2.5 mean {f['pm2p5'][ti].mean():.0f} ug/m3, max AQI {np.nanmax(f['aqi'][ti]):.0f} "
                f"({aqi_category(float(np.nanmax(f['aqi'][ti])))})."
            )
            steps.append({"timestamp": grid.times[ti].strftime("%Y-%m-%dT%H:%M:%S"), "summary": summary, "cells": cells})
        rng = lambda k: [float(np.nanmin(f[k][indices])), float(np.nanmax(f[k][indices]))]  # noqa: E731
        return {
            "generatedAt": datetime.now(timezone.utc).isoformat(),
            "region": {"name": name, "center": [float(grid.lat.mean()), float(grid.lon.mean())]},
            "variableRanges": {
                "windSpeed": rng("wind_ms"), "temperature": rng("t2m_c"), "pressure": rng("msl_hpa"),
                "pm25": rng("pm2p5"), "pm10": rng("pm10"), "aqi": rng("aqi"),
            },  # fmt: skip
            "steps": steps,
        }

    out_dir.mkdir(parents=True, exist_ok=True)
    n = len(grid.times)
    if grid.has_analysis:
        obs_idx, pred_idx = [0], list(range(1, n))
    else:
        obs_idx, pred_idx = [0], list(range(n))
    if max_steps is not None:
        pred_idx = pred_idx[:max_steps]

    paths = []
    p = out_dir / "auroraForecast.json"
    label = "analysis" if grid.has_analysis else "first forecast hour"
    p.write_text(json.dumps(_payload(obs_idx, f"{region_name} initial condition ({label})")), encoding="utf-8")
    paths.append(p)
    p = out_dir / "auroraForecastPredictions.json"
    p.write_text(json.dumps(_payload(pred_idx, f"Aurora forecast: {region_name}")), encoding="utf-8")
    paths.append(p)
    return paths


# ----------------------------------------------------------------------------------------------
# Demo data (no downloads, no GPU)
# ----------------------------------------------------------------------------------------------


def demo_frames(
    init_time: datetime, hours: int = 48, sites: Sequence[Site] = DELHI_SITES, seed: int = 0
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Synthesize a plausible November smog episode in Delhi.

    Returns (pollutants, meteorology) frames shaped exactly like the outputs of
    :func:`extract_pollutants` (12-hourly, including t0) and :func:`extract_meteorology`
    (hourly), so the rest of the pipeline is exercised unchanged.
    """
    rng = np.random.default_rng(seed)
    hourly = [init_time + timedelta(hours=h) for h in range(1, hours + 1)]
    twelve = [init_time + timedelta(hours=h) for h in range(0, hours + 1, 12)]
    kind_offset = {"traffic": 60.0, "industrial": 40.0, "residential": 0.0, "background": -30.0}

    def ist_hour(t: datetime) -> float:
        return (t.hour + 5.5) % 24

    def pm25(t: datetime, site: Site, offset: float) -> float:
        h = ist_hour(t)
        lead = (t - init_time).total_seconds() / 3600
        diurnal = 55 * math.exp(-((h - 7) ** 2) / 8) + 35 * math.exp(-((h - 22) ** 2) / 10)
        diurnal -= 45 * math.exp(-((h - 15) ** 2) / 12)
        trend = 1.3 * min(lead, 30) - 1.0 * max(lead - 30, 0)
        return max(20.0, 185 + kind_offset[site.kind] + offset + diurnal + trend)

    def blh(t: datetime) -> float:
        h = ist_hour(t)
        return 150 + 850 * math.exp(-((h - 14.5) ** 2) / 9)

    def wind(t: datetime, lead: float) -> float:
        h = ist_hour(t)
        return max(0.4, 1.2 + 1.3 * math.exp(-((h - 15) ** 2) / 14) + 0.02 * max(lead - 30, 0))

    prow, mrow = [], []
    for site in sites:
        offset = float(rng.normal(0, 12))
        for t in twelve:
            p = pm25(t, site, offset)
            h = ist_hour(t)
            prow.append(
                {
                    "time": t,
                    "site": site.name,
                    "pm2p5": p,
                    "pm10": p * 1.6,
                    "no2": 55 + kind_offset[site.kind] * 0.6 + 30 * math.exp(-((h - 21) ** 2) / 12),
                    "so2": 14 + rng.normal(0, 2),
                    "o3": 15 + 45 * math.exp(-((h - 14) ** 2) / 10),
                    "co": 1.4 + 0.004 * p,
                }
            )
        for t in hourly:
            lead = (t - init_time).total_seconds() / 3600
            h = ist_hour(t)
            t2m = 19 + 7 * math.cos((h - 15) / 24 * 2 * math.pi)
            mrow.append(
                {
                    "time": t,
                    "site": site.name,
                    "wind10_ms": wind(t, lead) + float(rng.normal(0, 0.15)),
                    "gust_ms": wind(t, lead) * 1.8,
                    "blh_m": blh(t) * (1 + float(rng.normal(0, 0.05))),
                    "t2m_c": t2m,
                    "rh_pct": float(np.clip(90 - 2.5 * (t2m - 12), 30, 98)),
                    "tp_1h_mm": 0.0,
                }
            )
    pollutants = pd.DataFrame(prow)
    pollutants["time"] = pd.to_datetime(pollutants["time"])
    met = pd.DataFrame(mrow)
    met["time"] = pd.to_datetime(met["time"])
    return pollutants, met


# ----------------------------------------------------------------------------------------------
# End-to-end pipeline
# ----------------------------------------------------------------------------------------------


@dataclasses.dataclass
class PipelineResult:
    pollutants: pd.DataFrame
    meteorology: pd.DataFrame
    fused: pd.DataFrame
    summary: pd.DataFrame
    messages: dict[str, list[dict]]
    city: dict[str, str]
    grid: Optional[GridForecast] = None


def run_pipeline(
    init_date: datetime,
    hours: int = 48,
    mode: Literal["demo", "local", "foundry"] = "demo",
    langs: Sequence[Lang] = ("ko", "en", "hi"),
    data_dir: Path = Path("~/downloads/delhi_aq").expanduser(),
    device: str = "cuda",
    sites: Sequence[Site] = DELHI_SITES,
) -> PipelineResult:
    """Run the whole storyboard: forecasts -> Delhi extraction -> AQI -> messages."""
    init_time = init_date.replace(hour=12, minute=0, second=0, microsecond=0, tzinfo=None)

    grid: Optional[GridForecast] = None
    if mode == "demo":
        pollutants, met = demo_frames(init_time, hours=hours, sites=sites)
        grid = demo_grid_forecast(pollutants, met, sites)
    else:
        backend: Backend = "foundry" if mode == "foundry" else "local"
        ap_steps = max(1, math.ceil(hours / 12))
        v15_steps = max(1, math.ceil(hours / 6))

        logger.info("Downloading CAMS and building the Air Pollution batch")
        surf_nc, atmos_nc = download_cams(init_time, data_dir)
        ap_batch = build_air_pollution_batch(
            surf_nc, atmos_nc, load_static("aurora-0.4-air-pollution-static.pickle")
        )
        logger.info("Running Aurora 0.4 Air Pollution for %d x 12 h (%s)", ap_steps, backend)
        ap_preds = run_air_pollution(ap_batch, ap_steps, backend=backend, device=device)
        pollutants = extract_pollutants([ap_batch, *ap_preds], sites)

        logger.info("Downloading ERA5 and building the Aurora 1.5 batch")
        surf_nc, atmos_nc = download_era5_for_v15(init_time, data_dir)
        v15_batch = build_v15_batch(
            surf_nc, atmos_nc, load_static("aurora-0.25-v1.5-static.pickle")
        )
        logger.info("Running Aurora 1.5 for %d x 6 h with hourly sub-steps (%s)", v15_steps, backend)
        v15_preds = run_v15(v15_batch, v15_steps, backend=backend, device=device)
        v15_preds = [p for p in v15_preds if p.metadata.time[0] <= init_time + timedelta(hours=hours)]
        met = extract_meteorology(v15_preds, sites)
        grid = build_grid_forecast(v15_preds, [ap_batch, *ap_preds], v15_input=v15_batch)

    fused = fuse(pollutants, met)
    summary = summarise(fused, sites)
    messages = {lang: build_messages(summary, lang) for lang in langs}
    city = {lang: city_message(summary, lang) for lang in langs}
    return PipelineResult(pollutants, met, fused, summary, messages, city, grid)


def write_outputs(result: PipelineResult, out_dir: Path) -> list[Path]:
    """Write CSV/JSON/Markdown artefacts to `out_dir` and return the paths."""
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = []

    def _save_csv(df: pd.DataFrame, name: str) -> None:
        p = out_dir / name
        df.to_csv(p, index=False)
        paths.append(p)

    _save_csv(result.pollutants, "pollutants_12h.csv")
    _save_csv(result.meteorology, "meteorology_hourly.csv")
    _save_csv(result.fused, "fused_hourly.csv")
    _save_csv(result.summary, "summary_by_site.csv")

    for lang, msgs in result.messages.items():
        p = out_dir / f"messages_{lang}.json"
        with open(p, "w", encoding="utf-8") as f:
            json.dump({"city": result.city[lang], "sites": msgs}, f, ensure_ascii=False, indent=2)
        paths.append(p)

        p = out_dir / f"bulletin_{lang}.md"
        with open(p, "w", encoding="utf-8") as f:
            f.write(f"# {result.city[lang]}\n\n")
            for m in msgs:
                f.write(m["long"] + "\n\n")
        paths.append(p)

    if result.grid is not None:
        paths.extend(export_frontend_json(result.grid, out_dir / "frontend"))
    return paths


def plot_overview(result: PipelineResult, path: Optional[Path] = None):
    """Plot PM2.5/AQI and dispersion diagnostics per site (requires matplotlib)."""
    import matplotlib.pyplot as plt

    fused = result.fused
    fig, axs = plt.subplots(3, 1, figsize=(11, 9), sharex=True)
    for site, f in fused.groupby("site", sort=False):
        axs[0].plot(f["time_ist"], f["pm2p5"], label=site, lw=1.2)
        axs[1].plot(f["time_ist"], f["blh_m"], lw=1.2)
        axs[2].plot(f["time_ist"], f["wind10_ms"] * 3.6, lw=1.2)
    for lo, hi, name in AQI_CATEGORIES[2:]:
        c_lo = next(c for c, _, i_lo, _ in CPCB_BREAKPOINTS["pm2p5"] if i_lo == lo)
        axs[0].axhline(c_lo, color="grey", ls=":", lw=0.8)
        axs[0].text(f["time_ist"].iloc[0], c_lo, f" {name}", va="bottom", fontsize=8, color="grey")
    axs[0].set_ylabel("PM2.5 (µg/m³)\n12-h model, interpolated")
    axs[1].axhline(STAGNANT_BLH_M, color="grey", ls=":", lw=0.8)
    axs[1].set_ylabel("Boundary-layer height (m)\nAurora 1.5 hourly")
    axs[2].axhline(10, color="grey", ls=":", lw=0.8)
    axs[2].set_ylabel("10 m wind (km/h)\nAurora 1.5 hourly")
    axs[2].set_xlabel("Time (IST)")
    axs[0].legend(ncol=2, fontsize=8)
    fig.suptitle("Delhi-NCR: Aurora Air Pollution + Aurora 1.5 dispersion outlook")
    fig.tight_layout()
    if path is not None:
        fig.savefig(path, dpi=130)
    return fig


def main(argv: Optional[Sequence[str]] = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--mode", choices=["demo", "local", "foundry"], default="demo")
    parser.add_argument(
        "--date", default=None, help="Initialisation date YYYY-MM-DD (12 UTC). Default: today."
    )
    parser.add_argument("--hours", type=int, default=48, help="Forecast horizon in hours.")
    parser.add_argument("--langs", default="ko,en,hi")
    parser.add_argument("--out", default="outputs")
    parser.add_argument("--data-dir", default="~/downloads/delhi_aq")
    parser.add_argument("--device", default="cuda" if torch.cuda.is_available() else "cpu")
    parser.add_argument("--plot", action="store_true", help="Also save overview.png (matplotlib).")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )
    init_date = (
        datetime.strptime(args.date, "%Y-%m-%d")
        if args.date
        else datetime.now(timezone.utc).replace(tzinfo=None)
    )
    langs = tuple(s.strip() for s in args.langs.split(",") if s.strip())  # type: ignore[assignment]

    result = run_pipeline(
        init_date,
        hours=args.hours,
        mode=args.mode,
        langs=langs,  # type: ignore[arg-type]
        data_dir=Path(args.data_dir).expanduser(),
        device=args.device,
    )
    out_dir = Path(args.out)
    paths = write_outputs(result, out_dir)
    if args.plot:
        plot_overview(result, out_dir / "overview.png")
        paths.append(out_dir / "overview.png")

    for lang in langs:
        print(result.city[lang])
    print()
    print(result.summary[["site", "aqi_now", "aqi_peak", "category_peak", "dominant",
                          "grap_stage", "stagnant_hours", "trend"]].to_string(index=False))  # fmt: skip
    print()
    print("\n".join(str(p) for p in paths))


if __name__ == "__main__":
    main()
