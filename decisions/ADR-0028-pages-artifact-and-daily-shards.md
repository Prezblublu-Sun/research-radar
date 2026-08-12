# ADR-0028: Disposable Pages artifact and sharded daily pages

**Status**: Accepted, staged rollout (2026-08-12)
**Related**: ADR-0015, ADR-0016, ADR-0027

## Context

The published `docs/` tree is about 1.6 GB. Daily HTML accounts for most of
that size: each of 4,208 pages embeds both its full paper cards and a copy of
the complete date dropdown. This is above the supported 1 GB GitHub Pages
published-site limit and couples source-data updates to a large set of derived
Git changes.

The browser also has compatibility state that cannot be migrated casually:
marks and notes use `radar:mark:<identity_key>`, the lit-system hand-off uses
`radar:promote-queue`, and external links target `YYYY-MM-DD.html#<anchor>`.

## Decision

1. Keep `data/` as the durable evidence layer. Build the website into a clean,
   ignored `_site/` directory and deploy it as a GitHub Pages Actions artifact.
2. Render each daily URL as a small static shell. Put public card data under
   `data/day/YYYY-MM-DD/manifest.json` and `page-N.json`, with 20 cards per
   shard. The date shell keeps only previous/archive/next navigation; it does
   not copy the complete archive dropdown.
3. Generate `identity_key` before display sorting, using the existing public
   identity algorithm. A daily manifest maps every authoritative card anchor
   to its page so old hash links can load the correct shard.
4. Preserve the first legacy anchor when normalized anchors collide. Give
   later collisions a stable identity-hash suffix, and reuse that authoritative
   anchor in daily, queue, search, and workbench links.
5. Use one DOM-safe JavaScript card renderer for daily and queue views. After
   inserting cards, call `RadarUI.hydrate()` so marks, notes, priority filters,
   and the promote queue retain their existing localStorage contracts.
6. Rebuild the complete weekly archive from committed manifests and daily data
   during artifact construction. Copy the small existing analytics artifacts
   until their generator is folded into the complete site build.
7. Serialize all repository writers through `research-radar-writer` and make
   queued jobs check out the latest `main` before committing.

## Rollout

The renderer has two explicit modes during migration:

- legacy writer calls keep generating embedded `docs/` pages;
- `scripts.rebuild_site --docs-dir _site --sharded-daily` builds the new
  artifact without changing tracked public output.

This first stage is merged and locally validated before changing the repository
Pages source from `main:/docs` to GitHub Actions. Once the artifact is deployed
and the public URL passes smoke tests, a follow-up removes `docs/` from writer
commits and deletes the obsolete generated daily HTML from version control.

## Consequences

- A clean public build becomes deterministic from repository data and config.
- Daily page payloads are bounded; users fetch at most 20 full cards per page.
- Hash links may trigger one manifest request and one shard request before
  scrolling, rather than resolving entirely from initial HTML.
- Filters apply to the currently loaded page. The UI states the all-day count
  and current-page count to make that boundary visible.
- The repository does not become smaller until the post-deployment cleanup
  removes historical generated `docs/` files and Git history is handled
  separately if desired.

## Rollback

Before the Pages-source switch, no rollback is needed because legacy `docs/`
publishing remains active. After the switch, set Pages back to `main:/docs` and
disable the artifact workflow; source data is unchanged.
