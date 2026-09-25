"""Serendipity pass: read the journals that produced today's High papers.

ADR-0035. The radar finds papers by keyword and concept, so it only ever
shows work that already looks like the user's own. A journal that just
produced a High-priority hit is, by that day's own evidence, publishing in
the right neighbourhood — and most of what it publishes that month never
matches a keyword and is therefore invisible.

So: record the journals of the day's High papers, draw two of each journal's
papers from the current month at random, and put them through the same
scorer. They are graded honestly (most will come back Low, and that is the
point of reading them), and they are kept **out** of the corpus — a separate
store, a separate page, their own counts. Nothing here can change what the
radar recommends, what the queue holds, or what reaches Zotero.

CLAUDE.md §1: "Adjacent-field inspiration counts as value". This is the
cheapest way to buy some, at roughly 0-5 journals and 0-10 extra papers a
day — a few cents of DeepSeek and about thirty OpenAlex filter calls.

The draw is seeded by date and journal, so re-running a day picks the same
papers instead of quietly spending more money on a different sample.
"""

from __future__ import annotations

import calendar
import datetime as dt
import hashlib
import json
import pathlib
import random

from fetchers import openalex_fetcher
from pipeline import direction_router
from render import identity as _identity

SCHEMA_VERSION = 1
# A day has 0-5 High papers; the cap only protects against a freak run.
MAX_JOURNALS = 6

# How many papers to draw. The draw scales *inversely* with the journal's
# monthly output, which is the opposite of the first rule and is what the
# evidence asked for.
#
# The 2026-09-18..24 backfill settled it. Nature Communications contributed
# ten papers across two days and every one of them scored Exclude, while the
# one High and all three Medium came from specialist journals — including
# the paper the keyword filter never found, "Neural operators solve inverse
# problems for constitutive model discovery" (CMAME). Monthly volume is a
# usable proxy for topical spread: a journal publishing 3,000 papers a month
# is publishing everything, so a random draw from it is a random draw from
# science, and reading more of it buys nothing.
#
# So a specialist journal gives up five and a megajournal two. The threshold
# is not arbitrary: the seventeen journals seen so far run 3, 3, 3, 13, 13,
# 15, 34, 36, 40, 72, 82, 102, 102, 134, 367, 726, 3375 — a 2.7x gap between
# 134 and 367, with exactly the three topically diffuse journals above it
# (Materials, Nature Communications, Scientific Reports).
MEGAJOURNAL_WORKS = 200
SPECIALIST_PICKS = 5
MEGAJOURNAL_PICKS = 2
# How many extra positions to look at beyond the target, so papers the radar
# already holds can be skipped without another round trip.
#
# Four was not enough. International Journal of Bioprinting publishes ~15
# papers a month and the radar already had six of them; adding the two this
# pass had drawn, more than half the pool was unusable, and a top-up asking
# for three more ran out of candidates and returned nothing. Ten means a
# small, well-covered journal is effectively scanned — which is right, since
# the few papers the radar missed are the entire point — while a megajournal
# still costs at most a dozen calls.
FETCH_HEADROOM = 10


def picks_for_volume(month_works: int) -> int:
    """How many papers to draw from a journal that published `month_works`."""
    if month_works <= 0:
        return 0
    return (MEGAJOURNAL_PICKS if month_works > MEGAJOURNAL_WORKS
            else SPECIALIST_PICKS)
# OpenAlex marks preprint servers and repositories as their own source type;
# arXiv has no monthly issue to browse, so only real journals qualify.
JOURNAL_SOURCE_TYPES = {"journal"}


def month_window(today: str) -> tuple[str, str]:
    """First of the month through the end of today's month.

    The upper bound is the month end rather than today so a paper dated
    later in the month — OpenAlex carries plenty, publishers deposit ahead —
    is reachable. Nothing outside the current month is ever drawn.
    """
    day = dt.date.fromisoformat(today)
    last = calendar.monthrange(day.year, day.month)[1]
    return day.replace(day=1).isoformat(), day.replace(day=last).isoformat()


