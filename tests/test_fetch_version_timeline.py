"""Tests for scripts/fetch_version_timeline.py — all GitHub I/O is mocked.

No network: ``_request_json`` is monkeypatched with a URL->response map, and the
HTTP-layer tests drive a fake ``urllib.request.urlopen``. Covers tag filtering,
prerelease exclusion, the full date fallback chain (release -> annotated tag ->
lightweight commit -> none => NEEDS_VERIFICATION), verbatim version strings, and
two-page pagination.
"""

from __future__ import annotations

import email.message
import re
import urllib.error
from typing import Any

import pytest

import fetch_version_timeline as fvt

_API = fvt._GITHUB_API
_OWNER = "acme"
_REPO = "tool"
_REPO_API = f"{_API}/repos/{_OWNER}/{_REPO}"


def _tag(name: str, sha: str) -> dict[str, Any]:
    return {"name": name, "commit": {"sha": sha}}


class _FakeHttp:
    """Stand-in for ``_request_json``: maps exact URL -> (payload, headers).

    Unmapped URLs return ``(None, {})`` — i.e. a 404-like "not found" signal,
    which is exactly how "no published release for this tag" looks.
    """

    def __init__(self, responses: dict[str, tuple[Any, dict[str, str]]]):
        self.responses = responses
        self.calls: list[str] = []

    def __call__(self, url: str, token: str | None) -> tuple[Any, dict[str, str]]:
        self.calls.append(url)
        return self.responses.get(url, (None, {}))


def _source(tag_filter: str, include_prereleases: bool = False) -> fvt.GitHubTagSource:
    return fvt.GitHubTagSource(
        _OWNER,
        _REPO,
        re.compile(tag_filter),
        include_prereleases=include_prereleases,
        token=None,
        pipeline_id="tool",
    )


# --- _parse_next_link -------------------------------------------------------


def test_parse_next_link_extracts_next_url():
    header = f'<{_REPO_API}/tags?per_page=100&page=2>; rel="next", <...&page=5>; rel="last"'
    assert fvt._parse_next_link(header) == f"{_REPO_API}/tags?per_page=100&page=2"


def test_parse_next_link_none_when_no_next():
    assert fvt._parse_next_link('<...&page=1>; rel="prev"') is None
    assert fvt._parse_next_link("") is None


# --- tag filtering + prerelease exclusion -----------------------------------


def test_tag_filter_excludes_non_matching_names(monkeypatch):
    fake = _FakeHttp(
        {
            f"{_REPO_API}/tags?per_page=100": (
                [_tag("v1.0.0", "sha1"), _tag("nightly", "sha2"), _tag("random-tag", "sha3")],
                {},
            ),
            f"{_REPO_API}/releases/tags/v1.0.0": ({"published_at": "2020-01-01T00:00:00Z"}, {}),
        }
    )
    monkeypatch.setattr(fvt, "_request_json", fake)
    versions = list(_source(r"^v\d+\.\d+\.\d+$").iter_versions())
    assert [v.version for v in versions] == ["v1.0.0"]


def test_prereleases_excluded_by_default_but_kept_when_requested(monkeypatch):
    tags = [_tag("v1.0.0", "s1"), _tag("v1.1.0rc1", "s2"), _tag("v1.2.0b2", "s3")]
    responses: dict[str, Any] = {f"{_REPO_API}/tags?per_page=100": (tags, {})}
    # Give each tag a published release so dates resolve cleanly.
    for name in ("v1.0.0", "v1.1.0rc1", "v1.2.0b2"):
        responses[f"{_REPO_API}/releases/tags/{name}"] = (
            {"published_at": "2021-05-05T12:00:00Z"},
            {},
        )
    monkeypatch.setattr(fvt, "_request_json", _FakeHttp(responses))

    # Loose filter so prereleases pass the filter and the prerelease guard is what drops them.
    default = list(_source(r"^v\d+\.\d+\.\d+").iter_versions())
    assert [v.version for v in default] == ["v1.0.0"]

    monkeypatch.setattr(fvt, "_request_json", _FakeHttp(responses))
    allp = list(_source(r"^v\d+\.\d+\.\d+", include_prereleases=True).iter_versions())
    assert [v.version for v in allp] == ["v1.0.0", "v1.1.0rc1", "v1.2.0b2"]


