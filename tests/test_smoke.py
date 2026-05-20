"""Smoke test: dev dependencies are importable."""

import jsonschema
import yaml


def test_imports() -> None:
    assert jsonschema is not None
    assert yaml is not None
