#!/usr/bin/env python3
"""Fetch a ``version -> {release_date, source_url}`` timeline from tagged repos.

Bucket 1 ONLY: version string + release date + source URL. This is maintenance
tooling (the agent never imports it); it feeds ``resolve_version`` /
``date_inferred_version`` and the registry's ``versions[]`` by emitting a
*staging* fragment under ``scripts/_staging/`` for human review. It NEVER edits
``kb/pipelines/*.yaml``.

Out of scope (deliberately): ``param_defaults``, runtime/env (MATLAB/Python/OS),
and data-release dates (HCP S500/S900/S1200 are a separate axis).

No fabrication: an unresolved release date is emitted as the ``NEEDS_VERIFICATION``
sentinel, never guessed.

Schema note (Phase 0 divergence). ``pipeline_registry.schema.json`` makes
``release_date`` a *required* string with ``format: date`` and has no sentinel
for a missing date (the ``needs_verification`` sentinel exists only for
``param_default.value``). Staging fragments are pre-merge drafts, so records with
a resolved date are validated against the strict ``version_record`` subschema,
while ``NEEDS_VERIFICATION`` rows are validated against a relaxed variant whose
``release_date`` is ``const "NEEDS_VERIFICATION"`` — every other shape error is
still caught, and the human resolves the date at merge.

HTTP is stdlib ``urllib`` only (no ``requests``). Reads ``GITHUB_TOKEN`` from the
environment and sends ``Authorization: Bearer`` when present (60 -> 5000 req/hr).
On HTTP 403 / rate-limit it fails loudly rather than emitting a partial timeline.

Usage::

    python scripts/fetch_version_timeline.py                 # fetch all registered
    python scripts/fetch_version_timeline.py hcp_minimal ccs # fetch a subset
    python scripts/fetch_version_timeline.py --list ccs       # raw tag names, no filter
"""

from __future__ import annotations

import argparse
import copy
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol, cast

import yaml
from jsonschema import Draft202012Validator, FormatChecker

# --- constants --------------------------------------------------------------

NEEDS_VERIFICATION = "NEEDS_VERIFICATION"

_GITHUB_API = "https://api.github.com"
_USER_AGENT = "fmri-defaults-kb-version-timeline-fetcher"
_API_VERSION = "2022-11-28"
_PER_PAGE = 100
_TIMEOUT_S = 30

# Prerelease markers (PEP 440-ish) checked at the END of a tag name, applied
# AFTER tag_filter. Strict numeric filters already exclude these, but a looser
# filter relies on this guard.
_PRERELEASE_RE = re.compile(
    r"[-._]?(?:a|b|c|rc|alpha|beta|dev|pre|preview|snapshot)\.?\d*$",
    re.IGNORECASE,
)

_SCHEMA_PATH = Path(__file__).resolve().parent.parent / "schemas" / "pipeline_registry.schema.json"
_STAGING_DIR = Path(__file__).resolve().parent / "_staging"


# --- errors -----------------------------------------------------------------


class FetcherError(RuntimeError):
    """Any unrecoverable error while fetching a timeline."""


class RateLimitError(FetcherError):
    """GitHub returned 403 / rate-limit. We fail loudly, never partially."""


# --- data model -------------------------------------------------------------


@dataclass(frozen=True)
class VersionRecord:
    """One ``versions[]`` row, Bucket-1 fields only."""

    version: str
    release_date: str | None
    release_source: str


class VersionSource(Protocol):
    """A source that can enumerate a pipeline's version timeline."""

    pipeline_id: str

    def iter_versions(self) -> Iterable[VersionRecord]: ...


# --- HTTP (stdlib urllib) ---------------------------------------------------


def _request_json(url: str, token: str | None) -> tuple[Any, dict[str, str]]:
    """GET ``url`` and return ``(parsed_json, response_headers)``.

    - 404 -> ``(None, headers)`` (an expected "no such release/ref" signal).
    - 403 -> :class:`RateLimitError` (fail loudly; never emit a partial timeline).
    - other HTTP / URL errors -> :class:`FetcherError`.
    """
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": _USER_AGENT,
        "X-GitHub-Api-Version": _API_VERSION,
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT_S) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
            return payload, {k: v for k, v in resp.headers.items()}
    except urllib.error.HTTPError as exc:
        resp_headers = {k: v for k, v in exc.headers.items()} if exc.headers else {}
        if exc.code == 404:
            return None, resp_headers
        if exc.code in (403, 429):
            remaining = resp_headers.get("X-RateLimit-Remaining")
            hint = (
                " (rate limit exhausted; set GITHUB_TOKEN to raise 60->5000/hr)"
                if remaining == "0"
                else " (set GITHUB_TOKEN if this is an auth/rate issue)"
            )
            raise RateLimitError(
                f"GitHub API GET {url} -> HTTP {exc.code} {exc.reason}{hint}"
            ) from exc
        raise FetcherError(f"GitHub API GET {url} -> HTTP {exc.code} {exc.reason}") from exc
    except urllib.error.URLError as exc:
        raise FetcherError(f"GitHub API GET {url} failed: {exc.reason}") from exc


