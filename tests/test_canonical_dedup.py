"""ADR-0031 end-to-end: canonical identity in the aggregator, the on-disk
merge, the public corpus view and the OpenAlex normalizer.

Run with:
    pytest tests/test_canonical_dedup.py
"""
from __future__ import annotations

import json
import pathlib
import sys

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from fetchers import openalex_fetcher  # noqa: E402
from pipeline import aggregator  # noqa: E402
from pipeline import run_daily as rd  # noqa: E402
from render import corpus_view  # noqa: E402


def _paper(source: str, *, doi: str = "", arxiv_id: str = "", pmid: str = "",
           oa_id: str = "", title: str = "bioprinting bioink study",
           abstract: str = "AI bioprinting bioink optimization study",
           date: str = "2026-09-01") -> dict:
    ident = oa_id or (f"pubmed:{pmid}" if pmid else (arxiv_id or doi or title))
    paper = {
        "source": source, "id": ident, "doi": doi, "title": title,
        "abstract": abstract, "authors": ["A. Author"],
        "first_author_affiliation": "", "corresponding_authors": [],
        "venue": "V", "year": 2026, "date": date,
        "url": f"https://doi.org/{doi}" if doi else ident,
        "cited_by_count": 0, "concepts": [], "categories": [],
    }
    if arxiv_id:
        paper["arxiv_id"] = arxiv_id
    if pmid:
        paper["pmid"] = pmid
    return paper


# ---------------------------------------------------------------------------
# aggregator
# ---------------------------------------------------------------------------

def test_openalex_copy_of_arxiv_preprint_is_one_paper_and_arxiv_record_wins():
    arxiv = _paper("arxiv", arxiv_id="2609.00965v1")
    copy = _paper("openalex", arxiv_id="2609.00965", abstract="",
                  oa_id="https://openalex.org/W7207880362")
    papers, keys = aggregator.aggregate([[arxiv], [copy]])
    assert len(papers) == 1
    assert papers[0]["source"] == "arxiv"
    assert papers[0]["also_seen_in"] == "openalex"
    assert keys == {"arxiv:2609.00965"}


def test_published_version_with_doi_supersedes_arxiv_record():
    arxiv = _paper("arxiv", doi="10.1038/s41524-026-02226-3", arxiv_id="2601.06820v1")
    journal = _paper("openalex", doi="10.1038/S41524-026-02226-3",
                     oa_id="https://openalex.org/W1")
    papers, keys = aggregator.aggregate([[arxiv], [journal]])
    assert len(papers) == 1
    assert papers[0]["source"] == "openalex"
    assert papers[0]["also_seen_in"] == "arxiv"
    assert keys == {"doi:10.1038/s41524-026-02226-3"}


def test_zenodo_pair_collapses_with_aliases_but_not_without():
    aliases = {"10.5281/zenodo.22057604": "10.5281/zenodo.22057603"}
    concept = _paper("openalex", doi="10.5281/zenodo.22057603", oa_id="https://openalex.org/W1")
    version = _paper("openalex", doi="10.5281/zenodo.22057604", oa_id="https://openalex.org/W2")
    with_aliases, _ = aggregator.aggregate([[concept, version]], aliases=aliases)
    without, _ = aggregator.aggregate([[concept, version]])
    assert len(with_aliases) == 1
    assert len(without) == 2


def test_pubmed_and_openalex_records_join_on_pmid_when_doi_is_missing():
    pm = _paper("pubmed", pmid="42709028")
    oa = _paper("openalex", pmid="42709028", oa_id="https://openalex.org/W9", abstract="")
    papers, keys = aggregator.aggregate([[pm], [oa]])
    assert len(papers) == 1 and keys == {"pmid:42709028"}


def test_legacy_seen_state_keys_still_suppress_refetch(tmp_path):
    # State written before ADR-0031 used `doi:<lower>` and `<source>:<id>`.
    state = tmp_path / "seen.json"
    state.write_text(json.dumps({"keys": [
        "doi:10.1/old", "arxiv:http://arxiv.org/abs/2601.00001v1",
    ]}), encoding="utf-8")
    old_doi = _paper("openalex", doi="10.1/OLD", oa_id="https://openalex.org/W3")
    old_arxiv = _paper("arxiv", arxiv_id="2601.00001v1")
    old_arxiv["id"] = "http://arxiv.org/abs/2601.00001v1"
    fresh = _paper("arxiv", arxiv_id="2601.00002v1")
    papers, keys = aggregator.aggregate([[old_doi, old_arxiv, fresh]], state)
    assert [p["arxiv_id"] for p in papers] == ["2601.00002v1"]
    assert "arxiv:2601.00002" in keys


def test_identity_less_records_keep_legacy_source_key():
    a = _paper("pubmed", title="No identifiers at all")
    a["id"] = "pubmed:"
    b = _paper("pubmed", title="No identifiers at all")
    b["id"] = "pubmed:"
    papers, _ = aggregator.aggregate([[a], [b]])
    assert len(papers) == 1  # same source:id -> same legacy key, as before


