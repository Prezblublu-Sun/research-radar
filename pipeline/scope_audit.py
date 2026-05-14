"""pipeline/scope_audit.py - static auditor for SCOPE.md boundary violations.

A read-only meta-tool. It walks the radar codebase and applies five violation
categories (forbidden imports, forbidden LLM endpoints/models, forbidden output
paths, forbidden domain identifiers, forbidden dependencies in pyproject.toml).
It emits a JSON report on stdout. Exit code 0 if no errors; non-zero otherwise
(CI-friendly).

Usage:
    python -m pipeline.scope_audit                  # stdout JSON, exit 0 if clean
    python -m pipeline.scope_audit --strict          # also fail on warnings
    python -m pipeline.scope_audit --output PATH     # write JSON to file
    python -m pipeline.scope_audit --quiet           # suppress stderr summary

================================================================================
JSON OUTPUT SCHEMA -- v1 (AUTHORITATIVE CONTRACT)
================================================================================

Top-level object:
    schema_version       str   "v1"
    tool                 str   "scope_audit"
    timestamp            str   ISO 8601 Zulu, second precision
    repo_root            str   absolute path that was scanned
    scanned              dict  {files: int, skipped_files: int, lines: int}
    summary              dict  {errors: int, warnings: int,
                                 by_category: {<cat>: {errors, warnings}}}
    violations           list  zero or more violation objects (see below)

Violation object:
    file                 str   path relative to repo_root
    line                 int   1-based line number
    column               int   0-based column (AST) or 0 (toml)
    category             str   one of: forbidden_import,
                                 forbidden_llm_endpoint, forbidden_output_path,
                                 forbidden_identifier_keyword,
                                 forbidden_dependency
    rule_id              str   stable ID, e.g. "FI001"
    severity             "error" | "warning"
    matched_text         str   the source snippet that triggered the rule
    message              str   human-readable explanation
    suggestion           str   what to do instead
    scope_ref            str   SCOPE.md breadcrumb (last "> "-segment is the
                                authoritative anchor; see SECTION ANCHORS below)

Exit code:
    0  if no error-severity violations (warnings ok unless --strict)
    1  otherwise

In-file suppression:
    Append `# noqa: SCOPE-<RULE_ID>` on the line where the violation fires.
    Multiple IDs may be comma-separated: `# noqa: SCOPE-FI001, SCOPE-OP001`.
    Suppression is local to that line.

================================================================================
SCOPE.md SECTION ANCHORS RELIED ON
================================================================================

Each `scope_ref` ends with a leaf segment that MUST appear verbatim in
SCOPE.md, so CI can grep -F to verify the contract. The auditor relies on
these section heading texts existing:

    "Full-text processing"
    "Knowledge construction"
    "Personalization / interaction"
    "Hard rules"

If you rename a SCOPE.md section, update RULE_CATALOG below in lockstep.
The test `test_scope_md_anchors_present` enforces this contract.
================================================================================
"""
from __future__ import annotations

import argparse
import ast
import datetime as dt
import json
import pathlib
import re
import sys
import tomllib  # 3.11+
from dataclasses import asdict, dataclass
from typing import Callable


# ============================================================================
# Rule catalog -- single source of truth for rule_id, severity, message,
# suggestion, and scope_ref.
# ============================================================================

@dataclass(frozen=True)
class Rule:
    rule_id: str
    category: str
    severity: str  # "error" | "warning"
    message: str
    suggestion: str
    scope_ref: str  # breadcrumb; LEAF must appear in SCOPE.md


