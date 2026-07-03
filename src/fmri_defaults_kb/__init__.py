"""Standalone knowledge base of fMRI pipeline defaults.

Consumed by the agent's Configurator only. The KB never imports the agent;
the contract surface is the basis_type string literals exported below.
"""

from __future__ import annotations

from fmri_defaults_kb.errors import (
    KbAmbiguousError,
    KbError,
    KbUnknownPipelineError,
    KbUnknownVersionError,
)
from fmri_defaults_kb.registry import (
    KB_BASIS_LITERALS,
    ConditionalParam,
    ConditionalRule,
    ParamResult,
    VersionCandidate,
    VersionResolution,
    get_param_defaults,
    recognize,
    resolve_version,
)
from fmri_defaults_kb.sentinels import NotApplicable

__all__ = [
    "KB_BASIS_LITERALS",
    "ConditionalParam",
    "ConditionalRule",
    "KbAmbiguousError",
    "KbError",
    "KbUnknownPipelineError",
    "KbUnknownVersionError",
    "NotApplicable",
    "ParamResult",
    "VersionCandidate",
    "VersionResolution",
    "get_param_defaults",
    "recognize",
    "resolve_version",
]