def _parse_next_link(link_header: str) -> str | None:
    """Return the ``rel="next"`` URL from an RFC 5988 ``Link`` header, or None."""
    if not link_header:
        return None
    for part in link_header.split(","):
        segments = part.split(";")
        if len(segments) < 2:
            continue
        url = segments[0].strip().lstrip("<").rstrip(">")
        for attr in segments[1:]:
            key, _, value = attr.strip().partition("=")
            if key == "rel" and value.strip('"') == "next":
                return url
    return None


# --- GitHub tag source ------------------------------------------------------


@dataclass
class GitHubTagSource:
    """Enumerate a pipeline's versions from a GitHub repo's tags.

    ``version`` is the tag name VERBATIM (no normalization) so it matches what a
    citation or ``release_source`` URL references.
    """

    owner: str
    repo: str
    tag_filter: re.Pattern[str]
    include_prereleases: bool = False
    token: str | None = None
    pipeline_id: str = ""

    def __post_init__(self) -> None:
        if self.token is None:
            self.token = os.environ.get("GITHUB_TOKEN")
        if not self.pipeline_id:
            self.pipeline_id = self.repo.lower()

    # -- public ----------------------------------------------------------

    def iter_raw_tag_names(self) -> Iterator[str]:
        """Every tag name, UNFILTERED (for ``--list`` scheme inspection)."""
        for tag in self._all_tags():
            yield cast(str, tag["name"])

    def iter_versions(self) -> Iterator[VersionRecord]:
        for tag in self._all_tags():
            name = cast(str, tag["name"])
            if not self.tag_filter.search(name):
                continue
            if not self.include_prereleases and _PRERELEASE_RE.search(name):
                continue
            sha = cast(str, tag["commit"]["sha"])
            release_date, has_release = self._resolve_date(name, sha)
            yield VersionRecord(
                version=name,
                release_date=release_date,
                release_source=self._release_source(name, has_release),
            )

    # -- internals -------------------------------------------------------

    def _all_tags(self) -> Iterator[dict[str, Any]]:
        url: str | None = f"{_GITHUB_API}/repos/{self.owner}/{self.repo}/tags?per_page={_PER_PAGE}"
        while url:
            payload, resp_headers = _request_json(url, self.token)
            if payload is None:
                raise FetcherError(f"repo {self.owner}/{self.repo} not found (GET /tags -> 404)")
            for tag in payload:
                yield cast("dict[str, Any]", tag)
            url = _parse_next_link(resp_headers.get("Link", ""))

    def _resolve_date(self, tag: str, peeled_sha: str) -> tuple[str | None, bool]:
        """Resolve a tag's date via the empirically-correct fallback chain.

        Returns ``(YYYY-MM-DD | None, has_published_release)``.
        """
        quoted = urllib.parse.quote(tag, safe="")
        base = f"{_GITHUB_API}/repos/{self.owner}/{self.repo}"

        # 1. published Release for this tag.
        release, _ = _request_json(f"{base}/releases/tags/{quoted}", self.token)
        has_release = release is not None
        if release is not None:
            published = release.get("published_at")
            if published:
                return _date_part(published), True

        # 2. dereference the tag ref. Singular /git/ref/tags/{tag} returns the
        #    exact single ref (the plural /git/refs/... prefix-matches).
        ref, _ = _request_json(f"{base}/git/ref/tags/{quoted}", self.token)
        if ref is not None:
            obj = ref.get("object", {})
            obj_sha = obj.get("sha", peeled_sha)
            if obj.get("type") == "tag":  # annotated tag
                annotated, _ = _request_json(f"{base}/git/tags/{obj_sha}", self.token)
                if annotated is not None:
                    tagger_date = annotated.get("tagger", {}).get("date")
                    if tagger_date:
                        return _date_part(tagger_date), has_release
            else:  # lightweight tag -> the commit it points at
                commit, _ = _request_json(f"{base}/commits/{obj_sha}", self.token)
                if commit is not None:
                    committer_date = commit.get("commit", {}).get("committer", {}).get("date")
                    if committer_date:
                        return _date_part(committer_date), has_release

        # 3. give up -> NEEDS_VERIFICATION downstream.
        return None, has_release

    def _release_source(self, tag: str, has_release: bool) -> str:
        base = f"https://github.com/{self.owner}/{self.repo}"
        return f"{base}/releases/tag/{tag}" if has_release else f"{base}/tree/{tag}"


