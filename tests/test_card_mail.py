"""ADR-0016 addendum 2026-09-22: the per-card D5 control mails the card
instead of queueing it for lit-system.

Run with:
    pytest tests/test_card_mail.py
"""
from __future__ import annotations

import pathlib
import sys

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from render import build_pages  # noqa: E402

STATIC = REPO_ROOT / "render" / "static"
CARD_JS = (STATIC / "radar-card.js").read_text(encoding="utf-8")
UI_JS = (STATIC / "radar-ui.js").read_text(encoding="utf-8")
UI_CSS = (STATIC / "radar-ui.css").read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# the button itself
# ---------------------------------------------------------------------------

def test_both_card_renderers_emit_the_mail_button():
    assert 'element("button", "rui-mail-btn", "发送到邮箱")' in CARD_JS
    tools = build_pages._card_tools({"doi": "10.1/x", "title": "T"})
    assert 'class="rui-mail-btn"' in tools
    assert "发送到邮箱" in tools


def test_the_promote_control_is_gone_everywhere():
    for blob, name in ((CARD_JS, "radar-card.js"), (UI_JS, "radar-ui.js"),
                       (UI_CSS, "radar-ui.css")):
        assert "rui-promote-btn" not in blob, name
        assert "radar:promote-queue" not in blob, name
        assert "rui-copy-promotes" not in blob, name
    # The label is gone from everything the reader sees; radar-ui.js keeps one
    # comment naming what the mail button replaced.
    assert "lit-system" not in CARD_JS and "lit-system" not in UI_CSS
    assert UI_JS.count("lit-system") == 1
    assert not hasattr(build_pages, "_render_my_promotes_page")
    assert "rui-promote-btn" not in build_pages._card_tools({"doi": "10.1/x"})


def test_mail_button_styling_replaced_the_queued_styling():
    assert ".rui-note-btn, .rui-mail-btn, .rui-btn {" in UI_CSS
    assert ".rui-mail-btn.rui-mailed" in UI_CSS
    assert "rui-queued" not in UI_CSS


# ---------------------------------------------------------------------------
# the composer contract
# ---------------------------------------------------------------------------

def test_composer_targets_the_owner_without_a_literal_address():
    assert '"sun1139156053"' in UI_JS and '"163.com"' in UI_JS
    # The full address must not appear as one string for naive scrapers.
    assert "sun1139156053@163.com" not in UI_JS
    assert 'MAIL_LOCAL + "@" + MAIL_DOMAIN' in UI_JS


def test_composer_uses_mailto_and_budgets_the_url():
    assert '"mailto:" + mailAddress()' in UI_JS
    assert "encodeURIComponent(subject)" in UI_JS
    assert "encodeURIComponent(body)" in UI_JS
    assert "MAIL_URL_BUDGET" in UI_JS
    # The budget must be conservative enough for the Windows shell handler.
    budget = int(UI_JS.split("var MAIL_URL_BUDGET =")[1].split(";")[0].strip())
    assert 500 <= budget <= 2000


def test_composer_copies_the_untruncated_text_and_flags_truncation():
    assert "navigator.clipboard.writeText(full)" in UI_JS
    assert "其余内容已复制到剪贴板" in UI_JS
    # The truncation note is appended after the fill loop, so its encoded
    # length must be reserved or the finished URL overshoots the budget.
    assert "var reserve = encodeURIComponent(MAIL_TRUNCATED_NOTE).length" in UI_JS
    assert "+ reserve <= MAIL_URL_BUDGET" in UI_JS


def test_an_oversized_section_is_shortened_rather_than_dropped():
    # One Chinese paragraph costs ~1,000 characters percent-encoded, so a
    # whole-section drop would leave the mail with only the title and links.
    composer = UI_JS.split("function sendCardByMail")[1].split("// ---- D4 + D5")[0]
    assert "var shortened = section;" in composer
    assert "shortened.slice(0, Math.floor(shortened.length * 0.8))" in composer
    assert '+ shortened + "…"' in composer or '+ shortened + "…"' in composer
    assert "while (shortened.length > 24)" in composer
    # Clipboard failure must not swallow the "mail opened" feedback.
    assert UI_JS.count('flash("✓ 已打开邮件")') >= 2


def test_composer_collects_the_card_fields_worth_mailing():
    for selector in (".paper-title", ".authors", ".venue", ".relevance",
                     ".summary", ".why-not-core", ".doi a"):
        assert selector in UI_JS, selector
    for label in ("标题：", "原文：", "雷达卡片：", "身份键：", "我的笔记：",
                  "中文摘要："):
        assert label in UI_JS, label
    assert "markRecord(idkey)" in UI_JS  # the reader's own note travels along


def test_composer_stays_dom_safe():
    composer = UI_JS.split("function sendCardByMail")[1].split("// ---- D4 + D5")[0]
    assert "innerHTML" not in composer
    assert "createElement" in composer  # the mailto anchor is built as a node


# ---------------------------------------------------------------------------
# pages
# ---------------------------------------------------------------------------

def test_library_page_drops_the_queue_panel_and_explains_the_button():
    library = build_pages._render_library_page()
    assert 'id="rui-copy-promotes"' not in library
    assert 'id="rui-clear-promotes"' not in library
    assert "lit-system" not in library
    assert "待导入队列" not in library
    assert "发送到邮箱" in library
    assert 'id="marks"' in library  # the marks panel survives untouched


def test_old_promote_url_redirects_to_the_library(tmp_path):
    build_pages.build(tmp_path, {"fea_surrogate": {"display_name": "FEA",
                                                   "color": "#345678"}},
                      sharded_daily=True)
    redirect = (tmp_path / "my-promotes.html").read_text(encoding="utf-8")
    assert 'url=library.html"' in redirect
    assert "library.html#promote" not in redirect


def test_pipeline_handoff_contract_is_untouched():
    # SCOPE.md's Radar -> lit-system export is a separate contract; removing
    # the browser button must not have removed it.
    assert (REPO_ROOT / "pipeline" / "export_candidates.py").exists()
