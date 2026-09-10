"""Blum official-source Knowledge Pack acquisition."""

from __future__ import annotations

import argparse
import difflib
import hashlib
import json
import re
import time
import unicodedata
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit
from urllib.robotparser import RobotFileParser
from xml.etree import ElementTree

import httpx
from pydantic import BaseModel

from community_intelligence.application.data_foundation import DataFoundationService
from community_intelligence.application.knowledge import KnowledgeService, SourceInput


class ParsedPage(BaseModel):
    title: str
    canonical_url: str
    language: str
    content: str
    published_at: str | None = None
    published_precision: str | None = None
    updated_at: str | None = None
    updated_precision: str | None = None
    author: str | None = None
    category: str | None = None


class NormalizedSource(BaseModel):
    artifact_id: str
    title: str
    canonical_url: str
    source_type: str
    source_channel: str
    language: str
    published_at: str | None = None
    published_precision: str | None = None
    updated_at: str | None = None
    updated_precision: str | None = None
    observed_at: str
    effective_from: str | None = None
    effective_precision: str | None = None
    author: str | None = None
    official_status: str
    content: str
    content_hash: str
    raw_hash: str
    historical_coverage: str
    metadata_provenance: dict[str, str]
    fetch_metadata: dict[str, Any]


class DiscoveryRecord(BaseModel):
    canonical_url: str
    domain: str
    title: str | None
    discovered_from: str
    source_channel: str
    candidate_source_type: str
    language: str | None
    fetch_status: str
    http_status: int | None
    discovered_at: str
    decision: str
    exclusion_reason: str | None = None


class BlogCatalogCard(BaseModel):
    catalog_url: str
    article_title: str
    category: str
    publication_date: str
    publication_date_precision: str
    read_article_url: str
    original_canonical_url: str
    target_kind: str
    catalog_observed_at: str
    catalog_raw_hash: str
    discovery_evidence: dict[str, Any]


class HistoricalBlogSource(BaseModel):
    artifact_id: str
    original_canonical_url: str
    archive_snapshot_url: str
    archive_snapshot_at: str | None
    archive_replay_mode: str
    official_catalog_url: str
    official_catalog_link_observed_at: str
    official_catalog_title: str
    official_catalog_category: str
    official_catalog_publication_date: str
    publication_date_precision: str
    normalized_title: str
    language: str
    html_language: str
    language_basis: str
    language_mismatch: bool
    source_type: str
    source_channel: str
    content_origin: str
    official_identity_basis: str
    content: str
    content_hash: str
    raw_snapshot_hash: str
    acquisition_observed_at: str
    parser_version: str
    provenance_relationship: dict[str, str]
    validation_status: str
    validation_failures: list[str]


@dataclass(frozen=True)
class AcquiredPage:
    requested_url: str
    final_url: str
    status_code: int
    content_type: str
    body: bytes
    fetched_at: datetime
    etag: str | None
    last_modified: str | None


USER_AGENT = "CommunityIntelligenceKnowledgeAcquisition/1.0"
BASELINE_COMMIT = "3858dbf4236a8b148997dede40b609f057d3b23e"
ARCHIVE_PARSER_VERSION = "wayback-webflow-richtext-v1"


@dataclass(frozen=True)
class AcquisitionTarget:
    origin: str
    navigation_url: str
    sitemap_url: str
    source_channel: str

    @property
    def domain(self) -> str:
        return urlsplit(self.origin).hostname or ""


TARGETS = (
    AcquisitionTarget(
        origin="https://help.blum.io",
        navigation_url="https://help.blum.io/",
        sitemap_url="https://help.blum.io/sitemap.xml",
        source_channel="docs",
    ),
    AcquisitionTarget(
        origin="https://blum.io",
        navigation_url="https://blum.io/blog",
        sitemap_url="https://blum.io/sitemap.xml",
        source_channel="website",
    ),
)


def canonicalize_url(url: str) -> str:
    parsed = urlsplit(url.strip())
    host = (parsed.hostname or "").casefold()
    port = f":{parsed.port}" if parsed.port and parsed.port not in {80, 443} else ""
    path = re.sub(r"/{2,}", "/", parsed.path or "/")
    if path != "/":
        path = path.rstrip("/")
    kept = [
        (key, value)
        for key, value in parse_qsl(parsed.query, keep_blank_values=True)
        if not key.casefold().startswith("utm_")
        and key.casefold() not in {"fbclid", "gclid", "ref", "referrer"}
    ]
    query = urlencode(sorted(kept))
    return urlunsplit((parsed.scheme.casefold(), host + port, path, query, ""))


def screen_url(url: str, allowed_domain: str) -> tuple[bool, str | None]:
    parsed = urlsplit(canonicalize_url(url))
    if parsed.scheme not in {"http", "https"} or parsed.hostname != allowed_domain:
        return False, "external_origin"
    path = parsed.path.casefold()
    query_keys = {key.casefold() for key, _ in parse_qsl(parsed.query)}
    if query_keys & {"page", "p", "offset", "cursor"} or re.search(r"/page/\d+", path):
        return False, "pagination"
    if any(segment in path.split("/") for segment in {"login", "account", "search", "signin"}):
        return False, "account_or_search"
    if re.search(r"/(?:tag|tags|category|categories)(?:/|$)", path):
        return False, "listing_page"
    return True, None


def parse_sitemap(body: bytes) -> tuple[list[str], list[str]]:
    root = ElementTree.fromstring(body)
    kind = root.tag.rsplit("}", 1)[-1]
    locations = [
        canonicalize_url((node.text or "").strip())
        for node in root.iter()
        if node.tag.rsplit("}", 1)[-1] == "loc" and (node.text or "").strip()
    ]
    if kind == "sitemapindex":
        return [], list(dict.fromkeys(locations))
    if kind == "urlset":
        return list(dict.fromkeys(locations)), []
    raise ValueError("unsupported sitemap document")


_DATE_ONLY = re.compile(r"\d{4}-\d{2}-\d{2}\Z")
_CATEGORY_VALUES = {
    "campaigns": "Campaigns",
    "company news": "Company News",
    "education": "Education",
    "new features": "New Features",
    "partnerships": "Partnerships",
    "product": "Product",
    "trends": "Trends",
}


