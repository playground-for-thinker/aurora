"""Copyright (c) Microsoft Corporation. Licensed under the MIT license.

Scene text shared by the storyboard slides (`build_storyboard_slides.py`) and the JupyterGIS story
map (`build_storymap_jgis.py`), written for a general audience: no code, file names or flags.

`scenes(D, lang)` returns one dict per scene with the narration as HTML (sizes in `em`, so the
caller sets the base size), a figure descriptor for the slides and a map specification for the
story map. Boxes separate what *this system* already produces (teal) from what a *government or
city* has to own (amber); messages are phone bubbles. Numbers come from `storymap_data.js`.
"""

from __future__ import annotations

from datetime import datetime, timedelta

NBLINK = "https://notebook.link/github/playground-for-thinker/aurora/tree/storymap"
TEAL, AMBER, INK, MUTED, PAPER = "#0b6e8f", "#b7791f", "#1e293b", "#64748b", "#f8fafc"
HOTSPOT = "Anand Vihar"


def text(lang: str, ko: str, en: str) -> str:
    return ko if lang == "ko" else en


def ist(times: list[str], i: int, lang: str) -> str:
    t = datetime.fromisoformat(times[i]) + timedelta(hours=5, minutes=30)
    return f"{t.month}월 {t.day}일 {t:%H:%M}" if lang == "ko" else f"{t.day} {t:%b} {t:%H:%M}"


def esc(s: str) -> str:
    # "~" between two numbers is read as strikethrough by the markdown renderer.
    return s.replace("~", "–").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


# ------------------------------------------------------------------------------------ HTML pieces
def ul(items: list[str]) -> str:
    return (
        "<ul style='margin:0 0 .5em 1.1em; padding:0;'>"
        + "".join(f"<li style='margin:0 0 .35em 0;'>{i}</li>" for i in items)
        + "</ul>"
    )


def note(body: str) -> str:
    return f"<div style='background:{PAPER}; border:1px solid #cbd5e1; padding:.45em .7em; border-radius:8px; margin:.5em 0; font-size:.9em; color:{INK};'>{body}</div>"


def sys_box(lang: str, body: str) -> str:
    return (f"<div style='background:#e6f3f7; border-left:6px solid {TEAL}; padding:.45em .7em; border-radius:8px; margin:.5em 0; font-size:.9em; color:{INK};'>"
            f"<b style='color:{TEAL};'>{text(lang, '현 시스템이 보여주는 것', 'What this system shows')}</b> · {body}</div>")  # fmt: skip


def gov_box(lang: str, body: str) -> str:
    return (f"<div style='background:#fff4e0; border-left:6px solid {AMBER}; padding:.45em .7em; border-radius:8px; margin:.5em 0; font-size:.9em; color:{INK};'>"
            f"<b style='color:{AMBER};'>{text(lang, '정부·시가 할 일', 'Government and city')}</b> · {body}</div>")  # fmt: skip


def phone(label: str, body: str, dark: bool = True) -> str:
    bg, fg = ("#0f172a", "#f8fafc") if dark else ("#e2e8f0", INK)
    return (f"<div style='background:{bg}; color:{fg}; padding:.5em .8em; border-radius:14px; margin:.5em 0; font-size:.85em; line-height:1.4;'>"
            f"<div style='font-size:.75em; opacity:.7; margin-bottom:.15em;'>📱 {label}</div>{esc(body)}</div>")  # fmt: skip


def table(header: list[str], rows: list[list[str]], align: str | None = None) -> str:
    al = (align or "l" * len(header)).ljust(len(header), "l")
    th = "".join(
        f"<th style='text-align:{'right' if al[k] == 'r' else 'left'}; padding:.3em .45em; border-bottom:2px solid rgba(100,116,139,.5); color:{MUTED}; font-size:.9em;'>{h}</th>"
        for k, h in enumerate(header)
    )
    trs = "".join(
        "<tr>"
        + "".join(
            f"<td style='text-align:{'right' if al[k] == 'r' else 'left'}; padding:.3em .45em; border-bottom:1px solid rgba(100,116,139,.25); vertical-align:top;'>{c}</td>"
            for k, c in enumerate(r)
        )
        + "</tr>"
        for r in rows
    )
    return f"<table style='border-collapse:collapse; width:100%; table-layout:fixed; word-break:break-word; font-size:.8em; margin:.4em 0 .6em;'><thead><tr>{th}</tr></thead><tbody>{trs}</tbody></table>"


