"""realignment_settings (2026-11-10): what a pipeline's realignment step passes to the wrapped tool's
job, and the wrapped tool's job default for every option the step leaves unset. The CONN entry is
read from the real KB; the edge cases from a copy of it."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

import pytest
import yaml
from jsonschema import Draft202012Validator

from fmri_defaults_kb import realignment_defaults, realignment_settings
from fmri_defaults_kb.errors import KbError, KbUnknownPipelineError

REPO_ROOT = Path(__file__).resolve().parents[1]
REAL_KB_ROOT = REPO_ROOT / "kb"
SCHEMA_DIR = REPO_ROOT / "schemas"
OPTIONS = (
    "reference_scan",
    "interpolation_estimate",
    "quality",
    "separation",
    "fwhm",
    "interpolation_reslice",
    "mask",
    "cost_function",
)


def _conn(version: str | None = None) -> dict[str, Any]:
    out = realignment_settings("conn", version, kb_root=REAL_KB_ROOT)
    assert out is not None
    return out


def _kb_copy(tmp_path: Path) -> Path:
    kb = tmp_path / "kb"
    shutil.copytree(REAL_KB_ROOT, kb)
    return kb


def _edit(path: Path, fn: Any) -> None:
    doc = yaml.safe_load(path.read_text())
    fn(doc)
    path.write_text(yaml.safe_dump(doc, sort_keys=False))


def test_conn_sets_register_to_first_and_cites_its_lines() -> None:
    ref = _conn()["reference_scan"]
    assert ref["value"] == "register to first"
    assert ref["set_by"] == "pipeline"
    assert ref["option"] == "eoptions.rtm"
    assert "lines 266, 2780 (rtm=0" in ref["source"]
    assert "every listed version (v20.07.29 to v25b)" in ref["source"]


@pytest.mark.parametrize(
    ("key", "value", "spm_line"),
    [
        ("interpolation_estimate", "2nd degree B-spline", "spm_defaults.m line 101"),
        ("quality", "0.9", "spm_defaults.m line 100"),
        ("separation", "4 mm", "spm_defaults.m line 103"),
        ("fwhm", "5 mm", "spm_defaults.m line 104"),
        ("interpolation_reslice", "4th degree B-spline", "spm_defaults.m line 107"),
    ],
)
def test_an_option_conn_leaves_unset_inherits_the_spm_job_default(
    key: str, value: str, spm_line: str
) -> None:
    item = _conn()[key]
    assert item["value"] == value
    assert item["set_by"] == "inherited"
    # the CONN line that builds the job and the SPM line the default is read from
    assert "the functional_realign&unwarp job (line 2780) leaves" in item["source"]
    assert spm_line in item["source"]


def test_every_option_the_entry_lists_is_resolved() -> None:
    out = _conn()
    assert all(out[k]["value"] for k in OPTIONS)
    assert out["documented_for"].startswith("SPM12 r7771")
    assert out["version_tokens"] == ["12"]


def test_mask_is_inherited_before_v22_and_set_from_v22_the_same_value() -> None:
    early = _conn("v21.06.05")["mask"]
    late = _conn("v25b")["mask"]
    assert (early["set_by"], late["set_by"]) == ("inherited", "pipeline")
    assert early["value"] == late["value"] == "mask images"
    assert "(line 2130) leaves uwroptions.mask unset" in early["source"]
    assert "lines 267, 2781 (rmask=1" in late["source"]
    both = _conn()["mask"]
    assert both["set_by"] == "mixed" and both["value"] == "mask images"
    assert both["source"].startswith("set from v22.06.27")


def test_a_listed_version_cites_its_own_lines_and_an_unlisted_one_reads_every_tag() -> None:
    assert (
        "conn_setup_preproc.m at v21.06.05, lines 190, 2130"
        in _conn("v21.06.05")["reference_scan"]["source"]
    )
    stated = realignment_settings("conn", "20.b", kb_root=REAL_KB_ROOT)
    assert stated is not None and stated["version"] is None
    assert "20.b is not a listed version" in stated["reference_scan"]["source"]


def test_the_inherited_reference_is_realign_and_unwarps_not_realigns(tmp_path: Path) -> None:
    """Were CONN to leave rtm unset, the job's default is register to first (unwarp.estimate.rtm),
    not Realign's register to mean."""
    kb = _kb_copy(tmp_path)
    _edit(
        kb / "pipelines" / "conn.yaml",
        lambda d: d["realignment_settings"]["settings"]["reference_scan"].update(
            ranges=[{"set": False}]
        ),
    )
    out = realignment_settings("conn", kb_root=kb)
    assert out is not None
    assert out["reference_scan"]["value"] == "register to first"
    assert out["reference_scan"]["set_by"] == "inherited"
    assert "spm_defaults.m line 113" in out["reference_scan"]["source"]
    realign = realignment_defaults("spm", kb_root=kb)
    assert realign is not None and realign["reference_scan"]["value"].startswith("register to mean")


