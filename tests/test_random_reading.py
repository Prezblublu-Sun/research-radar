"""ADR-0035: read the journals that produced today's High papers.

Two properties matter more than the feature itself:

* **isolation** — a randomly drawn paper is not a radar recommendation. It
  must never reach `data/daily/`, the seen-state, the queue or Zotero, and
  it must never change the day's priority counts.
* **fail-soft** — serendipity is a nice-to-have bolted onto the run that
  produces the corpus. No OpenAlex outage, no malformed journal, nothing
  here may fail the daily run.

Run with:
    pytest tests/test_random_reading.py
"""
from __future__ import annotations

import json
import pathlib
import sys

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from fetchers import openalex_fetcher  # noqa: E402
from pipeline import random_reading as rr  # noqa: E402
from pipeline import run_daily as rd  # noqa: E402
from render import build_pages  # noqa: E402
from scripts import backfill_random_reading as bf  # noqa: E402

DIRECTIONS = {
    "fea_surrogate": {"display_name": "FEA & Surrogate", "color": "#D85A30",
                      "strong_keywords": ["finite element"]},
    "ai_bioprinting": {"display_name": "AI Bioprinting", "color": "#7F77DD",
                       "strong_keywords": ["bioprinting"]},
}


def _high(venue="Computational Mechanics", venue_id="S147854436",
          venue_type="journal", **extra):
    paper = {
        "llm": {"priority": "High"}, "venue": venue, "venue_id": venue_id,
        "venue_type": venue_type, "venue_issn_l": "0178-7675",
        "direction": "fea_surrogate", "title": "Seed paper",
        "doi": "10.1/seed", "source": "openalex",
    }
    paper.update(extra)
    return paper


class FakeOpenAlex:
    """A journal with `count` works, addressable by 1-based position."""

    PAGE_LIMIT = openalex_fetcher.PAGE_LIMIT

    def __init__(self, counts: dict, *, fail_count=False, fail_draw=False,
                 doi_at=None):
        self.counts = counts
        self.fail_count = fail_count
        self.fail_draw = fail_draw
        self.doi_at = doi_at or (lambda sid, pos: f"10.9/{sid}-{pos}")
        self.calls = []

    def journal_month_count(self, source_id, from_date, to_date):
        self.calls.append(("count", source_id, from_date, to_date))
        if self.fail_count:
            raise RuntimeError("OpenAlex is down")
        return self.counts.get(source_id, 0)

    def journal_work_at(self, source_id, from_date, to_date, position):
        self.calls.append(("draw", source_id, position))
        if self.fail_draw:
            raise RuntimeError("OpenAlex is down")
        if position > self.counts.get(source_id, 0):
            return None
        return {
            "source": "openalex", "id": f"https://openalex.org/W{position}",
            "doi": self.doi_at(source_id, position), "title": f"Work {position}",
            "abstract": "", "authors": [], "venue": "J", "venue_id": source_id,
            "venue_type": "journal", "date": "2026-09-10", "year": 2026,
        }


# ---------------------------------------------------------------------------
# Which journals qualify
# ---------------------------------------------------------------------------

def test_only_journals_behind_a_high_paper_qualify():
    scored = [
        _high(),
        _high(venue="Nature Communications", venue_id="S64187185"),
        _high(venue="Nature Communications", venue_id="S64187185"),   # repeat
        _high(venue="arXiv", venue_id="S4306400194", venue_type="repository"),
        _high(venue="No id", venue_id=""),                            # arXiv/PubMed
        {"llm": {"priority": "Medium"}, "venue": "Other", "venue_id": "S9",
         "venue_type": "journal"},
    ]
    journals = rr.journals_of_high_papers(scored)
    assert [j["venue_id"] for j in journals] == ["S147854436", "S64187185"]
    # A journal that produced two High papers is still one journal, but the
    # page can say so.
    assert journals[1]["seed_count"] == 2
    assert journals[0]["seed_title"] == "Seed paper"
    assert journals[0]["direction"] == "fea_surrogate"


def test_a_preprint_server_has_no_monthly_issue_to_read():
    # arXiv is where a third of the High papers come from; it is a repository,
    # not a journal, and "what else did it publish this month" is 20,000 papers
    # of everything.
    assert rr.JOURNAL_SOURCE_TYPES == {"journal"}
    assert rr.journals_of_high_papers([_high(venue_type="repository")]) == []
    assert rr.journals_of_high_papers([_high(venue_type="")]) == []


def test_the_journal_list_is_capped():
    scored = [_high(venue=f"J{n}", venue_id=f"S{n}") for n in range(20)]
    assert len(rr.journals_of_high_papers(scored)) == rr.MAX_JOURNALS


def test_the_window_is_the_whole_calendar_month():
    # The upper bound is the month end, not today: publishers deposit ahead,
    # and a paper dated later this month is still "published this month".
    assert rr.month_window("2026-09-25") == ("2026-09-01", "2026-09-30")
    assert rr.month_window("2026-02-03") == ("2026-02-01", "2026-02-28")
    assert rr.month_window("2024-02-29") == ("2024-02-01", "2024-02-29")


# ---------------------------------------------------------------------------
# The draw
# ---------------------------------------------------------------------------

