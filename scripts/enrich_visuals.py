"""Discover reusable paper figures without touching ranking or search data.

This is an optional, failure-isolated enrichment command.  It reads the v2
daily corpus and writes one metadata-only sidecar keyed by the same strict
DOI/arXiv identities used by the public renderer.  It never downloads or
commits image/PDF binaries and it never mutates ``data/daily``.

Only figures whose article metadata carries an explicit CC0, CC BY, or
CC BY-SA licence are exposed.  Captions that signal third-party rights are
rejected even when the surrounding article has a permissive licence.

Usage::

    python -m scripts.enrich_visuals --limit 20
    python -m scripts.enrich_visuals --limit 100 --force
"""

from __future__ import annotations

import argparse
import datetime as dt
from html.parser import HTMLParser
import json
import os
from pathlib import Path
import re
import sys
import time
from typing import Iterable
import urllib.error
from urllib.parse import unquote, urlencode, urljoin, urlparse
import urllib.request
import xml.etree.ElementTree as ET

from render import corpus_view


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DAILY_DIR = ROOT / "data" / "daily"
DEFAULT_INDEX_PATH = ROOT / "data" / "visuals" / "index.json"

SCHEMA_VERSION = "v1"
DEFAULT_LIMIT = 20
DEFAULT_TIMEOUT_SECONDS = 12.0
DEFAULT_MIN_DELAY_SECONDS = 0.5
MAX_METADATA_BYTES = 8 * 1024 * 1024
IMAGE_SUFFIXES = {".gif", ".jpeg", ".jpg", ".png", ".webp"}
ALLOWED_LICENSES = {"CC0", "CC BY", "CC BY-SA"}

ID_CONVERTER_URL = (
    "https://pmc.ncbi.nlm.nih.gov/tools/idconv/api/v1/articles/"
)
PMC_BUCKET_HOST = "pmc-oa-opendata.s3.amazonaws.com"
PMC_BUCKET_URL = f"https://{PMC_BUCKET_HOST}/"
ARXIV_OAI_URL = "https://export.arxiv.org/oai2"

THIRD_PARTY_MARKERS = (
    "reproduced with permission",
    "reprinted with permission",
    "adapted with permission",
    "used with permission",
    "all rights reserved",
    "not included in the creative commons",
    "not covered by the creative commons",
    "excluded from the creative commons",
    "third-party material",
    "third party material",
    "copyright holder",
    "copyright ",
    "©",
)


class FetchError(RuntimeError):
    """A bounded remote-fetch failure suitable for negative caching."""


def utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def iso_z(value: dt.datetime) -> str:
    return value.astimezone(dt.timezone.utc).isoformat(
        timespec="seconds"
    ).replace("+00:00", "Z")


def parse_timestamp(value: object) -> dt.datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed.astimezone(dt.timezone.utc)


def normalize_license(value: object) -> str:
    """Return a compact licence label, preserving fail-closed semantics."""
    raw = str(value or "").strip()
    if not raw:
        return ""
    lower = raw.lower()
    if "publicdomain/zero" in lower or re.search(r"\bcc[ -]?0\b", lower):
        return "CC0"
    if "/licenses/by-sa/" in lower:
        return "CC BY-SA"
    if "/licenses/by/" in lower:
        return "CC BY"
    normalized = re.sub(r"[_-]+", " ", raw.upper())
    normalized = re.sub(r"\b(?:V?\d+(?:\.\d+)*)\b", "", normalized)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    tokens = set(normalized.split())
    if "CC" not in tokens and "CREATIVE COMMONS" not in normalized:
        return raw[:120]
    if "NC" in tokens and "ND" in tokens:
        return "CC BY-NC-ND"
    if "NC" in tokens and "SA" in tokens:
        return "CC BY-NC-SA"
    if "NC" in tokens:
        return "CC BY-NC"
    if "ND" in tokens:
        return "CC BY-ND"
    if "BY" in tokens and "SA" in tokens:
        return "CC BY-SA"
    if "BY" in tokens:
        return "CC BY"
    return raw[:120]


