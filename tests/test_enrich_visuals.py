import datetime as dt
import html as html_mod
import json
import pathlib
import sys
import urllib.error

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
                 content_length=None):
        self.payload = payload
        self.url = url
        self.headers = {}
        if content_length is not None:
            self.headers["Content-Length"] = str(content_length)
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


def test_http_client_verifies_image_magic_bytes():
    png = FakeHttpResponse(
        b"\x89PNG\r\n\x1a\ncontent", url="https://arxiv.org/html/figure.png",
    )
    ev.HttpClient(opener=FakeOpener(png), min_delay=0).verify_image(
        "https://arxiv.org/html/figure.png", allowed_hosts={"arxiv.org"},
    )

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
        "Photo by Example Photographer.",
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
    assert "permission" not in visual["caption"].lower()
    converter = client.calls[0]
    assert converter[2]["tool"] == "research-radar-visuals"
    assert converter[2]["email"] == "maintainer@example.org"
    assert all("deprecated" not in call[1] for call in client.calls)


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
    assert client.calls[0][0] == "https://oaipmh.arxiv.org/oai"
    assert client.calls[0][1]["metadataPrefix"] == "arXivRaw"
    assert client.calls[0][2] == {
        "oaipmh.arxiv.org", "export.arxiv.org",
    }


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
    stale_with_recent_error = {
        "status": "available", "checked_at": recent,
        "selector_version": ev.SELECTOR_VERSION - 1,
        "selector_error_at": ev.iso_z(NOW - dt.timedelta(hours=4)),
    }
    assert not ev.should_refresh(stale_with_recent_error, now=NOW)
    assert ev.should_refresh(
        stale_with_recent_error, now=NOW + dt.timedelta(days=1, seconds=1),
    )


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
    cached["selector_version"] = ev.SELECTOR_VERSION - 1
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
    assert saved["selector_version"] == ev.SELECTOR_VERSION - 1
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
        cached["selector_version"] = ev.SELECTOR_VERSION - 1
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
