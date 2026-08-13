import base64
import datetime as dt
import html as html_mod
import json
import pathlib
import sys
import urllib.error

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scripts import enrich_visuals as ev


UTC = dt.timezone.utc
NOW = dt.datetime(2026, 8, 12, 12, 0, tzinfo=UTC)

THIRD_PARTY_PRODUCTION_CAPTIONS = (
    "Figure 1: Examples of laboratory devices for granular materials in "
    "(a) triaxial compression and (b) continuous ring-shear conditions. "
    "Copyright: Dietmar Schulze .",
    "Schematic diagram of the experimental design. Created with "
    "BioRender.com (License number: AV27FQ9RWZ).",
    "A new paradigm in patient-matched scaffold-guided bone regeneration. "
    "Created in BioRender. Crook, J. "
    "(https://BioRender.com/e8aq7lf).",
    "Figure 1: Principle of Surrogate-Based Optimization (SBO), "
    "reproduced from [ 12 ] .",
    "Figure 3: From Keil et al. 2021 : On the floor with domain Ω.",
    "Figure 2: Reference measurements from Choi et al. of wake "
    "characteristics behind a single sphere.",
    "Biomaterial ink synthesis workflow (made using Illustrae [29]).",
    "Topographic map of water catchment and gauging stations "
    "( 45 , source:) .",
    "BEAR for studying the mechanics of additively manufactured components. "
    "(Photo credit: Aldair E. Gongora and Bowen Xu, Boston University).",
    "(a) The three-dimensional printing protocol developed by MX3D uses a "
    "weld head attached to a robotic arm (image by Joris Laarman, "
    "www.jorislaarman.com). (b) Pedestrian bridge manufactured using "
    "three-dimensional-printed steel [5].",
)

ORDINARY_SCIENTIFIC_CAPTIONS = (
    "Figure 8: Intermediate representations for the sign-example from "
    "van Amersfoort et al. 2020.",
    "Measurements use data from the validation set.",
    "From left to right, we show the source function and target function.",
    "Comparison against the reference solution.",
    "The data source: simulation output.",
    "The modified field preserves the original boundary values.",
    "Measurements taken from the dataset are shown in blue.",
    "Samples taken from a test set validate the modified scalar field.",
)


class FakeHttpResponse:
    def __init__(self, payload=b"{}", *, url="https://example.test/data",
                 content_length=None, content_type=None):
        self.payload = payload
        self.url = url
        self.headers = {}
        if content_length is not None:
            self.headers["Content-Length"] = str(content_length)
        if content_type is not None:
            self.headers["Content-Type"] = content_type
        self.closed = False

    def geturl(self):
        return self.url

    def read(self, limit):
        return self.payload[:limit]

    def close(self):
        self.closed = True


class FakeOpener:
    def __init__(self, *outcomes):
        self.outcomes = list(outcomes)
        self.calls = []

    def open(self, request, timeout):
        self.calls.append((request, timeout))
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def png_header(width, height):
    return (
        b"\x89PNG\r\n\x1a\n" + b"\x00\x00\x00\x0dIHDR" +
        width.to_bytes(4, "big") + height.to_bytes(4, "big") +
        b"\x08\x02\x00\x00\x00" + b"\x00\x00\x00\x00"
    )


def webp_image(kind, data):
    chunk = kind + len(data).to_bytes(4, "little") + data
    if len(data) % 2:
        chunk += b"\x00"
    body = b"WEBP" + chunk
    return b"RIFF" + len(body).to_bytes(4, "little") + body


def safe_svg(*, width="640", height="480", body="<path d='M0 0h1v1z'/>"):
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" '
        f'height="{height}" viewBox="0 0 640 480">{body}</svg>'
    ).encode()


def test_http_client_encodes_params_and_bounds_provider_response():
    response = FakeHttpResponse(
        b'{"records": []}',
        url="https://pmc.ncbi.nlm.nih.gov/result",
    )
    opener = FakeOpener(response)
    client = ev.HttpClient(opener=opener, min_delay=0)
    payload = client.get_json(
        ev.ID_CONVERTER_URL,
        params={"ids": "10.1/a b", "format": "json"},
        allowed_hosts={"pmc.ncbi.nlm.nih.gov"},
    )
    assert payload == {"records": []}
    requested_url = opener.calls[0][0].full_url
    assert "ids=10.1%2Fa+b" in requested_url
    assert response.closed

    oversized = FakeHttpResponse(
        b"x", url="https://pmc.ncbi.nlm.nih.gov/result",
        content_length=100,
    )
    client = ev.HttpClient(opener=FakeOpener(oversized), min_delay=0)
    try:
        client.get_bytes(
            ev.ID_CONVERTER_URL,
            allowed_hosts={"pmc.ncbi.nlm.nih.gov"}, max_bytes=10,
        )
    except ev.FetchError as exc:
        assert "size limit" in str(exc)
    else:
        raise AssertionError("oversized provider response was accepted")
    assert oversized.closed


def test_http_client_retries_transient_status_and_rejects_cross_host_redirect(
        monkeypatch):
    monkeypatch.setattr(ev.time, "sleep", lambda _seconds: None)
    transient = urllib.error.HTTPError(
        ev.ID_CONVERTER_URL, 429, "rate limited", {}, None,
    )
    success = FakeHttpResponse(
        b"ok", url="https://pmc.ncbi.nlm.nih.gov/result",
    )
    opener = FakeOpener(transient, success)
    client = ev.HttpClient(opener=opener, min_delay=0, max_attempts=2)
    assert client.get_bytes(
        ev.ID_CONVERTER_URL,
        allowed_hosts={"pmc.ncbi.nlm.nih.gov"},
    ) == b"ok"
    assert len(opener.calls) == 2

    redirected = FakeHttpResponse(url="https://publisher.example/figure")
    client = ev.HttpClient(opener=FakeOpener(redirected), min_delay=0)
    try:
        client.get_bytes(
            ev.ID_CONVERTER_URL,
            allowed_hosts={"pmc.ncbi.nlm.nih.gov"},
        )
    except ev.FetchError as exc:
        assert "redirected outside" in str(exc)
    else:
        raise AssertionError("cross-host redirect was accepted")
    assert redirected.closed


def test_http_client_accepts_only_official_arxiv_oai_redirect_hosts():
    migrated = FakeHttpResponse(
        b"<OAI-PMH />", url="https://oaipmh.arxiv.org/oai?verb=Identify",
    )
    client = ev.HttpClient(opener=FakeOpener(migrated), min_delay=0)
    assert client.get_bytes(
        "https://export.arxiv.org/oai2",
        allowed_hosts=ev.ARXIV_OAI_HOSTS,
    ) == b"<OAI-PMH />"
    assert migrated.closed

    outside = FakeHttpResponse(
        b"<OAI-PMH />", url="https://metadata.example/oai",
    )
    client = ev.HttpClient(opener=FakeOpener(outside), min_delay=0)
    try:
        client.get_bytes(
            "https://export.arxiv.org/oai2",
            allowed_hosts=ev.ARXIV_OAI_HOSTS,
        )
    except ev.FetchError as exc:
        assert "redirected outside" in str(exc)
    else:
        raise AssertionError("non-arXiv OAI redirect was accepted")
    assert outside.closed


def test_http_client_returns_png_dimensions_and_rejects_html():
    png = FakeHttpResponse(
        png_header(640, 480), url="https://arxiv.org/html/figure.png",
    )
    dimensions = ev.HttpClient(opener=FakeOpener(png), min_delay=0).verify_image(
        "https://arxiv.org/html/figure.png", allowed_hosts={"arxiv.org"},
    )
    assert dimensions == (640, 480)

    html = FakeHttpResponse(
        b"<!doctype html><title>404</title>",
        url="https://arxiv.org/html/missing.png",
    )
    try:
        ev.HttpClient(opener=FakeOpener(html), min_delay=0).verify_image(
            "https://arxiv.org/html/missing.png", allowed_hosts={"arxiv.org"},
        )
    except ev.FetchError as exc:
        assert "invalid signature" in str(exc)
    else:
        raise AssertionError("an HTML error page was accepted as an image")


def test_http_client_accepts_only_svg_mime_on_exact_arxiv_html_path():
    url = "https://arxiv.org/html/2608.12345v1/figures/result.svg"
    response = FakeHttpResponse(
        safe_svg(width="480pt", height="240pt"), url=url,
        content_type="image/svg+xml; charset=utf-8",
    )
    client = ev.HttpClient(opener=FakeOpener(response), min_delay=0)

    assert client.verify_svg(url, allowed_hosts={"arxiv.org"}) == (640, 320)
    assert response.closed

    wrong_type = FakeHttpResponse(
        safe_svg(), url=url, content_type="text/xml",
    )
    with pytest.raises(ev.SvgValidationError, match="media type"):
        ev.HttpClient(opener=FakeOpener(wrong_type), min_delay=0).verify_svg(
            url, allowed_hosts={"arxiv.org"},
        )


def test_http_client_caps_svg_response_at_two_mib():
    assert ev.MAX_SVG_BYTES == 2 * 1024 * 1024
    url = "https://arxiv.org/html/2608.12345v1/result.svg"
    oversized = FakeHttpResponse(
        safe_svg(), url=url, content_length=ev.MAX_SVG_BYTES + 1,
        content_type="image/svg+xml",
    )

    with pytest.raises(ev.FetchError, match="size limit"):
        ev.HttpClient(opener=FakeOpener(oversized), min_delay=0).verify_svg(
            url, allowed_hosts={"arxiv.org"},
        )
    assert oversized.closed


def test_http_client_rejects_svg_redirect_to_another_arxiv_work():
    requested = "https://arxiv.org/html/2608.12345v1/result.svg"
    redirected = FakeHttpResponse(
        safe_svg(),
        url="https://arxiv.org/html/2608.99999v1/result.svg",
        content_type="image/svg+xml",
    )
    with pytest.raises(ev.SvgValidationError, match="work path"):
        ev.HttpClient(opener=FakeOpener(redirected), min_delay=0).verify_svg(
            requested, allowed_hosts={"arxiv.org"},
        )


@pytest.mark.parametrize("url", [
    "http://arxiv.org/html/2608.12345/figure.svg",
    "https://export.arxiv.org/html/2608.12345/figure.svg",
    "https://arxiv.org:443/html/2608.12345/figure.svg",
    "https://arxiv.org/pdf/2608.12345/figure.svg",
    "https://arxiv.org/html/2608.12345/../figure.svg",
    "https://arxiv.org/html/2608.12345/figure.svg?download=1",
    "https://arxiv.org/html/2608.12345/figure.svg#panel",
    "https://arxiv.org/html/2608.12345/figure%2esvg",
    "https://arxiv.org/html/2608.12345/figure.svg",
    "https://arxiv.org/html/hep-th/9901001/figure.svg",
    "https://arxiv.org/html/not-an-id-v2/figure.svg",
])
def test_svg_url_boundary_rejects_nonexact_arxiv_html_assets(url):
    assert ev._arxiv_svg_url(url) == ""


def test_svg_validator_allows_internal_references_and_embedded_raster():
    embedded = base64.b64encode(png_header(32, 32)).decode()
    payload = safe_svg(body=(
        "<defs><linearGradient id='g'><stop offset='0'/></linearGradient>"
        "<clipPath id='c'><path d='M0 0h1v1z'/></clipPath></defs>"
        "<g style='fill:url(#g)' clip-path='url(#c)'>"
        "<use href='#c'/><image href='data:image/png;base64,"
        f"{embedded}'/></g>"
    ))

    assert ev._svg_dimensions(payload) == (640, 480)


def test_svg_validator_rejects_embedded_raster_decode_bomb_dimensions():
    assert ev.MAX_SVG_EMBEDDED_RASTER_PIXELS == 100_000_000
    embedded = base64.b64encode(png_header(100_000, 100_000)).decode()
    with pytest.raises(ev.SvgValidationError, match="pixel limit"):
        ev._svg_dimensions(safe_svg(
            body=f"<image href='data:image/png;base64,{embedded}'/>",
        ))


