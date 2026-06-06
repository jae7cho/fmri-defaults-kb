#!/usr/bin/env python3
"""Walk kb/ and validate every file against its corresponding JSON Schema."""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path
from typing import Any, cast

import yaml
from jsonschema import Draft202012Validator, FormatChecker

YAML_SCHEMA_MAPPING: dict[str, str] = {
    "tools": "tool_version.schema.json",
    "labs": "lab_fingerprint.schema.json",
    "citations": "citation_flagmap.schema.json",
    "pipelines": "pipeline_registry.schema.json",
}
CSV_SUBDIR = "dates"
CSV_SCHEMA = "date_version.schema.json"


def load_schema(schema_dir: Path, schema_name: str) -> dict[str, Any]:
    """Load a JSON Schema file from schema_dir by name."""
    with (schema_dir / schema_name).open("r", encoding="utf-8") as f:
        return cast("dict[str, Any]", json.load(f))


def _format_error(err) -> str:
    path = "/".join(str(p) for p in err.absolute_path) or "<root>"
    return f"{path}: {err.message}"


def validate_yaml_file(file_path: Path, schema: dict) -> list[str]:
    """Validate a single YAML file against the given schema. Return error messages."""
    with file_path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    return [_format_error(e) for e in validator.iter_errors(data)]


def validate_csv_file(file_path: Path, schema: dict) -> list[str]:
    """Validate each row of a CSV file against the given schema. Return error messages."""
    errors: list[str] = []
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    with file_path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row_index, row in enumerate(reader, start=2):
            for err in validator.iter_errors(row):
                errors.append(f"row {row_index}: {_format_error(err)}")
    return errors


def validate_kb_directory(kb_dir: Path, schema_dir: Path) -> tuple[int, int]:
    """Walk kb_dir, validate every file, print PASS/FAIL, return (passed, failed)."""
    passed = 0
    failed = 0

    for subdir_name, schema_name in YAML_SCHEMA_MAPPING.items():
        subdir = kb_dir / subdir_name
        if not subdir.exists():
            continue
        schema = load_schema(schema_dir, schema_name)
        for yaml_file in sorted(subdir.rglob("*.yaml")):
            errors = validate_yaml_file(yaml_file, schema)
            if errors:
                failed += 1
                print(f"FAIL {yaml_file}: {'; '.join(errors)}")
            else:
                passed += 1
                print(f"PASS {yaml_file}")

    dates_dir = kb_dir / CSV_SUBDIR
    if dates_dir.exists():
        schema = load_schema(schema_dir, CSV_SCHEMA)
        for csv_file in sorted(dates_dir.glob("*.csv")):
            errors = validate_csv_file(csv_file, schema)
            if errors:
                failed += 1
                print(f"FAIL {csv_file}: {'; '.join(errors)}")
            else:
                passed += 1
                print(f"PASS {csv_file}")

    return passed, failed


def main() -> int:
    schema_dir = Path("schemas")
    if not schema_dir.exists():
        print(f"ERROR: schemas directory not found at {schema_dir.resolve()}")
        return 1

    kb_dir = Path("kb")
    passed, failed = validate_kb_directory(kb_dir, schema_dir)

    if passed == 0 and failed == 0:
        print("nothing to validate")
    print(f"Summary: {passed} passed, {failed} failed")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
