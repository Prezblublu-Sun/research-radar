# ADR-0027: Research workbench, canonical site view, and index v2

**Status**: Accepted (2026-07-20)
**Related**: ADR-0015, ADR-0016, ADR-0022

## Context

The public site grew to 104,766 raw paper records. Its archive-first landing
page no longer supports the daily triage loop, the cross-corpus High page is a
multi-megabyte HTML document, and search downloads every yearly content blob
before accepting a query. A rescore-path bug also left 451 bucket ``counts``
blocks stale, so archive badges and paper priorities disagreed.

Historical migrations left a second integrity wrinkle: 3,562 raw records share
an exact DOI/arXiv identity with a record in another publication-date bucket.
Deleting those source records would be irreversible and would discard evidence
about conflicting source dates.

## Decision

1. Keep ``data/daily`` as the evidence layer. Repair derived ``counts`` but do
   not delete duplicate source records.
2. Build every public aggregate from a canonical read-only corpus view using
   the strict ADR-0015 identity key. Earliest ``first_seen_at`` wins; legacy
   records without that field precede timestamped records. No fuzzy matching.
3. Make ``index.html`` a workbench for the seven most recent successful or
   partially-successful daily runs. Move the publication archive to
   ``archive.html``.
4. Replace static all-corpus High/Medium HTML with a unified, lazily-loaded
   queue split by priority and publication year.
5. Split search into lightweight all-year metadata and optional, year-scoped
   deep-content shards. Filtering and sorting run in a Web Worker.
6. Keep the application static: Python generation, vanilla browser JavaScript,
   shared CSS, and backward-compatible localStorage state. No backend, login,
   sync service, or new runtime dependency.

## Consequences

- Site counts describe unique visible identities; manifests also expose raw and
  duplicate-suppression totals for auditability.
- A duplicate record may remain accessible in raw JSON but is suppressed from
  its non-canonical publication-date HTML page.
- Old navigation URLs remain as lightweight compatibility redirects.
- Search display remains metadata-first; full Chinese decision cards live on
  workbench, queue, and daily pages.

## Rollback

The canonical view and new indexes are derived outputs. Reverting the renderer
restores the prior pages without migrating or deleting paper records.