def journals_of_high_papers(scored: list[dict]) -> list[dict]:
    """Distinct journals behind today's High papers, in the order they appear.

    Carries the seed paper along: it is what makes the journal interesting,
    it names the direction the picks are graded against, and it is what the
    page shows as the reason this journal is on the list.
    """
    journals: dict[str, dict] = {}
    for paper in scored:
        if ((paper.get("llm") or {}).get("priority")) != "High":
            continue
        source_id = (paper.get("venue_id") or "").strip()
        if not source_id:
            continue  # arXiv/PubMed records, and anything pre-ADR-0035
        if (paper.get("venue_type") or "") not in JOURNAL_SOURCE_TYPES:
            continue  # a preprint server has no monthly issue to read
        if source_id in journals:
            journals[source_id]["seed_count"] += 1
            continue
        journals[source_id] = {
            "venue_id": source_id,
            "venue": paper.get("venue") or source_id,
            "issn_l": paper.get("venue_issn_l") or "",
            "direction": paper.get("direction"),
            "seed_title": paper.get("title") or "",
            "seed_identity_key": _identity.canonical_key(paper) or "",
            "seed_count": 1,
        }
    return list(journals.values())[:MAX_JOURNALS]


def drawn_keys(data_root) -> set[str]:
    """Identity keys this pass has already drawn on earlier days.

    The seed is per day, so the same journal drawn on two days draws two
    independent samples — which, out of a 13-paper month, will sometimes be
    the same paper. These never enter the corpus seen-state (that would hide
    them from real discovery), so the stream has to remember them itself.
    """
    folder = pathlib.Path(data_root) / "random_reading"
    if not folder.is_dir():
        return set()
    keys: set[str] = set()
    for path in folder.glob("*.json"):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        for paper in (payload.get("papers") or []):
            key = _identity.canonical_key(paper)
            if key:
                keys.add(key)
    return keys


def _rng(today: str, source_id: str) -> random.Random:
    """Deterministic per day and journal, so a re-run repeats the draw."""
    digest = hashlib.sha256(f"{today}:{source_id}".encode("utf-8")).hexdigest()
    return random.Random(int(digest[:16], 16))


def sample_journal(journal: dict, today: str, known_keys: set[str],
                   fetcher=None, have: int = 0) -> tuple[list[dict], dict]:
    """Draw unseen papers from this journal's month, scaled to its volume.

    `have` is how many papers this journal already contributed on this day,
    so a rule change can top a day up instead of redrawing it and throwing
    away what the last draw found.

    Returns the picks and a report of what the draw saw. Any OpenAlex failure
    is reported, never raised: a serendipity pass must not be able to fail
    the daily run.

    `fetcher` defaults to the module-level OpenAlex client but is resolved
    here rather than in the signature: a default bound at def-time cannot be
    replaced, and a test that believes it stubbed the network would quietly
    go out and hit it.
    """
    fetcher = fetcher or openalex_fetcher
    from_date, to_date = month_window(today)
    report = {
        "venue_id": journal["venue_id"],
        "venue": journal["venue"],
        "issn_l": journal.get("issn_l", ""),
        # Why this journal is here at all — the page shows it, and without
        # it a reader cannot tell the draw from a recommendation.
        "seed_title": journal.get("seed_title", ""),
        "seed_identity_key": journal.get("seed_identity_key", ""),
        "seed_count": journal.get("seed_count", 1),
        "direction": journal.get("direction"),
        "month": today[:7],
        "month_works": 0,
        "target_picks": 0,
        "positions": [],
        "skipped_known": 0,
        "truncated_pool": False,
        "error": "",
    }
    try:
        total = fetcher.journal_month_count(journal["venue_id"], from_date, to_date)
    except Exception as error:
        report["error"] = f"count failed: {type(error).__name__}: {error}"[:200]
        return [], report

    report["month_works"] = total
    if total <= 0:
        return [], report
    reachable = min(total, fetcher.PAGE_LIMIT)
    report["truncated_pool"] = total > reachable

    rng = _rng(today, journal["venue_id"])
    target = min(picks_for_volume(total), reachable)
    report["target_picks"] = target
    wanted = max(0, target - max(0, have))
    if not wanted:
        return [], report
    # The same seed gives the same ordering whatever k is — Python's sample
    # builds a partial shuffle — so a top-up walks further down the list the
    # first draw already used, rather than starting a different one.
    order = rng.sample(range(1, reachable + 1),
                       k=min(reachable, target + FETCH_HEADROOM))

    picks: list[dict] = []
    for position in order:
        if len(picks) >= wanted:
            break
        try:
            work = fetcher.journal_work_at(
                journal["venue_id"], from_date, to_date, position)
        except Exception as error:
            report["error"] = f"draw failed: {type(error).__name__}: {error}"[:200]
            break
        if not work:
            continue
        key = _identity.canonical_key(work)
        if key and key in known_keys:
            report["skipped_known"] += 1
            continue
        if key:
            known_keys.add(key)  # never draw the same paper twice in one run
        work["random_reading"] = {
            "venue": journal["venue"],
            "venue_id": journal["venue_id"],
            "issn_l": journal["issn_l"],
            "month": today[:7],
            "month_works": total,
            "position": position,
            "seed_title": journal["seed_title"],
            "seed_identity_key": journal["seed_identity_key"],
        }
        picks.append(work)
        report["positions"].append(position)
    return picks, report


