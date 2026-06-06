# KB-integration follow-ups

**Status:** All small items closed except **C** and **E**, both deferred — C to the
Methods Extractor thread, E to the preprocessing-group spec-test thread. Ready to
start Extractor work.

Durable tracking copy. Items reference working-tree changes rather than commit
SHAs: the corresponding work is staged in the working trees of `fmri-defaults-kb`
and `fmri-repro-agent` but not yet committed, so there are no SHAs/PRs to cite yet.

CCS pipeline seeding is **not** a backlog item — it is a delivered milestone and is
recorded in the CHANGELOGs, not here.

---

## A — Audit `fsl_mode_10000` in `IntensityNormalizationConvention` — CLOSED

The member `fsl_mode_10000` was a misnomer: there is no FSL "mode-based 10000"
normalization convention. Resolved in `fmri-repro-agent`:

- Renamed `fsl_mode_10000` → `fsl_median_10000` (the real per-volume convention:
  scale each volume so its median equals 10000).
- Added `fsl_grand_mean_10000` (mean-based, single-factor 4D grand-mean scaling to
  10000 — FSL `fslmaths -ing 10000` / FEAT default).
- Added per-member comments on the `IntensityNormalizationConvention` `Literal`
  distinguishing the mean / median / value conventions.
- Regenerated `schema/study_spec-0.1.0.schema.json` after the enum change.

Reference: working-tree changes to `src/fmri_repro/spec/preprocessing.py` (no SHA).

## B — Add KB-vocabulary ⊆ spec-`Literal` contract test — CLOSED

`fmri-repro-agent/tests/kb_client/test_vocab_contract.py`:

- Introspection-built `CONTRACTS` map — every `ProvenancedField[Literal]` /
  `ProvenancedField[list[Literal]]` field on every `PreprocStep` is covered
  automatically.
- Data-level check: every controlled-vocab value the KB serves is a member of the
  matching spec `Literal` (direction: KB ⊆ spec).
- Schema-shape tombstone with a documented `_NON_VOCAB_ENUM_PATHS = {version_kind}`
  allowlist (KB-internal metadata enums with no spec-`Literal` counterpart are
  exempt; any enum at a value-bearing path still trips it).
- `_STEP_CLASSES` ↔ `get_args(PreprocStep)` derived-truth-set guard, so a new step
  kind can't silently lose vocab coverage.

Reference: working-tree addition under `tests/kb_client/` (no SHA).

## C — `MSMAll` `surface_registration` has no population path — DEFERRED

Blocked on the Methods Extractor thread. A paper's HCP-provided
`*_MSMAll.dtseries.nii` data names a post-ICA+FIX re-registration that must be
captured as `Extracted(msm_all)` from the filename — it is never a base-pipeline
`version_default`. This needs the Extractor's extraction-rule infrastructure to
exist first; it closes when a filename-detection rule
(`*_MSMAll.dtseries.nii` → `Extracted(msm_all)`) can be added there.

## D — mypy hygiene — CLOSED (this pass)

- `fmri-repro-agent`: fixed the `_step_field` test-helper return type (cast the
  `getattr` result to `ProvenancedField`); typed `_STEP_CLASSES` as
  `tuple[type[BaseModel], ...]`; added `types-PyYAML` dev dependency.
- `fmri-defaults-kb`: added `[tool.mypy]` (mirroring the agent's profile),
  wired a `Mypy` step into CI, added `types-PyYAML` / `types-jsonschema` dev deps,
  and fixed the emergent `no-any-return` sites (`registry._find_version`,
  `validate_kb.load_schema`) plus an unused `type: ignore`. `mypy` is clean in
  both repos for the surfaces each owns.

Reference: working-tree changes in both repos (no SHA).

## E — 26 pre-existing mypy errors in `fmri-repro-agent/tests/spec/test_preprocessing.py` — DEFERRED

All `union-attr` errors (accessing `.value` / `.basis` / `.extraction` on
provenance unions). Origin: commit `15a43d5` ("feat(spec): add preprocessing group
to ReplicationSpec v0.1.0"), a separate preprocessing-group spec work stream —
verified pre-existing via `git stash` (committed HEAD shows the same 26). They live
in `tests/` and do **not** block CI: the agent CI gate is `mypy src`, which is
clean. Owned by the spec-test thread (touching the file mid-flight risks a merge
collision).

- **Status:** DEFERRED — owned by the spec-test thread; closes when that thread
  lands its own pass, or as a focused fix if it stalls.
- **Acceptance:** `mypy src tests` clean in `fmri-repro-agent`.
