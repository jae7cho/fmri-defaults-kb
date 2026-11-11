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
    # 'line N at <version>': the file is recorded once per version in sources
    assert entry["ranges"][0]["source"] == "line 10 at 1; line 10 at 2"


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


def test_options_at_date_gives_the_latest_release_and_earlier_minors() -> None:
    out = options_at_date("fmriprep", date(2019, 6, 1), kb_root=KB)
    assert [(c["version"], c["latest"]) for c in out["candidates"]] == [
        ("1.4.0", True),
        ("1.3.2", False),
        ("1.2.6", False),
    ]
    assert all(c["released"] <= "2019-06-01" for c in out["candidates"])
    assert "coregistration" in out["candidates"][0]["step_defaults"]
    assert options_at_date("fmriprep", date(2010, 1, 1), kb_root=KB)["candidates"] == []


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
        in_config = [
            o
            for o in pipeline_options("cpac", src["version"], kb_root=KB).values()
            if o.get("in_config", True)
        ]
        assert len(in_config) == src["options"], src


def test_cpac_step_parameters_cover_the_steps() -> None:
    steps = {p["step"] for p in step_parameters("cpac", "1.8.7", kb_root=KB)}
    assert {"slice_timing", "nuisance_regression", "scrubbing", "temporal_filtering"} <= steps


# --- 2026-11-11 (fill all gaps): every release, the GUI, the key map, placement, step defaults -----


def test_the_fmriprep_timeline_covers_every_final_release() -> None:
    from fmri_defaults_kb import release_timeline

    t = release_timeline("fmriprep", kb_root=KB)
    assert len(t) == 143 and sum(r["listed"] for r in t) == 21
    assert t[0]["version"] == "0.0.3" and t[-1]["version"].startswith("25.")
    # a patch release the KB does not list has its own option set
    assert pipeline_options("fmriprep", "1.1.1", kb_root=KB)["--bold2t1w-dof"]["default"] == 9


def test_cpac_gui_defaults_sit_beside_the_config_default() -> None:
    o = pipeline_options("cpac", "0.3.6", kb_root=KB)
    assert (o["fwhm"]["default"], o["fwhm"]["gui_default"]) == ([6], "4")
    assert o["runNuisance"]["gui_default"] == "On"  # a choice box starts on its first value
    doc = yaml.safe_load((KB / "pipeline_options" / "cpac.yaml").read_text())
    rules = {s["version"]: s.get("gui_rules") for s in doc["sources"]}
    assert rules["0.3.2"] == {"choice_line": 198, "checklist_line": 246}
    assert rules["1.8.7"] is None  # no GUI pages after 1.8.0


def test_cpac_flat_keys_map_to_their_nested_paths() -> None:
    doc = yaml.safe_load((KB / "pipeline_options" / "cpac.yaml").read_text())
    by = {o["id"]: o for o in doc["options"]}
    assert by["fwhm"]["nested_as"] == "post_processing.spatial_smoothing.fwhm"
    assert "fwhm" in by["post_processing.spatial_smoothing.fwhm"]["flat_as"]
    assert by["fdCalc"]["deprecated_in_1_8"] is True
    assert "1.7-1.8-nesting-mappings.yml" in doc["key_map_source"]


def test_a_fixed_value_between_its_read_versions_is_uncertain() -> None:
    dof = [p for p in step_parameters("fmriprep", "1.1.1", kb_root=KB) if p["parameter"] == "dof"]
    assert len(dof) == 1 and dof[0]["uncertain"] is True
    assert "(to 1.1.0)" in dof[0]["value"] and "(from 1.2.0)" in dof[0]["value"]
    inside = [
        p for p in step_parameters("fmriprep", "1.2.0", kb_root=KB) if p["parameter"] == "dof"
    ]
    assert "uncertain" not in inside[0]
    late = (
        step_parameters("fmriprep", "25.2.3", kb_root=KB)
        if "25.2.3"
        in {
            r["version"]
            for r in __import__("fmri_defaults_kb").release_timeline("fmriprep", kb_root=KB)
        }
        else []
    )
    assert all(p.get("uncertain") for p in late)


def test_step_defaults_group_options_and_fixed_values_by_step() -> None:
    from fmri_defaults_kb import step_defaults

    sd = step_defaults("cpac", "1.0.1", kb_root=KB)
    assert set(sd["smoothing"]["options"]) == {"fwhm"}
    assert sd["smoothing"]["options"]["fwhm"]["config_role"] == "example"
    assert sd["scrubbing"]["fixed"]
    fp = step_defaults("fmriprep", "20.2.0", kb_root=KB)
    assert fp["coregistration"]["options"]["--bold2t1w-dof"]["default"] == 6
    assert fp["temporal_filtering"]["options"] == {} and fp["temporal_filtering"]["fixed"]


def test_gui_options_reads_add_calls_and_the_constructor_rules() -> None:
    import pipeline_option_sources as src

    page = """
self.page.add(label="Run", control=control.CHOICE_BOX, name='runX', values=["Off", "On"])
self.page.add(label="W", control=control.TEXT_BOX, name='fwhm', values="4")
self.page.add(label="L", control=control.CHECKLIST_BOX, name='chk', type=dtype.LBOOL, values=['a', 'b'])
self.page.add(label="N", control=control.CHECKLIST_BOX, name='chk2', type=dtype.LSTR, values=['a'])
# self.page.add(label="gone", control=control.TEXT_BOX, name='commented', values="1")
"""
    rules = src.gui_rule_lines("x\n            self.selection = values[0]\n")
    assert rules == {"choice": 2}
    tree_defaults = {}
    import ast

    for node in ast.walk(ast.parse(page)):
        if isinstance(node, ast.Call) and getattr(node.func, "attr", None) == "add":
            kw = {k.arg: k.value for k in node.keywords}
            tree_defaults[ast.literal_eval(kw["name"])] = kw
    assert "commented" not in tree_defaults
    assert src.CONTROL["CHOICE_BOX"] == 0 and src.CONTROL["CHECKLIST_BOX"] == 6
