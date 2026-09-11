from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest

import community_intelligence.acquisition.blum as blum
from community_intelligence.acquisition.blum import (
    AcquiredPage,
    DiscoveryRecord,
    archive_hint_to_official_url,
    audit_blog_index,
    build_manifest,
    canonicalize_url,
    import_sources_into_frozen_m2,
    importable_source_input,
    load_discovery_hints,
    load_private_sources,
    normalize_page,
    parse_html_page,
    parse_sitemap,
    screen_url,
    unavailable_reason,
)

OBSERVED = datetime(2026, 9, 11, 10, tzinfo=UTC)


def test_blog_catalog_parser_freezes_card_level_provenance() -> None:
    body = b"""<html><main><div class="blog-grid">
      <article class="blog-card" data-category="New Features">
        <a href="https://web.archive.org/web/20260830134805/https://blum.io/post/mini-app">
          <div class="article-meta"><span>New Features</span><time>April 19, 2024</time></div>
          <h2>Blum's Telegram Mini App is Out</h2><span>Read article</span>
        </a>
      </article>
      <article class="blog-card" data-category="Product">
        <a href="/post/current"><div class="article-meta"><span>Product</span>
          <time>July 28, 2025</time></div><h2>Current Product</h2>
        </a>
      </article>
    </div></main></html>"""

    cards = blum.parse_blog_catalog(
        body,
        catalog_url="https://blum.io/blog/",
        observed_at=OBSERVED,
    )

    assert len(cards) == 2
    archived, current = cards
    assert archived.article_title == "Blum's Telegram Mini App is Out"
    assert archived.category == "New Features"
    assert archived.publication_date == "2024-04-19"
    assert archived.publication_date_precision == "date"
    assert archived.target_kind == "official_index_linked_archive"
    assert archived.original_canonical_url == "https://blum.io/post/mini-app"
    assert archived.catalog_raw_hash == hashlib.sha256(body).hexdigest()
    assert archived.discovery_evidence["relationship"] == "official_catalog_article_card"
    assert current.target_kind == "current_official"
    assert current.original_canonical_url == "https://blum.io/post/current"


def test_blog_catalog_parser_keeps_missing_category_as_unknown() -> None:
    body = b"""<article class="blog-card" data-category="">
      <a href="https://web.archive.org/web/20260830134805/https://blum.io/post/terms">
        <div class="article-meta"><span></span><time>May 27, 2025</time></div>
        <h2>Blum Trading Bot - Terms of Use</h2>
      </a></article>"""

    cards = blum.parse_blog_catalog(
        body,
        catalog_url="https://blum.io/blog/",
        observed_at=OBSERVED,
    )

    assert cards[0].category == "unknown"


def test_wayback_parser_recovers_article_and_excludes_archive_chrome() -> None:
    card = blum.BlogCatalogCard(
        catalog_url="https://blum.io/blog",
        article_title="Blum's Telegram Mini App is Out",
        category="New Features",
        publication_date="2024-04-19",
        publication_date_precision="date",
        read_article_url=(
            "https://web.archive.org/web/20260830134805/"
            "https://blum.io/post/blums-telegram-mini-app-is-out"
        ),
        original_canonical_url=(
            "https://blum.io/post/blums-telegram-mini-app-is-out"
        ),
        target_kind="official_index_linked_archive",
        catalog_observed_at="2026-09-11T10:00:00Z",
        catalog_raw_hash="a" * 64,
        discovery_evidence={"relationship": "official_catalog_article_card"},
    )
    body = b"""<html lang="en"><head><title>Blum Blog | Mini App</title></head><body>
      <div id="wm-ipp-base">Wayback Machine Save Page Now</div>
      <nav>Archive navigation</nav>
      <h1 class="heading-large">Blum's Telegram Mini App is Out</h1>
      <div class="rich-text-block-3 w-richtext">
        <p>Blum is available as a Telegram mini app with points farming.</p>
        <h2>How to begin</h2><ul><li>Open the bot.</li><li>Tap Farm.</li></ul>
        <p>See the <a href="https://web.archive.org/web/20260513185554/https://blum.io/">
        official home</a>.</p>
      </div><footer>Replay metadata text</footer>
    </body></html>"""
    page = AcquiredPage(
        requested_url=card.read_article_url,
        final_url=(
            "https://web.archive.org/web/20260513185554/"
            "https://www.blum.io/post/blums-telegram-mini-app-is-out"
        ),
        status_code=200,
        content_type="text/html",
        body=body,
        fetched_at=OBSERVED,
        etag=None,
        last_modified=None,
    )

    source = blum.normalize_historical_archive(page, card)

    assert source.normalized_title == card.article_title
    assert source.original_canonical_url == card.original_canonical_url
    assert source.archive_snapshot_at == "2026-05-13T18:55:54Z"
    assert source.official_catalog_publication_date == "2024-04-19"
    assert source.content_origin == "historical_archive_snapshot"
    assert source.official_identity_basis == "current_official_blog_index_link"
    assert source.source_type == "official_blog"
    assert "## How to begin" in source.content
    assert "- Open the bot." in source.content
    assert "[official home](https://blum.io/)" in source.content
    assert "Wayback Machine" not in source.content
    assert "Replay metadata" not in source.content
    assert source.validation_status == "passed"


