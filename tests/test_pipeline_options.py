"""Pipeline option inventories (2026-11-11): the extractor's parsing and range compression, the
lookup functions, and known facts of the generated fMRIPrep inventory."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

import pytest
import yaml
from jsonschema import Draft202012Validator

import extract_pipeline_options as ex
from fmri_defaults_kb import options_at_date, pipeline_options, step_parameters
from fmri_defaults_kb.errors import KbUnknownPipelineError, KbUnknownVersionError

REPO_ROOT = Path(__file__).resolve().parents[1]
KB = REPO_ROOT / "kb"

PARSER = """
import argparse
parser = argparse.ArgumentParser()
g_conf = parser.add_argument_group('Workflow configuration')
g_conf.add_argument('--bold2t1w-dof', action='store', default=6, choices=[6, 9, 12], type=int,
                    help='Degrees of freedom ' 'when registering')
# g_conf.add_argument('--commented-out', default=1)
g_conf.add_argument('--output-spaces', default=SpatialReferences(), nargs='*')
parser.add_argument('bids_dir', action='store')
"""

CONFIG = """
# the pipeline name
pipeline_setup:
  pipeline_name: cpac-default
# Smoothing
# FWHM in mm
spatial_smoothing:
  fwhm: [4]
  run: [On]
"""


def test_argparse_options_reads_groups_defaults_and_skips_comments() -> None:
    opts = {o["id"]: o for o in ex.argparse_options(PARSER)}
    assert set(opts) == {"--bold2t1w-dof", "--output-spaces", "bids_dir"}
    dof = opts["--bold2t1w-dof"]
    assert (dof["group"], dof["default"], dof["choices"], dof["type"]) == (
        "Workflow configuration",
        6,
        [6, 9, 12],
        "int",
    )
    assert dof["help"] == "Degrees of freedom when registering"
    # a default that is not a literal is kept as its expression, never evaluated
    assert opts["--output-spaces"]["default"] == {"expression": "SpatialReferences()"}


def test_yaml_options_flattens_keys_with_their_comments_and_lines() -> None:
    opts = {o["id"]: o for o in ex.yaml_options(CONFIG)}
    assert opts["spatial_smoothing.fwhm"]["default"] == [4]
    assert opts["spatial_smoothing.fwhm"]["line"] == 8
    assert opts["pipeline_setup.pipeline_name"]["help"] is None  # its comment is above the parent
    assert ex.yaml_options("# only a comment\n") == []


def test_compress_starts_a_range_only_where_the_default_changes() -> None:
    def v(default: int) -> tuple[str | None, list[dict[str, Any]]]:
        return ("p.py", [{"id": "--x", "default": default, "choices": None, "line": 10}])

    per: dict[str, tuple[str | None, list[dict[str, Any]]]] = {
        "1": v(9),
        "2": v(9),
        "3": v(6),
        "4": ("p.py", []),
        "5": v(6),
    }
    (entry,) = ex.compress(per, ["1", "2", "3", "4", "5"])
    assert [(r["from_version"], r["to_version"], r["default"]) for r in entry["ranges"]] == [
        ("1", "2", 9),
        ("3", "3", 6),
        ("5", "5", 6),
    ]
    assert entry["available"] == {"versions": ["1", "2", "3", "5"]}
    assert entry["ranges"][0]["source"] == "p.py line 10 at 1; p.py line 10 at 2"


def test_the_generated_inventory_validates() -> None:
    schema = json.loads((REPO_ROOT / "schemas" / "pipeline_options.schema.json").read_text())
    doc = yaml.safe_load((KB / "pipeline_options" / "fmriprep.yaml").read_text())
    validator = Draft202012Validator(schema)
    assert not list(validator.iter_errors(doc))
    doc["options"][0]["ranges"][0].pop("source")
    assert list(validator.iter_errors(doc))


def test_fmriprep_bold2t1w_dof_was_9_then_6() -> None:
    assert pipeline_options("fmriprep", "1.1.0", kb_root=KB)["--bold2t1w-dof"]["default"] == 9
    assert pipeline_options("fmriprep", "1.2.0", kb_root=KB)["--bold2t1w-dof"]["default"] == 6
    assert pipeline_options("fmriprep", "1.2.0", kb_root=KB)["--bold2t1w-dof"]["choices"] == [
        6,
        9,
        12,
    ]


def test_an_option_is_only_offered_where_it_exists() -> None:
    assert "--fd-spike-threshold" not in pipeline_options("fmriprep", "1.3.0", kb_root=KB)
    assert (
        pipeline_options("fmriprep", "1.4.0", kb_root=KB)["--fd-spike-threshold"]["default"] == 0.5
    )
    assert "--use-aroma" not in pipeline_options("fmriprep", "25.0.0", kb_root=KB)


def test_the_option_count_at_each_version_matches_the_parser() -> None:
    doc = yaml.safe_load((KB / "pipeline_options" / "fmriprep.yaml").read_text())
    for src in doc["sources"]:
        assert len(pipeline_options("fmriprep", src["version"], kb_root=KB)) == src["options"], src


def test_options_at_date_gives_the_candidates_released_by_then() -> None:
    out = options_at_date("fmriprep", date(2019, 6, 1), kb_root=KB)
    chosen = [c for c in out["candidates"] if c["chosen"]]
    assert [c["version"] for c in chosen] == ["1.4.0"]
    assert out["basis"] == "date_inferred_version" and out["version_certain"] is False
    assert all(isinstance(c["step_parameters"], list) for c in out["candidates"])


def test_unknown_pipeline_or_version_raises() -> None:
    with pytest.raises(KbUnknownPipelineError):
        pipeline_options("conn", "v25b", kb_root=KB)
    with pytest.raises(KbUnknownVersionError):
        step_parameters("fmriprep", "0.9.9", kb_root=KB)


def _param(version: str, step: str, name: str) -> str:
    found = [
        p["value"]
        for p in step_parameters("fmriprep", version, kb_root=KB)
        if (p["step"], p["parameter"]) == (step, name)
    ]
    assert len(found) == 1, (version, step, name)
    return str(found[0])


def test_fmriprep_step_parameters_change_where_the_code_changed() -> None:
    assert "6.0 mm" in _param("20.2.0", "smoothing", "ica_aroma_input_smoothing")
    assert "removed" in _param("23.1.0", "smoothing", "ica_aroma_input_smoothing")
    assert "128 s" in _param("1.0.0", "temporal_filtering", "compcor_highpass")
    assert "Lanczos" in _param("23.1.0", "normalization", "bold_resampling_interpolation")
    assert "Lanczos" not in _param("23.2.0", "normalization", "bold_resampling_interpolation")


def test_every_step_parameter_range_cites_a_tag() -> None:
    for p in step_parameters("fmriprep", "25.2.0", kb_root=KB):
        assert " line" in p["source"], p


# --- C-PAC: the default configuration at each version --------------------------------------------


def test_a_key_written_twice_keeps_its_last_value_as_safe_load_does() -> None:
    opts = {o["id"]: o for o in ex.yaml_options("a:\n  b: 1\n  b: 2\n")}
    assert opts["a.b"]["default"] == 2 and opts["a.b"]["line"] == 3


def test_an_invalid_line_is_dropped_and_recorded() -> None:
    dropped: list[str] = []
    opts = ex.yaml_options("x: None\n  - /p.nii.gz: Avg, Voxel\ny: 1\n", dropped)
    assert {o["id"] for o in opts} == {"x", "y"}
    assert len(dropped) == 1 and dropped[0].startswith("line 2")


def test_cpac_example_configs_carry_their_caveat() -> None:
    fwhm = pipeline_options("cpac", "0.3.6", kb_root=KB)["fwhm"]
    assert fwhm["default"] == [6] and fwhm["config_role"] == "example"
    assert "'4'" in fwhm["config_note"]  # the GUI's default differs
    late = pipeline_options("cpac", "1.8.7", kb_root=KB)["post_processing.spatial_smoothing.fwhm"]
    assert late["default"] == [4] and "config_role" not in late


def test_cpac_records_the_lines_it_could_not_parse() -> None:
    doc = yaml.safe_load((KB / "pipeline_options" / "cpac.yaml").read_text())
    notes = {s["version"]: s.get("note", "") for s in doc["sources"]}
    assert "unparseable lines dropped: line 364" in notes["1.0.3"]
    assert notes["1.1.0"].count("line ") >= 2


def test_cpac_option_counts_match_the_configuration_at_each_version() -> None:
    doc = yaml.safe_load((KB / "pipeline_options" / "cpac.yaml").read_text())
    assert len(doc["sources"]) == 34
    for src in doc["sources"]:
        assert len(pipeline_options("cpac", src["version"], kb_root=KB)) == src["options"], src


def test_cpac_step_parameters_cover_the_steps() -> None:
    steps = {p["step"] for p in step_parameters("cpac", "1.8.7", kb_root=KB)}
    assert {"slice_timing", "nuisance_regression", "scrubbing", "temporal_filtering"} <= steps
