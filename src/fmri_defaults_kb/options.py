"""Every user-settable option of a pipeline at each release, and the values its code fixes
(2026-11-11). Read from kb/pipeline_options/<pipeline_id>.yaml, which
scripts/extract_pipeline_options.py generates from the pipeline's parser or default
configuration at every final release tag.

The use: from a paper's publication date, the releases out by then (``options_at_date``) and
what each would have run, step by step (``step_defaults``).

Versions here are the inventory's own timeline (every final release tag, dated by git), not
kb/pipelines' listed versions. The curated fixed values (``step_parameters``) were read at the
listed versions; at a tag between two of their ranges both values are returned, marked
uncertain."""

from __future__ import annotations

import re
import threading
from datetime import date
from pathlib import Path
from typing import Any

import yaml

from fmri_defaults_kb.errors import KbUnknownPipelineError, KbUnknownVersionError
from fmri_defaults_kb.io import find_kb_root

_cache: dict[Path, dict[str, dict[str, Any]]] = {}
_lock = threading.Lock()

#: earlier minor releases offered beside the latest, for labs that had not upgraded
ADOPTION_LAG_MINORS = 2


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


def _vkey(version: str) -> tuple[int, ...]:
    return tuple(int(x) for x in re.findall(r"\d+", version))


def _inventory(pipeline_id: str, kb_root: Path | str | None) -> dict[str, Any]:
    docs = load_option_documents(kb_root)
    if pipeline_id not in docs:
        raise KbUnknownPipelineError(f"no option inventory for {pipeline_id}")
    return docs[pipeline_id]


def release_timeline(
    pipeline_id: str, *, kb_root: Path | str | None = None
) -> list[dict[str, Any]]:
    """``[{version, tag, date, listed}]``: every final release, oldest first."""
    return list(_inventory(pipeline_id, kb_root)["timeline"])


def _doc(
    pipeline_id: str, version: str, kb_root: Path | str | None
) -> tuple[dict[str, Any], list[str]]:
    doc = _inventory(pipeline_id, kb_root)
    ordered = [str(t["version"]) for t in doc["timeline"]]
    if version not in ordered:
        raise KbUnknownVersionError(f"{pipeline_id} has no release {version!r}")
    return doc, ordered


def _covers(rng: dict[str, Any], version: str, ordered: list[str]) -> bool:
    i = ordered.index(version)
    return ordered.index(str(rng["from_version"])) <= i <= ordered.index(str(rng["to_version"]))


def pipeline_options(
    pipeline_id: str, version: str, *, kb_root: Path | str | None = None
) -> dict[str, dict[str, Any]]:
    """``{option id: {default, choices?, group?, help?, source, file, ...}}`` for every option
    the pipeline offers at the release ``version``. The range cites ``line N at <version>`` in
    ``file``. A version whose configuration file is a shipped example, not a loaded default,
    adds ``config_role`` and ``config_note``; a C-PAC option the GUI sets adds ``gui_default``."""
    doc, ordered = _doc(pipeline_id, version, kb_root)
    src: dict[str, Any] = next(
        (s for s in doc.get("sources") or [] if str(s["version"]) == version), {}
    )
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
            **{
                k: opt[k]
                for k in (
                    "flags",
                    "group",
                    "type",
                    "help",
                    "nested_as",
                    "flat_as",
                    "deprecated_in_1_8",
                )
                if k in opt
            },
            **{k: v for k, v in rng.items() if k not in ("from_version", "to_version")},
            # the range cites 'line N at <version>'; the file is the version's, from sources
            "file": src.get("file"),
            **caveat,
        }
    return out


