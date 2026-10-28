"""kb/tools/: the package table and its reader (2026-10-28)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml
from jsonschema import Draft202012Validator

from fmri_defaults_kb import (
    KbUnknownToolError,
    listed_package_tokens,
    realignment_program,
    recognize_tool,
)
from fmri_defaults_kb.tools import clear_tool_cache, load_tool_documents

REPO_ROOT = Path(__file__).parent.parent
REAL_KB_ROOT = REPO_ROOT / "kb"
SCHEMA = json.loads((REPO_ROOT / "schemas" / "tool_registry.schema.json").read_text())


@pytest.fixture(autouse=True)
def _isolated_cache():
    clear_tool_cache()
    yield
    clear_tool_cache()


def test_every_tool_document_is_schema_valid() -> None:
    v = Draft202012Validator(SCHEMA)
    docs = sorted((REAL_KB_ROOT / "tools").glob("*.yaml"))
    assert len(docs) == 5
    for p in docs:
        errors = sorted(v.iter_errors(yaml.safe_load(p.read_text())), key=str)
        assert not errors, f"{p.name}: {[e.message for e in errors]}"


def test_the_five_packages_with_a_program_and_a_source_each() -> None:
    docs = load_tool_documents(REAL_KB_ROOT)
    assert set(docs) == {"afni", "fsl", "spm", "ants", "brainvoyager"}
    expected = {"afni": "3dvolreg", "fsl": "MCFLIRT", "spm": "Realign", "ants": "antsMotionCorr"}
    for tool_id, program in expected.items():
        rp = realignment_program(tool_id, kb_root=REAL_KB_ROOT)
        assert rp.program == program and rp.source
    assert realignment_program("brainvoyager", kb_root=REAL_KB_ROOT).source
    with pytest.raises(KbUnknownToolError):
        realignment_program("cpac", kb_root=REAL_KB_ROOT)


@pytest.mark.parametrize(
    ("name", "tool_id"),
    [
        ("SPM12", "spm"),
        ("SPM8", "spm"),
        ("spm", "spm"),
        ("Statistical Parametric Mapping 12", "spm"),
        ("Statistical Parametric Mapping", "spm"),
        ("FSL", "fsl"),
        ("FSL suite", "fsl"),
        ("FMRIB Software Library", "fsl"),
        ("AFNI", "afni"),
        ("ANTs", "ants"),
        ("BrainVoyager QX", "brainvoyager"),
        ("FSL 5.0.10", None),  # a separately written version is not part of FSL's name token
        ("AFNI48", None),  # the citation artefact is not a name either; the fallback handles tokens
        ("C-PAC", None),  # a pipeline, not a package
        ("XCP Engine", None),
        ("FCP analysis scripts", None),
        ("MCFLIRT", None),  # a program, not a package
        ("", None),
    ],
)
def test_recognize_tool_matches_whole_names_and_strips_a_version_token_only_for_spm(
    name: str, tool_id: str | None
) -> None:
    assert recognize_tool(name, kb_root=REAL_KB_ROOT) == tool_id


def test_listed_package_tokens_is_the_table_the_fallback_reads() -> None:
    assert listed_package_tokens(kb_root=REAL_KB_ROOT) == {
        "afni": False,
        "fsl": False,
        "spm": True,
        "ants": False,
        "brainvoyager": False,
    }


def test_a_name_two_tools_share_is_refused_not_guessed(tmp_path: Path) -> None:
    """The ambiguity guard: two documents listing the same alias -> None, never the first hit."""
    tools = tmp_path / "tools"
    tools.mkdir()
    for tool_id in ("alpha", "beta"):
        (tools / f"{tool_id}.yaml").write_text(
            f"tool_id: {tool_id}\ndisplay_name: {tool_id.title()}\naliases:\n  - shared name\n"
            "version_token: false\nrealignment:\n  program: x\n  source: y\n",
            encoding="utf-8",
        )
    assert recognize_tool("shared name", kb_root=tmp_path) is None
    assert recognize_tool("Alpha", kb_root=tmp_path) == "alpha"