@pytest.mark.parametrize("body", [
    "<script>alert(1)</script>",
    "<foreignObject><div>active HTML</div></foreignObject>",
    "<animate attributeName='x' to='2'/>",
    "<animateColor attributeName='fill' to='red'/>",
    "<path onload='alert(1)'/>",
    "<image href='https://publisher.example/image.png'/>",
    "<use href='../symbols.svg#mark'/>",
    "<style>@import url(https://publisher.example/a.css)</style>",
    "<path style='fill:url(https://publisher.example/pattern.svg#p)'/>",
    r"<path fill='u\72l(https://publisher.example/pattern.svg#p)'/>",
    "<path fill='u/**/rl(../pattern.svg#p)'/>",
    "<image href='data:image/svg+xml;base64,PHN2Zy8+'/>",
])
def test_svg_validator_rejects_active_or_external_content(body):
    with pytest.raises(ev.SvgValidationError):
        ev._svg_dimensions(safe_svg(body=body))


@pytest.mark.parametrize("payload", [
    b"<html><body>not SVG</body></html>",
    b"<svg><broken></svg>",
    b"<!DOCTYPE svg><svg width='10' height='10'/>",
    b"<!DOCTYPE svg [<!ENTITY x 'x'>]><svg width='10' height='10'/>",
    b"<svg width='100%' height='100%'/>",
    b"<svg viewBox='0 0 0 100'/>",
])
def test_svg_validator_fails_closed_on_malformed_xml_or_dimensions(payload):
    with pytest.raises(ev.SvgValidationError):
        ev._svg_dimensions(payload)


def test_svg_validator_rejects_non_utf8_and_encoded_doctype_bypass():
    utf16 = (
        '<?xml version="1.0" encoding="UTF-16"?>'
        '<!DOCTYPE svg [<!ENTITY x "external">]>'
        '<svg xmlns="http://www.w3.org/2000/svg" width="100" height="100">'
        '<text>&x;</text></svg>'
    ).encode("utf-16")
    with pytest.raises(ev.SvgValidationError, match="UTF-8"):
        ev._svg_dimensions(utf16)

    latin1 = safe_svg().replace(b"</svg>", b"<text>\xe9</text></svg>")
    with pytest.raises(ev.SvgValidationError, match="UTF-8"):
        ev._svg_dimensions(latin1)


def test_svg_validator_rejects_subpixel_rounding_and_one_sided_geometry():
    with pytest.raises(ev.SvgValidationError, match="dimensions"):
        ev._svg_dimensions(safe_svg(width="0.4", height="100"))
    with pytest.raises(ev.SvgValidationError, match="dimensions"):
        ev._svg_dimensions(
            b'<svg xmlns="http://www.w3.org/2000/svg" width="100" '
            b'viewBox="0 0 200 100"/>',
        )


@pytest.mark.parametrize(("width", "height"), [
    ("0", "100"),
    ("100", "0"),
    ("-100", "100"),
    ("100", "-100"),
])
def test_svg_validator_does_not_fallback_from_explicit_invalid_dimensions(
        width, height):
    payload = (
        '<svg xmlns="http://www.w3.org/2000/svg" '
        f'width="{width}" height="{height}" viewBox="0 0 200 100"/>'
    ).encode()
    with pytest.raises(ev.SvgValidationError, match="dimensions"):
        ev._svg_dimensions(payload)


@pytest.mark.parametrize("url", [
    "https://arxiv.org/html/2608.12345v1/figure.svg",
    "https://arxiv.org/html/hep-th/9901001v2/figures/figure.svg",
])
def test_svg_url_boundary_accepts_versioned_new_and_old_arxiv_ids(url):
    assert ev._arxiv_svg_url(url) == url


def test_svg_validator_bounds_depth_elements_attributes_and_embedded_images(
        monkeypatch):
    monkeypatch.setattr(ev, "MAX_SVG_DEPTH", 2)
    with pytest.raises(ev.SvgValidationError, match="complexity"):
        ev._svg_dimensions(safe_svg(body="<g><g><path/></g></g>"))

    monkeypatch.setattr(ev, "MAX_SVG_DEPTH", 64)
    monkeypatch.setattr(ev, "MAX_SVG_ELEMENTS", 2)
    with pytest.raises(ev.SvgValidationError, match="complexity"):
        ev._svg_dimensions(safe_svg(body="<g/><g/>"))

    monkeypatch.setattr(ev, "MAX_SVG_ELEMENTS", 20_000)
    monkeypatch.setattr(ev, "MAX_SVG_ATTRIBUTES", 1)
    with pytest.raises(ev.SvgValidationError, match="complexity"):
        ev._svg_dimensions(safe_svg())

    monkeypatch.setattr(ev, "MAX_SVG_ATTRIBUTES", 100_000)
    monkeypatch.setattr(ev, "MAX_SVG_EMBEDDED_IMAGES", 1)
    embedded = base64.b64encode(png_header(32, 32)).decode()
    images = (
        f"<image href='data:image/png;base64,{embedded}'/>" * 2
    )
    with pytest.raises(ev.SvgValidationError, match="too many"):
        ev._svg_dimensions(safe_svg(body=images))


def test_raster_dimensions_cover_jpeg_gif_and_all_webp_headers():
    jpeg = (
        b"\xff\xd8\xff\xe0\x00\x04ab" +
        b"\xff\xc2\x00\x0b\x08" +
        (720).to_bytes(2, "big") + (1280).to_bytes(2, "big") +
        b"\x01\x01\x11\x00"
    )
    gif = (
        b"GIF89a" + (320).to_bytes(2, "little") +
        (240).to_bytes(2, "little") + b"\x00\x00\x00"
    )
    vp8x = webp_image(
        b"VP8X", b"\x00\x00\x00\x00" +
        (799).to_bytes(3, "little") + (599).to_bytes(3, "little"),
    )
    lossless_bits = (511 - 1) | ((257 - 1) << 14)
    vp8l = webp_image(
        b"VP8L", b"\x2f" + lossless_bits.to_bytes(4, "little"),
    )
    vp8 = webp_image(
        b"VP8 ", b"\x00\x00\x00\x9d\x01\x2a" +
        (640).to_bytes(2, "little") + (360).to_bytes(2, "little"),
    )

    assert ev._raster_dimensions(jpeg) == (1280, 720)
    assert ev._raster_dimensions(gif) == (320, 240)
    assert ev._raster_dimensions(vp8x) == (800, 600)
    assert ev._raster_dimensions(vp8l) == (511, 257)
    assert ev._raster_dimensions(vp8) == (640, 360)


@pytest.mark.parametrize("payload", [
    b"\x89PNG\r\n\x1a\ntruncated",
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\x0cIHDR" + b"\x00" * 17,
    png_header(0, 480),
    png_header(ev.MAX_IMAGE_DIMENSION + 1, 1),
    b"GIF89a\x01",
    b"\xff\xd8\xff\xda\x00\x02",
    b"RIFF\x10\x00\x00\x00WEBPVP8X\x0a\x00\x00\x00short",
    b"RIFF\xff\xff\xff\x7fWEBP",
])
def test_raster_dimensions_fail_closed_on_malformed_headers(payload):
    with pytest.raises(ev.FetchError):
        ev._raster_dimensions(payload)


def test_normalize_license_is_fail_closed():
    assert ev.normalize_license("CC BY 4.0") == "CC BY"
    assert ev.normalize_license("https://creativecommons.org/licenses/by-sa/4.0/") == "CC BY-SA"
    assert ev.normalize_license("https://creativecommons.org/publicdomain/zero/1.0/") == "CC0"
    assert ev.normalize_license("CC-BY-NC-SA-4.0") == "CC BY-NC-SA"
    assert ev.normalize_license("arXiv perpetual non-exclusive license").startswith("arXiv")
    assert ev.ALLOWED_LICENSES == {"CC0", "CC BY", "CC BY-SA"}


def test_pmc_media_url_allows_only_public_raster_bucket_objects():
    assert ev.pmc_media_url(
        "s3://pmc-oa-opendata/PMC123.1/gr1.jpg?md5=abc"
    ) == "https://pmc-oa-opendata.s3.amazonaws.com/PMC123.1/gr1.jpg"
    assert ev.pmc_media_url(
        "https://pmc-oa-opendata.s3.amazonaws.com/PMC123.1/gr2.webp?md5=abc"
    ).endswith("gr2.webp?md5=abc")
    assert ev.pmc_media_url(
        "s3://pmc-oa-opendata/deprecated/oa_package/gr1.jpg"
    ) == ""
    assert ev.pmc_media_url("https://publisher.example/gr1.jpg") == ""
    assert ev.pmc_media_url(
        "s3://pmc-oa-opendata/PMC123.1/unsafe.svg"
    ) == ""


def test_select_pmc_figure_skips_third_party_caption_and_prefers_safe_one():
    xml = """
    <article xmlns:xlink="http://www.w3.org/1999/xlink">
      <body>
        <fig>
          <label>Figure 1</label>
          <caption><p>Adapted with permission from Example Publisher.</p></caption>
          <graphic xlink:href="gr1.jpg" />
        </fig>
        <fig>
          <label>Figure 2</label>
          <caption><p>Finite-element workflow and validation setup.</p></caption>
          <graphic xlink:href="gr2.jpg" />
        </fig>
      </body>
    </article>
    """
    selected = ev.select_pmc_figure(xml, [
        "s3://pmc-oa-opendata/PMC123.1/gr1.jpg",
        "s3://pmc-oa-opendata/PMC123.1/gr2.jpg",
    ])
    assert selected is not None
    assert selected["label"] == "Figure 2"
    assert selected["image_url"].endswith("/PMC123.1/gr2.jpg")


def test_arxiv_and_pmc_reject_all_production_third_party_captions():
    media_url = "s3://pmc-oa-opendata/PMC123.1/gr1.jpg"
    for caption in THIRD_PARTY_PRODUCTION_CAPTIONS:
        escaped = html_mod.escape(caption)
        arxiv_html = (
            '<figure><img src="figures/result.png" alt="Result field" />'
            f'<figcaption>{escaped}</figcaption></figure>'
        )
        assert ev.select_arxiv_figure(
            arxiv_html, "https://arxiv.org/html/2608.12345",
        ) is None, caption

        pmc_xml = (
            '<article xmlns:xlink="http://www.w3.org/1999/xlink"><body>'
            f'<fig><caption><p>{escaped}</p></caption>'
            '<graphic xlink:href="gr1.jpg" /></fig></body></article>'
        )
        assert ev.select_pmc_figure(pmc_xml, [media_url]) is None, caption


def test_rights_policy_covers_attribution_variants_and_alt_text():
    risky_variants = (
        "Adapted from Example Publisher.",
        "Reprinted, with permission, from Example Publisher.",
        "Photograph courtesy of Example Laboratory.",
        "Figure credit: Example Agency.",
        "Photo—credit: Example Agency.",
        "Photograph, credit—Example Agency.",
        "Image by Example Artist.",
        "Photo by Example Photographer.",
        "Photograph by Example Photographer.",
        "Illustration by Example Studio.",
        "Graphic—by Example Agency.",
        "Diagram by: 'ana pérez'.",
        "Artwork by © naïve atelier.",
        "Photograph created by mélange studio.",
        "Figure made by “mixedCase collective”.",
        "Illustration provided by 株式会社アート.",
        "Graphic supplied by 李明.",
        "Copyright.",
        "Copyright, Example Author.",
        "Copyrighted Example Publisher.",
        "Modified from [12].",
        "Redrawn from Smith et al.",
        "Taken from Jones et al. (2020).",
        "Diagram designed via Mind the Graph.",
        "Diagram created by BioRender.",
        "Diagram created on BioRender.com.",
        "Made with Bio Render.",
        "Stock photo of the experimental apparatus.",
        "Copyright© Example Author.",
    )
    assert all(ev.caption_has_third_party_rights(value)
               for value in risky_variants)

    selected = ev.select_arxiv_figure(
        '<figure><img src="result.png" '
        'alt="Created using BioRender.com" />'
        '<figcaption>Otherwise neutral result.</figcaption></figure>',
        "https://arxiv.org/html/2608.12345",
    )
    assert selected is None

    selected_pmc = ev.select_pmc_figure(
        '<article xmlns:xlink="http://www.w3.org/1999/xlink"><body><fig>'
        '<caption><p>Otherwise neutral result.</p></caption>'
        '<alt-text>Made using Illustrae [29].</alt-text>'
        '<graphic xlink:href="gr1.jpg" /></fig></body></article>',
        ["s3://pmc-oa-opendata/PMC123.1/gr1.jpg"],
    )
    assert selected_pmc is None