def test_a_setting_whose_value_differs_across_tags_is_a_range_not_a_value(tmp_path: Path) -> None:
    kb = _kb_copy(tmp_path)

    def change(d: dict[str, Any]) -> None:
        d["realignment_settings"]["settings"]["interpolation_estimate"]["ranges"] = [
            {"to_version": "v21.12.28", "set": False},
            {
                "from_version": "v22.06.27",
                "set": True,
                "value": "trilinear",
                "assignment": "einterp=1",
                "cites": ["job"],
            },
        ]

    _edit(kb / "pipelines" / "conn.yaml", change)
    item = realignment_settings("conn", kb_root=kb)["interpolation_estimate"]  # type: ignore[index]
    assert item["value"] is None
    assert item["range"] == (
        "v20.07.29 to v21.12.28: 2nd degree B-spline (inherited); "
        "v22.06.27 to v25b: trilinear (set)"
    )
    # one listed version still has one value
    one = realignment_settings("conn", "v25b", kb_root=kb)
    assert one is not None and one["interpolation_estimate"]["value"] == "trilinear"


def test_an_inherited_option_the_tool_records_no_default_for_is_an_error(tmp_path: Path) -> None:
    kb = _kb_copy(tmp_path)
    _edit(
        kb / "tools" / "spm.yaml",
        lambda d: d["realignment"]["unwarp_defaults"].pop("quality"),
    )
    with pytest.raises(KbError, match="quality"):
        realignment_settings("conn", kb_root=kb)


def test_a_pipeline_without_settings_is_none_and_an_unknown_one_raises() -> None:
    assert realignment_settings("dparsf", kb_root=REAL_KB_ROOT) is None
    with pytest.raises(KbUnknownPipelineError):
        realignment_settings("no_such_pipeline", kb_root=REAL_KB_ROOT)


def test_the_schema_requires_a_value_and_its_lines_when_the_pipeline_sets_an_option() -> None:
    schema = json.loads((SCHEMA_DIR / "pipeline_registry.schema.json").read_text())
    conn = yaml.safe_load((REAL_KB_ROOT / "pipelines" / "conn.yaml").read_text())
    validator = Draft202012Validator(schema)
    assert not list(validator.iter_errors(conn))
    broken = json.loads(json.dumps(conn))
    broken["realignment_settings"]["settings"]["reference_scan"]["ranges"] = [{"set": True}]
    assert list(validator.iter_errors(broken))


# --- 2026-11-11: fMRIPrep, C-PAC and HCP (blocks by version range, source text) ---------------


