# ADR-0035: Read the journals that produce High papers, at random

**Status**: Accepted (2026-09-25), implemented
**Related**: CLAUDE.md §1 (recall, not precision; adjacent-field inspiration
counts as value), ADR-0015 (v2 data model), ADR-0030 (OpenAlex cost model),
ADR-0031 (canonical identity), SCOPE.md § Allowed

## Context

Every paper the radar has ever shown was found by matching a keyword or an
OpenAlex concept. That is the right way to build a recall-first corpus, and
it has one structural blind spot: the radar cannot surface work it has no
words for. A method that would transfer to femoral-stem surrogate modelling,
described in vocabulary from a different field, is invisible by construction
— and it is exactly the kind of thing a PhD wants to have read.

There is a cheap signal for "this is the right neighbourhood" already in the
pipeline. When a paper scores **High**, the journal that published it is, by
that day's own evidence, publishing in the user's area. Most of what that
journal publishes in the same month matches no keyword and therefore never
appears. The user asked for that gap to be sampled: record the journals
behind the day's High papers, take two of each journal's papers from the
current month at random, evaluate them, and keep the record.

## Decision

A **serendipity pass** at the end of the daily run.

1. Collect the distinct journals of today's High papers. Only real journals
   qualify — OpenAlex types arXiv and other preprint servers as
   `repository`, and "what else did arXiv publish this month" is not a
   question worth asking. A journal behind two High papers is still one
   journal; the count is kept and shown.
2. For each (capped at six, against a freak day), ask OpenAlex how many
   articles and reviews it published between the first and last day of the
   current month, then draw two of them **uniformly at random**.
3. Route each draw for a prompt focus, falling back to the direction of the
   High paper that nominated the journal, and score it with the ordinary
   scorer and the ordinary prompt.
4. Write `data/random_reading/<date>.json` and render `random-reading.html`.

### Uniform, and cheap, and repeatable

OpenAlex bills per call. Reading a megajournal's month to throw nearly all
of it away would be fifteen pages of results; instead one call establishes
the size of the pool (`meta.count`) and one call per candidate addresses a
single work by position through basic paging. That is a genuinely uniform
draw for about three filter calls per journal — roughly thirty a day, about
$0.003. Basic paging stops at 10,000 results; a journal-month larger than
that is drawn from its first 10,000 and the file says so.

The draw is seeded with `sha256(date:source_id)`, so re-running a day picks
the same papers instead of quietly spending more money on a new sample.

Candidates are oversampled 3×, so a paper the corpus already holds can be
dropped without a second round trip to decide what to draw instead, and each
pick joins the known-key set so two journals cannot hand back the same work.

### Strictly outside the corpus

This is the part that matters. A randomly drawn paper is **not a radar
recommendation**, and nothing about it may pretend otherwise:

* it is written to `data/random_reading/`, never to `data/daily/`;
* it never enters the seen-state, so it can still be discovered normally
  later by a real keyword match — marking it seen would hide it forever;
* it is not in the queue, the search index, the workbench, or Zotero;
* it does not move the day's `priority_counts`; the pass reports its own.

Most draws will score Low or Exclude. That is the expected outcome of
reading outside your keywords, not a failure of the scorer, and the page
says so where the reader will see it.

### Fail-soft, and switchable

The pass runs after the corpus has been written and is wrapped so that no
OpenAlex outage, malformed journal or unexpected exception can fail the
daily run; a journal that fails is recorded with its error and the others
continue, and the manifest gets a `random_reading_partial` flag. The pass
is skipped entirely when the run fetched nothing, when the DeepSeek balance
is exhausted, or when `RADAR_RANDOM_READING=0`.

## Consequences

- Cost: 0-5 journals and 0-10 extra scored papers a day. Measured against
  the four runs before this ADR (High counts 1, 5, 3, 0), that is about
  +$0.004/day of DeepSeek on top of $0.03-0.06, and about $0.003/day of
  OpenAlex. CLAUDE.md §1 budgets ¥0.5-2/day; this is inside the noise.
- A megajournal is a weak signal. *Nature Communications* published 685
  papers in 2026-09; the first live draw returned plasma wakefield
  acceleration and optical-field photodetection. A specialist journal is
  where the value is — the same draw from *Computational Mechanics* (13
  papers that month) returned "From legacy finite element modeling to
  explainable simulation". The pool size is recorded per journal so the
  trade is visible. **Superseded the same day — see the addendum below.**
- `venue_id` / `venue_issn_l` / `venue_type` are new on OpenAlex records.
  Papers already in the corpus do not have them, so only journals seen from
  today onwards can be read. No backfill is planned.