RULE_CATALOG: dict[str, Rule] = {
    # ----- Forbidden imports (FI) -----
    "FI001": Rule("FI001", "forbidden_import", "error",
        "Importing a PDF parser belongs to lit-system; Radar must not parse full text.",
        "Hand DOIs to lit-system via data/exports/candidates.jsonl; let it parse.",
        "SCOPE.md > What Research Radar is NOT > Full-text processing"),
    "FI002": Rule("FI002", "forbidden_import", "error",
        "Importing a vector store belongs to lit-system; Radar must not own embeddings.",
        "Vector retrieval is lit-system's job. Radar emits JSONL candidates.",
        "SCOPE.md > What Research Radar is NOT > Knowledge construction"),
    "FI003": Rule("FI003", "forbidden_import", "error",
        "Importing an embedding library belongs to lit-system.",
        "Radar does no embedding. Stick to LLM scoring via DeepSeek API.",
        "SCOPE.md > What Research Radar is NOT > Knowledge construction"),
    "FI004": Rule("FI004", "forbidden_import", "error",
        "Importing a local LLM runtime violates the GPU/API resource boundary.",
        "Use DeepSeek API only (ADR-0012); no Ollama, no llama.cpp, no vLLM.",
        "SCOPE.md > Resource division of labor: GPU vs API > Hard rules"),
    "FI005": Rule("FI005", "forbidden_import", "error",
        "Importing a deep-learning training framework violates the GPU boundary.",
        "GPU is reserved for lit-system. Radar runs on free GitHub Actions only.",
        "SCOPE.md > Resource division of labor: GPU vs API > Hard rules"),
    "FI006": Rule("FI006", "forbidden_import", "error",
        "Importing a RAG framework conflates Radar with lit-system's role.",
        "RAG is lit-system's job. Radar is a discovery/scoring layer.",
        "SCOPE.md > What Research Radar is NOT > Knowledge construction"),
    "FI007": Rule("FI007", "forbidden_import", "error",
        "Importing a web/server framework drifts toward productization.",
        "Output is static HTML on GitHub Pages. No live service.",
        "SCOPE.md > What Research Radar is NOT > Personalization / interaction"),
    # ----- Forbidden LLM endpoints / model identifiers (LE) -----
    "LE001": Rule("LE001", "forbidden_llm_endpoint", "error",
        "Hard-coded local LLM endpoint (Ollama default port).",
        "Use DeepSeek API; OPENAI_BASE_URL=https://api.deepseek.com.",
        "SCOPE.md > Resource division of labor: GPU vs API > Hard rules"),
    "LE002": Rule("LE002", "forbidden_llm_endpoint", "error",
        "Local model identifier assigned to a model/base_url/endpoint variable.",
        "Radar uses deepseek-* models only. Update the assignment.",
        "SCOPE.md > Resource division of labor: GPU vs API > Hard rules"),
    "LE003": Rule("LE003", "forbidden_llm_endpoint", "warning",
        "Local-model string literal found outside a model/base_url/endpoint context.",
        "If this is incidental (doc, error message), suppress with # noqa: SCOPE-LE003.",
        "SCOPE.md > Resource division of labor: GPU vs API > Hard rules"),
    # ----- Forbidden output paths (OP) -----
    "OP001": Rule("OP001", "forbidden_output_path", "error",
        "Path literal points at lit-system territory (vector store / chunks / parsed PDFs).",
        "Don't write into lit-system directories. Use data/exports/ for handoff.",
        "SCOPE.md > What Research Radar is NOT > Knowledge construction"),
    # ----- Forbidden identifier keywords (IK) -----
    "IK001": Rule("IK001", "forbidden_identifier_keyword", "error",
        "Identifier name matches a strict lit-system domain term.",
        "Rename the symbol; this concept belongs to the deep-parsing layer.",
        "SCOPE.md > What Research Radar is NOT > Full-text processing"),
    "IK002": Rule("IK002", "forbidden_identifier_keyword", "warning",
        "Identifier name matches a loose lit-system domain term.",
        "If this name is intentional, suppress with # noqa: SCOPE-IK002.",
        "SCOPE.md > What Research Radar is NOT > Knowledge construction"),
    # ----- Forbidden pyproject dependency (PD) -----
    "PD001": Rule("PD001", "forbidden_dependency", "error",
        "pyproject.toml declares a dependency that pulls Radar into lit-system territory.",
        "Remove the dependency. If you need it, route the feature through lit-system.",
        "SCOPE.md > What Research Radar is NOT > Knowledge construction"),
}