# --- date fallback chain ----------------------------------------------------


def test_date_from_published_release(monkeypatch):
    fake = _FakeHttp(
        {
            f"{_REPO_API}/tags?per_page=100": ([_tag("v1.0.0", "sha1")], {}),
            f"{_REPO_API}/releases/tags/v1.0.0": (
                {"published_at": "2020-02-12T19:57:44Z"},
                {},
            ),
        }
    )
    monkeypatch.setattr(fvt, "_request_json", fake)
    (record,) = list(_source(r"^v\d+\.\d+\.\d+$").iter_versions())
    assert record.release_date == "2020-02-12"
    assert record.release_source == f"https://github.com/{_OWNER}/{_REPO}/releases/tag/v1.0.0"


def test_date_falls_back_to_annotated_tagger_date(monkeypatch):
    fake = _FakeHttp(
        {
            f"{_REPO_API}/tags?per_page=100": ([_tag("v2.0.0", "peeledsha")], {}),
            # no release (unmapped -> None)
            f"{_REPO_API}/git/ref/tags/v2.0.0": (
                {"object": {"type": "tag", "sha": "annsha"}},
                {},
            ),
            f"{_REPO_API}/git/tags/annsha": (
                {"tagger": {"date": "2016-08-09T10:00:00Z"}},
                {},
            ),
        }
    )
    monkeypatch.setattr(fvt, "_request_json", fake)
    (record,) = list(_source(r"^v\d+\.\d+\.\d+$").iter_versions())
    assert record.release_date == "2016-08-09"
    # No published release -> tree/ source URL.
    assert record.release_source == f"https://github.com/{_OWNER}/{_REPO}/tree/v2.0.0"


def test_date_falls_back_to_lightweight_commit_date(monkeypatch):
    fake = _FakeHttp(
        {
            f"{_REPO_API}/tags?per_page=100": ([_tag("v3.0.0", "commitsha")], {}),
            f"{_REPO_API}/git/ref/tags/v3.0.0": (
                {"object": {"type": "commit", "sha": "commitsha"}},
                {},
            ),
            f"{_REPO_API}/commits/commitsha": (
                {"commit": {"committer": {"date": "2014-09-10T21:34:16Z"}}},
                {},
            ),
        }
    )
    monkeypatch.setattr(fvt, "_request_json", fake)
    (record,) = list(_source(r"^v\d+\.\d+\.\d+$").iter_versions())
    assert record.release_date == "2014-09-10"


def test_date_unresolved_yields_none_then_needs_verification(monkeypatch, tmp_path):
    fake = _FakeHttp(
        {
            f"{_REPO_API}/tags?per_page=100": ([_tag("v4.0.0", "sha")], {}),
            # no release, no ref, no commit -> all unmapped -> None
        }
    )
    monkeypatch.setattr(fvt, "_request_json", fake)
    source = _source(r"^v\d+\.\d+\.\d+$")
    (record,) = list(source.iter_versions())
    assert record.release_date is None

    summary = fvt.write_staging(source, staging_dir=tmp_path)
    assert summary.needs_verification == 1
    text = (tmp_path / "tool.versions.yaml").read_text(encoding="utf-8")
    assert "NEEDS_VERIFICATION" in text


# --- verbatim version strings -----------------------------------------------


def test_version_strings_are_verbatim_no_normalization(monkeypatch):
    tags = [_tag("v4.1.3", "s1"), _tag("23.2.0", "s2")]
    responses: dict[str, Any] = {f"{_REPO_API}/tags?per_page=100": (tags, {})}
    for name in ("v4.1.3", "23.2.0"):
        responses[f"{_REPO_API}/releases/tags/{name}"] = (
            {"published_at": "2020-02-12T00:00:00Z"},
            {},
        )
    monkeypatch.setattr(fvt, "_request_json", _FakeHttp(responses))
    # Filter accepts both an optional-v and bare numeric scheme.
    versions = list(_source(r"^v?\d+\.\d+\.\d+$").iter_versions())
    assert {v.version for v in versions} == {"v4.1.3", "23.2.0"}


