"""Every shipped JS bundle has to parse.

The rest of the suite asserts the *contents* of these files with string
matching, which happily passes on a file the browser refuses to run. Only
radar-card.js was ever executed (by test_visual_card_ui, in node), so a stray
brace in radar-queue.js or radar-ui.js could ship silently and take the whole
page's behaviour with it — the pages are static, so there is no build step to
catch it either.

`node --check` parses without executing. It is present on the CI runner; a
developer machine without node skips these.

Run with:
    pytest tests/test_static_bundles_parse.py
"""
from __future__ import annotations

import pathlib
import shutil
import subprocess

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
STATIC = ROOT / "render" / "static"
BUNDLES = sorted(STATIC.glob("*.js"))

node = pytest.mark.skipif(shutil.which("node") is None,
                          reason="node is not installed on this machine")


def test_the_bundles_are_all_found():
    # A rename that this test then silently stops covering is the failure
    # mode worth guarding; the names are stable and few.
    assert {path.name for path in BUNDLES} == {
        "radar-card.js", "radar-day.js", "radar-queue.js", "radar-reading.js",
        "radar-search-worker.js", "radar-search.js", "radar-ui.js",
    }


@node
@pytest.mark.parametrize("path", BUNDLES, ids=lambda p: p.name)
def test_the_bundle_parses(path: pathlib.Path):
    result = subprocess.run(["node", "--check", str(path)],
                            capture_output=True, text=True)
    assert result.returncode == 0, f"{path.name} does not parse:\n{result.stderr}"