def _date_part(timestamp: str) -> str:
    """``2020-02-12T19:57:44Z`` -> ``2020-02-12``."""
    return timestamp[:10]


# --- stub sources (architecture-ready for Sub-A; not implemented) -----------


@dataclass
class SpmReleaseNotesSource:
    """SPM versions are release+revision (SPM8/12/25 + ``r#####``), dated from the
    SPM release-notes page, not git tags."""

    pipeline_id: str = "spm"

    def iter_versions(self) -> Iterable[VersionRecord]:
        raise NotImplementedError(
            "SPM: parse release + revision (SPM8/12/25, r#####) and dates from "
            "https://www.fil.ion.ucl.ac.uk/spm/software/ release notes — not git tags."
        )


@dataclass
class FslReleaseSource:
    """FSL releases/dates live in the FSL release history, not GitHub tags."""

    pipeline_id: str = "fsl"

    def iter_versions(self) -> Iterable[VersionRecord]:
        raise NotImplementedError(
            "FSL: scrape the FSL release history at "
            "https://fsl.fmrib.ox.ac.uk/fsl/fslwiki/FslReleaseHistory — not git tags."
        )


@dataclass
class FreeSurferReleaseSource:
    """FreeSurfer releases/dates live in its release notes, not GitHub tags."""

    pipeline_id: str = "freesurfer"

    def iter_versions(self) -> Iterable[VersionRecord]:
        raise NotImplementedError(
            "FreeSurfer: parse https://surfer.nmr.mgh.harvard.edu/fswiki/ReleaseNotes "
            "(and the freesurfer/freesurfer GitHub releases) — version+date, not bare tags."
        )


# --- registry ---------------------------------------------------------------


def build_source(pipeline_id: str, token: str | None = None) -> VersionSource:
    """Construct the registered source for ``pipeline_id``.

    CCS carries no release tags today (verified: ``git ls-remote --tags`` is
    empty); its filter is set permissively so any future ``vX.Y[.Z]`` tag is
    picked up. Inspect the live scheme with ``--list ccs`` before trusting it.
    """
    if pipeline_id == "hcp_minimal":
        return GitHubTagSource(
            "Washington-University",
            "HCPpipelines",
            re.compile(r"^v\d+\.\d+\.\d+$"),
            token=token,
            pipeline_id="hcp_minimal",
        )
    if pipeline_id == "fmriprep":
        return GitHubTagSource(
            "nipreps",
            "fmriprep",
            re.compile(r"^\d+\.\d+\.\d+$"),
            token=token,
            pipeline_id="fmriprep",
        )
    if pipeline_id == "ccs":
        return GitHubTagSource(
            "zuoxinian",
            "CCS",
            re.compile(r"^v?\d+\.\d+(?:\.\d+)?$"),
            token=token,
            pipeline_id="ccs",
        )
    raise FetcherError(
        f"no registered source for pipeline_id {pipeline_id!r}; "
        f"registered: {', '.join(REGISTERED_PIPELINES)}"
    )


REGISTERED_PIPELINES = ("hcp_minimal", "fmriprep", "ccs")


# --- validation -------------------------------------------------------------


def _build_validators() -> tuple[Draft202012Validator, Draft202012Validator]:
    """Return ``(strict, relaxed)`` validators for a single ``version_record``.

    ``strict`` is the schema's ``version_record`` subschema verbatim (resolved
    dates). ``relaxed`` pins ``release_date`` to ``const "NEEDS_VERIFICATION"``
    so unresolved-date rows still get every other field shape-checked.
    """
    full = json.loads(_SCHEMA_PATH.read_text(encoding="utf-8"))
    defs = full["$defs"]
    strict_schema = {**defs["version_record"], "$defs": defs}

    relaxed_schema = copy.deepcopy(strict_schema)
    relaxed_schema["properties"]["release_date"] = {"const": NEEDS_VERIFICATION}

    return (
        Draft202012Validator(strict_schema, format_checker=FormatChecker()),
        Draft202012Validator(relaxed_schema, format_checker=FormatChecker()),
    )


def _record_to_entry(record: VersionRecord) -> dict[str, Any]:
    """A staging ``versions[]`` entry. ``param_defaults`` is omitted (optional;
    Bucket 1 carries no defaults — the human adds them at merge)."""
    return {
        "version": record.version,
        "release_date": record.release_date if record.release_date else NEEDS_VERIFICATION,
        "release_source": record.release_source,
    }


