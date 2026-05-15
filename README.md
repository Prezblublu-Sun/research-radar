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

## Required GitHub Variables

- `MODEL_NAME` — `deepseek-v4-flash`
- `OPENALEX_EMAIL` — Your email (polite pool)
- `PUBMED_EMAIL` — Your email (NCBI required)
- `ZOT_COL_BIOPRINTING`, `ZOT_COL_HIP`, `ZOT_COL_FEA`, `ZOT_COL_AM` — Zotero collection keys

## Version governance

Every daily run is reproducible:

- `data/manifests/YYYY-MM-DD.json` — git commit, config hashes, model snapshot, package versions
- `CHANGELOG.md` — auto-updated when config or prompt changes
- `prompts/scorer_vN.txt` — versioned scorer prompts (never overwritten)
- Monthly GitHub Release `archive-YYYY-MM` — long-term data archive

## License

MIT. Original UI inspiration from dw-dengwei/daily-arXiv-ai-enhanced.