def test_rights_policy_does_not_reject_ordinary_scientific_from_or_source():
    media_url = "s3://pmc-oa-opendata/PMC123.1/gr1.jpg"
    for caption in ORDINARY_SCIENTIFIC_CAPTIONS:
        assert not ev.caption_has_third_party_rights(caption), caption
        escaped = html_mod.escape(caption)
        arxiv = ev.select_arxiv_figure(
            '<figure><img src="result.png" />'
            f'<figcaption>{escaped}</figcaption></figure>',
            "https://arxiv.org/html/2608.12345",
        )
        assert arxiv is not None, caption
        pmc = ev.select_pmc_figure(
            '<article xmlns:xlink="http://www.w3.org/1999/xlink"><body>'
            f'<fig><caption><p>{escaped}</p></caption>'
            '<graphic xlink:href="gr1.jpg" /></fig></body></article>',
            [media_url],
        )
        assert pmc is not None, caption


def test_rights_policy_does_not_confuse_scientific_by_phrases_with_credits():
    ordinary = (
        "Figure 2: Image generated by the surrogate model.",
        "Figure 2: Image produced by model predictions.",
        "Figure 2: image by Fourier transformation.",
        "Figure 2: image by inverse Fourier transformation.",
        "Figure 2: image by FFT.",
        "Figure 2: image by PCA.",
        "Figure 2: image by finite element analysis.",
        "Figure 2: image by Bayesian optimization.",
        "Figure 2: image by Design A.",
        "Figure 2: Image by Applying a Fourier transform.",
        "We obtain the image by applying a Gaussian filter.",
        "Figure 2: image created by applying a Gaussian filter.",
        "Figure 2: image provided by the finite-element solver.",
        "The graphic is followed by a quantitative comparison.",
        "Illustration produced by the finite-element solver.",
        "Photograph intensity is normalized by the reference field.",
        "The image bytes are decoded before plotting.",
        "Each image byte is normalized independently.",
        "The figure bypasses the interpolation stage.",
        "The graphic byproduct is removed during preprocessing.",
    )
    assert all(not ev.caption_has_third_party_rights(value)
               for value in ordinary)


def test_arxiv_selector_skips_real_ltx_table_image_structures():
    # arXiv 2405.17858v1: repeated cycle thumbnails are cells in a semantic
    # table and inherit its Table 1 caption.  The following ordinary figure
    # is the first eligible card candidate.
    fatigue_html = """
    <figure id="S3.T1" class="ltx_table">
      <table class="ltx_tabular"><tbody><tr><td>
        <img src="pictures/triangularCycle.png" id="S3.T1.g1"
             class="ltx_graphics ltx_img_square" width="32" height="29"
             alt="[Uncaptioned image]" />
      </td></tr></tbody></table>
      <figcaption><span class="ltx_tag ltx_tag_table">Table 1:</span>
        Overview of the experimental data selected.</figcaption>
    </figure>
    <figure id="S4.F4" class="ltx_figure">
      <img src="saadi_bootstrap6.png" width="600" height="420"
           alt="Bootstrap workflow" />
      <figcaption>Figure 4: Bootstrap sampling over blocks.</figcaption>
    </figure>
    """
    selected = ev.select_arxiv_figure(
        fatigue_html, "https://arxiv.org/html/2405.17858v1",
    )
    assert selected is not None
    assert selected["image_url"].endswith("/saadi_bootstrap6.png")
    assert selected["caption"].startswith("Figure 4:")

    # arXiv 2505.01281v2: the table caption precedes a grid of example
    # rasters.  The DOM ordering difference must not make B1.png eligible.
    transfer_html = """
    <figure id="S1.T1" class="ltx_table">
      <figcaption><span class="ltx_tag ltx_tag_table">Table 1:</span>
        Simulation datasets used for experiments.</figcaption>
      <table class="ltx_tabular"><tbody><tr><td>
        <img src="B1.png" width="144" height="72"
             alt="[Uncaptioned image]" />
      </td><td><img src="B2.png" width="144" height="72" /></td></tr>
      </tbody></table>
    </figure>
    <figure id="S1.F1" class="ltx_figure ltx_align_floatright">
      <img src="Dcodd.png" width="360" height="240" alt="Domain result" />
      <figcaption>Figure 1: Visualization of the domain adaptation method.
      </figcaption>
    </figure>
    """
    selected = ev.select_arxiv_figure(
        transfer_html, "https://arxiv.org/html/2505.01281v2",
    )
    assert selected is not None
    assert selected["image_url"].endswith("/Dcodd.png")


def test_arxiv_table_filter_does_not_reject_ordinary_figure_layout():
    html = """
    <figure id="S2.F1" class="ltx_figure ltx_align_center">
      <table class="comparison-layout"><tbody><tr><td>
        <img src="comparison.png" width="480" height="320"
             alt="Comparison field" />
      </td></tr></tbody></table>
      <figcaption>Figure 1: Comparison of computed fields.</figcaption>
    </figure>
    """
    selected = ev.select_arxiv_figure(
        html, "https://arxiv.org/html/2608.12345",
    )
    assert selected is not None
    assert selected["image_url"].endswith("/comparison.png")


def test_arxiv_selector_skips_uncaptioned_image_for_next_reviewable_figure():
    html = """
    <figure><img src="figures/uncaptioned.png"
                 alt="[Uncaptioned image]" /></figure>
    <figure><img src="figures/placeholder.png" alt="Scientific image" />
      <figcaption>[Uncaptioned figure]</figcaption></figure>
    <figure><img src="figures/reviewable.png"
                 alt="[Uncaptioned image]" />
      <figcaption>Figure 2: Validated stress field.</figcaption></figure>
    """

    selected = ev.select_arxiv_figure(
        html, "https://arxiv.org/html/2608.12345",
    )

    assert selected is not None
    assert selected["image_url"].endswith("/figures/reviewable.png")
    assert selected["caption"] == "Figure 2: Validated stress field."


def test_arxiv_selector_returns_none_when_all_captions_are_unreviewable():
    html = """
    <figure><img src="figures/no-caption.png" /></figure>
    <figure><img src="figures/placeholder.png" />
      <figcaption>See caption.</figcaption></figure>
    """
    assert ev.select_arxiv_figure(
        html, "https://arxiv.org/html/2608.12345",
    ) is None

    media_url = "s3://pmc-oa-opendata/PMC123.1/gr1.jpg"
    placeholders = (
        "", "Graphical abstract", "Graphical abstract:", "Fig. 1",
        "Figure 1:", "[No caption available]", "Uncaptioned photograph",
    )
    for caption in placeholders:
        escaped = html_mod.escape(caption)
        arxiv_html = (
            '<figure><img src="figure.png" />'
            f'<figcaption>{escaped}</figcaption></figure>'
        )
        assert ev.select_arxiv_figure(
            arxiv_html, "https://arxiv.org/html/2608.12345",
        ) is None
        xml = (
            '<article xmlns:xlink="http://www.w3.org/1999/xlink"><body>'
            f'<fig><caption><p>{escaped}</p></caption>'
            '<graphic xlink:href="gr1.jpg" /></fig></body></article>'
        )
        assert ev.select_pmc_figure(xml, [media_url]) is None


def test_arxiv_selector_checks_rights_text_outside_figcaption():
    html = """
    <figure>
      <img src="figures/risky.png" />
      <figcaption>Figure 1: Otherwise reviewable scientific result.</figcaption>
      <div class="ltx_role_note">Photograph by Example Photographer.</div>
    </figure>
    <figure>
      <img src="figures/safe.png" />
      <figcaption>Figure 2: Independent validation result.</figcaption>
    </figure>
    """

    selected = ev.select_arxiv_figure(
        html, "https://arxiv.org/html/2608.12345",
    )

    assert selected is not None
    assert selected["image_url"].endswith("/figures/safe.png")
    assert selected["caption"].startswith("Figure 2:")


def test_arxiv_parser_keeps_display_caption_separate_from_outer_figure_text():
    parser = ev.ArxivFigureParser()
    parser.feed("""
    <figure><span>Redrawn from Example Publisher.</span>
      <img src="figure.png" />
      <figcaption>Figure 1: Scientific result.</figcaption>
    </figure>
    """)
    figure = parser.figures[0]
    assert figure["caption"] == "Figure 1: Scientific result."
    assert figure["figure_text"] == (
        "Redrawn from Example Publisher. Figure 1: Scientific result."
    )


def test_pmc_selector_prefers_main_graphic_over_caption_inline_asset():
    xml = """
    <article xmlns:xlink="http://www.w3.org/1999/xlink"><body><fig>
      <label>Figure 1</label>
      <caption><p>Response <inline-graphic xlink:href="symbol.png" /> field.</p></caption>
      <graphic xlink:href="full-figure.png" />
    </fig></body></article>
    """
    selected = ev.select_pmc_figure(xml, [
        "s3://pmc-oa-opendata/PMC123.1/symbol.png",
        "s3://pmc-oa-opendata/PMC123.1/full-figure.png",
    ])
    assert selected is not None
    assert selected["image_url"].endswith("/full-figure.png")


def test_figure_selectors_skip_logos_covers_and_author_photos():
    xml = """
    <article xmlns:xlink="http://www.w3.org/1999/xlink"><body>
      <fig><label>Journal logo</label><graphic xlink:href="brand-logo.png" /></fig>
      <fig><label>Figure 1</label><caption><p>Validated workflow.</p></caption>
        <graphic xlink:href="workflow.png" /></fig>
    </body></article>
    """
    selected_pmc = ev.select_pmc_figure(xml, [
        "s3://pmc-oa-opendata/PMC123.1/brand-logo.png",
        "s3://pmc-oa-opendata/PMC123.1/workflow.png",
    ])
    assert selected_pmc is not None
    assert selected_pmc["image_url"].endswith("/workflow.png")

    html = """
    <html><body>
      <figure><img src="openmdao_main_logo.png" alt="Project logo" /></figure>
      <figure><img src="author-photo.jpg" alt="Author photo" /></figure>
      <figure><img src="figures/results.png" alt="Stress field" />
        <figcaption>Finite-element validation results.</figcaption></figure>
    </body></html>
    """
    selected_arxiv = ev.select_arxiv_figure(
        html, "https://arxiv.org/html/2606.13245",
    )
    assert selected_arxiv is not None
    assert selected_arxiv["image_url"].endswith("/figures/results.png")


