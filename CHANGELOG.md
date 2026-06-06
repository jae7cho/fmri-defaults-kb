# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

> **Vocabulary discipline.** Changes to KB schema enums (or to the spec
> `Literal` vocabularies the KB serves into) must be documented here, and
> marked **breaking** if a member is removed or renamed.

Nothing has been tagged yet, so all entries live under `[Unreleased]`.

## [Unreleased]

### Added

- `schemas/pipeline_registry.schema.json` (JSON Schema Draft 2020-12) — the
  pipeline registry: `versions[]`, `param_defaults`, and the
  `not_applicable` / `needs_verification` value sentinels.
- `src/fmri_defaults_kb/` package — `registry.py`, `io.py`, `sentinels.py`,
  exposing the query interface `recognize`, `resolve_version`,
  `get_param_defaults`.
- `kb/pipelines/hcp_minimal.yaml` — two version records (`v3.4.0` with
  `freesurfer_recon`, `v4.1.3` with `msm_sulc`), with intensity normalization
  verified at-tag (`fsl_grand_mean_10000` / FSL `-ing 10000`).
- `kb/pipelines/fmriprep.yaml` — version-path-only seed (`param_defaults`
  intentionally empty; per-flag inventory belongs in a future
  `kb/tools/fmriprep/` surface).
- `kb/pipelines/ccs.yaml` — two records, paper-anchored (`2015`) and a master
  commit checkpoint (CCS carries no release tags). Five `version_default`
  fields; `surface_projection.target_surface` and
  `temporal_filtering.effective_band_hz` intentionally unfilled (Xu 2015
  documents both as user-configurable). The paper's generic "MNI152" is
  resolved to `MNI152NLin6Asym` (FSL FLIRT/FNIRT's standard template), at
  confidence 0.9 to reflect the one-step template disambiguation.
- **(non-breaking, additive)** optional `version_kind` enum
  (`tag` / `commit` / `paper_anchored`) on `versions[]` items — supports
  master-based academic packages with no formal release tags.
- mypy configuration (`[tool.mypy]`) targeting `src` + `tests`, wired into CI
  alongside ruff and `validate_kb.py`; `types-PyYAML` / `types-jsonschema`
  dev dependencies.

### Fixed

- HCP `surface_registration` keying — dropped the `v3.8.0` record (its
  `PostFreeSurferPipeline.sh` default is still `FS` folding-based, identical
  to `v3.4.0`, so it added no keying signal) and added `v4.1.3`, the genuine
  `FS → MSMSulc` default boundary verified against `PostFreeSurferPipeline.sh`.
