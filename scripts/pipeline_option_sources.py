"""Source readers for extract_pipeline_options.py (2026-11-11): every final release tag with its
date, C-PAC's GUI defaults, and C-PAC's own 1.7-to-1.8 key map. Code is read with ``git show``
and parsed, never executed."""

from __future__ import annotations

import ast
import re
import subprocess
from pathlib import Path
from typing import Any

import yaml

FINAL_TAG = re.compile(r"^v?\d+(\.\d+)+$")  # a release; not rc, a, b, dev or post


def git_show(repo: Path, tag: str, path: str) -> str | None:
    p = subprocess.run(
        # refs/tags/ explicitly: a C-PAC tag (v1.3.0) is also a branch name
        ["git", "-C", str(repo), "show", f"refs/tags/{tag}:{path}"],
        capture_output=True,
        text=True,
    )
    return p.stdout if p.returncode == 0 else None


def vkey(version: str) -> tuple[int, ...]:
    return tuple(int(x) for x in re.findall(r"\d+", version))


def release_timeline(repo: Path) -> list[dict[str, Any]]:
    """Every final release tag, oldest first by version number, with the date git records for
    the tag (``creatordate``: the tagger date, or the commit date of a lightweight tag)."""
    out = subprocess.run(
        [
            "git",
            "-C",
            str(repo),
            "for-each-ref",
            # lstrip=2, not :short: a tag that is also a branch name shortens to tags/<name>
            "--format=%(refname:lstrip=2)|%(creatordate:short)",
            "refs/tags",
        ],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    rows = []
    for line in out.splitlines():
        tag, _, day = line.partition("|")
        if FINAL_TAG.match(tag):
            rows.append({"version": tag.lstrip("v"), "tag": tag, "date": day})
    return sorted(rows, key=lambda r: vkey(str(r["version"])))


# --- C-PAC's GUI pages ----------------------------------------------------------------------------

#: CPAC/GUI/interface/utils/constants.py (read at v0.3.6): the control enum
CONTROL = {
    "CHOICE_BOX": 0,
    "TEXT_BOX": 1,
    "COMBO_BOX": 2,
    "INT_CTRL": 3,
    "FLOAT_CTRL": 4,
    "DIR_COMBO_BOX": 5,
    "CHECKLIST_BOX": 6,
    "LISTBOX_COMBO": 7,
    "TEXTBOX_COMBO": 8,
    "CHECKBOX_GRID": 9,
}


def _literal(node: ast.AST | None) -> Any:
    if node is None:
        return None
    try:
        return ast.literal_eval(node)
    except (ValueError, SyntaxError, TypeError):
        return {"expression": ast.unparse(node)}


def _attr(node: ast.AST | None) -> str | None:
    return node.attr if isinstance(node, ast.Attribute) else None


def gui_rule_lines(source: str) -> dict[str, int]:
    """Where generic_class.py's control constructor sets a choice box's and a checklist's
    initial selection."""
    found: dict[str, int] = {}
    for i, line in enumerate(source.splitlines(), 1):
        if "self.selection = values[0]" in line:
            found.setdefault("choice", i)
        if re.search(r"if datatype\s*==\s*3", line):
            found.setdefault("checklist", i)
    return found


def gui_options(repo: Path, tag: str) -> tuple[dict[str, dict[str, Any]], dict[str, int]]:
    """Every ``<page>.add(..., control=..., name=..., values=...)`` call of the GUI pages
    (CPAC/GUI/interface/pages/*.py) at ``tag``, with the initial selection the control
    constructor (CPAC/GUI/interface/utils/generic_class.py) gives it: a choice box, its first
    value; a text, combo, number or directory control, its value; a checklist, all its values
    when the dtype is LBOOL (3), else none. Other controls keep their raw values. Also returns
    the generic_class.py lines of the choice-box and checklist rules at ``tag``."""
    names = subprocess.run(
        [
            "git",
            "-C",
            str(repo),
            "ls-tree",
            "-r",
            "--name-only",
            f"refs/tags/{tag}",
            "--",
            "CPAC/GUI/interface/pages",
        ],
        capture_output=True,
        text=True,
    ).stdout.split()
    if not names:
        return {}, {}
    rules = gui_rule_lines(git_show(repo, tag, "CPAC/GUI/interface/utils/generic_class.py") or "")
    out: dict[str, dict[str, Any]] = {}
    for path in sorted(n for n in names if n.endswith(".py")):
        try:
            tree = ast.parse(git_show(repo, tag, path) or "")
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)):
                continue
            if node.func.attr != "add":
                continue
            kw = {k.arg: k.value for k in node.keywords if k.arg}
            if "name" not in kw or "control" not in kw:
                continue
            name = _literal(kw["name"])
            if not isinstance(name, str):
                continue
            control = _attr(kw["control"])
            code = CONTROL.get(control or "")
            values = _literal(kw.get("values"))
            # relative to CPAC/GUI/interface/ (stated once in the schema)
            src = f"{path.removeprefix('CPAC/GUI/interface/')} line {node.lineno} at {tag}"
            default: Any
            if code == 0 and isinstance(values, list) and values:
                default = values[0]
            elif code in (1, 2, 3, 4, 5):
                default = values
            elif code == 6:
                default = values if _attr(kw.get("type")) == "LBOOL" else []
            else:
                default = {"gui_values": values}
            out[name] = {"gui_default": default, "gui_control": control, "gui_source": src}
    return out, rules


def nesting_map(repo: Path, tag: str) -> tuple[dict[str, str], set[str], str]:
    """C-PAC's own map of 1.7 flat keys to 1.8 nested paths, and the keys 1.8 deprecates, at
    ``tag`` (CPAC/resources/configs/1.7-1.8-nesting-mappings.yml, 1.7-1.8-deprecations.yml)."""
    base = "CPAC/resources/configs"
    mp = yaml.safe_load(git_show(repo, tag, f"{base}/1.7-1.8-nesting-mappings.yml") or "{}") or {}
    dep = yaml.safe_load(git_show(repo, tag, f"{base}/1.7-1.8-deprecations.yml") or "[]") or []
    flat_to_nested = {str(k): ".".join(str(x) for x in v) for k, v in mp.items()}
    src = f"{base}/1.7-1.8-nesting-mappings.yml and 1.7-1.8-deprecations.yml at {tag}"
    return flat_to_nested, {str(d) for d in dep}, src