def test_papers_are_drawn_from_the_month():
    fake = FakeOpenAlex({"S1": 40})
    picks, report = rr.sample_journal(
        {"venue_id": "S1", "venue": "J", "issn_l": "", "direction": "d",
         "seed_title": "t", "seed_identity_key": "doi:10.1/seed"},
        "2026-09-25", set(), fake)
    assert len(picks) == rr.SPECIALIST_PICKS        # 40 a month is specialist
    assert report["month_works"] == 40
    assert report["target_picks"] == rr.SPECIALIST_PICKS
    assert len(set(report["positions"])) == len(picks)  # never the same twice
    assert all(1 <= p <= 40 for p in report["positions"])
    meta = picks[0]["random_reading"]
    assert meta["venue"] == "J" and meta["month"] == "2026-09"
    assert meta["month_works"] == 40
    assert meta["seed_title"] == "t"


# ---------------------------------------------------------------------------
# How many to draw: five from a specialist journal, two from a megajournal
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("month_works,expected", [
    (0, 0),        # nothing published: nothing to read
    (3, 5),        # Smart Materials in Manufacturing
    (13, 5),       # Computational Mechanics
    (72, 5),       # CMAME — where the one High and two Medium came from
    (134, 5),      # Journal of Materials Science
    (200, 5),      # the threshold itself is still specialist
    (201, 2),
    (367, 2),      # Materials
    (726, 2),      # Nature Communications
    (3375, 2),     # Scientific Reports
])
def test_the_draw_scales_inversely_with_volume(month_works, expected):
    assert rr.picks_for_volume(month_works) == expected


def test_reading_more_of_a_megajournal_buys_nothing():
    # 2026-09-18..24: Nature Communications contributed ten papers over two
    # days and every one scored Exclude, while the one High and all three
    # Medium came from journals publishing tens of papers a month. Volume is
    # a proxy for topical spread, so the allocation runs the other way.
    assert rr.picks_for_volume(726) < rr.picks_for_volume(72)
    assert (rr.SPECIALIST_PICKS, rr.MEGAJOURNAL_PICKS) == (5, 2)
    assert rr.MEGAJOURNAL_WORKS == 200


def test_the_threshold_sits_in_the_gap_the_data_actually_has():
    # Seventeen journals observed so far: 3, 3, 3, 13, 13, 15, 34, 36, 40,
    # 72, 82, 102, 102, 134, 367, 726, 3375. The only 2.7x gap is 134 -> 367,
    # and exactly the three diffuse journals sit above it.
    specialist = [3, 13, 15, 34, 36, 40, 72, 82, 102, 134]
    diffuse = [367, 726, 3375]
    assert all(rr.picks_for_volume(n) == rr.SPECIALIST_PICKS for n in specialist)
    assert all(rr.picks_for_volume(n) == rr.MEGAJOURNAL_PICKS for n in diffuse)


def test_a_journal_smaller_than_its_allocation_gives_what_it_has():
    picks, report = rr.sample_journal(
        {"venue_id": "S1", "venue": "J", "issn_l": "", "direction": "d",
         "seed_title": "", "seed_identity_key": ""},
        "2026-09-25", set(), FakeOpenAlex({"S1": 3}))
    assert rr.picks_for_volume(3) == 5      # the rule asks for five...
    assert len(picks) == 3                  # ...the journal only has three
    assert report["target_picks"] == 3


def test_a_megajournal_gives_two_however_big_it_is():
    picks, report = rr.sample_journal(
        {"venue_id": "S1", "venue": "J", "issn_l": "", "direction": "d",
         "seed_title": "", "seed_identity_key": ""},
        "2026-09-25", set(), FakeOpenAlex({"S1": 3375}))
    assert len(picks) == rr.MEGAJOURNAL_PICKS == 2
    assert report["target_picks"] == 2


# ---------------------------------------------------------------------------
# Topping a day up after a rule change
# ---------------------------------------------------------------------------

def test_a_journal_that_already_met_its_allocation_draws_nothing():
    fake = FakeOpenAlex({"S1": 40})
    picks, report = rr.sample_journal(
        {"venue_id": "S1", "venue": "J", "issn_l": "", "direction": "d",
         "seed_title": "", "seed_identity_key": ""},
        "2026-09-25", set(), fake, have=5)
    assert picks == []
    assert report["target_picks"] == 5      # the target is still reported
    assert fake.calls == [("count", "S1", "2026-09-01", "2026-09-30")]


def test_only_the_shortfall_is_drawn():
    picks, report = rr.sample_journal(
        {"venue_id": "S1", "venue": "J", "issn_l": "", "direction": "d",
         "seed_title": "", "seed_identity_key": ""},
        "2026-09-25", set(), FakeOpenAlex({"S1": 40}), have=2)
    assert len(picks) == 3                  # 5 wanted, 2 already held
    assert report["target_picks"] == 5


def test_a_small_journal_the_radar_already_covers_still_fills_its_allocation():
    # The case that failed in production on 2026-09-25: Int. J. Bioprinting
    # publishes ~15 a month and the radar already held six; with only four
    # spare candidates the top-up ran out and returned nothing.
    fake = FakeOpenAlex({"S1": 15})
    journal = {"venue_id": "S1", "venue": "J", "issn_l": "", "direction": "d",
               "seed_title": "", "seed_identity_key": ""}
    # Nine of the fifteen are unusable: six in the corpus, three drawn before.
    known = {f"doi:10.9/s1-{n}" for n in range(1, 10)}
    picks, report = rr.sample_journal(journal, "2026-09-25", known, fake)
    assert len(picks) == rr.SPECIALIST_PICKS
    assert report["skipped_known"] >= 1
    assert all(p["doi"].lower() not in known for p in picks)


