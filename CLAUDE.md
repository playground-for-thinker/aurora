# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

`microsoft-aurora`: the PyTorch implementation of Aurora, a foundation model for Earth-system forecasting (weather, air pollution, ocean waves). Pretrained checkpoints live on HuggingFace (`microsoft/aurora`) and are downloaded on demand by `model.load_checkpoint()`. Several tests also download test fixtures from that repo, so a network connection is needed for the full suite.

## Commands

```bash
make install        # pip install -e ".[dev]" + pre-commit install
make test           # pytest tests -v --cov=aurora (HTML coverage in htmlcov/)
make docs           # jupyter-book build docs; output in docs/_build/html

pytest tests/v1p5/test_rollout_substepping.py            # one file
pytest tests/test_model.py::test_aurora_small             # one test
pytest tests -k "not test_aurora_small"                   # skip the slow checkpoint-download test

pre-commit run --all-files   # ruff (lint+format, incl. notebooks), mypy, misc hooks; same as CI
ruff check --fix . && ruff format .
mypy aurora
```

Notes:
- `ruff` is pinned to `0.4.1` in both `pyproject.toml` and `.pre-commit-config.yaml`; line length is 100. Ruff also formats `*.ipynb` files under `docs/`.
- `tests/test_headers.py` fails if any `.py` file (except the generated `aurora/_version.py`) does not start with the exact line `"""Copyright (c) Microsoft Corporation. Licensed under the MIT license.` — add it to every new Python file, including tests.
- `tests/test_model.py` loads the real small checkpoint and compares against reference outputs with tight tolerances; `tests/v1p5/` uses tiny randomly-initialised models (`_helpers._make_small_v1p5`) and runs fast. Prefer the latter pattern for new unit tests.
- `tests/foundry/` mocks the Foundry HTTP endpoint and Azure blob storage (`requests_mock`, monkeypatched `BlobClient`) and runs the MLflow server wrapper in a thread; no Azure credentials are needed.
- The version comes from git tags via `hatch-vcs`; `aurora/_version.py` is generated and gitignored.
- CI runs on Python 3.10 and 3.11, Ubuntu and Windows. Avoid Linux-only assumptions (e.g. pre-1970 `datetime.timestamp()` breaks on Windows; see `tests/conftest.py`).

## Architecture

### Data flow through `Aurora.forward` (`aurora/model/aurora.py`)

`Batch` in, `Batch` out. The pipeline inside `forward` is, in order:

1. `batch_transform_hook` (must be idempotent; also called separately by `rollout`).
2. Cast to model dtype, `_pre_norm_hook` (non-idempotent transforms such as log-scaling go here), `Batch.normalise` (per-variable location/scale from `aurora/normalisation.py`), `Batch.crop` to a multiple of `patch_size`, move to device.
3. Static vars get batch/history dims broadcast; positive vars are clamped; `_pre_encoder_hook`.
4. Lead times resolved to a `(B,)` tensor in hours (fixed `timestep`, or per-sample when `variable_lead_time=True`).
5. `Perceiver3DEncoder` (`encoder.py`) → `Swin3DTransformerBackbone` (`swin3d.py`, U-Net style encoder/decoder of 3D shifted-window blocks, optional LoRA per rollout step, optional stochastic noise injection) → `Perceiver3DDecoder` (`decoder.py`). Each stage is independently wrapped in `torch.autocast` according to `autocast_{encoder,backbone,decoder}`.
6. `_post_decoder_hook`, clamp positive vars (skipped on the first rollout step unless `clamp_at_first_step`), cast to float32, `Batch.unnormalise`, `_post_unnorm_hook`.

The decoder increments `metadata.rollout_step` on the prediction; the backbone uses it to select the LoRA adapter (`lora_mode`).

### Model variants are subclasses with hook overrides

`Aurora` is the 1.3B default (0.25° fine-tuned). `AuroraPretrained`, `AuroraSmallPretrained`, `Aurora12hPretrained`, `AuroraHighRes`, `AuroraAirPollution`, `AuroraWave`, `AuroraV1p5`, `AuroraV1p5Ensemble` each set `default_checkpoint_name`/`default_checkpoint_revision` (a pinned HF commit) and constructor defaults, and customise behaviour by overriding the hooks above plus `_adapt_checkpoint`. When adding behaviour for one variant, put it in a hook override on that subclass rather than branching inside `Aurora.forward`.