def caption_has_third_party_rights(caption: str) -> bool:
    compact = " ".join((caption or "").lower().split())
    return any(marker in compact for marker in THIRD_PARTY_MARKERS)


def _suffix(url: str) -> str:
    return Path(unquote(urlparse(url).path)).suffix.lower()


def _https_url(value: object, *, hosts: set[str]) -> str:
    """Validate/upgrade a URL and return an allowlisted HTTPS URL."""
    raw = str(value or "").strip()
    if raw.startswith("s3://pmc-oa-opendata/"):
        key = raw[len("s3://pmc-oa-opendata/"):].split("?", 1)[0]
        raw = PMC_BUCKET_URL + key
    parsed = urlparse(raw)
    host = (parsed.hostname or "").lower()
    if parsed.scheme not in {"http", "https"} or host not in hosts:
        return ""
    if host == PMC_BUCKET_HOST and parsed.path.startswith("/deprecated/"):
        return ""
    return parsed._replace(scheme="https").geturl()


def pmc_media_url(value: object) -> str:
    url = _https_url(value, hosts={PMC_BUCKET_HOST})
    return url if url and _suffix(url) in IMAGE_SUFFIXES else ""


def identity_key(paper: dict) -> str:
    """Use the renderer's exact, intentionally non-normalizing identity."""
    return corpus_view.identity_key(paper)


def _blank_visual(status: str, *, checked_at: str, reason: str = "",
                  license_name: str = "", provider: str = "") -> dict:
    result = {
        "status": status,
        "image_url": "",
        "caption": "",
        "source_label": "",
        "source_url": "",
        "license": license_name,
        "alt": "",
        "width": None,
        "height": None,
        "checked_at": checked_at,
    }
    if reason:
        result["reason"] = reason
    if provider:
        result["provider"] = provider
    return result


def _available_visual(*, checked_at: str, image_url: str, caption: str,
                      source_label: str, source_url: str,
                      license_name: str, alt: str, provider: str) -> dict:
    return {
        "status": "available",
        "image_url": image_url,
        "caption": caption[:1200],
        "source_label": source_label[:160],
        "source_url": source_url,
        "license": license_name,
        "alt": (alt or caption or "论文插图")[:500],
        "width": None,
        "height": None,
        "checked_at": checked_at,
        "provider": provider,
    }


