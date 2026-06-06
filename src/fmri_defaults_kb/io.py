"""YAML loader + in-memory index for kb/pipelines/."""

from __future__ import annotations

import os
import threading
from datetime import date
from pathlib import Path
from typing import Any

import yaml


def find_kb_root(kb_root: Path | str | None = None) -> Path:
    """Locate the kb/ data directory.

    Resolution order:
      1. explicit ``kb_root`` argument
      2. ``FMRI_DEFAULTS_KB_PATH`` environment variable
      3. walk up from this file looking for a ``kb/pipelines/`` sibling
         (works for editable / path installs in development).
    """
    if kb_root is not None:
        p = Path(kb_root)
        if not p.is_dir():
            raise FileNotFoundError(f"kb_root does not exist: {p}")
        return p

    env = os.environ.get("FMRI_DEFAULTS_KB_PATH")
    if env:
        p = Path(env)
        if not p.is_dir():
            raise FileNotFoundError(f"FMRI_DEFAULTS_KB_PATH does not exist: {p}")
        return p

    here = Path(__file__).resolve()
    for parent in here.parents:
        candidate = parent / "kb"
        if (candidate / "pipelines").is_dir() or candidate.is_dir():
            return candidate
    raise RuntimeError(
        "Could not locate fmri-defaults-kb data directory. "
        "Set FMRI_DEFAULTS_KB_PATH or pass kb_root explicitly."
    )


def load_pipeline_documents(kb_root: Path | str | None = None) -> dict[str, dict[str, Any]]:
    """Load every kb/pipelines/*.yaml and return ``{pipeline_id: document}``.

    No schema validation here; scripts/validate_kb.py is the gatekeeper.
    Documents are parsed once and cached per kb_root path.
    """
    root = find_kb_root(kb_root)
    return _load_cached(root.resolve())


_cache: dict[Path, dict[str, dict[str, Any]]] = {}
_cache_lock = threading.Lock()


def _load_cached(root: Path) -> dict[str, dict[str, Any]]:
    with _cache_lock:
        cached = _cache.get(root)
        if cached is not None:
            return cached

        pipelines_dir = root / "pipelines"
        documents: dict[str, dict[str, Any]] = {}
        if pipelines_dir.is_dir():
            for yaml_file in sorted(pipelines_dir.glob("*.yaml")):
                with yaml_file.open("r", encoding="utf-8") as f:
                    doc = yaml.safe_load(f)
                if not isinstance(doc, dict):
                    raise ValueError(f"{yaml_file}: top-level YAML must be a mapping")
                pipeline_id = doc.get("pipeline_id")
                if not pipeline_id:
                    raise ValueError(f"{yaml_file}: missing pipeline_id")
                if pipeline_id in documents:
                    raise ValueError(f"{yaml_file}: duplicate pipeline_id {pipeline_id!r}")
                _coerce_dates_in_place(doc)
                documents[pipeline_id] = doc

        _cache[root] = documents
        return documents


def clear_cache() -> None:
    with _cache_lock:
        _cache.clear()


def _coerce_dates_in_place(doc: dict[str, Any]) -> None:
    """PyYAML already parses ``YYYY-MM-DD`` as datetime.date; this is a no-op guard.

    Kept as a hook so future loaders that come through JSON (date as string)
    can be normalized here.
    """
    for version_record in doc.get("versions", []):
        rd = version_record.get("release_date")
        if isinstance(rd, str):
            version_record["release_date"] = date.fromisoformat(rd)
