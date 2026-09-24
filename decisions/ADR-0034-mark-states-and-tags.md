# ADR-0034: A mark is one state plus any number of tags

**Status**: Accepted (2026-09-24), implemented
**Amends**: ADR-0016 §D4 (the four-value mark enum), ADR-0032 (the synced
payload shape)
**Related**: ADR-0016 (curation UI), ADR-0032 (marks sync), ADR-0033 (auto
sync), `pipeline/marks_store.py`, `render/static/radar-ui.js`

## Context

ADR-0016 gave each card one mark drawn from a flat, mutually exclusive enum:
待阅读 / 已阅读 / 有启发 / 忽略. Fifteen months of use exposed two faults.

**The enum mixes two different questions.** 待阅读, 已阅读 and 忽略 answer
"where is this paper in my triage flow" — they replace each other, and only
one can be true. 有启发 answers "what do I think of it" — which does not
replace anything. Marking a paper 有启发 erased the fact that it had been
read; marking it 已阅读 erased the judgement. The user could record the
reading or the verdict, never both, and the pair the curated library actually
needs — "read, and worth something" — was the one pair the model forbade.

**Only one surface could filter on it.** The daily pages had a checkbox bar
over all four values. The queue had a bespoke three-way 忽略 select added the
same week (全部 / 已忽略以外 / 只看已忽略), which could express nothing about
待阅读. The reading list had its own tab strip. Three filters, three
vocabularies, one underlying field. The user's report was exactly this:
"待阅读等标签也应该可以筛选" — the other states are not filterable where it
matters.

## Decision

Split the field in two.

**State** — where the paper sits in the triage flow. One at a time, chosen
from a fixed vocabulary: `to-read`, `read`, `ignore`, or empty. Rendered as
radio buttons, as before.

**Tags** — judgements about the paper. Any number at a time, free text,
capped at 24 per paper and 40 characters each. 有启发 becomes the first tag
rather than a state. Rendered as a chip row on the card with a 标签 panel for
editing.

The stored record gains one optional field and stays backward compatible:

```json
{ "state": "read", "tags": ["有启发"], "at": "...", "note": "..." }
```

A missing `tags` is an empty list, so `schema_version` stays 1 and a browser
that predates this ADR can still sync. Tags are trimmed, deduplicated and
**sorted** before storage, so two devices that added the same tags in a
different order write byte-identical files instead of fighting over commits.

### One filter, three surfaces

`markFilterFn()` in `radar-ui.js` is now the only rule for "does the mark
filter show this paper": states are OR'd, and a chosen tag narrows further.
The daily pages, the queue and — through its own tab strip and tag picker —
the reading list all answer the question the same way. The queue's bespoke
忽略 select is gone; the shared bar replaced it, and unticking 未标记 is what
"only show me what I marked" now means.

That mode still loads only the year shards that can hold a matching mark
(`markedYears()`), which is what made the old 只看已忽略 view affordable; it
simply generalises from one state to the whole filter.

### Migration

Two paths, because both have to hold at once.

*This browser*: `migrateMarks()` runs once at load, rewrites every
`interesting` record to `read` + the 有启发 tag, carries the two saved
filters that named states, and stamps `radar:marks-schema = 2`. It
deliberately does **not** touch `at`: bumping it would make this browser win
every subsequent merge and silently revert marks made elsewhere.

*Any other browser*: `validate_payload` maps `interesting` the same way on
the way in. A tab that has not reloaded in weeks — the site is cached hard —
therefore syncs correctly without being rejected, and without needing to
know this ADR happened.

There was nothing to migrate server-side: `data/marks/` held no committed
device files when this shipped.

## Consequences

- "Read **and** 有启发" is now sayable, which is what the curated library
  (ADR-0032's stated purpose) will be built from. `by_tag()` and
  `tag_counts()` give the digest job the same access to tags that
  `by_state()` gives it to states.
- Tags are free text, so the vocabulary can fragment (有启发 vs 有启发 ).
  Mitigated, not solved, by normalisation plus a shared `<datalist>` and
  count-ordered filter chips that show what already exists.
- A paper can carry tags with no state. That is deliberate — "haven't read
  it, but it's 有启发" is a real thing to say — and it means a tombstone is
  now "no state, no note, **and** no tags".
- The filter bar is no longer a daily-page ornament; it drives what the queue
  fetches. A stale or hostile value in `radar:filter:marks` is therefore
  filtered to the known vocabulary on read.
- The priority checkbox filter now applies only on pages that show the
  control. It was previously global, so unticking High on a daily page
  silently emptied the queue, with nothing on screen to explain it.

## Not in this stage

- Tag rename / merge across papers. Remove-and-re-add works; a rename tool
  waits for evidence the vocabulary actually drifts.
- Tag-based pages (a 有启发 library, a per-tag feed). That is the next step
  and it reads `data/marks/`, not localStorage.
- AND semantics across several tags. One tag at a time is what the triage
  loop needs; multi-tag intersection waits for a real case.

## Rollback

Revert the bundle and `marks_store.py`. Records keep their `tags` field,
which the old validator drops silently, and migrated papers stay 已阅读 —
the 有启发 state does not come back on its own. Migrating forward again is
idempotent.