def test_wayback_raw_capture_url_preserves_catalog_target_identity() -> None:
    assert blum.wayback_raw_capture_url(
        "https://web.archive.org/web/20260830134805/https://blum.io/post/mini-app"
    ) == (
        "https://web.archive.org/web/20260830134805id_/https://blum.io/post/mini-app"
    )


def test_archive_fetch_retries_one_transient_timeout() -> None:
    calls = 0
    expected = AcquiredPage(
        requested_url="https://web.archive.org/web/20260101000000id_/https://blum.io/post/a",
        final_url="https://web.archive.org/web/20260101000000id_/https://blum.io/post/a",
        status_code=200,
        content_type="text/html",
        body=b"ok",
        fetched_at=OBSERVED,
        etag=None,
        last_modified=None,
    )

    class TransientFetcher:
        def fetch(self, url: str) -> AcquiredPage:
            nonlocal calls
            calls += 1
            if calls == 1:
                raise httpx.ReadTimeout("temporary")
            return expected

    assert blum.fetch_with_transient_retry(TransientFetcher(), expected.requested_url) == expected
    assert calls == 2


def test_wayback_parser_rejects_error_shell_and_title_mismatch() -> None:
    card = blum.BlogCatalogCard(
        catalog_url="https://blum.io/blog",
        article_title="Expected Blum Article",
        category="Company News",
        publication_date="2024-05-03",
        publication_date_precision="date",
        read_article_url=(
            "https://web.archive.org/web/20260830134805/https://blum.io/post/expected"
        ),
        original_canonical_url="https://blum.io/post/expected",
        target_kind="official_index_linked_archive",
        catalog_observed_at="2026-09-11T10:00:00Z",
        catalog_raw_hash="a" * 64,
        discovery_evidence={"relationship": "official_catalog_article_card"},
    )
    page = AcquiredPage(
        requested_url=card.read_article_url,
        final_url=(
            "https://web.archive.org/web/20260513185554/https://blum.io/post/other"
        ),
        status_code=200,
        content_type="text/html",
        body=(
            b'<html><h1>Other Page</h1><div class="rich-text-block-3 w-richtext">'
            b'<p>Wayback Machine does not have this URL archived.</p></div></html>'
        ),
        fetched_at=OBSERVED,
        etag=None,
        last_modified=None,
    )

    source = blum.normalize_historical_archive(page, card)

    assert source.validation_status == "failed"
    assert set(source.validation_failures) >= {
        "original_url_mismatch",
        "title_mismatch",
        "archive_error_shell",
    }


