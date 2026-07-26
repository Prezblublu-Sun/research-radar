from __future__ import annotations

import pytest

from fetchers import openalex_fetcher as oa


class Response:
    def __init__(self, status=200, headers=None):
        self.status_code = status
        self.headers = headers or {}

    def raise_for_status(self):
        if self.status_code >= 400:
            raise oa.requests.HTTPError(str(self.status_code))

    def json(self):
        return {"results": [], "meta": {"next_cursor": None}}


def test_missing_api_key_is_a_configuration_error(monkeypatch):
    monkeypatch.delenv("OPENALEX_API_KEY", raising=False)
    with pytest.raises(oa.OpenAlexConfigError, match="OPENALEX_API_KEY"):
        oa.fetch([], ["x"], max_pages=1)


def test_api_key_is_injected_and_default_page_size_is_100(monkeypatch):
    calls = []
    monkeypatch.setenv("OPENALEX_API_KEY", "secret-test-key")
    monkeypatch.setattr(
        oa.requests, "get",
        lambda url, params, timeout: calls.append(params) or Response(),
    )
    oa.fetch([], ["x"], max_pages=1)
    assert calls[0]["api_key"] == "secret-test-key"
    assert calls[0]["per-page"] == 100


def test_503_retries_then_succeeds(monkeypatch):
    responses = iter([Response(503), Response(503), Response()])
    sleeps = []
    monkeypatch.setattr(oa.requests, "get",
                        lambda *a, **kw: next(responses))
    monkeypatch.setattr(oa.time, "sleep", sleeps.append)
    assert oa.fetch([], ["x"], max_pages=1) == []
    assert sleeps == [2, 4]


def test_long_rate_limit_fails_fast_without_leaking_key(monkeypatch):
    monkeypatch.setenv("OPENALEX_API_KEY", "never-print-this")
    monkeypatch.setattr(
        oa.requests, "get",
        lambda *a, **kw: Response(429, {"Retry-After": "120"}),
    )
    with pytest.raises(oa.OpenAlexRateLimitError) as caught:
        oa.fetch([], ["x"], max_pages=1)
    assert "never-print-this" not in str(caught.value)