# ---------------------------------------------------------------------------
# corpus_view (public site)
# ---------------------------------------------------------------------------

def test_corpus_view_suppresses_zenodo_pair_and_keeps_first_seen_anchor():
    aliases = {"10.5281/zenodo.22057604": "10.5281/zenodo.22057603"}
    buckets = {
        "2026-08-22": [
            {"doi": "10.5281/zenodo.22057603", "first_seen_at": "2026-08-23T07:00:00Z",
             "title": "concept", "llm": {"priority": "Medium"}},
            {"doi": "10.5281/zenodo.22057604", "first_seen_at": "2026-08-23T07:00:00Z",
             "title": "version", "llm": {"priority": "Low"}},
        ],
    }
    visible, stats = corpus_view.canonicalize_buckets(buckets, aliases=aliases)
    assert [p["title"] for p in visible["2026-08-22"]] == ["concept"]
    assert stats.duplicates_suppressed == 1
    # The public identity of the survivor is untouched (anchors/marks stay valid).
    assert corpus_view.identity_key(visible["2026-08-22"][0]) == "doi:10.5281/zenodo.22057603"


def test_corpus_view_suppresses_openalex_copy_of_arxiv_record():
    buckets = {
        "2026-09-02": [
            {"source": "arxiv", "arxiv_id": "2609.00965v1", "title": "arxiv",
             "first_seen_at": "2026-09-03T07:00:00Z", "llm": {"priority": "High"}},
        ],
        "2026-09-05": [
            {"source": "openalex", "id": "https://openalex.org/W7207880362",
             "doi": "", "arxiv_id": "2609.00965", "title": "copy",
             "first_seen_at": "2026-09-06T07:00:00Z", "llm": {"priority": "Low"}},
        ],
    }
    visible, stats = corpus_view.canonicalize_buckets(buckets)
    assert [p["title"] for p in visible["2026-09-02"]] == ["arxiv"]
    assert visible["2026-09-05"] == []
    assert stats.priority_counts["High"] == 1 and stats.priority_counts["Low"] == 0


def test_corpus_view_still_never_merges_identity_less_records():
    buckets = {
        "2026-01-01": [{"source": "pubmed", "title": "Same title"}],
        "2026-02-01": [{"source": "pubmed", "title": "Same title"}],
    }
    visible, stats = corpus_view.canonicalize_buckets(buckets)
    assert sum(len(v) for v in visible.values()) == 2
    assert stats.duplicates_suppressed == 0


def test_corpus_view_case_variant_dois_are_one_paper():
    buckets = {
        "2026-03-01": [{"doi": "10.1016/J.X.1", "title": "upper", "first_seen_at": "2026-03-02T00:00:00Z"}],
        "2026-03-03": [{"doi": "10.1016/j.x.1", "title": "lower", "first_seen_at": "2026-03-04T00:00:00Z"}],
    }
    visible, stats = corpus_view.canonicalize_buckets(buckets)
    assert stats.duplicates_suppressed == 1
    assert [p["title"] for p in visible["2026-03-01"]] == ["upper"]


# ---------------------------------------------------------------------------
# run_daily on-disk merge
# ---------------------------------------------------------------------------

@pytest.fixture
def isolated_run(monkeypatch, tmp_path):
    data_dir = tmp_path / "data"
    docs_dir = tmp_path / "docs"
    (data_dir / "daily").mkdir(parents=True)
    docs_dir.mkdir()
    monkeypatch.setattr(rd, "DATA_DIR", data_dir)
    monkeypatch.setattr(rd, "DOCS_DIR", docs_dir)
    monkeypatch.setattr(rd, "SEEN_STATE", data_dir / "seen_dois.json")
    monkeypatch.setattr(rd, "MANIFESTS_DIR", data_dir / "manifests")
    monkeypatch.setattr(rd, "SNAPSHOTS_DIR", data_dir / "config_snapshots")
    monkeypatch.setattr(rd, "CHANGELOG", tmp_path / "CHANGELOG.md")
    monkeypatch.setattr(rd.llm_scorer, "score_batch", lambda routed, dirs: (routed, []))
    monkeypatch.setattr(rd.mf, "build_manifest", lambda **kw: {
        "run_id": "test-run", "git_commit": "deadbeef",
        "config": {"scorer_prompt": "test-hash"}})
    monkeypatch.setattr(rd.mf, "save_manifest", lambda *a, **kw: None)
    monkeypatch.setattr(rd.mf, "find_last_manifest", lambda *a, **kw: None)
    monkeypatch.setattr(rd.clu, "update_changelog", lambda **kw: False)
    monkeypatch.setattr(rd.clu, "save_config_snapshot", lambda *a, **kw: None)
    monkeypatch.setattr(rd.build_pages, "build", lambda *a, **kw: None)
    monkeypatch.setattr(rd.pubmed_fetcher, "fetch", lambda *a, **kw: [])
    return data_dir