def test_archive_language_audit_keeps_declared_language_mismatch() -> None:
    card = blum.BlogCatalogCard(
        catalog_url="https://blum.io/blog",
        article_title="English Campaign",
        category="Campaigns",
        publication_date="2025-05-19",
        publication_date_precision="date",
        read_article_url=(
            "https://web.archive.org/web/20260830134805/https://blum.io/post/campaign"
        ),
        original_canonical_url="https://blum.io/post/campaign",
        target_kind="official_index_linked_archive",
        catalog_observed_at="2026-09-11T10:00:00Z",
        catalog_raw_hash="a" * 64,
        discovery_evidence={"relationship": "official_catalog_article_card"},
    )
    page = AcquiredPage(
        requested_url=card.read_article_url,
        final_url=(
            "https://web.archive.org/web/20260116182721/https://www.blum.io/post/campaign"
        ),
        status_code=200,
        content_type="text/html",
        body=b"""<html lang="ru"><h1 class="heading-large">English Campaign</h1>
        <div class="rich-text-block-3 w-richtext"><p>This campaign rewards users who
        trade eligible tokens through the Blum Trading Bot during the stated period.</p>
        <p>Participants can review the official rules and prize allocation in this
        announcement before joining the campaign.</p></div></html>""",
        fetched_at=OBSERVED,
        etag=None,
        last_modified=None,
    )

    source = blum.normalize_historical_archive(page, card)

    assert source.html_language == "ru"
    assert source.language == "en"
    assert source.language_basis == "system-derived-script-audit"
    assert source.language_mismatch is True


def test_historical_archive_compatibility_probe_accepts_honest_day_precision() -> None:
    card = blum.BlogCatalogCard(
        catalog_url="https://blum.io/blog",
        article_title="Historical Article",
        category="Company News",
        publication_date="2024-05-03",
        publication_date_precision="date",
        read_article_url=(
            "https://web.archive.org/web/20260830134805/https://blum.io/post/historical"
        ),
        original_canonical_url="https://blum.io/post/historical",
        target_kind="official_index_linked_archive",
        catalog_observed_at="2026-09-11T10:00:00Z",
        catalog_raw_hash="a" * 64,
        discovery_evidence={"relationship": "official_catalog_article_card"},
    )
    page = AcquiredPage(
        requested_url=blum.wayback_raw_capture_url(card.read_article_url),
        final_url=(
            "https://web.archive.org/web/20260214064512id_/"
            "https://www.blum.io/post/historical"
        ),
        status_code=200,
        content_type="text/html",
        body=b"""<html lang="en"><h1 class="heading-large">Historical Article</h1>
        <div class="rich-text-block-3 w-richtext"><p>This is a sufficiently detailed
        historical Blum article body retained from the official-index-linked snapshot.</p>
        <p>It describes a product event but provides no precise publication time or
        independently confirmed effective validity interval.</p></div></html>""",
        fetched_at=OBSERVED,
        etag=None,
        last_modified=None,
    )
    source = blum.normalize_historical_archive(page, card)

    report = blum.assess_historical_frozen_m2_compatibility([source])

    assert report["source_count"] == 1
    assert report["honestly_importable_count"] == 1
    assert report["metadata_blocked_count"] == 0
    assert report["blocker_counts"] == {}


def test_controlled_set_is_limited_to_cn_chat_overlap() -> None:
    cards = [
        blum.BlogCatalogCard(
            catalog_url="https://blum.io/blog",
            article_title=f"Article {day}",
            category="Product",
            publication_date=day,
            publication_date_precision="date",
            read_article_url=(
                f"https://web.archive.org/web/20260830134805/https://blum.io/post/{day}"
            ),
            original_canonical_url=f"https://blum.io/post/{day}",
            target_kind="official_index_linked_archive",
            catalog_observed_at="2026-09-11T10:00:00Z",
            catalog_raw_hash="a" * 64,
            discovery_evidence={"relationship": "official_catalog_article_card"},
        )
        for day in ("2024-03-15", "2024-03-29", "2024-08-18", "2024-08-19")
    ]

    selected = blum.select_controlled_archive_cards(cards, limit=10)

    assert [card.publication_date for card in selected] == ["2024-03-29", "2024-08-18"]


