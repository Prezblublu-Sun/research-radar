from __future__ import annotations

import datetime as dt
import json
import pathlib

from pipeline import weekly_report
from scripts import rebuild_site


DIRECTIONS = {
    "fea_surrogate": {
        "display_name": "FEA & Surrogate Modelling",
        "color": "#345678",
    }
}
REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent


def _write_manifest(data_dir: pathlib.Path, run_date: str) -> None:
    manifests = data_dir / "manifests"
    manifests.mkdir(parents=True, exist_ok=True)
    (manifests / f"{run_date}.json").write_text(
        json.dumps({"run_id": f"{run_date}T03:00:00Z", "run_status": "success"}),
        encoding="utf-8",
    )


def _write_daily_paper(data_dir: pathlib.Path, publication_date: str) -> None:
    daily = data_dir / "daily"
    daily.mkdir(parents=True, exist_ok=True)
    paper = {
        "source": "openalex",
        "doi": "10.1234/example",
        "title": "Deterministic weekly paper",
        "authors": ["A. Author"],
        "venue": "Test Venue",
        "date": publication_date,
        "direction": "fea_surrogate",
        "cited_by_count": 0,
        "llm": {
            "priority": "High",
            "summary_zh": {},
            "relevance_to_user": "Relevant",
        },
    }
    (daily / f"{publication_date}.json").write_text(
        json.dumps({
            "schema_version": "v2",
            "date": publication_date,
            "papers": [paper],
        }),
        encoding="utf-8",
    )


def test_rebuild_all_weekly_uses_manifest_weeks_and_is_deterministic(tmp_path):
    data_dir = tmp_path / "data"
    output_dir = tmp_path / "weekly"
    _write_manifest(data_dir, "2026-05-13")
    _write_manifest(data_dir, "2026-05-20")
    _write_daily_paper(data_dir, "2026-05-13")

    output_dir.mkdir()
    stale = output_dir / "2020-W01.html"
    stale.write_text("stale", encoding="utf-8")

    first = weekly_report.rebuild_all_weekly(
        data_dir=data_dir,
        output_dir=output_dir,
        directions_cfg=DIRECTIONS,
    )
    first_bytes = {p.name: p.read_bytes() for p in sorted(output_dir.glob("*.html"))}

    second = weekly_report.rebuild_all_weekly(
        data_dir=data_dir,
        output_dir=output_dir,
        directions_cfg=DIRECTIONS,
    )
    second_bytes = {p.name: p.read_bytes() for p in sorted(output_dir.glob("*.html"))}

    assert [report["week_id"] for report in first] == ["2026-W20", "2026-W21"]
    assert second == first
    assert first_bytes == second_bytes
    assert not stale.exists()
    assert (output_dir / "2026-W20.html").exists()
    assert (output_dir / "2026-W21.html").exists()
    assert "2026-W21.html" in (output_dir / "index.html").read_text(encoding="utf-8")


def test_build_weekly_accepts_explicit_data_and_output_dirs(tmp_path):
    data_dir = tmp_path / "corpus"
    output_dir = tmp_path / "public" / "weekly"
    _write_daily_paper(data_dir, "2026-05-13")

    report = weekly_report.build_weekly(
        dt.date(2026, 5, 13),
        data_dir=data_dir,
        output_dir=output_dir,
        directions_cfg=DIRECTIONS,
    )

    assert report["week_id"] == "2026-W20"
    assert report["high_count"] == 1
    assert (output_dir / "2026-W20.html").exists()
    assert (output_dir / "index.html").exists()


