# `kb/pipelines/`

One YAML per named preprocessing pipeline. Schema:
[`schemas/pipeline_registry.schema.json`](../../schemas/pipeline_registry.schema.json).

Consumed by the agent Configurator's `base_pipeline.version` inference path
via the standalone [`fmri_defaults_kb`](../../src/fmri_defaults_kb) Python
query layer (`recognize`, `resolve_version`, `get_param_defaults`).

## Currently seeded

- `hcp_minimal.yaml` — HCP Minimal Preprocessing Pipeline. Two version
  records pinning the surface-registration default boundary: `v3.4.0`
  (`freesurfer_recon`, folding-based era) and `v4.1.3` (`msm_sulc`, the first
  tag whose `PostFreeSurferPipeline.sh` defaults `--regname` to `MSMSulc`).
  Intensity normalization is verified at-tag (`fsl_grand_mean_10000` /
  FSL `-ing 10000`, mean-based — distinct from the per-volume
  `fsl_median_10000` literal), no longer a `needs_verification` sentinel.
- `fmriprep.yaml` — version-path-only. Stable releases through 2025-10-02.
  `param_defaults` intentionally empty: fMRIPrep's per-flag inventory
  belongs in the future Sub-A auto-parsed `kb/tools/fmriprep/{version}.yaml`
  files, not here.
- `ccs.yaml` — Connectome Computation System (Xu et al. 2015). Two records:
  paper-anchored (`2015`) and a master commit checkpoint (CCS carries no
  release tags, so versioning is paper-anchored + commit, not tag-based).
  Five `version_default` fields; `surface_projection.target_surface` and
  `temporal_filtering.effective_band_hz` are intentionally unfilled — Xu 2015
  documents both as user-configurable, so the pipeline pins no default.
  `recognize("CCS")` now resolves to `ccs`.
