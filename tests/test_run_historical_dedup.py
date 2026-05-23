"""ADR-0020: pre-dedup against corpus before scoring in run_historical.

Routed papers already present in the target daily bucket (by v2.identity_key)
must be dropped BEFORE llm_scorer.score_batch is called, not at write time.
First-seen-wins at write time is retained as a safety net for papers that
slip through (e.g. duplicates within a single novel batch).
"""
from __future__ import annotations

import json
import pathlib
import sys

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from pipeline import run_historical as rh  # noqa: E402
from pipeline import v2_schema as v2  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _paper(doi: str = "", arxiv_id: str = "", date: str = "2024-03-15",
           title: str = "AI bioprinting bioink study",
           source: str = "openalex") -> dict:
    return {
        "source": source,
        "id": doi or arxiv_id or "noid",
        "doi": doi,
        "arxiv_id": arxiv_id,
        "title": title,
        "abstract": "AI bioprinting bioink optimization study",
        "authors": ["A. Author"],
        "first_author_affiliation": "",
        "corresponding_authors": [],
        "venue": "V",
        "year": int(date[:4]),
        "date": date,
        "url": f"https://example.org/{doi or arxiv_id}",
        "cited_by_count": 0,
        "concepts": [],
        "categories": [],
    }


def _mock_fetchers(monkeypatch, openalex_papers: list[dict]):
    monkeypatch.setattr(rh.arxiv_fetcher, "fetch", lambda **kw: [])
    monkeypatch.setattr(rh.openalex_fetcher, "fetch",
                        lambda **kw: list(openalex_papers))
    monkeypatch.setattr(rh.pubmed_fetcher, "fetch", lambda **kw: [])


def _seed_bucket(daily_dir: pathlib.Path, date: str, papers: list[dict]):
    """Write a v2 bucket file containing the given papers, mimicking the
    on-disk shape so identity_key lookups succeed."""
    daily_dir.mkdir(parents=True, exist_ok=True)
    seeded = []
    for p in papers:
        q = dict(p)
        q["schema_version"] = "v2"
        q["date_precision"] = v2.infer_date_precision(date)
        q["scorer_version"] = "v3"
        q["first_seen_at"] = "2024-01-01T00:00:00Z"
        seeded.append(q)
    v2.atomic_write_json(
        daily_dir / f"{date}.json", v2.build_v2_file(date, seeded)
    )


# ---------------------------------------------------------------------------
# 1. routed paper already in corpus is dropped BEFORE scoring
# ---------------------------------------------------------------------------

def test_existing_corpus_paper_is_dropped_before_scoring(monkeypatch, tmp_path):
    bucket_date = "2024-03-10"
    existing = _paper(doi="10.1/existing", date=bucket_date)
    novel = _paper(doi="10.1/new", date=bucket_date)
    _seed_bucket(tmp_path / "daily", bucket_date, [existing])
    _mock_fetchers(monkeypatch, [existing, novel])

    seen_routed: list[list[dict]] = []

    def fake_score(routed, dirs):
        seen_routed.append(list(routed))
        return list(routed), []
    monkeypatch.setattr(rh.llm_scorer, "score_batch", fake_score)

    output_dir = tmp_path / "historical"
    output_dir.mkdir()
    rh.run(from_date=bucket_date, to_date=bucket_date,
           dry_run=False, output_dir=output_dir, data_root=tmp_path,
           no_resume=True)

    assert len(seen_routed) == 1
    dois = {p["doi"] for p in seen_routed[0]}
    assert dois == {"10.1/new"}


# ---------------------------------------------------------------------------
# 2. routed paper NOT in corpus is scored and written
# ---------------------------------------------------------------------------

def test_novel_paper_is_scored_and_written(monkeypatch, tmp_path):
    bucket_date = "2024-03-10"
    novel = _paper(doi="10.1/new", date=bucket_date)
    _mock_fetchers(monkeypatch, [novel])
    monkeypatch.setattr(rh.llm_scorer, "score_batch",
                        lambda routed, dirs: (list(routed), []))

    output_dir = tmp_path / "historical"
    output_dir.mkdir()
    rh.run(from_date=bucket_date, to_date=bucket_date,
           dry_run=False, output_dir=output_dir, data_root=tmp_path,
           no_resume=True)

    bucket = json.loads((tmp_path / "daily" / f"{bucket_date}.json").read_text())
    assert {p["doi"] for p in bucket["papers"]} == {"10.1/new"}


# ---------------------------------------------------------------------------
# 3. routed paper with empty identity_key is ALWAYS scored
# ---------------------------------------------------------------------------

def test_paper_with_empty_identity_key_is_always_scored(monkeypatch, tmp_path):
    bucket_date = "2024-03-10"
    # No DOI, no arxiv_id -> identity_key returns "".
    no_id = _paper(doi="", arxiv_id="", date=bucket_date)
    no_id["id"] = "anything"
    # Seed the bucket so the corpus has something, just to be safe — the
    # no-key paper must not be deduped against any existing entry.
    seeded = _paper(doi="10.1/seeded", date=bucket_date)
    _seed_bucket(tmp_path / "daily", bucket_date, [seeded])

    _mock_fetchers(monkeypatch, [no_id])
    assert v2.identity_key(no_id) == ""

    seen_routed: list[list[dict]] = []

    def fake_score(routed, dirs):
        seen_routed.append(list(routed))
        return list(routed), []
    monkeypatch.setattr(rh.llm_scorer, "score_batch", fake_score)

    output_dir = tmp_path / "historical"
    output_dir.mkdir()
    rh.run(from_date=bucket_date, to_date=bucket_date,
           dry_run=False, output_dir=output_dir, data_root=tmp_path,
           no_resume=True)

    assert len(seen_routed) == 1
    # The no-identity paper survives pre-dedup and is scored.
    assert len(seen_routed[0]) == 1


