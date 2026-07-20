from __future__ import annotations

from render import corpus_view


def _paper(identity: str | None, priority: str, first_seen: str | None,
           *, title: str = "Paper") -> dict:
    paper = {
        "title": title,
        "first_seen_at": first_seen,
        "llm": {"priority": priority},
    }
    if identity:
        kind, value = identity.split(":", 1)
        paper["doi" if kind == "doi" else "arxiv_id"] = value
    return paper


def test_first_seen_record_wins_across_publication_buckets():
    buckets = {
        "2026-04-02": [
            _paper("doi:10.1/duplicate", "High", "2026-05-23T12:00:00Z",
                   title="Later observation"),
        ],
        "2026-03-23": [
            _paper("doi:10.1/duplicate", "High", "2026-05-16T05:00:00Z",
                   title="First observation"),
            _paper("arxiv:2603.1", "Medium", "2026-05-16T05:00:00Z"),
        ],
    }

    visible, stats = corpus_view.canonicalize_buckets(buckets)

    assert visible["2026-04-02"] == []
    assert [p["title"] for p in visible["2026-03-23"]] == [
        "First observation", "Paper"
    ]
    assert stats.raw_total == 3
    assert stats.unique_total == 2
    assert stats.duplicates_suppressed == 1
    assert stats.priority_counts == {
        "High": 1, "Medium": 1, "Low": 0, "Exclude": 0,
    }


def test_identity_less_records_are_never_fuzzy_deduplicated():
    buckets = {
        "2024-01-01": [_paper(None, "Low", None, title="Same title")],
        "2024-02-01": [_paper(None, "Low", None, title="Same title")],
    }

    visible, stats = corpus_view.canonicalize_buckets(buckets)

    assert sum(len(papers) for papers in visible.values()) == 2
    assert stats.duplicates_suppressed == 0


def test_legacy_record_without_timestamp_precedes_timestamped_duplicate():
    buckets = {
        "2020-01-01": [_paper("doi:10.1/legacy", "Low", None)],
        "2024-01-01": [
            _paper("doi:10.1/legacy", "High", "2026-05-20T00:00:00Z")
        ],
    }

    visible, _stats = corpus_view.canonicalize_buckets(buckets)

    assert len(visible["2020-01-01"]) == 1
    assert visible["2024-01-01"] == []