# ============================================================================
# Blocklists -- mapped to rule IDs
# ============================================================================

# Top-level package names (AST-based: match the first dot-segment of the
# imported module name, so "from chromadb.utils import X" matches "chromadb").
FORBIDDEN_IMPORTS: dict[str, str] = {
    # PDF parsers / OCR / table extractors -> FI001
    "docling": "FI001", "docling_core": "FI001",
    "pypdf": "FI001", "pypdf2": "FI001", "pypdfium2": "FI001",
    "pdfplumber": "FI001", "pdfminer": "FI001",
    "grobid_client": "FI001",
    # Vector stores -> FI002
    "chromadb": "FI002", "qdrant_client": "FI002", "pinecone": "FI002",
    "weaviate": "FI002", "faiss": "FI002", "pgvector": "FI002",
    # Embedding libs -> FI003
    "sentence_transformers": "FI003", "transformers": "FI003",
    # Local LLM runtimes -> FI004
    "ollama": "FI004", "llama_cpp": "FI004", "vllm": "FI004",
    # DL frameworks -> FI005
    "torch": "FI005", "torchvision": "FI005", "tensorflow": "FI005",
    "jax": "FI005",
    # RAG frameworks -> FI006
    "langchain": "FI006", "llama_index": "FI006", "llamaindex": "FI006",
    "haystack": "FI006",
    # Web/server frameworks -> FI007
    "flask": "FI007", "django": "FI007", "fastapi": "FI007",
    "starlette": "FI007", "tornado": "FI007", "aiohttp": "FI007",
}


# LE patterns
LE_LOCAL_ENDPOINT_RE = re.compile(r"(?:localhost|127\.0\.0\.1):11434")
LE_MODEL_NAME_RE = re.compile(
    r"\b(?:qwen|llama|mistral|vicuna|gemma|phi-?[0-9]|yi-)[\w.\-:]*",
    re.IGNORECASE,
)
LE_TRIGGER_LHS = re.compile(r"(model|base_url|endpoint)", re.IGNORECASE)


# OP patterns -- substrings to match in path-shaped string literals.
OP_LITSYSTEM_PATTERNS = [
    re.compile(r"(?:^|/)data/chroma_db(?:/|$)"),
    re.compile(r"(?:^|/)data/chunks(?:/|$)"),
    re.compile(r"(?:^|/)data/embeddings(?:/|$)"),
    re.compile(r"(?:^|/)data/docling(?:/|$)"),
    re.compile(r"(?:^|/)assets/chroma"),
    re.compile(r"(?:^|/)assets/chunks(?:/|$)"),
    re.compile(r"(?:^|/)assets/docling(?:/|$)"),
    re.compile(r"(?:^|/)metadata/P\d+\.json"),
    re.compile(r"(?:^|/)metadata/P\{"),
    re.compile(r"(?:^|/)corpus/"),
]


# IK token sets
IK_STRICT_SINGLE_TOKENS = {"docling", "chroma", "chromadb", "ocr"}
IK_STRICT_BIGRAMS = {
    ("pdf", "parse"), ("parse", "pdf"),
    ("pdf", "text"), ("text", "pdf"),
}
IK_LOOSE_TOKEN_PREFIXES = ("chunk", "embed", "vector")
IK_LOOSE_EXACT_TOKENS = {"rag"}


def _tokenize_identifier(name: str) -> list[str]:
    """Split snake_case + CamelCase into lowercase tokens.

    Examples:
        "DoclingParser"   -> ["docling", "parser"]
        "parse_pdf"       -> ["parse", "pdf"]
        "PDFParser"       -> ["pdf", "parser"]
        "embedding_model" -> ["embedding", "model"]
    """
    s = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", name)
    s = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1_\2", s)
    return [t.lower() for t in s.split("_") if t]


