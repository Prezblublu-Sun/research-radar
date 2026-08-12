from __future__ import annotations

import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from render import build_pages


DIRECTIONS = {
    "fea_surrogate": {
        "display_name": "FEA & Surrogate Modelling",
        "color": "#345678",
    }
}


def _available_visual(*, image_url: str, source_url: str,
                      license_name: str = "CC BY 4.0") -> dict:
    return {
        "status": "available",
        "image_url": image_url,
        "caption": "Figure caption",
        "source_label": "Figure 1",
        "source_url": source_url,
        "license": license_name,
        "alt": "A research figure",
        "width": 1200,
        "height": 800,
        "checked_at": "2026-08-12T10:00:00Z",
        "provider": "must-not-be-public",
        "reason": "must-not-be-public",
    }


def _write_registry(data_dir: pathlib.Path, folder: str,
                    records: dict[str, dict]) -> None:
    target = data_dir / folder
    target.mkdir(parents=True, exist_ok=True)
    (target / "index.json").write_text(json.dumps({
        "schema_version": "v1",
        "updated_at": "2026-08-12T10:00:00Z",
        "records": records,
    }), encoding="utf-8")


def _paper() -> dict:
    return {
        "source": "openalex",
        "doi": "10.1234/visual",
        "title": "Visual registry paper",
        "abstract": "Synthetic abstract.",
        "authors": ["A. Author"],
        "venue": "Test Venue",
        "year": 2026,
        "date": "2026-08-12",
        "direction": "fea_surrogate",
        "direction_name": "FEA & Surrogate Modelling",
        "first_seen_at": "2026-08-12T03:00:00Z",
        "llm": {
            "priority": "High",
            "relevance_level": "Direct",
            "summary_zh": {},
            "summary_en": {},
            "flags": {},
        },
    }


def _write_corpus(data_dir: pathlib.Path) -> None:
    daily = data_dir / "daily"
    daily.mkdir(parents=True, exist_ok=True)
    paper = _paper()
    (daily / "2026-08-12.json").write_text(json.dumps({
        "schema_version": "v2",
        "date": "2026-08-12",
        "date_precision": "day",
        "papers": [paper],
    }), encoding="utf-8")
    manifests = data_dir / "manifests"
    manifests.mkdir(parents=True, exist_ok=True)
    (manifests / "2026-08-12.json").write_text(json.dumps({
        "run_status": "success",
        "quality_flags": [],
    }), encoding="utf-8")


def test_visual_registry_is_fail_closed_compact_and_path_compatible(tmp_path):
    data_dir = tmp_path / "data"
    safe = _available_visual(
        image_url="https://pmc-oa-opendata.s3.amazonaws.com/a/figure.jpg",
        source_url="https://pmc.ncbi.nlm.nih.gov/articles/PMC123/",
    )
    _write_registry(data_dir, "figures", {
        "doi:primary-blocks-fallback": {"status": "not_found"},
        "doi:bad-host": _available_visual(
            image_url="https://images.example.com/figure.jpg",
            source_url="https://example.com/article",
        ),
        "doi:bad-license": _available_visual(
            image_url="https://arxiv.org/html/1234.5678/figure.png",
            source_url="https://arxiv.org/abs/1234.5678",
            license_name="All rights reserved",
        ),
    })
    _write_registry(data_dir, "visuals", {
        "doi:safe": safe,
        "doi:primary-blocks-fallback": safe,
        "doi:http-source": _available_visual(
            image_url="https://arxiv.org/html/1234.5678/figure.png",
            source_url="http://arxiv.org/abs/1234.5678",
        ),
    })

    registry = build_pages._load_visual_registry(data_dir)

    assert set(registry) == {"doi:safe"}
    assert registry["doi:safe"] == {
        "status": "available",
        "image_url": safe["image_url"],
        "source_url": safe["source_url"],
        "license": "CC BY 4.0",
        "caption": "Figure caption",
        "source_label": "Figure 1",
        "alt": "A research figure",
        "checked_at": "2026-08-12T10:00:00Z",
        "width": 1200,
        "height": 800,
    }


def test_visual_join_is_consistent_for_day_queue_and_workbench_not_search(
        tmp_path, monkeypatch):
    data_dir = tmp_path / "data"
    docs_dir = tmp_path / "site"
    _write_corpus(data_dir)
    visual = _available_visual(
        image_url="https://arxiv.org/html/2608.12345/figure.png",
        source_url="https://arxiv.org/abs/2608.12345",
        license_name="CC-BY-SA-4.0",
    )
    _write_registry(data_dir, "visuals", {"doi:10.1234/visual": visual})

    captured: list[dict | None] = []
    original_card = build_pages._paper_card

    def capture_card(*args, **kwargs):
        captured.append(kwargs.get("visual"))
        return original_card(*args, **kwargs)

    monkeypatch.setattr(build_pages, "_paper_card", capture_card)
    build_pages.build(
        docs_dir, DIRECTIONS, data_dir=data_dir, sharded_daily=True,
    )

    day_record = json.loads(
        (docs_dir / "data" / "day" / "2026-08-12" / "page-1.json")
        .read_text(encoding="utf-8")
    )["papers"][0]
    queue_record = json.loads(
        (docs_dir / "queue-high-2026.json").read_text(encoding="utf-8")
    )[0]
    search_record = json.loads(
        (docs_dir / "search-index-2026.json").read_text(encoding="utf-8")
    )[0]

    assert day_record["visual"] == queue_record["visual"]
    assert day_record["visual"]["image_url"] == visual["image_url"]
    assert captured and captured[0] == day_record["visual"]
    assert "visual" not in search_record


def test_legacy_embedded_day_receives_same_registry_visual(tmp_path, monkeypatch):
    data_dir = tmp_path / "data"
    docs_dir = tmp_path / "docs"
    _write_corpus(data_dir)
    visual = _available_visual(
        image_url="https://arxiv.org/html/2608.12345/figure.png",
        source_url="https://arxiv.org/abs/2608.12345",
    )
    _write_registry(data_dir, "figures", {"doi:10.1234/visual": visual})

    captured: list[dict | None] = []
    original_card = build_pages._paper_card

    def capture_card(*args, **kwargs):
        captured.append(kwargs.get("visual"))
        return original_card(*args, **kwargs)

    monkeypatch.setattr(build_pages, "_paper_card", capture_card)
    build_pages.build(docs_dir, DIRECTIONS, data_dir=data_dir)

    assert len(captured) >= 2  # embedded daily page and recent-run workbench
    assert all(item and item["image_url"] == visual["image_url"]
               for item in captured)
