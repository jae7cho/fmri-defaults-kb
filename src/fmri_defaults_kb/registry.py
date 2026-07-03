"""Pipeline-registry query interface.

Stdlib-only datatypes. No Pydantic. No agent import.

Functions:
  - recognize(name) -> pipeline_id | None
  - resolve_version(pipeline_id, paper_date) -> VersionResolution
  - get_param_defaults(pipeline_id, version, fields) -> {field_path: ParamResult}
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any, Final, cast

from fmri_defaults_kb.errors import (
    KbAmbiguousError,
    KbUnknownPipelineError,
    KbUnknownVersionError,
)
from fmri_defaults_kb.io import load_pipeline_documents
from fmri_defaults_kb.sentinels import NotApplicable, _NotApplicableSentinel

KB_BASIS_LITERALS: Final[frozenset[str]] = frozenset(
    {"version_default", "date_inferred_version", "derived"}
)

_DEFAULT_CONFIDENCE_VERSION_DEFAULT: Final[float] = 0.95
_DEFAULT_CONFIDENCE_DATE_INFERRED: Final[float] = 0.75


@dataclass(frozen=True)
class VersionCandidate:
    version: str
    release_date: date
    proposed_confidence: float
    source: str


@dataclass(frozen=True)
class VersionResolution:
    resolved_version: str
    basis_type: str  # one of KB_BASIS_LITERALS
    proposed_confidence: float
    source: str
    alternative_candidates: list[VersionCandidate]
    version_certain: bool


@dataclass(frozen=True)
class ConditionalRule:
    """One branch of a conditional default: when the ``conditional_on`` field's
    extracted value is in ``when``, the derived value is ``value`` with the given
    confidence/source. Resolved consumer-side (paper-aware); the KB never evaluates it."""

    when: tuple[str, ...]  # single-string ``when`` is normalized to a 1-tuple
    value: Any
    proposed_confidence: float
    source: str


@dataclass(frozen=True)
class ConditionalParam:
    """A default DERIVED from a sibling extracted field's value (e.g.
    ``surface_registration`` derived from ``target_surface``). Carried unresolved from the
    KB to the Configurator, which selects a rule against the paper's extracted data and
    emits a ``DerivedBasis`` inference (ceiling 0.70). The KB stays paper-agnostic."""

    conditional_on: str  # dotted spec-field path of the sibling extracted field
    rules: tuple[ConditionalRule, ...]


@dataclass(frozen=True)
class ParamResult:
    # ``value`` is a concrete default, the NotApplicable sentinel, or an unresolved
    # ConditionalParam (basis_type == "derived"); scalar/sentinel defaults are
    # "version_default".
    value: Any | _NotApplicableSentinel | ConditionalParam
    basis_type: str  # "version_default" | "derived"
    proposed_confidence: float
    source: str
    alternative_candidates: list[Any] = field(default_factory=list)


def _name_variants(name: str) -> list[str]:
    """Normalized needles to try for a pipeline name.

    The whole normalized name, plus — for a trailing ``Full Name (ACRONYM)`` — the
    pre-parenthesis part and the parenthetical content, so the near-universal
    first-use convention (``Connectome Computation System (CCS)``) resolves. Not
    fuzzy: these are the same entity written three ways, and the caller keeps an
    ambiguity guard.
    """
    variants = [_normalize(name)]
    m = re.match(r"^(.*\S)\s*\(([^()]+)\)\s*$", name)
    if m:
        variants.append(_normalize(m.group(1)))  # pre-parenthesis full name
        variants.append(_normalize(m.group(2)))  # parenthetical (acronym)
    return [v for v in variants if v]


def recognize(name: str, *, kb_root: Path | str | None = None) -> str | None:
    """Resolve a free-text pipeline name to a pipeline_id, or None if unknown.

    Case-insensitive, whitespace-normalized, matched against ``pipeline_id`` /
    ``display_name`` / ``aliases[]``. Also handles the ``Full Name (ACRONYM)``
    first-use convention (see :func:`_name_variants`). Precision-preserving: if the
    name's variants resolve to more than one distinct pipeline, returns ``None``
    (ambiguity guard) rather than guessing.
    """
    needles = set(_name_variants(name))
    if not needles:
        return None
    matched: set[str] = set()
    for pipeline_id, doc in load_pipeline_documents(kb_root).items():
        candidates = {
            _normalize(c)
            for c in (pipeline_id, doc.get("display_name", ""), *doc.get("aliases", []))
            if c
        }
        if needles & candidates:
            matched.add(pipeline_id)
    return next(iter(matched)) if len(matched) == 1 else None


def resolve_version(
    pipeline_id: str,
    paper_date: date | None,
    *,
    kb_root: Path | str | None = None,
) -> VersionResolution:
    """Pick a version for ``pipeline_id`` and report the basis.

    - If the document has a ``default_version`` or exactly one ``versions[]``
      entry: basis ``version_default``, ``version_certain=True``,
      ``alternative_candidates=[]``.
    - Else with ``paper_date``: latest ``versions[]`` entry whose
      ``release_date <= paper_date``. basis ``date_inferred_version``,
      ``version_certain=False``, alternatives = the adjacent-earlier
      release(s) to encode lab-adoption lag.
    - Else: raise ``KbAmbiguousError`` (no default + no date to discriminate).
    """
    doc = _get_doc(pipeline_id, kb_root)
    versions = doc["versions"]

    # version_default arm
    default_version_str = doc.get("default_version")
    if default_version_str is not None:
        chosen = _find_version(doc, default_version_str)
        return VersionResolution(
            resolved_version=chosen["version"],
            basis_type="version_default",
            proposed_confidence=_DEFAULT_CONFIDENCE_VERSION_DEFAULT,
            source=chosen["release_source"],
            alternative_candidates=[],
            version_certain=True,
        )
    if len(versions) == 1:
        only = versions[0]
        return VersionResolution(
            resolved_version=only["version"],
            basis_type="version_default",
            proposed_confidence=_DEFAULT_CONFIDENCE_VERSION_DEFAULT,
            source=only["release_source"],
            alternative_candidates=[],
            version_certain=True,
        )

    # date_inferred_version arm
    if paper_date is None:
        raise KbAmbiguousError(
            f"pipeline {pipeline_id!r} has {len(versions)} versions and no "
            "default_version; resolve_version requires paper_date"
        )

    sorted_versions = sorted(versions, key=lambda v: v["release_date"])
    eligible = [v for v in sorted_versions if v["release_date"] <= paper_date]
    if not eligible:
        raise KbAmbiguousError(
            f"pipeline {pipeline_id!r}: no release on or before {paper_date.isoformat()}; "
            f"earliest is {sorted_versions[0]['release_date'].isoformat()}"
        )

    chosen = eligible[-1]
    earlier = eligible[:-1]
    # Adjacent-earlier candidate(s): the immediately-preceding release(s) to
    # encode lab-adoption lag. Two prior releases keep the list small but
    # meaningful; emit fewer if not available.
    alternatives = [
        VersionCandidate(
            version=v["version"],
            release_date=v["release_date"],
            proposed_confidence=_DEFAULT_CONFIDENCE_DATE_INFERRED,
            source=v["release_source"],
        )
        for v in earlier[-2:]
    ]
    return VersionResolution(
        resolved_version=chosen["version"],
        basis_type="date_inferred_version",
        proposed_confidence=_DEFAULT_CONFIDENCE_DATE_INFERRED,
        source=chosen["release_source"],
        alternative_candidates=alternatives,
        version_certain=False,
    )


def get_param_defaults(
    pipeline_id: str,
    version: str,
    fields: list[str],
    *,
    kb_root: Path | str | None = None,
) -> dict[str, ParamResult]:
    """Return parameter defaults intrinsic to ``(pipeline_id, version)``.

    Only returns ``field_path``s in ``fields`` that have a concrete value or a
    ``not_applicable`` sentinel. Fields stored as ``needs_verification`` are
    omitted from the result; the Configurator therefore does not fire an
    inference on them, and the TODO remains visible only to KB curators.
    """
    doc = _get_doc(pipeline_id, kb_root)
    record = _find_version(doc, version)
    defaults: dict[str, Any] = record.get("param_defaults") or {}
    requested = set(fields)
    out: dict[str, ParamResult] = {}
    for field_path, raw in defaults.items():
        if field_path not in requested:
            continue
        value = _decode_value(raw["value"])
        if value is _NEEDS_VERIFICATION:
            continue
        if isinstance(value, ConditionalParam):
            # Conditional defaults carry confidence/source PER RULE; entry-level fields
            # are optional (schema if/then) and unused downstream. basis -> "derived".
            out[field_path] = ParamResult(
                value=value,
                basis_type="derived",
                proposed_confidence=float(raw.get("proposed_confidence", 0.0)),
                source=str(raw.get("source", "")),
                alternative_candidates=[],
            )
            continue
        out[field_path] = ParamResult(
            value=value,
            basis_type="version_default",
            proposed_confidence=float(raw["proposed_confidence"]),
            source=str(raw["source"]),
            alternative_candidates=[],
        )
    return out


# --- helpers ---------------------------------------------------------------


# Internal marker distinct from NotApplicable; signals "skip this field".
_NEEDS_VERIFICATION: Final = object()


def _build_conditional(raw: dict[str, Any]) -> ConditionalParam:
    """Build an unresolved ``ConditionalParam`` from a ``conditional_default`` mapping.

    Rules are NOT evaluated here (that is the paper-aware Configurator step); this only
    decodes the shape and normalizes each rule's ``when`` (string -> 1-tuple)."""
    rules: list[ConditionalRule] = []
    for r in raw["rules"]:
        when = r["when"]
        when_tuple = (when,) if isinstance(when, str) else tuple(when)
        rules.append(
            ConditionalRule(
                when=when_tuple,
                value=r["value"],
                proposed_confidence=float(r["proposed_confidence"]),
                source=str(r["source"]),
            )
        )
    return ConditionalParam(conditional_on=str(raw["conditional_on"]), rules=tuple(rules))