def test_a_top_up_walks_further_down_the_same_ordering():
    # Python's sample is a partial shuffle, so the same seed gives the same
    # prefix whatever k is: a top-up continues the first draw's list instead
    # of starting an unrelated one.
    journal = {"venue_id": "S1", "venue": "J", "issn_l": "", "direction": "d",
               "seed_title": "", "seed_identity_key": ""}
    first, _ = rr.sample_journal(journal, "2026-09-25", set(), FakeOpenAlex({"S1": 60}))
    known = {f"doi:{p['doi'].lower()}" for p in first}
    topped, _ = rr.sample_journal(journal, "2026-09-25", known,
                                  FakeOpenAlex({"S1": 60}), have=len(first))
    assert topped == []                         # already at the allocation
    # Raising the allocation draws papers the first pass had not reached.
    more, _ = rr.sample_journal(journal, "2026-09-25", set(known),
                                FakeOpenAlex({"S1": 60}), have=2)
    assert len(more) == rr.SPECIALIST_PICKS - 2
    assert not ({p["doi"] for p in more} & {p["doi"] for p in first})


def test_collect_tops_up_per_journal():
    fake = FakeOpenAlex({"S1": 40, "S2": 40})
    picks, _ = rr.collect(
        [_high(venue="A", venue_id="S1"), _high(venue="B", venue_id="S2")],
        set(), "2026-09-25", DIRECTIONS, {}, fake, have={"S1": 4})
    by_journal = {}
    for paper in picks:
        by_journal.setdefault(paper["random_reading"]["venue_id"], 0)
        by_journal[paper["random_reading"]["venue_id"]] += 1
    assert by_journal == {"S1": 1, "S2": 5}


def test_a_top_up_keeps_what_the_day_already_found(tmp_path):
    path = tmp_path / "2026-09-19.json"
    path.write_text(json.dumps({"papers": [
        {"doi": "10.9/kept-1", "random_reading": {"venue_id": "S1"}},
        {"doi": "10.9/kept-2", "random_reading": {"venue_id": "S1"}},
        {"doi": "10.9/kept-3", "random_reading": {"venue_id": "S2"}},
    ]}), encoding="utf-8")
    papers, held = bf.existing_day(path)
    assert [p["doi"] for p in papers] == ["10.9/kept-1", "10.9/kept-2", "10.9/kept-3"]
    assert held == {"S1": 2, "S2": 1}
    assert bf.existing_day(tmp_path / "missing.json") == ([], {})


def test_a_top_up_carries_the_earlier_draws_positions_forward():
    merged = bf.merge_reports(
        [{"venue_id": "S1", "positions": [3, 7], "skipped_known": 1}],
        [{"venue_id": "S1", "positions": [11], "skipped_known": 2},
         {"venue_id": "S2", "positions": [4], "skipped_known": 0}])
    assert merged[0]["positions"] == [3, 7, 11]
    assert merged[0]["skipped_known"] == 3
    assert merged[1]["positions"] == [4]


def test_force_and_top_up_are_different_things():
    source = (REPO_ROOT / "scripts" / "backfill_random_reading.py").read_text(encoding="utf-8")
    # --force throws the day away; because the stream remembers its own
    # picks, that guarantees a different sample and loses what was found.
    assert "elif not args.force:" in source
    assert "if args.top_up:" in source
    assert "held_papers + scored" in source


def test_the_same_day_always_draws_the_same_papers():
    # A re-run must not quietly spend money on a different sample.
    journal = {"venue_id": "S1", "venue": "J", "issn_l": "", "direction": "d",
               "seed_title": "", "seed_identity_key": ""}
    first, _ = rr.sample_journal(journal, "2026-09-25", set(), FakeOpenAlex({"S1": 500}))
    again, _ = rr.sample_journal(journal, "2026-09-25", set(), FakeOpenAlex({"S1": 500}))
    other, _ = rr.sample_journal(journal, "2026-09-26", set(), FakeOpenAlex({"S1": 500}))
    assert [p["doi"] for p in first] == [p["doi"] for p in again]
    assert [p["doi"] for p in first] != [p["doi"] for p in other]


def test_a_paper_already_in_the_corpus_is_skipped_not_shown_twice():
    fake = FakeOpenAlex({"S1": 40})
    journal = {"venue_id": "S1", "venue": "J", "issn_l": "", "direction": "d",
               "seed_title": "", "seed_identity_key": ""}
    # Learn which papers the draw wants, then declare them already known.
    wanted, _ = rr.sample_journal(journal, "2026-09-25", set(), FakeOpenAlex({"S1": 40}))
    known = {f"doi:{wanted[0]['doi'].lower()}"}
    picks, report = rr.sample_journal(journal, "2026-09-25", known, fake)
    assert report["skipped_known"] == 1
    assert all(p["doi"] != wanted[0]["doi"] for p in picks)
    assert len(picks) == rr.SPECIALIST_PICKS  # extra candidates covered the loss


def test_a_drawn_paper_joins_the_known_set_so_two_journals_cannot_collide():
    known = set()
    fake = FakeOpenAlex({"S1": 40}, doi_at=lambda sid, pos: "10.9/always-the-same")
    journal = {"venue_id": "S1", "venue": "J", "issn_l": "", "direction": "d",
               "seed_title": "", "seed_identity_key": ""}
    picks, report = rr.sample_journal(journal, "2026-09-25", known, fake)
    assert len(picks) == 1                      # every other draw was the same
    assert report["skipped_known"] >= 1
    assert "doi:10.9/always-the-same" in known


