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
  trade is visible; capping or weighting by monthly volume is deliberately
  **not** done here, because it is the user's call, not a default.
- `venue_id` / `venue_issn_l` / `venue_type` are new on OpenAlex records.
  Papers already in the corpus do not have them, so only journals seen from
  today onwards can be read. No backfill is planned.
- A random paper can be marked and tagged like any other (ADR-0034), so it
  can flow into the 待阅读 digest. The reading list renders it from its
  fallback card, since it has no day shard.

## Not in this stage

- Weighting or excluding journals by monthly volume, and any other change to
  *which* papers are drawn. The draw is uniform on purpose; narrowing it is
  a decision for the user once there is a month of evidence.
- Bringing a draw into the corpus when it scores well. Promotion would make
  the pass a discovery source, which changes what the radar claims to be.
- Reading the journals behind Medium papers. High is the sharp signal.

## Rollback

Set `RADAR_RANDOM_READING=0`, or revert the pass. `data/random_reading/`
becomes inert data and `random-reading.html` renders its empty state. No
corpus record, count, or manifest field outside `counts.random_reading` is
touched by this ADR.