def _ik_strict_match(tokens: list[str]) -> bool:
    if any(t in IK_STRICT_SINGLE_TOKENS for t in tokens):
        return True
    for i in range(len(tokens) - 1):
        if (tokens[i], tokens[i + 1]) in IK_STRICT_BIGRAMS:
            return True
    return False


def _ik_loose_match(tokens: list[str]) -> bool:
    for t in tokens:
        if t in IK_LOOSE_EXACT_TOKENS:
            return True
        if any(t.startswith(p) for p in IK_LOOSE_TOKEN_PREFIXES):
            return True
    return False


# ============================================================================
# Exclusions
# ============================================================================

EXCLUDED_DIRS = {
    ".venv", "venv", "env",
    ".git", ".pytest_cache", ".mypy_cache", ".ruff_cache",
    "__pycache__", "build", "dist",
    "tests",   # synthetic violations live here
    "docs",    # rendered HTML, may contain forbidden words incidentally
    "prompts", # versioned scorer prompts may reference forbidden concepts
}

EXCLUDED_FILES = {
    "pipeline/scope_audit.py",  # the auditor itself
}


# ============================================================================
# Violation representation
# ============================================================================

@dataclass
class Violation:
    file: str
    line: int
    column: int
    category: str
    rule_id: str
    severity: str
    matched_text: str
    message: str
    suggestion: str
    scope_ref: str


def _make_violation(rule_id: str, file: str, line: int, column: int,
                    matched_text: str) -> Violation:
    rule = RULE_CATALOG[rule_id]
    return Violation(
        file=file, line=line, column=column,
        category=rule.category, rule_id=rule.rule_id, severity=rule.severity,
        matched_text=matched_text, message=rule.message,
        suggestion=rule.suggestion, scope_ref=rule.scope_ref,
    )


# ============================================================================
# Noqa parsing
# ============================================================================

NOQA_LINE_RE = re.compile(r"#\s*noqa:\s*([A-Z0-9\-,\s]+)", re.IGNORECASE)
NOQA_TOKEN_RE = re.compile(r"SCOPE-([A-Z]{2}\d+)", re.IGNORECASE)


def parse_noqa_suppressions(source: str) -> dict[int, set[str]]:
    """Return {line_number: {rule_id, ...}} for `# noqa: SCOPE-<id>` markers."""
    out: dict[int, set[str]] = {}
    for i, line in enumerate(source.splitlines(), start=1):
        m = NOQA_LINE_RE.search(line)
        if not m:
            continue
        ids = {tok.upper() for tok in NOQA_TOKEN_RE.findall(m.group(1))}
        if ids:
            out[i] = ids
    return out


# ============================================================================
# Per-file Python auditor
# ============================================================================

def _lhs_names_match_trigger(targets: list[ast.AST]) -> bool:
    for t in targets:
        for name_node in ast.walk(t):
            if isinstance(name_node, ast.Name):
                if LE_TRIGGER_LHS.search(name_node.id):
                    return True
            elif isinstance(name_node, ast.Attribute):
                if LE_TRIGGER_LHS.search(name_node.attr):
                    return True
    return False


