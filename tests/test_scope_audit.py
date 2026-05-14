"""Tests for pipeline/scope_audit.py.

Covers each violation category with synthetic fixtures, plus the SCOPE.md
section anchor contract (the test that fails if SCOPE.md drifts away from
the rule catalog's scope_ref leaves).

Run with:
    pytest tests/test_scope_audit.py
"""
from __future__ import annotations

import json
import pathlib
import sys
import textwrap

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from pipeline import scope_audit as sa  # noqa: E402


# ============================================================================
# Helpers
# ============================================================================

def _write(p: pathlib.Path, content: str) -> pathlib.Path:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(textwrap.dedent(content).lstrip("\n"), encoding="utf-8")
    return p


def _run(tmp_path: pathlib.Path, strict: bool = False) -> tuple[int, dict]:
    out_path = tmp_path / "audit.json"
    argv = ["--repo-root", str(tmp_path),
            "--output", str(out_path),
            "--quiet"]
    if strict:
        argv.append("--strict")
    rc = sa.main(argv)
    data = json.loads(out_path.read_text())
    return rc, data


def _violations_with(report: dict, rule_id: str) -> list[dict]:
    return [v for v in report["violations"] if v["rule_id"] == rule_id]


@pytest.fixture
def tmp_repo(tmp_path: pathlib.Path) -> pathlib.Path:
    return tmp_path


# ============================================================================
# Clean baseline
# ============================================================================

def test_clean_repo_no_violations(tmp_repo):
    _write(tmp_repo / "pipeline" / "ok.py", """
        import os
        import json
        from openai import OpenAI

        MODEL = "deepseek-chat"
        BASE_URL = "https://api.deepseek.com"

        def score_paper(text: str) -> dict:
            return {"priority": "Medium"}
    """)
    rc, rep = _run(tmp_repo)
    assert rc == 0
    assert rep["summary"]["errors"] == 0
    assert rep["summary"]["warnings"] == 0
    assert rep["violations"] == []


# ============================================================================
# FI -- forbidden imports
# ============================================================================

@pytest.mark.parametrize("module, expected_rule", [
    ("docling",               "FI001"),
    ("pypdf",                 "FI001"),
    ("pdfplumber",            "FI001"),
    ("chromadb",              "FI002"),
    ("qdrant_client",         "FI002"),
    ("sentence_transformers", "FI003"),
    ("transformers",          "FI003"),
    ("ollama",                "FI004"),
    ("llama_cpp",             "FI004"),
    ("torch",                 "FI005"),
    ("tensorflow",            "FI005"),
    ("langchain",             "FI006"),
    ("fastapi",               "FI007"),
])
def test_FI_import_triggers_error(tmp_repo, module, expected_rule):
    _write(tmp_repo / "pipeline" / "x.py", f"import {module}\n")
    rc, rep = _run(tmp_repo)
    assert rc == 1
    vs = _violations_with(rep, expected_rule)
    assert len(vs) == 1
    assert vs[0]["severity"] == "error"
    assert module in vs[0]["matched_text"]


def test_FI_from_import_form(tmp_repo):
    _write(tmp_repo / "pipeline" / "x.py", "from chromadb.utils import embedding_functions\n")
    rc, rep = _run(tmp_repo)
    assert rc == 1
    vs = _violations_with(rep, "FI002")
    assert len(vs) == 1
    assert "chromadb" in vs[0]["matched_text"]


# ============================================================================
# LE -- LLM endpoints / model identifiers
# ============================================================================

def test_LE001_localhost_ollama_endpoint(tmp_repo):
    _write(tmp_repo / "pipeline" / "x.py", """
        URL = "http://localhost:11434/api/generate"
    """)
    rc, rep = _run(tmp_repo)
    assert rc == 1
    vs = _violations_with(rep, "LE001")
    assert len(vs) == 1
    assert vs[0]["severity"] == "error"


def test_LE002_qwen_in_model_assignment(tmp_repo):
    _write(tmp_repo / "pipeline" / "x.py", """
        MODEL = "qwen2.5-14b-32k"
    """)
    rc, rep = _run(tmp_repo)
    assert rc == 1
    vs = _violations_with(rep, "LE002")
    assert len(vs) == 1
    assert vs[0]["severity"] == "error"


def test_LE002_llama_in_base_url(tmp_repo):
    _write(tmp_repo / "pipeline" / "x.py", """
        base_url = "http://api.llama-server.local"
    """)
    rc, rep = _run(tmp_repo)
    assert rc == 1
    vs = _violations_with(rep, "LE002")
    assert len(vs) == 1


def test_LE003_qwen_outside_model_context_is_warning(tmp_repo):
    _write(tmp_repo / "pipeline" / "x.py", """
        comment = "We previously experimented with qwen2.5 but switched."
    """)
    rc, rep = _run(tmp_repo)
    assert rc == 0  # warning does not fail
    vs = _violations_with(rep, "LE003")
    assert len(vs) == 1
    assert vs[0]["severity"] == "warning"