class HttpClient:
    """Rate-limited HTTP reader with small retry and response-size bounds."""

    def __init__(self, *, timeout: float = DEFAULT_TIMEOUT_SECONDS,
                 min_delay: float = DEFAULT_MIN_DELAY_SECONDS,
                 max_attempts: int = 2,
                 opener: urllib.request.OpenerDirector | None = None):
        self.timeout = timeout
        self.min_delay = min_delay
        self.max_attempts = max(1, max_attempts)
        self.opener = opener or urllib.request.build_opener()
        self.headers = {
            "User-Agent": "ResearchRadarVisuals/1.0 (metadata enrichment)",
            "Accept": "application/json, application/xml, text/html;q=0.9, */*;q=0.1",
        }
        self._last_request_at = 0.0

    def _wait(self) -> None:
        remaining = self.min_delay - (time.monotonic() - self._last_request_at)
        if remaining > 0:
            time.sleep(remaining)

    def get_bytes(self, url: str, *, params: dict | None = None,
                  allowed_hosts: set[str], max_bytes: int = MAX_METADATA_BYTES) -> bytes:
        if params:
            separator = "&" if "?" in url else "?"
            url = f"{url}{separator}{urlencode(params, doseq=True)}"
        initial = urlparse(url)
        if initial.scheme != "https" or (initial.hostname or "").lower() not in allowed_hosts:
            raise FetchError("remote URL is outside the provider allowlist")
        last_error = "request failed"
        for attempt in range(self.max_attempts):
            self._wait()
            try:
                request = urllib.request.Request(url, headers=self.headers)
                response = self.opener.open(request, timeout=self.timeout)
                self._last_request_at = time.monotonic()
                final = urlparse(response.geturl())
                if final.scheme != "https" or (
                    final.hostname or ""
                ).lower() not in allowed_hosts:
                    response.close()
                    raise FetchError("provider redirected outside its allowlist")
                try:
                    declared = response.headers.get("Content-Length")
                    if declared and int(declared) > max_bytes:
                        raise FetchError("provider response exceeded size limit")
                    payload = response.read(max_bytes + 1)
                finally:
                    response.close()
                if len(payload) > max_bytes:
                    raise FetchError("provider response exceeded size limit")
                return payload
            except urllib.error.HTTPError as exc:
                self._last_request_at = time.monotonic()
                last_error = f"HTTP {exc.code}"
                if (exc.code in {429, 500, 502, 503, 504} and
                        attempt + 1 < self.max_attempts):
                    time.sleep(min(2.0, 0.5 * (2 ** attempt)))
                    continue
                break
            except (urllib.error.URLError, TimeoutError, OSError,
                    FetchError) as exc:
                last_error = str(exc) or type(exc).__name__
                if isinstance(exc, FetchError) or attempt + 1 >= self.max_attempts:
                    break
                time.sleep(min(2.0, 0.5 * (2 ** attempt)))
        raise FetchError(last_error)

    def get_json(self, url: str, *, params: dict | None = None,
                 allowed_hosts: set[str]) -> dict:
        try:
            payload = json.loads(self.get_bytes(
                url, params=params, allowed_hosts=allowed_hosts,
            ).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise FetchError("provider returned invalid JSON") from exc
        if not isinstance(payload, dict):
            raise FetchError("provider JSON root is not an object")
        return payload

    def get_text(self, url: str, *, params: dict | None = None,
                 allowed_hosts: set[str]) -> str:
        return self.get_bytes(
            url, params=params, allowed_hosts=allowed_hosts,
        ).decode("utf-8", errors="replace")


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].lower()


def _node_text(node: ET.Element | None) -> str:
    if node is None:
        return ""
    return " ".join("".join(node.itertext()).split())


def _graphic_href(fig: ET.Element) -> str:
    for node in fig.iter():
        if _local_name(node.tag) not in {"graphic", "inline-graphic"}:
            continue
        for key, value in node.attrib.items():
            if key == "href" or key.endswith("}href"):
                return value
    return ""


def _basename(value: str) -> str:
    return Path(unquote(urlparse(value).path)).name.lower()


def _match_media(href: str, media_urls: list[str]) -> str:
    wanted = _basename(href)
    if not wanted:
        return ""
    exact = { _basename(url): url for url in media_urls }
    if wanted in exact:
        return exact[wanted]
    wanted_stem = Path(wanted).stem
    for name, url in exact.items():
        if Path(name).stem == wanted_stem:
            return url
    return ""


