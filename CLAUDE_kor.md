# CLAUDE.md (한국어)

이 파일은 Claude Code(claude.ai/code)가 이 저장소의 코드를 다룰 때 참고하는 안내서입니다. 영어 원본은 `CLAUDE.md`입니다.

## 이 저장소는 무엇인가

`microsoft-aurora`: 지구 시스템 예측(기상, 대기오염, 해양 파랑)을 위한 파운데이션 모델 Aurora의 PyTorch 구현입니다. 사전학습 체크포인트는 HuggingFace(`microsoft/aurora`)에 있으며 `model.load_checkpoint()` 호출 시 필요할 때 내려받습니다. 일부 테스트도 같은 저장소에서 테스트 픽스처를 내려받으므로, 전체 테스트를 돌리려면 네트워크 연결이 필요합니다.

## 명령어

```bash
make install        # pip install -e ".[dev]" + pre-commit install
make test           # pytest tests -v --cov=aurora (HTML 커버리지는 htmlcov/)
make docs           # jupyter-book build docs; 결과물은 docs/_build/html

pytest tests/v1p5/test_rollout_substepping.py            # 파일 하나
pytest tests/test_model.py::test_aurora_small             # 테스트 하나
pytest tests -k "not test_aurora_small"                   # 느린 체크포인트 다운로드 테스트 제외

pre-commit run --all-files   # ruff(린트+포맷, 노트북 포함), mypy, 기타 훅; CI와 동일
ruff check --fix . && ruff format .
mypy aurora
```

참고:
- `ruff`는 `pyproject.toml`과 `.pre-commit-config.yaml` 모두에서 `0.4.1`로 고정되어 있고, 줄 길이는 100입니다. ruff는 `docs/` 아래의 `*.ipynb`도 포맷합니다.
- `tests/test_headers.py`는 모든 `.py` 파일(자동 생성되는 `aurora/_version.py` 제외)이 정확히 `"""Copyright (c) Microsoft Corporation. Licensed under the MIT license.` 로 시작하지 않으면 실패합니다. 테스트 파일을 포함해 새 Python 파일마다 이 헤더를 추가해야 합니다.
- `tests/test_model.py`는 실제 small 체크포인트를 내려받아 기준 출력과 엄격한 허용오차로 비교합니다. `tests/v1p5/`는 무작위 초기화된 아주 작은 모델(`_helpers._make_small_v1p5`)을 사용하며 빠르게 돌아갑니다. 새 단위 테스트는 후자의 패턴을 따르는 것이 좋습니다.
- `tests/foundry/`는 Foundry HTTP 엔드포인트와 Azure Blob Storage를 모킹(`requests_mock`, 몽키패치된 `BlobClient`)하고 MLflow 서버 래퍼를 스레드로 실행합니다. Azure 자격 증명은 필요 없습니다.
- 버전은 `hatch-vcs`를 통해 git 태그에서 나옵니다. `aurora/_version.py`는 생성 파일이며 gitignore 대상입니다.
- CI는 Python 3.10/3.11, Ubuntu/Windows에서 돌아갑니다. Linux 전용 가정은 피하세요(예: 1970년 이전 `datetime.timestamp()`는 Windows에서 깨집니다. `tests/conftest.py` 참고).

## 아키텍처

### `Aurora.forward`의 데이터 흐름 (`aurora/model/aurora.py`)

`Batch`가 들어가고 `Batch`가 나옵니다. `forward` 내부 파이프라인은 순서대로 다음과 같습니다.

1. `batch_transform_hook` (멱등이어야 함; `rollout`에서도 별도로 호출됨).
2. 모델 dtype으로 캐스팅, `_pre_norm_hook` (로그 스케일링처럼 멱등이 아닌 변환은 여기), `Batch.normalise` (`aurora/normalisation.py`의 변수별 location/scale), `patch_size`의 배수로 `Batch.crop`, 디바이스로 이동.
3. 정적 변수에 배치/히스토리 차원을 브로드캐스트; 양수 변수 클램프; `_pre_encoder_hook`.
4. 리드타임을 시간 단위 `(B,)` 텐서로 변환(고정 `timestep`, 또는 `variable_lead_time=True`일 때 샘플별).
5. `Perceiver3DEncoder`(`encoder.py`) → `Swin3DTransformerBackbone`(`swin3d.py`, 3D 시프트 윈도우 블록의 U-Net형 인코더/디코더, 롤아웃 스텝별 LoRA 옵션, 확률적 노이즈 주입 옵션) → `Perceiver3DDecoder`(`decoder.py`). 각 단계는 `autocast_{encoder,backbone,decoder}`에 따라 독립적으로 `torch.autocast`로 감싸집니다.
6. `_post_decoder_hook`, 양수 변수 클램프(`clamp_at_first_step`가 아니면 첫 롤아웃 스텝에서는 생략), float32로 캐스팅, `Batch.unnormalise`, `_post_unnorm_hook`.

디코더는 예측의 `metadata.rollout_step`을 1 증가시키고, 백본은 이 값으로 LoRA 어댑터를 선택합니다(`lora_mode`).

### 모델 변형은 훅을 오버라이드한 서브클래스

