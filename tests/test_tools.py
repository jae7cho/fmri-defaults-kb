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
from fmri_defaults_kb.tools import KbNoRealignmentError, clear_tool_cache, load_tool_documents

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
    assert (
        len(docs) == 11
    )  # mmps, freesurfer 2026-11-03; fmriprep, conn, cat12 2026-11-05; bioimage_suite 2026-11-09
    for p in docs:
        errors = sorted(v.iter_errors(yaml.safe_load(p.read_text())), key=str)
        assert not errors, f"{p.name}: {[e.message for e in errors]}"


def test_the_six_packages_with_a_program_and_a_source_each() -> None:
    docs = load_tool_documents(REAL_KB_ROOT)
    # mmps and freesurfer added 2026-11-03 (the author's requests; freesurfer has no realignment);
    # fmriprep, conn and cat12 added 2026-11-05 (the agent's stress_v1 fix 5; no realignment block)
    assert set(docs) == {
        "afni",
        "fsl",
        "spm",
        "ants",
        "brainvoyager",
        "mmps",
        "freesurfer",
        "fmriprep",
        "conn",
        "cat12",
        "bioimage_suite",  # 2026-11-09, the software scan; no realignment block
    }
    expected = {
        "afni": "3dvolreg",
        "fsl": "MCFLIRT",
        "spm": "Realign",
        "ants": "antsMotionCorr",
        "mmps": "3dvolreg",
    }
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
        ("MMPS", "mmps"),
        ("FreeSurfer", "freesurfer"),
        ("Multi-Modal Processing Stream", "mmps"),
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
        "mmps": False,
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


def test_a_package_without_a_realignment_program_is_listed_but_not_in_the_fallback() -> None:
    """2026-11-03: the realignment block is optional (FreeSurfer)."""
    docs = load_tool_documents(REAL_KB_ROOT)
    assert "realignment" not in docs["freesurfer"]
    assert [p["name"] for p in docs["freesurfer"]["programs"]] == [
        "recon-all",
        "aseg",
        "mri_vol2surf",
    ]
    assert all(p["source"] for p in docs["freesurfer"]["programs"])
    with pytest.raises(KbNoRealignmentError):
        realignment_program("freesurfer", kb_root=REAL_KB_ROOT)
    assert "freesurfer" not in listed_package_tokens(kb_root=REAL_KB_ROOT)


def test_the_three_packages_added_for_the_software_scan_have_no_realignment_program() -> None:
    # 2026-11-05: fMRIPrep, CONN and CAT12 are scanned for; none answers the motion fallback
    from fmri_defaults_kb.tools import KbNoRealignmentError

    docs = load_tool_documents(REAL_KB_ROOT)
    for tool_id in ("fmriprep", "conn", "cat12"):
        assert docs[tool_id]["programs"][0]["source"]
        with pytest.raises(KbNoRealignmentError):
            realignment_program(tool_id, kb_root=REAL_KB_ROOT)
    assert recognize_tool("CONN toolbox", kb_root=REAL_KB_ROOT) == "conn"
    assert recognize_tool("CAT12", kb_root=REAL_KB_ROOT) == "cat12"
    assert recognize_tool("fMRIPrep", kb_root=REAL_KB_ROOT) == "fmriprep"


def test_title_case_conn_is_recognized_only_as_a_toolbox_phrase() -> None:
    assert recognize_tool("Conn Connectivity toolbox", kb_root=REAL_KB_ROOT) == "conn"
    aliases = load_tool_documents(REAL_KB_ROOT)["conn"]["aliases"]
    assert "Conn" not in aliases  # a surname too