def test_historical_blog_runner_writes_private_artifacts_and_gate(tmp_path: Path) -> None:
    catalog_body = b"""<article class="blog-card" data-category="New Features">
      <a href="https://web.archive.org/web/20260830134805/https://blum.io/post/mini-app">
        <time>April 19, 2024</time><h2>Mini App Launch</h2>
      </a></article>"""
    archive_body = b"""<html lang="en"><h1 class="heading-large">Mini App Launch</h1>
      <div class="rich-text-block-3 w-richtext"><p>Blum launched its Telegram mini app
      so community members could access product features and begin using Blum Points.</p>
      <h2>Launch details</h2><p>The official article explains the initial product flow
      and the steps available to early users of the Telegram application.</p></div></html>"""

    requested_urls: list[str] = []

    class FakeFetcher:
        def fetch(self, url: str) -> AcquiredPage:
            requested_urls.append(url)
            if url == "https://blum.io/blog/":
                return AcquiredPage(
                    requested_url=url,
                    final_url=url,
                    status_code=200,
                    content_type="text/html",
                    body=catalog_body,
                    fetched_at=OBSERVED,
                    etag='"catalog"',
                    last_modified=None,
                )
            return AcquiredPage(
                requested_url=url,
                final_url=(
                    "https://web.archive.org/web/20260513185554id_/"
                    "https://www.blum.io/post/mini-app"
                ),
                status_code=200,
                content_type="text/html",
                body=archive_body,
                fetched_at=OBSERVED,
                etag=None,
                last_modified=None,
            )

    manifest = blum.run_historical_blog_acquisition(
        tmp_path,
        phase="controlled",
        fetcher=FakeFetcher(),
        generated_at=OBSERVED,
    )

    assert manifest["summary"]["total_blog_catalog_articles"] == 1
    assert manifest["summary"]["official_index_linked_archive_articles"] == 1
    assert manifest["summary"]["cn_chat_overlap_articles"] == 1
    assert manifest["summary"]["successfully_acquired_archive_snapshots"] == 1
    assert manifest["summary"]["provenance_incomplete_cases"] == 0
    assert manifest["controlled_gate"]["status"] == "passed"
    assert requested_urls[1] == (
        "https://web.archive.org/web/20260830134805id_/https://blum.io/post/mini-app"
    )
    assert "content" not in manifest["sources"][0]
    assert (tmp_path / "historical-blog" / "catalog.json").exists()
    assert (tmp_path / "historical-blog" / "controlled-gate.json").exists()
    normalized = json.loads(
        next((tmp_path / "historical-blog" / "normalized").glob("*.json")).read_text()
    )
    assert "Telegram mini app" in normalized["content"]
    loaded = blum.load_private_historical_sources(tmp_path / "historical-blog", phase="controlled")
    adapted = blum.historical_blog_source_input(loaded[0])
    assert adapted.published_on.isoformat() == "2024-04-19"
    assert adapted.published_at is None
    assert adapted.temporal_precision == "day"
    assert adapted.effective_from is None
    assert adapted.semantic_tags["archive_snapshot_time_role"] == "capture-only-not-publication"


def test_sitemap_parser_handles_urlset_and_index_without_guessing_types() -> None:
    urlset = b"""<?xml version="1.0"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
      <url><loc>https://blum.io/post/a</loc></url>
      <url><loc>https://blum.io/post/b?utm_source=x</loc></url>
    </urlset>"""
    sitemap_index = b"""<?xml version="1.0"?><sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
      <sitemap><loc>https://help.blum.io/sitemap-articles.xml</loc></sitemap>
    </sitemapindex>"""

    assert parse_sitemap(urlset) == (
        ["https://blum.io/post/a", "https://blum.io/post/b"],
        [],
    )
    assert parse_sitemap(sitemap_index) == (
        [],
        ["https://help.blum.io/sitemap-articles.xml"],
    )


def test_blog_index_audit_distinguishes_current_origin_from_archive_links() -> None:
    html = b"""<main>
      <article class="blog-card"><a href="/post/current"><time>July 28, 2025</time></a></article>
      <article class="blog-card"><a href="https://web.archive.org/web/1/https://blum.io/post/old">
      <time>March 1, 2024</time></a></article></main>"""

    audit = audit_blog_index(html, "https://blum.io/blog")

    assert audit == {
        "listed_article_count": 2,
        "listed_publication_date_count": 2,
        "listed_2024_article_count": 1,
        "same_origin_article_link_count": 1,
        "external_archive_article_link_count": 1,
    }
    assert (
        archive_hint_to_official_url(
            "https://web.archive.org/web/20260830/https://blum.io/post/old"
        )
        == "https://blum.io/post/old"
    )
    assert (
        archive_hint_to_official_url(
            canonicalize_url("https://web.archive.org/web/20260830/https://blum.io/post/old")
        )
        == "https://blum.io/post/old"
    )
    assert archive_hint_to_official_url("https://example.org/https://blum.io/post/old") is None