def test_arxiv_selector_rejects_online_legend_asset_and_keeps_main_panel():
    # Mirrors arXiv:2606.13245, where a short legend panel follows the actual
    # convergence plot within the same outer figure.
    html = """
    <figure id="S4.F5" class="ltx_figure">
      <figure class="ltx_figure ltx_figure_panel">
        <img src="2606.13245v1/figures/convergence.png"
             width="476" height="263" alt="Refer to caption" />
      </figure>
      <figure class="ltx_figure ltx_figure_panel">
        <img src="2606.13245v1/figures/legend.png"
             width="476" height="31" alt="Refer to caption" />
      </figure>
      <figcaption>Figure 5: Convergence history.</figcaption>
    </figure>
    """

    selected = ev.select_arxiv_figure(
        html, "https://arxiv.org/html/2606.13245",
    )

    assert selected is not None
    assert selected["image_url"].endswith("/figures/convergence.png")
    assert not selected["image_url"].endswith("/figures/legend.png")


def test_arxiv_selector_never_promotes_legend_when_main_asset_is_not_raster():
    # The exact failure shape from arXiv:2606.13245 Figure 5: its main plot is
    # an SVG object, while the only raster <img> is the separate legend strip.
    html = """
    <figure id="S4.F5" class="ltx_figure">
      <figure class="ltx_figure ltx_figure_panel">
        <object type="image/svg+xml" data="2606.13245v1/main.svg"></object>
      </figure>
      <figure class="ltx_figure ltx_figure_panel">
        <img src="2606.13245v1/figures/legend.png"
             width="476" height="31" alt="Refer to caption" />
      </figure>
      <figcaption>Figure 5: Convergence history.</figcaption>
    </figure>
    <figure class="ltx_figure">
      <img src="2606.13245v1/figures/next-complete.png"
           width="600" height="400" alt="Complete result" />
      <figcaption>Figure 6: Complete validation result.</figcaption>
    </figure>
    """

    selected = ev.select_arxiv_figure(
        html, "https://arxiv.org/html/2606.13245",
    )

    assert selected is not None
    assert selected["image_url"].endswith("/figures/next-complete.png")


def test_arxiv_selector_uses_exact_svg_object_only_after_all_rasters():
    html = """
    <figure class="ltx_figure">
      <object type="image/svg+xml" data="2608.12345v2/workflow.svg"
              width="600" height="400"></object>
      <figcaption>Figure 1: Complete SVG workflow.</figcaption>
    </figure>
    <figure class="ltx_figure">
      <img src="figures/result.png" width="640" height="480" />
      <figcaption>Figure 2: Raster validation result.</figcaption>
    </figure>
    """

    candidates = ev.select_arxiv_figures(
        html, "https://arxiv.org/html/2608.12345",
    )

    assert [pathlib.PurePosixPath(row["image_url"]).suffix
            for row in candidates] == [".png", ".svg"]
    svg = candidates[1]
    assert svg["image_url"] == (
        "https://arxiv.org/html/2608.12345v2/workflow.svg"
    )
    assert svg["media_type"] == ev.SVG_MEDIA_TYPE


def test_arxiv_selector_rejects_svg_outside_html_path_and_rights_risk():
    html = """
    <figure class="ltx_figure">
      <object type="image/svg+xml"
              data="https://publisher.example/workflow.svg"></object>
      <figcaption>Figure 1: External workflow.</figcaption>
    </figure>
    <figure class="ltx_figure">
      <object type="image/svg+xml"
              data="https://arxiv.org/pdf/2608.12345/workflow.svg"></object>
      <figcaption>Figure 2: Wrong arXiv endpoint.</figcaption>
    </figure>
    <figure class="ltx_figure">
      <object type="image/svg+xml" data="risky.svg"></object>
      <figcaption>Figure 3: Architecture adopted from [23].</figcaption>
    </figure>
    """

    assert ev.select_arxiv_figures(
        html, "https://arxiv.org/html/2608.12345",
    ) == []

    # Selector v8's additional SVG-only guard must not alter the established
    # raster selector; the shared policy remains its source of truth.
    raster = ev.select_arxiv_figure(
        '<figure><img src="existing.png" />'
        '<figcaption>Figure 3: Architecture adopted from [23].</figcaption>'
        '</figure>',
        "https://arxiv.org/html/2608.12345",
    )
    assert raster is not None
    assert raster["image_url"].endswith("/html/existing.png")


def test_arxiv_selector_rejects_cross_work_official_svg():
    html = """
    <figure><object type="image/svg+xml"
      data="https://arxiv.org/html/2608.99999v1/other.svg"></object>
      <figcaption>Figure 1: Cross-work asset.</figcaption></figure>
    """
    assert ev.select_arxiv_figures(
        html, "https://arxiv.org/html/2608.12345v2",
    ) == []


def test_arxiv_selector_checks_object_labels_without_cross_figure_leakage():
    html = """
    <figure><object type="image/svg+xml" data="title-risk.svg"
      title="Copyright: Example Publisher"></object>
      <figcaption>Figure 1: First workflow.</figcaption></figure>
    <figure><object type="image/svg+xml" data="aria-risk.svg"
      aria-label="Image by Example Artist"></object>
      <figcaption>Figure 2: Second workflow.</figcaption></figure>
    <figure><object type="image/svg+xml" data="title-adopted.svg"
      title="Architecture adopted from [23]"></object>
      <figcaption>Figure 3: Third workflow.</figcaption></figure>
    <figure><object type="image/svg+xml" data="aria-adopted.svg"
      aria-label="Architecture adopted from [24]"></object>
      <figcaption>Figure 4: Fourth workflow.</figcaption></figure>
    <figure><object type="image/svg+xml" data="safe.svg"
      title="Independent validation workflow"></object>
      <figcaption>Figure 5: Independent validation workflow.</figcaption></figure>
    """

    candidates = ev.select_arxiv_figures(
        html, "https://arxiv.org/html/2608.12345v2",
    )

    assert [candidate["image_url"] for candidate in candidates] == [
        "https://arxiv.org/html/2608.12345v2/safe.svg",
    ]


def test_arxiv_object_rights_label_does_not_change_v7_raster_selection():
    html = """
    <figure><img src="existing.png" alt="Validation field" />
      <object type="image/svg+xml" data="risky.svg"
        title="Copyright: Example Publisher"></object>
      <figcaption>Figure 1: Mixed-format validation result.</figcaption>
    </figure>
    """

    candidates = ev.select_arxiv_figures(
        html, "https://arxiv.org/html/2608.12345v2",
    )

    assert [candidate["image_url"] for candidate in candidates] == [
        "https://arxiv.org/html/existing.png",
    ]


def test_auxiliary_asset_filter_covers_colorbars_and_keys_without_overreach():
    assert ev.looks_like_auxiliary_image("figures/color_bar.png")
    assert ev.looks_like_auxiliary_image("figures/colourbar-vertical.webp")
    assert ev.looks_like_auxiliary_image("figures/key.png")
    assert ev.looks_like_auxiliary_image("figures/plot_onlycbar.png")
    assert ev.looks_like_auxiliary_image(
        "legal-mentions/EU_POS.jpg",
    )
    assert ev.looks_like_auxiliary_image("figures/asset-17.png", "Plot legend")
    assert not ev.looks_like_auxiliary_image(
        "figures/key-experimental-result.png", "Key experimental result",
    )


def test_arxiv_selector_prefers_complete_image_over_nested_subfigures():
    html = """
    <figure class="ltx_figure">
      <figure class="ltx_figure ltx_figure_panel">
        <img src="figures/panel-a.png" width="500" height="400" />
      </figure>
      <figure class="ltx_figure ltx_figure_panel">
        <img src="figures/panel-b.png" width="500" height="400" />
      </figure>
      <img src="figures/complete-figure.png" width="900" height="600"
           alt="Complete comparison" />
      <figcaption>Comparison across both experimental conditions.</figcaption>
    </figure>
    """
    selected = ev.select_arxiv_figure(
        html, "https://arxiv.org/html/2608.12345",
    )
    assert selected is not None
    assert selected["image_url"].endswith("/figures/complete-figure.png")

    ordinary = ev.select_arxiv_figure(
        '<figure class="ltx_figure_panel"><img src="single.png" />'
        '<figcaption>Ordinary single image.</figcaption></figure>',
        "https://arxiv.org/html/2608.12345",
    )
    assert ordinary is not None
    assert ordinary["image_url"].endswith("/html/single.png")


def test_arxiv_selector_keeps_first_panel_when_no_complete_image_exists():
    html = """
    <figure class="ltx_figure">
      <figure class="ltx_figure_panel">
        <img src="panel-a.png" width="200" height="100" />
      </figure>
      <figure class="ltx_figure_panel">
        <img src="panel-b.png" width="1200" height="900" />
      </figure>
      <figcaption>Two views of the same result.</figcaption>
    </figure>
    """
    selected = ev.select_arxiv_figure(
        html, "https://arxiv.org/html/2608.12345",
    )
    assert selected is not None
    assert selected["image_url"].endswith("/html/panel-a.png")


def test_arxiv_portrait_layout_class_does_not_mean_author_portrait():
    selected = ev.select_arxiv_figure(
        '<figure class="ltx_figure"><img src="architecture.png" '
        'class="ltx_graphics ltx_img_portrait" alt="Model architecture" />'
        '<figcaption>Figure 1: Surrogate architecture.</figcaption></figure>',
        "https://arxiv.org/html/2608.12345",
    )
    assert selected is not None
    assert selected["image_url"].endswith("/html/architecture.png")


def test_arxiv_selector_skips_geometric_colorbar_from_real_2011_structure():
    # Mirrors arXiv:2011.15110v2 Figure 10.  x1.png is rendered as 49x199
    # (the actual file is 97x398) beside the full 405x348 SVG eigenvector
    # panels.  Since SVG is intentionally outside the public raster contract,
    # selector v4 must skip this outer figure and continue to the next raster.
    html = """
    <figure id="S4.F10" class="ltx_figure ltx_figure_panel">
      <div class="ltx_flex_figure">
        <div class="ltx_flex_cell">
          <div class="ltx_figure_panel">
            <img src="2011.15110v2/x1.png" width="49" height="199"
                 class="ltx_graphics ltx_img_portrait"
                 alt="Refer to caption" />
          </div>
        </div>
      </div>
      <figcaption>Figure 10: AS and KLE eigenvectors.</figcaption>
      <div class="ltx_flex_figure">
        <figure class="ltx_figure_panel">
          <object type="image/svg+xml"
                  data="2011.15110v2/frame0_no_colorbar.svg"
                  width="405" height="348"></object>
        </figure>
        <figure class="ltx_figure_panel">
          <object type="image/svg+xml"
                  data="2011.15110v2/frame7_no_colorbar.svg"
                  width="405" height="348"></object>
        </figure>
      </div>
    </figure>
    <figure id="S5.F16" class="ltx_figure">
      <img src="2011.15110v2/figures/f_blob.png"
           width="333" height="254" alt="Refer to caption" />
      <figcaption>Figure 16: Truncated Gaussian blob forcing term.</figcaption>
    </figure>
    """

    selected = ev.select_arxiv_figure(
        html, "https://arxiv.org/html/2011.15110",
    )

    assert selected is not None
    assert selected["image_url"].endswith("/figures/f_blob.png")
    assert not selected["image_url"].endswith("/x1.png")


def test_geometric_filter_keeps_only_narrow_scientific_image():
    fixtures = (
        ("vertical-field.png", "49", "199"),
        ("horizontal-profile.png", "199", "49"),
    )
    for filename, width, height in fixtures:
        html = (
            '<figure class="ltx_figure">'
            f'<img src="figures/{filename}" width="{width}" '
            f'height="{height}" alt="Scientific field" />'
            '<figcaption>Validated scientific result.</figcaption></figure>'
        )
        selected = ev.select_arxiv_figure(
            html, "https://arxiv.org/html/2608.12345",
        )
        assert selected is not None
        assert selected["image_url"].endswith(f"/figures/{filename}")