def test_a_tiny_journal_gives_what_it_has():
    picks, report = rr.sample_journal(
        {"venue_id": "S1", "venue": "J", "issn_l": "", "direction": "d",
         "seed_title": "", "seed_identity_key": ""},
        "2026-09-25", set(), FakeOpenAlex({"S1": 1}))
    assert len(picks) == 1 and report["month_works"] == 1


def test_a_journal_with_no_papers_this_month_is_recorded_not_dropped():
    picks, report = rr.sample_journal(
        {"venue_id": "S1", "venue": "J", "issn_l": "", "direction": "d",
         "seed_title": "", "seed_identity_key": ""},
        "2026-09-25", set(), FakeOpenAlex({"S1": 0}))
    assert picks == []
    assert report["month_works"] == 0 and not report["error"]


def test_a_pool_deeper_than_basic_paging_is_sampled_from_what_is_reachable():
    # OpenAlex basic paging stops at 10,000; asking for position 30,000
    # returns nothing at all, so the draw must stay inside the limit.
    fake = FakeOpenAlex({"S1": 30_000})
    picks, report = rr.sample_journal(
        {"venue_id": "S1", "venue": "J", "issn_l": "", "direction": "d",
         "seed_title": "", "seed_identity_key": ""},
        "2026-09-25", set(), fake)
    assert report["truncated_pool"] is True
    assert report["month_works"] == 30_000
    assert all(p <= openalex_fetcher.PAGE_LIMIT for p in report["positions"])
    assert len(picks) == rr.MEGAJOURNAL_PICKS   # 30,000 a month is diffuse


# ---------------------------------------------------------------------------
# Fail-soft
# ---------------------------------------------------------------------------

def test_openalex_failing_to_count_is_reported_not_raised():
    picks, report = rr.sample_journal(
        {"venue_id": "S1", "venue": "J", "issn_l": "", "direction": "d",
         "seed_title": "", "seed_identity_key": ""},
        "2026-09-25", set(), FakeOpenAlex({"S1": 40}, fail_count=True))
    assert picks == []
    assert "count failed" in report["error"]


def test_openalex_failing_mid_draw_keeps_what_it_already_has():
    class HalfBroken(FakeOpenAlex):
        def journal_work_at(self, source_id, from_date, to_date, position):
            if len(self.calls) >= 2:            # count + one good draw
                raise RuntimeError("OpenAlex is down")
            return super().journal_work_at(source_id, from_date, to_date, position)

    picks, report = rr.sample_journal(
        {"venue_id": "S1", "venue": "J", "issn_l": "", "direction": "d",
         "seed_title": "", "seed_identity_key": ""},
        "2026-09-25", set(), HalfBroken({"S1": 40}))
    assert len(picks) == 1
    assert "draw failed" in report["error"]


def test_one_broken_journal_does_not_stop_the_others():
    class OnlyS1Breaks(FakeOpenAlex):
        def journal_month_count(self, source_id, from_date, to_date):
            if source_id == "S1":
                raise RuntimeError("OpenAlex is down")
            return super().journal_month_count(source_id, from_date, to_date)

    scored = [_high(venue="A", venue_id="S1"), _high(venue="B", venue_id="S2")]
    picks, report = rr.collect(scored, set(), "2026-09-25", DIRECTIONS, {},
                               OnlyS1Breaks({"S1": 40, "S2": 40}))
    assert report["errors"] == 1
    assert len(picks) == rr.SPECIALIST_PICKS   # S2 still delivered
    assert [j["venue"] for j in report["journals"]] == ["A", "B"]


# ---------------------------------------------------------------------------
# Scoring focus
# ---------------------------------------------------------------------------

def test_a_drawn_paper_is_graded_against_a_real_direction():
    # The scorer picks its prompt focus from paper["direction"]; a random
    # paper matches no keyword, and routing would leave it None.
    fake = FakeOpenAlex({"S1": 40})
    picks, _ = rr.collect([_high(venue_id="S1")], set(), "2026-09-25",
                          DIRECTIONS, {}, fake)
    assert picks and all(p["direction"] == "fea_surrogate" for p in picks)
    assert all(p["routing_reason"] == "inherited from the seed High paper"
               for p in picks)


def test_the_fetcher_can_actually_be_stubbed():
    # A `fetcher=openalex_fetcher` default is bound at def-time, so patching
    # the module attribute leaves it pointing at the real network and the
    # test silently goes online. Resolved at call time instead.
    import inspect
    for func in (rr.sample_journal, rr.collect):
        assert inspect.signature(func).parameters["fetcher"].default is None


def test_the_journal_report_says_why_the_journal_is_there():
    _, report = rr.sample_journal(
        {"venue_id": "S1", "venue": "J", "issn_l": "1234-5678",
         "direction": "fea_surrogate", "seed_title": "The High paper",
         "seed_identity_key": "doi:10.1/seed", "seed_count": 2},
        "2026-09-25", set(), FakeOpenAlex({"S1": 40}))
    assert report["seed_title"] == "The High paper"
    assert report["seed_identity_key"] == "doi:10.1/seed"
    assert report["seed_count"] == 2
    assert report["direction"] == "fea_surrogate"
    assert report["issn_l"] == "1234-5678"