def test_canonicalize_and_screen_only_keep_approved_content_urls() -> None:
    assert (
        canonicalize_url("https://blum.io/post/tokenomics/?utm_source=x&b=2&a=1#supply")
        == "https://blum.io/post/tokenomics?a=1&b=2"
    )
    assert screen_url("https://blum.io/post/tokenomics", "blum.io") == (True, None)
    assert screen_url("https://blum.io/blog?page=2", "blum.io") == (
        False,
        "pagination",
    )
    assert screen_url("https://blum.io/blog/tag/product", "blum.io") == (
        False,
        "listing_page",
    )
    assert screen_url("https://web.archive.org/web/1/https://blum.io/post/a", "blum.io") == (
        False,
        "external_origin",
    )
    assert screen_url("https://help.blum.io/login", "help.blum.io") == (
        False,
        "account_or_search",
    )


def test_archive_discovery_hint_marks_failed_official_retry_as_unavailable() -> None:
    archive_hint = "https://web.archive.org/web/20260830/https://blum.io/post/old"

    assert unavailable_reason(
        requested_url="https://blum.io/post/old",
        discovered_from=archive_hint,
        final_url="https://blum.io/post/old",
        status_code=404,
        content_type="text/html",
        screening_reason=None,
    ) == "official_source_unavailable_archive_fallback_candidate"
    assert unavailable_reason(
        requested_url="https://help.blum.io/blum-general-faq",
        discovered_from="public_index_discovery_hint",
        final_url="https://help.blum.io/blum-general-faq",
        status_code=403,
        content_type="text/html",
        screening_reason=None,
    ) == "official_source_unavailable"


def test_discovery_hint_loader_keeps_only_deduplicated_official_urls(tmp_path: Path) -> None:
    hint_file = tmp_path / "hints.txt"
    hint_file.write_text(
        "\n".join(
            [
                "https://help.blum.io/blum-general-faq",
                "https://help.blum.io/blum-general-faq#top",
                "https://blum.io/post/tokenomics?utm_source=index",
                "https://example.org/not-official",
                "not-a-url",
            ]
        ),
        encoding="utf-8",
    )

    assert load_discovery_hints(hint_file) == [
        "https://help.blum.io/blum-general-faq",
        "https://blum.io/post/tokenomics",
    ]


def test_parser_preserves_source_date_precision_and_removes_navigation() -> None:
    html = b"""<!doctype html><html lang="en"><head>
      <title>Memepad guide</title>
      <link rel="canonical" href="https://blum.io/post/memepad/">
      <meta property="article:published_time" content="2025-07-28">
      <meta name="author" content="Blum Editorial">
    </head><body><nav>Products Blog Login</nav><main><article>
      <div><span>Product</span><time>July 28, 2025</time></div><h1>Memepad guide</h1>
      <h2>Launch</h2><p>Create a token from the Telegram application.</p>
    </article><h2>Explore Blum in Telegram</h2></main>
    <footer>Contact support</footer></body></html>"""

    parsed = parse_html_page(html, "https://blum.io/post/memepad")

    assert parsed.title == "Memepad guide"
    assert parsed.canonical_url == "https://blum.io/post/memepad"
    assert parsed.language == "en"
    assert parsed.published_at == "2025-07-28"
    assert parsed.published_precision == "date"
    assert parsed.author == "Blum Editorial"
    assert "# Memepad guide" in parsed.content
    assert "## Launch" in parsed.content
    assert "Products Blog Login" not in parsed.content
    assert "Explore Blum in Telegram" not in parsed.content
    assert parsed.category == "Product"


