"""Daily pipeline orchestrator. Integrates four traceability patches:
  1. Per-day run_manifest.json with git commit, hashes, package versions
  2. Auto-maintained CHANGELOG.md on config/prompt drift
  3. Versioned scorer prompt (loaded from prompts/scorer_vN.txt)
  4. Pruned daily data is archived to GitHub Releases monthly
"""

from __future__ import annotations
import datetime as dt
import json
import pathlib
import sys
import yaml

from fetchers import arxiv_fetcher, openalex_fetcher, pubmed_fetcher
from pipeline import (
    aggregator,
    direction_router,
    llm_scorer,
    zotero_sync,
    manifest as mf,
    changelog_updater as clu,
)
from render import build_pages

ROOT = pathlib.Path(__file__).resolve().parent.parent
CONFIG = ROOT / "config" / "directions.yaml"
DATA_DIR = ROOT / "data"
DOCS_DIR = ROOT / "docs"
SEEN_STATE = DATA_DIR / "seen_dois.json"
MANIFESTS_DIR = DATA_DIR / "manifests"
SNAPSHOTS_DIR = DATA_DIR / "config_snapshots"
CHANGELOG = ROOT / "CHANGELOG.md"


def _print(msg: str):
    print(f"[{dt.datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


def run(days_back: int = 2, skip_zotero: bool = False, force: bool = False) -> dict:
    cfg = yaml.safe_load(CONFIG.read_text())
    directions = cfg["directions"]
    exclusions = cfg.get("exclusions", {})
    today = dt.date.today().isoformat()
    prompt_path = llm_scorer.get_active_prompt_path()

    all_lists: list[list[dict]] = []
    arxiv_cats, openalex_kws, openalex_concepts, pubmed_terms = set(), set(), set(), set()
    for dcfg in directions.values():
        sources = dcfg.get("sources", {})
        arxiv_cats.update(sources.get("arxiv_categories", []))
        openalex_kws.update(sources.get("openalex_keywords", []))
        openalex_concepts.update(sources.get("openalex_concepts", []))
        pubmed_terms.update(sources.get("pubmed_terms", []))

    sources_used = {
        "arxiv": {"categories": sorted(arxiv_cats), "days_back": days_back},
        "openalex": {"keywords": sorted(openalex_kws),
                     "concepts": sorted(openalex_concepts),
                     "days_back": days_back},
        "pubmed":   {"terms": sorted(pubmed_terms), "days_back": days_back},
    }

    if arxiv_cats:
        _print(f"Fetching arxiv: {sorted(arxiv_cats)}")
        try:
            all_lists.append(arxiv_fetcher.fetch(sorted(arxiv_cats), days_back=days_back))
            _print(f"  -> {len(all_lists[-1])} papers")
        except Exception as e:
            _print(f"  ! arxiv failed: {e}")

    if openalex_kws or openalex_concepts:
        _print(f"Fetching OpenAlex: {len(openalex_kws)} keywords, {len(openalex_concepts)} concepts")
        try:
            all_lists.append(openalex_fetcher.fetch(
                concepts=sorted(openalex_concepts),
                keywords=sorted(openalex_kws),
                days_back=days_back,
            ))
            _print(f"  -> {len(all_lists[-1])} papers")
        except Exception as e:
            _print(f"  ! OpenAlex failed: {e}")

    if pubmed_terms:
        _print(f"Fetching PubMed: {sorted(pubmed_terms)}")
        try:
            all_lists.append(pubmed_fetcher.fetch(sorted(pubmed_terms), days_back=days_back))
            _print(f"  -> {len(all_lists[-1])} papers")
        except Exception as e:
            _print(f"  ! PubMed failed: {e}")

    fetched_total = sum(len(l) for l in all_lists)

    _print("Aggregating + dedup by DOI")
    papers, updated_seen = aggregator.aggregate(all_lists, SEEN_STATE, force=force)
    _print(f"  -> {len(papers)} unique new papers")

    _print("Routing papers to directions")
    for p in papers:
        direction_router.route(p, directions, exclusions)
    routed = direction_router.filter_routed(papers)
    _print(f"  -> {len(routed)} matched at least one direction")
    bucket = {d: 0 for d in directions}
    for p in routed:
        bucket[p["direction"]] += 1
    for d, n in bucket.items():
        _print(f"     {d}: {n}")

    _print(f"LLM scoring {len(routed)} papers (prompt={prompt_path.name})")
    scored, raw_responses = llm_scorer.score_batch(routed, directions)
    priority_counts = {"High": 0, "Medium": 0, "Low": 0, "Exclude": 0}
    for p in scored:
        priority_counts[p.get("llm", {}).get("priority", "Low")] += 1
    _print(f"  -> {priority_counts}")

    counts = {
        "fetched": fetched_total,
        "after_dedup": len(papers),
        "after_routing": len(routed),
        "by_direction": bucket,
        "priority_counts": priority_counts,
    }

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    (DATA_DIR / "daily").mkdir(exist_ok=True)
    daily_file = DATA_DIR / "daily" / f"{today}.json"

    # ===== W1.1 Empty-run guard =====
    # Refuse to overwrite a non-empty existing daily JSON with an empty one.
    # This prevents the failure mode where Actions dedup-cleans every paper
    # and would otherwise write [] over yesterday's good data.
    run_status = "success"
    quality_flags = []

    if fetched_total == 0:
        _print("ABORT: fetched_total == 0. All three sources returned nothing.")
        _print("  Refusing to write daily JSON. This may be a network or API issue.")
        run_status = "failed"
        quality_flags.append("fetched_zero")
        # Still write a marker file in a separate location for diagnostics
        marker = DATA_DIR / "daily" / f"{today}.SKIPPED.json"
        marker.write_text(json.dumps({
            "date": today, "reason": "fetched_zero",
            "fetched_total": 0
        }, indent=2))
        _print(f"  Wrote skip marker: {marker}")
    elif len(scored) == 0 and daily_file.exists():
        try:
            existing = json.loads(daily_file.read_text())
            if isinstance(existing, list) and len(existing) > 0:
                _print(f"ABORT: would overwrite {len(existing)} existing papers with 0.")
                _print("  Refusing to write empty JSON over non-empty existing data.")
                run_status = "suspicious_empty"
                quality_flags.append("zero_scored_with_existing_data")
                marker = DATA_DIR / "daily" / f"{today}.SKIPPED.json"
                marker.write_text(json.dumps({
                    "date": today,
                    "reason": "zero_scored_would_overwrite",
                    "fetched_total": fetched_total,
                    "after_routing": len(routed),
                    "existing_count": len(existing)
                }, indent=2))
                _print(f"  Wrote skip marker: {marker}")
            else:
                daily_file.write_text(json.dumps(scored, ensure_ascii=False, indent=2))
                aggregator.save_state(updated_seen, SEEN_STATE)
                _print(f"Saved {daily_file} (empty, no prior data to preserve)")
        except (json.JSONDecodeError, OSError) as e:
            _print(f"Warning: couldn't read existing JSON ({e}); writing fresh.")
            daily_file.write_text(json.dumps(scored, ensure_ascii=False, indent=2))
            aggregator.save_state(updated_seen, SEEN_STATE)
            _print(f"Saved {daily_file}")
    else:
        daily_file.write_text(json.dumps(scored, ensure_ascii=False, indent=2))
        aggregator.save_state(updated_seen, SEEN_STATE)
        _print(f"Saved {daily_file}")

    # Quality flags for downstream (manifest, report)
    if fetched_total > 0 and fetched_total < 50:
        quality_flags.append("low_fetch_count")
    if len(routed) == 0 and fetched_total > 0:
        quality_flags.append("zero_routed")
    if priority_counts.get("High", 0) + priority_counts.get("Medium", 0) == 0 and len(routed) > 0:
        quality_flags.append("zero_high_medium")
    # =================================


    manifest = mf.build_manifest(
        config_path=CONFIG,
        prompt_path=prompt_path,
        sources_used=sources_used,
        counts=counts,
        llm_responses=raw_responses,
        run_status=run_status,
        quality_flags=quality_flags,
    )
    MANIFESTS_DIR.mkdir(parents=True, exist_ok=True)
    manifest_path = MANIFESTS_DIR / f"{today}.json"
    mf.save_manifest(manifest, manifest_path)
    _print(f"Wrote manifest {manifest_path}")

    last_manifest = mf.find_last_manifest(DATA_DIR, before_date=today)
    last_snapshot = SNAPSHOTS_DIR / f"{last_manifest.stem}.yaml" if last_manifest else None
    last_prompt_hash = None
    if last_manifest:
        try:
            last_prompt_hash = json.loads(last_manifest.read_text())\
                .get("config", {}).get("scorer_prompt")
        except Exception:
            pass

    new_prompt_hash = manifest["config"]["scorer_prompt"]
    drift = clu.update_changelog(
        today=today,
        config_path=CONFIG,
        last_config_snapshot=last_snapshot,
        prompt_path=prompt_path,
        last_prompt_hash=last_prompt_hash,
        new_prompt_hash=new_prompt_hash,
        changelog_path=CHANGELOG,
        run_id=manifest["run_id"],
        counts=counts,
    )
    if drift:
        _print("CHANGELOG updated (config or prompt drift detected)")
    clu.save_config_snapshot(CONFIG, SNAPSHOTS_DIR / f"{today}.yaml")

    _print("Rendering HTML")
    build_pages.build(scored, today, DOCS_DIR, directions, manifest=manifest)
    _print(f"  -> docs/{today}.html and updated docs/index.html")

    if skip_zotero:
        _print("Skipping Zotero sync (skip_zotero=True)")
        zot_report = {"skipped": True}
    else:
        _print("Syncing to Zotero (priority >= Medium)")
        try:
            zot_report = zotero_sync.sync(scored, min_priority="Medium")
            _print(f"  -> {zot_report}")
        except Exception as e:
            _print(f"  ! Zotero sync failed: {e}")
            zot_report = {"error": str(e)}

    return {
        "date": today,
        "run_id": manifest["run_id"],
        "git_commit": manifest["git_commit"],
        "run_status": run_status,
        "quality_flags": quality_flags,
        "counts": counts,
        "zotero": zot_report,
        "changelog_updated": drift,
    }


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    days = int(args[0]) if args else 1
    skip_zot = "--skip-zotero" in sys.argv
    force = "--force" in sys.argv
    if force:
        print("[!] --force enabled: dedup will be bypassed")
    report = run(days_back=days, skip_zotero=skip_zot, force=force)
    print("\n=== Daily report ===")
    print(json.dumps(report, indent=2, ensure_ascii=False))
