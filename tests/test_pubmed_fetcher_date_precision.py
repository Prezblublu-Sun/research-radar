"""Tests for the date_precision field on PubMed-normalized papers.

Per ADR-0015 §4.1, PubMed records are always day-precision because EDAT
(Entrez Date — when the record entered PubMed) is always a full date.

Run with:
    pytest tests/test_pubmed_fetcher_date_precision.py
"""
from __future__ import annotations

import pathlib
import re
import sys

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from fetchers import pubmed_fetcher  # noqa: E402


_FAKE_EFETCH_XML = """<?xml version="1.0"?>
<PubmedArticleSet>
  <PubmedArticle>
    <MedlineCitation>
      <PMID>12345678</PMID>
      <Article>
        <Journal><Title>Journal of Test</Title></Journal>
        <ArticleTitle>A test article about femoral stems</ArticleTitle>
        <Abstract>
          <AbstractText>Background test content.</AbstractText>
        </Abstract>
        <AuthorList>
          <Author>
            <LastName>Smith</LastName>
            <ForeName>Jane</ForeName>
            <AffiliationInfo><Affiliation>UCL</Affiliation></AffiliationInfo>
          </Author>
        </AuthorList>
      </Article>
    </MedlineCitation>
    <PubmedData>
      <History>
        <PubDate><Year>2024</Year><Month>03</Month><Day>15</Day></PubDate>
      </History>
      <ArticleIdList>
        <ArticleId IdType="doi">10.1/test</ArticleId>
      </ArticleIdList>
    </PubmedData>
  </PubmedArticle>
</PubmedArticleSet>
"""


def _install_fake_eutils(monkeypatch):
    """Fake esearch (JSON) and efetch (XML) so fetch() runs end-to-end."""
    class FakeResp:
        def __init__(self, *, json_data=None, text=""):
            self._json = json_data
            self.text = text

        def raise_for_status(self):
            pass

        def json(self):
            return self._json

    def fake_get(url, params=None, **kw):
        if "esearch" in url:
            return FakeResp(json_data={"esearchresult": {"idlist": ["12345678"]}})
        if "efetch" in url:
            return FakeResp(text=_FAKE_EFETCH_XML)
        raise AssertionError(f"unexpected URL: {url}")

    monkeypatch.setattr(pubmed_fetcher.requests, "get", fake_get)
    monkeypatch.setattr(pubmed_fetcher.time, "sleep", lambda *a, **kw: None)


def test_pubmed_paper_has_day_precision(monkeypatch):
    _install_fake_eutils(monkeypatch)
    papers = pubmed_fetcher.fetch(["femoral stem"], days_back=7)
    assert len(papers) == 1
    assert papers[0]["date_precision"] == "day"


def test_pubmed_paper_date_is_iso_yyyy_mm_dd(monkeypatch):
    _install_fake_eutils(monkeypatch)
    papers = pubmed_fetcher.fetch(["femoral stem"], days_back=7)
    assert len(papers) == 1
    date = papers[0]["date"]
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", date), f"unexpected date: {date!r}"
    assert date == "2024-03-15"
