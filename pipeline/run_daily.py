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
    v2_schema as v2,
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


# ADR-0015 v2 schema helpers live in pipeline/v2_schema.py and are shared
# with pipeline.run_historical. Keep changes there, not here.


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

    arxiv_lookback = days_back
    openalex_lookback = max(days_back, 14)
    pubmed_lookback = days_back

    # Per-source counts: only populated when a fetcher was attempted AND succeeded.
    # A source that was not attempted (empty config) stays absent; a source whose
    # try block raised stays absent too (the except branch already logged it).
    source_counts: dict[str, int] = {}

    if arxiv_cats:
        _print(f"Fetching arxiv (lookback={arxiv_lookback}d): {sorted(arxiv_cats)}")
        try:
            all_lists.append(arxiv_fetcher.fetch(sorted(arxiv_cats), days_back=arxiv_lookback))
            source_counts["arxiv"] = len(all_lists[-1])
            _print(f"  -> {len(all_lists[-1])} papers")
        except Exception as e:
            _print(f"  ! arxiv failed: {e}")

    if openalex_kws or openalex_concepts:
        _print(f"Fetching OpenAlex (lookback={openalex_lookback}d): {len(openalex_kws)} keywords, {len(openalex_concepts)} concepts")
        try:
            all_lists.append(openalex_fetcher.fetch(
                concepts=sorted(openalex_concepts),
                keywords=sorted(openalex_kws),
                days_back=openalex_lookback,
            ))
            source_counts["openalex"] = len(all_lists[-1])
            _print(f"  -> {len(all_lists[-1])} papers")
        except Exception as e:
            _print(f"  ! OpenAlex failed: {e}")

    if pubmed_terms:
        _print(f"Fetching PubMed (lookback={pubmed_lookback}d): {sorted(pubmed_terms)}")
        try:
            all_lists.append(pubmed_fetcher.fetch(sorted(pubmed_terms), days_back=pubmed_lookback))
            source_counts["pubmed"] = len(all_lists[-1])
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
    n_boosted = direction_router.apply_crossover_boost(scored)
    _print(f"  -> crossover boost applied to {n_boosted} paper(s)")
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
        # v2 multi-file bucketing diagnostics (ADR-0015 §4.5 / §7(iv)):
        "touched_dates": None,  # filled in after bucketing below
        "papers_with_missing_date": None,
    }

    # ===== ADR-0015 v2: per-publication-date bucketing + merge =====
    # One run touches every publication-date bucket of the papers it scored
    # (typically many, e.g. with a 14-day OpenAlex lookback). For each bucket
    # we read the existing v2 file (if any), merge by identity_key with
    # first-seen-wins, and write back atomically. Empty-run guard simplifies
    # to: refuse to do anything when fetched_total == 0; otherwise the merge
    # cannot lose existing papers, so the "would overwrite N with 0" check
    # from v1 is now obsolete.
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    daily_dir = DATA_DIR / "daily"
    daily_dir.mkdir(exist_ok=True)
    run_ts = v2.utc_now_iso()
    scorer_version = v2.scorer_version_from_active_prompt()

    run_status = "success"
    quality_flags = []
    touched_dates: dict[str, int] = {}
    missing_date = 0

    if fetched_total == 0:
        _print("ABORT: fetched_total == 0. All three sources returned nothing.")
        _print("  Refusing to write daily JSON. This may be a network or API issue.")
        run_status = "failed"
        quality_flags.append("fetched_zero")
        marker = daily_dir / f"{today}.SKIPPED.json"
        marker.write_text(json.dumps({
            "date": today, "reason": "fetched_zero", "fetched_total": 0,
        }, indent=2))
        _print(f"  Wrote skip marker: {marker}")
    else:
        # Bucket scored papers by paper["date"].
        buckets: dict[str, list[dict]] = {}
        for p in scored:
            d = (p.get("date") or "").strip()
            if not d:
                missing_date += 1
                continue
            buckets.setdefault(d, []).append(p)

        # Merge each bucket with whatever is already on disk; first-seen wins.
        for bucket_date, new_papers in buckets.items():
            target = daily_dir / f"{bucket_date}.json"
            existing_papers, _existing_meta = v2.load_existing_v2(target)
            existing_keys = {
                k for k in (v2.identity_key(p) for p in existing_papers) if k
            }
            added = 0
            for p in new_papers:
                k = v2.identity_key(p)
                if k and k in existing_keys:
                    continue  # first-seen wins; do not re-score in place
                p_out = dict(p)
                p_out["schema_version"] = "v2"
                p_out["date_precision"] = v2.infer_date_precision(p_out.get("date", ""))
                p_out["scorer_version"] = scorer_version
                p_out["first_seen_at"] = run_ts
                existing_papers.append(p_out)
                if k:
                    existing_keys.add(k)
                added += 1
            if added > 0:
                v2.atomic_write_json(target, v2.build_v2_file(bucket_date, existing_papers))
                touched_dates[bucket_date] = added

        # Discovery log: one record per observed scored paper (ADR-0015 §4.3).
        discovery_records = []
        for p in scored:
            k = v2.identity_key(p)
            if not k:
                continue
            discovery_records.append({
                "doi_or_arxiv_id": k,
                "first_seen_at": run_ts,
                "run_type": "daily",
            })
        if discovery_records:
            log_path = DATA_DIR / "discovery_log" / f"{today}.json"
            existing_log: list = []
            if log_path.exists():
                try:
                    loaded = json.loads(log_path.read_text(encoding="utf-8"))
                    if isinstance(loaded, list):
                        existing_log = loaded
                except (json.JSONDecodeError, OSError):
                    existing_log = []
            v2.atomic_write_json(log_path, existing_log + discovery_records)

        aggregator.save_state(updated_seen, SEEN_STATE)
        total_added = sum(touched_dates.values())
        if total_added == 0 and scored:
            _print(f"All {len(scored)} scored papers were already on disk; no bucket files updated.")
        else:
            _print(f"Wrote {total_added} new papers across {len(touched_dates)} bucket(s): "
                   f"{sorted(touched_dates.items())}")
        if missing_date:
            _print(f"  (skipped {missing_date} paper(s) with empty date field)")

    counts["touched_dates"] = dict(touched_dates)
    counts["papers_with_missing_date"] = missing_date

    # Quality flags for downstream (manifest, report)
    if fetched_total > 0 and fetched_total < 50:
        quality_flags.append("low_fetch_count")
    if len(routed) == 0 and fetched_total > 0:
        quality_flags.append("zero_routed")
    if priority_counts.get("High", 0) + priority_counts.get("Medium", 0) == 0 and len(routed) > 0:
        quality_flags.append("zero_high_medium")
    # Per-source silent-zero detection: an attempted fetcher that returned 0
    # papers gets its own flag, so single-source outages don't get masked by
    # the other sources keeping fetched_total healthy.
    for src, count in source_counts.items():
        if count == 0:
            quality_flags.append(f"{src}_returned_zero")
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
    build_pages.build(DOCS_DIR, directions, manifest=manifest,
                      touched_dates=set(touched_dates.keys()))
    if touched_dates:
        _print(f"  -> re-rendered {len(touched_dates)} touched page(s) + index.html")
    else:
        _print("  -> nothing new to render; refreshed index.html only")

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
