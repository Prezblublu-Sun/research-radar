# ADR-0029: Open-license card visuals as a sidecar

- Status: accepted
- Date: 2026-08-12

## Context

Research Radar cards are text-heavy. A compact scientific illustration can
make a paper easier to recognize, but the canonical daily records contain no
image field. Fetching publisher pages during rendering would make builds
non-deterministic, and copying arbitrary figures would create copyright,
repository-size, and deployment risks.

The existing discovery contract must remain stable: fetch, deduplication,
direction routing, LLM priority evaluation, search ranking, Zotero delivery,
and browser-local marks must not depend on image availability.

## Decision

Visual discovery is an optional enrichment workflow after the normal daily
writer succeeds.

- Only official machine-readable article services are eligible.
- A visual is published only when its machine-readable license is on the
  configured reuse allowlist.
- PMC's current AWS article dataset is the preferred source because its
  metadata exposes the article license and media objects directly.
- Other providers require a provider-specific license check; an accessible
  image URL alone is not permission to reuse it.
- No PDF is downloaded or parsed. No OCR, figure understanding, ranking, or
  generated replacement image is performed.
- The repository stores a compact sidecar registry keyed by the existing
  public `identity_key`; source image binaries are not committed.
- Rendering joins the sidecar after canonicalization. Search documents do not
  contain visual fields, so retrieval and ranking remain unchanged.
- `available` renders a lazy external preview with attribution. Missing,
  blocked, transient failure, malformed, and browser load-error states render
  the same honest message: `暂时没有获取到图片`.
- Enrichment failures never modify `data/daily`, `llm`, priority, or the
  identity contract and never block the daily discovery/scoring workflow.

## Consequences

Card rendering gains a small optional data dependency, while the core corpus
and search index stay unchanged. Coverage is intentionally lower than a broad
publisher scraper. The feature can be disabled by removing the sidecar without
changing any paper or user state. External source availability may still vary,
so the browser renderer must fail closed to the no-image state.

If visual coverage later needs local thumbnails at corpus scale, those assets
must move to bounded object storage/CDN with a separate cost and license review;
they must not be accumulated in Git or the Pages artifact.

## Provider references

- PMC current AWS article dataset and media metadata:
  <https://pmc.ncbi.nlm.nih.gov/tools/pmcaws/>
- PMC ID Converter API:
  <https://pmc.ncbi.nlm.nih.gov/tools/id-converter-api/>
- arXiv permissions and figure reuse:
  <https://info.arxiv.org/help/license/reuse.html>
