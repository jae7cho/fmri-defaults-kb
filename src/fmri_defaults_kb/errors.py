"""KB-side exceptions."""

from __future__ import annotations


class KbError(Exception):
    """Base class for KB query errors."""


class KbAmbiguousError(KbError):
    """resolve_version called without paper_date on a pipeline that has multiple versions and no default_version marker."""


class KbUnknownPipelineError(KbError):
    """Pipeline id passed to resolve_version / get_param_defaults is not registered."""


class KbUnknownVersionError(KbError):
    """Version string passed to get_param_defaults does not match any versions[] entry."""