def test_daily_merge_uses_zenodo_aliases_and_skips_the_version_copy(monkeypatch, isolated_run):
    aliases = {"10.5281/zenodo.22057604": "10.5281/zenodo.22057603"}
    calls: list = []

    def fake_resolve(dois, cache_path, **kw):
        calls.append((sorted(d for d in dois if d), pathlib.Path(cache_path)))
        return aliases, {"looked_up": 1, "resolved": 1, "failed": 0, "skipped_cap": 0}

    monkeypatch.setattr(rd.doi_aliases, "resolve_zenodo", fake_resolve)
    monkeypatch.setattr(rd.arxiv_fetcher, "fetch", lambda *a, **kw: [])
    monkeypatch.setattr(rd.openalex_fetcher, "fetch", lambda *a, **kw: [
        _paper("openalex", doi="10.5281/zenodo.22057603", oa_id="https://openalex.org/W1",
               date="2026-08-22"),
    ])
    rd.run(days_back=1, skip_zotero=True)

    # Second run sees the *version* DOI of the same upload.
    monkeypatch.setattr(rd.openalex_fetcher, "fetch", lambda *a, **kw: [
        _paper("openalex", doi="10.5281/zenodo.22057604", oa_id="https://openalex.org/W2",
               date="2026-08-22"),
    ])
    rd.run(days_back=1, skip_zotero=True, force=True)

    bucket = json.loads((isolated_run / "daily" / "2026-08-22.json").read_text(encoding="utf-8"))
    assert [p["doi"] for p in bucket["papers"]] == ["10.5281/zenodo.22057603"]
    assert calls[0][1] == isolated_run / "doi_aliases.json"
    assert "10.5281/zenodo.22057603" in calls[0][0]


def test_daily_merge_skips_openalex_copy_of_existing_arxiv_record(monkeypatch, isolated_run):
    monkeypatch.setattr(rd.doi_aliases, "resolve_zenodo",
                        lambda dois, path, **kw: ({}, {"looked_up": 0, "resolved": 0,
                                                       "failed": 0, "skipped_cap": 0}))
    monkeypatch.setattr(rd.openalex_fetcher, "fetch", lambda *a, **kw: [])
    monkeypatch.setattr(rd.arxiv_fetcher, "fetch", lambda *a, **kw: [
        _paper("arxiv", arxiv_id="2609.00965v1", date="2026-09-02"),
    ])
    rd.run(days_back=1, skip_zotero=True)

    monkeypatch.setattr(rd.arxiv_fetcher, "fetch", lambda *a, **kw: [])
    monkeypatch.setattr(rd.openalex_fetcher, "fetch", lambda *a, **kw: [
        _paper("openalex", arxiv_id="2609.00965", oa_id="https://openalex.org/W7207880362",
               date="2026-09-02"),
    ])
    rd.run(days_back=1, skip_zotero=True, force=True)

    bucket = json.loads((isolated_run / "daily" / "2026-09-02.json").read_text(encoding="utf-8"))
    assert [p["source"] for p in bucket["papers"]] == ["arxiv"]


def test_daily_run_survives_alias_resolver_failure(monkeypatch, isolated_run):
    def boom(*a, **kw):
        raise RuntimeError("zenodo exploded")

    monkeypatch.setattr(rd.doi_aliases, "resolve_zenodo", boom)
    monkeypatch.setattr(rd.arxiv_fetcher, "fetch", lambda *a, **kw: [_paper("arxiv", arxiv_id="2609.1v1")])
    monkeypatch.setattr(rd.openalex_fetcher, "fetch", lambda *a, **kw: [])
    report = rd.run(days_back=1, skip_zotero=True)
    assert report["run_status"] == "success"


# ---------------------------------------------------------------------------
# OpenAlex normalizer
# ---------------------------------------------------------------------------

def test_openalex_normalizer_exposes_arxiv_id_and_pmid():
    work = {
        "id": "https://openalex.org/W7207880362", "doi": None, "title": "t",
        "publication_year": 2026, "publication_date": "2026-09-02", "type": "preprint",
        "ids": {"openalex": "https://openalex.org/W7207880362",
                "pmid": "https://pubmed.ncbi.nlm.nih.gov/42709028"},
        "primary_location": {"landing_page_url": "https://arxiv.org/abs/2609.00965",
                             "pdf_url": "https://arxiv.org/pdf/2609.00965",
                             "source": {"display_name": "arXiv (Cornell University)"}},
        "locations": [],
    }
    paper = openalex_fetcher._normalize(work)
    assert paper["arxiv_id"] == "2609.00965"
    assert paper["pmid"] == "42709028"
    assert paper["doi"] == ""


def test_openalex_normalizer_without_ids_or_locations_is_unchanged():
    work = {"id": "https://openalex.org/W1", "doi": "https://doi.org/10.1/x",
            "title": "t", "publication_year": 2026, "publication_date": "2026-09-02"}
    paper = openalex_fetcher._normalize(work)
    assert paper["arxiv_id"] == "" and paper["pmid"] == ""
    assert paper["doi"] == "10.1/x"
