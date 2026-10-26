# 뉴델리 대기질 조기경보 예제

[![Story Map · 한국어](https://img.shields.io/badge/Story%20Map-%ED%95%9C%EA%B5%AD%EC%96%B4-0b6e8f?logo=jupyter&logoColor=white)](https://notebook.link/github/playground-for-thinker/aurora/tree/storymap/specta/?path=delhi_aq_storymap_ko.jGIS) [![Story Map · English](https://img.shields.io/badge/Story%20Map-English-0b6e8f?logo=jupyter&logoColor=white)](https://notebook.link/github/playground-for-thinker/aurora/tree/storymap/specta/?path=delhi_aq_storymap_en.jGIS) [![Storyboard · 한국어](https://img.shields.io/badge/Storyboard-%ED%95%9C%EA%B5%AD%EC%96%B4-0b6e8f?logo=jupyter&logoColor=white)](https://notebook.link/github/playground-for-thinker/aurora/tree/storymap/specta/?path=storyboard_ko.ipynb) [![Storyboard · English](https://img.shields.io/badge/Storyboard-English-0b6e8f?logo=jupyter&logoColor=white)](https://notebook.link/github/playground-for-thinker/aurora/tree/storymap/specta/?path=storyboard_en.ipynb) [![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/playground-for-thinker/aurora/blob/main/examples/delhi_air_quality/example_delhi_air_quality.ipynb) [![Binder](https://mybinder.org/badge_logo.svg)](https://mybinder.org/v2/gh/playground-for-thinker/aurora/main?labpath=examples%2Fdelhi_air_quality%2Fexample_delhi_air_quality.ipynb)

Aurora 0.4° Air Pollution(오염물질 농도)과 Aurora 1.5(시간별 확산 기상)를 결합해 델리 NCR 10개 지점의 CPCB AQI·GRAP 단계를 산출하고, 시민용 경보 메시지(힌디어/영어/한국어)를 만드는 예제입니다. 전체 흐름과 설계 의도는 [`STORYBOARD_kor.md`](STORYBOARD_kor.md)를 보세요.

## 바로 열어보기

| 무엇 | 링크 | 비고 |
| - | - | - |
| 스토리 맵 · 한국어 (JupyterGIS 문서, notebook.link) | [https://notebook.link/github/playground-for-thinker/aurora/tree/storymap/specta/?path=delhi_aq_storymap_ko.jGIS](https://notebook.link/github/playground-for-thinker/aurora/tree/storymap/specta/?path=delhi_aq_storymap_ko.jGIS) | 전체 화면(Specta) 분할 구성: 왼쪽 절반 지도, 오른쪽 절반 장면별 설명(스크롤). 편집기로 열기: [lab/?path=delhi_aq_storymap_ko.jGIS](https://notebook.link/github/playground-for-thinker/aurora/tree/storymap/lab/?path=delhi_aq_storymap_ko.jGIS). 파일은 `storymap/delhi_aq_storymap_ko.jGIS` + `storymap/data/`. 19개 장면, AQI 타일(4개 시각)·바람·정체 확률·지점·델리 경계. 배지: 위 "Story Map" |
| 스토리 맵 · English | [https://notebook.link/github/playground-for-thinker/aurora/tree/storymap/specta/?path=delhi_aq_storymap_en.jGIS](https://notebook.link/github/playground-for-thinker/aurora/tree/storymap/specta/?path=delhi_aq_storymap_en.jGIS) | 같은 레이어, 영어 장면. 단일 HTML 파일 버전(한국어 ⇄ English 전환, 로컬에서 바로 열기)은 `storymap.html` + `storymap_data.js` |
| 스토리보드 · 한국어 (발표용 슬라이드, notebook.link) | [https://notebook.link/github/playground-for-thinker/aurora/tree/storymap/specta/?path=storyboard_ko.ipynb](https://notebook.link/github/playground-for-thinker/aurora/tree/storymap/specta/?path=storyboard_ko.ipynb) | 12장. 왼쪽 그림, 오른쪽 설명. 일반인 대상 스토리(코드 없음), "현 시스템이 보여주는 것"과 "정부·시가 할 일" 박스로 구분. 각 장 오른쪽 위 버튼으로 English ⇄ 한국어 전환. 파일은 `storymap/storyboard_ko.ipynb` |
| 스토리보드 · English (slides) | [https://notebook.link/github/playground-for-thinker/aurora/tree/storymap/specta/?path=storyboard_en.ipynb](https://notebook.link/github/playground-for-thinker/aurora/tree/storymap/specta/?path=storyboard_en.ipynb) | 같은 12장, 영어. 기술 문서는 `STORYBOARD_kor.md`/`STORYBOARD.md`, 단일 HTML 파일 버전은 `storyboard.html` |
| 노트북 실행 (Google Colab) | [![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/playground-for-thinker/aurora/blob/main/examples/delhi_air_quality/example_delhi_air_quality.ipynb) | demo 모드는 GPU·데이터 불필요. 첫 셀이 `microsoft-aurora`와 `delhi_aq.py`를 자동으로 받습니다 |
| 노트북 실행 (Binder, JupyterLab) | [![Binder](https://mybinder.org/badge_logo.svg)](https://mybinder.org/v2/gh/playground-for-thinker/aurora/main?labpath=examples%2Fdelhi_air_quality%2Fexample_delhi_air_quality.ipynb) | 첫 빌드는 수 분 소요 |
| 노트북 미리보기 (nbviewer) | [https://nbviewer.org/github/playground-for-thinker/aurora/blob/main/examples/delhi_air_quality/example_delhi_air_quality.ipynb](https://nbviewer.org/github/playground-for-thinker/aurora/blob/main/examples/delhi_air_quality/example_delhi_air_quality.ipynb) | 실행 없이 읽기 |
| 스토리보드 문서 | [`STORYBOARD_kor.md`](STORYBOARD_kor.md) · [`STORYBOARD.md`](STORYBOARD.md) | 마크다운 버전 |
| 스토리보드 PDF (한국어) | [`STORYBOARD_kor.pdf`](STORYBOARD_kor.pdf) | `python make_storyboard_pdf.py STORYBOARD_kor.md STORYBOARD_kor.pdf`로 재생성 (Nanum 글꼴, reportlab) |
| 배지 SVG (자체 호스팅용) | [`badges/story-map.svg`](badges/story-map.svg) | shields.io 대신 쓸 수 있는 정적 배지 |

배지 이미지는 shields.io, Colab, Binder가 제공합니다. Colab/Binder/nbviewer 링크는 `github.com/playground-for-thinker/aurora`의 `main` 브랜치를 가리키므로, 이 디렉터리가 GitHub에 푸시된 뒤에 동작합니다. 스토리 맵·스토리보드 링크는 `storymap/` 폴더를 `storymap` 브랜치로 발행한 뒤(`./publish_storymap_branch.sh`, 자세한 내용은 [`storymap/README.md`](storymap/README.md)) 동작하며, 보는 사람에게 notebook.link 계정은 필요 없습니다.

## 설치

```bash
# 저장소 루트에서
make install                      # 또는 pip install -e .
pip install cdsapi matplotlib     # 데이터 다운로드와 시각화 (demo 모드에는 불필요)
```

## 실행 모드

| 모드 | 설명 | 필요한 것 |
| - | - | - |
| `demo` | 합성 데이터로 후처리(AQI, 메시지)만 실행 | 없음. 다운로드·GPU 불필요 |
| `hybrid` | 기상은 **실제 Aurora 1.5**(공개 ARCO-ERA5 초기장, 계정 불필요), 오염 농도는 합성 | `pip install gcsfs zarr`, GPU(24 GB에서 확인), 체크포인트 다운로드(약 5 GB) |
| `local` | CAMS/ERA5 다운로드 후 두 모델을 로컬 GPU에서 실행 | ADS·CDS 계정, HuggingFace 체크포인트 다운로드(수 GB), GPU |
| `foundry` | 데이터는 로컬에서 준비, 추론은 Azure AI Foundry의 Aurora 엔드포인트에서 실행 | ADS·CDS 계정, Foundry 엔드포인트, Blob SAS URL |

```bash
cd examples/delhi_air_quality

python delhi_aq.py --mode demo --date 2025-11-05 --hours 48 --out outputs
python delhi_aq.py --mode demo --date 2025-11-05 --members 10 --out outputs          # + 시뮬레이션 앙상블
python delhi_aq.py --mode hybrid --date 2025-11-05 --members 5 --device cuda -v --out outputs   # 실제 Aurora 1.5 + 앙상블
python delhi_aq.py --mode local --date 2025-11-05 --hours 48 --device cuda --plot -v
python delhi_aq.py --mode foundry --date 2025-11-05 --hours 48 --plot -v
```

산출물(`outputs/`):

- `pollutants_12h.csv`: 지점별 12시간 간격 농도(PM2.5, PM10 ㎍/㎥; NO2, SO2, O3 ㎍/㎥; CO mg/㎥)
- `meteorology_hourly.csv`: 지점별 시간별 풍속, 돌풍, 경계층 높이, 기온, 상대습도, 강수
- `fused_hourly.csv`: 시간별 AQI, 범주, 주 오염물질, GRAP 단계, 정체 여부, 환기계수
- `summary_by_site.csv`: 지점별 정점 AQI/시각, 정체 시간, 추세
- `messages_{ko,en,hi}.json`: 도시 헤드라인 + 지점별 `short`(푸시/SMS) / `long`(상세) 메시지
- `bulletin_{ko,en,hi}.md`: 운영자용 브리핑
- `overview.png` (`--plot`): PM2.5, 경계층 높이, 풍속 시계열
- 로드맵 실행 산출물: `ensemble_stagnation_sites.csv`·`ensemble_stagnation_tile.npz`(앙상블 정체 확률, `--members`), `bias_correction.csv`(지점별 선형 보정, 합성 관측), `delivery_log.json`(발송 어댑터 dry run), `run_delhi_aq_cron.sh`(자동화), `provenance.json`(어느 값이 Aurora 직접 분석이고 어느 값이 합성·추가 분석인지)
- `frontend/auroraForecast.json`, `frontend/auroraForecastPredictions.json`: 델리 NCR 타일(27.5~31.5°N, 76~80°E, 0.25°)의 시간별 격자. `msresearch-aurora` 지도 프런트엔드가 읽는 형식(아래 참고)

## 환경 변수

데이터 다운로드(둘은 URL이 달라 `~/.cdsapirc` 하나로는 충돌하므로 환경 변수를 권장):

```bash
export ADS_API_KEY=...   # https://ads.atmosphere.copernicus.eu (CAMS)
export CDS_API_KEY=...   # https://cds.climate.copernicus.eu (ERA5)
```

Foundry 모드. "Aurora"(Air Pollution 포함)와 "Aurora-1.5"는 별도 엔드포인트이므로 접미사로 구분합니다. 접미사가 없으면 `FOUNDRY_ENDPOINT`/`FOUNDRY_TOKEN`을 공통으로 씁니다.

```bash
export FOUNDRY_ENDPOINT_AP=https://.../     export FOUNDRY_TOKEN_AP=...
export FOUNDRY_ENDPOINT_V15=https://.../    export FOUNDRY_TOKEN_V15=...
export BLOB_URL_WITH_SAS="https://<account>.blob.core.windows.net/<container>/<folder>?<read+write SAS>"
```

## 스토리 맵 데이터 갱신

스토리 맵은 두 가지 형태로 제공되며 둘 다 `storymap_data.js`를 읽습니다.

- `storymap/*.jGIS` — JupyterGIS 문서. notebook.link·JupyterLab·JupyterLite에서 열리는 공개용 버전. 레이어는 `storymap/data/*.geojson`, notebook.link 환경은 `storymap/environment.yml` + `nblink-lock.json`. 자세한 내용은 [`storymap/README.md`](storymap/README.md)
- `storymap.html` — 단일 HTML 파일. 로컬에서 바로 열어보는 버전(한국어 ⇄ English 전환)

스토리보드 발표 슬라이드도 같은 폴더에 있습니다: `storymap/storyboard_{ko,en}.ipynb`는 슬라이드 12장(장마다 마크다운 셀 하나, 왼쪽 그림·오른쪽 설명)이며 `build_storyboard_slides.py`가 `storymap_data.js`에서 그림(matplotlib, Nanum 글꼴)과 문안을 만듭니다. 코드 셀이 없어 커널 없이 바로 열립니다. `storyboard.html`은 단일 HTML 파일 버전입니다.

파이프라인 산출물 폴더에서 다시 만들려면:

```bash
python build_storymap_data.py outputs --finetune-log path/to/finetune_smoke.log   # storymap_data.js
python build_storymap_jgis.py                                                   # storymap/*.jGIS + storymap/data/*.geojson
python build_storyboard_slides.py                                               # storymap/storyboard_{ko,en}.ipynb + storymap/img/ (발표용 슬라이드)
./publish_storymap_branch.sh                                                    # storymap 브랜치로 발행 → notebook.link 링크 활성화
```

지도 경계(Natural Earth, geoBoundaries)는 기존 `storymap_data.js`에서 재사용하고, 타일·지점 시계열·앙상블 확률·편향 보정·발송 로그·크론 스크립트·출처(provenance)는 산출물에서 읽습니다. 두 버전 모두 출처에 따라 각 장면에 "Aurora 직접 분석 / 추가 분석 / 합성" 태그를 붙입니다.

## msresearch-aurora 스킬과의 연계

저장소의 `msresearch-aurora/`는 [microsoft/vibe-kit](https://github.com/microsoft/vibe-kit)의 Aurora 스킬 사본입니다. 지역 추론 예제(노르웨이)와 Leaflet 기반 React 지도, ERA5 유틸리티 스크립트, 그리고 PyTorch Lightning 파인튠 스타터(`starter-code/`, 패키지명 `vibe_tune_aurora`)가 들어 있습니다. 이 예제는 세 지점에서 그 스킬을 활용합니다.

### 1) 지도 시각화: 델리 NCR 타일을 스킬의 프런트엔드로 보기

`delhi_aq.py`는 노르웨이 예제의 `build_forecast_module.py`와 같은 JSON 스키마(`steps[].cells[]`에 `windSpeed`, `windDirection`, `temperature`, `pressure`)를 쓰되, 셀마다 `pm25`, `pm10`, `aqi`를 추가로 넣습니다. 프런트엔드는 추가 키를 무시하므로 수정 없이도 바람·기온·기압 지도는 바로 뜹니다.

```bash
# (1) 델리 NCR 경계로 프런트엔드 복제 (ERA5 다운로드는 건너뜀)
cd msresearch-aurora/assets/inference/scripts
python3 setup_region.py --name "Delhi NCR" --lat-min 27.5 --lat-max 31.5 --lon-min 76 --lon-max 80 --skip-download

# (2) 예제 실행 결과의 JSON을 프런트엔드 데이터 폴더로 복사
cd ../../../..   # 저장소 루트
python examples/delhi_air_quality/delhi_aq.py --mode demo --date 2025-11-05 --out examples/delhi_air_quality/outputs
mkdir -p msresearch-aurora/assets/inference/delhi-ncr-example/frontend/public/data
cp examples/delhi_air_quality/outputs/frontend/*.json msresearch-aurora/assets/inference/delhi-ncr-example/frontend/public/data/

# (3) 지도 실행 후 http://localhost:5174 에서 "Aurora Predictions" 토글
cd msresearch-aurora/assets/inference/delhi-ncr-example/frontend
npm install && npm run dev
```

"CDS Observations" 토글에는 초기장(분석장)이, "Aurora Predictions" 토글에는 시간별 예측이 들어갑니다. 시간 슬라이더는 UTC로 표시됩니다(IST = UTC+5:30).

PM2.5/AQI를 지도 변수로 직접 선택하려면 복제된 프런트엔드에 다음 네 곳을 손보면 됩니다(모두 `delhi-ncr-example/frontend/src/`).

| 파일 | 수정 |
| - | - |
| `data/auroraForecast.ts` | `ForecastCell` 타입에 `pm25?: number; pm10?: number; aqi?: number;` 추가, `Forecast.variableRanges`에 `pm25?`, `aqi?` 추가 |
| `App.tsx` | `variableOptions`에 `"pm25", "aqi"` 추가; `variableLabels`/`valueUnits`에 라벨(`PM2.5`, `µg/m³`; `AQI (CPCB)`, `""`) 추가; `getVariableRange`와 `getCellValue`의 `switch`에 두 case 추가 |
| `utils/gridUtils.ts` | `getValue`의 `switch`에 `case "pm25": return cell.pm25 ?? 0;`, `case "aqi": return cell.aqi ?? 0;` 추가 |
| (선택) `App.tsx` | `formatLegendLabel`/`formatRangeValue`에서 `aqi`는 `toFixed(0)` 처리 |

### 2) 데이터 유틸리티

- `assets/inference/scripts/validate_grid.py`: 다른 타일 경계를 쓰고 싶을 때 16의 배수 격자인지 확인.
- `assets/inference/scripts/download_era5_subset.py`: 특정 지역·기간의 ERA5 서브셋을 내려받아 검증용 관측으로 활용.
- `assets/inference/scripts/check_divergence.py`, `validate_forecast.py`: 예측의 발산 여부와 RMSE/MAE/편향 점검. 이 예제의 출력은 `Batch.to_netcdf`로 저장하면 그대로 입력할 수 있습니다.

### 3) 파인튠 스타터로 가는 길

스킬은 "실제 문제에 쓰려면 파인튠"을 권장합니다(`docs/about-finetune.md`). 이 예제의 가장 큰 한계인 0.4° 해상도와 인도 지역 편향은 `starter-code/`의 학습 루프로 Air Pollution 모델을 인도 지역 CAMS 재분석 또는 격자화한 CPCB 관측에 적응시켜 줄일 수 있습니다. 시작은 다음과 같습니다.

```bash
cd msresearch-aurora
python3 initialization/initialize_starter_code.py --skip-tests   # 저장소 루트에 aurora-finetune/ 생성
cd ../aurora-finetune && uv sync
uv run pytest tests/test_training.py::test_finetuning_2t_var_pretrained --maxfail=1
uv run python -m vibe_tune_aurora.cli.train --help
```

`docs/finetuning-guide.md`(변수 확장, AMP, LoRA)와 이 저장소의 `docs/finetuning.md`(정규화 통계 등록, `strict=False` 로드)를 함께 참고하세요.

## 노트북

`example_delhi_air_quality.ipynb`는 같은 파이프라인을 스토리보드 순서대로 실행하며 표와 그래프를 보여줍니다. 저장소의 다른 예제처럼 `jupyter lab`에서 열면 됩니다.

## 주의

- Aurora 1.5는 IFS HRES T0로 파인튜닝된 모델입니다. 이 예제는 공식 1.5 예제와 같이 접근이 쉬운 ERA5를 입력으로 쓰므로 정확도가 보장되지 않습니다.
- Air Pollution 모델은 0.4° 해상도입니다. 지점별 수치는 격자 보간 결과이며 도로변 농도를 뜻하지 않습니다.
- 메시지의 GRAP 조치는 "해당 수준"에 대한 안내이며, 실제 조치 발효는 CAQM의 공식 공지를 따릅니다. 모든 메시지에 면책 문구가 포함됩니다.