# ============================================================================
# OP -- forbidden output paths
# ============================================================================

@pytest.mark.parametrize("path_literal", [
    "data/chroma_db/collection",
    "data/chunks/P1.jsonl",
    "data/embeddings/vec.npy",
    "data/docling/output.json",
    "assets/chroma_db",
    "metadata/P42.json",
])
def test_OP001_litsystem_paths(tmp_repo, path_literal):
    _write(tmp_repo / "pipeline" / "x.py", f"""
        PATH = "{path_literal}"
    """)
    rc, rep = _run(tmp_repo)
    assert rc == 1
    vs = _violations_with(rep, "OP001")
    assert len(vs) == 1
    assert path_literal in vs[0]["matched_text"]


def test_OP001_does_not_fire_on_safe_paths(tmp_repo):
    _write(tmp_repo / "pipeline" / "x.py", """
        OK1 = "data/daily/2026-05-14.json"
        OK2 = "data/exports/candidates.jsonl"
        OK3 = "data/manifests/x.json"
    """)
    rc, rep = _run(tmp_repo)
    assert rc == 0
    assert _violations_with(rep, "OP001") == []


# ============================================================================
# IK -- identifier keywords
# ============================================================================

@pytest.mark.parametrize("identifier", [
    "docling_extract",
    "DoclingParser",
    "chroma_client",
    "ChromaDB",
    "pdf_parse",
    "parse_pdf_text",
    "ocr_engine",
])
def test_IK001_strict_identifier(tmp_repo, identifier):
    _write(tmp_repo / "pipeline" / "x.py", f"""
        def {identifier if not identifier[0].isupper() else identifier.lower() + '_fn'}():
            pass

        class {identifier if identifier[0].isupper() else identifier.title()}Class:
            pass

        {identifier if not identifier[0].isupper() else identifier.lower() + '_var'} = 1
    """)
    rc, rep = _run(tmp_repo)
    vs = _violations_with(rep, "IK001")
    assert len(vs) >= 1, f"expected IK001 fire for {identifier}"
    assert vs[0]["severity"] == "error"


@pytest.mark.parametrize("identifier", [
    "chunk_size",
    "chunks_dir",
    "build_chunks",
    "embedding_model_name",
    "embed_text",
    "vector_store_path",
    "rag_pipeline",
    "RagChain",
])
def test_IK002_loose_identifier(tmp_repo, identifier):
    _write(tmp_repo / "pipeline" / "x.py", f"""
        {identifier} = 1
    """)
    rc, rep = _run(tmp_repo)
    # Loose is WARN; rc should be 0 in non-strict mode
    assert rc == 0
    vs = _violations_with(rep, "IK002")
    assert len(vs) == 1, f"expected IK002 fire for {identifier}"
    assert vs[0]["severity"] == "warning"


def test_IK_does_not_fire_on_safe_identifiers(tmp_repo):
    _write(tmp_repo / "pipeline" / "x.py", """
        def score_paper(): pass
        def fetch_papers(): pass
        class DirectionRouter: pass

        institution = "UCL"
        first_author_affiliation = ""
        corresponding_authors = []
        priority_counts = {}
    """)
    rc, rep = _run(tmp_repo)
    assert _violations_with(rep, "IK001") == []
    assert _violations_with(rep, "IK002") == []


# ============================================================================
# PD -- pyproject.toml dependency scan
# ============================================================================

def test_PD001_chromadb_in_project_dependencies(tmp_repo):
    _write(tmp_repo / "pyproject.toml", """
        [project]
        name = "x"
        version = "0.0.1"
        dependencies = [
            "requests>=2.0",
            "chromadb>=0.5.0",
        ]
    """)
    rc, rep = _run(tmp_repo)
    assert rc == 1
    vs = _violations_with(rep, "PD001")
    assert len(vs) == 1
    assert "chromadb" in vs[0]["matched_text"]


def test_PD001_in_dependency_groups_dev(tmp_repo):
    _write(tmp_repo / "pyproject.toml", """
        [project]
        name = "x"
        version = "0.0.1"
        dependencies = []

        [dependency-groups]
        dev = ["docling>=2.0"]
    """)
    rc, rep = _run(tmp_repo)
    assert rc == 1
    assert len(_violations_with(rep, "PD001")) == 1


def test_PD001_does_not_fire_on_safe_deps(tmp_repo):
    _write(tmp_repo / "pyproject.toml", """
        [project]
        name = "x"
        version = "0.0.1"
        dependencies = ["openai>=1.0", "pyzotero>=1.5", "requests>=2.0"]

        [dependency-groups]
        dev = ["pytest>=7.0"]
    """)
    rc, rep = _run(tmp_repo)
    assert rc == 0
    assert _violations_with(rep, "PD001") == []


# ============================================================================
# Suppression (# noqa: SCOPE-<ID>)
# ============================================================================

