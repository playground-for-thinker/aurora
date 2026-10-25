<img src="docs/gifs/high_res_2t.gif" alt="고해상도(0.1도) 2m 기온 예측 gif" width="150px">&nbsp;&nbsp;&nbsp;<img src="docs/gifs/no2.gif" alt="이산화질소 예측 gif" width="150px">&nbsp;&nbsp;&nbsp;<img src="docs/gifs/wave_direction.gif" alt="해양 파향 예측 gif" width="150px">&nbsp;&nbsp;&nbsp;<img src="docs/gifs/tc_tracks.gif" alt="열대성 저기압 경로 예측 gif" width="220px">

# Aurora: 지구 시스템을 위한 파운데이션 모델

[![CI](https://github.com/microsoft/Aurora/actions/workflows/ci.yaml/badge.svg)](https://github.com/microsoft/Aurora/actions/workflows/ci.yaml)
[![Documentation](https://img.shields.io/badge/docs-latest-blue.svg)](https://microsoft.github.io/aurora)
[![Paper](https://img.shields.io/badge/arXiv-2405.13063-blue)](https://arxiv.org/abs/2405.13063)
[![DOI](https://zenodo.org/badge/828987595.svg)](https://doi.org/10.5281/zenodo.14983583)

지구 시스템 예측을 위한 Aurora 모델의 구현입니다. 영어 원본은 `README.md`입니다.

[논문 링크.](https://www.nature.com/articles/s41586-025-09005-y)

[자세한 사용법과 더 많은 예제는 문서를 참고하세요.](https://microsoft.github.io/aurora)
[ERA5 데이터로 모델을 실행하는 완전한 예제](https://microsoft.github.io/aurora/example_era5.html)로 바로 갈 수도 있습니다.

인용은 다음과 같이 해주세요:

```
@article{bodnar2025aurora,
    title = {A Foundation Model for the Earth System},
    author = {Cristian Bodnar and Wessel P. Bruinsma and Ana Lucic and Megan Stanley and Anna Allen and Johannes Brandstetter and Patrick Garvan and Maik Riechert and Jonathan A. Weyn and Haiyu Dong and Jayesh K. Gupta and Kit Thambiratnam and Alexander T. Archibald and Chun-Chieh Wu and Elizabeth Heider and Max Welling and Richard E. Turner and Paris Perdikaris},
    journal = {Nature},
    year = {2025},
    month = {May},
    day = {21},
    issn = {1476-4687},
    doi = {10.1038/s41586-025-09005-y},
    url = {https://doi.org/10.1038/s41586-025-09005-y},
}
```

목차:

- [Aurora란?](#aurora란)
- [시작하기](#시작하기)
- [기여하기](#기여하기)
- [라이선스](#라이선스)
- [보안](#보안)
- [책임 있는 AI 투명성 문서](#책임-있는-ai-투명성-문서)
- [상표](#상표)
- [FAQ](#faq)

Aurora를 상업적으로 활용하는 데 관심이 있다면 [AIWeatherClimate@microsoft.com](mailto:AIWeatherClimate@microsoft.com)으로 이메일을 보내주세요.
연구 관련 질문이나 이 코드에 대한 기술 지원은 [이슈를 열거나](https://github.com/microsoft/aurora/issues/new/choose) 논문 저자들에게 연락해 주세요.

## Aurora란?

Aurora는 기온과 같은 대기 변수를 예측할 수 있는 머신러닝 모델입니다.
_파운데이션 모델_이란 먼저 많은 데이터로 일반적으로 학습한 뒤,
비교적 적은 데이터로 특화된 대기 예측 과제에 적응시킬 수 있는 모델을 뜻합니다.
저희는 그런 특화 버전을 네 가지 제공합니다:
중해상도 기상 예측용 하나,
고해상도 기상 예측용 하나,
대기오염 예측용 하나,
해양 파랑 예측용 하나입니다.

## 시작하기

`pip`으로 설치:

```bash
pip install microsoft-aurora
```

또는 `conda` / `mamba`로 설치:

```bash
mamba install microsoft-aurora -c conda-forge
```

사전학습된 small 모델을 무작위 데이터로 실행:

```python
from datetime import datetime

import torch

from aurora import AuroraSmallPretrained, Batch, Metadata

model = AuroraSmallPretrained()
model.load_checkpoint()

batch = Batch(
    surf_vars={k: torch.randn(1, 2, 17, 32) for k in ("2t", "10u", "10v", "msl")},
    static_vars={k: torch.randn(17, 32) for k in ("lsm", "z", "slt")},
    atmos_vars={k: torch.randn(1, 2, 4, 17, 32) for k in ("z", "u", "v", "t", "q")},
    metadata=Metadata(
        lat=torch.linspace(90, -90, 17),
        lon=torch.linspace(0, 360, 32 + 1)[:-1],
        time=(datetime(2020, 6, 1, 12, 0),),
        atmos_levels=(100, 250, 500, 850),
    ),
)

prediction = model.forward(batch)

print(prediction.surf_vars["2t"])
```

이 코드는 500 MB를 다운로드합니다.

더 자세한 사용법과 사용 가능한 모델 목록은 [문서](https://microsoft.github.io/aurora)를 읽어주세요.

## 예제: 뉴델리 대기질 조기경보

`examples/delhi_air_quality/`에 Aurora 1.5(시간별 확산 기상)와 Aurora Air Pollution(오염물질 농도)을 결합해 델리 NCR의 CPCB AQI·GRAP 단계와 시민용 경보 메시지(힌디어/영어/한국어)를 만드는 예제가 있습니다.

[![Story Map · 한국어/English](https://img.shields.io/badge/Story%20Map-%ED%95%9C%EA%B5%AD%EC%96%B4%20%2F%20English-0b6e8f?logo=googlemaps&logoColor=white)](https://claude.ai/artifact/PKH8XS3B3Nb85WaVMbmZSW) [![Storyboard · 한국어/English](https://img.shields.io/badge/Storyboard-%ED%95%9C%EA%B5%AD%EC%96%B4%20%2F%20English-0b6e8f?logo=readme&logoColor=white)](https://claude.ai/artifact/6GkTNUq54pqXGZBVx7BGSE) [![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/playground-for-thinker/aurora/blob/main/examples/delhi_air_quality/example_delhi_air_quality.ipynb) [![Binder](https://mybinder.org/badge_logo.svg)](https://mybinder.org/v2/gh/playground-for-thinker/aurora/main?labpath=examples%2Fdelhi_air_quality%2Fexample_delhi_air_quality.ipynb)

- 스토리 맵 (지도 위 장면별 내러티브, 한국어 ⇄ English 전환): [https://claude.ai/artifact/PKH8XS3B3Nb85WaVMbmZSW](https://claude.ai/artifact/PKH8XS3B3Nb85WaVMbmZSW)
- 스토리보드 (한국어 ⇄ English 전환): [https://claude.ai/artifact/6GkTNUq54pqXGZBVx7BGSE](https://claude.ai/artifact/6GkTNUq54pqXGZBVx7BGSE)
- 노트북 바로 실행: [![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/playground-for-thinker/aurora/blob/main/examples/delhi_air_quality/example_delhi_air_quality.ipynb) [![Binder](https://mybinder.org/badge_logo.svg)](https://mybinder.org/v2/gh/playground-for-thinker/aurora/main?labpath=examples%2Fdelhi_air_quality%2Fexample_delhi_air_quality.ipynb)
- 설명과 실행 방법: [`examples/delhi_air_quality/README_kor.md`](examples/delhi_air_quality/README_kor.md)

## 기여하기

[`CONTRIBUTING.md`](CONTRIBUTING.md)를 참고하세요.

## 라이선스

[`LICENSE.txt`](LICENSE.txt)를 참고하세요.

## 보안

[`SECURITY.md`](SECURITY.md)를 참고하세요.

## 책임 있는 AI 투명성 문서

AI 시스템은 기술뿐 아니라 그것을 사용하는 사람, 영향을 받는 사람, 그리고 배포되는 환경까지 포함합니다.
의도된 목적에 적합한 시스템을 만들려면 기술이 어떻게 작동하는지, 그 능력과 한계는 무엇인지, 최상의 성능을 어떻게 얻는지 이해해야 합니다.
Microsoft는 AI 원칙을 실천하기 위해 폭넓게 노력하고 있습니다.
자세한 내용은 [Microsoft의 책임 있는 AI 원칙](https://www.microsoft.com/en-us/ai/responsible-ai)을 참고하세요.

### 이 코드의 사용
이 코드를 공개하는 목적은
(1) 논문의 재현성을 높이고
(2) 대기 예측을 위한 파운데이션 모델 연구를 지원하고 가속하는 것입니다.
이 코드는 비학술적 목적으로 개발되거나 테스트되지 않았으므로, 그러한 용도로만, 전적으로 사용자 책임하에 사용해야 합니다.

### 의도된 용도
Aurora는 중해상도 및 고해상도 기상 예측, 대기오염 예측, 해양 파랑 예측, 그리고 전 지구 환경 모델링 과제를 위해 만들어졌습니다.
파운데이션 모델 아키텍처 덕분에 비교적 제한된 과제별 학습 데이터로 특화된 대기 예측 과제에 적응시킬 수 있습니다.

### 범위 밖 사용 사례
Aurora는 전문가 검토 없는 직접적인 운영 의사결정, 예측 정확도 보장이 필요한 응용, 또는 환경과 무관한 예측 과제를 위해 설계되거나 평가되지 않았습니다.
안전이 중요한 계획이나 자동화된 의사결정 파이프라인에 사용할 때는 적절한 도메인 검증이 함께 이루어져야 합니다.

### 한계
Aurora는 미래의 기상, 대기오염, 해양 파랑을 정확히 예측하도록 학습되었지만,
신경망 기반이므로 예측이 항상 정확하다는 엄격한 보장은 없습니다.
입력을 변경하거나, 학습 세트에 없던 샘플을 주거나,
학습 세트에 있었지만 단순히 운이 나쁜 샘플을 주는 경우에도 임의로 나쁜 예측이 나올 수 있습니다.
또한 Aurora는 매우 다양한 데이터셋으로 학습되었지만, 그중 어느 데이터셋에 존재하는 편향을 물려받을 가능성이 있습니다.
Aurora와 같은 예측 시스템은 기상 예측 파이프라인의 한 조각일 뿐이며,
그 출력은 사람이나 기업이 운영을 계획하는 데 직접 사용되도록 만들어진 것이 아닙니다.
운영에 유용해지려면 일련의 추가 검증 테스트가 필요합니다.

위에 더해, 여기서 공개된 모델은 내부에서 원래 개발된 모델의 간소화 버전입니다.
최대한 꼼꼼히 작업했지만, 공개된 모델이 원래 모델과 미묘하고 의도치 않은 방식으로 다를 수 있습니다.
이는 예측 성능에 영향을 줄 수 있습니다.

### 책임 있는 AI 고려사항
Aurora는 연구용 예측 모델이며 운영 기상 서비스로 취급해서는 안 됩니다.
확립된 벤치마크에서 전통적인 수치 모델과 비슷하거나 더 나을 수 있지만,
분포 밖 조건(예: 희귀한 극한 현상, 레짐 전환, 기반 재분석·시뮬레이션의 과거 신뢰도가 낮은 지역/변수)에서는 신뢰도가 떨어질 수 있습니다.
사용자가 불확실성, 앙상블 스프레드, 학습 데이터의 알려진 한계를 간과하면 출력이 잘못 해석될 수도 있습니다.

주요 책임 있는 AI 위험은
(1) 비전문가의 의도치 않은 사용과
(2) 도메인 검증 없이 중대한 의사결정(예: 긴급 대응, 핵심 인프라 운영, 인명 안전 계획)에 하류에서 사용하는 것입니다.
이러한 위험을 줄이기 위해 개발자는:
이 릴리스가 연구 평가와 재현성을 위한 것임을 명확히 알리고;
출력이 실제 의사결정에 반영되기 전에 도메인 전문가 검토를 요구하고;
초기 조건이 신뢰할 수 있는 출처(예: 공인 기상 기관 및 데이터 제공자)에서 온 것인지 확인하는 기본적인 입력 검증을 구현하고;
의도한 응용에 해당하는 특정 지역, 예측 기간, 변수에 대해 공인된 물리 모델링 시스템과 성능을 비교해야 합니다.

Aurora는 전문가 분석을 위한 의사결정 지원 구성요소로 통합하는 것이 가장 좋으며,
행동을 자동으로 촉발하는 완전 자율 트리거로 쓰여서는 안 됩니다.
위험이 높은 시나리오에서는 사람의 검토(human-in-the-loop), 보수적인 경보 임계값, 보정/검증 테스트,
입력 소스나 전·후처리를 바꿀 때의 지속적인 드리프트 모니터링과 같은 추가 안전장치를 적용하세요.

### 데이터
코드에 포함된 모델들은 다양한 공개 데이터로 학습되었습니다.
모든 데이터에 대한 설명과 다운로드 링크는 [논문의 Supplementary C](https://arxiv.org/pdf/2405.13063)에 있습니다.
체크포인트에는 ERA5, CMIP6(CMCC-CM2-VHR4 및 ECMWF-IFS-HR), HRES 예보, GFS T0, GFS 예보,
HRES T0,
HRES 분석,
HRES-WAM 분석,
CAMS 재분석 및 CAMS 분석 데이터가 포함되어 있습니다.

### 평가
모든 버전의 Aurora는 학습 중 보지 않은 데이터에 대한 예측을 평가하여 광범위하게 검증되었습니다.
이 평가는 RMSE(평균 제곱근 오차)와 ACC(아노말리 상관계수) 같은 정확도 척도를 비교할 뿐 아니라,
극한 고온·저온 같은 극한 상황과 2023년 폭풍 Ciarán 같은 희귀 사건에서의 동작도 살핍니다.
이 평가가 [논문](https://arxiv.org/pdf/2405.13063)의 주요 주제입니다.

*참고: 이 파일에 포함된 문서는 정보 제공 목적이며 적용되는 라이선스 조건을 대체하지 않습니다.*

## 상표

이 프로젝트에는 프로젝트, 제품, 서비스의 상표나 로고가 포함될 수 있습니다.
Microsoft 상표나 로고의 승인된 사용은 [Microsoft 상표 및 브랜드 가이드라인](https://www.microsoft.com/en-us/legal/intellectualproperty/trademarks/usage/general)을 따라야 합니다.
이 프로젝트의 수정 버전에서 Microsoft 상표나 로고를 사용할 때 혼동을 일으키거나 Microsoft의 후원을 암시해서는 안 됩니다.
제3자 상표나 로고의 사용은 해당 제3자의 정책을 따릅니다.

## FAQ

### 로컬 개발을 위해 저장소를 어떻게 설정하나요?

먼저 저장소를 편집 가능 모드로 설치하고 `pre-commit`을 설정합니다:

```bash
make install
```

테스트를 실행하고 커버리지를 출력하려면:

```bash
make test
```

그런 다음 `htmlcov/index.html`을 열어 브라우저에서 커버리지를 살펴볼 수 있습니다.

문서를 로컬에서 빌드하려면:

```bash
make docs
```

문서를 로컬에서 보려면 브라우저에서 `docs/_build/index.html`을 여세요.