def test_geometric_filter_ignores_invalid_img_companions():
    invalid_companions = (
        '<img src="" width="900" height="600" />',
        '<img src="figures/vector.svg" width="900" height="600" />',
    )
    for companion in invalid_companions:
        html = (
            '<figure class="ltx_figure">'
            '<img src="figures/vertical-field.png" width="49" '
            'height="199" alt="Scientific field" />'
            f'{companion}'
            '<figcaption>Validated scientific result.</figcaption></figure>'
        )
        selected = ev.select_arxiv_figure(
            html, "https://arxiv.org/html/2608.12345",
        )
        assert selected is not None
        assert selected["image_url"].endswith(
            "/figures/vertical-field.png"
        )


def test_arxiv_parser_tracks_graphic_order_around_objects_and_invalid_images():
    parser = ev.ArxivFigureParser()
    parser.feed("""
    <figure class="ltx_figure">
      <object type="image/svg+xml" data="figures/before.svg"
              width="400" height="300"></object>
      <img src="" width="900" height="600" />
      <img src="figures/first.png" width="49" height="199" />
      <object type="image/svg+xml" data="figures/between.svg"
              width="500" height="350"></object>
      <img src="figures/not-raster.svg" width="800" height="600" />
      <img src="figures/second.webp" width="640" height="480" />
    </figure>
    """)

    figure = parser.figures[0]
    assert [
        (graphic["kind"], graphic["src"])
        for graphic in figure["graphics"]
    ] == [
        ("object", "figures/before.svg"),
        ("img", "figures/first.png"),
        ("object", "figures/between.svg"),
        ("img", "figures/second.webp"),
    ]
    assert [
        (image["src"], image["graphic_order"])
        for image in figure["images"]
    ] == [
        ("", None),
        ("figures/first.png", 1),
        ("figures/not-raster.svg", None),
        ("figures/second.webp", 3),
    ]


def test_geometric_filter_keeps_large_narrow_scientific_panel_with_companion():
    # A narrow layout can be scientific even beside another panel.  The
    # absolute small-size gates ensure it is not removed on ratio alone.
    html = """
    <figure class="ltx_figure">
      <figure class="ltx_figure_panel">
        <img src="figures/vertical-section.png" width="120" height="720"
             alt="Depth-resolved field" />
      </figure>
      <figure class="ltx_figure_panel">
        <img src="figures/context.png" width="900" height="600" />
      </figure>
      <figcaption>Vertical section and spatial context.</figcaption>
    </figure>
    """
    selected = ev.select_arxiv_figure(
        html, "https://arxiv.org/html/2608.12345",
    )
    assert selected is not None
    assert selected["image_url"].endswith("/figures/vertical-section.png")


def test_available_visual_truncates_caption_and_alt_at_safe_boundaries():
    latex = r"$\frac{\sigma_{equivalent}}{\varepsilon_{reference}}$"
    caption_prefix = "Validated finite-element field. " * 37
    caption = caption_prefix + latex + " after the mathematical expression"
    alt = "Patient-specific stress reconstruction " * 20

    visual = ev._available_visual(
        checked_at=ev.iso_z(NOW),
        image_url="https://arxiv.org/html/2608.12345/figure.png",
        caption=caption, source_label="arXiv",
        source_url="https://arxiv.org/abs/2608.12345",
        license_name="CC BY", alt=alt, provider="arxiv",
    )

    assert len(visual["caption"]) <= 1200
    assert len(visual["alt"]) <= 500
    assert caption.startswith(visual["caption"])
    assert alt.startswith(visual["alt"])
    assert caption[len(visual["caption"])].isspace()
    assert alt[len(visual["alt"])].isspace()
    assert visual["caption"].count("$") % 2 == 0
    assert visual["caption"].count("{") == visual["caption"].count("}")


def test_select_pmc_figure_rejects_all_required_exclusion_phrases():
    phrases = [
        "Reproduced with permission from A",
        "Adapted with permission from B",
        "Copyright 2024 Example",
        "© 2024 Example",
        "All rights reserved",
        "Not included in the Creative Commons licence",
    ]
    for index, phrase in enumerate(phrases):
        xml = f"""
        <article xmlns:xlink="http://www.w3.org/1999/xlink">
          <fig><caption><p>{phrase}</p></caption>
          <graphic xlink:href="gr{index}.jpg" /></fig>
        </article>
        """
        assert ev.select_pmc_figure(
            xml, [f"s3://pmc-oa-opendata/PMC123.1/gr{index}.jpg"]
        ) is None

    outside_caption = """
    <article xmlns:xlink="http://www.w3.org/1999/xlink">
      <fig><caption><p>Otherwise neutral caption.</p></caption>
        <attrib>Reproduced with permission from Example Publisher.</attrib>
        <graphic xlink:href="gr9.jpg" /></fig>
    </article>
    """
    assert ev.select_pmc_figure(
        outside_caption, ["s3://pmc-oa-opendata/PMC123.1/gr9.jpg"]
    ) is None


class SizedImageClient:
    def __init__(self, outcomes):
        self.outcomes = outcomes
        self.calls = []

    def verify_image(self, url, *, allowed_hosts):
        self.calls.append((url, allowed_hosts))
        outcome = self.outcomes[url]
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


@pytest.mark.parametrize("dimensions", [(64, 64), (16, 256), (49, 199)])
def test_verified_candidate_keeps_conservative_boundary_and_narrow_images(
        dimensions):
    url = "https://arxiv.org/html/figure.png"
    client = SizedImageClient({url: dimensions})
    verified = ev.VisualResolver(client)._verified_card_candidate(
        [{"image_url": url}], allowed_hosts={"arxiv.org"},
    )
    assert verified == ({"image_url": url}, *dimensions)


def test_verified_candidate_deduplicates_and_checks_at_most_six_images():
    urls = [f"https://arxiv.org/html/figure-{index}.png" for index in range(8)]
    candidates = [{"image_url": urls[0]}, {"image_url": urls[0]}]
    candidates.extend({"image_url": url} for url in urls[1:])
    client = SizedImageClient({url: (28, 28) for url in urls})

    assert ev.VisualResolver(client)._verified_card_candidate(
        candidates, allowed_hosts={"arxiv.org"},
    ) is None
    assert [call[0] for call in client.calls] == urls[:6]


def test_verified_candidate_does_not_hide_transient_fetch_error():
    first = "https://arxiv.org/html/first.png"
    second = "https://arxiv.org/html/second.png"
    client = SizedImageClient({
        first: ev.FetchError("temporary timeout"), second: (800, 600),
    })

    with pytest.raises(ev.FetchError, match="temporary timeout"):
        ev.VisualResolver(client)._verified_card_candidate(
            [{"image_url": first}, {"image_url": second}],
            allowed_hosts={"arxiv.org"},
        )
    assert [call[0] for call in client.calls] == [first]


class FakePmcClient:
    def __init__(self):
        self.calls = []

    def get_json(self, url, *, params=None, allowed_hosts):
        self.calls.append(("json", url, params, allowed_hosts))
        if url == ev.ID_CONVERTER_URL:
            return {"records": [{"pmcid": "PMC123", "pmid": 123}]}
        assert url == f"{ev.PMC_BUCKET_URL}metadata/PMC123.2.json"
        return {
            "license_code": "CC BY 4.0",
            "xml_url": "s3://pmc-oa-opendata/PMC123.2/PMC123.2.xml?md5=x",
            "media_urls": [
                "s3://pmc-oa-opendata/PMC123.2/gr1.jpg?md5=y",
                "s3://pmc-oa-opendata/PMC123.2/gr2.jpg?md5=z",
            ],
        }

    def get_text(self, url, *, params=None, allowed_hosts):
        self.calls.append(("text", url, params, allowed_hosts))
        if url == ev.PMC_BUCKET_URL:
            return """
            <ListBucketResult xmlns="http://s3.amazonaws.com/doc/2006-03-01/">
              <CommonPrefixes><Prefix>PMC123.1/</Prefix></CommonPrefixes>
              <CommonPrefixes><Prefix>PMC123.2/</Prefix></CommonPrefixes>
            </ListBucketResult>
            """
        assert url.endswith("/PMC123.2/PMC123.2.xml")
        return """
        <article xmlns:xlink="http://www.w3.org/1999/xlink"><body>
          <fig><label>Fig. 1</label>
            <caption><p>© Elsevier; used with permission.</p></caption>
            <graphic xlink:href="gr1.jpg" /></fig>
          <fig><label>Fig. 2</label>
            <caption><p>Patient-specific geometry and stress field.</p></caption>
            <graphic xlink:href="gr2.jpg" /></fig>
        </body></article>
        """

    def verify_image(self, url, *, allowed_hosts):
        self.calls.append(("image", url, None, allowed_hosts))
        assert url.endswith("/PMC123.2/gr2.jpg")
        assert allowed_hosts == {ev.PMC_BUCKET_HOST}
        return 900, 600


def test_pmc_resolver_uses_new_s3_metadata_and_latest_version():
    client = FakePmcClient()
    resolver = ev.VisualResolver(client, email="maintainer@example.org")
    visual = resolver.resolve_pmc(
        {"pmid": "123", "title": "Paper"}, ev.iso_z(NOW)
    )
    assert visual["status"] == "available"
    assert visual["license"] == "CC BY"
    assert visual["image_url"].endswith("/PMC123.2/gr2.jpg")
    assert visual["source_url"] == "https://pmc.ncbi.nlm.nih.gov/articles/PMC123/"
    assert visual["source_label"] == "PubMed Central · Fig. 2"
    assert (visual["width"], visual["height"]) == (900, 600)
    assert "permission" not in visual["caption"].lower()
    converter = client.calls[0]
    assert converter[2]["tool"] == "research-radar-visuals"
    assert converter[2]["email"] == "maintainer@example.org"
    assert all("deprecated" not in call[1] for call in client.calls)


class TinyThenValidPmcClient(FakePmcClient):
    def get_text(self, url, *, params=None, allowed_hosts):
        if url == ev.PMC_BUCKET_URL:
            return super().get_text(
                url, params=params, allowed_hosts=allowed_hosts,
            )
        self.calls.append(("text", url, params, allowed_hosts))
        return """
        <article xmlns:xlink="http://www.w3.org/1999/xlink"><body>
          <fig><label>Fig. 1</label><caption><p>Small sample tile.</p></caption>
            <graphic xlink:href="gr1.jpg" /></fig>
          <fig><label>Fig. 2</label><caption><p>Complete result field.</p></caption>
            <graphic xlink:href="gr2.jpg" /></fig>
        </body></article>
        """

    def verify_image(self, url, *, allowed_hosts):
        self.calls.append(("image", url, None, allowed_hosts))
        if url.endswith("/gr1.jpg"):
            return 28, 28
        assert url.endswith("/gr2.jpg")
        return 640, 480


def test_pmc_resolver_tries_next_figure_after_tiny_asset():
    client = TinyThenValidPmcClient()
    visual = ev.VisualResolver(client).resolve_pmc(
        {"pmid": "123", "title": "Paper"}, ev.iso_z(NOW),
    )

    assert visual["status"] == "available"
    assert visual["image_url"].endswith("/gr2.jpg")
    assert (visual["width"], visual["height"]) == (640, 480)
    assert [call[1] for call in client.calls if call[0] == "image"] == [
        "https://pmc-oa-opendata.s3.amazonaws.com/PMC123.2/gr1.jpg",
        "https://pmc-oa-opendata.s3.amazonaws.com/PMC123.2/gr2.jpg",
    ]


class BlockedPmcClient(FakePmcClient):
    def get_json(self, url, *, params=None, allowed_hosts):
        if url == ev.ID_CONVERTER_URL:
            return {"records": [{"pmcid": "PMC123"}]}
        return {
            "license_code": "CC BY-NC-ND 4.0",
            "xml_url": "s3://pmc-oa-opendata/PMC123.2/article.xml",
            "media_urls": ["s3://pmc-oa-opendata/PMC123.2/gr1.jpg"],
        }