# --- pagination -------------------------------------------------------------


def test_pagination_follows_link_rel_next(monkeypatch):
    page1 = f"{_REPO_API}/tags?per_page=100"
    page2 = f"{_REPO_API}/tags?per_page=100&page=2"
    fake = _FakeHttp(
        {
            page1: ([_tag("v1.0.0", "s1")], {"Link": f'<{page2}>; rel="next"'}),
            page2: ([_tag("v2.0.0", "s2")], {}),
            f"{_REPO_API}/releases/tags/v1.0.0": ({"published_at": "2019-01-01T00:00:00Z"}, {}),
            f"{_REPO_API}/releases/tags/v2.0.0": ({"published_at": "2020-01-01T00:00:00Z"}, {}),
        }
    )
    monkeypatch.setattr(fvt, "_request_json", fake)
    versions = list(_source(r"^v\d+\.\d+\.\d+$").iter_versions())
    assert [v.version for v in versions] == ["v1.0.0", "v2.0.0"]
    assert page1 in fake.calls and page2 in fake.calls


def test_iter_raw_tag_names_unfiltered(monkeypatch):
    fake = _FakeHttp(
        {f"{_REPO_API}/tags?per_page=100": ([_tag("v1.0.0", "s1"), _tag("nightly", "s2")], {})}
    )
    monkeypatch.setattr(fvt, "_request_json", fake)
    assert list(_source(r"^v\d+\.\d+\.\d+$").iter_raw_tag_names()) == ["v1.0.0", "nightly"]


# --- staging output + validation + sorting ----------------------------------


def test_write_staging_sorts_by_date_with_unknown_last(monkeypatch, tmp_path):
    tags = [_tag("v2.0.0", "s2"), _tag("v1.0.0", "s1"), _tag("v3.0.0", "s3")]
    responses: dict[str, Any] = {f"{_REPO_API}/tags?per_page=100": (tags, {})}
    responses[f"{_REPO_API}/releases/tags/v2.0.0"] = ({"published_at": "2020-06-01T00:00:00Z"}, {})
    responses[f"{_REPO_API}/releases/tags/v1.0.0"] = ({"published_at": "2018-01-01T00:00:00Z"}, {})
    # v3.0.0: no date anywhere -> NEEDS_VERIFICATION, sorts last.
    monkeypatch.setattr(fvt, "_request_json", _FakeHttp(responses))

    summary = fvt.write_staging(_source(r"^v\d+\.\d+\.\d+$"), staging_dir=tmp_path)
    assert summary.count == 3
    assert summary.earliest == "2018-01-01"
    assert summary.latest == "2020-06-01"
    assert summary.needs_verification == 1

    import yaml

    doc = yaml.safe_load((tmp_path / "tool.versions.yaml").read_text(encoding="utf-8"))
    order = [v["version"] for v in doc["versions"]]
    assert order == ["v1.0.0", "v2.0.0", "v3.0.0"]
    assert doc["versions"][-1]["release_date"] == "NEEDS_VERIFICATION"
    # param_defaults omitted (optional; Bucket 1 only).
    assert "param_defaults" not in doc["versions"][0]


def test_validation_rejects_missing_required_field(monkeypatch, tmp_path):
    """A record missing a required field (release_source) must fail loudly."""
    strict, relaxed = fvt._build_validators()
    bad = {"version": "v1.0.0", "release_date": "2020-01-01"}  # no release_source
    with pytest.raises(fvt.FetcherError, match="schema validation"):
        fvt._validate_entry(bad, strict, relaxed)


def test_validation_rejects_non_sentinel_bad_date(monkeypatch):
    """A resolved-date row routes to the strict validator, where format:date is
    enforced — a non-date, non-sentinel string is rejected (not silently kept)."""
    strict, relaxed = fvt._build_validators()
    bad = {
        "version": "v1.0.0",
        "release_date": "sometime-2020",
        "release_source": "https://github.com/acme/tool/releases/tag/v1.0.0",
    }
    with pytest.raises(fvt.FetcherError, match="schema validation"):
        fvt._validate_entry(bad, strict, relaxed)


