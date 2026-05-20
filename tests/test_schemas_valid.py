"""Each *.schema.json under schemas/ must itself be a valid Draft 2020-12 schema."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

SCHEMA_DIR = Path(__file__).parent.parent / "schemas"
SCHEMA_FILES = sorted(SCHEMA_DIR.glob("*.schema.json"))


@pytest.mark.parametrize("schema_path", SCHEMA_FILES, ids=[p.name for p in SCHEMA_FILES])
def test_schema_is_valid_draft_2020_12(schema_path: Path) -> None:
    with schema_path.open("r", encoding="utf-8") as f:
        schema = json.load(f)
    Draft202012Validator.check_schema(schema)
