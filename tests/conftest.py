"""pytest collection-time setup shared by all research-radar tests.

`pipeline.llm_scorer` reads OPENAI_API_KEY / OPENAI_BASE_URL / MODEL_NAME at
module-load time (because the OpenAI client is constructed at import). Any
test that imports a `pipeline.*` module which in turn imports llm_scorer
(directly or transitively) needs these env vars present, even though tests
monkeypatch `llm_scorer.score_batch` so the values are never actually used.

We use `os.environ.setdefault` so a real environment (e.g. a developer's
shell with real credentials) is never overridden.
"""
import os

os.environ.setdefault("OPENAI_API_KEY", "test-key-not-real")
os.environ.setdefault("OPENAI_BASE_URL", "https://example.invalid")
os.environ.setdefault("MODEL_NAME", "deepseek-v4-flash")
