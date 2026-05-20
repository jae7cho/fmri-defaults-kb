# Contributing

Thanks for your interest in `fmri-defaults-kb`. Knowledge base coverage is the project's primary deliverable, so contributions that expand the KB are especially welcome — new tool-version YAMLs in `kb/tools/`, date-to-version rows in `kb/dates/`, lab fingerprints in `kb/labs/`, and methods-paper-to-flag mappings in `kb/citations/` are all valuable additions.

## Before you open a pull request

The KB schemas are still pre-alpha and may change before v0.1.0. For now, please open a [Discussion](https://github.com/jae7cho/fmri-defaults-kb/discussions) or [Issue](https://github.com/jae7cho/fmri-defaults-kb/issues) before submitting new tool-version YAMLs or other KB entries. A short heads-up helps avoid duplicated work, gives a chance to flag any pending schema changes, and makes review smoother.

For typo fixes, documentation improvements, or small clarifications, feel free to open a pull request directly.

## How to contribute a KB entry

1. Open a Discussion or Issue describing the tool, version, lab, or citation you intend to add.
2. Once direction is confirmed, add the corresponding YAML/CSV file under the appropriate `kb/` subdirectory.
3. Include the source(s) you used to determine the default values or mappings (release notes, source code references, published methods sections, etc.) in the entry's `provenance` fields.
4. Open a pull request referencing the original Discussion or Issue.

## Code of Conduct

Participation in this project is governed by the project's [Code of Conduct](CODE_OF_CONDUCT.md).
