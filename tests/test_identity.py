"""ADR-0031: canonical work identity. Exact identifiers only.

Run with:
    pytest tests/test_identity.py
"""
from __future__ import annotations

import pathlib
import sys

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from render import identity  # noqa: E402


# ---------------------------------------------------------------------------
# DOI normalisation
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("raw, expected", [
    ("10.1016/J.JMBBM.2024.106864", "10.1016/j.jmbbm.2024.106864"),
    ("https://doi.org/10.1038/s41598-024-61305-x", "10.1038/s41598-024-61305-x"),
    ("http://dx.doi.org/10.1/ABC", "10.1/abc"),
    ("doi:10.1/x", "10.1/x"),
    ("  10.1/y  ", "10.1/y"),
    ("", ""),
    (None, ""),
])
def test_normalize_doi(raw, expected):
    assert identity.normalize_doi(raw) == expected


def test_doi_case_variants_share_one_key():
    a = identity.canonical_key({"doi": "10.1016/J.X.2026.1"})
    b = identity.canonical_key({"doi": "https://doi.org/10.1016/j.x.2026.1"})
    assert a == b == "doi:10.1016/j.x.2026.1"


# ---------------------------------------------------------------------------
# arXiv
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("raw, expected", [
    ("2609.08102v1", "2609.08102"),
    ("2609.08102", "2609.08102"),
    ("arXiv:2609.08102v3", "2609.08102"),
    ("http://arxiv.org/abs/2609.08102v1", "2609.08102"),
    ("https://arxiv.org/pdf/2609.08102.pdf", "2609.08102"),
    ("https://arxiv.org/abs/2609.00965", "2609.00965"),
    ("hep-th/9901001v2", "hep-th/9901001"),
    ("", ""),
])
def test_arxiv_base_id(raw, expected):
    assert identity.arxiv_base_id(raw) == expected


def test_arxiv_doi_is_the_arxiv_identity():
    # OpenAlex sometimes carries arXiv's own DOI; it names the same preprint.
    assert identity.canonical_key({"doi": "10.48550/arXiv.2609.08102"}) == "arxiv:2609.08102"


def test_arxiv_versions_are_one_work_but_public_identity_keeps_version():
    v1 = {"arxiv_id": "2609.08102v1"}
    v2 = {"arxiv_id": "2609.08102v2"}
    assert identity.canonical_key(v1) == identity.canonical_key(v2) == "arxiv:2609.08102"


def test_openalex_preprint_copy_matches_arxiv_record():
    # OpenAlex W7207880362: doi=None, landing page arxiv.org/abs/2609.00965.
    openalex_copy = {"source": "openalex", "id": "https://openalex.org/W7207880362",
                     "doi": "", "arxiv_id": "2609.00965"}
    arxiv_record = {"source": "arxiv", "arxiv_id": "2609.00965v1"}
    assert identity.canonical_key(openalex_copy) == identity.canonical_key(arxiv_record)


# ---------------------------------------------------------------------------
# Repositories with version DOIs
# ---------------------------------------------------------------------------

def test_figshare_version_suffix_is_stripped():
    concept = identity.canonical_key({"doi": "10.6084/m9.figshare.32345264"})
    version = identity.canonical_key({"doi": "10.6084/m9.figshare.32345264.v1"})
    assert concept == version == "doi:10.6084/m9.figshare.32345264"


def test_zenodo_uses_alias_map_and_keeps_unknown_dois():
    aliases = {"10.5281/zenodo.22057604": "10.5281/zenodo.22057603"}
    version = {"doi": "10.5281/zenodo.22057604"}
    concept = {"doi": "10.5281/zenodo.22057603"}
    assert identity.canonical_key(version, aliases) == "doi:10.5281/zenodo.22057603"
    assert identity.canonical_key(concept, aliases) == "doi:10.5281/zenodo.22057603"
    # Without the alias map (or for an unresolved DOI) nothing is guessed.
    assert identity.canonical_key(version) == "doi:10.5281/zenodo.22057604"
    assert identity.canonical_key({"doi": "10.5281/zenodo.99"}, aliases) == "doi:10.5281/zenodo.99"


def test_non_repository_dois_are_never_suffix_stripped():
    # ".v2" is part of a legitimate journal DOI here, not a version marker.
    assert identity.canonical_key({"doi": "10.1000/journal.v2"}) == "doi:10.1000/journal.v2"


# ---------------------------------------------------------------------------
# Secondary identifiers and precedence
# ---------------------------------------------------------------------------

def test_pmid_and_openalex_fallbacks():
    assert identity.canonical_key({"source": "pubmed", "id": "pubmed:42709028",
                                   "pmid": "42709028"}) == "pmid:42709028"
    assert identity.canonical_key({"source": "openalex",
                                   "id": "https://openalex.org/W7155576308"}) == "openalex:W7155576308"
    assert identity.canonical_key({"openalex_id": "W1"}) == "openalex:W1"


def test_precedence_doi_over_arxiv_over_pmid_over_openalex():
    paper = {"source": "openalex", "id": "https://openalex.org/W1",
             "doi": "10.1/x", "arxiv_id": "2601.00001", "pmid": "7"}
    assert identity.canonical_key(paper) == "doi:10.1/x"
    del paper["doi"]
    assert identity.canonical_key(paper) == "arxiv:2601.00001"
    del paper["arxiv_id"]
    assert identity.canonical_key(paper) == "pmid:7"
    del paper["pmid"]
    assert identity.canonical_key(paper) == "openalex:W1"


def test_records_without_any_exact_identifier_have_no_canonical_key():
    assert identity.canonical_key({"source": "pubmed", "title": "Same title"}) == ""
    assert identity.canonical_key({"source": "openalex", "id": "not-a-work-id"}) == ""
    assert identity.canonical_key({"pmid": "n/a"}) == ""
