# Delhi Smog Story Map (JupyterGIS · notebook.link)

델리 대기질 조기경보 예제의 스토리 맵을 **JupyterGIS 문서(`.jGIS`)** 로 만든 폴더입니다. Claude 등 특정 서비스에 묶이지 않고,
[JupyterGIS](https://github.com/geojupyter/jupytergis)가 설치된 JupyterLab·JupyterLite, 그리고 [notebook.link](https://notebook.link)에서 그대로 열립니다.

The story map of the Delhi air-quality example as a **JupyterGIS document (`.jGIS`)**. It is not tied to Claude or any other
hosted service: open it in JupyterLab/JupyterLite with [JupyterGIS](https://github.com/geojupyter/jupytergis) installed, or on
[notebook.link](https://notebook.link).

| 파일 / File | 내용 / Content |
| - | - |
| `delhi_aq_storymap_ko.jGIS` | 한국어 스토리 맵 (19 장면) · Korean story map (19 scenes) |
| `delhi_aq_storymap_en.jGIS` | English story map (19 scenes) |
| `storyboard_ko.ipynb`, `storyboard_en.ipynb` | 발표용 스토리보드 슬라이드 12장 (Specta slides): 왼쪽 그림, 오른쪽 설명, 코드 없음 · 12-slide storyboard for a general audience: figure left, narration right, no code |
| `img/{ko,en}/*.png` | 슬라이드 그림 (노트북에도 내장됨) · slide figures (also embedded in the notebooks) |
| `data/*.geojson` | 두 문서가 공유하는 레이어 · layers shared by both documents: AQI tile at 4 forecast hours, 10 m wind, stagnation probability, sites, Delhi NCT, NCR tile, 0.4° cell |
| `environment.yml`, `nblink-lock.json` | notebook.link 환경 (`xeus-python`, `jupytergis-lite`, `specta`, `matplotlib`) · environment and lock file read by notebook.link |
| `jupyter-lite.json` | 앱 이름과 Specta 상단 바 설정 · app name and Specta top-bar settings |

## 열기 / Open

notebook.link은 GitHub 저장소 URL 앞에 `notebook.link/`를 붙이면 열립니다. 이 폴더가 `storymap` 브랜치의 루트로 발행되어 있을 때
(아래 "발행" 참고) 링크는 다음과 같습니다. notebook.link prefixes a GitHub URL; with this folder published as the root of the
`storymap` branch (see "Publish" below) the links are:

| | URL |
| - | - |
| 스토리 맵 · 한국어 (Specta 전체 화면) | `https://notebook.link/github/playground-for-thinker/aurora/tree/storymap/specta/?path=delhi_aq_storymap_ko.jGIS` |
| Story map · English (Specta, full screen) | `https://notebook.link/github/playground-for-thinker/aurora/tree/storymap/specta/?path=delhi_aq_storymap_en.jGIS` |
| JupyterGIS 편집기 · editor (layers, segments, Preview Mode) | `https://notebook.link/github/playground-for-thinker/aurora/tree/storymap/lab/?path=delhi_aq_storymap_ko.jGIS` |
| 스토리보드 · 한국어 (Specta 슬라이드, 장마다 English ⇄ 한국어 전환) | `https://notebook.link/github/playground-for-thinker/aurora/tree/storymap/specta/?path=storyboard_ko.ipynb` |
| Storyboard · English (Specta slides) | `https://notebook.link/github/playground-for-thinker/aurora/tree/storymap/specta/?path=storyboard_en.ipynb` |
| JupyterLab 파일 탐색기 · file browser | `https://notebook.link/github/playground-for-thinker/aurora/tree/storymap/lab/` |

처음 열 때 notebook.link가 `environment.yml` + `nblink-lock.json`을 읽어 WebAssembly 패키지를 설치합니다(수십 초). 편집기에서는 왼쪽
*Layers*/*Segments* 패널과 오른쪽 *Story* 패널이 보이고, ▶ 로 장면을 넘기면 지도가 이동하며 레이어가 바뀝니다. 지도 장면의 ⓘ 버튼
(Identify)으로 셀·지점 값을 클릭해 볼 수 있습니다.

On first start notebook.link reads `environment.yml` + `nblink-lock.json` and installs the WebAssembly packages (tens of seconds).
In the editor the left *Layers*/*Segments* panels and the right *Story* panel appear; ▶ moves through the scenes, panning the map
and toggling layers. In map scenes the ⓘ (Identify) button lets you click cells and sites for their values.

로컬 JupyterLab: `pip install jupytergis` 후 `.jGIS` 파일을 더블클릭. Local JupyterLab: `pip install jupytergis`, then double-click a `.jGIS` file.

## 다시 만들기 / Rebuild

```bash
cd examples/delhi_air_quality
python build_storymap_data.py outputs/hybrid_2025-11-05 --finetune-log outputs/hybrid_2025-11-05/finetune_smoke.log  # storymap_data.js
python build_storymap_jgis.py                       # storymap/*.jGIS + storymap/data/*.geojson
python build_storymap_jgis.py --story-type "Vertical Scroll"   # scrolling layout instead of guided ▶ steps
python build_storyboard_slides.py                  # storymap/storyboard_{ko,en}.ipynb + img/ (12 slides, figures via matplotlib + Nanum fonts)
```

`build_storymap_jgis.py` reads `storymap_data.js` (the same data file as `storymap.html`) and writes plain JSON following the
JupyterGIS project schema 0.6.0. Every scene is a `StorySegmentLayer` with an extent, markdown and layer-visibility overrides, so the
file can also be edited in the JupyterGIS UI and saved back.

The storyboard notebooks contain markdown cells only (one per slide, figures embedded as data URIs), so Specta shows them without starting a kernel; in the JupyterLab view they open as a normal notebook.

After editing `environment.yml`: `pip install mambajs && mambajs create-lock environment.yml nblink-lock.json`.

## 발행 / Publish

notebook.link은 참조한 커밋의 저장소 크기를 50 MB 이하로 요구합니다. 이 저장소의 `main`은 그보다 크므로(`msresearch-aurora/`),
이 폴더만 담은 `storymap` 브랜치를 발행합니다. notebook.link requires the referenced tree to stay under 50 MB; `main` is larger
than that, so this folder is published on its own as the `storymap` branch:

```bash
./examples/delhi_air_quality/publish_storymap_branch.sh          # git subtree split → branch "storymap", then push
```

짧은 별칭 링크(`https://notebook.link/@<user>/<alias>`)는 notebook.link에 로그인 → *Links → New Link → Repository* 에서 저장소,
참조 `storymap`, *Document path* `delhi_aq_storymap_ko.jGIS`, 인터페이스 *Presentation* 을 선택해 만들 수 있습니다. A short alias
link can be created from the notebook.link dashboard (*Links → New Link → Repository*, reference `storymap`, document path
`delhi_aq_storymap_ko.jGIS`, interface *Presentation*).
