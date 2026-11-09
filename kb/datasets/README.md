# `kb/datasets/`

One YAML per public data release whose preprocessing is a named KB pipeline (added 2026-11-09).
Schema: [`schemas/dataset_registry.schema.json`](../../schemas/dataset_registry.schema.json).

A dataset phrase resolves to its pipeline with provenance "via data release":
`fmri_defaults_kb.recognize_dataset(name, release)` matches a release's own aliases, then its
study's family aliases narrowed by the release; `recognize()` falls back to the release-specific
aliases only, so a bare study name ("HCP", "ABCD") is never a pipeline name. Every entry carries its
release document as the source; `pipeline_version` appears only where that document states one.

- `hcp_s900`, `hcp_s1200` → `hcp_minimal` (v3.1, as the reference manuals state it; HCP-YA resolves
  through their family aliases)
- `hcp_d_2_0` → `hcp_minimal` (unversioned; the Lifespan 2.0 appendix states no version)
- `abcd_3_0`, `abcd_4_0`, `abcd_5_0` → `abcd_daic` (the author's mapping; the DOI records name no pipeline)
- `abcd_collection_3165` → `abcd_bids`