def _validate_entry(
    entry: dict[str, Any],
    strict: Draft202012Validator,
    relaxed: Draft202012Validator,
) -> None:
    validator = relaxed if entry["release_date"] == NEEDS_VERIFICATION else strict
    errors = sorted(validator.iter_errors(entry), key=lambda e: list(e.absolute_path))
    if errors:
        joined = "; ".join(
            f"{'/'.join(str(p) for p in e.absolute_path) or '<root>'}: {e.message}" for e in errors
        )
        raise FetcherError(f"staging record failed schema validation: {entry!r}: {joined}")


# --- output -----------------------------------------------------------------


@dataclass(frozen=True)
class SourceSummary:
    pipeline_id: str
    count: int
    earliest: str | None
    latest: str | None
    needs_verification: int
    out_path: Path


def _sort_key(record: VersionRecord) -> tuple[int, str]:
    # Unknown dates sort LAST (1, ""); known dates sort ascending by date.
    return (1, "") if record.release_date is None else (0, record.release_date)


def write_staging(source: VersionSource, *, staging_dir: Path = _STAGING_DIR) -> SourceSummary:
    """Fetch, validate, and write ``{pipeline_id}.versions.yaml``. Idempotent."""
    strict, relaxed = _build_validators()
    records = sorted(source.iter_versions(), key=_sort_key)

    entries: list[dict[str, Any]] = []
    for record in records:
        entry = _record_to_entry(record)
        _validate_entry(entry, strict, relaxed)
        entries.append(entry)

    staging_dir.mkdir(parents=True, exist_ok=True)
    out_path = staging_dir / f"{source.pipeline_id}.versions.yaml"
    header = (
        f"# STAGING fragment for kb/pipelines/{source.pipeline_id}.yaml — "
        "review before merge.\n"
        "# Bucket 1 only (version / release_date / release_source). "
        "Generated by scripts/fetch_version_timeline.py.\n"
        f"# '{NEEDS_VERIFICATION}' dates are unresolved — fill in by hand, do not guess.\n"
    )
    body = yaml.safe_dump({"versions": entries}, sort_keys=False, allow_unicode=True)
    out_path.write_text(header + body, encoding="utf-8")

    known = [r.release_date for r in records if r.release_date is not None]
    return SourceSummary(
        pipeline_id=source.pipeline_id,
        count=len(records),
        earliest=min(known) if known else None,
        latest=max(known) if known else None,
        needs_verification=sum(1 for r in records if r.release_date is None),
        out_path=out_path,
    )


def _print_summary(summary: SourceSummary) -> None:
    span = (
        f"{summary.earliest}..{summary.latest}"
        if summary.earliest and summary.latest
        else "(no resolved dates)"
    )
    print(
        f"{summary.pipeline_id}: {summary.count} versions, "
        f"date range {span}, {summary.needs_verification} {NEEDS_VERIFICATION} "
        f"-> {summary.out_path}"
    )
    if summary.pipeline_id == "hcp_minimal":
        print(
            "  reminder: these are HCPpipelines *tag* dates, NOT S500/S900/S1200 "
            "data-release dates — reconcile that axis by hand at merge."
        )


# --- CLI --------------------------------------------------------------------


def _run_list(pipeline_id: str, token: str | None) -> int:
    source = build_source(pipeline_id, token)
    if not isinstance(source, GitHubTagSource):
        raise FetcherError(f"--list is only supported for GitHub tag sources, not {pipeline_id!r}")
    print(f"# raw tags for {pipeline_id} ({source.owner}/{source.repo}), unfiltered:")
    names = list(source.iter_raw_tag_names())
    for name in names:
        print(name)
    print(f"# {len(names)} tag(s) total")
    return 0


def _run_fetch(pipeline_ids: list[str], token: str | None) -> int:
    for pipeline_id in pipeline_ids:
        source = build_source(pipeline_id, token)
        summary = write_staging(source)
        _print_summary(summary)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--list",
        metavar="PIPELINE_ID",
        dest="list_pipeline",
        help="print raw (unfiltered) tag names for one source and exit",
    )
    parser.add_argument(
        "pipelines",
        nargs="*",
        help=f"pipeline ids to fetch (default: all registered: {', '.join(REGISTERED_PIPELINES)})",
    )
    args = parser.parse_args(argv)
    token = os.environ.get("GITHUB_TOKEN")

    try:
        if args.list_pipeline:
            return _run_list(args.list_pipeline, token)
        targets = args.pipelines or list(REGISTERED_PIPELINES)
        return _run_fetch(targets, token)
    except FetcherError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