`aurora/model/compat.py` rewrites published checkpoint state dicts (renaming keys, splitting fused embeddings into per-variable weights, etc.) so they load into the current module layout. New variables appended to a model need normalisation stats added to the `locations`/`scales` dicts in `aurora/normalisation.py` and `load_checkpoint(strict=False)`. Toggling `use_lora` changes the parameter set, so it also requires `strict=False`.

### Aurora 1.5 specifics (`AuroraV1p5`)

- 26 surface vars incl. `insolation` (recomputed from `aurora/insolation.py` after every prediction) and `scaled_*` vars that are log-transformed in `_pre_norm_hook` / inverted in `_post_unnorm_hook`.
- `output_only_surf_vars` are predicted but absent from inputs; `_pre_encoder_hook` zero-pads them (mutating the batch dicts in place on purpose) and `rollout._advance_batch` drops them when building the next input.
- `rollout_input_clipping` is applied by `rollout`, not by `forward`, so training losses see unclipped predictions.
- Defaults to fp16 autocast on all three stages with `use_fp16_safe_attention=True`.
- `AuroraV1p5Ensemble` sets `stochastic=True`; noise lives in the backbone (`reset_noise`, `set_noise_accumulation`, optional `generator` arg to `forward` for reproducibility).

### Rollout (`aurora/rollout.py`)

`rollout(model, batch, steps, fine_lead_times=...)` is a generator yielding one `Batch` per (sub-)step. With `fine_lead_times`, each main step produces predictions at several lead times from the same state; only the last (which must equal `model.timestep`) advances the autoregressive state. `rollout_ensemble` tiles the batch along the batch dimension (`tile_batch`/`split_batch` in `batch.py`) so members get independent noise.

### `Batch` / `Metadata` (`aurora/batch.py`)

Frozen-style dataclasses manipulated with `dataclasses.replace`. Shapes: surface `(b, t, h, w)`, static `(h, w)`, atmospheric `(b, t, c, h, w)`. `Metadata.__post_init__` enforces lat in `[-90, 90]` strictly decreasing and lon in `[0, 360)` strictly increasing. `Batch` also has `regrid`, `to_netcdf`/`from_netcdf`.

### Other top-level modules

- `aurora/tracker.py`: `Tracker` for tropical-cyclone tracking over successive predictions.
- `aurora/foundry/`: client/server code for Aurora on Azure AI Foundry. `client/api.submit` is the user entry point; `common/channel.py` moves batches via Azure blob storage (`BlobStorageChannel`); `common/model.py` is a name→model registry built from `Model.__subclasses__()` (every subclass needs a `name`); `server/mlflow_wrapper.py` is the MLflow pyfunc server, packaged by `package_mlflow.py` (building your own endpoint is documented as deprecated).
- `finetuning/`: a minimal Docker image and training loop; see `docs/finetuning.md` for memory requirements (`autocast=True` + `configure_activation_checkpointing()` on an 80 GB A100).

## Non-package directories

- `examples/delhi_air_quality/`: a worked example chaining `AuroraAirPollution` and `AuroraV1p5` into a Delhi air-quality alert pipeline (CLI, notebook, Korean storyboard). Its long multilingual strings are exempt from ruff's E501 via a per-file ignore in `pyproject.toml`; the copyright-header test still applies.
- `msresearch-aurora/`: an untracked copy of the `microsoft/vibe-kit` Aurora skill (regional inference example with a React map, ERA5 utilities, a PyTorch Lightning fine-tuning starter). It is documentation and tooling around the package, not part of it; the Delhi example exports JSON for its frontend.

## Docs

`docs/` is a Jupyter Book (`docs/_toc.yml`). Example notebooks are committed with outputs and are linted by ruff. `docs/api.rst` and `docs/foundry/api.rst` list public symbols explicitly with `autoclass`/`autofunction` directives, so a new public symbol needs an entry there as well as an export in `aurora/__init__.py` and its `__all__`.
