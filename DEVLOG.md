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

## 2026-11-09 (night, 3) — recognize_program

- `ef27524` — `recognize_program`:
  - **What it does:** returns (program, package) when a phrase names exactly one realignment
    program the KB records. The pipelines' programs are read first, so 3dvolreg is AFNI's, not the
    mmps wrapper's.
  - **"Realign":** also an ordinary verb, so it counts only beside "SPM" or as spm_realign.
  - **Why:** the agent's new precedence, where a program the paper names for the step outranks any
    default.
  - Tests: 153 passed.

Commits here: `ef27524`, then this entry.

## 2026-11-10 — CONN's realignment settings, and SPM's Realign & Unwarp defaults

- `e2364e6` — `realignment_settings`:
  - **What CONN sets:** conn_setup_preproc.m was read at all 7 listed tags (v20.07.29 to v25b).
    The functional_realign&unwarp step builds spm.spatial.realignunwarp and sets two options:
    - eoptions.rtm: rtm=0, register to first, at every tag;
    - uwroptions.mask: rmask=1, from v22.06.27.
    It leaves eoptions.einterp, quality, sep, fwhm and uwroptions.rinterp unset, and spm_jobman
    fills them. No other option line exists in the step. Control: the same search finds three
    option lines in the neighbouring functional_realign step.
  - **SPM's job defaults:** `realignment.unwarp_defaults` at r7771, each with its
    spm_cfg_realignunwarp.m and spm_defaults.m lines. They are register to first (not Realign's
    register to mean), 2nd degree B-spline, 0.9, 4 mm, 5 mm, 4th degree B-spline, mask images and
    least squares.
  - **The function:** each setting is either set by the pipeline (CONN's lines) or inherited (the
    CONN line that leaves it unset, plus SPM's lines). mask is "mixed": inherited before v22.06.27,
    set after, mask images either way. A setting that differs across versions comes back as a range
    with no value; none does for CONN.
  - **Schemas:** both extended; the validator passes 27.
  - **Tests:** 167 passed. Three mutations were caught: Realign's defaults in place of Realign &
    Unwarp's, swapped set/inherited labels, and the range branch removed.

Commits here: `e2364e6`, then this entry.

## 2026-11-11 — washu_4dfp; verification; the AFNI timeline; fMRIPrep, C-PAC and HCP settings

- `5ffc547`
  - **washu_4dfp:** the Washington University 4dfp pipeline. The program is cross_realign3d_4dfp,
    from the 4dfp documentation ("motion correct fMRI timeseries within and across runs"; the page
    is tools/fmri/fmri.html, as tools/fmri.html returns 404), so verification is manual.
    - Power et al. 2014 (NeuroImage 84:320-341, DOI checked in CrossRef) describes the step, not
      the program.
    - No reference frame is asserted: the docs offer "-r specify non-default reference frame"
      but never say which frame the default is.
    - Version: paper-anchored, Power2014.
  - **verification:** required on all 11 pipeline ranges and 6 tool entries, filled from each
    source text.
    - script_at_tag: abcd_bids, ccs, conn, cpac (2), dparsf, fcp_scripts, hcp_minimal (2).
    - manual: fmriprep, washu_4dfp; tools afni, ants, brainvoyager, fsl, spm.
    - paper: abcd_daic; tool mmps.
  - **AFNI timeline:** 3dvolreg is documented from 2.21 (README.registration line 2, signed
    November 1998). Whether an earlier release shipped it is not established. imreg and 2dImReg
    are the 2D alternatives, so a paper from 1999 or earlier that names no program is
    version-dependent between them. No other tool has a timeline.
  - **realignment_settings by version,** read at tags by three delegated readers. I spot-checked
    13 citations, all matching:
    - **fmriprep (MCFLIRT):** the reference differs across four version ranges. Cost (normcorr)
      and estimation interpolation (trilinear) are inherited from MCFLIRT. MCFLIRT's resampled
      output is never used.
    - **cpac (3dvolreg):** -Fourier is set at every tag. The reference differs by range
      (0.3.2-1.6.1, 1.6.2-1.7.2, 1.8.0-1.8.7). Weighted least squares is inherited.
    - **hcp_minimal:** flirt per volume to v3.4.0, mcflirt from v4.1.3. The reference is the scout.
      The cost is corratio, then normcorr, so it is a range when no version is known (as for the
      data releases' unlisted v3.1). The final interpolation is spline, from Glasser 2013, not
      from the resampling script.
  - **The function:** a list of blocks over version ranges; source text in place of line cites;
    the wrapped defaults found by job.
  - **FSL:** the reslice default (trilinear, mcflirt 2111.0) and flirt_defaults (corratio,
    trilinear; flirt 4ce498ce), both read in current source, not the FSL 5.0.x/6.0.x builds the
    pipelines bundled. A paper naming FSL with no pipeline now gets "estimate: trilinear;
    reslice: trilinear".
  - **Not added:** HCP v3.1 to the version list, because it would move date-inferred versions of
    2014 papers away from v3.4.0's parameter defaults.
  - **Tests:** 185 passed; validator 28. Six mutations caught: three on the settings code,
    three on the block and job logic.

The freeze: the agent repo's `sfn2026-freeze` stays at e437668, which pins KB `baf06f4`. This
entry is post-freeze.

Commits here: `5ffc547`, then this entry.

**Correction (2026-11-11), to the entry above:** I spot-checked 17 citations, not 13, all
matching. That is 9 pipeline-code lines (fMRIPrep 2, HCP 3, C-PAC 4) and 8 FSL default lines
(mcflirt 4, flirt 4). In addition, I read fMRIPrep's mcflirt connections at 3 tags myself.

**Follow-up (2026-11-11):** CI failed at the entry above. CI runs `uv run mypy` over tests as
well, and three `type: ignore` comments in tests/test_verification_and_washu.py were unused (I
had checked `src` only). They are removed in `f176e24`, where CI passed (lint-validate-test).

Commits here: `f6fb7e9` (the correction), `f176e24`, then this note.

## 2026-11-11 (2) — option inventories for fMRIPrep and C-PAC

- `e66d7d3` — every user-settable option at each listed version, and the values the code fixes.
  - **Why** (the author's request): a model can infer what a pipeline would have run from a
    paper's publication year: the versions released by then (`options_at_date`), and their
    options and defaults.
  - **fMRIPrep:** 91 CLI options over 21 tags, from the argparse calls (`fmriprep/cli/run.py` to
    20.0.0, `parser.py` from 20.1.0).
    - The parsed count equals a text count of add_argument calls at every tag, less the
      commented-out ones (2 per tag, 1 at 25.2.0).
    - 15 random citations checked at both range ends.
    - Example: --bold2t1w-dof defaults to 9 at 1.0.0-1.1.0, then 6.
  - **C-PAC:** 766 config keys over 34 tags, from the default configuration of each version.
    1.8.0 renamed the flat keys into a nested schema, so a setting can have two ids.
    - The extracted count equals an independent yaml.safe_load leaf count at every tag except
      1.0.3 and 1.1.0. Their template is invalid YAML; the dropped lines are recorded in sources.
    - A key written twice keeps its last value, as C-PAC's loader (yaml.safe_load) has it.
    - 0.3.2-1.0.2 are role example: no code loads that YAML; the GUI holds the defaults, and they
      can differ (fwhm [6] in the YAML, 4 in the GUI's smoothing.py line 44 at v0.3.6).
  - **Fixed values (curated, scripts/data/):** fMRIPrep 32 parameters (66 ranges), C-PAC 19
    (55 ranges), read at tags by delegated readers. 13 citations spot-checked (8 fMRIPrep,
    5 C-PAC), all matching. The UNVERIFIED items are marked in place.
  - **API:** `pipeline_options`, `step_parameters`, `options_at_date`.
  - **Tests:** 203 passed; validator 30. Three mutations caught (range contiguity, last
    duplicate wins, the example caveat).
  - **Not covered:**
    - Tags between the listed versions (fMRIPrep has 212 tags in all, counting release
      candidates and patch releases).
    - C-PAC's GUI defaults for 0.3.2-1.0.2.
    - A map between C-PAC's flat and nested key names.

Post-freeze, as the entries above.

Commits here: `e66d7d3`, then this entry.

## 2026-11-11 (3) — the option inventories' gaps filled

- `ff83a7f`
  - **Every release:** fMRIPrep 143 final tags (from 0.0.3), C-PAC 34, each dated by git.
    - Each inventory carries its own timeline, so kb/pipelines' version lists, and everything
      keyed on them, are unchanged.
    - fMRIPrep's parser is read wherever it lived (run_workflow.py, cli/run.py, cli/parser.py).
    - At all 143 tags the parsed count equals the live add_argument lines.
    - The tag listing reads `refname:lstrip=2`, because C-PAC's v1.3.0 is also a branch and
      `:short` gives tags/v1.3.0.
  - **C-PAC GUI defaults (0.3.2-1.8.0):** every page.add() initial value, by generic_class.py's
    rules: a choice box starts on its first value; a checklist starts all checked only for dtype
    LBOOL.
    - The rule lines are recorded per tag.
    - A tokenizer check at 0.3.6, 1.4.3 and 1.8.0 finds every live name= extracted. The rest sit
      in comments or disabled triple-quoted strings (e.g. the MultipleRegressionSCA class at 1.8.0).
  - **C-PAC's own 1.7-1.8 key map:** 221 flat keys carry nested_as, 209 nested keys flat_as, and
    21 flat keys are deprecated_in_1_8.
  - **Step maps (curated):** the options that answer each step. C-PAC's were selected by pattern,
    then reviewed: MDMR, PyPEER, ALFF and the motion-estimate filter removed; Regressors added to
    temporal filtering and scrubbing.
  - **Lookups:** release_timeline, step_defaults, and options_at_date (the latest release by the
    date, plus the last release of each of the two minor versions before it).
    - step_parameters at an unlisted tag: inside a read range, its value.
    - Between two ranges: both values, marked uncertain (fMRIPrep 1.1.1's coregistration DOF:
      "9 (to 1.1.0) or 6 (from 1.2.0)").
    - After the last: its value, marked uncertain.
  - **Size:** range citations are "line N at <version>", the file recorded once per version, and
    GUI citations are relative to CPAC/GUI/interface/. cpac.yaml is 476 KB, under the 500 KB hook.
  - **Tests:** 209 passed; validator 30. Six mutations caught across the two option rounds.

Post-freeze.

Commits here: `ff83a7f`, then this entry.

## 2026-11-11 (4) — step-option claims, tested at every claimed release

- `7649464` — the author's item 2.
  - **Claims:** each curated step option is {id, from_version, to_version} on the inventory's
    timeline, seeded from its availability and split at gaps.
  - **The test:** walks every claimed release and fails on any where the option does not exist.
  - **Positive controls:**
    - --fd-spike-threshold claimed from 1.3.0 is caught at 1.3.0, 1.3.1 and 1.3.2.
    - C-PAC's flat fwhm claimed through 1.8.1 is caught at 1.8.1. The GUI pages keep the name
      through 1.8.0.
  - **step_defaults** shows an option only within its claim. That filter's mutation survived
    until a test of a claim narrower than the option's life was added; it is now caught.
  - **Tests:** 213 passed.

Post-freeze.

Commits here: `7649464`, then this entry.