def test_a_drawn_paper_that_does_match_keeps_its_own_direction():
    class Bioprinting(FakeOpenAlex):
        def journal_work_at(self, source_id, from_date, to_date, position):
            work = super().journal_work_at(source_id, from_date, to_date, position)
            if work:
                work["abstract"] = "a bioprinting bioprinting study"
            return work

    picks, _ = rr.collect([_high(venue_id="S1")], set(), "2026-09-25",
                          DIRECTIONS, {}, Bioprinting({"S1": 40}))
    assert picks and all(p["direction"] == "ai_bioprinting" for p in picks)


# ---------------------------------------------------------------------------
# Inside the daily run
# ---------------------------------------------------------------------------

@pytest.fixture
def daily(monkeypatch, tmp_path):
    data_dir = tmp_path / "data"
    (data_dir / "daily").mkdir(parents=True)
    monkeypatch.setattr(rd, "DATA_DIR", data_dir)
    monkeypatch.setattr(rd, "SEEN_STATE", data_dir / "seen_dois.json")
    monkeypatch.setattr(rd, "MANIFESTS_DIR", data_dir / "manifests")
    monkeypatch.setattr(rd, "SNAPSHOTS_DIR", data_dir / "config_snapshots")
    monkeypatch.setattr(rd, "CHANGELOG", tmp_path / "CHANGELOG.md")
    captured = {}
    monkeypatch.setattr(rd.mf, "build_manifest",
                        lambda **kw: captured.setdefault("manifest", kw) and None
                        or {"run_id": "t", "git_commit": "d",
                            "config": {"scorer_prompt": "h"}})
    monkeypatch.setattr(rd.mf, "save_manifest", lambda *a, **kw: None)
    monkeypatch.setattr(rd.mf, "find_last_manifest", lambda *a, **kw: None)
    monkeypatch.setattr(rd.clu, "update_changelog", lambda **kw: False)
    monkeypatch.setattr(rd.clu, "save_config_snapshot", lambda *a, **kw: None)
    monkeypatch.setattr(rd.build_pages, "build", lambda *a, **kw: None)
    monkeypatch.setattr(rd.arxiv_fetcher, "fetch", lambda *a, **kw: [])
    monkeypatch.setattr(rd.pubmed_fetcher, "fetch", lambda *a, **kw: [])
    return tmp_path, captured


def _seed_paper(doi="10.1/seed"):
    return {
        "source": "openalex", "id": doi, "doi": doi,
        # Routed by the real config/directions.yaml, which these tests load:
        # "femoral stem" is a strong keyword and pairs with "finite element".
        "title": "femoral stem finite element study",
        "abstract": "a finite element study of a femoral stem",
        "authors": [], "venue": "Computational Mechanics",
        "venue_id": "S147854436", "venue_type": "journal", "venue_issn_l": "",
        "year": 2026, "date": "2026-09-19", "url": "", "cited_by_count": 0,
        "concepts": [], "categories": [],
    }


def _install(monkeypatch, fake, *, priority="High"):
    monkeypatch.setattr(rd.openalex_fetcher, "fetch",
                        lambda *a, **kw: [_seed_paper()])
    monkeypatch.setattr(rd.random_reading, "openalex_fetcher", fake)

    def score(papers, dirs):
        for paper in papers:
            paper["llm"] = {"priority": priority, "summary_zh": {"motivation": "m"}}
        return papers, [{"_usage": {}} for _ in papers]

    monkeypatch.setattr(rd.llm_scorer, "score_batch", score)


def test_the_pass_writes_its_own_file_and_never_the_corpus(monkeypatch, daily):
    tmp_path, _ = daily
    fake = FakeOpenAlex({"S147854436": 40})
    _install(monkeypatch, fake)
    report = rd.run(days_back=1, skip_zotero=True)

    data_dir = tmp_path / "data"
    written = sorted((data_dir / "random_reading").glob("*.json"))
    assert len(written) == 1
    payload = json.loads(written[0].read_text(encoding="utf-8"))
    assert payload["schema_version"] == rr.SCHEMA_VERSION
    assert payload["counts"]["journals"] == 1
    assert payload["counts"]["papers"] == rr.SPECIALIST_PICKS
    assert len(payload["papers"]) == rr.SPECIALIST_PICKS
    assert all(p["random_reading"]["venue_id"] == "S147854436"
               for p in payload["papers"])

    # The corpus holds the seed paper and nothing else.
    corpus = json.loads((data_dir / "daily" / "2026-09-19.json").read_text(encoding="utf-8"))
    assert [p["doi"] for p in corpus["papers"]] == ["10.1/seed"]
    for bucket in (data_dir / "daily").glob("*.json"):
        dois = {p["doi"] for p in json.loads(bucket.read_text(encoding="utf-8"))["papers"]}
        assert not any(doi.startswith("10.9/") for doi in dois), bucket

    # ...and the day's priority counts describe the corpus, not the draw.
    assert report["counts"]["priority_counts"]["High"] == 1
    assert report["counts"]["random_reading"]["papers"] == rr.SPECIALIST_PICKS


def test_a_drawn_paper_can_still_be_discovered_normally_later(monkeypatch, daily):
    # Marking it seen would hide it forever from the real keyword search.
    tmp_path, _ = daily
    _install(monkeypatch, FakeOpenAlex({"S147854436": 40}))
    rd.run(days_back=1, skip_zotero=True)
    seen = json.loads((tmp_path / "data" / "seen_dois.json").read_text(encoding="utf-8"))
    assert not any(str(key).startswith("doi:10.9/") for key in seen["keys"])


