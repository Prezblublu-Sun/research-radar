"""A deploy must reach a browser that already has the site.

GitHub Pages serves the bundles with `Cache-Control: max-age=600` and the
pages used to reference them by bare name, so a behaviour change took up to
ten minutes to reach a returning reader — longer while a tab stayed open.
On 2026-09-26 that turned into "still can't see it" about a fix that had
already deployed: the HTML was new, the cached radar-day.js was not.

Every reference now carries the file's content hash, so a changed bundle is
a changed URL.

Run with:
    pytest tests/test_asset_cache_busting.py
"""
from __future__ import annotations

import pathlib
import re
import sys

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from render import build_pages  # noqa: E402

STATIC = REPO_ROOT / "render" / "static"
BUNDLES = ["radar-ui.css", "radar-ui.js", "radar-card.js", "radar-day.js",
           "radar-queue.js", "radar-search.js", "radar-reading.js"]

PAGES = {
    "daily": lambda: build_pages._render_daily(
        [], "2026-09-25", {}, ["2026-09-25"], None),
    "queue": build_pages._render_queue_page,
    "reading": build_pages._render_reading_page,
    "library": build_pages._render_library_page,
    "random": lambda: build_pages._render_random_reading_page([], {}),
}


@pytest.mark.parametrize("name", BUNDLES)
def test_every_bundle_url_carries_its_content_hash(name):
    version = build_pages._asset_version(name)
    assert re.fullmatch(r"[0-9a-f]{10}", version), name
    assert build_pages._asset(name) == f"{name}?v={version}"


def test_the_hash_actually_follows_the_content(tmp_path, monkeypatch):
    before = build_pages._asset_version("radar-ui.js")
    # Same file, same answer — the cache must not make it drift.
    assert build_pages._asset_version("radar-ui.js") == before
    # A different file, a different answer.
    assert build_pages._asset_version("radar-day.js") != before


def test_a_missing_bundle_degrades_to_an_unversioned_url():
    # Better a stale cache than a 404 on a name that does not exist.
    assert build_pages._asset_version("not-a-bundle.js") == ""
    assert build_pages._asset("not-a-bundle.js") == "not-a-bundle.js"


@pytest.mark.parametrize("page", sorted(PAGES))
def test_no_page_references_a_bundle_without_a_version(page):
    html = PAGES[page]()
    for name in BUNDLES:
        for bare in (f'src="{name}"', f'href="{name}"'):
            assert bare not in html, f"{page} references {name} unversioned"
    assert "radar-ui.js?v=" in html


def test_the_search_worker_inherits_the_bundle_version():
    # It is fetched by radar-search.js, not by the page, so the page's ?v=
    # cannot reach it on its own — it reads it off its own <script> tag.
    source = (STATIC / "radar-search.js").read_text(encoding="utf-8")
    assert 'new Worker("radar-search-worker.js" + assetQuery)' in source
    assert "document.currentScript && document.currentScript.src" in source
    assert 'var at = src.indexOf("?");' in source


def test_every_shipped_bundle_is_actually_copied_into_the_artifact():
    # A versioned URL for a file the build never copies is a 404, which is
    # worse than the stale cache this replaces.
    copied = build_pages._copy_static_assets.__doc__ is not None
    source = (REPO_ROOT / "render" / "build_pages.py").read_text(encoding="utf-8")
    block = source.split("def _copy_static_assets")[1].split("def ")[0]
    for name in BUNDLES + ["radar-search-worker.js"]:
        assert f'"{name}"' in block, name
    assert copied
