"""Standalone knowledge base of fMRI pipeline defaults.

Consumed by the agent's Configurator only. The KB never imports the agent;
the contract surface is the basis_type string literals exported below.
"""

from __future__ import annotations

from fmri_defaults_kb.datasets import (
    VIA_DATA_RELEASE,
    DatasetMatch,
    load_dataset_documents,
    recognize_dataset,
)
from fmri_defaults_kb.errors import (
    KbAmbiguousError,
    KbError,
    KbUnknownPipelineError,
    KbUnknownVersionError,
)
from fmri_defaults_kb.options import (
    load_option_documents,
    options_at_date,
    pipeline_options,
    release_timeline,
    step_defaults,
    step_parameters,
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
    realignment_settings,
    realignment_tool_at,
    realignment_tool_over,
    recognize,
    recognize_with_provenance,
    resolve_version,
)
from fmri_defaults_kb.sentinels import NotApplicable
from fmri_defaults_kb.tools import (
    KbNoRealignmentError,
    KbUnknownToolError,
    RealignmentProgram,
    listed_package_tokens,
    realignment_defaults,
    realignment_program,
    recognize_program,
    recognize_tool,
)

__all__ = [
    "KB_BASIS_LITERALS",
    "VIA_DATA_RELEASE",
    "ConditionalParam",
    "ConditionalRule",
    "DatasetMatch",
    "KbAmbiguousError",
    "KbError",
    "KbNoRealignmentError",
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
    "load_dataset_documents",
    "load_option_documents",
    "options_at_date",
    "pipeline_options",
    "realignment_defaults",
    "realignment_program",
    "realignment_settings",
    "realignment_tool_at",
    "realignment_tool_over",
    "recognize",
    "recognize_dataset",
    "recognize_program",
    "recognize_tool",
    "recognize_with_provenance",
    "release_timeline",
    "resolve_version",
    "step_defaults",
    "step_parameters",
]