# ------------------------------------------------------------------------------------ scenes
def scenes(D: dict, lang: str) -> list[dict]:
    """Twelve scenes. Each: key, eyebrow, title, body (HTML), fig (descriptor), map (story-map spec)."""
    times = D["times"]
    M = D.get("messages") or {}
    PV = D.get("provenance") or {}
    met_real = "Aurora" in (PV.get("meteorology") or "")
    pm_real = "Aurora" in (PV.get("pollutants") or "")
    ens_real = "Aurora" in (PV.get("ensemble") or "")
    av = D["sites"][HOTSPOT]
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
    tag_ens = (
        t("앙상블: Aurora 1.5 Ensemble", "Ensemble: Aurora 1.5 Ensemble")
        if ens_real
        else t("앙상블: 시뮬레이션", "Ensemble: simulated")
    )
    S: list[dict] = []

    def add(
        key,
        eyebrow,
        title,
        body,
        fig,
        view,
        aqi=None,
        wind=None,
        grid=False,
        coarse=False,
        prob=False,
        marker=False,
    ):
        S.append({"key": key, "eyebrow": eyebrow, "title": title, "body": body, "fig": fig,
                  "map": {"view": view, "aqi": aqi, "wind": wind, "grid": grid, "coarse": coarse, "prob": prob, "marker": marker}})  # fmt: skip

    add(
        "cover",
        t("Aurora 기상 AI · 델리 대기질 경보", "Aurora Earth-system AI · Delhi air-quality alerts"),
        t(
            "시민에게 닿는 한 줄의 대기질 경보",
            "One line of air-quality warning that reaches a citizen",
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
                    "예측을 인도 공식 기준(CPCB 대기질지수 AQI, 단계별 조치 GRAP)으로 바꿔 힌디어·영어·한국어 메시지로 만듭니다.",
                    "The forecast becomes India's official scale (the CPCB air-quality index AQI and the staged GRAP measures) and messages in Hindi, English and Korean.",
                ),
                t(
                    "이 이야기: 왜 델리인가 → Aurora가 무엇을 계산하는가 → 시민에게 어떻게 닿는가 → 시스템과 정부의 역할.",
                    "This story: why Delhi → what Aurora computes → how it reaches citizens → what the system does and what government must own.",
                ),
            ]
        )
        + f"<div style='font-size:.8em; color:{MUTED};'>{tag_met} · {tag_pm} · {t('초기 시각', 'initial time')} {PV.get('init_time', '').replace('T', ' ')} UTC</div>",
        (
            "map",
            {
                "step": 35,
                "view": "delhi",
                "title": t(
                    f"예측 AQI · {ist(times, 35, lang)} IST (가장 심한 시각)",
                    f"Forecast AQI · {ist(times, 35, lang)} IST (worst hour)",
                ),
            },
        ),
        "world",
        aqi="h35",
    )

    add(
        "background",
        t("1 · 배경", "1 · Background"),
        t("왜 델리이고, 왜 11월인가", "Why Delhi, why November"),
        ul(
            [
                t(
                    "델리 수도권은 매년 10월 말–1월에 세계 최악 수준의 미세먼지를 겪습니다. 볏짚 소각, 디왈리 폭죽, 교통·건설·발전 배출이 겹칩니다.",
                    "Delhi-NCR suffers some of the world's worst particulate pollution from late October to January: stubble burning, Diwali fireworks, traffic, construction and power plants.",
                ),
                t(
                    "겨울밤에는 <b>혼합층(오염이 섞이는 공기층)이 100–300 m로 낮아지고 바람이 약해져</b> 오염이 지표 근처에 갇힙니다. 같은 배출량이라도 밤이 더 나쁩니다.",
                    "On winter nights the <b>mixing layer (the layer of air pollution mixes into) drops to 100–300 m and winds die down</b>, trapping pollution near the ground. Same emissions, worse nights.",
                ),
                t(
                    "인도에는 이미 제도가 있습니다: 국가 AQI(CPCB)와 단계별 조치 GRAP(건설 중단, 차량 제한, 원격수업…).",
                    "India already has the institutions: a national AQI (CPCB) and the staged GRAP measures (construction bans, vehicle limits, online classes…).",
                ),
            ]
        )
        + note(
            t(
                '핵심 질문은 "얼마나 나빠질까"가 아니라 <b>"언제, 어디서, 왜 나빠지고, 시민은 무엇을 해야 하는가"</b>를 12–48시간 앞서 전하는 것입니다. 지도의 사각형이 이 이야기가 다루는 델리 수도권입니다.',
                'The question is not "how bad" but <b>"when, where, why, and what should citizens do"</b>, 12 to 48 hours ahead. The square on the map is the Delhi region this story covers.',
            )
        ),
        ("mixing", {}),
        "india",
    )

    add(
        "system",
        t("2 · 시스템", "2 · System") + f" · {tag_met} · {tag_pm}",
        t("Aurora가 두 번 등장한다", "Aurora appears twice"),
        ul(
            [
                t(
                    "<b>Aurora</b>는 위성·관측 기반 분석 자료를 입력받아 지구의 날씨와 대기 성분을 예측하는 AI 모델입니다. 컴퓨터 한 대로 수 분 안에 48시간을 예측합니다.",
                    "<b>Aurora</b> is an AI model that takes global analyses and forecasts the Earth's weather and atmospheric composition. One computer gives 48 hours in minutes.",
                ),
                t(
                    "<b>대기오염 모델</b>은 농도를 직접 예측하지만 12시간 간격입니다. <b>Aurora 1.5</b>는 오염을 예측하지 않지만 시간별 바람과 혼합층을 줍니다.",
                    "The <b>air-pollution model</b> predicts concentrations directly but every 12 hours. <b>Aurora 1.5</b> predicts no pollutants but gives hourly wind and mixing height.",
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
                "두 모델 실행 → 10개 지점의 AQI·GRAP 수준·정체 시간 → 메시지 초안까지 자동. 지도의 가는 격자가 모델이 계산하는 칸(0.25°)입니다.",
                "both models → AQI, GRAP level and stagnant hours at 10 sites → draft messages, all automatic. The thin grid on the map is the model's 0.25° cells.",
            ),
        ),
        ("system", {}),
        "tile",
        aqi="h00",
        grid=True,
    )

    add(
        "timeline",
        t("3 · 하루의 흐름", "3 · One day"),
        t(
            "48시간: 저녁 경보에서 아침 업데이트까지",
            "48 hours: from the evening alert to the morning update",
        ),
        table(
            [
                t("시각 (IST)", "Time (IST)"),
                t("장면", "Scene"),
                t("무슨 일이 일어나는가", "What happens"),
            ],
            [
                [
                    "17:30",
                    t("예측 실행", "Forecast run"),
                    t(
                        "정오(UTC) 분석 자료 확보, 두 모델 실행 (약 10분)",
                        "noon (UTC) analyses arrive, both models run (about 10 min)",
                    ),
                ],
                [
                    "18:00",
                    t("저녁 경보", "Evening alert"),
                    t("지점별 한 줄 메시지, 운영자 브리핑", "one line per site, operator briefing"),
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
                        "새 자료로 재실행, 등교·출근 전 발송",
                        "re-run on new data, sent before school and commute",
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
        )
        + f"<div style='font-size:.8em; color:{MUTED};'>{t('그래프: Anand Vihar의 AQI와 혼합층. 파란 띠가 정체 시간(바람 10 km/h 미만, 혼합층 500 m 미만).', 'Chart: AQI and mixing height at Anand Vihar; blue bands are stagnant hours (wind below 10 km/h, mixing height below 500 m).')}</div>",
        ("timeline", {}),
        "delhi",
        aqi="h00",
    )

    add(
        "evening",
        t("4 · 저녁", "4 · Evening") + f" · {tag_pm}",
        t(f"{ist(times, 0, lang)} IST, 저녁 경보", f"{ist(times, 0, lang)} IST, the evening alert"),
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
        (
            "map",
            {
                "step": 0,
                "view": "delhi",
                "title": t(
                    f"예측 AQI · {ist(times, 0, lang)} IST",
                    f"Forecast AQI · {ist(times, 0, lang)} IST",
                ),
            },
        ),
        "delhi",
        aqi="h00",
    )

    add(
        "night",
        t("5 · 밤", "5 · Night") + f" · {tag_met}",
        t(
            f"{ist(times, 8, lang)} IST, 정체가 시작된다",
            f"{ist(times, 8, lang)} IST, stagnation sets in",
        ),
        ul(
            [
                t(
                    f"Aurora 1.5가 예측한 첫째 밤 Anand Vihar의 혼합층은 최저 <b>{night_blh} m</b>, 풍속 중앙값 <b>{night_wind:.1f} km/h</b>. 지도의 짧은 선이 그 바람(불어가는 방향, 길이는 세기)입니다.",
                    f"For the first night Aurora 1.5 puts Anand Vihar's mixing layer as low as <b>{night_blh} m</b> with a median wind of <b>{night_wind:.1f} km/h</b>; the short lines on the map are that wind (direction it blows, length its strength).",
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
                "시간별 정체 판정은 Aurora 1.5가 실제 초기장으로 계산한 결과입니다.",
                "the hourly stagnation flags are real Aurora 1.5 output from a real initial condition.",
            ),
        ),
        (
            "map",
            {
                "step": 8,
                "view": "delhi",
                "title": t(
                    f"AQI와 10 m 바람 · {ist(times, 8, lang)} IST",
                    f"AQI and 10 m wind · {ist(times, 8, lang)} IST",
                ),
                "wind": True,
                "labels": False,
            },
        ),
        "delhi",
        aqi="h08",
        wind="h08",
    )

    add(
        "peak",
        t("6 · 새벽", "6 · Pre-dawn") + f" · {tag_pm}",
        t(
            f"{ist(times, 35, lang)} IST, 가장 심각한 곳",
            f"{ist(times, 35, lang)} IST, the worst-hit site",
        ),
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
            t("민감군·운영자용 상세 (일부)", "Detail for sensitive groups and operators (excerpt)"),
            "\n".join(
                [ln for ln in ((M.get(lang) or {}).get("long", "")).split("\n") if ln.strip()][1:4]
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
        ("peaks", {}),
        "hotspot",
        aqi="h35",
        wind="h35",
        marker=True,
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
        add(
            "probability",
            t("7 · 불확실성", "7 · Uncertainty") + f" · {tag_ens}",
            t('"정체 확률 80%"로 말하기', 'Saying "80% chance of stagnation"'),
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
                align="lrrr",
            )
            + sys_box(
                lang,
                t(
                    "앙상블 실행과 확률 계산까지 자동. 확률을 문구로 바꾸는 기준은 보건 당국과 정해야 합니다.",
                    "the ensemble run and the probabilities are automatic; the thresholds that turn them into wording are agreed with health authorities.",
                ),
            ),
            (
                "map",
                {
                    "step": 35,
                    "view": "delhi",
                    "title": t(
                        f"정체 확률 · {ist(times, 35, lang)} IST (진할수록 높음)",
                        f"Stagnation probability · {ist(times, 35, lang)} IST (darker = higher)",
                    ),
                    "prob": True,
                },
            ),
            "delhi",
            prob=True,
        )

    add(
        "message",
        t("8 · 메시지 설계", "8 · Message design"),
        t(
            "160자 안에 무엇·언제·어디·왜·어떻게",
            "What, when, where, why and how in 160 characters",
        ),
        ul(
            [
                t(
                    "<b>무엇</b>(수치+CPCB 범주) · <b>언제</b>(정점 시각) · <b>어디</b>(지점) · <b>어떻게</b>(행동 1–2개). 짧은 문장은 문자·푸시, 긴 문장은 앱·브리핑용.",
                    "<b>What</b> (value + CPCB category) · <b>when</b> (peak time) · <b>where</b> (site) · <b>how</b> (one or two actions). Short for SMS/push, long for the app and briefings.",
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
                "문구는 보건 전문가가 검수·수정할 수 있게 코드 밖에 둡니다. 최종 문안의 책임은 발령 기관에 있습니다.",
                "the wording is kept where health experts can review and edit it; the issuing authority owns the final text.",
            ),
        ),
        ("message", {}),
        "delhi",
        aqi="h35",
        marker=True,
    )

    add(
        "roles",
        t("9 · 역할 구분", "9 · Who does what"),
        t(
            "시스템이 보여주는 것과 정부·시가 맡아야 할 것",
            "What the system shows and what government and city must own",
        ),
        sys_box(
            lang,
            t(
                "예측 → AQI·GRAP 수준 → 정체 시간·확률 → 메시지 초안·브리핑·지도. 12시간마다 자동 재발행. 우편번호→지점 매핑 시연.",
                "forecast → AQI and GRAP level → stagnant hours and probability → draft messages, briefing, maps. Automatic re-issue every 12 h. Postal code → site mapping demonstrated.",
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
        ("roles", {}),
        "delhi",
        aqi="h35",
    )

    add(
        "limits",
        t("10 · 한계와 책임", "10 · Limits and responsibility") + f" · {tag_pm}",
        t(
            "해상도의 진실, 그리고 책임 있는 사용",
            "The truth about resolution, and responsible use",
        ),
        ul(
            [
                t(
                    "큰 사각형이 대기오염 모델의 칸 하나(0.4°). 델리 대부분이 두세 칸에 들어갑니다. <b>지점 간 차이는 보간 결과</b>이지 도로변 측정값이 아닙니다.",
                    "The large square is one cell (0.4°) of the air-pollution model; most of Delhi fits in two or three. <b>Differences between sites are interpolation</b>, not roadside measurements.",
                ),
                t(
                    "시간별 농도 곡선은 12시간 예측을 이은 것이고, 시간별 구조의 근거는 Aurora 1.5의 기상입니다. 메시지에도 그렇게 적습니다.",
                    "The hourly concentration curve joins 12-hour forecasts; the hourly structure comes from Aurora 1.5's weather, and the messages say so.",
                ),
                t(
                    "이 실행에서 농도는 <b>합성 예시</b>입니다(농도 자료는 계정이 필요). 정체 시간대는 실제 모델 결과입니다.",
                    "In this run the concentrations are a <b>synthetic example</b> (the pollutant data needs an account); the stagnant hours are real model output.",
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
                "실제 서비스에는 관측소별 보정이나 지역 자료로의 추가 학습이 필요하며, 이는 공식 관측 데이터 제공이 전제입니다.",
                "a real service needs per-station correction or further training on regional data, which presupposes access to the official observations.",
            ),
        ),
        (
            "map",
            {
                "step": 35,
                "view": "delhi",
                "title": t(
                    "대기오염 모델의 0.4° 칸 하나와 10개 지점",
                    "One 0.4° cell of the air-pollution model and the ten sites",
                ),
                "coarse": True,
                "grid": True,
            },
        ),
        "delhi",
        aqi="h35",
        coarse=True,
        grid=True,
    )

    add(
        "next",
        t("11 · 다음 단계", "11 · Next steps"),
        t("실행해 본 것과 남은 것", "Done, and still to do"),
        ul(
            [
                t(
                    "불확실성(앙상블), 관측 보정 절차, 학습 절차 점검, 발송 어댑터, 자동화의 다섯 항목은 이 예제에서 실행해 봤습니다.",
                    "Five items were run in this example: ensemble uncertainty, the correction procedure, a training-procedure check, the delivery adapter and automation.",
                ),
                t(
                    "남은 것은 모두 <b>정부·시와의 협력</b>이 전제입니다: 공식 관측 연결, 지역 자료 추가 학습, 농도 자료 연계.",
                    "Everything that remains presupposes <b>cooperation with government and city</b>: official observations, further training on regional data, pollutant data.",
                ),
                t(
                    '한 줄 요약: Aurora는 "언제, 어디서, 왜"를 12–48시간 앞서 계산해 주고, 그것을 시민의 행동으로 바꾸는 마지막 구간은 제도와 채널의 몫입니다.',
                    'In one line: Aurora computes "when, where and why" 12 to 48 hours ahead; turning that into citizens\' actions is the job of institutions and channels.',
                ),
            ]
        )
        + note(
            t(
                f"발표용 슬라이드: <a href='{NBLINK}/specta/?path=storyboard_ko.ipynb'>한국어</a> · <a href='{NBLINK}/specta/?path=storyboard_en.ipynb'>English</a> · 이 지도 이야기의 영어판: <a href='{NBLINK}/specta/?path=delhi_aq_storymap_en.jGIS'>English story map</a>",
                f"Slides: <a href='{NBLINK}/specta/?path=storyboard_en.ipynb'>English</a> · <a href='{NBLINK}/specta/?path=storyboard_ko.ipynb'>한국어</a> · Korean version of this map story: <a href='{NBLINK}/specta/?path=delhi_aq_storymap_ko.jGIS'>한국어 스토리 맵</a>",
            )
        ),
        ("roadmap", {}),
        "delhi",
        aqi="h35",
    )
    return S