def test_fmriprep_leaves_cost_and_estimation_to_mcflirt_and_its_reference_varies() -> None:
    out = realignment_settings("fmriprep", kb_root=REAL_KB_ROOT)
    assert out is not None and out["wraps"] == "fsl" and out["job"] == "mcflirt"
    assert out["cost_function"]["value"].startswith("normalised correlation")
    assert out["cost_function"]["set_by"] == "inherited"
    assert "Globaloptions.h line 99" in out["cost_function"]["source"]
    assert out["interpolation_estimate"]["value"] == "trilinear"
    assert out["interpolation_reslice"]["set_by"] == "pipeline"
    assert out["interpolation_reslice"]["value"].startswith("not from MCFLIRT")
    ref = out["reference_scan"]
    assert ref["value"] is None and "23.2.0 to 25.2.0" in ref["range"]
    one = realignment_settings("fmriprep", "22.0.0", kb_root=REAL_KB_ROOT)
    assert one is not None and "SBRef) when present" in one["reference_scan"]["value"]
    late = realignment_settings("fmriprep", "25.2.0", kb_root=REAL_KB_ROOT)
    assert late is not None and "SBRef is not used" in late["reference_scan"]["value"]


def test_cpac_sets_fourier_and_leaves_the_cost_to_3dvolreg() -> None:
    out = realignment_settings("cpac", kb_root=REAL_KB_ROOT)
    assert out is not None and out["wraps"] == "afni"
    assert (out["interpolation_estimate"]["value"], out["interpolation_estimate"]["set_by"]) == (
        "Fourier",
        "pipeline",
    )
    assert out["interpolation_reslice"]["value"].startswith("Fourier")
    assert out["cost_function"]["value"] == "weighted least squares"
    assert out["cost_function"]["set_by"] == "inherited"
    assert out["reference_scan"]["value"] is None  # mean, two passes -> configurable -> one pass
    late = realignment_settings("cpac", "1.8.7", kb_root=REAL_KB_ROOT)
    assert late is not None and "in one pass" in late["reference_scan"]["value"]


def test_hcp_switches_job_by_version_and_the_cost_differs_across_them() -> None:
    flirt = realignment_settings("hcp_minimal", "v3.4.0", kb_root=REAL_KB_ROOT)
    mcflirt = realignment_settings("hcp_minimal", "v4.1.3", kb_root=REAL_KB_ROOT)
    assert flirt is not None and mcflirt is not None
    assert (flirt["job"], mcflirt["job"]) == ("flirt", "mcflirt")
    assert flirt["cost_function"]["value"] == "correlation ratio (corratio)"
    assert "globaloptions.cc line 408" in flirt["cost_function"]["source"]
    assert mcflirt["cost_function"]["value"].startswith("normalised correlation")
    both = realignment_settings("hcp_minimal", kb_root=REAL_KB_ROOT)
    assert both is not None
    assert both["cost_function"]["value"] is None
    assert both["cost_function"]["range"] == (
        "v3.4.0: correlation ratio (corratio) (inherited); "
        "v4.1.3: normalised correlation (normcorr) (inherited)"
    )
    # the scout reference and the trilinear estimation hold in both eras
    assert both["reference_scan"]["value"].startswith("the scout image")
    assert both["interpolation_estimate"]["value"] == "trilinear"
    # the data releases' v3.1 is not a listed version: it reads both eras
    stated = realignment_settings("hcp_minimal", "v3.1", kb_root=REAL_KB_ROOT)
    assert stated is not None and stated["cost_function"]["value"] is None


def test_two_blocks_covering_one_version_is_an_error(tmp_path: Path) -> None:
    kb = _kb_copy(tmp_path)

    def overlap(d: dict[str, Any]) -> None:
        d["realignment_settings"][1].pop("from_version")

    _edit(kb / "pipelines" / "hcp_minimal.yaml", overlap)
    with pytest.raises(KbError, match="2 realignment_settings blocks cover"):
        realignment_settings("hcp_minimal", kb_root=kb)


def test_the_schema_requires_a_source_or_cites_for_a_set_range() -> None:
    schema = json.loads((SCHEMA_DIR / "pipeline_registry.schema.json").read_text())
    validator = Draft202012Validator(schema)
    doc = yaml.safe_load((REAL_KB_ROOT / "pipelines" / "cpac.yaml").read_text())
    assert not list(validator.iter_errors(doc))
    doc["realignment_settings"]["settings"]["interpolation_estimate"]["ranges"][0].pop("source")
    assert list(validator.iter_errors(doc))
