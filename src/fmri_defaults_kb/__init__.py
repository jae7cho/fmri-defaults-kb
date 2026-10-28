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
    RealignmentDefault,
    VersionCandidate,
    VersionResolution,
    get_param_defaults,
    get_realignment_tool,
    realignment_tool_over,
    recognize,
    resolve_version,
)
from fmri_defaults_kb.sentinels import NotApplicable
from fmri_defaults_kb.tools import (
    KbUnknownToolError,
    RealignmentProgram,
    listed_package_tokens,
    realignment_program,
    recognize_tool,
)

__all__ = [
    "KB_BASIS_LITERALS",
    "ConditionalParam",
    "ConditionalRule",
    "KbAmbiguousError",
    "KbError",
    "KbUnknownPipelineError",
    "KbUnknownToolError",
    "KbUnknownVersionError",
    "NotApplicable",
    "ParamResult",
    "RealignmentDefault",
    "RealignmentProgram",
    "VersionCandidate",
    "VersionResolution",
    "get_param_defaults",
    "get_realignment_tool",
    "listed_package_tokens",
    "realignment_program",
    "realignment_tool_over",
    "recognize",
    "recognize_tool",
    "resolve_version",
]
