#!/usr/bin/env python3
"""Extract every user-settable option of a pipeline at each listed version (2026-11-11).

The author's request: complete coverage of the options each version offers, so that a model can
infer what a pipeline would have done from a paper's publication year (the versions released by
then, their options and defaults). Mechanical, so it is complete and re-runnable:

- fmriprep: every ``add_argument`` call of the command-line parser, read with ``ast`` at each
  listed tag (``fmriprep/cli/run.py`` to 20.0.0, ``fmriprep/cli/parser.py`` from 20.1.0): its
  flags, argument group, default, choices, action, type, nargs and help, with the line.
- cpac: every key of the default pipeline configuration YAML at each listed tag (the file per
  version is given by ``--config-map``), flattened to dotted paths, with its default, the comment
  lines above it, and the line.

Options are compressed into version ranges over the KB's listed versions: a new range starts
where the default or the allowed values change. Help text and comments are kept from the latest
version that has the option. The source repository is read with ``git show <tag>:<path>``; the
code is parsed, never executed.

Hard-coded workflow parameters (values no option exposes) are not extractable this way; a
curated file of them (``--step-parameters``) is copied into the output under ``step_parameters``.

    python scripts/extract_pipeline_options.py fmriprep --repo <clone> --out kb/pipeline_options/fmriprep.yaml
    python scripts/extract_pipeline_options.py cpac --repo <clone> --config-map <map.yaml> --out kb/pipeline_options/cpac.yaml
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import yaml

KB = Path(__file__).resolve().parents[1] / "kb"


def git_show(repo: Path, tag: str, path: str) -> str | None:
    p = subprocess.run(
        # refs/tags/ explicitly: a C-PAC tag (v1.3.0) is also a branch name
        ["git", "-C", str(repo), "show", f"refs/tags/{tag}:{path}"],
        capture_output=True,
        text=True,
    )
    return p.stdout if p.returncode == 0 else None


def resolve_tag(repo: Path, version: str) -> str:
    for cand in (version, f"v{version}"):
        p = subprocess.run(
            ["git", "-C", str(repo), "rev-parse", "-q", "--verify", f"refs/tags/{cand}"],
            capture_output=True,
            text=True,
        )
        if p.returncode == 0:
            return cand
    raise SystemExit(f"no tag for version {version}")


def listed_versions(pipeline_id: str) -> list[str]:
    doc = yaml.safe_load((KB / "pipelines" / f"{pipeline_id}.yaml").read_text())
    return [
        str(v["version"])
        for v in sorted(doc["versions"], key=lambda v: (str(v["release_date"]), str(v["version"])))
    ]


# --- fmriprep: the argparse calls -----------------------------------------------------------------


def _literal(node: ast.AST | None) -> Any:
    if node is None:
        return None
    try:
        return ast.literal_eval(node)
    except (ValueError, SyntaxError, TypeError):
        return {"expression": ast.unparse(node)}


def _text(node: ast.AST | None) -> str | None:
    if node is None:
        return None
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.JoinedStr) or isinstance(node, ast.BinOp) or isinstance(node, ast.Call):
        return ast.unparse(node)
    return ast.unparse(node)


def argparse_options(source: str) -> list[dict[str, Any]]:
    """Every ``<x>.add_argument(...)`` call: flags, group title, default, choices and so on."""
    tree = ast.parse(source)
    groups: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Call):
            f = node.value.func
            if isinstance(f, ast.Attribute) and f.attr in (
                "add_argument_group",
                "add_mutually_exclusive_group",
            ):
                title = _text(node.value.args[0]) if node.value.args else None
                for t in node.targets:
                    if isinstance(t, ast.Name):
                        groups[t.id] = title or (
                            "(mutually exclusive)" if f.attr.endswith("group") else ""
                        )
    out = []
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)):
            continue
        if node.func.attr != "add_argument":
            continue
        flags = [
            a.value for a in node.args if isinstance(a, ast.Constant) and isinstance(a.value, str)
        ]
        if not flags:
            continue
        kw = {k.arg: k.value for k in node.keywords if k.arg}
        owner = node.func.value.id if isinstance(node.func.value, ast.Name) else None
        longs = [f for f in flags if f.startswith("--")]
        out.append(
            {
                "id": longs[0] if longs else flags[0],
                "flags": flags,
                "group": groups.get(owner or "", None),
                "default": _literal(kw.get("default")),
                "choices": _literal(kw.get("choices")),
                "action": _text(kw.get("action")),
                "type": _text(kw.get("type")),
                "nargs": _literal(kw.get("nargs")),
                "help": _text(kw.get("help")),
                "line": node.lineno,
            }
        )
    return out


def fmriprep_version(repo: Path, tag: str) -> tuple[str, list[dict[str, Any]]]:
    # the parser moved: fmriprep/run_workflow.py (0.0.3-0.3.1), cli/run.py (0.3.2-20.0.x),
    # cli/parser.py (from 20.1.0)
    for path in ("fmriprep/cli/parser.py", "fmriprep/cli/run.py", "fmriprep/run_workflow.py"):
        src = git_show(repo, tag, path)
        if src and "add_argument(" in src:
            return path, argparse_options(src)
    raise SystemExit(f"no parser at {tag}")


# --- cpac: the default configuration YAML ---------------------------------------------------------


def tolerant_compose(source: str, max_drops: int = 10) -> tuple[yaml.Node | None, list[str]]:
    """``yaml.compose``, dropping (blanking) the line a parse error points at and retrying, at
    most ``max_drops`` times; returns the node and a record of each dropped line. A file that
    still does not parse raises. (C-PAC 1.0.3-1.1.0's template has an invalid line 376.)"""
    lines = source.splitlines()
    dropped: list[str] = []
    for _ in range(max_drops + 1):
        try:
            return yaml.compose("\n".join(lines), Loader=yaml.SafeLoader), dropped
        except yaml.MarkedYAMLError as exc:
            mark = exc.problem_mark
            if mark is None or len(dropped) == max_drops:
                raise
            dropped.append(f"line {mark.line + 1} ({exc.problem}): {lines[mark.line].strip()[:80]}")
            lines[mark.line] = ""
    raise AssertionError("unreachable")


def yaml_options(source: str, dropped: list[str] | None = None) -> list[dict[str, Any]]:
    """Every leaf key of a YAML mapping as a dotted path, with its value, line and the comment
    lines directly above it. Lines the parser could not read are dropped and recorded in
    ``dropped`` (when given)."""
    lines = source.splitlines()
    root, gone = tolerant_compose(source)
    if dropped is not None:
        dropped.extend(gone)
    out: list[dict[str, Any]] = []

    def comments_above(line_idx: int) -> str | None:
        got = []
        i = line_idx - 1
        while i >= 0 and lines[i].strip().startswith("#"):
            got.append(lines[i].strip().lstrip("#").strip())
            i -= 1
        text = " ".join(reversed([g for g in got if g]))
        return text or None

    def walk(node: yaml.Node, prefix: str) -> None:
        if isinstance(node, yaml.MappingNode):
            for k, v in node.value:
                key = str(k.value)
                path = f"{prefix}.{key}" if prefix else key
                if isinstance(v, yaml.MappingNode) and v.value:
                    walk(v, path)
                else:
                    value = yaml.constructor.SafeConstructor().construct_object(v, deep=True)
                    out.append(
                        {
                            "id": path,
                            "default": value,
                            "choices": None,
                            "help": comments_above(k.start_mark.line),
                            "line": k.start_mark.line + 1,
                        }
                    )

    if root is not None:
        walk(root, "")
    # a key written twice: the last occurrence wins, as yaml.safe_load (C-PAC's loader) has it
    last: dict[str, dict[str, Any]] = {}
    for o in out:
        last[o["id"]] = o
    return list(last.values())


# --- ranges ----------------------------------------------------------------------------------------


def _key(opt: dict[str, Any]) -> str:
    return json.dumps(
        {
            k: opt.get(k)
            for k in ("default", "choices", "action", "nargs", "gui_default", "in_config")
        },
        sort_keys=True,
        default=str,
    )


def _src(path: str | None, o: dict[str, Any], v: str) -> str:
    """'line N at <version>': the file is the version's own, recorded once in ``sources``."""
    if o.get("line") is None:  # only in the GUI pages
        return str(o.get("gui_source") or f"GUI pages at {v}")
    return f"line {o['line']} at {v}"


def compress(
    per_version: dict[str, tuple[str | None, list[dict[str, Any]]]], versions: list[str]
) -> list[dict[str, Any]]:
    ids: list[str] = []
    for v in versions:
        for o in per_version[v][1]:
            if o["id"] not in ids:
                ids.append(o["id"])
    out = []
    for oid in ids:
        ranges: list[dict[str, Any]] = []
        latest: dict[str, Any] | None = None
        present: list[str] = []
        for v in versions:
            path, opts = per_version[v]
            found = next((x for x in opts if x["id"] == oid), None)
            if found is None:
                continue
            o = found
            present.append(v)
            latest = o
            last = ranges[-1] if ranges else None
            contiguous = (
                last is not None and versions.index(last["to_version"]) == versions.index(v) - 1
            )
            if last is not None and contiguous and last["_key"] == _key(o):
                last["to_version"] = v
                last["_to_src"] = _src(path, o, v)
            else:
                ranges.append(
                    {
                        "from_version": v,
                        "to_version": v,
                        "default": o.get("default"),
                        **({"choices": o["choices"]} if o.get("choices") is not None else {}),
                        **({"action": o["action"]} if o.get("action") else {}),
                        **({"nargs": o["nargs"]} if o.get("nargs") is not None else {}),
                        **({"in_config": False} if o.get("in_config") is False else {}),
                        **(
                            {"gui_default": o["gui_default"], "gui_source": o["gui_source"]}
                            if "gui_default" in o
                            else {}
                        ),
                        "_key": _key(o),
                        "_from_src": _src(path, o, v),
                        "_to_src": _src(path, o, v),
                    }
                )
        for r in ranges:
            r["source"] = r.pop("_from_src") + (
                "" if r["from_version"] == r["to_version"] else f"; {r.pop('_to_src')}"
            )
            r.pop("_to_src", None)
            r.pop("_key")
        assert latest is not None
        entry: dict[str, Any] = {"id": oid}
        if latest.get("flags") and latest["flags"] != [oid]:
            entry["flags"] = latest["flags"]
        if latest.get("group"):
            entry["group"] = latest["group"]
        if latest.get("type"):
            entry["type"] = latest["type"]
        if latest.get("help"):
            entry["help"] = " ".join(str(latest["help"]).split())
        entry["available"] = (
            {"from_version": present[0], "to_version": present[-1]}
            if len(present) == versions.index(present[-1]) - versions.index(present[0]) + 1
            else {"versions": present}
        )
        entry["ranges"] = ranges
        out.append(entry)
    return out


def main(argv: list[str] | None = None) -> int:
    from pipeline_option_sources import gui_options, nesting_map, release_timeline

    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("pipeline", choices=["fmriprep", "cpac"])
    ap.add_argument("--repo", type=Path, required=True)
    ap.add_argument(
        "--config-map", type=Path, help="cpac: YAML list of {version, path, role, note}"
    )
    ap.add_argument("--step-parameters", type=Path, help="curated hard-coded parameters to copy in")
    ap.add_argument("--step-options", type=Path, help="curated {step: [option ids]} to copy in")
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args(argv)
    # 2026-11-11 (the author's "fill all gaps"): every final release tag, not only the KB's
    # listed versions; each row of the timeline says whether the KB lists it
    listed = set(listed_versions(a.pipeline))
    timeline = release_timeline(a.repo)
    versions = [str(r["version"]) for r in timeline]
    per_version: dict[str, tuple[str | None, list[dict[str, Any]]]] = {}
    sources: list[dict[str, Any]] = []
    cmap: dict[str, Any] = {}
    roles: dict[str, tuple[Any, Any]] = {}
    rule_rows: dict[str, dict[str, int]] = {}
    if a.pipeline == "cpac":
        if not a.config_map:
            raise SystemExit("cpac needs --config-map")
        rows = yaml.safe_load(a.config_map.read_text())
        cmap = {str(r["version"]): r.get("path") for r in rows}
        roles = {str(r["version"]): (r.get("role"), r.get("note")) for r in rows}
        missing = [v for v in versions if v not in cmap]
        if missing:
            raise SystemExit(f"--config-map has no row for {missing}")
    for row in timeline:
        v, tag = str(row["version"]), str(row["tag"])
        path: str | None
        if a.pipeline == "fmriprep":
            path, opts = fmriprep_version(a.repo, tag)
        else:
            path = cmap.get(v)
            src = git_show(a.repo, tag, path) if path else None
            dropped: list[str] = []
            opts = yaml_options(src, dropped) if src else []
            if dropped:
                note = roles.get(v, (None, None))[1]
                extra = "unparseable lines dropped: " + "; ".join(dropped)
                roles[v] = (roles.get(v, (None, None))[0], f"{note} {extra}" if note else extra)
            gui, gui_rules = gui_options(a.repo, tag)
            if gui_rules:
                roles.setdefault(v, (None, None))
                rule_rows[v] = gui_rules
            for o in opts:
                if o["id"] in gui:
                    o.update(gui[o["id"]])
            known = {o["id"] for o in opts}
            for name, g in gui.items():
                if name not in known:  # in the GUI, not in this version's YAML
                    opts.append(
                        {"id": name, "default": None, "in_config": False, "line": None, **g}
                    )
        text = git_show(a.repo, tag, path) if path else None
        per_version[v] = (path, opts)
        sources.append(
            {
                "version": v,
                "tag": tag,
                "file": path,
                "options": len([o for o in opts if o.get("in_config", True)]),
                **({"sha256": hashlib.sha256(text.encode()).hexdigest()[:12]} if text else {}),
                **({"role": roles[v][0]} if roles.get(v, (None,))[0] else {}),
                **({"note": roles[v][1]} if roles.get(v, (None, None))[1] else {}),
                **(
                    {"gui_rules": {f"{k}_line": n for k, n in rule_rows[v].items()}}
                    if v in rule_rows
                    else {}
                ),
            }
        )
        print(f"{v}: {path} ({len(opts)} options)", file=sys.stderr)
    options = compress(per_version, versions)
    if a.pipeline == "cpac":
        latest = str(timeline[-1]["tag"])
        flat_to_nested, deprecated, map_src = nesting_map(a.repo, latest)
        nested_from: dict[str, list[str]] = {}
        for flat, nested in flat_to_nested.items():
            nested_from.setdefault(nested, []).append(flat)
        for o in options:
            oid = str(o["id"])
            if oid in flat_to_nested:
                o["nested_as"] = flat_to_nested[oid]
            if oid in nested_from:
                o["flat_as"] = sorted(nested_from[oid])
            if oid in deprecated:
                o["deprecated_in_1_8"] = True
    doc: dict[str, Any] = {
        "pipeline_id": a.pipeline,
        "generated_by": "scripts/extract_pipeline_options.py",
        "method": (
            "every add_argument call of the command-line parser, parsed with ast at every final "
            "release tag"
            if a.pipeline == "fmriprep"
            else "every key of the default pipeline configuration YAML at every final release tag, "
            "with the GUI pages' initial values where the GUI exists"
        ),
        "repository": (
            "https://github.com/nipreps/fmriprep"
            if a.pipeline == "fmriprep"
            else "https://github.com/FCP-INDI/C-PAC"
        ),
        **({"key_map_source": map_src} if a.pipeline == "cpac" else {}),
        "timeline": [{**r, "listed": str(r["version"]) in listed} for r in timeline],
        "sources": sources,
        "options": options,
    }
    if a.step_parameters:
        doc["step_parameters"] = yaml.safe_load(a.step_parameters.read_text())
    if a.step_options:
        doc["step_options"] = yaml.safe_load(a.step_options.read_text())
    a.out.parent.mkdir(parents=True, exist_ok=True)
    header = (
        f"# Generated by scripts/extract_pipeline_options.py ({a.pipeline}); do not edit by hand.\n"
        "# Re-run the script to regenerate; curated inputs are in scripts/data/.\n"
    )
    a.out.write_text(header + yaml.safe_dump(doc, sort_keys=False, allow_unicode=True, width=100))
    print(
        f"wrote {a.out}: {len(doc['options'])} options over {len(versions)} versions",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