def test_pmc_resolver_blocks_non_allowlisted_article_license():
    visual = ev.VisualResolver(BlockedPmcClient()).resolve_pmc(
        {"doi": "10.1/example"}, ev.iso_z(NOW)
    )
    assert visual["status"] == "blocked"
    assert visual["reason"] == "pmc_license_not_reusable"
    assert visual["image_url"] == ""
    assert visual["license"] == "CC BY-NC-ND"


class FakeArxivClient:
    def __init__(self, license_url="https://creativecommons.org/licenses/by/4.0/"):
        self.license_url = license_url
        self.calls = []

    def get_text(self, url, *, params=None, allowed_hosts):
        self.calls.append((url, params, allowed_hosts))
        if url == ev.ARXIV_OAI_URL:
            return (
                '<OAI-PMH><record><metadata><arXivRaw>'
                f'<license>{self.license_url}</license>'
                '</arXivRaw></metadata></record></OAI-PMH>'
            )
        return """
        <html><body>
          <figure><img src="x1.png" />
            <figcaption>Reproduced with permission from Publisher.</figcaption>
          </figure>
          <figure class="ltx_figure"><img src="figures/x2.png" alt="Workflow" />
            <figcaption>Overview of the proposed workflow.</figcaption>
          </figure>
        </body></html>
        """

    def verify_image(self, url, *, allowed_hosts):
        self.calls.append(("image", url, allowed_hosts))
        assert allowed_hosts == {"arxiv.org"}
        return 1024, 768


def test_arxiv_resolver_requires_oai_license_and_skips_excluded_figure():
    client = FakeArxivClient()
    visual = ev.VisualResolver(client).resolve_arxiv(
        {"arxiv_id": "2605.12345v2", "title": "Paper"}, ev.iso_z(NOW)
    )
    assert visual["status"] == "available"
    assert visual["license"] == "CC BY"
    assert visual["image_url"] == (
        "https://arxiv.org/html/figures/x2.png"
    )
    assert visual["source_url"] == "https://arxiv.org/abs/2605.12345"
    assert (visual["width"], visual["height"]) == (1024, 768)
    assert client.calls[0][0] == "https://oaipmh.arxiv.org/oai"
    assert client.calls[0][1]["metadataPrefix"] == "arXivRaw"
    assert client.calls[0][2] == {
        "oaipmh.arxiv.org", "export.arxiv.org",
    }


class CandidateArxivClient(FakeArxivClient):
    def __init__(self, html, dimensions):
        super().__init__()
        self.html = html
        self.dimensions = dimensions
        self.image_calls = []

    def get_text(self, url, *, params=None, allowed_hosts):
        if url == ev.ARXIV_OAI_URL:
            return super().get_text(
                url, params=params, allowed_hosts=allowed_hosts,
            )
        self.calls.append((url, params, allowed_hosts))
        return self.html

    def verify_image(self, url, *, allowed_hosts):
        self.image_calls.append(url)
        outcome = self.dimensions[pathlib.PurePosixPath(url).name]
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


class SvgCandidateArxivClient(CandidateArxivClient):
    def __init__(self, html, dimensions, svg_dimensions):
        super().__init__(html, dimensions)
        self.svg_dimensions = svg_dimensions
        self.svg_calls = []

    def verify_svg(self, url, *, allowed_hosts):
        self.svg_calls.append(url)
        assert allowed_hosts == {"arxiv.org"}
        outcome = self.svg_dimensions[pathlib.PurePosixPath(url).name]
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


TARGET_TINY_ARXIV_HTML = """
<html><body>
  <figure class="ltx_figure">
    <figure class="ltx_figure_panel">
      <img src="figures/mnist_salt_and_peppered-000.png" />
      <img src="figures/mnist_salt_and_peppered-001.png" />
    </figure>
    <figcaption>Samples of original and corrupted MNIST images.</figcaption>
  </figure>
  <figure><img src="ensemble_cifar_dense_ras1.png" />
    <figcaption>Ensemble uncertainty experiments.</figcaption></figure>
  <figure><img src="al_cifar_balanced_aquisition_ras1.png" />
    <figcaption>Balanced acquisition experiments.</figcaption></figure>
  <figure><img src="ensemble_cifar_dense_alpha_0.09_ras1.png" />
    <figcaption>Dense ensemble experiments.</figcaption></figure>
</body></html>
"""


def test_arxiv_target_all_tiny_outer_figures_becomes_not_found():
    dimensions = {
        "mnist_salt_and_peppered-000.png": (28, 28),
        "ensemble_cifar_dense_ras1.png": (1, 300),
        "al_cifar_balanced_aquisition_ras1.png": (1, 300),
        "ensemble_cifar_dense_alpha_0.09_ras1.png": (1, 300),
    }
    client = CandidateArxivClient(TARGET_TINY_ARXIV_HTML, dimensions)

    candidates = ev.select_arxiv_figures(
        TARGET_TINY_ARXIV_HTML, "https://arxiv.org/html/2211.14605",
    )
    assert len(candidates) == 4
    assert candidates[0]["image_url"].endswith(
        "/figures/mnist_salt_and_peppered-000.png"
    )
    visual = ev.VisualResolver(client).resolve_arxiv(
        {"arxiv_id": "2211.14605v2"}, ev.iso_z(NOW),
    )

    assert visual["status"] == "not_found"
    assert visual["reason"] == "arxiv_no_card_sized_figure"
    assert [pathlib.PurePosixPath(url).name for url in client.image_calls] == [
        "mnist_salt_and_peppered-000.png",
        "ensemble_cifar_dense_ras1.png",
        "al_cifar_balanced_aquisition_ras1.png",
        "ensemble_cifar_dense_alpha_0.09_ras1.png",
    ]
    assert not any("-001.png" in url for url in client.image_calls)


def test_arxiv_resolver_skips_tiny_then_persists_next_image_dimensions():
    html = """
    <figure><img src="tiny.png" />
      <figcaption>A small example tile.</figcaption></figure>
    <figure><img src="complete.png" />
      <figcaption>The complete computed field.</figcaption></figure>
    """
    client = CandidateArxivClient(
        html, {"tiny.png": (28, 28), "complete.png": (800, 600)},
    )
    visual = ev.VisualResolver(client).resolve_arxiv(
        {"arxiv_id": "2608.12345v1"}, ev.iso_z(NOW),
    )

    assert visual["status"] == "available"
    assert visual["image_url"].endswith("/complete.png")
    assert (visual["width"], visual["height"]) == (800, 600)
    assert len(client.image_calls) == 2


def test_arxiv_resolver_uses_svg_fallback_and_persists_media_type():
    html = """
    <figure><img src="tiny.png" />
      <figcaption>Figure 1: Small raster tile.</figcaption></figure>
    <figure><object type="image/svg+xml" data="2608.12345v1/result.svg"
              width="640" height="480"></object>
      <figcaption>Figure 2: Complete vector result.</figcaption></figure>
    """
    client = SvgCandidateArxivClient(
        html, {"tiny.png": (28, 28)}, {"result.svg": (800, 600)},
    )

    visual = ev.VisualResolver(client).resolve_arxiv(
        {"arxiv_id": "2608.12345v1"}, ev.iso_z(NOW),
    )

    assert visual["status"] == "available"
    assert visual["image_url"].endswith("/result.svg")
    assert visual["media_type"] == "image/svg+xml"
    assert (visual["width"], visual["height"]) == (800, 600)
    assert len(client.image_calls) == 1
    assert len(client.svg_calls) == 1


def test_arxiv_resolver_pins_relative_svg_to_requested_version():
    html = """
    <figure><object type="image/svg+xml" data="result.svg"
              width="640" height="480"></object>
      <figcaption>Figure 1: Complete vector result.</figcaption></figure>
    """
    versioned = SvgCandidateArxivClient(
        html, {}, {"result.svg": (640, 480)},
    )
    visual = ev.VisualResolver(versioned).resolve_arxiv(
        {"arxiv_id": "2608.12345v2"}, ev.iso_z(NOW),
    )
    assert visual["image_url"] == (
        "https://arxiv.org/html/2608.12345v2/result.svg"
    )

    unversioned = SvgCandidateArxivClient(
        html, {}, {"result.svg": (640, 480)},
    )
    visual = ev.VisualResolver(unversioned).resolve_arxiv(
        {"arxiv_id": "2608.12345"}, ev.iso_z(NOW),
    )
    assert visual["status"] == "not_found"
    assert visual["reason"] == "arxiv_html_no_reusable_figure"
    assert unversioned.svg_calls == []


def test_svg_policy_rejection_tries_next_candidate_within_six_budget():
    candidates = [
        {"image_url": "https://arxiv.org/html/2608.12345v1/unsafe.svg",
         "media_type": ev.SVG_MEDIA_TYPE},
        {"image_url": "https://arxiv.org/html/2608.12345v1/safe.svg",
         "media_type": ev.SVG_MEDIA_TYPE},
    ]
    client = SvgCandidateArxivClient("", {}, {
        "unsafe.svg": ev.SvgValidationError("active content"),
        "safe.svg": (640, 480),
    })

    verified = ev.VisualResolver(client)._verified_card_candidate(
        candidates, allowed_hosts={"arxiv.org"},
    )

    assert verified == (candidates[1], 640, 480)
    assert [pathlib.PurePosixPath(url).name for url in client.svg_calls] == [
        "unsafe.svg", "safe.svg",
    ]


def test_svg_network_error_remains_transient_and_stops_fallback():
    first = {
        "image_url": "https://arxiv.org/html/2608.12345v1/first.svg",
        "media_type": ev.SVG_MEDIA_TYPE,
    }
    second = {
        "image_url": "https://arxiv.org/html/2608.12345v1/second.svg",
        "media_type": ev.SVG_MEDIA_TYPE,
    }
    client = SvgCandidateArxivClient("", {}, {
        "first.svg": ev.FetchError("temporary SVG timeout"),
        "second.svg": (640, 480),
    })

    with pytest.raises(ev.FetchError, match="temporary SVG timeout"):
        ev.VisualResolver(client)._verified_card_candidate(
            [first, second], allowed_hosts={"arxiv.org"},
        )
    assert len(client.svg_calls) == 1


def test_arxiv_image_fetch_error_remains_error_not_not_found():
    html = """
    <figure><img src="first.png" />
      <figcaption>The complete computed field.</figcaption></figure>
    <figure><img src="second.png" />
      <figcaption>An alternative field.</figcaption></figure>
    """
    client = CandidateArxivClient(html, {
        "first.png": ev.FetchError("image timeout"),
        "second.png": (800, 600),
    })

    visual = ev.VisualResolver(client).resolve(
        {"arxiv_id": "2608.12345"}, now=NOW,
    )
    assert visual["status"] == "error"
    assert "image timeout" in visual["reason"]
    assert len(client.image_calls) == 1


def test_arxiv_resolver_does_not_fetch_html_for_default_license():
    client = FakeArxivClient("http://arxiv.org/licenses/nonexclusive-distrib/1.0/")
    visual = ev.VisualResolver(client).resolve_arxiv(
        {"arxiv_id": "2605.12345v1"}, ev.iso_z(NOW)
    )
    assert visual["status"] == "blocked"
    assert visual["image_url"] == ""
    assert len(client.calls) == 1


class IsolatedResolver(ev.VisualResolver):
    def __init__(self, pmc_result, arxiv_result):
        self.pmc_result = pmc_result
        self.arxiv_result = arxiv_result

    def resolve_pmc(self, paper, checked_at):
        if isinstance(self.pmc_result, Exception):
            raise self.pmc_result
        return self.pmc_result

    def resolve_arxiv(self, paper, checked_at):
        if isinstance(self.arxiv_result, Exception):
            raise self.arxiv_result
        return self.arxiv_result