def test_normalizer_uses_frozen_taxonomy_and_content_hash() -> None:
    page = AcquiredPage(
        requested_url="https://blum.io/post/memepad",
        final_url="https://blum.io/post/memepad/",
        status_code=200,
        content_type="text/html",
        body=b"<html></html>",
        fetched_at=OBSERVED,
        etag='"abc"',
        last_modified=None,
    )
    parsed = parse_html_page(
        b"""<html lang="en"><head><title>Memepad</title>
        <meta property="article:published_time" content="2025-07-28"></head>
        <body><article><p>Product</p><h1>Memepad</h1>
        <p>Create and trade a token in Telegram with Blum.</p></article></body></html>""",
        page.final_url,
    )

    source = normalize_page(page, parsed, source_channel="website")

    assert source.source_type == "product_docs"
    assert source.source_channel == "website"
    assert source.metadata_provenance["source_type"] == "system-derived"
    assert source.metadata_provenance["published_at"] == "source-provided"
    assert len(source.content_hash) == 64
    assert source.official_status == "verified_official"
    assert source.historical_coverage == "partial"


def test_manifest_counts_hash_duplicates_failures_unknowns_and_time_coverage() -> None:
    discovery = [
        DiscoveryRecord(
            canonical_url="https://blum.io/post/a",
            domain="blum.io",
            title="A",
            discovered_from="https://blum.io/sitemap.xml",
            source_channel="website",
            candidate_source_type="official_blog",
            language="en",
            fetch_status="succeeded",
            http_status=200,
            discovered_at="2026-09-11T10:00:00Z",
            decision="included",
        ),
        DiscoveryRecord(
            canonical_url="https://blum.io/post/b",
            domain="blum.io",
            title="B",
            discovered_from="https://blum.io/blog",
            source_channel="website",
            candidate_source_type="unknown",
            language="en",
            fetch_status="failed",
            http_status=503,
            discovered_at="2026-09-11T10:00:00Z",
            decision="failed",
        ),
    ]
    first = normalize_page(
        AcquiredPage(
            requested_url="https://blum.io/post/a",
            final_url="https://blum.io/post/a",
            status_code=200,
            content_type="text/html",
            body=b"a",
            fetched_at=OBSERVED,
            etag=None,
            last_modified=None,
        ),
        parse_html_page(
            b"<html lang=en><head><title>A</title></head><body>"
            b"<article>Useful body</article></body></html>",
            "https://blum.io/post/a",
        ),
        source_channel="website",
    )
    duplicate = first.model_copy(
        update={"canonical_url": "https://blum.io/post/a-copy", "title": "A copy"}
    )

    manifest = build_manifest(
        discovery,
        [first, duplicate],
        generated_at=OBSERVED,
        baseline_commit="3858dbf4236a8b148997dede40b609f057d3b23e",
    )

    assert manifest["version"] == "blum-knowledge-pack-v1"
    assert manifest["summary"]["discovered_url_count"] == 2
    assert manifest["summary"]["fetched_source_count"] == 2
    assert manifest["summary"]["content_hash_duplicate_count"] == 1
    assert manifest["summary"]["fetch_failure_count"] == 1
    assert manifest["summary"]["unknown_source_type_count"] == 0
    assert manifest["summary"]["published_at_ratio"] == 0


def test_manifest_separates_help_hint_coverage_from_fetch_success() -> None:
    discovery = [
        DiscoveryRecord(
            canonical_url="https://help.blum.io/blum-general-faq",
            domain="help.blum.io",
            title=None,
            discovered_from="archive_url_inventory_hint",
            source_channel="docs",
            candidate_source_type="unknown",
            language=None,
            fetch_status="failed",
            http_status=403,
            discovered_at="2026-09-11T10:00:00Z",
            decision="failed",
            exclusion_reason="official_source_unavailable",
        )
    ]

    manifest = build_manifest(
        discovery,
        [],
        generated_at=OBSERVED,
        baseline_commit="3858dbf4236a8b148997dede40b609f057d3b23e",
    )

    assert manifest["summary"]["help_official_url_candidate_count"] == 1
    assert manifest["summary"]["help_official_url_recovered_count"] == 0
    assert manifest["summary"]["help_official_url_unavailable_count"] == 1


