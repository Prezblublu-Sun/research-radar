"""Visual-panel contracts shared by static and lazy paper cards."""

from __future__ import annotations

import pathlib
import sys


ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from render import build_pages  # noqa: E402


CARD_JS = (ROOT / "render" / "static" / "radar-card.js").read_text(
    encoding="utf-8"
)
CSS = (ROOT / "render" / "static" / "radar-ui.css").read_text(
    encoding="utf-8"
)


def _paper() -> dict:
    return {
        "source": "arxiv",
        "doi": "10.1/visual",
        "title": "Compact visual card",
        "authors": ["A. Author"],
        "venue": "Test Venue",
        "date": "2026-08-12",
        "direction": "fea_surrogate",
        "direction_name": "FEA & Surrogate",
        "llm": {
            "priority": "High",
            "summary_zh": {"motivation": "动机", "method": "方法"},
            "summary_en": {},
            "flags": {},
        },
    }


def _available_visual() -> dict:
    return {
        "status": "available",
        "image_url": "https://arxiv.org/html/2608.00001/figure-1.png",
        "caption": "Figure <1> & validation",
        "source_label": "arXiv & Figure 1",
        "source_url": "https://arxiv.org/abs/2608.00001",
        "license": "CC BY 4.0",
        "alt": "A surrogate-model validation chart",
        "width": 1200,
        "height": 800,
    }


def test_static_card_renders_compact_accessible_visual_panel():
    rendered = build_pages._paper_card(
        _paper(), "#123456", visual=_available_visual()
    )
    assert 'class="paper-body"' in rendered
    assert 'class="paper-copy"' in rendered
    assert 'class="paper-visual"' in rendered
    assert 'data-visual-status="available"' in rendered
    assert 'loading="lazy"' in rendered
    assert 'decoding="async"' in rendered
    assert 'width="1200"' in rendered and 'height="800"' in rendered
    assert 'alt="A surrogate-model validation chart"' in rendered
    assert "Figure &lt;1&gt; &amp; validation" in rendered
    assert "arXiv &amp; Figure 1" in rendered
    assert 'rel="noopener noreferrer"' in rendered
    assert 'class="paper-visual__image-link" href="https://arxiv.org/html/2608.00001/figure-1.png"' in rendered
    assert 'aria-label="查看原图"' in rendered
    assert 'class="paper-visual__source" href="https://arxiv.org/abs/2608.00001"' in rendered


def test_static_card_missing_or_unsafe_visual_has_explicit_fallback():
    missing = build_pages._paper_card(_paper(), "#123456")
    unsafe = build_pages._paper_card(_paper(), "#123456", visual={
        "status": "available",
        "image_url": "javascript:alert(1)",
        "source_url": "javascript:alert(2)",
        "license": "CC BY 4.0",
    })
    for rendered in (missing, unsafe):
        assert 'class="paper-visual paper-visual--empty"' in rendered
        assert "暂时没有获取到图片" in rendered
        assert "javascript:" not in rendered


def test_lazy_renderer_uses_same_safe_visual_and_error_contract():
    for token in (
        "record.visual", "record.figure", 'image.loading = "lazy"',
        'image.decoding = "async"', 'image.referrerPolicy = "no-referrer"',
        'addEventListener("error"',
        "暂时没有获取到图片", "noopener noreferrer",
        'imageLink.href = imageUrl', 'aria-label", "查看原图',
        "ensureVisualViewer", 'dialog.showModal()',
        'viewer.source.hidden = !sourceUrl',
        'document.documentElement.contains(visualViewerState.trigger)',
        'querySelectorAll(".paper-visual img")',
        '"pmc-oa-opendata.s3.amazonaws.com": true',
        "visualImageHosts[parsed.hostname.toLowerCase()]",
    ):
        assert token in CARD_JS
    assert "innerHTML" not in CARD_JS
    assert "javascript:" not in CARD_JS


def test_legacy_embedded_day_loads_shared_broken_image_fallback():
    rendered = build_pages._render_daily_embedded(
        [], "2026-08-12", {}, ["2026-08-12"], None
    )
    assert rendered.count('<script src="radar-card.js" defer></script>') == 1


def test_visual_css_is_compact_responsive_and_preserves_scientific_figures():
    assert ".paper-body" in CSS
    assert "grid-template-columns: minmax(0, 1fr)" in CSS
    assert ".paper-visual__frame" in CSS
    assert "height: 132px" in CSS
    assert "object-fit: contain" in CSS
    assert 'content: "原图 ↗"' in CSS
    assert "cursor: zoom-in" in CSS
    assert ".paper-visual-viewer::backdrop" in CSS
    assert "max-height: 92vh" in CSS
    assert ".paper-visual-viewer__viewport" in CSS
    assert "@media (min-width: 761px) and (max-width: 1000px)" in CSS
    assert "@media (max-width: 460px)" in CSS
    assert ".paper-visual { order: -1" in CSS


def test_visual_public_text_truncation_uses_a_readable_boundary():
    caption = ("finite element validation results " * 30).strip()
    alt = ("surrogate model response field " * 20).strip()
    safe = build_pages._safe_visual_record({
        **_available_visual(), "caption": caption, "alt": alt,
    })
    assert safe is not None
    assert len(safe["caption"]) <= 600
    assert len(safe["alt"]) <= 300
    assert safe["caption"].endswith("…")
    assert safe["alt"].endswith("…")
    assert safe["caption"][:-1].endswith(("results", "validation", "element", "finite"))


def test_placeholder_alt_is_replaced_by_the_paper_title():
    rendered = build_pages._paper_card(
        _paper(), "#123456", visual={
            **_available_visual(), "alt": "Refer to caption",
        },
    )
    assert 'alt="论文插图：Compact visual card"' in rendered
    assert "Refer to caption" not in rendered
    assert "usefulVisualAlt" in CARD_JS