`Aurora`가 기본 1.3B 모델(0.25° 파인튜닝)입니다. `AuroraPretrained`, `AuroraSmallPretrained`, `Aurora12hPretrained`, `AuroraHighRes`, `AuroraAirPollution`, `AuroraWave`, `AuroraV1p5`, `AuroraV1p5Ensemble`는 각각 `default_checkpoint_name`/`default_checkpoint_revision`(고정된 HF 커밋)과 생성자 기본값을 설정하고, 위 훅들과 `_adapt_checkpoint`를 오버라이드하여 동작을 바꿉니다. 특정 변형에만 필요한 동작은 `Aurora.forward` 안에서 분기하지 말고 해당 서브클래스의 훅 오버라이드에 넣으세요.

`aurora/model/compat.py`는 공개된 체크포인트의 state dict를 현재 모듈 구조에 맞게 재작성합니다(키 이름 변경, 합쳐진 임베딩을 변수별 가중치로 분리 등). 모델에 새 변수를 추가하려면 `aurora/normalisation.py`의 `locations`/`scales` 딕셔너리에 정규화 통계를 넣고 `load_checkpoint(strict=False)`로 로드해야 합니다. `use_lora`를 바꾸면 파라미터 집합이 달라지므로 역시 `strict=False`가 필요합니다.

### Aurora 1.5 특이사항 (`AuroraV1p5`)

- 26개 표면 변수. `insolation`(`aurora/insolation.py`로 매 예측 후 재계산)과 `scaled_*` 변수(`_pre_norm_hook`에서 로그 변환, `_post_unnorm_hook`에서 역변환)를 포함합니다.
- `output_only_surf_vars`는 예측은 하지만 입력에는 없는 변수입니다. `_pre_encoder_hook`이 0으로 패딩하고(의도적으로 배치 딕셔너리를 제자리에서 수정), `rollout._advance_batch`가 다음 입력을 만들 때 이를 버립니다.
- `rollout_input_clipping`은 `forward`가 아니라 `rollout`에서 적용되므로, 학습 손실은 클리핑되지 않은 예측을 봅니다.
- 기본값으로 세 단계 모두 fp16 autocast를 사용하고 `use_fp16_safe_attention=True`입니다.
- `AuroraV1p5Ensemble`은 `stochastic=True`를 설정합니다. 노이즈는 백본에 있습니다(`reset_noise`, `set_noise_accumulation`, 재현성을 위한 `forward`의 `generator` 인자).

### 롤아웃 (`aurora/rollout.py`)

`rollout(model, batch, steps, fine_lead_times=...)`는 (서브)스텝마다 `Batch` 하나를 내는 제너레이터입니다. `fine_lead_times`를 주면 각 메인 스텝에서 같은 상태로부터 여러 리드타임의 예측을 만들고, 마지막 값(`model.timestep`과 같아야 함)만 자기회귀 상태를 전진시킵니다. `rollout_ensemble`은 배치 차원으로 타일링(`batch.py`의 `tile_batch`/`split_batch`)하여 멤버마다 독립적인 노이즈를 받게 합니다.

### `Batch` / `Metadata` (`aurora/batch.py`)

`dataclasses.replace`로 다루는 불변 스타일 데이터클래스입니다. 형상: 표면 `(b, t, h, w)`, 정적 `(h, w)`, 대기 `(b, t, c, h, w)`. `Metadata.__post_init__`은 위도가 `[-90, 90]`에서 엄격히 감소, 경도가 `[0, 360)`에서 엄격히 증가함을 강제합니다. `Batch`에는 `regrid`, `to_netcdf`/`from_netcdf`도 있습니다.

### 기타 최상위 모듈

- `aurora/tracker.py`: 연속 예측에 대한 열대성 저기압 추적용 `Tracker`.
- `aurora/foundry/`: Azure AI Foundry 상의 Aurora용 클라이언트/서버 코드. `client/api.submit`이 사용자 진입점; `common/channel.py`는 Azure Blob Storage로 배치를 주고받음(`BlobStorageChannel`); `common/model.py`는 `Model.__subclasses__()`로 만든 이름→모델 레지스트리(서브클래스마다 `name` 필수); `server/mlflow_wrapper.py`는 MLflow pyfunc 서버로 `package_mlflow.py`가 패키징함(직접 엔드포인트를 만드는 것은 문서상 deprecated).
- `finetuning/`: 최소 Docker 이미지와 학습 루프. 메모리 요구사항은 `docs/finetuning.md` 참고(80 GB A100에서 `autocast=True` + `configure_activation_checkpointing()`).

## 패키지 외 디렉터리

- `examples/delhi_air_quality/`: `AuroraAirPollution`과 `AuroraV1p5`를 연결해 델리 대기질 경보를 만드는 예제(CLI, 노트북, 한국어 스토리보드). 다국어 긴 문자열 때문에 `pyproject.toml`의 per-file ignore로 ruff E501이 면제되지만, 저작권 헤더 테스트는 그대로 적용됩니다.
- `msresearch-aurora/`: `microsoft/vibe-kit`의 Aurora 스킬 사본(untracked). 지역 추론 예제와 React 지도, ERA5 유틸리티, PyTorch Lightning 파인튠 스타터가 들어 있습니다. 패키지의 일부가 아닌 주변 도구·문서이며, 델리 예제가 이 프런트엔드용 JSON을 내보냅니다.

## 문서

`docs/`는 Jupyter Book(`docs/_toc.yml`)입니다. 예제 노트북은 출력과 함께 커밋되며 ruff로 린트됩니다. `docs/api.rst`와 `docs/foundry/api.rst`는 `autoclass`/`autofunction` 지시어로 공개 심볼을 명시적으로 나열하므로, 새 공개 심볼은 `aurora/__init__.py`와 그 `__all__`에 export하는 것과 함께 해당 파일에도 항목을 추가해야 합니다.