def test_the_pass_is_skipped_when_there_is_no_high_paper(monkeypatch, daily):
    tmp_path, _ = daily
    fake = FakeOpenAlex({"S147854436": 40})
    _install(monkeypatch, fake, priority="Medium")
    report = rd.run(days_back=1, skip_zotero=True)
    assert report["counts"]["random_reading"]["papers"] == 0
    assert not (tmp_path / "data" / "random_reading").exists()
    assert fake.calls == []                    # not one OpenAlex call


def test_the_switch_turns_the_whole_pass_off(monkeypatch, daily):
    tmp_path, _ = daily
    fake = FakeOpenAlex({"S147854436": 40})
    _install(monkeypatch, fake)
    monkeypatch.setenv("RADAR_RANDOM_READING", "0")
    report = rd.run(days_back=1, skip_zotero=True)
    assert report["counts"]["random_reading"]["status"] == "skipped"
    assert fake.calls == []
    assert not (tmp_path / "data" / "random_reading").exists()


def test_an_exhausted_balance_skips_the_pass_rather_than_failing(monkeypatch, daily):
    tmp_path, _ = daily
    fake = FakeOpenAlex({"S147854436": 40})
    _install(monkeypatch, fake)
    monkeypatch.setattr(rd.llm_scorer, "budget_exhausted", lambda: "402 no balance")
    report = rd.run(days_back=1, skip_zotero=True)
    assert report["counts"]["random_reading"]["status"] == "skipped"
    assert fake.calls == []


def test_the_pass_blowing_up_does_not_fail_the_daily_run(monkeypatch, daily):
    tmp_path, _ = daily
    _install(monkeypatch, FakeOpenAlex({"S147854436": 40}))

    def explode(*a, **kw):
        raise RuntimeError("something entirely unexpected")

    monkeypatch.setattr(rd.random_reading, "collect", explode)
    report = rd.run(days_back=1, skip_zotero=True)
    assert report["run_status"] == "success"
    assert report["counts"]["random_reading"]["status"].startswith("failed:")
    # The corpus was still written.
    assert (tmp_path / "data" / "daily" / "2026-09-19.json").exists()


def test_a_partial_draw_is_flagged_in_the_manifest(monkeypatch, daily):
    tmp_path, _ = daily
    _install(monkeypatch, FakeOpenAlex({"S147854436": 40}, fail_count=True))
    report = rd.run(days_back=1, skip_zotero=True)
    assert "random_reading_partial" in report["quality_flags"]


# ---------------------------------------------------------------------------
# The page
# ---------------------------------------------------------------------------

def test_the_page_shows_the_pool_and_what_the_rule_asked_for(tmp_path):
    (tmp_path / "random_reading").mkdir(parents=True)
    (tmp_path / "random_reading" / "2026-09-25.json").write_text(json.dumps({
        "schema_version": 1, "date": "2026-09-25", "month": "2026-09",
        "counts": {"journals": 1, "papers": 1},
        "journals": [{"venue_id": "S1", "venue": "Computational Mechanics",
                      "seed_title": "The High paper", "seed_count": 1,
                      "month": "2026-09", "month_works": 13, "target_picks": 2,
                      "positions": [3],
                      "skipped_known": 2, "truncated_pool": False, "error": ""}],
        "papers": [{"doi": "10.9/x", "title": "A drawn paper", "authors": [],
                    "venue": "Computational Mechanics", "date": "2026-09-10",
                    "direction": "fea_surrogate",
                    "random_reading": {"venue_id": "S1", "venue": "Computational Mechanics",
                                       "seed_title": "The High paper"},
                    "llm": {"priority": "Low", "summary_zh": {"motivation": "动机"}}}],
    }, ensure_ascii=False), encoding="utf-8")

    html = build_pages._render_random_reading_page(
        build_pages._load_random_reading(tmp_path), DIRECTIONS)
    assert "Computational Mechanics" in html
    assert "因为今天的 High：The High paper" in html
    assert "2026-09 共 13 篇" in html
    assert "专业刊，抽 2 篇" in html
    assert "跳过 2 篇已在库" in html
    assert "A drawn paper" in html
    assert "2026-09-25" in html
    # The disclaimer matters: these are not recommendations.
    assert "不是雷达推荐" in html


def test_the_page_labels_a_megajournal_as_one(tmp_path):
    (tmp_path / "random_reading").mkdir(parents=True)
    (tmp_path / "random_reading" / "2026-09-21.json").write_text(json.dumps({
        "date": "2026-09-21", "counts": {"journals": 1, "papers": 0},
        "journals": [{"venue_id": "S1", "venue": "Nature Communications",
                      "month": "2026-09", "month_works": 726, "target_picks": 2,
                      "positions": [], "skipped_known": 0, "error": ""}],
        "papers": [{"doi": "10.9/x", "title": "t", "authors": [], "llm": {},
                    "random_reading": {"venue_id": "S1"}}],
    }, ensure_ascii=False), encoding="utf-8")
    html = build_pages._render_random_reading_page(
        build_pages._load_random_reading(tmp_path), DIRECTIONS)
    assert "大刊，抽 2 篇" in html
    assert build_pages.RANDOM_MEGAJOURNAL_WORKS == rr.MEGAJOURNAL_WORKS


