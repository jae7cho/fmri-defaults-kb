# DEVLOG

Contemporaneous dated record of project sessions. Each entry: date, hours, what I worked on. Maintained as evidentiary record.

---

## 2026-05-19

**Hours:** ~0.5

Knowledge base repository initialized. Scaffolding created via Claude Code session.

---

## 2026-10-28

**The package table and the realignment defaults, for the agent's `motion_correction.method`
inference arm** (the agent's `docs/design/DESIGN_motion_inference_arm.md`, the author's rulings of
2026-10-28, F3/F6/F7). Committed under the author's override of the working-hours hook, invoked in
the message.

- `6a608f5` — `kb/tools/`: one document per software package (AFNI, FSL, SPM, ANTs, BrainVoyager)
  with aliases, a `version_token` flag (SPM's version is part of the name token; a digit run after
  the others is the text layer's citation artefact) and a realignment block — program and a citable
  source each. `schemas/tool_registry.schema.json`. `fmri_defaults_kb.tools`: `recognize_tool`
  (whole-name match, a trailing version token stripped for SPM, an ambiguity guard),
  `realignment_program`, `listed_package_tokens` — the one table the agent's package basis and its
  value-in-quote fallback read. `validate_kb` picks a `kb/tools` document's schema by content (a
  `realignment` block marks a package document), so the per-version tool inventories keep theirs.
  Tests: 22 (schema validity, programs and sources, 18 recognizer cases, the token table, the
  ambiguity guard); mutations: version-token stripping disabled (3 fail), the guard dropped (1).
