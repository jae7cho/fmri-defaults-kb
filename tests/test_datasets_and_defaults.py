"""kb/datasets, the dataset fallback of recognize(), and the realignment defaults (2026-11-09)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml
from jsonschema import Draft202012Validator

from fmri_defaults_kb import (
    VIA_DATA_RELEASE,
    KbUnknownToolError,
    load_dataset_documents,
    realignment_defaults,
    recognize,
    recognize_dataset,
    recognize_tool,
    recognize_with_provenance,
)
from fmri_defaults_kb.datasets import same_release
from fmri_defaults_kb.io import load_pipeline_documents

REAL_KB_ROOT = Path(__file__).resolve().parents[1] / "kb"
SCHEMAS = Path(__file__).resolve().parents[1] / "schemas"


def test_every_dataset_is_schema_valid_and_points_at_a_listed_pipeline() -> None:
    v = Draft202012Validator(json.loads((SCHEMAS / "dataset_registry.schema.json").read_text()))
    docs = sorted((REAL_KB_ROOT / "datasets").glob("*.yaml"))
    pipelines = load_pipeline_documents(REAL_KB_ROOT)
    assert {p.stem for p in docs} == {
        "hcp_s900",
        "hcp_s1200",
        "hcp_d_2_0",
        "abcd_3_0",
        "abcd_4_0",
        "abcd_5_0",
        "abcd_collection_3165",
    }
    for p in docs:
        doc = yaml.safe_load(p.read_text())
        assert not list(v.iter_errors(doc)), p.name
        assert doc["dataset_id"] == p.stem and doc["pipeline"] in pipelines
        assert doc["source"]
    # a version only where the release document states one (the two HCP-YA manuals)
    versions = {
        d["dataset_id"]: d.get("pipeline_version")
        for d in load_dataset_documents(REAL_KB_ROOT).values()
    }
    assert {k for k, v in versions.items() if v} == {"hcp_s900", "hcp_s1200"}


def test_a_release_alias_resolves_through_recognize_with_its_provenance() -> None:
    assert recognize("HCP S1200", kb_root=REAL_KB_ROOT) == "hcp_minimal"
    assert recognize_with_provenance("HCP S1200", kb_root=REAL_KB_ROOT) == (
        "hcp_minimal",
        VIA_DATA_RELEASE,
    )
    assert recognize_with_provenance("ABCD Release 4.0", kb_root=REAL_KB_ROOT) == (
        "abcd_daic",
        VIA_DATA_RELEASE,
    )
    assert recognize_with_provenance("NDA collection 3165", kb_root=REAL_KB_ROOT) == (
        "abcd_bids",
        VIA_DATA_RELEASE,
    )
    # a pipeline name keeps its own provenance
    assert recognize_with_provenance("HCP pipelines", kb_root=REAL_KB_ROOT) == (
        "hcp_minimal",
        "pipeline name",
    )
    assert recognize_with_provenance("DPABI", kb_root=REAL_KB_ROOT) == ("dparsf", "pipeline name")


@pytest.mark.parametrize(
    "name", ["HCP", "ABCD", "Human Connectome Project", "ABCD Study", "HCP-YA"]
)
def test_a_bare_study_name_is_not_a_pipeline_name(name: str) -> None:
    assert recognize(name, kb_root=REAL_KB_ROOT) is None
    assert recognize_with_provenance(name, kb_root=REAL_KB_ROOT) is None


@pytest.mark.parametrize(
    ("name", "release", "pipeline", "version", "ids"),
    [
        ("ABCD Study", "3.0", "abcd_daic", None, ("abcd_3_0",)),
        (
            "Adolescent Brain Cognitive Development (ABCD) Study",
            "4.0",
            "abcd_daic",
            None,
            ("abcd_4_0",),
        ),
        ("ABCD", "Release 5.0", "abcd_daic", None, ("abcd_5_0",)),
        ("ABCD", None, "abcd_daic", None, ("abcd_3_0", "abcd_4_0", "abcd_5_0")),
        ("Human Connectome Project", "S900", "hcp_minimal", "v3.1", ("hcp_s900",)),
        ("Human Connectome Project", "1200 Subjects", "hcp_minimal", "v3.1", ("hcp_s1200",)),
        ("HCP-YA", None, "hcp_minimal", "v3.1", ("hcp_s1200", "hcp_s900")),
        ("HCP-D", None, "hcp_minimal", None, ("hcp_d_2_0",)),
        ("ABCC", None, "abcd_bids", None, ("abcd_collection_3165",)),
    ],
)
def test_a_study_name_and_release_resolve_to_the_pipeline(
    name: str, release: str | None, pipeline: str, version: str | None, ids: tuple[str, ...]
) -> None:
    m = recognize_dataset(name, release, kb_root=REAL_KB_ROOT)
    assert m is not None
    assert (m.pipeline_id, m.pipeline_version, m.dataset_ids, m.provenance) == (
        pipeline,
        version,
        ids,
        VIA_DATA_RELEASE,
    )


def test_an_unlisted_release_or_an_unknown_study_resolves_to_nothing() -> None:
    assert recognize_dataset("ABCD", "2.0", kb_root=REAL_KB_ROOT) is None
    assert recognize_dataset("UK Biobank", None, kb_root=REAL_KB_ROOT) is None


def test_a_study_whose_releases_map_to_two_pipelines_is_ambiguous(tmp_path: Path) -> None:
    kb = tmp_path / "kb"
    (kb / "datasets").mkdir(parents=True)
    for rid, pipe in (("syn_1", "p_one"), ("syn_2", "p_two")):
        (kb / "datasets" / f"{rid}.yaml").write_text(
            yaml.safe_dump(
                {
                    "dataset_id": rid,
                    "display_name": rid,
                    "aliases": [f"SYN {rid}"],
                    "family": "syn",
                    "family_aliases": ["Synthetic Study"],
                    "release": rid[-1],
                    "pipeline": pipe,
                    "source": "synthetic",
                }
            )
        )
    assert recognize_dataset("Synthetic Study", None, kb_root=kb) is None
    m = recognize_dataset("Synthetic Study", "2", kb_root=kb)
    assert m is not None and m.pipeline_id == "p_two"


def test_same_release() -> None:
    assert same_release("3.0", "3") and same_release("S1200", "1200 Subjects Release")
    assert not same_release("3.0", "4.0") and same_release("collection 3165", "3165")


# --- the realignment defaults ---------------------------------------------------------------------


def test_the_three_programs_carry_sourced_defaults() -> None:
    spm = realignment_defaults("spm", kb_root=REAL_KB_ROOT)
    fsl = realignment_defaults("fsl", kb_root=REAL_KB_ROOT)
    afni = realignment_defaults("afni", kb_root=REAL_KB_ROOT)
    assert spm and fsl and afni
    assert spm["version_tokens"] == ["12"]
    assert spm["interpolation_estimate"]["value"] == "2nd degree B-spline"
    assert spm["interpolation_reslice"]["value"] == "4th degree B-spline"
    assert spm["cost_function"]["value"] == "least squares"
    assert fsl["reference_scan"]["value"] == "middle volume"
    assert fsl["cost_function"]["value"].startswith("normalised correlation")
    # 2026-11-11: sourced in FSL's mcflirt code at tag 2111.0 (it was omitted, unsourced, before)
    assert fsl["interpolation_reslice"]["value"] == "trilinear"
    assert "mcflirt.cc lines 740-744" in fsl["interpolation_reslice"]["source"]
    assert afni["reference_scan"]["value"].startswith("first volume")
    for d in (spm, fsl, afni):
        for key in (
            "reference_scan",
            "interpolation_estimate",
            "interpolation_reslice",
            "cost_function",
        ):
            if key in d:
                assert d[key]["value"] and d[key]["source"], key


def test_a_package_without_defaults_or_unknown() -> None:
    assert realignment_defaults("mmps", kb_root=REAL_KB_ROOT) is None
    assert realignment_defaults("freesurfer", kb_root=REAL_KB_ROOT) is None
    with pytest.raises(KbUnknownToolError):
        realignment_defaults("nope", kb_root=REAL_KB_ROOT)


def test_the_new_pipelines_and_the_scan_package() -> None:
    docs = load_pipeline_documents(REAL_KB_ROOT)
    assert [v["version"] for v in docs["abcd_bids"]["versions"]][:1] == ["v0.0.0"]
    assert len(docs["abcd_bids"]["versions"]) == 10
    assert docs["abcd_daic"]["versions"][0]["version_kind"] == "paper_anchored"
    assert (
        recognize("ABCD Data Analysis and Informatics Core pipeline", kb_root=REAL_KB_ROOT)
        == "abcd_daic"
    )
    assert recognize_tool("BioImage Suite", kb_root=REAL_KB_ROOT) == "bioimage_suite"


def test_a_version_is_given_only_when_every_matched_release_states_the_same(tmp_path: Path) -> None:
    kb = tmp_path / "kb"
    (kb / "datasets").mkdir(parents=True)
    for rid, ver in (("syn_1", "v1"), ("syn_2", "v2")):
        (kb / "datasets" / f"{rid}.yaml").write_text(
            yaml.safe_dump(
                {
                    "dataset_id": rid,
                    "display_name": rid,
                    "aliases": [f"SYN {rid}"],
                    "family": "syn",
                    "family_aliases": ["Synthetic Study"],
                    "release": rid[-1],
                    "pipeline": "p_one",
                    "pipeline_version": ver,
                    "source": "synthetic",
                }
            )
        )
    m = recognize_dataset("Synthetic Study", None, kb_root=kb)
    assert m is not None and m.pipeline_id == "p_one" and m.pipeline_version is None
    one = recognize_dataset("Synthetic Study", "1", kb_root=kb)
    assert one is not None and one.pipeline_version == "v1"


@pytest.mark.parametrize(
    ("phrase", "expected"),
    [
        ("MCFLIRT", ("MCFLIRT", "fsl")),
        ("mcflirt", ("MCFLIRT", "fsl")),
        ("FLIRT", ("FLIRT", "fsl")),
        ("AFNI's 3dvolreg", ("3dvolreg", "afni")),  # AFNI's, not the mmps wrapper's
        ("SPM12 Realign", ("Realign", "spm")),
        ("spm_realign", ("Realign", "spm")),
        ("antsMotionCorr", ("antsMotionCorr", "ants")),
        ("Realign each timepoint's image to a reference image", None),  # a verb, no package
        ("realigned and unwarped", None),
        ("SPM12", None),  # a package, not a program
        ("MCFLIRT and FLIRT", None),  # two programs
    ],
)
def test_recognize_program(phrase: str, expected: tuple[str, str] | None) -> None:
    from fmri_defaults_kb import recognize_program

    assert recognize_program(phrase, kb_root=REAL_KB_ROOT) == expected
