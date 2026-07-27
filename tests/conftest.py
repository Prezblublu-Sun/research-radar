"""pytest collection-time setup shared by all research-radar tests.

Scorer tests monkeypatch the constructed client's network method. Supplying a
non-secret placeholder keeps that client available while production imports
without an OPENAI_API_KEY remain valid for fetch-only dry-runs.

We use `os.environ.setdefault` so a real environment (e.g. a developer's
shell with real credentials) is never overridden.
"""
import os

os.environ.setdefault("OPENAI_API_KEY", "test-key-not-real")
os.environ.setdefault("OPENAI_BASE_URL", "https://example.invalid")
os.environ.setdefault("MODEL_NAME", "deepseek-v4-flash")
os.environ.setdefault("OPENALEX_API_KEY", "test-openalex-key-not-real")