def step_parameters(
    pipeline_id: str, version: str, *, kb_root: Path | str | None = None
) -> list[dict[str, Any]]:
    """The values the pipeline's code fixes at ``version`` (curated, read at the listed
    versions): ``[{step, parameter, value, source, ...}]``. Placed by version number: inside a
    range, its value; between two ranges, both values with ``uncertain: True``; after the last
    range, its value with ``uncertain: True`` (not read at this tag)."""
    doc, _ = _doc(pipeline_id, version, kb_root)
    key = _vkey(version)
    out = []
    for p in doc.get("step_parameters") or []:
        ranges = sorted(p["ranges"], key=lambda r: _vkey(str(r["from_version"])))
        base = {"step": p["step"], "parameter": p["parameter"]}
        hit = next(
            (
                r
                for r in ranges
                if _vkey(str(r["from_version"])) <= key <= _vkey(str(r["to_version"]))
            ),
            None,
        )
        if hit is not None:
            out.append(
                {
                    **base,
                    **{k: v for k, v in hit.items() if k not in ("from_version", "to_version")},
                }
            )
            continue
        before = [r for r in ranges if _vkey(str(r["to_version"])) < key]
        after = [r for r in ranges if _vkey(str(r["from_version"])) > key]
        if before and after:
            a, b = before[-1], after[0]
            out.append(
                {
                    **base,
                    "value": f"{a['value']} (to {a['to_version']}) or {b['value']} (from {b['from_version']})",
                    "source": f"{a['source']} | {b['source']}",
                    "uncertain": True,
                    "note": f"{version} lies between the versions these values were read at",
                }
            )
        elif before:
            a = before[-1]
            out.append(
                {
                    **base,
                    "value": a["value"],
                    "source": a["source"],
                    "uncertain": True,
                    "note": f"read up to {a['to_version']}; not read at {version}",
                }
            )
    return out


def step_defaults(
    pipeline_id: str, version: str, *, kb_root: Path | str | None = None
) -> dict[str, dict[str, Any]]:
    """Step by step, what the release ``version`` offers and fixes: ``{step: {"options": {id:
    option}, "fixed": [step parameter]}}``, the options from the inventory's curated
    ``step_options`` that exist at ``version``."""
    doc, _ = _doc(pipeline_id, version, kb_root)
    opts = pipeline_options(pipeline_id, version, kb_root=kb_root)
    fixed = step_parameters(pipeline_id, version, kb_root=kb_root)
    steps = list((doc.get("step_options") or {}).keys())
    steps += [p["step"] for p in fixed if p["step"] not in steps]
    out: dict[str, dict[str, Any]] = {}
    for step in steps:
        ids = (doc.get("step_options") or {}).get(step) or []
        out[step] = {
            "options": {i: opts[i] for i in ids if i in opts},
            "fixed": [p for p in fixed if p["step"] == step],
        }
    return out


def _minor(version: str) -> tuple[int, ...]:
    return _vkey(version)[:2]


def options_at_date(
    pipeline_id: str, paper_date: date, *, kb_root: Path | str | None = None
) -> dict[str, Any]:
    """What the pipeline would have run for a paper published on ``paper_date``: the latest
    release out by then, and the last release of each of the ``ADOPTION_LAG_MINORS`` minor
    versions before it (labs that had not upgraded), each with its step defaults. None of the
    candidates is certain: the paper does not state its version."""
    timeline = release_timeline(pipeline_id, kb_root=kb_root)
    out_by_then = [t for t in timeline if date.fromisoformat(str(t["date"])) <= paper_date]
    if not out_by_then:
        return {"pipeline": pipeline_id, "paper_date": paper_date.isoformat(), "candidates": []}
    latest = out_by_then[-1]
    earlier: list[dict[str, Any]] = []
    for t in reversed(out_by_then[:-1]):
        minors = {_minor(str(latest["version"]))} | {_minor(str(e["version"])) for e in earlier}
        if _minor(str(t["version"])) not in minors:
            earlier.append(t)
        if len(earlier) == ADOPTION_LAG_MINORS:
            break
    candidates = [latest, *earlier]
    return {
        "pipeline": pipeline_id,
        "paper_date": paper_date.isoformat(),
        "basis": "latest release on or before the date, and the last release of each of "
        f"the {ADOPTION_LAG_MINORS} minor versions before it",
        "candidates": [
            {
                "version": str(t["version"]),
                "released": str(t["date"]),
                "latest": t is latest,
                "options": pipeline_options(pipeline_id, str(t["version"]), kb_root=kb_root),
                "step_defaults": step_defaults(pipeline_id, str(t["version"]), kb_root=kb_root),
            }
            for t in candidates
        ],
    }
