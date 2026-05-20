# fmri-defaults-kb

A curated, versioned knowledge base of neuroimaging tool defaults, lab fingerprints, and methods-paper-to-flag mappings for fMRI preprocessing pipelines.

Developed on personal time and equipment. Not affiliated with any employer.

## Purpose

fMRI methods sections routinely under-report the actual parameters used during preprocessing, and the mapping between a tool version and its built-in defaults drifts silently between minor releases — a pipeline run with FSL 6.0.4 is not necessarily a pipeline run with FSL 6.0.6, even when the methods text is identical. Carp (2012, *NeuroImage* 63:289-300) documented 207 unique pipelines across 241 fMRI studies, illustrating the scale of unreported and undocumented methodological variation that this gap produces. The motivation for this knowledge base is to make the implicit, version-dependent defaults of common neuroimaging tools explicit, machine-readable, and easy to cite.

The knowledge base is organized around four sub-components: (A) a **tool-version defaults database** capturing the default parameter values shipped with each released version of a tool; (B) **date-to-version mappings** so that a publication date or analysis date can be translated into the most plausible tool version in use; (C) **lab-fingerprint priors** describing the parameter conventions typical of specific research groups or pipelines; and (D) **methods-paper-citation to pipeline-flag mappings** linking widely cited methodological papers to the concrete tool flags they imply. The knowledge base is designed to be useful and citable independently of the sibling agent project — researchers, reviewers, and reproducibility auditors should be able to consume it on its own terms, without depending on any particular automation layer.

## Repository structure

- `kb/tools/` — `{tool}/{version}.yaml` files, one per released tool version, capturing default parameters.
- `kb/dates/` — `{tool}.csv` files mapping release/availability dates to versions for each tool.
- `kb/labs/` — `{lab_slug}.yaml` files describing lab-level parameter conventions and fingerprints.
- `kb/citations/` — `{doi_or_slug}.yaml` files mapping methods-paper citations to specific pipeline flags.
- `schemas/` — JSON Schemas defining the structure of each entry type in `kb/`.
- `scripts/` — utility scripts including the KB validator.

## Status

Pre-alpha. Schemas may evolve before v0.1.0.

## Sibling repository

The companion agent project lives at [fmri-repro-agent](https://github.com/jae7cho/fmri-repro-agent). This knowledge base is intentionally maintained as a standalone artifact so it can be cited and reused independently.

## Contributing

KB coverage is the project's primary metric — contributions of new tool-version YAMLs, lab fingerprints, or methods-paper-to-flag mappings are particularly welcome. See [CONTRIBUTING.md](CONTRIBUTING.md).

## Citation

If you use this knowledge base, please cite it as described in [CITATION.cff](CITATION.cff).

## License

Apache License 2.0. See [LICENSE](LICENSE) and [NOTICE](NOTICE).