def audit_python_file(path: pathlib.Path,
                      repo_root: pathlib.Path) -> list[Violation]:
    rel = str(path.relative_to(repo_root))
    try:
        source = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return []
    try:
        tree = ast.parse(source, filename=str(path))
    except SyntaxError:
        return []

    suppressions = parse_noqa_suppressions(source)
    violations: list[Violation] = []

    def emit(rule_id: str, line: int, col: int, matched: str):
        if rule_id in suppressions.get(line, set()):
            return
        violations.append(_make_violation(rule_id, rel, line, col, matched))

    # Pass 1: collect model-context string literal positions (for LE002 vs LE003)
    model_context_positions: set[tuple[int, int]] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            targets = list(node.targets)
        elif isinstance(node, ast.AnnAssign):
            targets = [node.target]
        else:
            continue
        if not _lhs_names_match_trigger(targets):
            continue
        if node.value is None:
            continue
        for sub in ast.walk(node.value):
            if isinstance(sub, ast.Constant) and isinstance(sub.value, str):
                model_context_positions.add((sub.lineno, sub.col_offset))

    # Pass 2: emit all rules
    for node in ast.walk(tree):
        # ---- FI: imports
        if isinstance(node, ast.Import):
            for alias in node.names:
                top = alias.name.split(".")[0].lower()
                rule = FORBIDDEN_IMPORTS.get(top)
                if rule:
                    emit(rule, node.lineno, node.col_offset,
                         f"import {alias.name}")
        elif isinstance(node, ast.ImportFrom):
            mod_top = (node.module or "").split(".")[0].lower()
            rule = FORBIDDEN_IMPORTS.get(mod_top)
            if rule:
                names = ", ".join(a.name for a in node.names)
                emit(rule, node.lineno, node.col_offset,
                     f"from {node.module} import {names}")

        # ---- LE001 / LE002 / LE003 / OP001: string literals
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            s = node.value
            if LE_LOCAL_ENDPOINT_RE.search(s):
                emit("LE001", node.lineno, node.col_offset, s[:80])
            elif LE_MODEL_NAME_RE.search(s):
                if (node.lineno, node.col_offset) in model_context_positions:
                    emit("LE002", node.lineno, node.col_offset, s[:80])
                else:
                    emit("LE003", node.lineno, node.col_offset, s[:80])
            else:
                for op_re in OP_LITSYSTEM_PATTERNS:
                    if op_re.search(s):
                        emit("OP001", node.lineno, node.col_offset, s[:80])
                        break

        # ---- IK: identifiers
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            _check_identifier(emit, node.name, node.lineno, node.col_offset)
        elif isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name):
                    _check_identifier(emit, t.id, t.lineno, t.col_offset)
        elif isinstance(node, ast.AnnAssign):
            if isinstance(node.target, ast.Name):
                _check_identifier(emit, node.target.id,
                                  node.target.lineno, node.target.col_offset)

    return violations


def _check_identifier(emit: Callable[[str, int, int, str], None],
                      name: str, line: int, col: int) -> None:
    tokens = _tokenize_identifier(name)
    if _ik_strict_match(tokens):
        emit("IK001", line, col, name)
        return
    if _ik_loose_match(tokens):
        emit("IK002", line, col, name)


# ============================================================================
# pyproject.toml auditor
# ============================================================================

def audit_pyproject(path: pathlib.Path,
                    repo_root: pathlib.Path) -> list[Violation]:
    rel = str(path.relative_to(repo_root))
    try:
        raw = path.read_text(encoding="utf-8")
        data = tomllib.loads(raw)
    except (OSError, ValueError):
        return []

    src_lines = raw.splitlines()

    def find_line(needle: str) -> int:
        for i, line in enumerate(src_lines, start=1):
            if needle in line:
                return i
        return 0

    violations: list[Violation] = []
    deps: list[str] = []

    project = data.get("project", {})
    deps.extend(project.get("dependencies", []) or [])
    for group_deps in (project.get("optional-dependencies", {}) or {}).values():
        deps.extend(group_deps or [])
    for group_deps in (data.get("dependency-groups", {}) or {}).values():
        deps.extend(group_deps or [])

    rule = RULE_CATALOG["PD001"]
    for raw_dep in deps:
        m = re.match(r"^([A-Za-z][A-Za-z0-9_.\-]*)", raw_dep)
        if not m:
            continue
        pkg = m.group(1).lower().replace("-", "_")
        if pkg in FORBIDDEN_IMPORTS:
            violations.append(Violation(
                file=rel, line=find_line(raw_dep), column=0,
                category=rule.category, rule_id="PD001",
                severity=rule.severity,
                matched_text=raw_dep, message=rule.message,
                suggestion=rule.suggestion, scope_ref=rule.scope_ref,
            ))
    return violations


