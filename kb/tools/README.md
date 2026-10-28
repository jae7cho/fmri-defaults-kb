# `kb/tools/`

One YAML per software **package** (not pipeline). Schema:
[`schemas/tool_registry.schema.json`](../../schemas/tool_registry.schema.json).

Consumed by `fmri_defaults_kb.tools` (`recognize_tool`, `realignment_program`,
`listed_package_tokens`). First use (2026-10-28): the realignment program a package supplies
when a paper names the package for its preprocessing as a whole and no step-level tool —
the agent's `motion_correction.method` package basis (`derived`, ceiling 0.70) and the
motion value-in-quote check's listed-package fallback, which read this one table.

A package is not a pipeline: a pipeline (`kb/pipelines/`) composes programs and fixes which
one runs; a package ships the program. `version_token: true` marks packages whose version is
part of the name token as written (SPM8, SPM12); for the others a digit run after the name is
the PDF text layer's citation artefact, not a version.
