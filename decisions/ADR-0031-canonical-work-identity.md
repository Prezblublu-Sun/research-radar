# ADR-0031: Canonical work identity for dedup decisions

**Status**: Accepted (2026-09-14)
**Supersedes**: ADR-0025 (draft figshare/Zenodo suffix rule)
**Related**: ADR-0015 §4.4 (identity_key), ADR-0027/0028 (anchors and
localStorage keys), CLAUDE.md §4 ("DOI-only strict dedup. No fuzzy dedup")

## Context — what the 2026 search index showed

The public 2026 shard (`search-index-2026.json`, 8,905 records on
2026-09-11) contains 230 groups of records with byte-identical titles,
265 excess records in total. Classified by identity key:

| Cause | Groups | Why strict `identity_key` misses it |
|---|---|---|
| Zenodo concept + version DOI (`…22057603` / `…22057604`) | 93 | Different DOI strings; the integers are consecutive, so no suffix rule applies |
| OpenAlex copy of an arXiv preprint (DOI-less, venue "ArXiv.org") | 85 of the 148 `noid:` records | OpenAlex work has no DOI; its arXiv id is only in `primary_location.landing_page_url`; the arXiv-fetcher record carries `arxiv_id` with a `v1` suffix |
| arXiv preprint vs journal version | 61 | Genuinely different DOIs; out of scope here (needs a preprint-relation source) |
| Same PubMed / repository record, two `noid:` hashes | 33 | Identity-less records are appended on every fetch; the seen-state truncation (fixed in ADR-0030) let them return |
| figshare `.v1` version DOI | 8 (19 base collisions in 2026) | Suffix-distinct DOI strings |
| DOI case variants (`J.X` vs `j.x`) | 7 | `identity_key` compares raw strings; DOIs are case-insensitive |

Each duplicate costs a second DeepSeek scoring, appears twice in the
workbench and queue, and can carry a contradictory priority (a Leiden thesis
was Low in one copy and Medium in the other).

The Zenodo record API is the authority for versions: on 2026-09-14
`GET /api/records/22057603` and `/records/22057604` both returned
`conceptdoi = 10.5281/zenodo.22057603`. OpenAlex exposes the arXiv id of a
DOI-less preprint in `primary_location.landing_page_url`
(`https://arxiv.org/abs/2609.00965`; 328 such works since 2026-09-01).

## Decision

1. **Two keys, two jobs.** `identity_key` (ADR-0015 §4.4: `doi:<raw>` /
   `arxiv:<raw>`) is unchanged and keeps naming anchors, `radar:mark:*`
   localStorage entries, discovery-log rows and the visual registry. A new
   `canonical_key` (`render/identity.py`, stdlib-only) decides only whether
   two records are the same work. The first-seen record always keeps its
   public identity; later duplicates are suppressed.
2. **Canonical key rules — exact identifiers only.** In precedence order:
   - DOI, case-folded with resolver prefixes stripped (DOI Handbook: DOIs
     are case-insensitive).
   - `10.48550/arxiv.<id>` is arXiv's own DOI for a preprint → `arxiv:<id>`.
   - figshare `…figshare.<n>.v<k>` → `…figshare.<n>` (DataCite `IsVersionOf`).
   - Zenodo `10.5281/zenodo.<n>` → concept DOI via an alias table resolved
     from the Zenodo record API (`pipeline/doi_aliases.py`, cache in
     `data/doi_aliases.json`, ≤100 lookups per run, 1 s apart, stops at the
     first network failure; an unresolved DOI keeps its own identity until
     a later run resolves it).
   - arXiv id with the `vN` suffix removed.
   - PubMed PMID (`pmid:`), then OpenAlex work id (`openalex:`).
   - Otherwise no canonical identity: the record is never merged. Title,
     author and date similarity remain forbidden.
3. **Where it applies.** `aggregator.aggregate` (fetch-time dedup and the
   seen-state; legacy keys in an older `seen_dois.json` are still honoured
   so the switch does not re-score the window), the on-disk first-seen-wins
   merge in `run_daily` and `run_historical`, the corpus pre-dedup in
   `run_historical`, `corpus_view.canonicalize_buckets` (public site), and
   `export_candidates` (lit-system hand-off).
4. **OpenAlex normalizer** now records `pmid` (from `ids.pmid`) and
   `arxiv_id` (from location URLs) so the exact identifiers exist on the
   record.
5. **Within-run merge preference.** When an arXiv record and a same-work
   record from OpenAlex/PubMed collide, the newcomer replaces the arXiv
   record only when it carries a DOI (the published version). A DOI-less
   OpenAlex copy of the preprint never replaces the richer arXiv record;
   both directions record `also_seen_in`.

## Why this is not fuzzy dedup

Every rule maps identifiers that the issuing registry declares to denote
one work: DOI case-insensitivity is specified by the DOI Handbook, arXiv's
`10.48550` DOIs are minted per arXiv id, DataCite version relations are
declared by the repository, and the Zenodo concept DOI comes from Zenodo's
own record. PMID and OpenAlex ids are unique identifiers, not descriptions.
No rule compares titles, authors or dates.

## Consequences

- Expected effect on the 2026 shard: ~102 Zenodo, ~85 OpenAlex-arXiv, ~19
  figshare, ~7 case-variant and most PubMed/repository `noid` duplicates
  disappear from the public views on the next build; the 61 preprint /
  journal pairs remain and are visible for a later decision.
- Fewer duplicate scorings per day (each pair was scored twice).
- `data/doi_aliases.json` is a new committed data file written by the daily
  and backfill workflows (both already `git add data/`).
- A DOI-less OpenAlex preprint copy fetched *before* its arXiv record now
  wins first-seen and keeps its `noid:` anchor; the later arXiv record is
  suppressed on the site. Acceptable: the copy still links to arXiv.
- Anchors and marks: unchanged for every existing record.

## Rollback

Remove the `aliases` argument at the call sites and restore the strict
`identity_key` in `aggregator._dedup_key`, `run_daily`, `run_historical`
and `corpus_view`; delete `data/doi_aliases.json`. No stored record is
modified by this ADR, so rollback is a code revert.

## Verification

`tests/test_identity.py`, `tests/test_doi_aliases.py`,
`tests/test_canonical_dedup.py` (aggregator, on-disk merge, corpus view,
OpenAlex normalizer). Live: the resolver run against the real Zenodo API for
the 22057603/22057604 pair returns one concept DOI for both.
