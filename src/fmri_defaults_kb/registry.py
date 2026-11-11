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
    KbError,
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
class RealignmentDefault:
    """The realignment program a pipeline runs at a version (2026-10-28), from the document's
    ``realignment_tool.ranges``. ``stable_across_range`` is the range's own mark."""

    pipeline_id: str
    version: str
    program: str
    package: str
    stable_across_range: bool
    source: str
    notes: str | None
    # 2026-11-09: whether the pipeline lets the user choose the program at this version (then
    # ``program`` is its default), the programs it offers, and the source line saying so
    configurable: bool = False
    options: tuple[str, ...] = ()
    choice_source: str | None = None
    # 2026-11-11: how the program attribution is verified (script_at_tag | manual | paper |
    # unverified), the range's own field
    verification: str = "unverified"


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
    if len(matched) == 1:
        return next(iter(matched))
    if matched:
        return None
    # 2026-11-09: a release-specific dataset alias ("HCP S1200") resolves to the release's
    # pipeline (kb/datasets); a bare study name does not. recognize_with_provenance says which.
    from fmri_defaults_kb.datasets import release_alias_match

    via = release_alias_match(name, kb_root=kb_root)
    return via.pipeline_id if via is not None else None


def recognize_with_provenance(
    name: str, *, kb_root: Path | str | None = None
) -> tuple[str, str] | None:
    """``(pipeline_id, provenance)``: ``"pipeline name"`` when the name is the pipeline's, ``"via data
    release"`` when it is a release-specific dataset alias (kb/datasets); None otherwise."""
    from fmri_defaults_kb.datasets import VIA_DATA_RELEASE, release_alias_match

    found = recognize(name, kb_root=kb_root)
    if found is None:
        return None
    via = release_alias_match(name, kb_root=kb_root)
    direct = via is None or found != via.pipeline_id or _is_pipeline_name(name, found, kb_root)
    return (found, "pipeline name" if direct else VIA_DATA_RELEASE)


def _is_pipeline_name(name: str, pipeline_id: str, kb_root: Path | str | None) -> bool:
    doc = load_pipeline_documents(kb_root).get(pipeline_id) or {}
    candidates = {
        _normalize(c)
        for c in (pipeline_id, doc.get("display_name", ""), *doc.get("aliases", []))
        if c
    }
    return bool(set(_name_variants(name)) & candidates)


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


# --- realignment tool (2026-10-28) ------------------------------------------


def _ordered_versions(doc: dict[str, Any]) -> list[dict[str, Any]]:
    return sorted(doc["versions"], key=lambda v: (v["release_date"], v["version"]))


def get_realignment_tool(
    pipeline_id: str, version: str, *, kb_root: Path | str | None = None
) -> RealignmentDefault | None:
    """The realignment program ``pipeline_id`` runs at ``version``, or ``None`` when the
    document records none for that version. A range covers the listed versions whose
    release order lies between ``from_version`` and ``to_version`` (both inclusive; either
    may be absent)."""
    doc = _get_doc(pipeline_id, kb_root)
    _find_version(doc, version)  # KbUnknownVersionError for an unlisted version
    block = doc.get("realignment_tool")
    if not block:
        return None
    ordered = [v["version"] for v in _ordered_versions(doc)]
    idx = ordered.index(version)
    for rng in block["ranges"]:
        lo = ordered.index(rng["from_version"]) if rng.get("from_version") else 0
        hi = ordered.index(rng["to_version"]) if rng.get("to_version") else len(ordered) - 1
        if lo <= idx <= hi:
            return RealignmentDefault(
                pipeline_id=pipeline_id,
                version=version,
                program=str(rng["program"]),
                package=str(rng["package"]),
                stable_across_range=bool(rng["stable_across_range"]),
                source=str(rng["source"]),
                notes=(str(rng["notes"]) if rng.get("notes") else None),
                configurable=bool(rng.get("configurable", False)),
                options=tuple(str(o) for o in rng.get("options") or ()),
                choice_source=(str(rng["choice_source"]) if rng.get("choice_source") else None),
                verification=str(rng.get("verification") or "unverified"),
            )
    return None


def _vkey(version: str) -> tuple[int, ...]:
    import re as _re

    return tuple(int(x) for x in _re.findall(r"\d+", version))


