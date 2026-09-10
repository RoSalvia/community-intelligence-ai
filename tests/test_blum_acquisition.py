from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

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


def test_frozen_m2_adapter_refuses_date_only_or_missing_validity() -> None:
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

    with pytest.raises(ValueError, match="precise source-provided published_at"):
        importable_source_input(source)


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
    assert adapted.source_type == "product_docs"

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
