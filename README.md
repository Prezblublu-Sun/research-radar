# Research Radar

Daily paper digest for **AI for 3D Bioprinting · Hip Implant & Femoral Stem · FEA Surrogate Modelling · AM Biomedical Materials**.

Pulls from arXiv + OpenAlex + PubMed, dedups by DOI, scores each paper with DeepSeek (priority + structured Chinese summary + tags), publishes to GitHub Pages, and syncs High/Medium papers into Zotero.

Runs daily via GitHub Actions. Zero server cost, ~¥15/month LLM cost.

## Setup

See `TODO.md` for the full first-time setup checklist.

Quick reference:

- Direction config: `config/directions.yaml`
- Active scorer prompt: `prompts/scorer_v3.txt`
- Main entry: `python -m pipeline.run_daily`
- Local dry-run without Zotero: `python -m pipeline.run_daily 1 --skip-zotero`

## Required GitHub Secrets

- `OPENAI_API_KEY` — DeepSeek API key
- `OPENAI_BASE_URL` — `https://api.deepseek.com`
- `ZOTERO_USER_ID` — Numeric user ID from zotero.org/settings/keys
- `ZOTERO_API_KEY` — Zotero API key with write access

## Optional GitHub Secrets

- `OPENALEX_API_KEY` — Free OpenAlex account key. Anonymous queries remain
  supported; configuring a key gives the scheduled runner a larger,
  account-bound allowance and reduces shared-IP rate limiting.

## Required GitHub Variables

- `MODEL_NAME` — `deepseek-v4-flash`
- `OPENALEX_EMAIL` — Contact email retained for backward compatibility
- `PUBMED_EMAIL` — Your email (NCBI required)
- `ZOT_COL_BIOPRINTING`, `ZOT_COL_HIP`, `ZOT_COL_FEA`, `ZOT_COL_AM` — Zotero collection keys

## Version governance

Every daily run is reproducible:

- `data/manifests/YYYY-MM-DD.json` — git commit, config hashes, model snapshot, package versions
- `CHANGELOG.md` — auto-updated when config or prompt changes
- `prompts/scorer_vN.txt` — versioned scorer prompts (never overwritten)
- Monthly GitHub Release `archive-YYYY-MM` — long-term data archive

## Open-license card visuals

`enrich-research-radar-visuals` runs after a successful daily workflow and
checks a bounded, newest-first High/Medium batch. It reads official PMC/arXiv
metadata, exposes a figure only under the configured reusable Creative Commons
licenses, and writes metadata to `data/visuals/index.json`. It never changes
paper scores or search ranking and does not store image/PDF binaries in Git.

Manual examples:

```bash
python -m scripts.enrich_visuals --limit 20
python -m scripts.enrich_visuals \
  --identity doi:10.1016/j.isci.2026.116487 --limit 1 --force
```

Set `PUBMED_EMAIL` for the PMC ID Converter. Missing, restricted, and failed
lookups render the explicit card state `暂时没有获取到图片`.

## License

MIT. Original UI inspiration from dw-dengwei/daily-arXiv-ai-enhanced.