def test_rebuild_site_adds_weekly_analytics_and_nojekyll(tmp_path, monkeypatch):
    project_root = tmp_path / "project"
    source_analytics = project_root / "docs" / "analytics"
    source_analytics.mkdir(parents=True)
    (source_analytics / "index.html").write_text("analytics", encoding="utf-8")
    data_dir = project_root / "data"
    data_dir.mkdir(parents=True)
    config_path = project_root / "directions.yaml"
    config_path.write_text(
        "directions:\n  fea_surrogate:\n    display_name: FEA\n    color: '#345678'\n",
        encoding="utf-8",
    )
    site_dir = project_root / "_site"

    calls = {}

    def fake_build(output_dir, directions, *, data_dir, sharded_daily):
        calls["build"] = (output_dir, directions, data_dir, sharded_daily)
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "index.html").write_text("site", encoding="utf-8")

    def fake_weekly(**kwargs):
        calls["weekly"] = kwargs
        kwargs["output_dir"].mkdir(parents=True, exist_ok=True)
        return [{"week_id": "2026-W20"}]

    monkeypatch.setattr(rebuild_site, "ROOT", project_root)
    monkeypatch.setattr(rebuild_site.build_pages, "build", fake_build)
    monkeypatch.setattr(rebuild_site.weekly_report, "rebuild_all_weekly", fake_weekly)

    assert rebuild_site.main([
        "--docs-dir", str(site_dir),
        "--data-dir", str(data_dir),
        "--directions-yaml", str(config_path),
        "--sharded-daily",
    ]) == 0

    assert calls["build"][0] == site_dir
    assert calls["build"][3] is True
    assert calls["weekly"]["output_dir"] == site_dir / "weekly"
    assert (site_dir / "analytics" / "index.html").read_text() == "analytics"
    assert (site_dir / ".nojekyll").exists()


def test_legacy_rebuild_does_not_gain_weekly_archive_coupling(
        tmp_path, monkeypatch):
    project_root = tmp_path / "project"
    data_dir = project_root / "data"
    data_dir.mkdir(parents=True)
    config_path = project_root / "directions.yaml"
    config_path.write_text(
        "directions:\n  fea_surrogate:\n"
        "    display_name: FEA\n    color: '#345678'\n",
        encoding="utf-8",
    )
    output_dir = project_root / "legacy-output"
    calls = {"weekly": 0}

    def fake_build(target, directions, *, data_dir, sharded_daily):
        assert sharded_daily is False
        target.mkdir(parents=True, exist_ok=True)
        (target / "index.html").write_text("site", encoding="utf-8")

    def forbidden_weekly(**kwargs):
        calls["weekly"] += 1
        raise AssertionError("legacy rebuild must not rebuild weekly reports")

    monkeypatch.setattr(rebuild_site, "ROOT", project_root)
    monkeypatch.setattr(rebuild_site.build_pages, "build", fake_build)
    monkeypatch.setattr(
        rebuild_site.weekly_report, "rebuild_all_weekly", forbidden_weekly,
    )

    assert rebuild_site.main([
        "--docs-dir", str(output_dir),
        "--data-dir", str(data_dir),
        "--directions-yaml", str(config_path),
    ]) == 0
    assert calls["weekly"] == 0
    assert (output_dir / ".nojekyll").exists()


def test_visual_enrichment_is_a_post_daily_sidecar_writer():
    workflow = (REPO_ROOT / ".github" / "workflows" / "visuals.yml").read_text(
        encoding="utf-8"
    )
    pages = (REPO_ROOT / ".github" / "workflows" / "pages.yml").read_text(
        encoding="utf-8"
    )

    assert "name: enrich-research-radar-visuals" in workflow
    assert "- daily-research-radar" in workflow
    assert "github.event.workflow_run.conclusion == 'success'" in workflow
    assert "group: research-radar-writer" in workflow
    assert "ref: main" in workflow
    assert "python -m scripts.enrich_visuals" in workflow
    assert "Priority queue to backfill" in workflow
    assert "- High+Medium" in workflow
    assert 'VISUAL_LIMIT" -gt 500' in workflow
    assert 'VISUAL_BATCHES" -gt 3' in workflow
    assert 'case "$VISUAL_SCOPE"' in workflow
    assert '--priorities "${priorities[@]}"' in workflow
    assert "Optional exact doi: or arxiv: identity to refresh" in workflow
    assert "github.event_name == 'workflow_dispatch' && inputs.identity || ''" in workflow
    assert '[[ "$VISUAL_IDENTITY" =~ ^(doi|arxiv):[^[:space:]]+$ ]]' in workflow
    assert 'identity_args=(--identity "$VISUAL_IDENTITY")' in workflow
    assert '"${identity_args[@]}"' in workflow
    assert "batch <= VISUAL_BATCHES" in workflow
    assert "No further eligible records; stopping early." in workflow
    assert "git add data/visuals/index.json" in workflow
    assert "pipeline.run_daily" not in workflow
    assert "git add data/ docs/" not in workflow
    assert "- enrich-research-radar-visuals" in pages
