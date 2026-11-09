"""``kb/datasets``: public data releases whose preprocessing is a named KB pipeline (2026-11-09).

A dataset phrase resolves to its pipeline with provenance ``"via data release"``:

* :func:`recognize_dataset` takes a dataset name and, optionally, the release as written. The name
  is matched whole (case- and whitespace-insensitive, ``Full Name (ACRONYM)`` variants as in
  :func:`registry.recognize`) against each release's own aliases first, then against its study's
  family aliases, narrowed by the release. A release that names no listed release of the study
  resolves to nothing; a study name without a release resolves only when every listed release of
  it maps to the same pipeline. The pipeline version is given only when every matched release
  states the same one.
* :func:`registry.recognize` falls back to the release-specific aliases only, never to a bare study
  name, so ``recognize("HCP")`` stays unresolved.
"""

from __future__ import annotations

import re
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from fmri_defaults_kb.io import find_kb_root

VIA_DATA_RELEASE = "via data release"

_cache: dict[Path, dict[str, dict[str, Any]]] = {}
_lock = threading.Lock()


@dataclass(frozen=True)
class DatasetMatch:
    pipeline_id: str
    pipeline_version: str | None
    dataset_ids: tuple[str, ...]
    source: str
    provenance: str = VIA_DATA_RELEASE


def load_dataset_documents(kb_root: Path | str | None = None) -> dict[str, dict[str, Any]]:
    """Every ``kb/datasets/*.yaml``, ``{dataset_id: document}``; cached per KB root. A KB without the
    folder has no datasets."""
    root = find_kb_root(kb_root).resolve()
    with _lock:
        if root not in _cache:
            docs: dict[str, dict[str, Any]] = {}
            folder = root / "datasets"
            for f in sorted(folder.glob("*.yaml")) if folder.is_dir() else []:
                doc = yaml.safe_load(f.read_text(encoding="utf-8"))
                docs[str(doc["dataset_id"])] = doc
            _cache[root] = docs
        return _cache[root]


def _needles(name: str) -> set[str]:
    from fmri_defaults_kb.registry import _name_variants

    return set(_name_variants(name))


def _norm(s: str) -> str:
    return " ".join(s.lower().split())


def _release_numbers(s: str) -> list[float]:
    return [float(x) for x in re.findall(r"\d+(?:\.\d+)?", s)]


def same_release(listed: str, written: str) -> bool:
    """A written release names a listed one when their first numbers are equal ("3.0" and "3";
    "S1200" and "1200 Subjects"). No number in either: equal after normalisation."""
    a, b = _release_numbers(listed), _release_numbers(written)
    if a and b:
        return a[0] == b[0]
    return _norm(listed) == _norm(written)


def _match(docs: list[dict[str, Any]]) -> DatasetMatch | None:
    if not docs:
        return None
    pipelines = {str(d["pipeline"]) for d in docs}
    if len(pipelines) != 1:
        return None
    versions = {d.get("pipeline_version") for d in docs}
    version = next(iter(versions)) if len(versions) == 1 else None
    return DatasetMatch(
        pipeline_id=pipelines.pop(),
        pipeline_version=version,
        dataset_ids=tuple(sorted(str(d["dataset_id"]) for d in docs)),
        source="; ".join(str(d["source"]) for d in docs),
    )


def release_alias_match(name: str, *, kb_root: Path | str | None = None) -> DatasetMatch | None:
    """A release-specific alias (or the dataset id / display name), taken whole."""
    needles = _needles(name)
    if not needles:
        return None
    docs = [
        d
        for d in load_dataset_documents(kb_root).values()
        if needles
        & {
            _norm(c)
            for c in (d["dataset_id"], d.get("display_name", ""), *d.get("aliases", []))
            if c
        }
    ]
    return _match(docs)


def recognize_dataset(
    name: str, release: str | None = None, *, kb_root: Path | str | None = None
) -> DatasetMatch | None:
    """The pipeline a dataset phrase resolves to, via its data release (module docstring)."""
    direct = release_alias_match(name, kb_root=kb_root)
    if direct is not None:
        return direct
    needles = _needles(name)
    if not needles:
        return None
    family = [
        d
        for d in load_dataset_documents(kb_root).values()
        if needles & {_norm(c) for c in d.get("family_aliases", [])}
    ]
    if release and release.strip():
        return _match([d for d in family if same_release(str(d["release"]), release)])
    return _match(family)
