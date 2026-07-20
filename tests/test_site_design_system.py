from __future__ import annotations

import pathlib
import re


ROOT = pathlib.Path(__file__).resolve().parent.parent
CSS = (ROOT / "render" / "static" / "radar-ui.css").read_text(
    encoding="utf-8"
)
QUEUE_JS = (ROOT / "render" / "static" / "radar-queue.js").read_text(
    encoding="utf-8"
)
SEARCH_JS = (ROOT / "render" / "static" / "radar-search.js").read_text(
    encoding="utf-8"
)
SEARCH_WORKER_JS = (
    ROOT / "render" / "static" / "radar-search-worker.js"
).read_text(encoding="utf-8")


def _luminance(hex_color: str) -> float:
    channels = [int(hex_color[index:index + 2], 16) / 255
                for index in (1, 3, 5)]
    linear = [value / 12.92 if value <= 0.04045
              else ((value + 0.055) / 1.055) ** 2.4
              for value in channels]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def _contrast(foreground: str, background: str) -> float:
    first, second = _luminance(foreground), _luminance(background)
    return (max(first, second) + 0.05) / (min(first, second) + 0.05)


def _token(name: str) -> str:
    match = re.search(rf"--{re.escape(name)}:\s*(#[0-9a-f]{{6}})", CSS, re.I)
    assert match, f"missing CSS token --{name}"
    return match.group(1)


def test_core_text_and_priority_pairs_meet_wcag_aa_contrast():
    pairs = [
        ("c-text-primary", "c-bg"),
        ("c-text-meta", "c-bg"),
        ("c-priority-h", "c-priority-h-bg"),
        ("c-priority-m", "c-priority-m-bg"),
        ("c-priority-l", "c-priority-l-bg"),
        ("c-priority-x", "c-priority-x-bg"),
    ]
    for foreground, background in pairs:
        assert _contrast(_token(foreground), _token(background)) >= 4.5


def test_readability_and_mobile_contracts_are_present():
    assert "font: 16px/1.62" in CSS
    assert ".paper-title" in CSS and "font-size: 17px" in CSS
    assert ".meta" in CSS and "font-size: 12.5px" in CSS
    assert ".summary { font-size: 14px; line-height: 1.52; }" in CSS
    assert "min-height: 36px" in CSS
    assert "@media (max-width: 760px)" in CSS
    assert "@media (max-width: 460px)" in CSS


def test_paper_cards_use_two_columns_with_mobile_fallback():
    assert ".paper-grid" in CSS
    assert "grid-template-columns: repeat(2, minmax(0, 1fr))" in CSS
    assert ".paper-grid { grid-template-columns: 1fr; }" in CSS


def test_lazy_queue_builds_untrusted_records_with_dom_text_nodes():
    assert "textContent" in QUEUE_JS
    assert "document.createTextNode" in QUEUE_JS
    assert "innerHTML" not in QUEUE_JS
    assert "PAGE_SIZE = 25" in QUEUE_JS


def test_search_is_progressive_worker_backed_and_dom_safe():
    assert 'new Worker("radar-search-worker.js")' in SEARCH_JS
    assert 'fetch("search-index-manifest.json")' in SEARCH_JS
    assert 'fetch("search-index-" + selectedYear + ".json")' in SEARCH_JS
    assert 'fetch("search-deep-" + selectedYear + ".json")' in SEARCH_JS
    assert "setTimeout(sendSearch, 180)" in SEARCH_JS
    assert "textContent" in SEARCH_JS
    assert "innerHTML" not in SEARCH_JS
    assert "_search_blob" in SEARCH_WORKER_JS
    assert "deep_blob" in SEARCH_WORKER_JS
