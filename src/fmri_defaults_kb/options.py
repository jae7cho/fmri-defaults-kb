"""Every user-settable option of a pipeline at each listed version, and the values its code fixes
(2026-11-11). Read from kb/pipeline_options/<pipeline_id>.yaml, which
scripts/extract_pipeline_options.py generates from the pipeline's parser or default
configuration at each tag.

The use: from a paper's publication date, the versions released by then (``resolve_version``)
and what each would have run (``options_at_date``)."""

from __future__ import annotations

import threading
from datetime import date
from pathlib import Path
from typing import Any

import yaml

from fmri_defaults_kb.errors import KbUnknownPipelineError, KbUnknownVersionError
from fmri_defaults_kb.io import find_kb_root
from fmri_defaults_kb.registry import _get_doc, _ordered_versions, resolve_version

_cache: dict[Path, dict[str, dict[str, Any]]] = {}
_lock = threading.Lock()


def load_option_documents(kb_root: Path | str | None = None) -> dict[str, dict[str, Any]]:
    """Every kb/pipeline_options/*.yaml as ``{pipeline_id: document}`` (cached per root)."""
    root = find_kb_root(kb_root).resolve()
    with _lock:
        if root not in _cache:
            docs: dict[str, dict[str, Any]] = {}
            for f in sorted((root / "pipeline_options").glob("*.yaml")):
                doc = yaml.safe_load(f.read_text(encoding="utf-8"))
                docs[str(doc["pipeline_id"])] = doc
            _cache[root] = docs
        return _cache[root]


def _versions(pipeline_id: str, kb_root: Path | str | None) -> list[str]:
    return [str(v["version"]) for v in _ordered_versions(_get_doc(pipeline_id, kb_root))]


def _covers(rng: dict[str, Any], version: str, ordered: list[str]) -> bool:
    i = ordered.index(version)
    return ordered.index(str(rng["from_version"])) <= i <= ordered.index(str(rng["to_version"]))


def _doc(
    pipeline_id: str, version: str, kb_root: Path | str | None
) -> tuple[dict[str, Any], list[str]]:
    docs = load_option_documents(kb_root)
    if pipeline_id not in docs:
        raise KbUnknownPipelineError(f"no option inventory for {pipeline_id}")
    ordered = _versions(pipeline_id, kb_root)
    if version not in ordered:
        raise KbUnknownVersionError(f"{pipeline_id} has no listed version {version!r}")
    return docs[pipeline_id], ordered


def pipeline_options(
    pipeline_id: str, version: str, *, kb_root: Path | str | None = None
) -> dict[str, dict[str, Any]]:
    """``{option id: {default, choices?, group?, help?, source, ...}}`` for every option the
    pipeline offers at the listed ``version``. KbUnknownPipelineError when the KB has no option
    inventory for the pipeline; KbUnknownVersionError for a version it does not list."""
    doc, ordered = _doc(pipeline_id, version, kb_root)
    src: dict[str, Any] = next(
        (s for s in doc.get("sources") or [] if str(s["version"]) == version), {}
    )
    # a version whose configuration file is a shipped example, not a loaded default
    caveat = (
        {"config_role": "example", "config_note": src.get("note")}
        if src.get("role") == "example"
        else {}
    )
    out: dict[str, dict[str, Any]] = {}
    for opt in doc.get("options") or []:
        rng = next((r for r in opt["ranges"] if _covers(r, version, ordered)), None)
        if rng is None:
            continue
        out[str(opt["id"])] = {
            **{k: opt[k] for k in ("flags", "group", "type", "help") if k in opt},
            **{k: v for k, v in rng.items() if k not in ("from_version", "to_version")},
            **caveat,
        }
    return out


def step_parameters(
    pipeline_id: str, version: str, *, kb_root: Path | str | None = None
) -> list[dict[str, Any]]:
    """The values the pipeline's code fixes at ``version`` (curated): ``[{step, parameter,
    value, source, override_flag | config_key}]``."""
    doc, ordered = _doc(pipeline_id, version, kb_root)
    out = []
    for p in doc.get("step_parameters") or []:
        rng = next((r for r in p["ranges"] if _covers(r, version, ordered)), None)
        if rng is not None:
            out.append(
                {
                    "step": p["step"],
                    "parameter": p["parameter"],
                    **{k: v for k, v in rng.items() if k not in ("from_version", "to_version")},
                }
            )
    return out


def options_at_date(
    pipeline_id: str, paper_date: date, *, kb_root: Path | str | None = None
) -> dict[str, Any]:
    """What the pipeline would have run for a paper published on ``paper_date``: the version
    ``resolve_version`` picks (the latest released by then) and its alternatives (earlier
    releases, for adoption lag), each with its options and fixed step parameters."""
    res = resolve_version(pipeline_id, paper_date, kb_root=kb_root)
    names = [res.resolved_version] + [c.version for c in res.alternative_candidates]
    return {
        "pipeline": pipeline_id,
        "paper_date": paper_date.isoformat(),
        "basis": res.basis_type,
        "version_certain": res.version_certain,
        "candidates": [
            {
                "version": v,
                "chosen": v == res.resolved_version,
                "options": pipeline_options(pipeline_id, v, kb_root=kb_root),
                "step_parameters": step_parameters(pipeline_id, v, kb_root=kb_root),
            }
            for v in names
        ],
    }