- A random paper can be marked and tagged like any other (ADR-0034), so it
  can flow into the 待阅读 digest. The reading list renders it from its
  fallback card, since it has no day shard.

## Not in this stage

- Excluding journals by monthly volume outright. The draw now scales with
  volume (addendum below) but every qualifying journal still contributes.
- Bringing a draw into the corpus when it scores well. Promotion would make
  the pass a discovery source, which changes what the radar claims to be.
- Reading the journals behind Medium papers. High is the sharp signal.

## Rollback

Set `RADAR_RANDOM_READING=0`, or revert the pass. `data/random_reading/`
becomes inert data and `random-reading.html` renders its empty state. No
corpus record, count, or manifest field outside `counts.random_reading` is
touched by this ADR.

## Addendum 2026-09-25 — the draw scales with the journal's volume

The first cut drew a flat two papers per journal. The user asked for the
count to follow the journal's output instead, at "about 5% of what it
published". Measured against the eight journals behind the High papers of
2026-09-17..23 before changing anything:

| journal | 2026-09 output | flat 2 | uncapped 5% |
|---|---:|---:|---:|
| Scientific Reports | 3,375 | 2 | **169** |
| Nature Communications | 726 | 2 | **36** |
| Comput. Methods Appl. Mech. Engrg. | 72 | 2 | 4 |
| Fatigue & Fracture Engng Mater. | 36 | 2 | 2 |
| Int. J. Bioprinting | 15 | 2 | 1 |
| **Computational Mechanics** | 13 | 2 | **1** |
| Virtual and Physical Prototyping | 13 | 2 | 1 |
| Smart Materials in Manufacturing | 3 | 2 | 1 |
| **week total** | | **16** | **215** |

Uncapped, 5% inverts the signal: 205 of the 215 draws (95%) land in the two
journals that are topically furthest away, while the specialist journal whose
draw was actually relevant *shrinks* from two papers to one. Cost is not the
constraint — 215 papers a week is about ¥0.09/day — the page is: thirty-one
cards a day of mostly cell biology and plasma physics.

So the rule is bounded at both ends, and the bounds are the design:

    picks = min(5, max(2, round(month_works * 0.05)))

The floor keeps a specialist journal at two. The cap stops a megajournal
from swamping the page and preserves the property that made the flat rule
tolerable — a journal nobody can usefully sample costs almost nothing.
The same week draws **24** papers under this rule, about 3.4 a day.

`target_picks` is recorded per journal and shown on the page next to the
pool size, so the rule's arithmetic is visible rather than implied.

Not revisited: which papers are drawn (still uniform over the month), and
whether a big journal should be skipped entirely (it is not — it just
contributes at most five).

## Addendum 2026-09-25 (second) — the allocation is inverted

The 5% rule lasted one backfill. Running it over 2026-09-18..24 produced 24
papers across nine journals and scored them:

| source | papers | High | Medium |
|---|---:|---:|---:|
| Nature Communications (726/month) | 10 | 0 | 0 |
| specialist journals (3–72/month) | 14 | 1 | 3 |

Every one of the ten megajournal draws scored Exclude. The one High —
"Neural operators solve inverse problems for constitutive model discovery",
CMAME, 72 papers that month — is a paper the keyword filter never found,
which is the entire justification for this ADR.

So the allocation runs the other way: **a specialist journal gives up five
papers and a megajournal two.** Monthly volume is a usable proxy for topical
spread — a journal publishing three thousand papers a month is publishing
everything, so a random draw from it is a random draw from science, and
reading more of it buys nothing.

    picks = 5 if month_works <= 200 else 2

The threshold is placed where the data has a gap, not by taste. The
seventeen journals observed so far publish 3, 3, 3, 13, 13, 15, 34, 36, 40,
72, 82, 102, 102, 134, 367, 726, 3375 a month; the only wide gap is 134 →
367 (2.7x), and exactly the three topically diffuse journals — *Materials*,
*Nature Communications*, *Scientific Reports* — sit above it.

### Topping up instead of redrawing

Changing the rule raises most journals from two to five, which needed a way
to grow a day that already exists. `--force` cannot do it: it discards the
day, and because the stream remembers its own picks (`drawn_keys`), the
redraw is *guaranteed* to be different papers — it would have thrown the
High paper away. `--top-up` keeps what is there, asks each journal only for
its shortfall, and merges the report so the earlier draw's positions survive.

Superseded from the first addendum: `SAMPLE_FRACTION`, `MIN_PICKS`,
`MAX_PICKS`. The measurements in it stand and are why this one exists.

