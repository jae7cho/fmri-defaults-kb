"""Software-package (tool) registry: ``kb/tools/*.yaml``.

A package is not a pipeline. ``kb/pipelines/`` says which program a pipeline runs for a step;
``kb/tools/`` says which program a package ships for it. First consumer (2026-10-28): the agent's
``motion_correction.method`` package basis (``derived``, ceiling 0.70) and the motion
value-in-quote check's listed-package fallback -- one table for both.

Functions:
  - recognize_tool(name) -> tool_id | None
  - realignment_program(tool_id) -> RealignmentProgram
  - listed_package_tokens() -> {token: version_token}
"""

from __future__ import annotations

import re
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from fmri_defaults_kb.errors import KbError
from fmri_defaults_kb.io import find_kb_root


class KbUnknownToolError(KbError):
    """``tool_id`` is not a document under ``kb/tools/``."""


@dataclass(frozen=True)
class RealignmentProgram:
    tool_id: str
    program: str
    source: str
    notes: str | None


_cache: dict[Path, dict[str, dict[str, Any]]] = {}
_cache_lock = threading.Lock()


def load_tool_documents(kb_root: Path | str | None = None) -> dict[str, dict[str, Any]]:
    """Load every ``kb/tools/*.yaml`` and return ``{tool_id: document}``, cached per root."""
    root = find_kb_root(kb_root).resolve()
    with _cache_lock:
        cached = _cache.get(root)
        if cached is not None:
            return cached
        tools_dir = root / "tools"
        documents: dict[str, dict[str, Any]] = {}
        if tools_dir.is_dir():
            for yaml_file in sorted(tools_dir.glob("*.yaml")):
                with yaml_file.open("r", encoding="utf-8") as f:
                    doc = yaml.safe_load(f)
                if not isinstance(doc, dict) or not doc.get("tool_id"):
                    raise ValueError(f"{yaml_file}: a tool document needs a top-level tool_id")
                documents[str(doc["tool_id"])] = doc
        _cache[root] = documents
        return documents


def clear_tool_cache() -> None:
    with _cache_lock:
        _cache.clear()


def _normalize(s: str) -> str:
    return " ".join(s.lower().split())


_TRAILING_VERSION = re.compile(r"^(.*?[a-z])\s*v?\d+(?:\.\d+)*$")


def _needles(name: str, version_token: bool) -> set[str]:
    """The normalized forms a name may match under: itself, and -- for a version_token package --
    itself with a trailing version token removed (``spm12`` -> ``spm``,
    ``statistical parametric mapping 12`` -> ``statistical parametric mapping``)."""
    n = _normalize(name)
    out = {n}
    if version_token:
        m = _TRAILING_VERSION.match(n)
        if m:
            out.add(m.group(1).strip())
    return {x for x in out if x}


def recognize_tool(name: str, *, kb_root: Path | str | None = None) -> str | None:
    """Resolve a free-text package name to a ``tool_id``, or ``None`` if unknown.

    Whole-name match after normalization against ``tool_id`` / ``display_name`` / ``aliases``;
    a trailing version token is stripped first for ``version_token`` packages. Not fuzzy: a
    pipeline name (``C-PAC``), a program (``MCFLIRT``) or a prefix match is ``None``. Ambiguity
    guard: two distinct tools -> ``None``.
    """
    if not name or not name.strip():
        return None
    matched: set[str] = set()
    for tool_id, doc in load_tool_documents(kb_root).items():
        candidates = {
            _normalize(c)
            for c in (tool_id, doc.get("display_name", ""), *doc.get("aliases", []))
            if c
        }
        if _needles(name, bool(doc.get("version_token"))) & candidates:
            matched.add(tool_id)
    return next(iter(matched)) if len(matched) == 1 else None


def realignment_program(tool_id: str, *, kb_root: Path | str | None = None) -> RealignmentProgram:
    """The realignment program ``tool_id`` ships, with its source."""
    documents = load_tool_documents(kb_root)
    if tool_id not in documents:
        raise KbUnknownToolError(tool_id)
    block = documents[tool_id]["realignment"]
    return RealignmentProgram(
        tool_id=tool_id,
        program=str(block["program"]),
        source=str(block["source"]),
        notes=(str(block["notes"]) if block.get("notes") else None),
    )


def listed_package_tokens(*, kb_root: Path | str | None = None) -> dict[str, bool]:
    """``{bare name token: version_token}`` for every listed package -- the table the motion
    value-in-quote fallback reads. The token is the ``tool_id`` (``afni``, ``fsl``, ``spm``,
    ``ants``, ``brainvoyager``); ``version_token`` says whether digits after it are part of the
    name (SPM12) or a citation artefact (AFNI48)."""
    return {
        tool_id: bool(doc.get("version_token"))
        for tool_id, doc in load_tool_documents(kb_root).items()
    }