def test_precision_aware_m2_adapter_accepts_date_only_without_effective_time() -> None:
    page = AcquiredPage(
        requested_url="https://blum.io/post/a",
        final_url="https://blum.io/post/a",
        status_code=200,
        content_type="text/html",
        body=b"a",
        fetched_at=OBSERVED,
        etag=None,
        last_modified=None,
    )
    source = normalize_page(
        page,
        parse_html_page(
            b"""<html lang=en><head><title>A</title>
            <meta property="article:published_time" content="2025-07-28"></head>
            <body><article><p>Product</p><h1>A</h1><p>Useful body.</p></article></body></html>""",
            page.final_url,
        ),
        source_channel="website",
    )

    adapted = importable_source_input(source)

    assert adapted.source_type == "official_blog"
    assert adapted.published_on.isoformat() == "2025-07-28"
    assert adapted.published_at is None
    assert adapted.temporal_precision == "day"
    assert adapted.effective_from is None
    assert adapted.source_timezone == "date-only"
    assert adapted.metadata_provenance["validity"] == "not-provided"


def test_frozen_m2_adapter_accepts_precise_source_time_without_changing_baseline(
    tmp_path: Path,
) -> None:
    page = AcquiredPage(
        requested_url="https://blum.io/post/a",
        final_url="https://blum.io/post/a",
        status_code=200,
        content_type="text/html",
        body=b"a",
        fetched_at=OBSERVED,
        etag=None,
        last_modified=None,
    )
    source = normalize_page(
        page,
        parse_html_page(
            b"""<html lang=en><head><title>A</title>
            <meta property="article:published_time" content="2025-07-28T12:30:00+00:00"></head>
            <body><article><p>Product</p><h1>A</h1><p>Useful body.</p></article></body></html>""",
            page.final_url,
        ),
        source_channel="website",
    ).model_copy(
        update={
            "effective_from": "2025-07-28T12:30:00+00:00",
            "effective_precision": "datetime",
            "metadata_provenance": {
                "source_type": "system-derived",
                "source_channel": "human-confirmed",
                "language": "source-provided",
                "authority_level": "human-confirmed",
                "official_status": "human-confirmed",
                "published_at": "source-provided",
                "validity": "human-confirmed",
            },
        }
    )

    adapted = importable_source_input(source)

    assert adapted.published_at == datetime(2025, 7, 28, 12, 30, tzinfo=UTC)
    assert adapted.effective_from == adapted.published_at
    assert adapted.source_type == "official_blog"

    result = import_sources_into_frozen_m2(
        [source],
        database_path=tmp_path / "blum.sqlite3",
        artifact_root=tmp_path / "knowledge",
        clock=lambda: OBSERVED,
    )

    assert result["workspace"]["project_name"] == "Blum Hero Workspace"
    assert result["imported_count"] == 1
    assert result["blocked_count"] == 0


def test_private_source_loader_verifies_normalized_and_raw_hashes(tmp_path: Path) -> None:
    page = AcquiredPage(
        requested_url="https://blum.io/post/a",
        final_url="https://blum.io/post/a",
        status_code=200,
        content_type="text/html",
        body=b"<html><article><h1>A</h1><p>Useful body.</p></article></html>",
        fetched_at=OBSERVED,
        etag=None,
        last_modified=None,
    )
    source = normalize_page(
        page,
        parse_html_page(page.body, page.final_url),
        source_channel="website",
    )
    (tmp_path / "raw").mkdir()
    (tmp_path / "normalized").mkdir()
    (tmp_path / "raw" / f"{source.artifact_id}.html").write_bytes(page.body)
    (tmp_path / "normalized" / f"{source.artifact_id}.json").write_text(
        source.model_dump_json(), encoding="utf-8"
    )
    (tmp_path / "manifest.json").write_text(
        json.dumps({"sources": [{"artifact_id": source.artifact_id}]}), encoding="utf-8"
    )

    assert load_private_sources(tmp_path) == [source]

    (tmp_path / "raw" / f"{source.artifact_id}.html").write_bytes(b"tampered")
    with pytest.raises(ValueError, match="raw snapshot hash mismatch"):
        load_private_sources(tmp_path)
