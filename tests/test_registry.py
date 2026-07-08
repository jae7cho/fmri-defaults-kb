"""Tests for fmri_defaults_kb.registry."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from fmri_defaults_kb import (
    KB_BASIS_LITERALS,
    ConditionalParam,
    KbAmbiguousError,
    NotApplicable,
    get_param_defaults,
    recognize,
    resolve_version,
)
from fmri_defaults_kb.errors import KbUnknownPipelineError
from fmri_defaults_kb.io import clear_cache

FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "valid"
REAL_KB_ROOT = Path(__file__).parent.parent / "kb"


@pytest.fixture(autouse=True)
def _isolated_cache():
    clear_cache()
    yield
    clear_cache()


# --- recognize -------------------------------------------------------------


def test_recognize_resolves_pipeline_id_directly():
    assert recognize("test_singleton", kb_root=FIXTURE_ROOT) == "test_singleton"


def test_recognize_resolves_display_name():
    assert recognize("Test Singleton Pipeline", kb_root=FIXTURE_ROOT) == "test_singleton"


def test_recognize_resolves_alias_case_insensitively():
    assert recognize("tsp", kb_root=FIXTURE_ROOT) == "test_singleton"
    assert recognize("  TSP  ", kb_root=FIXTURE_ROOT) == "test_singleton"


def test_recognize_unknown_returns_none():
    assert recognize("nonexistent pipeline", kb_root=FIXTURE_ROOT) is None


def test_recognize_empty_returns_none():
    assert recognize("", kb_root=FIXTURE_ROOT) is None
    assert recognize("   ", kb_root=FIXTURE_ROOT) is None


# --- recognize: Full Name (ACRONYM) convention -----------------------------


def test_recognize_full_name_acronym_resolves():
    # the fix: "Connectome Computation System (CCS)" (first-use convention) -> ccs.
    assert recognize("Connectome Computation System (CCS)", kb_root=REAL_KB_ROOT) == "ccs"
    # unchanged: the two plain forms still resolve.
    assert recognize("CCS", kb_root=REAL_KB_ROOT) == "ccs"
    assert recognize("Connectome Computation System", kb_root=REAL_KB_ROOT) == "ccs"


def test_recognize_paren_version_uses_pre_paren_name():
    # "fMRIPrep (v20.2.0)": pre-paren matches fmriprep; the version parenthetical matches nothing.
    assert recognize("fMRIPrep (v20.2.0)", kb_root=REAL_KB_ROOT) == "fmriprep"


def test_recognize_unknown_full_name_acronym_is_none():
    assert recognize("Totally Unknown (XYZ)", kb_root=REAL_KB_ROOT) is None


def _write_min_pipeline(pipelines_dir: Path, pid: str, aliases: list[str]) -> None:
    (pipelines_dir / f"{pid}.yaml").write_text(
        f"pipeline_id: {pid}\naliases: {aliases}\nversions: []\n"
    )


def test_recognize_ambiguity_guard_returns_none(tmp_path: Path):
    # Full name and acronym resolving to DIFFERENT pipelines -> None (never guess).
    pdir = tmp_path / "pipelines"
    pdir.mkdir()
    _write_min_pipeline(pdir, "p1", ["Foo"])
    _write_min_pipeline(pdir, "p2", ["BAR"])
    assert recognize("Foo (BAR)", kb_root=tmp_path) is None  # p1 vs p2 -> ambiguous
    # controls: unambiguous forms still resolve
    assert recognize("Foo", kb_root=tmp_path) == "p1"
    assert recognize("Foo (P1)", kb_root=tmp_path) == "p1"  # both variants -> p1


# --- resolve_version: version_default arm ----------------------------------


def test_resolve_version_singleton_returns_version_default():
    res = resolve_version("test_singleton", paper_date=None, kb_root=FIXTURE_ROOT)
    assert res.resolved_version == "1.0.0"
    assert res.basis_type == "version_default"
    assert res.version_certain is True
    assert res.alternative_candidates == []
    assert 0 < res.proposed_confidence <= 0.95


def test_resolve_version_singleton_ignores_paper_date():
    res = resolve_version("test_singleton", paper_date=date(1999, 1, 1), kb_root=FIXTURE_ROOT)
    assert res.basis_type == "version_default"


# --- resolve_version: date_inferred_version arm ----------------------------


def test_resolve_version_multi_picks_latest_at_or_before_paper_date():
    res = resolve_version("test_multi_version", paper_date=date(2022, 1, 1), kb_root=FIXTURE_ROOT)
    assert res.resolved_version == "2.0.0"
    assert res.basis_type == "date_inferred_version"
    assert res.version_certain is False
    # Adjacent-earlier candidate is v1.0.0
    versions = [c.version for c in res.alternative_candidates]
    assert versions == ["1.0.0"]


def test_resolve_version_multi_returns_latest_eligible_with_two_earlier():
    res = resolve_version("test_multi_version", paper_date=date(2024, 1, 1), kb_root=FIXTURE_ROOT)
    assert res.resolved_version == "3.0.0"
    assert res.basis_type == "date_inferred_version"
    # Adjacent-earlier candidates capped at the two most recent priors
    versions = [c.version for c in res.alternative_candidates]
    assert versions == ["1.0.0", "2.0.0"]


def test_resolve_version_multi_without_date_raises_ambiguous():
    with pytest.raises(KbAmbiguousError):
        resolve_version("test_multi_version", paper_date=None, kb_root=FIXTURE_ROOT)


def test_resolve_version_no_eligible_release_raises_ambiguous():
    with pytest.raises(KbAmbiguousError):
        resolve_version(
            "test_multi_version",
            paper_date=date(2000, 1, 1),
            kb_root=FIXTURE_ROOT,
        )


def test_resolve_version_unknown_pipeline_raises():
    with pytest.raises(KbUnknownPipelineError):
        resolve_version("does_not_exist", paper_date=None, kb_root=FIXTURE_ROOT)


# --- get_param_defaults ----------------------------------------------------


def test_get_param_defaults_returns_only_requested_documented_fields():
    out = get_param_defaults(
        "test_singleton",
        "1.0.0",
        ["spatial_normalization.target_space", "not_in_yaml.field"],
        kb_root=FIXTURE_ROOT,
    )
    assert set(out) == {"spatial_normalization.target_space"}
    assert out["spatial_normalization.target_space"].value == "MNI152NLin6Asym"
    assert out["spatial_normalization.target_space"].basis_type == "version_default"


def test_get_param_defaults_decodes_not_applicable_sentinel():
    out = get_param_defaults(
        "test_singleton",
        "1.0.0",
        ["temporal_filtering.effective_band_hz"],
        kb_root=FIXTURE_ROOT,
    )
    assert "temporal_filtering.effective_band_hz" in out
    result = out["temporal_filtering.effective_band_hz"]
    assert result.value is NotApplicable
    # Never-null guarantee: the value is the singleton, not None / missing.
    assert result.value is not None


def test_get_param_defaults_omits_needs_verification_sentinel():
    out = get_param_defaults(
        "test_singleton",
        "1.0.0",
        ["intensity_normalization.value"],
        kb_root=FIXTURE_ROOT,
    )
    # needs_verification is stored in the YAML but get_param_defaults omits it
    # so the Configurator never fires an inference on an unverified value.
    assert out == {}


def test_get_param_defaults_decodes_conditional_unresolved():
    # A conditional_default decodes to ParamResult(basis_type="derived",
    # value=ConditionalParam) WITHOUT evaluating the rules (that is the paper-aware
    # Configurator step). Entry-level confidence/source are absent in the fixture.
    out = get_param_defaults(
        "test_singleton",
        "1.0.0",
        ["surface_projection.surface_registration"],
        kb_root=FIXTURE_ROOT,
    )
    assert "surface_projection.surface_registration" in out
    result = out["surface_projection.surface_registration"]
    assert result.basis_type == "derived"
    assert isinstance(result.value, ConditionalParam)
    cond = result.value
    assert cond.conditional_on == "surface_projection.target_surface"
    assert len(cond.rules) == 2
    # rule 0: single-string `when` normalized to a 1-tuple; carries per-rule conf/source
    r0 = cond.rules[0]
    assert r0.when == ("fsLR_32k",)
    assert r0.value == "msm_sulc"
    assert r0.proposed_confidence == 0.70
    assert r0.source == "fixture: code-verified path"
    # rule 1: list `when` -> tuple, the lineage-inferred branch at lower confidence
    r1 = cond.rules[1]
    assert r1.when == ("fsaverage", "fsaverage5", "fsaverage6", "fsnative")
    assert r1.value == "freesurfer_recon"
    assert r1.proposed_confidence == 0.55


# --- two-version keying proof (the load-bearing test) ----------------------


def test_two_version_keying_proof_param_value_differs_across_versions():
    """Same field path, same pipeline_id, different versions ⇒ different values.

    If this test ever passes by returning the same value for both versions,
    the (pipeline, version) keying has collapsed and the registry is broken.
    """
    v1 = get_param_defaults(
        "test_multi_version",
        "1.0.0",
        ["surface_projection.surface_registration"],
        kb_root=FIXTURE_ROOT,
    )
    v2 = get_param_defaults(
        "test_multi_version",
        "2.0.0",
        ["surface_projection.surface_registration"],
        kb_root=FIXTURE_ROOT,
    )
    assert v1["surface_projection.surface_registration"].value == "folding_based"
    assert v2["surface_projection.surface_registration"].value == "msm_all"
    assert (
        v1["surface_projection.surface_registration"].value
        != v2["surface_projection.surface_registration"].value
    )


def test_hcp_keying_proof_v340_vs_v413_surface_registration():
    """Real-HCP keying proof at the v4.0.1→v4.1.3 registration-default boundary.

    PostFreeSurferPipeline.sh defaults `--regname` to `FS` at v3.4.0 (and
    through v4.0.1) and switches to `MSMSulc` at v4.1.3. The KB pins the
    boundary by recording v3.4.0 and v4.1.3 — the difference proves
    (pipeline, version) keying carries real semantics for HCP minimal.
    """
    v340 = get_param_defaults(
        "hcp_minimal",
        "v3.4.0",
        ["surface_projection.surface_registration"],
        kb_root=REAL_KB_ROOT,
    )
    v413 = get_param_defaults(
        "hcp_minimal",
        "v4.1.3",
        ["surface_projection.surface_registration"],
        kb_root=REAL_KB_ROOT,
    )
    assert v340["surface_projection.surface_registration"].value == "freesurfer_recon"
    assert v413["surface_projection.surface_registration"].value == "msm_sulc"
    assert (
        v340["surface_projection.surface_registration"].value
        != v413["surface_projection.surface_registration"].value
    )


def _fmriprep_cond(version: str) -> ConditionalParam:
    out = get_param_defaults(
        "fmriprep",
        version,
        ["surface_projection.surface_registration"],
        kb_root=REAL_KB_ROOT,
    )
    result = out["surface_projection.surface_registration"]
    assert result.basis_type == "derived"
    assert isinstance(result.value, ConditionalParam)
    return result.value


def _rule_value_for(cond: ConditionalParam, target_surface: str) -> str:
    matches = [r.value for r in cond.rules if target_surface in r.when]
    assert len(matches) == 1, f"{target_surface} not matched by exactly one rule"
    return str(matches[0])


def test_fmriprep_surface_registration_conditional_flips_at_23_2_0():
    """First production use of the B1 target_surface-conditional, on the real KB.

    fMRIPrep aligns FreeSurfer surface targets (native/fsaverage*) via recon-all at
    ALL versions, but fsLR grayordinate alignment switches from FreeSurfer folding-based
    registration to MSM-Sulc at 23.2.0 (CHANGES.rst 23.2.0, 2024-01-10; PR #3085). The
    default is DERIVED from the paper's extracted target_surface, so it is one conditional
    whose fsLR branch is version-keyed while its fsaverage branch is not.
    """
    pre, post = _fmriprep_cond("23.1.0"), _fmriprep_cond("23.2.0")
    assert pre.conditional_on == "surface_projection.target_surface"

    # fsaverage-family + native -> freesurfer_recon on BOTH sides of the boundary
    for cond in (pre, post):
        assert _rule_value_for(cond, "fsaverage") == "freesurfer_recon"
        assert _rule_value_for(cond, "native") == "freesurfer_recon"

    # fsLR grayordinate targets flip freesurfer_recon -> msm_sulc at 23.2.0
    assert _rule_value_for(pre, "fsLR_32k") == "freesurfer_recon"
    assert _rule_value_for(post, "fsLR_32k") == "msm_sulc"
    assert _rule_value_for(post, "fsLR_164k") == "msm_sulc"

    # earliest and latest builds agree with their side of the boundary
    assert _rule_value_for(_fmriprep_cond("1.0.0"), "fsLR_32k") == "freesurfer_recon"
    assert _rule_value_for(_fmriprep_cond("25.2.0"), "fsLR_32k") == "msm_sulc"

    # every rule carries the required per-rule confidence + source, capped at the 0.70
    # DerivedBasis ceiling (schema requires them; _build_conditional reads them directly)
    for r in post.rules:
        assert 0.0 < r.proposed_confidence <= 0.70
        assert r.source


def test_hcp_intensity_normalization_concrete_at_both_versions():
    """Verified intensity-normalization values fire as version_default fills.

    Both v3.4.0 and v4.1.3 use FSL `-ing 10000` (grand-mean / mean-based to
    10000) per the tagged IntensityNormalization.sh. Previously these fields
    were `needs_verification` (omitted by get_param_defaults); they now
    return concrete values and the convention is `fsl_grand_mean_10000` —
    distinct from the per-volume `fsl_median_10000` literal.
    """
    for version in ("v3.4.0", "v4.1.3"):
        result = get_param_defaults(
            "hcp_minimal",
            version,
            ["intensity_normalization.convention", "intensity_normalization.value"],
            kb_root=REAL_KB_ROOT,
        )
        assert result["intensity_normalization.convention"].value == "fsl_grand_mean_10000"
        assert result["intensity_normalization.value"].value == 10000


# --- CCS: paper-anchored pipeline with stable (un-keyed) defaults -----------

# Master commit pinned in kb/pipelines/ccs.yaml (zuoxinian/CCS has zero tags).
CCS_COMMIT = "2e413113d3a981e3201cf81f5189c83e35483c60"
CCS_FILLED_FIELDS = [
    "spatial_normalization.target_space",
    "spatial_normalization.resolution_mm",
    "surface_projection.surface_registration",
    "intensity_normalization.convention",
    "intensity_normalization.value",
]
CCS_OMITTED_FIELDS = [
    "surface_projection.target_surface",
    "temporal_filtering.effective_band_hz",
]


def test_ccs_yaml_validates_against_pipeline_registry_schema():
    """Test 1 — kb/pipelines/ccs.yaml validates against the registry schema,
    including the additive optional ``version_kind`` (enum tag/commit/
    paper_anchored). Mirrors what scripts/validate_kb.py asserts in CI."""
    import json

    import yaml
    from jsonschema import Draft202012Validator, FormatChecker

    schema_path = Path(__file__).parent.parent / "schemas" / "pipeline_registry.schema.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    doc = yaml.safe_load((REAL_KB_ROOT / "pipelines" / "ccs.yaml").read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    errors = [
        "/".join(str(p) for p in e.absolute_path) + ": " + e.message
        for e in validator.iter_errors(doc)
    ]
    assert not errors, "ccs.yaml ⊄ schema:\n  " + "\n  ".join(errors)
    # version_kind is actually carried (guards against a schema that silently
    # drops the field via additionalProperties).
    kinds = {v["version"]: v.get("version_kind") for v in doc["versions"]}
    assert kinds["2015"] == "paper_anchored"
    assert kinds[CCS_COMMIT] == "commit"


def test_ccs_cross_pipeline_keying_differentiates_on_resolution_mm():
    """Test 2 — cross-pipeline keying proof.

    Under spec-faithful encoding CCS uses the same FSL MNI152 6th-gen template
    (``MNI152NLin6Asym``) and FreeSurfer folding-based registration
    (``freesurfer_recon``) as HCP minimal v3.4.0, so those fields are
    intentionally SHARED. The field that genuinely differs by ``pipeline_id``
    is ``resolution_mm`` (CCS 3 mm vs HCP 2 mm) — that is the load-bearing
    cross-pipeline distinction, proving the registry keys by pipeline_id and
    not merely by version string.
    """
    hcp = get_param_defaults(
        "hcp_minimal",
        "v3.4.0",
        ["spatial_normalization.resolution_mm", *CCS_FILLED_FIELDS],
        kb_root=REAL_KB_ROOT,
    )
    ccs = get_param_defaults("ccs", "2015", CCS_FILLED_FIELDS, kb_root=REAL_KB_ROOT)

    # The genuine cross-pipeline differentiator:
    assert hcp["spatial_normalization.resolution_mm"].value == 2
    assert ccs["spatial_normalization.resolution_mm"].value == 3
    assert (
        ccs["spatial_normalization.resolution_mm"].value
        != hcp["spatial_normalization.resolution_mm"].value
    )

    # Honestly assert the intentionally-shared fields are shared (so a future
    # edit that accidentally diverges them trips here and gets re-justified).
    for shared in (
        "spatial_normalization.target_space",
        "surface_projection.surface_registration",
        "intensity_normalization.convention",
    ):
        assert ccs[shared].value == hcp[shared].value


def test_ccs_within_pipeline_defaults_identical_across_both_versions():
    """Test 3 — within-pipeline keying is intentionally null for CCS.

    The 2015 paper-anchored entry and the 2021 commit checkpoint return
    IDENTICAL values for all five filled fields. This is the stable-defaults
    case (contrast HCP minimal's FS→MSMSulc transition, which keys
    surface_registration across versions). Xing 2022 reports no change to any
    of these defaults, so the commit entry mirrors 2015 exactly.
    """
    v2015 = get_param_defaults("ccs", "2015", CCS_FILLED_FIELDS, kb_root=REAL_KB_ROOT)
    vcommit = get_param_defaults("ccs", CCS_COMMIT, CCS_FILLED_FIELDS, kb_root=REAL_KB_ROOT)
    assert set(v2015) == set(vcommit) == set(CCS_FILLED_FIELDS)
    for field_path in CCS_FILLED_FIELDS:
        assert v2015[field_path].value == vcommit[field_path].value, field_path


def test_ccs_target_surface_and_effective_band_hz_absent_at_both_versions():
    """Test 4 — deliberate omission of target_surface + effective_band_hz.

    Xu 2015 documents both as user-configurable (no single CCS default), so
    ccs.yaml omits them entirely. get_param_defaults must therefore return NO
    entry for either field at either version — distinct from HCP minimal,
    which fills target_surface (fsLR_32k) and marks effective_band_hz with the
    not_applicable sentinel. Absence here means "CCS pins no default", so the
    Configurator fires nothing and leaves the fields to extraction.
    """
    for version in ("2015", CCS_COMMIT):
        out = get_param_defaults(
            "ccs",
            version,
            CCS_OMITTED_FIELDS,
            kb_root=REAL_KB_ROOT,
        )
        assert out == {}, (
            f"{version}: expected no defaults for {CCS_OMITTED_FIELDS}, got {set(out)}"
        )


def test_ccs_two_versions_use_date_inferred_arm_not_version_default():
    """CCS has two version records and no default_version, so resolve_version
    walks the date_inferred arm (version_certain=False) — the precondition for
    the option-(a) gate that the agent-side CCS test exercises."""
    res = resolve_version("ccs", date(2021, 6, 1), kb_root=REAL_KB_ROOT)
    assert res.resolved_version == "2015"
    assert res.basis_type == "date_inferred_version"
    assert res.version_certain is False


# --- contract surface -------------------------------------------------------


def test_kb_basis_literals_contains_expected_strings():
    # "derived" added for conditional (sibling-field-keyed) param defaults -> DerivedBasis.
    assert KB_BASIS_LITERALS == frozenset({"version_default", "date_inferred_version", "derived"})


def test_kb_basis_literals_is_immutable():
    with pytest.raises((AttributeError, TypeError)):
        KB_BASIS_LITERALS.add("rogue_basis")


# --- coverage stub ---------------------------------------------------------


def test_coverage_stub_reports_per_version_field_count(capsys):
    """Smoke test for a documentation-coverage signal.

    Prints per-(pipeline, version) field-count so curators have a running
    indicator of how much intrinsic-parameter coverage exists. Not a hard
    threshold; just visibility.
    """
    from fmri_defaults_kb.io import load_pipeline_documents

    docs = load_pipeline_documents(kb_root=FIXTURE_ROOT)
    lines = []
    for pid, doc in sorted(docs.items()):
        for v in doc["versions"]:
            count = len(v.get("param_defaults") or {})
            lines.append(f"{pid}@{v['version']}: {count} param_defaults")
    assert lines  # at least one (pipeline, version) pair documented
    print("\n".join(lines))