def test_relaxed_validator_accepts_needs_verification_date():
    strict, relaxed = fvt._build_validators()
    entry = {
        "version": "v1.0.0",
        "release_date": "NEEDS_VERIFICATION",
        "release_source": "https://github.com/acme/tool/tree/v1.0.0",
    }
    # Must not raise.
    fvt._validate_entry(entry, strict, relaxed)


# --- HTTP error mapping (_request_json) -------------------------------------


class _FakeResp:
    def __init__(self, body: bytes, headers: dict[str, str]):
        self._body = body
        msg = email.message.Message()
        for k, v in headers.items():
            msg[k] = v
        self.headers = msg

    def read(self) -> bytes:
        return self._body

    def __enter__(self) -> _FakeResp:
        return self

    def __exit__(self, *exc: object) -> None:
        return None


def _http_error(code: int, headers: dict[str, str]) -> urllib.error.HTTPError:
    msg = email.message.Message()
    for k, v in headers.items():
        msg[k] = v
    return urllib.error.HTTPError("http://x", code, "boom", msg, None)


def test_request_json_404_returns_none(monkeypatch):
    def fake_urlopen(req, timeout=0):
        raise _http_error(404, {})

    monkeypatch.setattr(fvt.urllib.request, "urlopen", fake_urlopen)
    payload, _ = fvt._request_json("http://x", token=None)
    assert payload is None


def test_request_json_403_rate_limit_fails_loudly(monkeypatch):
    def fake_urlopen(req, timeout=0):
        raise _http_error(403, {"X-RateLimit-Remaining": "0"})

    monkeypatch.setattr(fvt.urllib.request, "urlopen", fake_urlopen)
    with pytest.raises(fvt.RateLimitError, match="rate limit"):
        fvt._request_json("http://x", token=None)


def test_request_json_success_returns_payload_and_headers(monkeypatch):
    import json as _json

    def fake_urlopen(req, timeout=0):
        return _FakeResp(_json.dumps([{"name": "v1.0.0"}]).encode(), {"Link": "next-ish"})

    monkeypatch.setattr(fvt.urllib.request, "urlopen", fake_urlopen)
    payload, headers = fvt._request_json("http://x", token=None)
    assert payload == [{"name": "v1.0.0"}]
    assert headers["Link"] == "next-ish"


def test_request_json_sends_bearer_when_token_present(monkeypatch):
    captured: dict[str, Any] = {}

    def fake_urlopen(req, timeout=0):
        captured["auth"] = req.get_header("Authorization")
        import json as _json

        return _FakeResp(_json.dumps({}).encode(), {})

    monkeypatch.setattr(fvt.urllib.request, "urlopen", fake_urlopen)
    fvt._request_json("http://x", token="secrettoken")
    assert captured["auth"] == "Bearer secrettoken"


# --- registry + stubs -------------------------------------------------------


def test_build_source_unknown_pipeline_raises():
    with pytest.raises(fvt.FetcherError, match="no registered source"):
        fvt.build_source("not_a_pipeline")


def test_registered_sources_have_expected_repos():
    assert isinstance(fvt.build_source("hcp_minimal"), fvt.GitHubTagSource)
    hcp = fvt.build_source("hcp_minimal")
    assert isinstance(hcp, fvt.GitHubTagSource)
    assert (hcp.owner, hcp.repo) == ("Washington-University", "HCPpipelines")
    fmriprep = fvt.build_source("fmriprep")
    assert isinstance(fmriprep, fvt.GitHubTagSource)
    assert (fmriprep.owner, fmriprep.repo) == ("nipreps", "fmriprep")
    ccs = fvt.build_source("ccs")
    assert isinstance(ccs, fvt.GitHubTagSource)
    assert (ccs.owner, ccs.repo) == ("zuoxinian", "CCS")


@pytest.mark.parametrize(
    "cls", [fvt.SpmReleaseNotesSource, fvt.FslReleaseSource, fvt.FreeSurferReleaseSource]
)
def test_stub_sources_raise_not_implemented(cls):
    with pytest.raises(NotImplementedError):
        list(cls().iter_versions())
