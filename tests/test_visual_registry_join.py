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

THIRD_PARTY_PRODUCTION_CAPTIONS = (
    "Copyright: Dietmar Schulze.",
    "Created with BioRender.com (License number: AV27FQ9RWZ).",
    "Created in BioRender. Crook, J. (https://BioRender.com/e8aq7lf).",
    "Principle of SBO, reproduced from [12].",
    "Figure 3: From Keil et al. 2021: On the floor with domain Ω.",
    "Reference measurements from Choi et al. of wake characteristics.",
    "Biomaterial ink synthesis workflow (made using Illustrae [29]).",
    "Topographic map of water catchment (45, source:).",
    "BEAR for studying the mechanics of additively manufactured components. "
    "(Photo credit: Aldair E. Gongora and Bowen Xu, Boston University).",
    "Image by Example Artist.",
    "Photograph by Example Photographer.",
    "Illustration by Example Studio.",
    "Graphic—by Example Agency.",
    "The three-dimensional printing protocol developed by MX3D uses a weld "
    "head attached to a robotic arm (image by Joris Laarman, "
    "www.jorislaarman.com).",
)


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
        "selector_version": 2,
        "selector_error_at": "2026-08-12T11:00:00Z",
        "selector_error_reason": "must-not-be-public",
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


def test_public_svg_visual_requires_verified_arxiv_shape_and_dimensions():
    base = {
        **_available_visual(
            image_url=(
                "https://arxiv.org/html/2608.12345v2/figures/workflow.svg"
            ),
            source_url="https://arxiv.org/abs/2608.12345",
        ),
        "provider": "arxiv",
        "media_type": "image/svg+xml",
        "width": 900,
        "height": 600,
    }
    safe = build_pages._safe_visual_record(base)
    assert safe is not None
    assert safe["media_type"] == "image/svg+xml"

    unsafe_variants = (
        {"media_type": "image/png"},
        {"provider": "pmc"},
        {"image_url": "https://export.arxiv.org/html/2608.12345v2/f.svg"},
        {"image_url": "https://arxiv.org/html/2608.12345/f.svg"},
        {"image_url": "https://arxiv.org/html/2608.12345v0/f.svg"},
        {"image_url": "https://arxiv.org/html/2608.54321v1/f.svg"},
        {"image_url": "https://arxiv.org/html/2608.12345v2/../evil.svg"},
        {"image_url": "https://arxiv.org/html/2608.12345v2//evil.svg"},
        {"image_url": "https://arxiv.org:443/html/2608.12345v2/f.svg"},
        {"image_url": "https://arxiv.org/html/2608.12345v2/f.svg?raw=1"},
        {"image_url": "https://arxiv.org/html/2608.12345v2/f%2esvg"},
        {"source_url": "https://publisher.example/article"},
        {"source_url": "https://arxiv.org/abs/2608.12345?download=1"},
        {"caption": "Figure 1: Architecture adopted from [23]."},
        {"width": 20, "height": 20},
        {"width": None},
    )
    for changes in unsafe_variants:
        assert build_pages._safe_visual_record({**base, **changes}) is None


def test_public_raster_media_type_must_match_file_suffix():
    base = _available_visual(
        image_url="https://arxiv.org/html/2608.12345/figure.png",
        source_url="https://arxiv.org/abs/2608.12345",
    )
    assert build_pages._safe_visual_record({
        **base, "media_type": "image/png",
    }) is not None
    assert build_pages._safe_visual_record({
        **base, "media_type": "image/jpeg",
    }) is None


def test_public_visual_boundary_rejects_rights_in_caption_or_alt():
    base = _available_visual(
        image_url="https://arxiv.org/html/2608.12345/figure.png",
        source_url="https://arxiv.org/abs/2608.12345",
    )
    for text in THIRD_PARTY_PRODUCTION_CAPTIONS:
        assert build_pages._safe_visual_record({
            **base, "caption": text, "alt": "Scientific result",
        }) is None
        assert build_pages._safe_visual_record({
            **base, "caption": "Scientific result", "alt": text,
        }) is None

    assert build_pages._safe_visual_record({
        **base,
        "caption": "Figure 1: Scientific result.",
        "alt": "Stress field",
        "source_label": "Photograph by Example Photographer",
    }) is None

    assert build_pages._safe_visual_record({
        **base,
        "caption": "Figure 1: Scientific result.",
        "alt": "Stress field",
        "source_label": "Image by Example Artist",
    }) is None

    assert build_pages._safe_visual_record({
        **base,
        "caption": "Figure 1: Image generated by the surrogate model.",
        "alt": "Stress field",
        "source_label": "arXiv · 论文插图",
    }) is not None

    for direct_credit in (
        "Diagram by: 'ana pérez'.",
        "Artwork by © naïve atelier.",
        "Photograph created by mélange studio.",
        "Figure made by “mixedCase collective”.",
        "Illustration provided by 株式会社アート.",
        "Graphic supplied by 李明.",
    ):
        assert build_pages._safe_visual_record({
            **base, "caption": direct_credit, "alt": "Scientific result",
        }) is None

    for scientific_phrase in (
        "Figure 2: image by Fourier transformation.",
        "Figure 2: image by inverse Fourier transformation.",
        "Figure 2: image by FFT.",
        "Figure 2: image by PCA.",
        "Figure 2: image by finite element analysis.",
        "Figure 2: image by Bayesian optimization.",
        "Figure 2: image by Design A.",
        "Figure 2: Image by Applying a Fourier transform.",
        "Figure 2: image by applying a Gaussian filter.",
        "Figure 2: image generated by the surrogate model.",
        "Figure 2: image produced by model predictions.",
        "The image bytes are decoded before plotting.",
        "Each image byte is normalized independently.",
        "The figure bypasses the interpolation stage.",
        "The graphic byproduct is removed during preprocessing.",
    ):
        assert build_pages._safe_visual_record({
            **base, "caption": scientific_phrase,
            "alt": "Scientific result",
        }) is not None


