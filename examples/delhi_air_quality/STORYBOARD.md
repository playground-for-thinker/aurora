# Storyboard: Aurora-based air-quality early warning for New Delhi

> "From tonight until tomorrow morning the AQI around Anand Vihar is expected to exceed 450. Keep windows closed and avoid outdoor activity before school."
>
> This document walks scene by scene through what it takes for that one line to reach a citizen, and where Aurora is used along the way. Korean version: `STORYBOARD_kor.md`. Interactive version with a KO/EN switch: [https://claude.ai/artifact/6GkTNUq54pqXGZBVx7BGSE](https://claude.ai/artifact/6GkTNUq54pqXGZBVx7BGSE) (source: `storyboard.html`).

Related files:

| File | Role |
| - | - |
| `delhi_aq.py` | The whole pipeline (data → models → AQI → messages). Also a CLI |
| `example_delhi_air_quality.ipynb` | Notebook that follows the storyboard |
| `README_kor.md` | Installation, run modes, environment variables, msresearch-aurora linkage |

---

## 0. Background: why Delhi, why November

- Delhi-NCR suffers some of the world's worst particulate episodes every year from late October to January. Post-harvest stubble burning in neighbouring states, Diwali fireworks and traffic, construction and power emissions coincide with winter's **shallow mixing layer (boundary-layer height 100–300 m) and weak winds**, which trap pollution near the ground.
- India operates a national AQI (CPCB scale) and a staged response plan, **GRAP** (Graded Response Action Plan, run by CAQM). GRAP ties AQI bands to concrete actions such as construction bans, vehicle restrictions, online classes and work-from-home, so the chain **forecast → stage → action** already exists institutionally.
- The question this storyboard answers is therefore not "how bad will it get" but **"when, where, because of which weather conditions, and what should citizens do"**, delivered 12 to 48 hours ahead.

## 1. Cast

| Role | What they want | Output in this example |
| - | - | - |
| General public | One line about what to watch out for tonight or tomorrow morning | `short` in `messages_*.json` (push/SMS) |
| Sensitive groups (children, older adults, respiratory patients, carers) | Concrete actions and time windows | Health advice and dispersion lines in the `long` message |
| Operators (DPCC/CAQM staff or a service team) | Peak time per site, the basis for the GRAP stage, the trend | `summary_by_site.csv`, `bulletin_*.md` |
| Data/ML engineers | A reproducible pipeline that switches between local and cloud | `--mode local|foundry` in `delhi_aq.py` |

## 2. System: Aurora appears twice

```
   [Data sources]                      [Aurora models]                        [Delhi post-processing]        [Citizens]

 CAMS global analysis (0.4°) ────►  Aurora 0.4° Air Pollution  ──┐
  PM1/2.5/10, NO2, SO2,            12-h steps × 4 = 48 h          │  10 sites, bilinear   CPCB AQI     messages
  O3, CO + meteorology             (local GPU or the Foundry       ├─► (Anand Vihar, ITO, ─► GRAP stage ─► ko/en/hi ─► push/SMS/
                                    "Aurora" endpoint)             │   Dwarka, ...)         stagnation    short/long   WhatsApp/app
 ERA5 or IFS HRES T0 (0.25°) ────► Aurora 1.5                     ─┘
  26 surface vars, 13 levels        6 h × 8 + hourly sub-steps
                                    = 48 hourly predictions
                                    (boundary-layer height, 10 m wind,
                                     temperature, dew point, rain, gusts)
```

**Why two models.** Aurora 1.5 is a weather model and does not predict pollutants. What it adds is **hourly** dispersion conditions: boundary-layer height (`blh`), wind speed, precipitation. Aurora Air Pollution predicts pollutant concentrations directly, but at 12-hour steps and 0.4°. Together they answer both "how high is the concentration" (Air Pollution) and "from what hour tonight does stagnation set in" (1.5).

**What "high resolution" means here.** Two things. (1) **Temporal**: Aurora 1.5 with `fine_lead_times=[1,…,6]` gives hourly predictions. (2) **Spatial presentation**: the 0.4°/0.25° grids are bilinearly interpolated to ten representative Delhi-NCR locations. The grid itself cannot resolve intra-city differences, so site-to-site differences mostly reflect the regional spatial gradient (see §6).

**Linkage with the msresearch-aurora skill.** The repository's `msresearch-aurora/` directory (the Aurora skill from microsoft/vibe-kit) contributes three things. (1) The Norway example's React map frontend: the pipeline exports a Delhi-NCR tile (27.5–31.5°N, 76–80°E) in the same JSON schema, so a map cloned with `setup_region.py --name "Delhi NCR"` shows wind, temperature and pressure (and PM2.5/AQI after a small patch) on a time slider. (2) Validation utilities such as `validate_grid.py`, `download_era5_subset.py`, `check_divergence.py`, `validate_forecast.py`. (3) The fine-tuning starter in `starter-code/` (§7). Step-by-step instructions are in `README_kor.md`.

**Linkage with Azure AI Foundry.** Checkpoints download automatically from HuggingFace `microsoft/aurora`. Without a GPU, or in production, `--mode foundry` submits jobs with `aurora.foundry.submit` to the **"Aurora"** (includes Air Pollution) and **"Aurora-1.5"** endpoints. The Aurora-1.5 endpoint supports `fine_lead_times`, `saved_surf_vars` (store only the needed variables) and `async_upload_workers` to cut transfer volume and time.

## 3. Scene-by-scene timeline (example: issued 5 November)

| Time (IST) | Scene | What the system does |
| - | - | - |
| 17:30 (= 12 UTC) | **S1. Initial conditions** | Download CAMS 00/12 UTC analysis and ERA5 (or HRES T0) 06/12 UTC. Load static-variable pickles. Build two `Batch` objects |
| 17:40 | **S2. Run forecasts** | Air Pollution 4 steps (+12/24/36/48 h); Aurora 1.5 8 steps × 6 sub-steps (+1…+48 h). One GPU or Foundry |
| 17:50 | **S3. Extract and fuse** | Interpolate to 10 sites. Interpolate 12-hourly concentrations to hourly and flag **stagnant hours** (wind < 10 km/h, mixing height < 500 m) from 1.5's hourly `blh` and wind. Compute CPCB AQI, dominant pollutant, GRAP stage |
| 18:00 | **S4. Evening alert** | Per-site `short` message (push/SMS). Example: "[Air quality alert] Anand Vihar: peak AQI 500 (Severe) expected around 07 Nov 05:30 IST. Main pollutant PM10, PM2.5 up to 321 ug/m3. Even healthy people are affected." |
| 18:00 | **S4b. Map check** | Load `outputs/frontend/*.json` into the msresearch-aurora frontend so operators can see the spatial pattern over the whole tile (south-eastern stagnation, wind direction) |
| 18:00 | **S5. Operator briefing** | `bulletin_en.md`: city headline plus per-site detail (peak time, trend, stagnant hours, GRAP guidance). Operators compare with the official CAQM stage |
| 22:00–08:00 | **S6. Stagnation window** | The 1.5-predicted night-time mixing layer of 150–300 m and 1–2 m/s winds. Reflected in the message as "pollution will tend to pool near the surface from night to morning". Reminders for sensitive groups (close windows, skip early-morning exercise) can go out |
| 06:00 (next day) | **S7. Morning update** | Re-run from the 00 UTC initial condition (cron). "Peak 07:00–09:00, wear a mask" before school and commute |
| Afterwards | **S8. Verification** | Compare per-site predictions with CPCB/DPCC observations (SAMEER, CPCB CCR). Derive bias corrections and feed them into the next issue |

## 4. Message design principles

1. Put **what (value and category), when (IST peak time), where (site) and how (one or two actions)** in under 160 characters. `short` is for SMS/push; `long` is for app detail and briefings.
2. **Use CPCB category names verbatim** (Good / Satisfactory / Moderate / Poor / Very Poor / Severe). They must match what citizens see in the news and the official app.
3. **Name sensitive groups first** in the advice (children, older adults, pregnant women, respiratory patients).
4. **Describe GRAP stages as "corresponding level" only.** Enforcement is CAQM's call, so write "may be enforced" and point to official notices.
5. **Include one sentence of meteorological reasoning** ("37 h of stagnation with mixing height below 500 m and wind below 10 km/h"). People who understand why nights are worse comply better.
6. **A fixed disclaimer**: "AI-model (Aurora) guidance for information only; follow official CPCB/CAQM alerts."
7. Languages: Hindi (primary), English (secondary), and Korean for the operating team. All templates live in `HEALTH_ADVICE`, `GRAP_ADVICE` and `CATEGORY_NAMES` in `delhi_aq.py`, so health experts can review the wording without touching code.

## 5. Sample output (demo mode)

City headline:

> Delhi-NCR outlook: median peak AQI 433 (Severe); worst site Anand Vihar at AQI 500 (Severe) around 07 Nov 05:30 IST. Corresponds to GRAP Stage 4.

Per-site detail (from `bulletin_en.md`):

> ■ Anand Vihar air-quality outlook (05 Nov 18:30 IST to 07 Nov 17:30 IST)
> - AQI now 385, peaking at 500 (Severe) around 07 Nov 05:30 IST. Trend: roughly steady.
> - Main pollutant: PM10. PM2.5 up to 321 ug/m3, PM10 up to 514 ug/m3.
> - Dispersion: Stagnant conditions (wind below 10 km/h, mixing height below 500 m) are expected for 37 h, 20 h of them overnight (minimum mixing height about 133 m). …
> - Health advice: Even healthy people are affected. Stay indoors as much as possible …
> - Measures: GRAP Stage IV (Severe+) level: truck entry restrictions, expanded work-from-home … Follow official notices.

Demo-mode numbers are synthetic and imitate a typical November episode. Real forecasts come from `--mode local` or `--mode foundry`.

## 6. Limits and responsible use

- **Spatial resolution**: the Air Pollution model runs at 0.4° (about 40 km). Site differences are interpolation; roadside or industrial-estate concentrations are not resolved. A real service needs per-station bias correction (§3 S8) or additional fine-tuning on CPCB data.
- **Temporal resolution**: the hourly concentration curve is a linear interpolation of 12-hour forecasts. The hourly structure comes from Aurora 1.5's meteorology, and the messages say so.
- **Input data**: Aurora 1.5 was fine-tuned on IFS HRES T0. This example uses the more accessible ERA5, so accuracy is not guaranteed (same position as the official 1.5 example). The Air Pollution model is for CAMS analysis only.
- **Gases at 1000 hPa**: NO2/SO2/O3/CO are 1000 hPa mixing ratios converted with air density. Delhi (about 216 m above sea level) sits slightly above the 1000 hPa surface, so these are approximations. In practice PM2.5/PM10 dominate the AQI.
- **Operational decisions**: as the repository's Responsible AI documentation states, Aurora is a research model and must not drive operational decisions without expert review. Every message tells readers to follow official CPCB/CAQM alerts.

## 7. Roadmap

1. **Uncertainty**: run `AuroraV1p5Ensemble` with `rollout_ensemble` to express probabilities such as "80% chance of stagnation".
2. **Assimilating or correcting with CPCB observations**: learn per-site residuals between observations and forecasts (start with simple linear or quantile mapping).
3. **Fine-tuning**: use `msresearch-aurora/starter-code/` (PyTorch Lightning loop, `vibe_tune_aurora.cli.train`) to adapt the Air Pollution model to regional CAMS reanalysis or gridded CPCB observations and reduce regional bias. Model-side requirements (normalisation statistics, `strict=False` loading) are in this repository's `docs/finetuning.md`; training-side guidance is in the skill's `docs/finetuning-guide.md`.
4. **Channels**: a small adapter that pushes `messages_hi.json` to the WhatsApp Business API, an SMS gateway or the Delhi government app backend. Map users to the nearest site by residential pin code.
5. **Automation**: run `python delhi_aq.py --mode foundry --plot` from cron at 00 and 12 UTC and archive the outputs in blob storage.