def realignment_tool_at(
    pipeline_id: str, version: str, *, kb_root: Path | str | None = None
) -> RealignmentDefault | None:
    """``get_realignment_tool`` for any version string (2026-11-09). A listed version is looked up
    as there; a version the KB does not list (a dataset's "v3.1", a paper's unreleased "0.4.0")
    falls into the range whose bounds contain it by version-number order, where a range without
    ``from_version`` starts before the earliest listed version and one without ``to_version``
    runs past the latest. None when no range contains it or the version has no number."""
    doc = _get_doc(pipeline_id, kb_root)
    listed = {str(v["version"]) for v in doc["versions"]}
    if version in listed:
        return get_realignment_tool(pipeline_id, version, kb_root=kb_root)
    key = _vkey(version)
    block = doc.get("realignment_tool")
    if not key or not block:
        return None
    for rng in block["ranges"]:
        lo = _vkey(str(rng["from_version"])) if rng.get("from_version") else None
        hi = _vkey(str(rng["to_version"])) if rng.get("to_version") else None
        if (lo is None or lo <= key) and (hi is None or key <= hi):
            return RealignmentDefault(
                pipeline_id=pipeline_id,
                version=version,
                program=str(rng["program"]),
                package=str(rng["package"]),
                stable_across_range=bool(rng["stable_across_range"]),
                source=str(rng["source"]),
                notes=(str(rng["notes"]) if rng.get("notes") else None),
                configurable=bool(rng.get("configurable", False)),
                options=tuple(str(o) for o in rng.get("options") or ()),
                choice_source=(str(rng["choice_source"]) if rng.get("choice_source") else None),
                verification=str(rng.get("verification") or "unverified"),
            )
    return None


def realignment_tool_over(
    pipeline_id: str, versions: list[str], *, kb_root: Path | str | None = None
) -> RealignmentDefault | None:
    """The ONE realignment default that holds over every version in ``versions`` -- the
    date-inferred version and its alternative candidates -- when each falls in a range marked
    ``stable_across_range`` and all name the same program; else ``None``. This is the agent's
    F3 condition for a ``date_inferred_version`` fill of ``motion_correction.method``."""
    found = [get_realignment_tool(pipeline_id, v, kb_root=kb_root) for v in versions]
    if not found or any(f is None for f in found):
        return None
    first = found[0]
    assert first is not None
    if any(not f.stable_across_range or f.program != first.program for f in found if f):
        return None
    return first


# --- what a pipeline's realignment step passes to the wrapped tool's job (2026-11-10) -----------


def _job_defaults(tool_id: str, job: str, kb_root: Path | str | None) -> dict[str, Any]:
    """The wrapped tool's defaults for ``job``: the block of the tool entry's ``realignment`` whose
    ``job`` matches (``unwarp_defaults`` for SPM's spm.spatial.realignunwarp, ``defaults`` for FSL's
    mcflirt, ``flirt_defaults`` for FSL's flirt, ...). KbError when the entry records none."""
    from fmri_defaults_kb.tools import load_tool_documents  # tools imports registry

    block = (load_tool_documents(kb_root).get(tool_id) or {}).get("realignment") or {}
    for cand in block.values():
        if isinstance(cand, dict) and cand.get("job") == job:
            return dict(cand)
    raise KbError(f"the {tool_id} tool entry records no defaults for the job {job}")


def _in_range(rng: dict[str, Any], version: str, ordered: list[str]) -> bool:
    idx = ordered.index(version)
    lo = ordered.index(rng["from_version"]) if rng.get("from_version") else 0
    hi = ordered.index(rng["to_version"]) if rng.get("to_version") else len(ordered) - 1
    return lo <= idx <= hi