def test_the_page_explains_itself_when_there_is_nothing_yet(tmp_path):
    html = build_pages._render_random_reading_page(
        build_pages._load_random_reading(tmp_path), DIRECTIONS)
    assert "还没有随机阅读记录" in html
    assert 'href="random-reading.html" aria-current="page"' in html


def test_one_unreadable_day_does_not_empty_the_page(tmp_path):
    (tmp_path / "random_reading").mkdir(parents=True)
    (tmp_path / "random_reading" / "2026-09-24.json").write_text("{broken",
                                                                 encoding="utf-8")
    (tmp_path / "random_reading" / "2026-09-25.json").write_text(json.dumps({
        "date": "2026-09-25", "counts": {"journals": 0, "papers": 1},
        "journals": [], "papers": [{"doi": "10.9/x", "title": "Survivor",
                                    "authors": [], "llm": {}}],
    }), encoding="utf-8")
    days = build_pages._load_random_reading(tmp_path)
    assert [d["date"] for d in days] == ["2026-09-25"]


def test_the_page_is_in_the_navigation():
    assert 'href="random-reading.html"' in build_pages._site_nav()
    assert "随机阅读" in build_pages._site_nav()


# ---------------------------------------------------------------------------
# Not drawing the same paper twice on different days
# ---------------------------------------------------------------------------

def test_earlier_draws_are_remembered(tmp_path):
    folder = tmp_path / "random_reading"
    folder.mkdir()
    (folder / "2026-09-19.json").write_text(json.dumps({
        "papers": [{"doi": "10.9/Already-Seen"}, {"doi": ""}]}), encoding="utf-8")
    (folder / "2026-09-20.json").write_text("{broken", encoding="utf-8")
    assert rr.drawn_keys(tmp_path) == {"doi:10.9/already-seen"}
    assert rr.drawn_keys(tmp_path / "nope") == set()


def test_a_journal_drawn_on_two_days_does_not_repeat_itself(tmp_path):
    # The seed is per day, so two days are two independent samples — out of a
    # 13-paper month they will sometimes collide. These papers never enter the
    # corpus seen-state, so the stream has to remember them itself.
    journal = {"venue_id": "S1", "venue": "J", "issn_l": "", "direction": "d",
               "seed_title": "", "seed_identity_key": ""}
    known = set()
    first, _ = rr.sample_journal(journal, "2026-09-19", known, FakeOpenAlex({"S1": 6}))
    second, _ = rr.sample_journal(journal, "2026-09-20", known, FakeOpenAlex({"S1": 6}))
    drawn = [p["doi"] for p in first] + [p["doi"] for p in second]
    assert len(drawn) == len(set(drawn))


def test_the_daily_run_excludes_what_the_stream_already_drew(monkeypatch, daily):
    tmp_path, _ = daily
    _install(monkeypatch, FakeOpenAlex({"S147854436": 40}))
    rd.run(days_back=1, skip_zotero=True)
    folder = tmp_path / "data" / "random_reading"
    first = {p["doi"] for p in json.loads(
        next(folder.glob("*.json")).read_text(encoding="utf-8"))["papers"]}
    assert first
    # A second run on the same day would redraw the same positions; the
    # remembered keys are what stop it handing back the same papers.
    assert "already = set(updated_seen) | random_reading.drawn_keys(DATA_DIR)" in \
        (REPO_ROOT / "pipeline" / "run_daily.py").read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Backfilling past days
# ---------------------------------------------------------------------------

def test_a_run_day_is_reconstructed_from_first_seen_at(tmp_path):
    # A run scores a 14-day publication window, so "the papers of run-day D"
    # are the records stamped with D — not the bucket named D.
    daily_dir = tmp_path / "daily"
    daily_dir.mkdir(parents=True)
    (daily_dir / "2026-09-10.json").write_text(json.dumps({"papers": [
        {"doi": "10.1/a", "first_seen_at": "2026-09-19T05:00:00Z"},
        {"doi": "10.1/b", "first_seen_at": "2026-09-20T05:00:00Z"},
    ]}), encoding="utf-8")
    (daily_dir / "2026-09-19.json").write_text(json.dumps({"papers": [
        {"doi": "10.1/c", "first_seen_at": "2026-09-19T05:00:00Z"},
    ]}), encoding="utf-8")
    grouped = bf.papers_by_run_day(tmp_path, ["2026-09-19", "2026-09-20"])
    assert {p["doi"] for p in grouped["2026-09-19"]} == {"10.1/a", "10.1/c"}
    assert {p["doi"] for p in grouped["2026-09-20"]} == {"10.1/b"}


def test_buckets_far_outside_the_window_are_not_even_opened(tmp_path):
    daily_dir = tmp_path / "daily"
    daily_dir.mkdir(parents=True)
    (daily_dir / "2020-01-01.json").write_text("{not json", encoding="utf-8")
    (daily_dir / "2026-09-19.json").write_text(json.dumps({"papers": [
        {"doi": "10.1/c", "first_seen_at": "2026-09-19T05:00:00Z"}]}), encoding="utf-8")
    grouped = bf.papers_by_run_day(tmp_path, ["2026-09-19"])
    assert [p["doi"] for p in grouped["2026-09-19"]] == ["10.1/c"]