def select_pmc_figure(xml_text: str, media_urls: Iterable[object]) -> dict | None:
    """Choose a safe graphical abstract or first ordinary JATS figure."""
    safe_media = [url for value in media_urls if (url := pmc_media_url(value))]
    if not safe_media:
        return None
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return None
    candidates = []
    for order, fig in enumerate(node for node in root.iter()
                                if _local_name(node.tag) == "fig"):
        caption_node = next((node for node in fig.iter()
                             if _local_name(node.tag) == "caption"), None)
        label_node = next((node for node in fig.iter()
                           if _local_name(node.tag) == "label"), None)
        caption = _node_text(caption_node)
        label = _node_text(label_node)
        # Rights/credit statements may sit in ``attrib`` or another child of
        # ``fig`` rather than inside the caption itself.
        if caption_has_third_party_rights(_node_text(fig)):
            continue
        image_url = _match_media(_graphic_href(fig), safe_media)
        if not image_url:
            continue
        kind = (fig.attrib.get("fig-type") or "").lower()
        figure_id = (fig.attrib.get("id") or "").lower()
        media_name = _basename(image_url)
        haystack = f"{kind} {figure_id} {media_name} {label} {caption}".lower()
        preferred = int(
            "graphical abstract" in haystack or
            "graphical-abstract" in haystack or
            media_name.startswith(("ga", "fx"))
        )
        unnumbered = int(
            kind in {"unnumbered", "undfig"} or figure_id.startswith("undfig")
        )
        display_label = label or (
            "Graphical abstract" if preferred else "Figure"
        )
        candidates.append((-(preferred * 2 + unnumbered), order, {
            "image_url": image_url,
            "caption": caption,
            "label": display_label,
        }))
    return min(candidates, default=(0, 0, None))[2]


def _pmc_versions(list_xml: str, pmcid: str) -> list[str]:
    try:
        root = ET.fromstring(list_xml)
    except ET.ParseError as exc:
        raise FetchError("PMC S3 returned invalid listing XML") from exc
    pattern = re.compile(rf"^{re.escape(pmcid)}\.(\d+)/$")
    found = []
    for node in root.iter():
        if _local_name(node.tag) != "prefix":
            continue
        value = (node.text or "").strip()
        match = pattern.match(value)
        if match:
            found.append((int(match.group(1)), value.rstrip("/")))
    return [value for _, value in sorted(found, reverse=True)]