def _decode_value(raw: Any) -> Any:
    """Translate schema sentinels + the conditional shape into Python markers."""
    if isinstance(raw, dict) and "conditional_on" in raw:
        return _build_conditional(raw)
    if isinstance(raw, dict) and "kind" in raw:
        kind = raw["kind"]
        if kind == "not_applicable":
            return NotApplicable
        if kind == "needs_verification":
            return _NEEDS_VERIFICATION
        raise ValueError(f"unknown value sentinel kind: {kind!r}")
    # YAML lists -> tuples are NOT done here; consumers that need tuples
    # (e.g. effective_band_hz) accept list-shaped values via Pydantic coercion.
    return raw


def _normalize(s: str) -> str:
    return " ".join(s.lower().split())


def _get_doc(pipeline_id: str, kb_root: Path | str | None) -> dict[str, Any]:
    documents = load_pipeline_documents(kb_root)
    if pipeline_id not in documents:
        raise KbUnknownPipelineError(pipeline_id)
    return documents[pipeline_id]


def _find_version(doc: dict[str, Any], version: str) -> dict[str, Any]:
    for v in doc["versions"]:
        if v["version"] == version:
            # doc came from untyped YAML (dict[str, Any]); the version record is
            # itself a mapping. Narrow the Any back to the declared return type.
            return cast(dict[str, Any], v)
    raise KbUnknownVersionError(f"pipeline {doc['pipeline_id']!r} has no version {version!r}")