def _iso_timestamp(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _normalize_time(value: str | None) -> tuple[str | None, str | None]:
    if not value:
        return None, None
    text = " ".join(value.split()).strip()
    if _DATE_ONLY.fullmatch(text):
        return text, "date"
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        parsed = None
    if parsed is not None:
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            return parsed.date().isoformat(), "date"
        return parsed.isoformat(), "datetime"
    for pattern in ("%B %d, %Y", "%b %d, %Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(text, pattern).date().isoformat(), "date"
        except ValueError:
            continue
    return None, None


class _ContentParser(HTMLParser):
    _BLOCKS = {"p", "li", "blockquote", "pre", "h1", "h2", "h3", "h4", "h5", "h6"}
    _SKIP = {"script", "style", "svg", "noscript", "template", "nav", "footer", "aside"}

    def __init__(self, base_url: str) -> None:
        super().__init__(convert_charrefs=True)
        self.base_url = base_url
        self.language = "unknown"
        self.canonical: str | None = None
        self.meta: dict[str, str] = {}
        self.head_title: list[str] = []
        self.h1: list[str] = []
        self.time_text: list[str] = []
        self.links: list[str] = []
        self._in_title = False
        self._in_time = False
        self._article_depth = 0
        self._seen_article = False
        self._main_depth = 0
        self._skip_depth = 0
        self._block_tag: str | None = None
        self._block_parts: list[str] = []
        self.blocks: list[tuple[str, str]] = []

    @staticmethod
    def _attrs(attrs: list[tuple[str, str | None]]) -> dict[str, str]:
        return {key.casefold(): value or "" for key, value in attrs}

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.casefold()
        values = self._attrs(attrs)
        if tag == "html" and values.get("lang"):
            self.language = values["lang"].casefold().split("-")[0]
        if tag == "title":
            self._in_title = True
        if tag == "link" and "canonical" in values.get("rel", "").casefold():
            self.canonical = urljoin(self.base_url, values.get("href", ""))
        if tag == "meta":
            key = values.get("property") or values.get("name") or values.get("itemprop")
            if key and values.get("content"):
                self.meta[key.casefold()] = values["content"].strip()
        if tag == "a" and values.get("href"):
            self.links.append(urljoin(self.base_url, values["href"]))
        if tag in self._SKIP:
            self._skip_depth += 1
        if tag == "article":
            if not self._seen_article:
                self.blocks = []
                self._block_parts = []
                self._block_tag = None
                self._seen_article = True
            self._article_depth += 1
        elif tag == "main":
            self._main_depth += 1
        if tag == "time":
            self._in_time = True
            datetime_value = values.get("datetime")
            if datetime_value:
                self.time_text.append(datetime_value)
        if self._inside_content and tag in self._BLOCKS:
            self._flush_block()
            self._block_tag = tag

    def handle_endtag(self, tag: str) -> None:
        tag = tag.casefold()
        if tag in self._BLOCKS and self._block_tag == tag:
            self._flush_block()
        if tag == "time":
            self._in_time = False
        if tag == "title":
            self._in_title = False
        if tag == "article":
            self._flush_block()
            self._article_depth = max(0, self._article_depth - 1)
        elif tag == "main":
            self._flush_block()
            self._main_depth = max(0, self._main_depth - 1)
        if tag in self._SKIP:
            self._skip_depth = max(0, self._skip_depth - 1)

    @property
    def _inside_content(self) -> bool:
        container_depth = self._article_depth if self._seen_article else self._main_depth
        return bool(container_depth and not self._skip_depth)

    def handle_data(self, data: str) -> None:
        value = " ".join(data.split())
        if not value:
            return
        if self._in_title:
            self.head_title.append(value)
        if self._in_time:
            self.time_text.append(value)
        if self._inside_content:
            if self._block_tag is None:
                self._block_tag = "p"
            self._block_parts.append(value)
            if self._block_tag == "h1":
                self.h1.append(value)

    def _flush_block(self) -> None:
        text = " ".join(self._block_parts).strip()
        if text and self._block_tag:
            self.blocks.append((self._block_tag, text))
        self._block_parts = []
        self._block_tag = None


def extract_links(body: bytes, url: str) -> list[str]:
    parser = _ContentParser(url)
    parser.feed(body.decode("utf-8", errors="replace"))
    return list(dict.fromkeys(canonicalize_url(link) for link in parser.links))


def archive_hint_to_official_url(url: str) -> str | None:
    parsed = urlsplit(url)
    if parsed.hostname != "web.archive.org":
        return None
    match = re.search(r"https:/+blum\.io/post/[^?#]+", url)
    if not match:
        return None
    official_path = match.group(0).split("blum.io", 1)[1]
    return canonicalize_url("https://blum.io" + official_path)


def canonicalize_original_blum_url(url: str) -> str:
    parsed = urlsplit(url.strip())
    host = (parsed.hostname or "").casefold()
    if host == "www.blum.io":
        host = "blum.io"
    if host != "blum.io":
        raise ValueError("archive original URL is not a Blum origin")
    return canonicalize_url(urlunsplit(("https", host, parsed.path, parsed.query, "")))


def parse_wayback_snapshot_url(url: str) -> tuple[str, str]:
    match = re.match(
        r"https?://web\.archive\.org/web/(\d{14})(?:[a-z]+_)?/(https?:/{1,2}.+)$",
        url.strip(),
        flags=re.I,
    )
    if not match:
        raise ValueError("invalid Wayback snapshot URL")
    snapshot = datetime.strptime(match.group(1), "%Y%m%d%H%M%S").replace(tzinfo=UTC)
    original = re.sub(r"^(https?):/([^/])", r"\1://\2", match.group(2), flags=re.I)
    return _iso_timestamp(snapshot), canonicalize_original_blum_url(original)


def wayback_raw_capture_url(url: str) -> str:
    if not re.match(r"https?://web\.archive\.org/web/\d{14}/https?:/{1,2}", url, flags=re.I):
        raise ValueError("catalog target is not a standard Wayback snapshot URL")
    return re.sub(r"(/web/\d{14})/", r"\1id_/", url, count=1, flags=re.I)


def _unwrap_wayback_resource_url(url: str) -> str:
    match = re.match(
        r"https?://web\.archive\.org/web/\d{14}(?:[a-z]+_)?/(https?:/{1,2}.+)$",
        url.strip(),
        flags=re.I,
    )
    if not match:
        return canonicalize_url(url)
    original = re.sub(r"^(https?):/([^/])", r"\1://\2", match.group(1), flags=re.I)
    parsed = urlsplit(original)
    if parsed.hostname in {"blum.io", "www.blum.io"}:
        return canonicalize_original_blum_url(original)
    return canonicalize_url(original)


class _BlogCatalogParser(HTMLParser):
    def __init__(self, base_url: str) -> None:
        super().__init__(convert_charrefs=True)
        self.base_url = base_url
        self.cards: list[dict[str, str]] = []
        self._card: dict[str, str] | None = None
        self._article_depth = 0
        self._capture: str | None = None
        self._parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.casefold()
        values = {key.casefold(): value or "" for key, value in attrs}
        classes = set(values.get("class", "").split())
        if tag == "article" and "blog-card" in classes and self._card is None:
            self._card = {"category": values.get("data-category", "").strip()}
            self._article_depth = 1
            return
        if self._card is None:
            return
        if tag == "article":
            self._article_depth += 1
        if tag == "a" and "read_article_url" not in self._card and values.get("href"):
            self._card["read_article_url"] = urljoin(self.base_url, values["href"])
        if tag == "time":
            self._capture = "publication_date"
            self._parts = []
        elif tag == "h2":
            self._capture = "article_title"
            self._parts = []

    def handle_data(self, data: str) -> None:
        if self._capture and self._card is not None:
            value = " ".join(data.split())
            if value:
                self._parts.append(value)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.casefold()
        if self._card is None:
            return
        if self._capture and tag in {"time", "h2"}:
            self._card[self._capture] = " ".join(self._parts).strip()
            self._capture = None
            self._parts = []
        if tag == "article":
            self._article_depth -= 1
            if self._article_depth == 0:
                self.cards.append(self._card)
                self._card = None


def parse_blog_catalog(
    body: bytes,
    *,
    catalog_url: str,
    observed_at: datetime,
) -> list[BlogCatalogCard]:
    parser = _BlogCatalogParser(catalog_url)
    parser.feed(body.decode("utf-8", errors="replace"))
    catalog_hash = hashlib.sha256(body).hexdigest()
    result: list[BlogCatalogCard] = []
    for index, card in enumerate(parser.cards):
        missing = {
            key
            for key in ("article_title", "publication_date", "read_article_url")
            if not card.get(key)
        }
        if missing:
            raise ValueError(f"Blog catalog card {index} missing {sorted(missing)}")
        published, precision = _normalize_time(card["publication_date"])
        if not published or precision != "date":
            raise ValueError(f"Blog catalog card {index} has invalid publication date")
        read_url = card["read_article_url"]
        original = archive_hint_to_official_url(read_url)
        if original:
            target_kind = "official_index_linked_archive"
        else:
            try:
                original = canonicalize_original_blum_url(read_url)
            except ValueError as error:
                raise ValueError(f"Blog catalog card {index} has unsupported target") from error
            if not urlsplit(original).path.startswith("/post/"):
                raise ValueError(f"Blog catalog card {index} target is not an article")
            target_kind = "current_official"
        result.append(
            BlogCatalogCard(
                catalog_url=canonicalize_url(catalog_url),
                article_title=card["article_title"],
                category=card.get("category") or "unknown",
                publication_date=published,
                publication_date_precision=precision,
                read_article_url=read_url,
                original_canonical_url=original,
                target_kind=target_kind,
                catalog_observed_at=_iso_timestamp(observed_at),
                catalog_raw_hash=catalog_hash,
                discovery_evidence={
                    "relationship": "official_catalog_article_card",
                    "catalog_url": canonicalize_url(catalog_url),
                    "card_index": index,
                },
            )
        )
    return result


def select_controlled_archive_cards(
    cards: Sequence[BlogCatalogCard],
    *,
    limit: int = 10,
) -> list[BlogCatalogCard]:
    overlap_start = "2024-03-19"
    overlap_end = "2024-08-18"
    selected = [
        card
        for card in cards
        if card.target_kind == "official_index_linked_archive"
        and overlap_start <= card.publication_date <= overlap_end
    ]
    return sorted(selected, key=lambda card: card.publication_date)[:limit]


class _ArchiveArticleParser(HTMLParser):
    _BLOCKS = {"p", "li", "blockquote", "pre", "h1", "h2", "h3", "h4", "h5", "h6"}
    _SKIP = {"script", "style", "svg", "noscript", "template", "nav", "footer", "aside"}

    def __init__(self, base_url: str) -> None:
        super().__init__(convert_charrefs=True)
        self.base_url = base_url
        self.language = "unknown"
        self.title_parts: list[str] = []
        self._title_depth = 0
        self._content_depth = 0
        self._skip_depth = 0
        self._block_tag: str | None = None
        self._block_parts: list[str] = []
        self._link_href: str | None = None
        self._link_parts: list[str] = []
        self.blocks: list[tuple[str, str]] = []
        self.content_container_found = False

    @staticmethod
    def _attrs(attrs: list[tuple[str, str | None]]) -> dict[str, str]:
        return {key.casefold(): value or "" for key, value in attrs}

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.casefold()
        values = self._attrs(attrs)
        classes = set(values.get("class", "").split())
        if tag == "html" and values.get("lang"):
            self.language = values["lang"].casefold().split("-", 1)[0]
        if tag == "h1" and "heading-large" in classes and not self._content_depth:
            self._title_depth = 1
        elif self._title_depth:
            self._title_depth += 1
        if tag in self._SKIP:
            self._skip_depth += 1
        if tag == "div" and "w-richtext" in classes and not self.content_container_found:
            self.content_container_found = True
            self._content_depth = 1
            return
        if self._content_depth:
            if tag == "div":
                self._content_depth += 1
            if not self._skip_depth and tag in self._BLOCKS:
                self._flush_block()
                self._block_tag = tag
            if not self._skip_depth and tag == "a" and values.get("href"):
                self._link_href = urljoin(self.base_url, values["href"])
                self._link_parts = []

    def handle_data(self, data: str) -> None:
        value = " ".join(data.split())
        if not value:
            return
        if self._title_depth:
            self.title_parts.append(value)
        if not self._content_depth or self._skip_depth:
            return
        if self._block_tag is None:
            self._block_tag = "p"
        if self._link_href:
            self._link_parts.append(value)
        else:
            self._block_parts.append(value)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.casefold()
        if self._link_href and tag == "a":
            label = " ".join(self._link_parts).strip()
            target = _unwrap_wayback_resource_url(self._link_href)
            self._block_parts.append(f"[{label}]({target})" if label else target)
            self._link_href = None
            self._link_parts = []
        if self._content_depth and tag in self._BLOCKS and self._block_tag == tag:
            self._flush_block()
        if self._title_depth:
            self._title_depth -= 1
        if tag in self._SKIP:
            self._skip_depth = max(0, self._skip_depth - 1)
        if self._content_depth and tag == "div":
            self._content_depth -= 1
            if self._content_depth == 0:
                self._flush_block()

    def _flush_block(self) -> None:
        text = " ".join(self._block_parts).strip()
        if text and self._block_tag:
            self.blocks.append((self._block_tag, text))
        self._block_parts = []
        self._block_tag = None


def _title_similarity(left: str, right: str) -> float:
    def normalized(value: str) -> str:
        return re.sub(r"[^\w]+", " ", value.casefold()).strip()

    return difflib.SequenceMatcher(None, normalized(left), normalized(right)).ratio()


def _audit_content_language(content: str, declared: str) -> tuple[str, str, bool]:
    letters = [character for character in content if character.isalpha()]
    if len(letters) < 40:
        return declared, "source-provided-html-lang", False
    cyrillic = sum("\u0400" <= character <= "\u04ff" for character in letters)
    latin = sum("LATIN" in unicodedata.name(character, "") for character in letters)
    if cyrillic / len(letters) >= 0.25:
        audited = "ru"
    elif latin / len(letters) >= 0.75:
        audited = "en"
    else:
        audited = declared
    mismatch = declared not in {"", "unknown"} and audited != declared
    basis = "system-derived-script-audit" if mismatch or declared == "unknown" else (
        "source-provided-html-lang"
    )
    return audited, basis, mismatch


def normalize_historical_archive(
    page: AcquiredPage,
    card: BlogCatalogCard,
) -> HistoricalBlogSource:
    failures: list[str] = []
    try:
        snapshot_at, original_url = parse_wayback_snapshot_url(page.final_url)
    except ValueError:
        snapshot_at = None
        original_url = card.original_canonical_url
        failures.append("invalid_archive_snapshot_url")
    if original_url != card.original_canonical_url:
        failures.append("original_url_mismatch")
    if page.status_code != 200:
        failures.append("archive_http_failure")
    if page.content_type != "text/html":
        failures.append("archive_non_html")

    parser = _ArchiveArticleParser(page.final_url)
    parser.feed(page.body.decode("utf-8", errors="replace"))
    parser._flush_block()
    title = " ".join(parser.title_parts).strip()
    content = _markdown_blocks(parser.blocks, title or card.article_title)
    if not parser.content_container_found:
        failures.append("article_body_not_found")
    if not title or _title_similarity(title, card.article_title) < 0.85:
        failures.append("title_mismatch")
    if len(content) < 100:
        failures.append("thin_snapshot")
    lowered = content.casefold()
    if any(
        marker in lowered
        for marker in (
            "wayback machine does not have",
            "this site has been blocked",
            "page cannot be crawled",
            "dns points to prohibited ip",
        )
    ):
        failures.append("archive_error_shell")
    if any(marker in lowered for marker in ("save page now", "wm-ipp", "capture controls")):
        failures.append("archive_chrome_contamination")
    failures = list(dict.fromkeys(failures))
    language, language_basis, language_mismatch = _audit_content_language(
        content, parser.language
    )
    return HistoricalBlogSource(
        artifact_id=hashlib.sha256(card.original_canonical_url.encode()).hexdigest()[:24],
        original_canonical_url=card.original_canonical_url,
        archive_snapshot_url=page.final_url,
        archive_snapshot_at=snapshot_at,
        archive_replay_mode="raw_capture_id",
        official_catalog_url=card.catalog_url,
        official_catalog_link_observed_at=card.catalog_observed_at,
        official_catalog_title=card.article_title,
        official_catalog_category=card.category,
        official_catalog_publication_date=card.publication_date,
        publication_date_precision=card.publication_date_precision,
        normalized_title=title or card.article_title,
        language=language,
        html_language=parser.language,
        language_basis=language_basis,
        language_mismatch=language_mismatch,
        source_type="official_blog",
        source_channel="website",
        content_origin="historical_archive_snapshot",
        official_identity_basis="current_official_blog_index_link",
        content=content,
        content_hash=hashlib.sha256(content.encode()).hexdigest(),
        raw_snapshot_hash=hashlib.sha256(page.body).hexdigest(),
        acquisition_observed_at=_iso_timestamp(page.fetched_at),
        parser_version=ARCHIVE_PARSER_VERSION,
        provenance_relationship={
            "identity_evidence": "current_official_blog_index_article_card",
            "content_evidence": "official_index_linked_wayback_raw_capture",
            "original_identity": "original_blum_post_url",
            "publication_date_evidence": "current_official_blog_index",
            "snapshot_time_evidence": "wayback_snapshot_url",
        },
        validation_status="failed" if failures else "passed",
        validation_failures=failures,
    )


def assess_historical_frozen_m2_compatibility(
    sources: Sequence[HistoricalBlogSource],
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    blocker_counts: Counter[str] = Counter()
    for source in sources:
        blockers: list[str] = []
        if source.validation_status != "passed":
            blockers.append("acquisition_or_parser_validation_failed")
        if source.publication_date_precision != "datetime":
            blockers.append("date_only_publication_vs_precise_datetime")
        blockers.append("missing_confirmed_effective_from")
        blocker_counts.update(blockers)
        rows.append(
            {
                "artifact_id": source.artifact_id,
                "original_canonical_url": source.original_canonical_url,
                "honestly_importable": not blockers,
                "blockers": blockers,
            }
        )
    return {
        "source_count": len(sources),
        "honestly_importable_count": sum(row["honestly_importable"] for row in rows),
        "metadata_blocked_count": sum(not row["honestly_importable"] for row in rows),
        "blocker_counts": dict(sorted(blocker_counts.items())),
        "sources": rows,
    }


def unavailable_reason(
    *,
    requested_url: str,
    discovered_from: str,
    final_url: str,
    status_code: int,
    content_type: str,
    screening_reason: str | None,
) -> str:
    """Classify a failed fetch without treating an archive hint as authority."""
    archive_discovered_official = (
        archive_hint_to_official_url(discovered_from) == canonicalize_url(requested_url)
    )
    redirected_to_archive = (
        screening_reason == "external_origin"
        and urlsplit(canonicalize_url(final_url)).hostname == "web.archive.org"
    )
    if archive_discovered_official or redirected_to_archive:
        return "official_source_unavailable_archive_fallback_candidate"
    if discovered_from in {"archive_url_inventory_hint", "public_index_discovery_hint"}:
        return "official_source_unavailable"
    if screening_reason:
        return screening_reason
    if content_type != "text/html":
        return "non_html"
    if status_code != 200:
        return "http_failure"
    return "fetch_failure"


def load_discovery_hints(path: str | Path) -> list[str]:
    """Load official URLs from a local discovery-only inventory."""
    values = Path(path).expanduser().read_text(encoding="utf-8").splitlines()
    accepted: list[str] = []
    for value in values:
        url = canonicalize_url(value)
        parsed = urlsplit(url)
        if parsed.scheme not in {"http", "https"}:
            continue
        if parsed.hostname not in {"help.blum.io", "blum.io"}:
            continue
        accepted.append(url)
    return list(dict.fromkeys(accepted))


def audit_blog_index(body: bytes, url: str) -> dict[str, int]:
    text = body.decode("utf-8", errors="replace")
    cards = re.findall(
        r'<article\b[^>]*class="[^"]*\bblog-card\b[^"]*"[^>]*>(.*?)</article>',
        text,
        flags=re.I | re.S,
    )
    dates: list[str] = []
    links: list[str] = []
    for card in cards:
        dates.extend(
            re.sub(r"<[^>]+>", "", match).strip()
            for match in re.findall(r"<time\b[^>]*>(.*?)</time>", card, flags=re.I | re.S)
        )
        links.extend(
            urljoin(url, value)
            for value in re.findall(r'<a\b[^>]*href="([^"]+)"', card, flags=re.I)
        )
    same_origin = {
        canonicalize_url(link)
        for link in links
        if urlsplit(link).hostname == "blum.io"
        and urlsplit(canonicalize_url(link)).path.startswith("/post/")
    }
    archive = {
        canonicalize_url(link)
        for link in links
        if urlsplit(link).hostname == "web.archive.org" and "/https://blum.io/post/" in link
    }
    return {
        "listed_article_count": len(cards),
        "listed_publication_date_count": len(dates),
        "listed_2024_article_count": sum(value.endswith("2024") for value in dates),
        "same_origin_article_link_count": len(same_origin),
        "external_archive_article_link_count": len(archive),
    }


def _markdown_blocks(blocks: list[tuple[str, str]], title: str) -> str:
    rendered: list[str] = []
    title_seen = False
    for tag, text in blocks:
        if tag == "h1":
            if text.casefold() == title.casefold() and title_seen:
                continue
            prefix = "# "
            title_seen = text.casefold() == title.casefold()
        elif tag.startswith("h") and tag[1:].isdigit():
            prefix = "#" * min(6, int(tag[1:])) + " "
        elif tag == "li":
            prefix = "- "
        elif tag == "blockquote":
            prefix = "> "
        else:
            prefix = ""
        rendered.append(prefix + text)
    if not title_seen:
        rendered.insert(0, "# " + title)
    return "\n\n".join(dict.fromkeys(rendered)).strip()


def parse_html_page(body: bytes, url: str) -> ParsedPage:
    text = body.decode("utf-8", errors="replace")
    parser = _ContentParser(url)
    parser.feed(text)
    parser._flush_block()
    title = " ".join(parser.h1).strip() or " ".join(parser.head_title).strip()
    title = re.sub(r"\s+[|l]\s+Blum.*$", "", title, flags=re.I).strip()
    if not title:
        title = urlsplit(url).path.rstrip("/").rsplit("/", 1)[-1].replace("-", " ").title()
    published_raw = next(
        (
            parser.meta[key]
            for key in ("article:published_time", "datepublished", "date")
            if key in parser.meta
        ),
        None,
    )
    updated_raw = next(
        (
            parser.meta[key]
            for key in ("article:modified_time", "datemodified", "last-modified")
            if key in parser.meta
        ),
        None,
    )
    if not published_raw:
        published_raw = next(
            (value for value in parser.time_text if _normalize_time(value)[0]), None
        )
    published_at, published_precision = _normalize_time(published_raw)
    updated_at, updated_precision = _normalize_time(updated_raw)
    block_texts = [value for _, value in parser.blocks[:20]]
    category = next(
        (
            canonical
            for value in block_texts
            for key, canonical in _CATEGORY_VALUES.items()
            if value.casefold() == key or value.casefold().startswith(key + " ")
        ),
        None,
    )
    canonical = canonicalize_url(parser.canonical or url)
    return ParsedPage(
        title=title,
        canonical_url=canonical,
        language=parser.language,
        content=_markdown_blocks(parser.blocks, title),
        published_at=published_at,
        published_precision=published_precision,
        updated_at=updated_at,
        updated_precision=updated_precision,
        author=parser.meta.get("author"),
        category=category,
    )


def _source_type(parsed: ParsedPage) -> str:
    host = urlsplit(parsed.canonical_url).hostname
    haystack = f"{parsed.title}\n{parsed.content[:1000]}".casefold()
    if host == "help.blum.io":
        if "faq" in haystack or "frequently asked" in haystack:
            return "faq"
        if "maintenance" in haystack:
            return "maintenance_notice"
        if any(term in haystack for term in ("campaign rules", "eligibility", "prize pool")):
            return "campaign_rules"
        if any(term in haystack for term in ("community rules", "community guidelines")):
            return "community_rules"
        return "product_docs"
    category = (parsed.category or "").casefold()
    if category == "product":
        return "product_docs"
    if category == "new features":
        return "release_notes"
    if category == "campaigns":
        return "campaign_rules"
    return "official_blog"


def normalize_page(
    page: AcquiredPage, parsed: ParsedPage, *, source_channel: str
) -> NormalizedSource:
    content = parsed.content.replace("\r\n", "\n").strip()
    source_type = _source_type(parsed)
    host = urlsplit(parsed.canonical_url).hostname
    provenance = {
        "source_type": "system-derived",
        "source_channel": "human-confirmed",
        "language": "source-provided" if parsed.language != "unknown" else "system-derived",
        "authority_level": "human-confirmed",
        "official_status": "human-confirmed",
    }
    if parsed.published_at:
        provenance["published_at"] = "source-provided"
    if parsed.updated_at:
        provenance["updated_at"] = "source-provided"
    return NormalizedSource(
        artifact_id=hashlib.sha256(parsed.canonical_url.encode()).hexdigest()[:24],
        title=parsed.title,
        canonical_url=parsed.canonical_url,
        source_type=source_type,
        source_channel=source_channel,
        language=parsed.language,
        published_at=parsed.published_at,
        published_precision=parsed.published_precision,
        updated_at=parsed.updated_at,
        updated_precision=parsed.updated_precision,
        observed_at=_iso_timestamp(page.fetched_at),
        author=parsed.author,
        official_status="verified_official",
        content=content,
        content_hash=hashlib.sha256(content.encode()).hexdigest(),
        raw_hash=hashlib.sha256(page.body).hexdigest(),
        historical_coverage=(
            "partial" if host == "blum.io" and parsed.published_at else "unavailable"
        ),
        metadata_provenance=provenance,
        fetch_metadata={
            "requested_url": page.requested_url,
            "final_url": page.final_url,
            "http_status": page.status_code,
            "content_type": page.content_type,
            "fetched_at": _iso_timestamp(page.fetched_at),
            "etag": page.etag,
            "last_modified": page.last_modified,
        },
    )


def build_manifest(
    discovery: list[DiscoveryRecord],
    sources: list[NormalizedSource],
    *,
    generated_at: datetime,
    baseline_commit: str,
) -> dict[str, Any]:
    source_type_counts = Counter(source.source_type for source in sources)
    language_counts = Counter(source.language for source in sources)
    channel_counts = Counter(source.source_channel for source in sources)
    domain_counts = Counter({"help.blum.io": 0, "blum.io": 0})
    domain_counts.update(urlsplit(source.canonical_url).hostname or "unknown" for source in sources)
    historical_counts = Counter(source.historical_coverage for source in sources)
    hashes = Counter(source.content_hash for source in sources)
    provenance_counts: Counter[str] = Counter()
    for source in sources:
        provenance_counts.update(source.metadata_provenance.values())
    count = len(sources)
    source_records = [source.model_dump(exclude={"content"}, mode="json") for source in sources]
    discovery_records = [record.model_dump(mode="json") for record in discovery]
    official_blog_candidates = [
        record
        for record in discovery
        if record.domain == "blum.io" and urlsplit(record.canonical_url).path.startswith("/post/")
    ]
    help_official_candidates = [
        record
        for record in discovery
        if record.domain == "help.blum.io"
        and record.discovered_from
        in {"archive_url_inventory_hint", "public_index_discovery_hint"}
        and record.decision in {"included", "failed"}
    ]
    return {
        "version": "blum-knowledge-pack-v1",
        "manifest_schema_version": "1.0.0",
        "generated_at": _iso_timestamp(generated_at),
        "frozen_m2_baseline_commit": baseline_commit,
        "scope": ["https://help.blum.io", "https://blum.io/blog"],
        "summary": {
            "discovered_url_count": len({record.canonical_url for record in discovery}),
            "fetched_source_count": count,
            "domain_counts": dict(sorted(domain_counts.items())),
            "source_channel_counts": dict(sorted(channel_counts.items())),
            "source_type_counts": dict(sorted(source_type_counts.items())),
            "language_counts": dict(sorted(language_counts.items())),
            "published_at_count": sum(source.published_at is not None for source in sources),
            "published_at_ratio": (
                sum(source.published_at is not None for source in sources) / count if count else 0
            ),
            "updated_at_count": sum(source.updated_at is not None for source in sources),
            "updated_at_ratio": (
                sum(source.updated_at is not None for source in sources) / count if count else 0
            ),
            "content_hash_duplicate_count": sum(value - 1 for value in hashes.values()),
            "unknown_source_type_count": sum(source.source_type == "unknown" for source in sources),
            "fetch_failure_count": sum(record.fetch_status == "failed" for record in discovery),
            "official_blog_post_candidate_count": len(official_blog_candidates),
            "official_blog_post_recovered_count": sum(
                record.decision == "included" for record in official_blog_candidates
            ),
            "official_source_unavailable_count": sum(
                record.exclusion_reason == "official_source_unavailable_archive_fallback_candidate"
                for record in official_blog_candidates
            ),
            "help_official_url_candidate_count": len(help_official_candidates),
            "help_official_url_recovered_count": sum(
                record.decision == "included" for record in help_official_candidates
            ),
            "help_official_url_unavailable_count": sum(
                record.exclusion_reason == "official_source_unavailable"
                for record in help_official_candidates
            ),
            "archive_fallback_hint_count": sum(
                record.exclusion_reason == "archive_fallback_hint" for record in discovery
            ),
            "decision_counts": dict(
                sorted(Counter(record.decision for record in discovery).items())
            ),
            "exclusion_reason_counts": dict(
                sorted(
                    Counter(
                        record.exclusion_reason
                        for record in discovery
                        if record.exclusion_reason is not None
                    ).items()
                )
            ),
            "historical_coverage_counts": dict(sorted(historical_counts.items())),
            "metadata_provenance_counts": dict(sorted(provenance_counts.items())),
        },
        "discovery_inventory": discovery_records,
        "sources": source_records,
    }


def importable_source_input(source: NormalizedSource) -> SourceInput:
    if source.published_precision != "datetime" or not source.published_at:
        raise ValueError("Frozen M2 requires a precise source-provided published_at")
    if source.effective_precision != "datetime" or not source.effective_from:
        raise ValueError("Frozen M2 requires a precise source-provided effective_from")
    if source.metadata_provenance.get("validity") not in {
        "source-provided",
        "human-confirmed",
    }:
        raise ValueError("Frozen M2 requires confirmed effective validity provenance")

    def parse(value: str) -> datetime:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if result.tzinfo is None or result.utcoffset() is None:
            raise ValueError("Frozen M2 timestamps must be offset-aware")
        return result

    published = parse(source.published_at)
    effective = parse(source.effective_from)
    updated = parse(source.updated_at) if source.updated_precision == "datetime" else None
    observed = parse(source.observed_at)
    return SourceInput(
        title=source.title,
        source_type=source.source_type,
        source_channel=source.source_channel,
        content=source.content,
        canonical_url=source.canonical_url,
        author=source.author,
        language=source.language,
        project_scope="blum",
        authority_level="official",
        official_status=source.official_status,
        verification_method="human-confirmed official Blum origin",
        published_at=published,
        updated_at=updated,
        effective_from=effective,
        observed_at=observed,
        source_timezone="UTC"
        if published.utcoffset().total_seconds() == 0
        else str(published.tzinfo),
        status="unknown",
        metadata_provenance={
            "source_type": source.metadata_provenance["source_type"],
            "authority_level": source.metadata_provenance["authority_level"],
            "official_status": source.metadata_provenance["official_status"],
            "published_at": source.metadata_provenance["published_at"],
            "validity": source.metadata_provenance["validity"],
        },
        semantic_tags={},
    )


def import_sources_into_frozen_m2(
    sources: list[NormalizedSource],
    *,
    database_path: str | Path,
    artifact_root: str | Path,
    clock: Any | None = None,
) -> dict[str, Any]:
    foundation_arguments: dict[str, Any] = {
        "database_path": database_path,
        "artifact_root": Path(artifact_root).parent / "workspace-runs",
    }
    if clock is not None:
        foundation_arguments["clock"] = clock
    foundation = DataFoundationService(**foundation_arguments)
    workspace = foundation.create_workspace("Blum Hero Workspace")
    knowledge_arguments: dict[str, Any] = {
        "database": foundation.database,
        "artifact_root": artifact_root,
        "embedder": None,
        "answerer": None,
    }
    if clock is not None:
        knowledge_arguments["clock"] = clock
    service = KnowledgeService(**knowledge_arguments)
    imported: list[dict[str, Any]] = []
    blocked: list[dict[str, str]] = []
    for source in sources:
        try:
            adapted = importable_source_input(source)
        except ValueError as error:
            blocked.append(
                {
                    "artifact_id": source.artifact_id,
                    "canonical_url": source.canonical_url,
                    "category": "metadata",
                    "reason": str(error),
                }
            )
            continue
        result = service.add_source(workspace["workspace_id"], adapted)
        imported.append(
            {
                "artifact_id": source.artifact_id,
                "canonical_url": source.canonical_url,
                "source_id": result["source_id"],
                "revision_id": result["revision_id"],
            }
        )
    return {
        "workspace": workspace,
        "database_path": str(Path(database_path).expanduser().resolve()),
        "imported_count": len(imported),
        "blocked_count": len(blocked),
        "imported": imported,
        "blocked": blocked,
    }


class PoliteFetcher:
    def __init__(self, *, min_delay_seconds: float = 1.0, timeout_seconds: float = 30.0):
        if min_delay_seconds < 1.0:
            raise ValueError("minimum request delay is one second")
        self.min_delay_seconds = min_delay_seconds
        self._last_request_at: float | None = None
        self.client = httpx.Client(
            follow_redirects=False,
            timeout=timeout_seconds,
            headers={
                "User-Agent": USER_AGENT,
                "Accept": "text/html,application/xml,text/xml;q=0.9",
            },
        )

    def close(self) -> None:
        self.client.close()

    def fetch(self, url: str) -> AcquiredPage:
        requested_url = url
        response: httpx.Response | None = None
        for _ in range(6):
            if self._last_request_at is not None:
                remaining = self.min_delay_seconds - (time.monotonic() - self._last_request_at)
                if remaining > 0:
                    time.sleep(remaining)
            response = self.client.get(url)
            self._last_request_at = time.monotonic()
            if response.status_code not in {301, 302, 303, 307, 308}:
                break
            location = response.headers.get("location")
            if not location:
                break
            redirected = urljoin(url, location)
            if urlsplit(redirected).hostname != urlsplit(requested_url).hostname:
                url = redirected
                break
            url = redirected
        if response is None:
            raise RuntimeError("HTTP request did not produce a response")
        return AcquiredPage(
            requested_url=requested_url,
            final_url=url,
            status_code=response.status_code,
            content_type=response.headers.get("content-type", "").split(";", 1)[0].casefold(),
            body=response.content,
            fetched_at=datetime.now(tz=UTC),
            etag=response.headers.get("etag"),
            last_modified=response.headers.get("last-modified"),
        )


def fetch_with_transient_retry(
    fetcher: PoliteFetcher | Any,
    url: str,
    *,
    max_attempts: int = 2,
) -> AcquiredPage:
    if max_attempts < 1:
        raise ValueError("max_attempts must be positive")
    for attempt in range(max_attempts):
        try:
            return fetcher.fetch(url)
        except httpx.TransportError:
            if attempt + 1 == max_attempts:
                raise
    raise RuntimeError("unreachable retry state")


def _candidate_decision(url: str, target: AcquisitionTarget) -> tuple[bool, str | None]:
    allowed, reason = screen_url(url, target.domain)
    if not allowed:
        return allowed, reason
    path = urlsplit(canonicalize_url(url)).path.casefold()
    if target.domain == "blum.io":
        if path.startswith("/post/"):
            return True, None
        if path in {"/", "/blog", "/id", "/ko-kr", "/pt-br", "/ru", "/tr", "/zh"}:
            return False, "navigation_or_marketing"
        if path in {"/privacy-policy", "/terms-of-use"}:
            return False, "legal_page"
        return False, "not_blog_content"
    if path in {"", "/"}:
        return False, "navigation_or_marketing"
    if path.startswith("/.well-known/") or path in {
        "/ads.txt",
        "/app-ads.txt",
        "/atom.xml",
        "/feed",
        "/feed.xml",
        "/feeds/all.atom.xml",
        "/index.xml",
    }:
        return False, "metadata_or_feed"
    if "%e2%80%a6" in path or "…" in path:
        return False, "truncated_url"
    if re.search(r"\.(?:css|js|png|jpe?g|gif|svg|webp|woff2?|ico)$", path):
        return False, "asset"
    return True, None


def _robot_parser(robots_url: str, body: bytes) -> RobotFileParser:
    parser = RobotFileParser(robots_url)
    parser.parse(body.decode("utf-8", errors="replace").splitlines())
    return parser


def _record(
    *,
    url: str,
    target: AcquisitionTarget,
    discovered_from: str,
    discovered_at: datetime,
    decision: str,
    exclusion_reason: str | None = None,
    title: str | None = None,
    source_type: str = "unknown",
    language: str | None = None,
    fetch_status: str = "not_fetched",
    http_status: int | None = None,
) -> DiscoveryRecord:
    return DiscoveryRecord(
        canonical_url=canonicalize_url(url),
        domain=urlsplit(canonicalize_url(url)).hostname or "unknown",
        title=title,
        discovered_from=discovered_from,
        source_channel=target.source_channel,
        candidate_source_type=source_type,
        language=language,
        fetch_status=fetch_status,
        http_status=http_status,
        discovered_at=_iso_timestamp(discovered_at),
        decision=decision,
        exclusion_reason=exclusion_reason,
    )


def _write_private_source(root: Path, page: AcquiredPage, source: NormalizedSource) -> None:
    raw_path = root / "raw" / f"{source.artifact_id}.html"
    normalized_path = root / "normalized" / f"{source.artifact_id}.json"
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    normalized_path.parent.mkdir(parents=True, exist_ok=True)
    raw_path.write_bytes(page.body)
    normalized_path.write_text(source.model_dump_json(indent=2), encoding="utf-8")


def load_private_sources(root: str | Path) -> list[NormalizedSource]:
    private_root = Path(root).expanduser().resolve()
    manifest = json.loads((private_root / "manifest.json").read_text(encoding="utf-8"))
    sources: list[NormalizedSource] = []
    for record in manifest.get("sources", []):
        artifact_id = record["artifact_id"]
        normalized_path = private_root / "normalized" / f"{artifact_id}.json"
        raw_path = private_root / "raw" / f"{artifact_id}.html"
        source = NormalizedSource.model_validate_json(normalized_path.read_text(encoding="utf-8"))
        if hashlib.sha256(source.content.encode()).hexdigest() != source.content_hash:
            raise ValueError(f"normalized content hash mismatch: {artifact_id}")
        if hashlib.sha256(raw_path.read_bytes()).hexdigest() != source.raw_hash:
            raise ValueError(f"raw snapshot hash mismatch: {artifact_id}")
        if source.artifact_id != artifact_id:
            raise ValueError(f"artifact id mismatch: {artifact_id}")
        sources.append(source)
    return sources


def _write_historical_source(
    root: Path,
    page: AcquiredPage,
    source: HistoricalBlogSource,
) -> None:
    raw_path = root / "raw" / f"{source.artifact_id}.html"
    normalized_path = root / "normalized" / f"{source.artifact_id}.json"
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    normalized_path.parent.mkdir(parents=True, exist_ok=True)
    raw_path.write_bytes(page.body)
    normalized_path.write_text(source.model_dump_json(indent=2), encoding="utf-8")


def _historical_summary(
    cards: Sequence[BlogCatalogCard],
    selected: Sequence[BlogCatalogCard],
    sources: Sequence[HistoricalBlogSource],
    attempts: Sequence[dict[str, Any]],
) -> dict[str, Any]:
    archive_cards = [
        card for card in cards if card.target_kind == "official_index_linked_archive"
    ]
    live_cards = [card for card in cards if card.target_kind == "current_official"]
    overlap_cards = select_controlled_archive_cards(cards, limit=len(cards))
    passed = [source for source in sources if source.validation_status == "passed"]
    hashes = Counter(source.content_hash for source in passed)
    provenance_required = {
        "identity_evidence",
        "content_evidence",
        "original_identity",
        "publication_date_evidence",
        "snapshot_time_evidence",
    }
    return {
        "total_blog_catalog_articles": len(cards),
        "current_live_articles": len(live_cards),
        "official_index_linked_archive_articles": len(archive_cards),
        "blog_2024_articles": sum(card.publication_date.startswith("2024-") for card in cards),
        "cn_chat_overlap_articles": len(overlap_cards),
        "selected_archive_articles": len(selected),
        "successfully_acquired_archive_snapshots": len(passed),
        "failed_snapshots": len(selected) - len(passed),
        "language_distribution": dict(sorted(Counter(s.language for s in passed).items())),
        "html_language_distribution": dict(
            sorted(Counter(s.html_language for s in passed).items())
        ),
        "language_mismatch_count": sum(source.language_mismatch for source in passed),
        "category_distribution": dict(
            sorted(Counter(s.official_catalog_category for s in passed).items())
        ),
        "content_hash_duplicates": sum(value - 1 for value in hashes.values()),
        "publication_date_coverage_count": sum(bool(card.publication_date) for card in cards),
        "archive_snapshot_time_coverage_count": sum(
            source.archive_snapshot_at is not None for source in passed
        ),
        "original_canonical_url_coverage_count": sum(
            bool(card.original_canonical_url) for card in cards
        ),
        "parser_failure_count": sum(
            source.validation_status == "failed" for source in sources
        ),
        "provenance_incomplete_cases": sum(
            not provenance_required.issubset(source.provenance_relationship)
            or not source.archive_snapshot_at
            or not source.original_canonical_url
            for source in sources
        ),
        "failure_reason_counts": dict(
            sorted(
                Counter(
                    reason
                    for attempt in attempts
                    for reason in attempt.get("validation_failures", [])
                ).items()
            )
        ),
    }


def run_historical_blog_acquisition(
    output_root: str | Path,
    *,
    phase: str,
    min_delay_seconds: float = 1.0,
    fetcher: PoliteFetcher | Any | None = None,
    generated_at: datetime | None = None,
) -> dict[str, Any]:
    if phase not in {"controlled", "all"}:
        raise ValueError("historical Blog phase must be controlled or all")
    root = Path(output_root).expanduser().resolve() / "historical-blog"
    root.mkdir(parents=True, exist_ok=True)
    now = generated_at or datetime.now(tz=UTC)
    owned_fetcher = fetcher is None
    client = fetcher or PoliteFetcher(min_delay_seconds=min_delay_seconds)
    try:
        catalog_page = client.fetch("https://blum.io/blog/")
        if catalog_page.status_code != 200 or catalog_page.content_type != "text/html":
            raise RuntimeError("official Blum Blog catalog is unavailable")
        cards = parse_blog_catalog(
            catalog_page.body,
            catalog_url="https://blum.io/blog/",
            observed_at=catalog_page.fetched_at,
        )
        catalog_hash = hashlib.sha256(catalog_page.body).hexdigest()
        catalog_raw_path = root / "catalog" / f"blum-blog-{catalog_hash}.html"
        catalog_raw_path.parent.mkdir(parents=True, exist_ok=True)
        catalog_raw_path.write_bytes(catalog_page.body)
        (root / "catalog.json").write_text(
            json.dumps(
                {
                    "version": "blum-blog-catalog-v1",
                    "catalog_url": "https://blum.io/blog",
                    "catalog_observed_at": _iso_timestamp(catalog_page.fetched_at),
                    "catalog_raw_hash": catalog_hash,
                    "articles": [card.model_dump(mode="json") for card in cards],
                },
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        gate_path = root / "controlled-gate.json"
        if phase == "all":
            if not gate_path.exists():
                raise RuntimeError("controlled archive validation gate has not passed")
            gate = json.loads(gate_path.read_text(encoding="utf-8"))
            if gate.get("status") != "passed" or gate.get("catalog_raw_hash") != catalog_hash:
                raise RuntimeError("controlled archive gate is stale or failed")
            selected = [
                card
                for card in cards
                if card.target_kind == "official_index_linked_archive"
            ]
        else:
            selected = select_controlled_archive_cards(cards)

        sources: list[HistoricalBlogSource] = []
        attempts: list[dict[str, Any]] = []
        for card in selected:
            archive_request_url = wayback_raw_capture_url(card.read_article_url)
            try:
                page = fetch_with_transient_retry(client, archive_request_url)
            except httpx.HTTPError as error:
                attempts.append(
                    {
                        "original_canonical_url": card.original_canonical_url,
                        "catalog_read_article_url": card.read_article_url,
                        "archive_request_url": archive_request_url,
                        "fetch_status": "failed",
                        "validation_failures": [type(error).__name__],
                    }
                )
                continue
            source = normalize_historical_archive(page, card)
            _write_historical_source(root, page, source)
            sources.append(source)
            attempts.append(
                {
                    "artifact_id": source.artifact_id,
                    "original_canonical_url": card.original_canonical_url,
                    "catalog_read_article_url": card.read_article_url,
                    "archive_request_url": archive_request_url,
                    "archive_snapshot_url": source.archive_snapshot_url,
                    "http_status": page.status_code,
                    "fetch_status": "succeeded",
                    "validation_status": source.validation_status,
                    "validation_failures": source.validation_failures,
                }
            )
    finally:
        if owned_fetcher:
            client.close()

    summary = _historical_summary(cards, selected, sources, attempts)
    all_passed = bool(selected) and summary["failed_snapshots"] == 0
    controlled_gate = {
        "status": "passed" if phase == "controlled" and all_passed else "not_applicable",
        "catalog_raw_hash": catalog_hash,
        "selected_count": len(selected),
        "passed_count": summary["successfully_acquired_archive_snapshots"],
    }
    manifest = {
        "version": "blum-historical-blog-pack-v1",
        "phase": phase,
        "generated_at": _iso_timestamp(now),
        "frozen_m2_baseline_commit": BASELINE_COMMIT,
        "catalog": {
            "url": "https://blum.io/blog",
            "observed_at": _iso_timestamp(catalog_page.fetched_at),
            "raw_hash": catalog_hash,
        },
        "summary": summary,
        "controlled_gate": controlled_gate,
        "attempts": attempts,
        "sources": [source.model_dump(exclude={"content"}, mode="json") for source in sources],
    }
    manifest_path = root / f"manifest-{phase}.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    if phase == "controlled":
        gate_path.write_text(
            json.dumps(controlled_gate, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    return manifest


def run_acquisition(
    output_root: str | Path,
    *,
    min_delay_seconds: float = 1.0,
    fetcher: PoliteFetcher | None = None,
    generated_at: datetime | None = None,
    discovery_hints: Sequence[str] = (),
) -> dict[str, Any]:
    root = Path(output_root).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    now = generated_at or datetime.now(tz=UTC)
    owned_fetcher = fetcher is None
    client = fetcher or PoliteFetcher(min_delay_seconds=min_delay_seconds)
    records: dict[str, DiscoveryRecord] = {}
    sources: list[NormalizedSource] = []
    diagnostics: dict[str, Any] = {}
    duplicate_discovery_count = 0
    try:
        for target in TARGETS:
            target_diagnostics: dict[str, Any] = {
                "robots_url": target.origin + "/robots.txt",
                "robots_status": None,
                "sitemap_status": None,
                "navigation_status": None,
                "content_signals": [],
            }
            diagnostics[target.domain] = target_diagnostics
            try:
                robots_page = client.fetch(target.origin + "/robots.txt")
            except httpx.HTTPError as error:
                target_diagnostics["robots_error"] = type(error).__name__
                continue
            target_diagnostics["robots_status"] = robots_page.status_code
            target_diagnostics["robots_sha256"] = hashlib.sha256(robots_page.body).hexdigest()
            target_diagnostics["content_signals"] = list(
                dict.fromkeys(
                    line.split(":", 1)[1].strip()
                    for line in robots_page.body.decode("utf-8", errors="replace").splitlines()
                    if line.casefold().startswith("content-signal:")
                )
            )
            if robots_page.status_code != 200:
                target_diagnostics["crawl_status"] = "robots_unavailable"
                continue
            robots = _robot_parser(target.origin + "/robots.txt", robots_page.body)
            discovered: list[tuple[str, str]] = []
            discovered.extend(
                (url, "archive_url_inventory_hint")
                for url in discovery_hints
                if urlsplit(canonicalize_url(url)).hostname == target.domain
            )
            sitemap_queue = [target.sitemap_url]
            seen_sitemaps: set[str] = set()
            while sitemap_queue and len(seen_sitemaps) < 20:
                sitemap_url = sitemap_queue.pop(0)
                if sitemap_url in seen_sitemaps or not robots.can_fetch(USER_AGENT, sitemap_url):
                    continue
                seen_sitemaps.add(sitemap_url)
                try:
                    sitemap_page = client.fetch(sitemap_url)
                except httpx.HTTPError as error:
                    target_diagnostics.setdefault("sitemap_errors", []).append(type(error).__name__)
                    continue
                target_diagnostics["sitemap_status"] = sitemap_page.status_code
                if sitemap_page.status_code != 200:
                    target_diagnostics.setdefault("sitemap_http_failures", []).append(
                        {"url": sitemap_url, "status": sitemap_page.status_code}
                    )
                    continue
                try:
                    urls, child_sitemaps = parse_sitemap(sitemap_page.body)
                except (ElementTree.ParseError, ValueError):
                    target_diagnostics.setdefault("sitemap_parse_failures", []).append(sitemap_url)
                    continue
                discovered.extend((url, sitemap_url) for url in urls)
                sitemap_queue.extend(child_sitemaps)

            if robots.can_fetch(USER_AGENT, target.navigation_url):
                try:
                    navigation = client.fetch(target.navigation_url)
                except httpx.HTTPError as error:
                    target_diagnostics["navigation_error"] = type(error).__name__
                else:
                    target_diagnostics["navigation_status"] = navigation.status_code
                    if navigation.status_code == 200:
                        if target.domain == "blum.io":
                            target_diagnostics["blog_index_audit"] = audit_blog_index(
                                navigation.body, target.navigation_url
                            )
                        discovered.extend(
                            (url, target.navigation_url)
                            for url in extract_links(navigation.body, target.navigation_url)
                        )
                    else:
                        records[canonicalize_url(target.navigation_url)] = _record(
                            url=target.navigation_url,
                            target=target,
                            discovered_from="configured_official_navigation",
                            discovered_at=now,
                            decision="failed",
                            exclusion_reason="navigation_fetch_failed",
                            fetch_status="failed",
                            http_status=navigation.status_code,
                        )

            expanded_discovery: list[tuple[str, str]] = []
            for raw_url, discovered_from in discovered:
                expanded_discovery.append((raw_url, discovered_from))
                hint = archive_hint_to_official_url(raw_url)
                if hint:
                    expanded_discovery.append((hint, raw_url))

            for raw_url, discovered_from in expanded_discovery:
                url = canonicalize_url(raw_url)
                if url in records:
                    duplicate_discovery_count += 1
                    continue
                is_candidate, reason = _candidate_decision(url, target)
                if not is_candidate:
                    if archive_hint_to_official_url(url):
                        reason = "archive_fallback_hint"
                    records[url] = _record(
                        url=url,
                        target=target,
                        discovered_from=discovered_from,
                        discovered_at=now,
                        decision="excluded",
                        exclusion_reason=reason,
                    )
                    continue
                if not robots.can_fetch(USER_AGENT, url):
                    records[url] = _record(
                        url=url,
                        target=target,
                        discovered_from=discovered_from,
                        discovered_at=now,
                        decision="excluded",
                        exclusion_reason="robots_disallowed",
                    )
                    continue
                try:
                    page = client.fetch(url)
                except httpx.HTTPError as error:
                    records[url] = _record(
                        url=url,
                        target=target,
                        discovered_from=discovered_from,
                        discovered_at=now,
                        decision="failed",
                        exclusion_reason=type(error).__name__,
                        fetch_status="failed",
                    )
                    continue
                final_url = canonicalize_url(page.final_url)
                final_allowed, final_reason = screen_url(final_url, target.domain)
                if page.status_code != 200 or not final_allowed or page.content_type != "text/html":
                    records[url] = _record(
                        url=url,
                        target=target,
                        discovered_from=discovered_from,
                        discovered_at=now,
                        decision="failed",
                        exclusion_reason=unavailable_reason(
                            requested_url=url,
                            discovered_from=discovered_from,
                            final_url=final_url,
                            status_code=page.status_code,
                            content_type=page.content_type,
                            screening_reason=final_reason,
                        ),
                        fetch_status="failed",
                        http_status=page.status_code,
                    )
                    continue
                parsed = parse_html_page(page.body, final_url)
                if len(parsed.content) < 80:
                    records[url] = _record(
                        url=url,
                        target=target,
                        discovered_from=discovered_from,
                        discovered_at=now,
                        decision="excluded",
                        exclusion_reason="thin_or_shell_page",
                        fetch_status="succeeded",
                        http_status=page.status_code,
                        title=parsed.title,
                        language=parsed.language,
                    )
                    continue
                source = normalize_page(page, parsed, source_channel=target.source_channel)
                _write_private_source(root, page, source)
                sources.append(source)
                records[url] = _record(
                    url=source.canonical_url,
                    target=target,
                    discovered_from=discovered_from,
                    discovered_at=now,
                    decision="included",
                    fetch_status="succeeded",
                    http_status=page.status_code,
                    title=source.title,
                    source_type=source.source_type,
                    language=source.language,
                )
    finally:
        if owned_fetcher:
            client.close()

    manifest = build_manifest(
        list(records.values()), sources, generated_at=now, baseline_commit=BASELINE_COMMIT
    )
    manifest["acquisition"] = {
        "user_agent": USER_AGENT,
        "minimum_request_delay_seconds": min_delay_seconds,
        "diagnostics": diagnostics,
    }
    manifest["summary"]["url_duplicate_count"] = duplicate_discovery_count
    (root / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return manifest


def _cli_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="blum-knowledge-acquisition")
    commands = parser.add_subparsers(dest="command", required=True)
    acquire = commands.add_parser("acquire", help="discover and normalize approved Blum sources")
    acquire.add_argument("--output-root", required=True)
    acquire.add_argument("--min-delay-seconds", type=float, default=1.0)
    acquire.add_argument("--discovery-hints-file")
    historical = commands.add_parser(
        "historical-blog", help="acquire official-index-linked Blog archive snapshots"
    )
    historical.add_argument("--output-root", required=True)
    historical.add_argument("--phase", choices=("controlled", "all"), required=True)
    historical.add_argument("--min-delay-seconds", type=float, default=1.0)
    import_command = commands.add_parser("import", help="import compatible sources into Frozen M2")
    import_command.add_argument("--private-root", required=True)
    import_command.add_argument("--database", required=True)
    import_command.add_argument("--artifact-root", required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    arguments = _cli_parser().parse_args(argv)
    if arguments.command == "acquire":
        result = run_acquisition(
            arguments.output_root,
            min_delay_seconds=arguments.min_delay_seconds,
            discovery_hints=(
                load_discovery_hints(arguments.discovery_hints_file)
                if arguments.discovery_hints_file
                else ()
            ),
        )
        print(json.dumps(result["summary"], ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    if arguments.command == "historical-blog":
        result = run_historical_blog_acquisition(
            arguments.output_root,
            phase=arguments.phase,
            min_delay_seconds=arguments.min_delay_seconds,
        )
        print(json.dumps(result["summary"], ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    sources = load_private_sources(arguments.private_root)
    result = import_sources_into_frozen_m2(
        sources,
        database_path=arguments.database,
        artifact_root=arguments.artifact_root,
    )
    report_path = Path(arguments.private_root).expanduser().resolve() / "import-report.json"
    report_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
