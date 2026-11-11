"""2026-11-11: every realignment range and tool realignment entry says how its program attribution
is verified; the WashU 4dfp pipeline entry."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml
from jsonschema import Draft202012Validator

from fmri_defaults_kb import (
    get_realignment_tool,
    realignment_program,
    realignment_settings,
    recognize,
    recognize_program,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
KB = REPO_ROOT / "kb"
SCHEMAS = REPO_ROOT / "schemas"
KINDS = {"script_at_tag", "manual", "paper", "unverified"}

#: Read from each entry's source text (DEVLOG 2026-11-11): the strongest evidence it cites.
EXPECTED_PIPELINES = {
    "abcd_bids": ["script_at_tag"],
    "abcd_daic": ["paper"],
    "ccs": ["script_at_tag"],
    "conn": ["script_at_tag"],
    "cpac": ["script_at_tag", "script_at_tag"],
    "dparsf": ["script_at_tag"],
    "fcp_scripts": ["script_at_tag"],
    "fmriprep": ["manual"],
    "hcp_minimal": ["script_at_tag", "script_at_tag"],
    "washu_4dfp": ["manual"],
}
EXPECTED_TOOLS = {
    "afni": "manual",
    "ants": "manual",
    "brainvoyager": "manual",
    "fsl": "manual",
    "mmps": "paper",
    "spm": "manual",
}


def test_every_pipeline_range_records_its_verification() -> None:
    seen = {}
    for f in sorted((KB / "pipelines").glob("*.yaml")):
        doc = yaml.safe_load(f.read_text())
        ranges = (doc.get("realignment_tool") or {}).get("ranges") or []
        seen[doc["pipeline_id"]] = [r["verification"] for r in ranges]
        assert all(v in KINDS for v in seen[doc["pipeline_id"]]), f.name
    assert seen == EXPECTED_PIPELINES


def test_every_tool_realignment_entry_records_its_verification() -> None:
    seen = {}
    for f in sorted((KB / "tools").glob("*.yaml")):
        doc = yaml.safe_load(f.read_text())
        if doc.get("realignment"):
            seen[doc["tool_id"]] = doc["realignment"]["verification"]
    assert seen == EXPECTED_TOOLS


def test_the_lookups_carry_it() -> None:
    assert get_realignment_tool("hcp_minimal", "v3.4.0", kb_root=KB).verification == "script_at_tag"  # type: ignore[union-attr]
    assert get_realignment_tool("abcd_daic", "Hagler2019", kb_root=KB).verification == "paper"  # type: ignore[union-attr]
    assert realignment_program("fsl", kb_root=KB).verification == "manual"


@pytest.mark.parametrize(
    ("schema", "path"),
    [
        ("pipeline_registry.schema.json", ("realignment_tool", "ranges", 0)),
        ("tool_registry.schema.json", ("realignment",)),
    ],
)
def test_the_schemas_reject_an_entry_without_it(schema: str, path: tuple[object, ...]) -> None:
    validator = Draft202012Validator(json.loads((SCHEMAS / schema).read_text()))
    doc = yaml.safe_load(
        (
            KB / ("pipelines/conn.yaml" if path[0] == "realignment_tool" else "tools/spm.yaml")
        ).read_text()
    )
    assert not list(validator.iter_errors(doc))
    target = doc
    for key in path:
        target = target[key]
    target.pop("verification")
    assert list(validator.iter_errors(doc))
    target["verification"] = "read it somewhere"
    assert list(validator.iter_errors(doc))


@pytest.mark.parametrize(
    "name",
    [
        "pipeline developed at Washington University",
        "pipeline developed at Washington University, St Louis",
        "Washington University in St. Louis",
        "WashU pipeline",
        "4dfp",
    ],
)
def test_the_washu_aliases_resolve(name: str) -> None:
    assert recognize(name, kb_root=KB) == "washu_4dfp"


def test_washu_runs_cross_realign3d_4dfp_with_no_reference_asserted() -> None:
    rt = get_realignment_tool("washu_4dfp", "Power2014", kb_root=KB)
    assert rt is not None
    assert (rt.program, rt.package, rt.configurable, rt.verification) == (
        "cross_realign3d_4dfp",
        "4dfp",
        False,
        "manual",
    )
    assert "motion correct fMRI timeseries within and across runs" in rt.source
    assert "No reference frame is asserted" in (rt.notes or "")
    assert realignment_settings("washu_4dfp", kb_root=KB) is None  # no settings asserted
    assert recognize_program("realigned with cross_realign3d_4dfp", kb_root=KB) == (
        "cross_realign3d_4dfp",
        "4dfp",
    )
    doc = yaml.safe_load((KB / "pipelines" / "washu_4dfp.yaml").read_text())
    assert [v["version_kind"] for v in doc["versions"]] == ["paper_anchored"]


def test_afni_records_when_3dvolreg_is_documented_and_its_2d_alternatives() -> None:
    doc = yaml.safe_load((KB / "tools" / "afni.yaml").read_text())
    progs = {p["name"]: p for p in doc["programs"]}
    vol = progs["3dvolreg"]
    assert vol["available_from"] == "2.21"
    assert "November 1998" in vol["available_from_source"]
    assert vol["alternatives"] == ["imreg", "2dImReg"]
    assert "version-dependent" in vol["notes"]
    assert {"imreg", "2dImReg"} <= set(progs)


def test_no_other_tool_has_a_timeline_yet() -> None:
    with_timeline = []
    for f in sorted((KB / "tools").glob("*.yaml")):
        doc = yaml.safe_load(f.read_text())
        if any("available_from" in p for p in doc.get("programs") or []):
            with_timeline.append(doc["tool_id"])
    assert with_timeline == ["afni"]