# ============================================================================
# Discovery and report
# ============================================================================

def discover_python_files(repo_root: pathlib.Path) -> tuple[list[pathlib.Path], int]:
    """Return (py_files_to_scan, skipped_count)."""
    to_scan: list[pathlib.Path] = []
    skipped = 0
    for path in sorted(repo_root.rglob("*.py")):
        rel_parts = path.relative_to(repo_root).parts
        if any(part in EXCLUDED_DIRS for part in rel_parts):
            skipped += 1
            continue
        rel_str = "/".join(rel_parts)
        if rel_str in EXCLUDED_FILES:
            skipped += 1
            continue
        to_scan.append(path)
    return to_scan, skipped


def build_report(repo_root: pathlib.Path,
                 violations: list[Violation],
                 scanned_files: int, skipped_files: int,
                 total_lines: int) -> dict:
    by_category: dict[str, dict[str, int]] = {}
    for v in violations:
        c = by_category.setdefault(v.category, {"errors": 0, "warnings": 0})
        c["errors" if v.severity == "error" else "warnings"] += 1
    return {
        "schema_version": "v1",
        "tool": "scope_audit",
        "timestamp": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "repo_root": str(repo_root),
        "scanned": {
            "files": scanned_files,
            "skipped_files": skipped_files,
            "lines": total_lines,
        },
        "summary": {
            "errors":   sum(1 for v in violations if v.severity == "error"),
            "warnings": sum(1 for v in violations if v.severity == "warning"),
            "by_category": by_category,
        },
        "violations": [asdict(v) for v in violations],
    }


def run_audit(repo_root: pathlib.Path) -> dict:
    """Programmatic entry point. Returns the JSON-shaped report dict."""
    repo_root = repo_root.resolve()
    py_files, skipped = discover_python_files(repo_root)
    total_lines = 0
    violations: list[Violation] = []
    for f in py_files:
        try:
            total_lines += sum(1 for _ in f.open(encoding="utf-8"))
        except (OSError, UnicodeDecodeError):
            pass
        violations.extend(audit_python_file(f, repo_root))
    pyproject = repo_root / "pyproject.toml"
    if pyproject.exists():
        violations.extend(audit_pyproject(pyproject, repo_root))
    return build_report(
        repo_root=repo_root, violations=violations,
        scanned_files=len(py_files), skipped_files=skipped,
        total_lines=total_lines,
    )


# ============================================================================
# CLI
# ============================================================================

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Static auditor for SCOPE.md boundary violations."
    )
    parser.add_argument(
        "--repo-root", type=pathlib.Path,
        default=pathlib.Path(__file__).resolve().parent.parent,
        help="Project root to scan (default: parent of this file).",
    )
    parser.add_argument(
        "--output", type=pathlib.Path, default=None,
        help="Write JSON to this path. Default: stdout.",
    )
    parser.add_argument(
        "--strict", action="store_true",
        help="Exit non-zero on warnings too (default: errors only).",
    )
    parser.add_argument(
        "--quiet", action="store_true",
        help="Suppress stderr summary line.",
    )
    args = parser.parse_args(argv)

    report = run_audit(args.repo_root)
    out_json = json.dumps(report, indent=2, ensure_ascii=False)

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(out_json, encoding="utf-8")
    else:
        print(out_json)

    if not args.quiet:
        s = report["summary"]
        print(
            f"[scope_audit] {s['errors']} error(s), {s['warnings']} warning(s) "
            f"across {report['scanned']['files']} file(s)",
            file=sys.stderr,
        )

    has_errors = report["summary"]["errors"] > 0
    has_warnings = report["summary"]["warnings"] > 0
    if has_errors or (args.strict and has_warnings):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