def collect(scored: list[dict], known_keys: set[str], today: str,
            directions_cfg: dict, exclusions: dict | None = None,
            fetcher=None, have: dict[str, int] | None = None
            ) -> tuple[list[dict], dict]:
    """Pick this run's random reading. Returns (papers, report).

    `known_keys` is mutated: papers already in the corpus are skipped, and
    each pick joins the set so one journal cannot hand back another's paper.

    `have` maps a venue id to how many papers that journal already
    contributed on this day, for topping a day up after a rule change.
    """
    report = {"journals": [], "papers": 0, "errors": 0}
    journals = journals_of_high_papers(scored)
    picks: list[dict] = []
    for journal in journals:
        drawn, journal_report = sample_journal(
            journal, today, known_keys, fetcher,
            have=(have or {}).get(journal["venue_id"], 0))
        report["journals"].append(journal_report)
        if journal_report["error"]:
            report["errors"] += 1
        for paper in drawn:
            # Route it for a better prompt focus, but never let an unrouted
            # paper go to the scorer with no direction at all: fall back to
            # the direction of the High paper that nominated this journal.
            direction_router.route(paper, directions_cfg, exclusions or {})
            if not paper.get("direction"):
                paper["direction"] = journal["direction"]
                paper["direction_name"] = (directions_cfg.get(journal["direction"]) or {}).get(
                    "display_name") if journal["direction"] else None
                paper["routing_reason"] = "inherited from the seed High paper"
            picks.append(paper)
    report["papers"] = len(picks)
    return picks, report


def build_file(today: str, picks: list[dict], report, scorer_version: str,
               generated_at: str) -> dict:
    """The on-disk record. Deliberately self-contained: the random papers are
    not in data/daily/, so this file is the only place they exist.

    `report` is either a collect() report or, when a caller has merged the
    journal entries itself (a top-up), that list of entries.
    """
    if isinstance(report, list):
        journals, errors = report, sum(1 for j in report if j.get("error"))
    else:
        journals, errors = report["journals"], report["errors"]
    return {
        "schema_version": SCHEMA_VERSION,
        "date": today,
        "month": today[:7],
        "generated_at": generated_at,
        "scorer_version": scorer_version,
        "journals": journals,
        "counts": {
            "journals": len(journals),
            "papers": len(picks),
            "errors": errors,
        },
        "papers": picks,
    }