def test_provider_failure_does_not_block_available_fallback():
    arxiv = ev._available_visual(
        checked_at=ev.iso_z(NOW), image_url="https://arxiv.org/html/1/fig.png",
        caption="Safe", source_label="arXiv",
        source_url="https://arxiv.org/abs/1", license_name="CC BY",
        alt="Safe", provider="arxiv",
    )
    result = IsolatedResolver(ev.FetchError("PMC timeout"), arxiv).resolve(
        {"doi": "10.1/a", "arxiv_id": "1"}, now=NOW
    )
    assert result["status"] == "available"
    assert result["provider"] == "arxiv"


def test_secondary_provider_failure_does_not_override_pmc_negative_result():
    pmc = ev._blank_visual(
        "not_found", checked_at=ev.iso_z(NOW),
        reason="pmc_no_reusable_figure", provider="pmc",
    )
    result = IsolatedResolver(pmc, ev.FetchError("arXiv timeout")).resolve(
        {"doi": "10.1/a", "arxiv_id": "1"}, now=NOW
    )
    assert result["status"] == "not_found"
    assert result["provider"] == "pmc"


def test_registry_cache_ttls():
    recent = ev.iso_z(NOW - dt.timedelta(days=10))
    old = ev.iso_z(NOW - dt.timedelta(days=31))
    assert not ev.should_refresh(
        {"status": "not_found", "checked_at": recent}, now=NOW
    )
    assert ev.should_refresh(
        {"status": "not_found", "checked_at": old}, now=NOW
    )
    assert not ev.should_refresh(
        {"status": "error", "checked_at": ev.iso_z(NOW - dt.timedelta(hours=4))},
        now=NOW,
    )
    assert ev.should_refresh(
        {"status": "available", "checked_at": recent}, now=NOW, force=True
    )
    assert ev.should_refresh(
        {"status": "available", "checked_at": recent}, now=NOW,
    )
    assert not ev.should_refresh({
        "status": "available", "checked_at": recent,
        "selector_version": ev.SELECTOR_VERSION,
    }, now=NOW)
    assert not ev.should_refresh({
        "status": "available", "checked_at": recent,
        "selector_version": ev.MIN_CURRENT_AVAILABLE_SELECTOR_VERSION,
    }, now=NOW)
    assert ev.should_refresh({
        "status": "available", "checked_at": recent,
        "selector_version": ev.MIN_CURRENT_AVAILABLE_SELECTOR_VERSION - 1,
    }, now=NOW)
    stale_with_recent_error = {
        "status": "available", "checked_at": recent,
        "selector_version": ev.MIN_CURRENT_AVAILABLE_SELECTOR_VERSION - 1,
        "selector_error_at": ev.iso_z(NOW - dt.timedelta(hours=4)),
    }
    assert not ev.should_refresh(stale_with_recent_error, now=NOW)
    assert ev.should_refresh(
        stale_with_recent_error, now=NOW + dt.timedelta(days=1, seconds=1),
    )


@pytest.mark.parametrize("reason", [
    "arxiv_html_no_reusable_figure",
    "arxiv_no_card_sized_figure",
])
def test_selector_v8_retries_old_arxiv_negative_once(reason):
    old_selector = {
        "status": "not_found",
        "reason": reason,
        "checked_at": ev.iso_z(NOW - dt.timedelta(hours=1)),
        "selector_version": ev.SELECTOR_VERSION - 1,
    }
    assert ev.should_refresh(old_selector, now=NOW)

    refreshed = ev._blank_visual(
        "not_found", checked_at=ev.iso_z(NOW), reason=reason,
        provider="arxiv",
    )
    assert refreshed["selector_version"] == ev.SELECTOR_VERSION
    assert not ev.should_refresh(
        refreshed, now=NOW + dt.timedelta(seconds=1),
    )


def test_blank_visuals_persist_current_selector_version():
    assert ev._blank_visual(
        "error", checked_at=ev.iso_z(NOW), reason="timeout",
    )["selector_version"] == ev.SELECTOR_VERSION


def test_candidates_are_recent_first_then_priority(tmp_path):
    daily = tmp_path / "daily"
    daily.mkdir()
    (daily / "2025-01-01.json").write_text(json.dumps({
        "papers": [{
            "doi": "10.1/old-high",
            "first_seen_at": "2025-01-01T01:00:00Z",
            "llm": {"priority": "High"},
        }]
    }), encoding="utf-8")
    (daily / "2026-08-12.json").write_text(json.dumps({
        "papers": [
            {"doi": "10.1/new-medium",
             "first_seen_at": "2026-08-12T01:00:00Z",
             "llm": {"priority": "Medium"}},
            {"doi": "10.1/new-high",
             "first_seen_at": "2026-08-12T01:00:00Z",
             "llm": {"priority": "High"}},
        ]
    }), encoding="utf-8")
    keys = [row[0] for row in ev.iter_candidates(daily, {"High", "Medium"})]
    assert keys == [
        "doi:10.1/new-high", "doi:10.1/new-medium", "doi:10.1/old-high"
    ]


def test_candidates_use_canonical_winner_priority_not_stale_duplicate(tmp_path):
    daily = tmp_path / "daily"
    daily.mkdir()
    (daily / "2026-01-01.json").write_text(json.dumps({
        "papers": [
            {"doi": "10.1/demoted", "first_seen_at": "2026-01-01T00:00:00Z",
             "llm": {"priority": "Low"}},
            {"doi": "10.1/kept", "first_seen_at": "2026-01-01T00:00:00Z",
             "llm": {"priority": "High"}},
        ],
    }), encoding="utf-8")
    (daily / "2026-08-12.json").write_text(json.dumps({
        "papers": [
            {"doi": "10.1/demoted", "first_seen_at": "2026-08-12T00:00:00Z",
             "llm": {"priority": "High"}},
            {"doi": "10.1/kept", "first_seen_at": "2026-08-12T00:00:00Z",
             "llm": {"priority": "Exclude"}},
        ],
    }), encoding="utf-8")

    rows = ev.iter_candidates(daily, {"High", "Medium"})

    assert [row[0] for row in rows] == ["doi:10.1/kept"]
    assert rows[0][2] == "2026-01-01"


def test_candidate_identity_filter_is_exact_and_repeatable(tmp_path):
    daily = tmp_path / "daily"
    daily.mkdir()
    (daily / "2026-08-12.json").write_text(json.dumps({
        "papers": [
            {"doi": "10.1/keep", "llm": {"priority": "High"}},
            {"doi": "10.1/skip", "llm": {"priority": "High"}},
        ]
    }), encoding="utf-8")
    rows = ev.iter_candidates(
        daily, {"High", "Medium"}, {"doi:10.1/keep"},
    )
    assert [row[0] for row in rows] == ["doi:10.1/keep"]


class SometimesFailingResolver:
    def resolve(self, paper, *, now=None):
        if paper["doi"].endswith("first"):
            raise RuntimeError("provider unavailable")
        return ev._available_visual(
            checked_at=ev.iso_z(now),
            image_url="https://arxiv.org/html/1/fig.png",
            caption="Safe figure", source_label="arXiv",
            source_url="https://arxiv.org/abs/1", license_name="CC BY",
            alt="Safe", provider="arxiv",
        )


def test_enrich_is_failure_isolated_and_writes_flat_identity_registry(tmp_path):
    daily = tmp_path / "daily"
    daily.mkdir()
    (daily / "2026-08-12.json").write_text(json.dumps({
        "papers": [
            {"doi": "10.1/first", "llm": {"priority": "High"}},
            {"doi": "10.1/second", "llm": {"priority": "Medium"}},
            {"doi": "10.1/low", "llm": {"priority": "Low"}},
        ]
    }), encoding="utf-8")
    index = tmp_path / "visuals" / "index.json"
    result = ev.enrich(
        daily_dir=daily, index_path=index,
        resolver=SometimesFailingResolver(), limit=10,
        priorities={"High", "Medium"}, now=NOW,
    )
    assert result["attempted"] == 2
    assert result["counts"] == {"error": 1, "available": 1}
    saved = json.loads(index.read_text(encoding="utf-8"))
    assert saved["schema_version"] == "v1"
    assert set(saved["records"]) == {"doi:10.1/first", "doi:10.1/second"}
    assert saved["records"]["doi:10.1/first"]["status"] == "error"
    available = saved["records"]["doi:10.1/second"]
    assert available["status"] == "available"
    assert available["license"] == "CC BY"
    assert not (index.parent / "index.json.tmp").exists()


def test_transient_refresh_error_preserves_last_known_good_visual(tmp_path):
    daily = tmp_path / "daily"
    daily.mkdir()
    (daily / "2026-08-12.json").write_text(json.dumps({
        "papers": [{"doi": "10.1/first", "llm": {"priority": "High"}}],
    }), encoding="utf-8")
    index = tmp_path / "visuals" / "index.json"
    index.parent.mkdir()
    cached = ev._available_visual(
        checked_at=ev.iso_z(NOW - dt.timedelta(days=2)),
        image_url="https://arxiv.org/html/1/good.png",
        caption="Last known good", source_label="arXiv",
        source_url="https://arxiv.org/abs/1", license_name="CC BY",
        alt="Good", provider="arxiv",
    )
    cached["selector_version"] = (
        ev.MIN_CURRENT_AVAILABLE_SELECTOR_VERSION - 1
    )
    index.write_text(json.dumps({
        "schema_version": "v1", "records": {"doi:10.1/first": cached},
    }), encoding="utf-8")

    result = ev.enrich(
        daily_dir=daily, index_path=index,
        resolver=SometimesFailingResolver(), limit=1,
        priorities={"High"}, now=NOW,
    )

    saved = json.loads(index.read_text(encoding="utf-8"))["records"][
        "doi:10.1/first"
    ]
    assert result["counts"] == {"preserved_available": 1}
    assert saved["status"] == "available"
    assert saved["image_url"] == cached["image_url"]
    assert saved["selector_version"] == (
        ev.MIN_CURRENT_AVAILABLE_SELECTOR_VERSION - 1
    )
    assert saved["selector_error_at"] == ev.iso_z(NOW)
    assert "provider unavailable" in saved["selector_error_reason"]
    assert not ev.should_refresh(saved, now=NOW + dt.timedelta(hours=1))
    assert ev.should_refresh(saved, now=NOW + dt.timedelta(days=1, seconds=1))


class PolicyResultResolver:
    def __init__(self, status):
        self.status = status

    def resolve(self, _paper, *, now=None):
        return ev._blank_visual(
            self.status, checked_at=ev.iso_z(now),
            reason="figure_rights_policy", provider="arxiv",
        )


def test_policy_results_replace_stale_available_last_known_good(tmp_path):
    # Last-known-good is a transient network-error fallback, not an override
    # for a newer selector finding that the visual is unsafe or unavailable.
    for status in ("blocked", "not_found"):
        root = tmp_path / status
        daily = root / "daily"
        daily.mkdir(parents=True)
        (daily / "2026-08-12.json").write_text(json.dumps({
            "papers": [{
                "doi": "10.1/policy",
                "llm": {"priority": "High"},
            }],
        }), encoding="utf-8")
        index = root / "visuals" / "index.json"
        index.parent.mkdir()
        cached = ev._available_visual(
            checked_at=ev.iso_z(NOW - dt.timedelta(days=2)),
            image_url="https://arxiv.org/html/1/old-risky.png",
            caption="Old visual", source_label="arXiv",
            source_url="https://arxiv.org/abs/1", license_name="CC BY",
            alt="Old visual", provider="arxiv",
        )
        cached["selector_version"] = (
            ev.MIN_CURRENT_AVAILABLE_SELECTOR_VERSION - 1
        )
        index.write_text(json.dumps({
            "schema_version": "v1",
            "records": {"doi:10.1/policy": cached},
        }), encoding="utf-8")

        result = ev.enrich(
            daily_dir=daily, index_path=index,
            resolver=PolicyResultResolver(status), limit=1,
            priorities={"High"}, now=NOW,
        )

        saved = json.loads(index.read_text(encoding="utf-8"))["records"][
            "doi:10.1/policy"
        ]
        assert result["counts"] == {status: 1}
        assert saved["status"] == status
        assert saved["reason"] == "figure_rights_policy"
        assert saved["checked_at"] == ev.iso_z(NOW)
        assert saved["image_url"] == ""
        assert "selector_error_at" not in saved