def realignment_settings(
    pipeline_id: str, version: str | None = None, *, kb_root: Path | str | None = None
) -> dict[str, Any] | None:
    """What ``pipeline_id``'s realignment step passes to the job of the tool it wraps, setting by
    setting, or None when the pipeline document records no ``realignment_settings``.

    The shape of :func:`fmri_defaults_kb.realignment_defaults` (``documented_for``,
    ``version_tokens`` and one ``{value, source}`` per setting), with ``set_by`` and ``option`` on
    each setting:

    - ``set_by="pipeline"``: the step sets the option itself; the source is the pipeline's lines.
    - ``set_by="inherited"``: the step leaves it unset and the job runs with the wrapped tool's
      default; the value is the tool entry's, the source is the pipeline's line plus the tool's.
    - ``set_by="mixed"``: set at some versions, inherited at others, with the same value.

    ``realignment_settings`` is one block or (2026-11-11) a list of blocks, each over a version
    range (``from_version`` / ``to_version``) with its own step, job and wrapped tool, as when a
    pipeline changed programs (HCP: flirt to v3.4.0, mcflirt from v4.1.3). A setting's range gives
    its pipeline-side source either as ``cites`` into the block's ``lines`` (CONN) or as a
    ``source`` text.

    ``version``: a listed version reads that version's ranges. ``None`` or an unlisted version
    reads every listed version. A setting whose value differs across them has value None and a
    ``range`` naming each version span's value. ``documented_for`` and ``version_tokens`` are the
    wrapped tools' (the inherited values are read at those tool versions)."""
    doc = _get_doc(pipeline_id, kb_root)
    raw = doc.get("realignment_settings")
    if not raw:
        return None
    blocks: list[dict[str, Any]] = raw if isinstance(raw, list) else [raw]
    ordered = [str(v["version"]) for v in _ordered_versions(doc)]
    listed = version is not None and version in ordered
    versions = [version] if listed and version is not None else ordered
    scope = (
        f"at {version}"
        if listed
        else f"at every listed version ({ordered[0]} to {ordered[-1]})"
        + (f"; {version} is not a listed version" if version is not None else "")
    )

    def block_at(v: str) -> dict[str, Any]:
        hits = [b for b in blocks if _in_range(b, v, ordered)]
        if len(hits) != 1:
            raise KbError(f"{pipeline_id}: {len(hits)} realignment_settings blocks cover {v}")
        return hits[0]

    defaults_of: dict[int, dict[str, Any]] = {
        id(b): _job_defaults(str(b["wraps"]), str(b["job"]), kb_root) for b in blocks
    }
    used = [block_at(v) for v in versions]
    documented = sorted({str(defaults_of[id(b)].get("documented_for")) for b in used})
    tokens = sorted({str(t) for b in used for t in defaults_of[id(b)].get("version_tokens") or []})
    out: dict[str, Any] = {
        "pipeline": pipeline_id,
        "version": version if listed else None,
        "wraps": used[0]["wraps"] if len({b["wraps"] for b in used}) == 1 else None,
        "job": " / ".join(sorted({str(b["job"]) for b in used})),
        "step": " / ".join(sorted({str(b["step"]) for b in used})),
        "documented_for": "; ".join(documented),
        "version_tokens": tokens,
    }

    def describe(
        block: dict[str, Any], rng: dict[str, Any], v: str, key: str, option: str | None
    ) -> tuple[str, str]:
        fname = str(block.get("file") or "")
        row = {str(r["version"]): r for r in block.get("lines") or []}.get(v, {})
        tool_defaults = defaults_of[id(block)]
        if rng["set"]:
            if rng.get("source"):
                return str(rng["value"]), str(rng["source"])
            cited = ", ".join(str(row[c]) for c in rng["cites"])
            src = f"{fname} at {v}, lines {cited} ({rng['assignment']}, passed as {option})"
            if rng.get("option_line"):
                src += f"; changeable with its option (line {row[rng['option_line']]})"
            return str(rng["value"]), src
        if key not in tool_defaults:
            raise KbError(
                f"{pipeline_id} leaves {key} to {block['wraps']}, which records no default"
            )
        what = f"{option} unset" if option else "the setting to the job"
        if rng.get("source"):
            pipeline_side = str(rng["source"])
        else:
            pipeline_side = (
                f"{fname} at {v}: the {block['step']} job (line {row['job']}) leaves {what}, and "
                f"spm_jobman (line {row['run']}) fills it"
            )
        src = f"{pipeline_side}; the {block['wraps']} default: {tool_defaults[key]['source']}"
        return str(tool_defaults[key]["value"]), src

    keys: list[str] = []
    for b in blocks:
        keys += [k for k in b["settings"] if k not in keys]
    for key in keys:
        per: list[tuple[str, bool, str, str]] = []  # version, set, value, source
        options: set[str | None] = set()
        for v in versions:
            block = block_at(v)
            setting = block["settings"].get(key)
            if setting is None:
                raise KbError(f"{pipeline_id}: the block covering {v} records no {key}")
            option = setting.get("option")
            options.add(option)
            rng = next((r for r in setting["ranges"] if _in_range(r, v, ordered)), None)
            if rng is None:
                raise KbError(f"{pipeline_id}: no range of {key} covers {v}")
            value, src = describe(block, rng, v, key, option)
            per.append((v, bool(rng["set"]), value, src))
        values = {p[2] for p in per}
        sets = {p[1] for p in per}
        set_by = "mixed" if len(sets) > 1 else ("pipeline" if sets == {True} else "inherited")
        item: dict[str, Any] = {
            "option": next(iter(options))
            if len(options) == 1
            else " / ".join(sorted(str(o) for o in options)),
            "set_by": set_by,
        }
        if len(values) > 1:
            spans: list[tuple[str, str, str, str]] = []  # first, last, value, set/inherited
            for v, is_set, value, _ in per:
                tag = "set" if is_set else "inherited"
                if spans and spans[-1][2:] == (value, tag):
                    spans[-1] = (spans[-1][0], v, value, tag)
                else:
                    spans.append((v, v, value, tag))
            item.update(
                value=None,
                range="; ".join(
                    f"{a if a == b else a + ' to ' + b}: {value} ({tag})"
                    for a, b, value, tag in spans
                ),
                source=f"{pipeline_id} realignment_settings {scope}",
            )
        elif set_by == "mixed":
            first_set = next(p for p in per if p[1])
            last_unset = [p for p in per if not p[1]][-1]
            latest_set = [p for p in per if p[1]][-1]
            item.update(
                value=per[0][2],
                source=(
                    f"set from {first_set[0]}: {latest_set[3]}. Before {first_set[0]}, inherited: "
                    f"{last_unset[3]}. The same value either way"
                ),
            )
        else:
            item.update(
                value=per[0][2], source=f"{scope}; {per[-1][3]}" if not listed else per[-1][3]
            )
        out[key] = item
    return out