def test_public_visual_boundary_requires_caption_but_not_useful_alt():
    base = _available_visual(
        image_url="https://arxiv.org/html/2608.12345/figure.png",
        source_url="https://arxiv.org/abs/2608.12345",
    )
    for caption in (
        "", "   ", "[Uncaptioned image]", "See caption.",
        "Figure 1:", "Graphical abstract:", "[No caption available]",
        "Uncaptioned photograph",
    ):
        assert build_pages._safe_visual_record({
            **base, "caption": caption,
        }) is None

    safe = build_pages._safe_visual_record({
        **base,
        "caption": "Figure 1: Validated scientific result.",
        "alt": "[Uncaptioned image]",
    })
    assert safe is not None
    assert "alt" not in safe


def test_public_visual_boundary_temporarily_hides_arxiv_table_thumbnails():
    base = _available_visual(
        image_url="https://arxiv.org/html/2608.12345/figure.png",
        source_url="https://arxiv.org/abs/2608.12345",
    )
    for caption in (
        "Table 1: Simulation datasets used for experiments.",
        "Tab. IV: Overview of the material parameters.",
    ):
        assert build_pages._safe_visual_record({
            **base, "provider": "arxiv", "caption": caption,
        }) is None

    for caption in (
        "Figure 2: Results are summarized in Table 1.",
        "Figure 3: Normalized prediction error.",
        "The table-driven method produces this validated stress field.",
    ):
        assert build_pages._safe_visual_record({
            **base, "provider": "arxiv", "caption": caption,
        }) is not None

    # JATS figures have their own structural selector; a PMC scientific figure
    # is not suppressed merely because its caption happens to start this way.
    assert build_pages._safe_visual_record({
        **base, "provider": "pmc",
        "caption": "Table 1: Simulation datasets used for experiments.",
    }) is not None


def test_risky_existing_registry_never_reaches_public_card_surfaces(
        tmp_path, monkeypatch):
    data_dir = tmp_path / "data"
    docs_dir = tmp_path / "site"
    papers = []
    records = {}
    image_urls = []
    for index, caption in enumerate(THIRD_PARTY_PRODUCTION_CAPTIONS):
        paper = dict(_paper())
        paper["doi"] = f"10.1234/risky-{index}"
        paper["title"] = f"Risky visual {index}"
        papers.append(paper)
        image_url = f"https://arxiv.org/html/2608.12345/risky-{index}.png"
        image_urls.append(image_url)
        records[f"doi:10.1234/risky-{index}"] = {
            **_available_visual(
                image_url=image_url,
                source_url="https://arxiv.org/abs/2608.12345",
            ),
            "caption": caption,
        }

    daily = data_dir / "daily"
    daily.mkdir(parents=True)
    (daily / "2026-08-12.json").write_text(json.dumps({
        "schema_version": "v2", "date": "2026-08-12",
        "date_precision": "day", "papers": papers,
    }), encoding="utf-8")
    manifests = data_dir / "manifests"
    manifests.mkdir(parents=True)
    (manifests / "2026-08-12.json").write_text(json.dumps({
        "run_status": "success", "quality_flags": [],
    }), encoding="utf-8")
    _write_registry(data_dir, "visuals", records)

    captured: list[dict | None] = []
    original_card = build_pages._paper_card

    def capture_card(*args, **kwargs):
        captured.append(kwargs.get("visual"))
        return original_card(*args, **kwargs)

    monkeypatch.setattr(build_pages, "_paper_card", capture_card)
    build_pages.build(
        docs_dir, DIRECTIONS, data_dir=data_dir, sharded_daily=True,
    )

    day = json.loads(
        (docs_dir / "data" / "day" / "2026-08-12" / "page-1.json")
        .read_text(encoding="utf-8")
    )["papers"]
    queue = json.loads(
        (docs_dir / "queue-high-2026.json").read_text(encoding="utf-8")
    )
    search = json.loads(
        (docs_dir / "search-index-2026.json").read_text(encoding="utf-8")
    )
    workbench = (docs_dir / "index.html").read_text(encoding="utf-8")

    assert len(day) == len(queue) == len(search) == len(papers)
    assert all("visual" not in record for record in day)
    assert all("visual" not in record for record in queue)
    assert all("visual" not in record for record in search)
    assert captured and all(visual is None for visual in captured)
    assert all(image_url not in workbench for image_url in image_urls)
    assert "暂时没有获取到图片" in workbench


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