# ---------------------------------------------------------------------------
# 4. dry_run path does not pre-dedup and does not call score_batch
# ---------------------------------------------------------------------------

def test_dry_run_does_not_predupe_or_score(monkeypatch, tmp_path):
    bucket_date = "2024-03-10"
    existing = _paper(doi="10.1/existing", date=bucket_date)
    _seed_bucket(tmp_path / "daily", bucket_date, [existing])
    _mock_fetchers(monkeypatch, [existing, _paper(doi="10.1/new",
                                                   date=bucket_date)])

    called = {"score_batch": 0}

    def fake_score(routed, dirs):
        called["score_batch"] += 1
        return list(routed), []
    monkeypatch.setattr(rh.llm_scorer, "score_batch", fake_score)

    output_dir = tmp_path / "historical"
    output_dir.mkdir()
    rh.run(from_date=bucket_date, to_date=bucket_date,
           dry_run=True, output_dir=output_dir, data_root=tmp_path,
           no_resume=True)

    # Dry-run never reaches the scorer.
    assert called["score_batch"] == 0

    # And dry-run does not record any skipped_existing (it skipped the whole
    # pre-dedup block); after_routing reports the FULL routed count.
    p = json.loads((output_dir / "_progress.json").read_text())
    counts = p["months"]["2024-03"]["counts"]
    assert counts["after_routing"] == 2
    assert counts["skipped_existing"] == 0


# ---------------------------------------------------------------------------
# 5. skipped_existing is correct and surfaced in the month-summary dict
# ---------------------------------------------------------------------------

def test_skipped_existing_count_surfaced_in_progress(monkeypatch, tmp_path):
    bucket_date = "2024-03-10"
    e1 = _paper(doi="10.1/old1", date=bucket_date)
    e2 = _paper(doi="10.1/old2", date=bucket_date)
    n1 = _paper(doi="10.1/new1", date=bucket_date)
    _seed_bucket(tmp_path / "daily", bucket_date, [e1, e2])
    _mock_fetchers(monkeypatch, [e1, e2, n1])

    monkeypatch.setattr(rh.llm_scorer, "score_batch",
                        lambda routed, dirs: (list(routed), []))

    output_dir = tmp_path / "historical"
    output_dir.mkdir()
    rh.run(from_date=bucket_date, to_date=bucket_date,
           dry_run=False, output_dir=output_dir, data_root=tmp_path,
           no_resume=True)

    p = json.loads((output_dir / "_progress.json").read_text())
    counts = p["months"]["2024-03"]["counts"]
    # after_routing stays the full routed count (existing reporting unchanged).
    assert counts["after_routing"] == 3
    assert counts["skipped_existing"] == 2
    assert counts["scored"] == 1


# ---------------------------------------------------------------------------
# 6. first-seen-wins still drops a duplicate that slips through pre-dedup
# ---------------------------------------------------------------------------

def test_first_seen_wins_dedups_within_a_single_novel_batch(
    monkeypatch, tmp_path
):
    """Two routed papers with the same identity_key, neither yet in the
    corpus, both survive pre-dedup. The write-time first-seen-wins must still
    write only one row to the bucket."""
    bucket_date = "2024-03-10"
    p1 = _paper(doi="10.1/dup", date=bucket_date, title="dup A")
    p2 = _paper(doi="10.1/dup", date=bucket_date, title="dup B")
    # Source-distinct so within-run dedup in _run_month doesn't collapse them
    # before pre-dedup. _dedup_key would normally collapse them; we need to
    # actually exercise the write-time first-seen-wins. Use the openalex
    # mock returning both; within-run dedup uses a dict keyed on _dedup_key,
    # so duplicates with the same DOI ARE collapsed pre-routing. To exercise
    # the write-time guard, monkeypatch _dedup_key to a uniquifying key so
    # both papers reach routing/pre-dedup/scoring, then collide at write.
    counter = {"n": 0}

    def uniq_key(paper):
        counter["n"] += 1
        return f"uniq:{counter['n']}"
    monkeypatch.setattr(rh, "_dedup_key", uniq_key)

    _mock_fetchers(monkeypatch, [p1, p2])
    monkeypatch.setattr(rh.llm_scorer, "score_batch",
                        lambda routed, dirs: (list(routed), []))

    output_dir = tmp_path / "historical"
    output_dir.mkdir()
    rh.run(from_date=bucket_date, to_date=bucket_date,
           dry_run=False, output_dir=output_dir, data_root=tmp_path,
           no_resume=True)

    bucket = json.loads((tmp_path / "daily" / f"{bucket_date}.json").read_text())
    # Both made it past pre-dedup (neither was in the empty corpus), but
    # first-seen-wins at write time keeps only the first.
    assert len(bucket["papers"]) == 1
    assert bucket["papers"][0]["doi"] == "10.1/dup"
