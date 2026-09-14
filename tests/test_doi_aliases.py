"""ADR-0031: Zenodo concept-DOI resolution with an on-disk cache.

Run with:
    pytest tests/test_doi_aliases.py
"""
from __future__ import annotations

import json
import pathlib
import sys

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from pipeline import doi_aliases  # noqa: E402


class _Resp:
    def __init__(self, status=200, payload=None, boom=False):
        self.status_code = status
        self._payload = payload or {}
        self._boom = boom

    def json(self):
        if self._boom:
            raise ValueError("bad json")
        return self._payload


def _zenodo_api(records: dict, calls: list, *, fail_after: int | None = None):
    """records: recid -> (status, payload). Records every requested recid."""
    def get(url, timeout=None, headers=None):
        recid = url.rstrip("/").rsplit("/", 1)[-1]
        calls.append(recid)
        if fail_after is not None and len(calls) > fail_after:
            raise ConnectionError("zenodo down")
        status, payload = records.get(recid, (404, {}))
        return _Resp(status, payload)
    return get


class _Session:
    def __init__(self, get):
        self.get = get


def test_version_and_concept_records_map_to_the_concept_doi(tmp_path):
    # Live behaviour observed 2026-09-14: GET /records/22057603 (concept)
    # and /records/22057604 (version) both return conceptdoi ...22057603.
    payload = {"doi": "10.5281/zenodo.22057604",
               "conceptdoi": "10.5281/zenodo.22057603", "conceptrecid": "22057603"}
    calls: list = []
    session = _Session(_zenodo_api({"22057603": (200, payload),
                                    "22057604": (200, payload)}, calls))
    cache = tmp_path / "doi_aliases.json"

    aliases, report = doi_aliases.resolve_zenodo(
        ["10.5281/zenodo.22057604", "https://doi.org/10.5281/zenodo.22057603",
         "10.1016/j.not.zenodo", None, ""],
        cache, pause=0, session=session)

    assert aliases["10.5281/zenodo.22057604"] == "10.5281/zenodo.22057603"
    assert aliases["10.5281/zenodo.22057603"] == "10.5281/zenodo.22057603"
    assert report == {"looked_up": 1, "resolved": 1, "failed": 0, "skipped_cap": 0}
    # One lookup resolved both DOIs (the API echoes the version DOI), and
    # the non-Zenodo DOI was never queried.
    assert calls == ["22057604"]
    saved = json.loads(cache.read_text(encoding="utf-8"))
    assert saved["schema_version"] == 1
    assert saved["zenodo"] == aliases


def test_cached_dois_are_not_looked_up_again(tmp_path):
    cache = tmp_path / "doi_aliases.json"
    doi_aliases.save(cache, {"zenodo": {"10.5281/zenodo.1": "10.5281/zenodo.0"}})
    calls: list = []
    session = _Session(_zenodo_api({}, calls))

    aliases, report = doi_aliases.resolve_zenodo(["10.5281/zenodo.1"], cache,
                                                 pause=0, session=session)

    assert calls == []
    assert report["looked_up"] == 0
    assert aliases == {"10.5281/zenodo.1": "10.5281/zenodo.0"}


def test_network_failure_stops_early_and_caches_nothing(tmp_path):
    cache = tmp_path / "doi_aliases.json"
    calls: list = []
    session = _Session(_zenodo_api({}, calls, fail_after=0))

    aliases, report = doi_aliases.resolve_zenodo(
        ["10.5281/zenodo.1", "10.5281/zenodo.2"], cache, pause=0, session=session)

    assert calls == ["1"]  # stopped after the first failure
    assert report["failed"] == 1 and report["resolved"] == 0
    assert aliases == {}
    assert not cache.exists()


def test_withdrawn_record_maps_to_itself(tmp_path):
    cache = tmp_path / "doi_aliases.json"
    calls: list = []
    session = _Session(_zenodo_api({"5": (404, {})}, calls))

    aliases, report = doi_aliases.resolve_zenodo(["10.5281/zenodo.5"], cache,
                                                 pause=0, session=session)

    assert aliases == {"10.5281/zenodo.5": "10.5281/zenodo.5"}
    assert report["resolved"] == 1


def test_lookup_cap_is_respected(tmp_path):
    cache = tmp_path / "doi_aliases.json"
    calls: list = []
    payload = {"doi": "x", "conceptdoi": ""}
    session = _Session(_zenodo_api({str(i): (200, payload) for i in range(10)}, calls))

    _aliases, report = doi_aliases.resolve_zenodo(
        [f"10.5281/zenodo.{i}" for i in range(10)], cache,
        pause=0, max_lookups=3, session=session)

    assert len(calls) == 3
    assert report["skipped_cap"] == 7


def test_record_without_conceptdoi_maps_to_itself(tmp_path):
    cache = tmp_path / "doi_aliases.json"
    session = _Session(_zenodo_api({"7": (200, {"doi": "10.5281/zenodo.7"})}, []))
    aliases, _ = doi_aliases.resolve_zenodo(["10.5281/zenodo.7"], cache,
                                            pause=0, session=session)
    assert aliases == {"10.5281/zenodo.7": "10.5281/zenodo.7"}


def test_load_tolerates_missing_or_corrupt_cache(tmp_path):
    assert doi_aliases.load(tmp_path / "missing.json") == {"schema_version": 1, "zenodo": {}}
    bad = tmp_path / "bad.json"
    bad.write_text("{oops", encoding="utf-8")
    assert doi_aliases.flat(doi_aliases.load(bad)) == {}
