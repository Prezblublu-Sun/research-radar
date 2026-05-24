# ADR-0022: search-index era-split + blob slimming (drop summary_en)

**Status**: Accepted (2026-05-24)
**Related**: ADR-0015 (v2 corpus), build_pages._build_search_index,
session-log-2026-05-23 follow-up #5 (search-index approaching 100MB)

## Context

The daily cron failed on 2026-05-24 (run 26354088757). fetch/score/render
all succeeded; the git PUSH was rejected:

    remote: error: File docs/search-index.json is 244.28 MB; this exceeds
    GitHub's file size limit of 100.00 MB
    ! [remote rejected] main -> main (pre-receive hook declined)

Root cause: the single-file client-side search index outgrew GitHub's
100 MB hard per-file limit. Today's 10-year refetch (+68k papers ->
~103k total) and the rescore (which filled every previously-silent
paper's bilingual summary) inflated the index. The origin copy was
77 MB (built from the pre-refetch ~34k corpus); the cron rebuilt it over
the full 103k corpus and produced 244 MB, which git refuses.

This was a known, deferred risk (session log #5). It is now blocking the
daily cron every run — fetch+score waste plus lost daily data, since the
push that would persist the run is rejected.

### Measurements (2026-05-24, full 103k corpus)

  - blob field is 85% of index size (51.7 MB of 61 MB raw on the old
    34k index; dominated by abstract[:500] + summary_zh + summary_en +
    relevance_to_user + why_not_core per paper).
  - A single-file index over the full corpus cannot fit under 100 MB:
    even a lean blob (title + abstract[:500] + zh summary only) over
    103k papers is ~146 MB raw. No single-file slimming gets under the
    limit. Splitting is mandatory.
  - Per-year size (full bilingual blob): every year < 32 MB raw; largest
    is 2021 at 31.8 MB (~40 MB as JSON). Year granularity leaves ample
    headroom under 100 MB and room for growth.

## Decision

Two changes to build_pages._build_search_index and the inline search JS.

### 1. Era-split by year

Instead of writing one docs/search-index.json, write one file per year:

    docs/search-index-2014.json
    docs/search-index-2015.json
    ...
    docs/search-index-2026.json

plus a manifest:

    docs/search-index-manifest.json
        {"years": ["2014", ..., "2026"], "counts": {"2014": 32, ...},
         "total": 103026, "generated_at": "..."}

Each per-year file is the same list-of-records shape as before, holding
only that year's papers (grouped by paper date[:4], falling back to the
bucket filename year). Every year file stays well under 100 MB.

The old single docs/search-index.json is removed from git (git rm) and
no longer generated — it is superseded by the per-year files + manifest.

### 2. blob slimming — drop summary_en

The per-record blob drops summary_en. Rationale: abstract[:500] is
already English, so the English summary is a near-duplicate; removing it
shrinks the index and user download with negligible search-coverage loss.
why_not_core IS retained (per user decision). Final blob =
    title + abstract[:500] + relevance_to_user + summary_zh(all) +
    why_not_core + tags + key_terms + authors + venue + affiliation
all lowercased, same as today minus summary_en.

This does NOT affect any page DISPLAY. blob is used only for client-side
substring matching (JS: p.blob.indexOf(q)); it is never rendered.
Search-result cards render from separate fields (title/authors/venue/
priority/direction_name/...). Paper detail pages (docs/YYYY-MM-DD.html)
render bilingual summaries directly from data/daily/*.json, independent
of the search index. So summary_en still shows on detail pages; only the
search blob loses it.

### 3. Front-end: load all year files, merge, search unchanged

The inline search JS changes from a single fetch('search-index.json') to:
  - fetch the manifest,
  - Promise.all fetch every per-year file listed,
  - concatenate into the in-memory INDEX array,
  - then the existing filter/sort/render logic runs UNCHANGED.

This keeps search behaviour identical (cross-year substring search) with
no lazy-load complexity. After slimming, total download is smaller than
the old single file. (If total ever grows uncomfortable, a future ADR can
add real lazy-loading keyed on the manifest — out of scope now.)

## Consequences

  - Daily cron push succeeds again: no file exceeds 100 MB.
  - Search behaviour unchanged for the user; result cards and detail
    pages display exactly as before (summary_en still on detail pages).
  - Slightly reduced English-only search coverage (summary_en text no
    longer matchable), mitigated by abstract[:500] already being English.
  - One manifest + N year files instead of one index; build writes more
    files but each is small.
  - search-index.json removed from history going forward (git rm); the
    77 MB blob stops being re-pushed.

## Testing

  - _build_search_index writes search-index-YYYY.json for each year
    present + search-index-manifest.json; no docs/search-index.json.
  - Every per-year file parses as JSON and is < 100 MB (assert on the
    largest; in practice < 40 MB).
  - manifest years/counts match the per-year files; sum of counts ==
    total papers indexed.
  - blob no longer contains summary_en text (pick a paper whose
    summary_en has a distinctive token absent from abstract/zh; assert
    it's not in blob) but DOES still contain why_not_core + summary_zh.
  - A record's display fields (title/authors/priority/...) are unchanged.
  - Inline JS: manifest-driven multi-fetch merges to the same INDEX
    shape; filter/sort/render untouched (smoke: a known query returns the
    expected paper across the right year file).
