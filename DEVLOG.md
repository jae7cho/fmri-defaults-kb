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
