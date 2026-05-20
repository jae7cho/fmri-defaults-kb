"""Exercise validate_kb_directory against valid and invalid fixtures."""

from __future__ import annotations

from pathlib import Path

from validate_kb import validate_kb_directory

REPO_ROOT = Path(__file__).parent.parent
SCHEMA_DIR = REPO_ROOT / "schemas"
FIXTURE_VALID = REPO_ROOT / "tests" / "fixtures" / "valid"
FIXTURE_INVALID = REPO_ROOT / "tests" / "fixtures" / "invalid"


def test_valid_fixtures_pass() -> None:
    passed, failed = validate_kb_directory(FIXTURE_VALID, SCHEMA_DIR)
    assert passed > 0
    assert failed == 0


def test_invalid_fixtures_fail() -> None:
    _passed, failed = validate_kb_directory(FIXTURE_INVALID, SCHEMA_DIR)
    assert failed > 0