class CountingResolver:
    def __init__(self):
        self.calls = []

    def resolve(self, paper, *, now=None):
        self.calls.append(ev.identity_key(paper))
        return ev._available_visual(
            checked_at=ev.iso_z(now),
            image_url="https://arxiv.org/html/2608.12345/figure.png",
            caption="Safe figure", source_label="arXiv",
            source_url="https://arxiv.org/abs/2608.12345",
            license_name="CC BY", alt="Safe", provider="arxiv",
        )


def test_lookup_aliases_deduplicate_requests_without_changing_public_keys(
        tmp_path):
    daily = tmp_path / "daily"
    daily.mkdir()
    papers = [
        {"doi": "10.1234/CaseSensitive", "llm": {"priority": "High"}},
        # Non-target priorities are not requested independently, but a result
        # discovered for the same provider identity is still copied to their
        # exact renderer keys.
        {"doi": "10.1234/casesensitive", "llm": {"priority": "Low"}},
        {"arxiv_id": "2608.12345v1", "llm": {"priority": "Medium"}},
        {"arxiv_id": "2608.12345v3", "llm": {"priority": "Exclude"}},
    ]
    (daily / "2026-08-12.json").write_text(json.dumps({
        "papers": papers,
    }), encoding="utf-8")
    index = tmp_path / "visuals" / "index.json"
    resolver = CountingResolver()

    result = ev.enrich(
        daily_dir=daily, index_path=index, resolver=resolver, limit=10,
        priorities={"High", "Medium"}, now=NOW,
    )

    exact_keys = {ev.identity_key(paper) for paper in papers}
    assert exact_keys == {
        "doi:10.1234/CaseSensitive", "doi:10.1234/casesensitive",
        "arxiv:2608.12345v1", "arxiv:2608.12345v3",
    }
    assert ev.visual_lookup_key(papers[0]) == ev.visual_lookup_key(papers[1])
    assert ev.visual_lookup_key(papers[2]) == ev.visual_lookup_key(papers[3])
    assert result["attempted"] == 2
    assert len(resolver.calls) == 2
    assert result["counts"] == {"available": 2}
    saved = json.loads(index.read_text(encoding="utf-8"))["records"]
    assert set(saved) == exact_keys
    assert all(saved[key]["status"] == "available" for key in exact_keys)


def test_fresh_registry_alias_is_reused_and_copied_to_current_exact_key(tmp_path):
    daily = tmp_path / "daily"
    daily.mkdir()
    (daily / "2026-08-12.json").write_text(json.dumps({
        "papers": [{
            "doi": "10.1234/lowercase",
            "llm": {"priority": "High"},
        }],
    }), encoding="utf-8")
    index = tmp_path / "visuals" / "index.json"
    cached = ev._available_visual(
        checked_at=ev.iso_z(NOW - dt.timedelta(days=1)),
        image_url="https://arxiv.org/html/2608.12345/figure.png",
        caption="Cached figure", source_label="arXiv",
        source_url="https://arxiv.org/abs/2608.12345",
        license_name="CC BY", alt="Cached", provider="arxiv",
    )
    index.parent.mkdir()
    index.write_text(json.dumps({
        "schema_version": "v1",
        "records": {"doi:10.1234/LOWERCASE": cached},
    }), encoding="utf-8")
    resolver = CountingResolver()

    result = ev.enrich(
        daily_dir=daily, index_path=index, resolver=resolver, limit=10,
        priorities={"High", "Medium"}, now=NOW,
    )

    assert result["attempted"] == 0
    assert resolver.calls == []
    saved = json.loads(index.read_text(encoding="utf-8"))["records"]
    assert saved["doi:10.1234/lowercase"] == cached
    assert saved["doi:10.1234/LOWERCASE"] == cached


class MetadataCapturingResolver:
    def __init__(self):
        self.papers = []

    def resolve(self, paper, *, now=None):
        self.papers.append(paper)
        return ev._available_visual(
            checked_at=ev.iso_z(now),
            image_url="https://arxiv.org/html/2608.12345/figure.png",
            caption="Safe aliased figure", source_label="arXiv",
            source_url="https://arxiv.org/abs/2608.12345",
            license_name="CC BY", alt="Safe aliased figure",
            provider="arxiv",
        )


def _write_fresh_negative(index, *, status="not_found",
                          reason="no_supported_public_figure_source"):
    index.parent.mkdir()
    cached = ev._blank_visual(
        status, checked_at=ev.iso_z(NOW - dt.timedelta(hours=1)),
        reason=reason,
    )
    index.write_text(json.dumps({
        "schema_version": "v1",
        "records": {"doi:10.1234/samework": cached},
    }), encoding="utf-8")
    return cached


def test_doi_alias_metadata_enriches_resolver_without_changing_public_identity(
        tmp_path):
    daily = tmp_path / "daily"
    daily.mkdir()
    papers = [
        {
            "doi": "10.1234/samework",
            "title": "Canonical title",
            "source": "openalex",
            "llm": {"priority": "High"},
        },
        {
            "doi": "10.1234/SameWork",
            "arxiv_id": "2608.12345v2",
            "title": "Metadata donor title",
            "source": "arxiv",
            "llm": {"priority": "Medium"},
        },
    ]
    bucket = daily / "2026-08-12.json"
    bucket.write_text(json.dumps({"papers": papers}), encoding="utf-8")
    original_daily = bucket.read_bytes()
    index = tmp_path / "visuals" / "index.json"
    _write_fresh_negative(index)
    resolver = MetadataCapturingResolver()

    result = ev.enrich(
        daily_dir=daily, index_path=index, resolver=resolver, limit=10,
        priorities={"High"}, now=NOW,
    )

    assert result["attempted"] == 1
    assert result["counts"] == {"available": 1}
    assert len(resolver.papers) == 1
    resolver_paper = resolver.papers[0]
    assert ev.identity_key(resolver_paper) == "doi:10.1234/samework"
    assert resolver_paper["arxiv_id"] == "2608.12345v2"
    assert resolver_paper["title"] == "Canonical title"
    assert resolver_paper["source"] == "openalex"
    assert resolver_paper["llm"] == {"priority": "High"}
    assert bucket.read_bytes() == original_daily

    saved = json.loads(index.read_text(encoding="utf-8"))["records"]
    assert set(saved) == {
        "doi:10.1234/samework", "doi:10.1234/SameWork",
    }
    assert all(record["status"] == "available" for record in saved.values())

    # The one-time bypass is specific to the old source-less negative.  Once
    # an ordinary fresh result exists, normal cache reuse resumes.
    second_resolver = MetadataCapturingResolver()
    second = ev.enrich(
        daily_dir=daily, index_path=index, resolver=second_resolver, limit=10,
        priorities={"High"}, now=NOW + dt.timedelta(seconds=1),
    )
    assert second["attempted"] == 0
    assert second_resolver.papers == []


def test_doi_metadata_donor_can_come_from_noncanonical_raw_observation(
        tmp_path):
    daily = tmp_path / "daily"
    daily.mkdir()
    (daily / "2026-01-01.json").write_text(json.dumps({
        "papers": [{
            "doi": "10.1234/samework",
            "title": "Canonical title",
            "source": "openalex",
            "llm": {"priority": "High"},
        }],
    }), encoding="utf-8")
    (daily / "2026-08-12.json").write_text(json.dumps({
        "papers": [{
            "doi": "10.1234/samework",
            "arxiv_id": "2608.12345v3",
            "first_seen_at": "2026-08-12T00:00:00Z",
            "title": "Later donor title",
            "source": "arxiv",
            "llm": {"priority": "Low"},
        }],
    }), encoding="utf-8")
    index = tmp_path / "visuals" / "index.json"
    _write_fresh_negative(index)
    resolver = MetadataCapturingResolver()

    result = ev.enrich(
        daily_dir=daily, index_path=index, resolver=resolver, limit=10,
        priorities={"High"}, now=NOW,
    )

    assert result["attempted"] == 1
    assert len(resolver.papers) == 1
    assert resolver.papers[0]["arxiv_id"] == "2608.12345v3"
    assert resolver.papers[0]["title"] == "Canonical title"
    assert resolver.papers[0]["llm"] == {"priority": "High"}


@pytest.mark.parametrize(("status", "reason"), [
    ("not_found", "arxiv_html_no_reusable_figure"),
    ("blocked", "pmc_license_not_reusable"),
    ("error", "pmc: HTTP 429"),
])
def test_alias_metadata_does_not_bypass_other_fresh_cache_results(
        tmp_path, status, reason):
    daily = tmp_path / "daily"
    daily.mkdir()
    (daily / "2026-08-12.json").write_text(json.dumps({
        "papers": [
            {
                "doi": "10.1234/samework",
                "llm": {"priority": "High"},
            },
            {
                "doi": "10.1234/SameWork",
                "arxiv_id": "2608.12345v1",
                "llm": {"priority": "Low"},
            },
        ],
    }), encoding="utf-8")
    index = tmp_path / "visuals" / "index.json"
    cached = _write_fresh_negative(index, status=status, reason=reason)
    resolver = MetadataCapturingResolver()

    result = ev.enrich(
        daily_dir=daily, index_path=index, resolver=resolver, limit=10,
        priorities={"High"}, now=NOW,
    )

    assert result["attempted"] == 0
    assert resolver.papers == []
    saved = json.loads(index.read_text(encoding="utf-8"))["records"]
    assert saved["doi:10.1234/samework"] == cached
    assert saved["doi:10.1234/SameWork"] == cached


def test_doi_alias_arxiv_versions_are_one_nonconflicting_work(tmp_path):
    daily = tmp_path / "daily"
    daily.mkdir()
    (daily / "2026-08-12.json").write_text(json.dumps({
        "papers": [
            {
                "doi": "10.1234/samework",
                "llm": {"priority": "High"},
            },
            {
                "doi": "10.1234/SameWork",
                "arxiv_id": "2608.12345v1",
                "llm": {"priority": "Low"},
            },
            {
                "doi": "10.1234/SAMEWORK",
                "arxiv_id": "2608.12345v3",
                "llm": {"priority": "Exclude"},
            },
        ],
    }), encoding="utf-8")

    rows = ev.iter_candidates(daily, {"High"})

    assert len(rows) == 1
    assert rows[0][0] == "doi:10.1234/samework"
    assert rows[0][1]["arxiv_id"] == "2608.12345v1"


def test_conflicting_doi_alias_arxiv_metadata_fails_closed(tmp_path):
    daily = tmp_path / "daily"
    daily.mkdir()
    (daily / "2026-08-12.json").write_text(json.dumps({
        "papers": [
            {
                "doi": "10.1234/samework",
                "llm": {"priority": "High"},
            },
            {
                "doi": "10.1234/SameWork",
                "arxiv_id": "2608.11111v1",
                "llm": {"priority": "Low"},
            },
            {
                "doi": "10.1234/SAMEWORK",
                "arxiv_id": "2608.22222v1",
                "llm": {"priority": "Exclude"},
            },
        ],
    }), encoding="utf-8")
    index = tmp_path / "visuals" / "index.json"
    _write_fresh_negative(index)
    resolver = MetadataCapturingResolver()

    rows = ev.iter_candidates(daily, {"High"})
    assert len(rows) == 1
    assert rows[0][0] == "doi:10.1234/samework"
    assert not rows[0][1].get("arxiv_id")

    result = ev.enrich(
        daily_dir=daily, index_path=index, resolver=resolver, limit=10,
        priorities={"High"}, now=NOW,
    )
    assert result["attempted"] == 0
    assert resolver.papers == []