def test_noqa_suppresses_matching_rule(tmp_repo):
    _write(tmp_repo / "pipeline" / "x.py",
           "import docling  # noqa: SCOPE-FI001\n")
    rc, rep = _run(tmp_repo)
    assert rc == 0
    assert _violations_with(rep, "FI001") == []


def test_noqa_does_not_suppress_other_rules(tmp_repo):
    _write(tmp_repo / "pipeline" / "x.py",
           "import docling  # noqa: SCOPE-OP001\n")
    rc, rep = _run(tmp_repo)
    assert rc == 1
    assert len(_violations_with(rep, "FI001")) == 1


def test_noqa_multiple_rules(tmp_repo):
    _write(tmp_repo / "pipeline" / "x.py", """
        import docling  # noqa: SCOPE-FI001, SCOPE-IK001
    """)
    rc, rep = _run(tmp_repo)
    assert rc == 0
    assert _violations_with(rep, "FI001") == []


# ============================================================================
# Exclusions
# ============================================================================

def test_tests_dir_skipped(tmp_repo):
    _write(tmp_repo / "tests" / "fixture.py", "import docling\n")
    rc, rep = _run(tmp_repo)
    assert rc == 0
    assert rep["violations"] == []


def test_docs_dir_skipped(tmp_repo):
    _write(tmp_repo / "docs" / "generated.py", "import chromadb\n")
    rc, rep = _run(tmp_repo)
    assert rc == 0


def test_prompts_dir_skipped(tmp_repo):
    _write(tmp_repo / "prompts" / "draft.py", "import langchain\n")
    rc, rep = _run(tmp_repo)
    assert rc == 0


def test_scope_audit_py_self_exempt(tmp_repo):
    # If we wrote a file at the same exempted path, even with violations,
    # it should be skipped.
    _write(tmp_repo / "pipeline" / "scope_audit.py",
           "import docling\nFORBIDDEN = ['docling']\n")
    rc, rep = _run(tmp_repo)
    assert rc == 0
    assert rep["violations"] == []


def test_venv_dir_skipped(tmp_repo):
    _write(tmp_repo / ".venv" / "lib" / "x.py", "import chromadb\n")
    rc, rep = _run(tmp_repo)
    assert rc == 0


# ============================================================================
# CLI / exit codes / report shape
# ============================================================================

def test_strict_mode_fails_on_warnings(tmp_repo):
    _write(tmp_repo / "pipeline" / "x.py",
           'msg = "we tried qwen2.5 but moved on"\n')
    rc_normal, _ = _run(tmp_repo, strict=False)
    rc_strict, _ = _run(tmp_repo, strict=True)
    assert rc_normal == 0
    assert rc_strict == 1


def test_json_schema_top_level_keys(tmp_repo):
    _write(tmp_repo / "pipeline" / "x.py", "x = 1\n")
    _, rep = _run(tmp_repo)
    for key in ("schema_version", "tool", "timestamp", "repo_root",
                "scanned", "summary", "violations"):
        assert key in rep, f"missing top-level key: {key}"
    assert rep["schema_version"] == "v1"
    assert rep["tool"] == "scope_audit"
    for key in ("files", "skipped_files", "lines"):
        assert key in rep["scanned"]
    for key in ("errors", "warnings", "by_category"):
        assert key in rep["summary"]


def test_violation_object_shape(tmp_repo):
    _write(tmp_repo / "pipeline" / "x.py", "import docling\n")
    _, rep = _run(tmp_repo)
    v = rep["violations"][0]
    for key in ("file", "line", "column", "category", "rule_id",
                "severity", "matched_text", "message", "suggestion",
                "scope_ref"):
        assert key in v, f"missing violation key: {key}"


# ============================================================================
# SCOPE.md anchor contract -- the test the user explicitly asked for
# ============================================================================

def test_scope_md_anchors_present():
    """Each rule's scope_ref leaf must literally appear in the real SCOPE.md.

    If a future edit renames a SCOPE.md section, this test fails immediately,
    forcing RULE_CATALOG to be updated in lockstep.
    """
    scope_md = REPO_ROOT / "SCOPE.md"
    assert scope_md.exists(), f"SCOPE.md not found at {scope_md}"
    text = scope_md.read_text(encoding="utf-8")

    missing: list[tuple[str, str]] = []
    for rule in sa.RULE_CATALOG.values():
        leaf = rule.scope_ref.rsplit(" > ", 1)[-1]
        if leaf not in text:
            missing.append((rule.rule_id, leaf))
    assert not missing, (
        f"SCOPE.md is missing section anchors required by RULE_CATALOG: "
        f"{missing}. Either restore the section title in SCOPE.md, or "
        f"update RULE_CATALOG to reflect the new title."
    )


def test_rule_catalog_severities_are_valid():
    for rule in sa.RULE_CATALOG.values():
        assert rule.severity in ("error", "warning"), rule


def test_rule_catalog_ids_are_unique():
    ids = [r.rule_id for r in sa.RULE_CATALOG.values()]
    assert len(ids) == len(set(ids))