- `fd4da34` — `realignment_tool` ranges in the five pipeline documents (`schemas/pipeline_registry.schema.json`
  gains the optional block): fMRIPrep and HCP minimal MCFLIRT (stable), CCS 3dvolreg (stable,
  script-sourced, the paper's wording to be verified), C-PAC 3dvolreg in two ranges — 0.3.x recorded
  but not stable, 1.x stable from the default pipeline configuration — with the parameter
  no-defaults policy untouched; a new `fcp_scripts.yaml` (the 1000 Functional Connectomes Project
  scripts, one paper-anchored version, 3dvolreg from the scripts) so `recognize("FCP analysis
  scripts")` resolves. `registry`: `RealignmentDefault`, `get_realignment_tool` (by release order
  over the ranges), `realignment_tool_over` (the one default that holds over an inferred range when
  every version falls in a stable range with one program). Mutations: the lower bound made
  exclusive (3 fail), the stability mark ignored (1). `validate_kb`: 10 PASS, 0 FAIL. 101 tests;
  ruff, format and mypy clean.

Held for the author: the C-PAC timeline carries no `0.4.0` (a corpus paper states that version, so
the agent's lookup finds no release and fills nothing); the 0.3.x range's default is recorded, not
verified per release; CCS's and the FCP scripts' programs are script-sourced.

## 2026-11-03

**MMPS in `kb/tools/`** (the author's request, for the agent's KB software scan, which finds software
by `kb/tools` names). Committed under the author's allowance of working-hours commits for this set.

- `1a3a057` — `kb/tools/mmps.yaml`: aliases MMPS and Multi-Modal Processing Stream; source Hagler et al.
  (2019), sections 2.1 (MMPS named as the in-house package) and 2.7.1 (head motion corrected with
  AFNI's 3dvolreg); the realignment program is AFNI's, which MMPS calls. The package table the
  agent's motion value-in-quote fallback reads now lists `mmps`, so a motion quote naming MMPS
  reaches that fallback. Tests: 103 pass.

Held for the author: FreeSurfer has no entry (the schema requires a realignment program), so the
agent's scan does not find it.

## 2026-11-03 (evening)

**FreeSurfer in `kb/tools/`; the realignment block optional** (the author's ruling, for the agent's
KB software scan). Committed under the author's allowance in the message.

- `a36477e` — the registry schema's `realignment` block optional and a `programs` list added;
  `kb/tools/freesurfer.yaml` with recon-all, aseg and mri_vol2surf, each with its source (Fischl 2012;
  Dale, Fischl & Sereno 1999; Fischl et al. 2002, as cited in Hagler et al. 2019's reference list;
  Hagler et al. 2019 sections 2.7.3 and 2.7.4). The name "recon-all" is the FreeSurfer distribution's
  command and was not checked against a document. `realignment_program` raises
  `KbNoRealignmentError` for FreeSurfer; `listed_package_tokens` leaves it out, so a motion quote
  naming FreeSurfer is never package-attributed. Tests: 105 pass.

**FREEZE (dated 2026-11-03, the author's instruction).** Frozen at this repository's `a36477e`. No
feature work until after 2026-11-14, except fixes found while building the poster.

**Fix after the freeze (2026-11-03).** `8997f44` — CI's "Validate KB" step failed on `3c2427e`:
`scripts/validate_kb.py` told a package document by its `realignment` block, which `a36477e` made
optional, so FreeSurfer's document was validated against the per-version inventory schema. It now
tells them apart by `tool_id`. A regression test validates the real KB (12 documents pass). The
local suite had passed because the validator script runs only in CI; the freeze point is unchanged
in content.

## 2026-11-05 — defaults for fields a paper defers to its pipeline; three scan packages

These are for the agent's stress_v1 fixes (the author's list of 2026-11-05; agent DEVLOG, same date).
Commits were allowed in work hours by the author's standing instruction through 2026-11-14.

- `1ae10d3` — fMRIPrep 20.2.0 and 1.5.3 `param_defaults` for 12 fields, read from each tag's workflow
  `__desc__` boilerplate. The pinned packages were read at the lower bound of each pin (smriprep
  0.7.0 / 0.4.0), and the CLI defaults that pick a branch at the tag. fMRIPrep 1.5.3 (2019-12-12) is
  added to the timeline. HCP minimal preprocessing v3.4.0 and v4.1.3 get six fields from Glasser et
  al. (2013); each source says the scripts at the tag were not read. There is no schema change.
  Tests: 6; 3 mutations killed; validate_kb 12 passed.
- `bda087b` — kb/tools adds fMRIPrep, CONN and CAT12, none with a realignment block. Title-case
  "Conn" matches only inside a toolbox phrase, since it is also a surname. Tests: 2 more and the
  package set updated; 3 mutations killed; validate_kb 15 passed.

Commits here: `1ae10d3`, `bda087b`, then this entry.

**CI fix after the push (2026-11-05).** `ce9301a` — CI's mypy runs over `tests/`, which the local hooks
do not. It rejected the CompCor mask test of `1ae10d3` (an `in` test on a value typed as possibly
not a string), and the test now reads it through `str()`. `uv run mypy` is clean and 114 tests pass.
Commits here: `ce9301a`, then this entry.

## 2026-11-09 — CONN in kb/pipelines

For the agent's resolution call (agent DEVLOG, same date): a paper that hands its preprocessing to
CONN's default pipeline now gets its realignment program from the KB. Commits were allowed in work
hours by the author's standing instruction through 2026-11-14.

- `263e461` — `kb/pipelines/conn.yaml`. Its versions are the seven alfnie/conn GitHub release tags,
  v20.07.29 to v25b. The realignment program is SPM Realign (package spm), marked stable across the
  range. The source is `conn_setup_preproc.m`, parsed at every tag: all six default pipelines include
  `functional_realign&unwarp` (or `&fieldmap`), which builds `spm.spatial.realignunwarp`. CONN
  releases from before the GitHub history are not listed. `param_defaults` is empty.
  `kb/tools/conn.yaml` is unchanged: it still has no realignment block, so CONN is not a listed
  package for the motion fallback.
  Tests: 1 new, and the seeded-pipeline set updated; 115 passed. Positive control: setting
  `stable_across_range: false` fails the new test. validate_kb: 16 passed.

Commits here: `263e461`, then this entry.

## 2026-11-09 (evening) — three pipelines, kb/datasets, sourced realignment defaults

The author's KB list ahead of the 45-paper re-run. Every value carries its source or is omitted.
Commits in work hours by the author's standing instruction through 2026-11-14.

- `5b54ee9`
  - **Pipelines:**
    - `abcd_daic`: 3dvolreg, from Hagler et al. 2019 §2.7.1.
    - `abcd_bids`: MCFLIRT, confirmed in DCAN's `app/pipelines.py` and in DCAN-HCP at every release.
      It is a full entry, not a stub, because the repository confirms the program.
    - `dparsf`: SPM Realign, from `DPARSFA_run.m` at its one tag; Yan & Zang 2010 and Yan et al.
      2016 with their DOIs checked against CrossRef.
    - `tools/bioimage_suite` for the software scan.
  - **`kb/datasets`** (new, with schema and validation):
    - HCP S900 and S1200 → `hcp_minimal` at v3.1, as their reference manuals state it. HCP-YA
      resolves through their family aliases.
    - HCP-D 2.0 → `hcp_minimal`, unversioned.
    - ABCD 3.0, 4.0 and 5.0 → `abcd_daic`. This mapping is the author's; the DOI records name no
      pipeline.
    - NDA collection 3165 → `abcd_bids`.
    - `recognize()` falls back to release-specific aliases only; `recognize_with_provenance()`
      returns "via data release".
  - **Realignment defaults**, read from the program's own source:
    - SPM12 r7771: `spm_defaults.m` and `spm_cfg_realign.m`.
    - FSL MCFLIRT: the usage text and FSL docs. No reslice default is sourced, so it is omitted.
    - AFNI 3dvolreg: the AFNI_26.3.10 help text. Its interpolation default changed (Fourier, then
      heptic) in an unstated release, and both are recorded.
  - Tests: 139 passed; validate_kb 27 passed; 5 mutations killed.

Commits here: `5b54ee9`, then this entry.

## 2026-11-09 (late) — configurable realignment; two corrections

- `20b210a`
  - **The new field:** every pipeline range says whether the user chooses the realignment program,
    among what, and on what source line.
  - **Configurable:** C-PAC from 1.6.2 (3dvolreg default, mcflirt offered) and HCP Pipelines v4.1.3
    (MCFLIRT default, FLIRT offered).
  - **Not configurable**, each with its source line: C-PAC to 1.6.1, every tag read and now verified;
    HCP v3.4.0; CCS; the FCP scripts (fcon_1000 v1.1 read); CONN; DPARSF; ABCD DAIC; ABCD-BIDS;
    fMRIPrep.
  - **Corrections:**
    - hcp_minimal v3.4.0 is FLIRT-based (`mcflirt_acc.sh`, FSL flirt per volume), not MCFLIRT as
      recorded on 2026-10-28;
    - ccs cited a script path (`ccs_02_funcpreproc.sh`) that does not exist at its commit.
  - Tests: 141 passed; validate_kb 27 passed.

Commits here: `20b210a`, then this entry.

## 2026-11-09 (night) — realignment_tool_at; the HCP FLIRT range sourced

- `3e9c6a3`
  - **`realignment_tool_at`:** places a version the KB does not list into the range that contains
    it by version order.
  - **HCP data releases:** the S900/S1200 "v3.1" resolves into the FLIRT range, with no choice. The
    agent therefore gives them INFERRED_DEFAULT, not "version-dependent".
  - **hcp_minimal's FLIRT range:** sourced to Glasser 2013 and to the v3.1 and v3.4.0 tags.
  - **v3.1 is public:** the HCPpipelines v3.1 tag exists and was read, so the note says so (it was
    to say the tag is not public). `--mctype` first appears at v3.15.0.
  - Tests: 142 passed.

Commits here: `3e9c6a3`, then this entry.
