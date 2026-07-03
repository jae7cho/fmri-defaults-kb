"""Exercise validate_kb_directory against valid and invalid fixtures."""

from __future__ import annotations

import json
from pathlib import Path

from jsonschema import Draft202012Validator

from validate_kb import validate_kb_directory

REPO_ROOT = Path(__file__).parent.parent
SCHEMA_DIR = REPO_ROOT / "schemas"
FIXTURE_VALID = REPO_ROOT / "tests" / "fixtures" / "valid"
FIXTURE_INVALID = REPO_ROOT / "tests" / "fixtures" / "invalid"


def _param_default_validator() -> Draft202012Validator:
    schema = json.loads((SCHEMA_DIR / "pipeline_registry.schema.json").read_text())
    return Draft202012Validator({"$ref": "#/$defs/param_default", "$defs": schema["$defs"]})


_COND_VALUE = {
    "conditional_on": "surface_projection.target_surface",
    "rules": [
        {"when": "fsLR_32k", "value": "msm_sulc", "proposed_confidence": 0.70, "source": "x"},
        {
            "when": ["fsaverage", "fsaverage5"],
            "value": "freesurfer_recon",
            "proposed_confidence": 0.55,
            "source": "y",
        },
    ],
}


def test_schema_accepts_conditional_without_entry_level_conf_source() -> None:
    # A conditional_default may omit entry-level proposed_confidence/source (per-rule carries).
    assert _param_default_validator().is_valid({"value": _COND_VALUE})


def test_schema_requires_conf_source_for_scalar_value() -> None:
    # The if/else guard (with the type:object fix): a scalar value MUST carry entry-level
    # proposed_confidence + source.
    v = _param_default_validator()
    assert not v.is_valid({"value": "MNI152NLin6Asym"})
    assert v.is_valid({"value": "MNI152NLin6Asym", "proposed_confidence": 0.9, "source": "d"})


def test_schema_requires_conf_source_for_sentinel_value() -> None:
    # A sentinel object (no `conditional_on`) still requires entry-level conf/source.
    assert not _param_default_validator().is_valid({"value": {"kind": "not_applicable"}})


def test_schema_rejects_conditional_rule_missing_source() -> None:
    bad = {
        "value": {
            "conditional_on": "a.b",
            "rules": [{"when": "x", "value": "y", "proposed_confidence": 0.5}],  # no source
        }
    }
    assert not _param_default_validator().is_valid(bad)


def test_valid_fixtures_pass() -> None:
    passed, failed = validate_kb_directory(FIXTURE_VALID, SCHEMA_DIR)
    assert passed > 0
    assert failed == 0


def test_invalid_fixtures_fail() -> None:
    _passed, failed = validate_kb_directory(FIXTURE_INVALID, SCHEMA_DIR)
    assert failed > 0