class ArxivFigureParser(HTMLParser):
    """Small parser for official arXiv HTML ``figure`` elements."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.depth = 0
        self.caption_depth = 0
        self.current: dict | None = None
        self.figures: list[dict] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        attributes = dict(attrs)
        if tag == "figure":
            if self.depth == 0:
                self.current = {"src": "", "caption_parts": [],
                                "class": attributes.get("class") or ""}
            self.depth += 1
            return
        if self.depth and tag == "img" and self.current is not None:
            self.current["src"] = self.current["src"] or attributes.get("src") or ""
            self.current["alt"] = attributes.get("alt") or ""
        if self.depth and tag == "figcaption":
            self.caption_depth += 1

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag == "figcaption" and self.caption_depth:
            self.caption_depth -= 1
        if tag == "figure" and self.depth:
            self.depth -= 1
            if self.depth == 0 and self.current is not None:
                self.current["caption"] = " ".join(
                    " ".join(self.current.pop("caption_parts")).split()
                )
                self.figures.append(self.current)
                self.current = None

    def handle_data(self, data: str) -> None:
        if self.depth and self.caption_depth and self.current is not None:
            self.current["caption_parts"].append(data)


def select_arxiv_figure(html_text: str, page_url: str) -> dict | None:
    parser = ArxivFigureParser()
    parser.feed(html_text)
    safe = []
    for order, figure in enumerate(parser.figures):
        caption = figure.get("caption") or ""
        if caption_has_third_party_rights(caption):
            continue
        image_url = _https_url(
            urljoin(page_url.rstrip("/") + "/", figure.get("src") or ""),
            hosts={"arxiv.org"},
        )
        if not image_url or _suffix(image_url) not in IMAGE_SUFFIXES:
            continue
        haystack = f"{figure.get('class', '')} {caption}".lower()
        preferred = int("graphical abstract" in haystack)
        safe.append((-preferred, order, {
            "image_url": image_url,
            "caption": caption,
            "alt": figure.get("alt") or "",
        }))
    return min(safe, default=(0, 0, None))[2]


class VisualResolver:
    def __init__(self, client: HttpClient, *, email: str = ""):
        self.client = client
        self.email = email.strip()

    def _pmcid(self, paper: dict) -> str:
        requested = str(paper.get("pmid") or "").strip()
        if not requested:
            requested = str(paper.get("doi") or "").strip()
        if not requested:
            return ""
        params = {
            "ids": requested,
            "format": "json",
            "tool": "research-radar-visuals",
        }
        if self.email:
            params["email"] = self.email
        payload = self.client.get_json(
            ID_CONVERTER_URL,
            params=params,
            allowed_hosts={"pmc.ncbi.nlm.nih.gov"},
        )
        for record in payload.get("records") or []:
            if isinstance(record, dict) and record.get("pmcid"):
                pmcid = str(record["pmcid"]).upper()
                return pmcid if re.fullmatch(r"PMC\d+", pmcid) else ""
        return ""

    def resolve_pmc(self, paper: dict, checked_at: str) -> dict | None:
        if not (paper.get("doi") or paper.get("pmid")):
            return None
        pmcid = self._pmcid(paper)
        if not pmcid:
            return None
        listing = self.client.get_text(
            PMC_BUCKET_URL,
            params={"list-type": "2", "prefix": f"{pmcid}.", "delimiter": "/"},
            allowed_hosts={PMC_BUCKET_HOST},
        )
        versions = _pmc_versions(listing, pmcid)
        if not versions:
            return _blank_visual(
                "not_found", checked_at=checked_at,
                reason="pmc_version_not_available", provider="pmc",
            )
        version = versions[0]
        metadata = self.client.get_json(
            f"{PMC_BUCKET_URL}metadata/{version}.json",
            allowed_hosts={PMC_BUCKET_HOST},
        )
        license_name = normalize_license(metadata.get("license_code"))
        if license_name not in ALLOWED_LICENSES:
            return _blank_visual(
                "blocked", checked_at=checked_at,
                reason="pmc_license_not_reusable", license_name=license_name,
                provider="pmc",
            )
        xml_url = _https_url(metadata.get("xml_url"), hosts={PMC_BUCKET_HOST})
        if not xml_url:
            return _blank_visual(
                "not_found", checked_at=checked_at,
                reason="pmc_jats_not_available", license_name=license_name,
                provider="pmc",
            )
        xml_text = self.client.get_text(
            xml_url, allowed_hosts={PMC_BUCKET_HOST},
        )
        selected = select_pmc_figure(xml_text, metadata.get("media_urls") or [])
        if not selected:
            return _blank_visual(
                "not_found", checked_at=checked_at,
                reason="pmc_no_reusable_figure", license_name=license_name,
                provider="pmc",
            )
        source_url = f"https://pmc.ncbi.nlm.nih.gov/articles/{pmcid}/"
        return _available_visual(
            checked_at=checked_at,
            image_url=selected["image_url"], caption=selected["caption"],
            source_label=f"PubMed Central · {selected['label']}",
            source_url=source_url, license_name=license_name,
            alt=selected["caption"] or paper.get("title") or "PMC 论文插图",
            provider="pmc",
        )

    def resolve_arxiv(self, paper: dict, checked_at: str) -> dict | None:
        raw_id = str(paper.get("arxiv_id") or "").strip()
        if not raw_id:
            return None
        base_id = re.sub(r"v\d+$", "", raw_id, flags=re.IGNORECASE)
        oai = self.client.get_text(
            ARXIV_OAI_URL,
            params={
                "verb": "GetRecord",
                "identifier": f"oai:arXiv.org:{base_id}",
                "metadataPrefix": "arXivRaw",
            },
            allowed_hosts={"export.arxiv.org"},
        )
        try:
            root = ET.fromstring(oai)
        except ET.ParseError as exc:
            raise FetchError("arXiv OAI returned invalid XML") from exc
        license_value = ""
        for node in root.iter():
            if _local_name(node.tag) == "license" and (node.text or "").strip():
                license_value = (node.text or "").strip()
                break
        license_name = normalize_license(license_value)
        if license_name not in ALLOWED_LICENSES:
            return _blank_visual(
                "blocked", checked_at=checked_at,
                reason="arxiv_license_not_reusable", license_name=license_name,
                provider="arxiv",
            )
        page_url = f"https://arxiv.org/html/{base_id}"
        html_text = self.client.get_text(
            page_url, allowed_hosts={"arxiv.org"},
        )
        selected = select_arxiv_figure(html_text, page_url)
        if not selected:
            return _blank_visual(
                "not_found", checked_at=checked_at,
                reason="arxiv_html_no_reusable_figure",
                license_name=license_name, provider="arxiv",
            )
        return _available_visual(
            checked_at=checked_at, image_url=selected["image_url"],
            caption=selected["caption"], source_label="arXiv · 论文插图",
            source_url=f"https://arxiv.org/abs/{base_id}",
            license_name=license_name,
            alt=selected.get("alt") or selected["caption"] or
                paper.get("title") or "arXiv 论文插图",
            provider="arxiv",
        )

    def resolve(self, paper: dict, *, now: dt.datetime | None = None) -> dict:
        checked_at = iso_z(now or utc_now())
        # PMC has structured media, figure captions, and article-level licence
        # metadata, so it is always preferred when a DOI/PMID maps there.
        errors = []
        try:
            pmc = self.resolve_pmc(paper, checked_at)
        except FetchError as exc:
            pmc = None
            errors.append(f"pmc: {exc}")
        if pmc is not None and pmc.get("status") == "available":
            return pmc
        try:
            arxiv = self.resolve_arxiv(paper, checked_at)
        except FetchError as exc:
            arxiv = None
            errors.append(f"arxiv: {exc}")
        if arxiv is not None and arxiv.get("status") == "available":
            return arxiv
        if pmc is not None and pmc.get("status") == "blocked":
            return pmc
        if arxiv is not None:
            return arxiv
        if pmc is not None:
            return pmc
        if errors:
            return _blank_visual(
                "error", checked_at=checked_at,
                reason="; ".join(errors)[:240],
            )
        return _blank_visual(
            "not_found", checked_at=checked_at,
            reason="no_supported_public_figure_source",
        )


def load_registry(path: Path) -> dict:
    if not path.exists():
        return {"schema_version": SCHEMA_VERSION, "updated_at": None,
                "records": {}}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"schema_version": SCHEMA_VERSION, "updated_at": None,
                "records": {}}
    records = payload.get("records") if isinstance(payload, dict) else None
    if not isinstance(records, dict):
        records = {}
    return {
        "schema_version": SCHEMA_VERSION,
        "updated_at": payload.get("updated_at") if isinstance(payload, dict) else None,
        "records": records,
    }


def save_registry(path: Path, registry: dict, *, now: dt.datetime | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    registry["schema_version"] = SCHEMA_VERSION
    registry["updated_at"] = iso_z(now or utc_now())
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(
        json.dumps(registry, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.replace(temp, path)


def should_refresh(record: object, *, now: dt.datetime | None = None,
                   force: bool = False) -> bool:
    if force or not isinstance(record, dict):
        return True
    checked = parse_timestamp(record.get("checked_at"))
    if checked is None:
        return True
    age = (now or utc_now()) - checked
    status = record.get("status")
    ttl = {
        "available": dt.timedelta(days=180),
        "blocked": dt.timedelta(days=180),
        "not_found": dt.timedelta(days=30),
        "error": dt.timedelta(days=1),
    }.get(status, dt.timedelta(0))
    return age >= ttl


def iter_candidates(
        daily_dir: Path, priorities: set[str],
        identities: set[str] | None = None) -> list[tuple[str, dict, str]]:
    candidates: dict[str, tuple[dict, str]] = {}
    for path in sorted(daily_dir.glob("*.json"), reverse=True):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        papers = payload if isinstance(payload, list) else payload.get("papers", [])
        if not isinstance(papers, list):
            continue
        for paper in papers:
            if not isinstance(paper, dict):
                continue
            priority = str((paper.get("llm") or {}).get("priority") or "")
            if priority not in priorities:
                continue
            key = identity_key(paper)
            if identities is not None and key not in identities:
                continue
            if key and key not in candidates:
                candidates[key] = (paper, path.stem)
    order = {"High": 0, "Medium": 1}
    rows = [
        (key, paper, date) for key, (paper, date) in candidates.items()
    ]
    # Stable two-pass sort: newest Radar discovery first, then High before
    # Medium within the same discovery time. Publication buckets may be dated
    # in the future and therefore are not a reliable recency signal.
    rows.sort(key=lambda item: (
        order.get(str((item[1].get("llm") or {}).get("priority")), 9),
        item[0],
    ))
    rows.sort(
        key=lambda item: str(item[1].get("first_seen_at") or item[2]),
        reverse=True,
    )
    return rows


def enrich(*, daily_dir: Path, index_path: Path, resolver: VisualResolver,
           limit: int, priorities: set[str], force: bool = False,
           write: bool = True, now: dt.datetime | None = None,
           identities: set[str] | None = None) -> dict:
    current_time = now or utc_now()
    registry = load_registry(index_path)
    records = registry["records"]
    attempted = 0
    counts: dict[str, int] = {}
    for key, paper, _bucket_date in iter_candidates(
            daily_dir, priorities, identities):
        if attempted >= limit:
            break
        if not should_refresh(records.get(key), now=current_time, force=force):
            continue
        attempted += 1
        try:
            visual = resolver.resolve(paper, now=current_time)
        except Exception as exc:  # one provider/paper must never stop the batch
            visual = _blank_visual(
                "error", checked_at=iso_z(current_time),
                reason=f"{type(exc).__name__}: {str(exc)[:240]}",
            )
        records[key] = visual
        status = str(visual.get("status") or "error")
        counts[status] = counts.get(status, 0) + 1
        if write:
            save_registry(index_path, registry, now=current_time)
    return {"attempted": attempted, "counts": counts,
            "registry_records": len(records), "registry": registry}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Discover licence-safe public figures for Radar cards.",
    )
    parser.add_argument("--daily-dir", type=Path, default=DEFAULT_DAILY_DIR)
    parser.add_argument("--index", type=Path, default=DEFAULT_INDEX_PATH)
    parser.add_argument("--limit", type=int, default=DEFAULT_LIMIT)
    parser.add_argument(
        "--priorities", nargs="+", default=["High", "Medium"],
        choices=["High", "Medium", "Low", "Exclude"],
    )
    parser.add_argument(
        "--identity", action="append", default=None,
        help=("Resolve only this exact public identity key (repeatable), "
              "for example doi:10.1234/example."),
    )
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT_SECONDS)
    parser.add_argument("--min-delay", type=float,
                        default=DEFAULT_MIN_DELAY_SECONDS)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--no-write", action="store_true",
                        help="Resolve records but do not update the sidecar.")
    parser.add_argument(
        "--email", default=os.environ.get("PUBMED_EMAIL", ""),
        help="Contact email sent to the PMC ID Converter API.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.limit < 1:
        print("--limit must be at least 1", file=sys.stderr)
        return 2
    if args.timeout <= 0 or args.min_delay < 0:
        print("--timeout must be > 0 and --min-delay must be >= 0", file=sys.stderr)
        return 2
    client = HttpClient(timeout=args.timeout, min_delay=args.min_delay)
    resolver = VisualResolver(client, email=args.email)
    result = enrich(
        daily_dir=args.daily_dir, index_path=args.index,
        resolver=resolver, limit=args.limit,
        priorities=set(args.priorities), force=args.force,
        write=not args.no_write,
        identities=set(args.identity) if args.identity else None,
    )
    print(json.dumps({key: value for key, value in result.items()
                      if key != "registry"}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