def test_an_old_high_paper_gets_its_journal_resolved(monkeypatch):
    # Records written before ADR-0035 have no venue_id at all.
    calls = []

    def resolve(ids):
        calls.append(list(ids))
        return {"W1": {"venue_id": "S147854436", "venue": "Computational Mechanics",
                       "venue_issn_l": "0178-7675", "venue_type": "journal"}}

    monkeypatch.setattr(bf.openalex_fetcher, "resolve_sources", resolve)
    papers = [
        {"id": "https://openalex.org/W1", "source": "openalex",
         "llm": {"priority": "High"}},
        {"id": "https://openalex.org/W2", "source": "openalex",
         "llm": {"priority": "Medium"}},                      # not High
        {"id": "2609.1", "source": "arxiv", "llm": {"priority": "High"}},
        {"id": "https://openalex.org/W3", "source": "openalex", "venue_id": "S9",
         "llm": {"priority": "High"}},                        # already has one
    ]
    high = bf.high_papers_with_journals(papers)
    assert calls == [["W1"]]             # only the High ones that need it
    assert high[0]["venue_id"] == "S147854436"
    assert high[0]["venue_type"] == "journal"
    assert high[2]["venue_id"] == "S9"   # untouched


def test_a_day_that_already_has_a_file_is_not_redrawn(tmp_path, monkeypatch, capsys):
    (tmp_path / "daily").mkdir(parents=True)
    (tmp_path / "random_reading").mkdir(parents=True)
    (tmp_path / "random_reading" / "2026-09-19.json").write_text(
        json.dumps({"papers": []}), encoding="utf-8")
    monkeypatch.setattr(bf.openalex_fetcher, "resolve_sources", lambda ids: {})
    assert bf.main(["--data-root", str(tmp_path),
                    "--from", "2026-09-19", "--to", "2026-09-19"]) == 0
    assert "already has a file" in capsys.readouterr().out


def test_the_backfill_is_the_production_code_path():
    source = (REPO_ROOT / "scripts" / "backfill_random_reading.py").read_text(encoding="utf-8")
    # The draw, the rule and the file layout must not be reimplemented here.
    assert "random_reading.collect(" in source
    assert "random_reading.build_file(" in source
    assert "llm_scorer.score_batch(" in source
    for reimplemented in ("SAMPLE_FRACTION", "picks_for_volume", "journal_work_at"):
        assert reimplemented not in source, reimplemented
    # The month follows the day being backfilled, never today.
    assert "day, directions, exclusions" in source


# ---------------------------------------------------------------------------
# The fetcher half
# ---------------------------------------------------------------------------

def test_the_normalised_record_carries_the_journal_identity():
    work = {
        "id": "https://openalex.org/W1", "title": "t", "publication_date": "2026-09-10",
        "primary_location": {"source": {"id": "https://openalex.org/S147854436",
                                        "display_name": "Computational Mechanics",
                                        "issn_l": "0178-7675", "type": "journal"}},
    }
    paper = openalex_fetcher._normalize(work)
    assert paper["venue_id"] == "S147854436"
    assert paper["venue_issn_l"] == "0178-7675"
    assert paper["venue_type"] == "journal"


def test_a_work_with_no_venue_has_no_journal_identity():
    paper = openalex_fetcher._normalize({"id": "x", "title": "t",
                                         "publication_date": "2026-09-10"})
    assert paper["venue_id"] == "" and paper["venue_type"] == ""


@pytest.mark.parametrize("raw,expected", [
    ({"id": "https://openalex.org/S123"}, "S123"),
    ({"id": "S123"}, "S123"),
    ({"id": "https://openalex.org/W123"}, ""),     # a work is not a source
    ({"id": "https://openalex.org/Sabc"}, ""),
    ({}, ""),
    (None, ""),
])
def test_the_source_id_is_validated_not_just_split(raw, expected):
    assert openalex_fetcher._source_id(raw) == expected


def test_the_journal_month_filter_is_bounded_on_both_sides():
    flt = openalex_fetcher.journal_month_filter("S1", "2026-09-01", "2026-09-30")
    assert "primary_location.source.id:S1" in flt
    assert "from_publication_date:2026-09-01" in flt
    assert "to_publication_date:2026-09-30" in flt
    assert "type:article|review" in flt


def test_sources_are_resolved_in_batches_without_duplicates(monkeypatch):
    seen = []

    def fake(params):
        ids = params["filter"].split(":", 1)[1].split("|")
        # `select` is what keeps a 50-work payload small.
        assert params["select"] == "id,primary_location"
        seen.append(ids)
        return {"results": [
            {"id": f"https://openalex.org/{i}",
             "primary_location": {"source": {"id": f"https://openalex.org/S{i[1:]}",
                                             "display_name": "J", "type": "journal"}}}
            for i in ids]}

    monkeypatch.setattr(openalex_fetcher, "_request_json", fake)
    ids = [f"W{n}" for n in range(120)] + ["W5", ""]
    out = openalex_fetcher.resolve_sources(ids)
    assert [len(batch) for batch in seen] == [50, 50, 20]   # deduped, batched
    assert out["W5"]["venue_id"] == "S5"
    assert out["W5"]["venue_type"] == "journal"


def test_a_position_outside_basic_paging_is_not_requested(monkeypatch):
    monkeypatch.setattr(openalex_fetcher, "_request_json",
                        lambda params: pytest.fail("should not have been called"))
    assert openalex_fetcher.journal_work_at("S1", "a", "b", 0) is None
    assert openalex_fetcher.journal_work_at(
        "S1", "a", "b", openalex_fetcher.PAGE_LIMIT + 1) is None
