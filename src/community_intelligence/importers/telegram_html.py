"""Telegram Desktop HTML adapter for a private canonical conversation dataset.

The adapter intentionally stops at structural normalization. It does not classify,
filter, summarize, OCR, transcribe, or otherwise interpret conversation content.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from collections import Counter, defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from community_intelligence.importers.telegram import _digest
from community_intelligence.io import (
    cleanup_private_directory,
    data_artifact_contents,
    publication_metadata,
    publish_directory_no_replace,
    write_dataset,
)
from community_intelligence.models import CommunityDataset, DatasetManifest, MessageRecord

PARSER_VERSION = "telegram_desktop_html_v1.0.0"
SCHEMA_VERSION = "1.0.0"
SOURCE_FORMAT = "telegram_desktop_html"
_MESSAGE_ID = re.compile(r"message(?P<id>\d+)\Z")
_REPLY_HREF = re.compile(r"#go_to_message(?P<id>\d+)\Z")
_HTML_PAGE = re.compile(r"messages(?P<number>\d*)\.html\Z")
_VOID_ELEMENTS = frozenset(
    {
        "area",
        "base",
        "br",
        "col",
        "embed",
        "hr",
        "img",
        "input",
        "link",
        "meta",
        "source",
        "track",
        "wbr",
    }
)


@dataclass
class _Node:
    tag: str
    attrs: dict[str, str | None]
    children: list[_Node | str] = field(default_factory=list)

    @property
    def classes(self) -> frozenset[str]:
        return frozenset((self.attrs.get("class") or "").split())


@dataclass
class _RawBlock:
    node: _Node
    fragment: str
    start_offset: int
    end_offset: int
    start_line: int


class _TelegramDocumentParser(HTMLParser):
    """Capture exact top-level Telegram message fragments and their small subtrees."""

    def __init__(self, source: str) -> None:
        super().__init__(convert_charrefs=True)
        self.source = source
        self._line_offsets: list[int] = []
        offset = 0
        for line in source.splitlines(keepends=True):
            self._line_offsets.append(offset)
            offset += len(line)
        self._stack: list[_Node] = []
        self._root: _Node | None = None
        self._start_offset: int | None = None
        self._start_line: int | None = None
        self.blocks: list[_RawBlock] = []
        self.incomplete_fragment: tuple[int, int] | None = None

    def _offset(self) -> int:
        line, column = self.getpos()
        return self._line_offsets[line - 1] + column

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        classes = frozenset((attributes.get("class") or "").split())
        if self._root is None:
            if tag == "div" and "message" in classes:
                self._root = _Node(tag, attributes)
                self._stack = [self._root]
                self._start_offset = self._offset()
                self._start_line = self.getpos()[0]
            return
        child = _Node(tag, attributes)
        self._stack[-1].children.append(child)
        if tag not in _VOID_ELEMENTS:
            self._stack.append(child)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if self._root is not None:
            self._stack[-1].children.append(_Node(tag, dict(attrs)))

    def handle_data(self, data: str) -> None:
        if self._root is not None:
            self._stack[-1].children.append(data)

    def handle_endtag(self, tag: str) -> None:
        if self._root is None:
            return
        if len(self._stack) == 1 and tag == self._root.tag:
            end_offset = self._offset() + len(f"</{tag}>")
            assert self._start_offset is not None
            assert self._start_line is not None
            self.blocks.append(
                _RawBlock(
                    node=self._root,
                    fragment=self.source[self._start_offset : end_offset],
                    start_offset=self._start_offset,
                    end_offset=end_offset,
                    start_line=self._start_line,
                )
            )
            self._root = None
            self._stack = []
            self._start_offset = None
            self._start_line = None
            return
        for index in range(len(self._stack) - 1, 0, -1):
            if self._stack[index].tag == tag:
                del self._stack[index:]
                return

    def close(self) -> None:
        super().close()
        if self._root is not None and self._start_offset is not None:
            self.incomplete_fragment = (self._start_offset, len(self.source))


@dataclass
class _Occurrence:
    snapshot_label: str
    snapshot_root: Path
    source_html_file: str
    source_ordinal: int
    start_line: int
    start_offset: int
    end_offset: int
    raw_html_sha256: str
    source_message_id: str | None
    record_type: str
    joined: bool
    timestamp: str | None
    timestamp_source: dict[str, str] | None
    author_identity: dict[str, str | None] | None
    author_key: str | None
    text_original: str
    links: list[dict[str, str]]
    reply_to_message_id: str | None
    forwarded_from: str | None
    media: list[dict[str, Any]]
    service_text: str

    def provenance(self, *, selected: bool) -> dict[str, Any]:
        return {
            "end_offset": self.end_offset,
            "raw_html_sha256": self.raw_html_sha256,
            "selected": selected,
            "snapshot": self.snapshot_label,
            "source_html_file": self.source_html_file,
            "source_ordinal": self.source_ordinal,
            "start_line": self.start_line,
            "start_offset": self.start_offset,
        }


@dataclass
class _Snapshot:
    label: str
    root: Path
    html_files: list[dict[str, Any]]
    occurrences: list[_Occurrence]
    id_set: frozenset[str]
    malformed: list[dict[str, Any]]


def _nodes(root: _Node) -> Iterable[_Node]:
    yield root
    for child in root.children:
        if isinstance(child, _Node):
            yield from _nodes(child)


def _first_by_class(root: _Node, class_name: str) -> _Node | None:
    return next((node for node in _nodes(root) if class_name in node.classes), None)


def _text_content(root: _Node | None) -> str:
    if root is None:
        return ""
    fragments: list[str] = []

    def walk(node: _Node) -> None:
        for child in node.children:
            if isinstance(child, str):
                fragments.append(child)
            elif child.tag == "br":
                fragments.append("\n")
            else:
                walk(child)

    walk(root)
    return "".join(fragments).strip()


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_json(value: object) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return _sha256_bytes(encoded)


def _page_number(path: Path) -> int:
    match = _HTML_PAGE.fullmatch(path.name)
    if match is None:
        raise ValueError(f"not a Telegram HTML message page: {path.name}")
    return int(match.group("number") or "1")


def _timestamp(
    title: str | None,
    *,
    timezone: ZoneInfo,
    timezone_name: str,
    timezone_provenance: str,
) -> tuple[str | None, dict[str, str] | None]:
    if not title:
        return None, None
    try:
        local = datetime.strptime(title, "%d %B %Y, %H:%M:%S")
    except ValueError:
        return None, {
            "local_value": "",
            "raw_title": title,
            "source_timezone": timezone_name,
            "timezone_provenance": timezone_provenance,
        }
    aware = local.replace(tzinfo=timezone)
    utc_value = aware.astimezone(UTC).isoformat().replace("+00:00", "Z")
    return (
        utc_value,
        {
            "local_value": local.isoformat(),
            "raw_title": title,
            "source_timezone": timezone_name,
            "timezone_provenance": timezone_provenance,
        },
    )


def _utc_json(value: datetime | None) -> str | None:
    return value.isoformat().replace("+00:00", "Z") if value is not None else None


def _author(
    root: _Node,
    *,
    joined: bool,
    source_message_id: str | None,
    occurrence_key: str,
    previous: tuple[dict[str, str | None], str] | None,
) -> tuple[dict[str, str | None], str]:
    author_node = _first_by_class(root, "from_name")
    display_name = _text_content(author_node) or None
    if joined and display_name is None and previous is not None:
        inherited, author_key = previous
        return (
            {
                "anchor_source_message_id": inherited["anchor_source_message_id"],
                "display_name": inherited["display_name"],
                "resolution": "joined_inheritance",
                "status": inherited["status"],
            },
            author_key,
        )
    anchor = source_message_id or occurrence_key
    if display_name == "Deleted Account":
        return (
            {
                "anchor_source_message_id": anchor,
                "display_name": display_name,
                "resolution": "explicit_from_name",
                "status": "deleted_account",
            },
            f"deleted-account:{anchor}",
        )
    if display_name is not None:
        return (
            {
                "anchor_source_message_id": anchor,
                "display_name": display_name,
                "resolution": "explicit_from_name",
                "status": "available",
            },
            f"display-name:{display_name}",
        )
    resolution = "joined_inheritance_failed" if joined else "missing_from_name"
    return (
        {
            "anchor_source_message_id": anchor,
            "display_name": None,
            "resolution": resolution,
            "status": "missing",
        },
        f"missing-author:{anchor}",
    )


def _links(root: _Node | None) -> list[dict[str, str]]:
    if root is None:
        return []
    return [
        {"href": href, "text": _text_content(node)}
        for node in _nodes(root)
        if node.tag == "a" and (href := node.attrs.get("href")) is not None
    ]


def _media(root: _Node) -> list[dict[str, Any]]:
    media: list[dict[str, Any]] = []
    for node in _nodes(root):
        classes = node.classes
        kind: str | None = None
        if "photo_wrap" in classes:
            kind = "photo"
        elif "sticker_wrap" in classes:
            kind = "sticker"
        elif "animated_wrap" in classes:
            kind = "gif"
        elif "video_file_wrap" in classes:
            kind = "video_file"
        elif "media_location" in classes:
            kind = "location"
        elif "media_photo" in classes:
            kind = "embedded_photo"
        elif "media_video" in classes:
            kind = "embedded_video"
        if kind is None:
            continue
        href = node.attrs.get("href")
        image = next((child for child in _nodes(node) if child.tag == "img"), None)
        source = image.attrs.get("src") if image is not None else None
        local_path = href if href and not _is_external_reference(href) else None
        thumbnail_path = source if source and not _is_external_reference(source) else None
        if thumbnail_path == local_path:
            thumbnail_path = None
        media.append(
            {
                "href": href,
                "kind": kind,
                "local_path": local_path,
                "status_text": _text_content(_first_by_class(node, "status")) or None,
                "thumbnail_path": thumbnail_path,
            }
        )
    return media


def _is_external_reference(value: str) -> bool:
    return value.startswith(("http://", "https://", "mailto:", "#"))


def _reply_target(root: _Node) -> tuple[str | None, bool]:
    reply = _first_by_class(root, "reply_to")
    if reply is None:
        return None, False
    for node in _nodes(reply):
        if node.tag != "a":
            continue
        match = _REPLY_HREF.fullmatch(node.attrs.get("href") or "")
        if match is not None:
            return match.group("id"), False
    return None, True


def _quarantine(occurrence: _Occurrence, reason: str, **extra: Any) -> dict[str, Any]:
    return {
        "raw_html_sha256": occurrence.raw_html_sha256,
        "reason": reason,
        "source_html_file": occurrence.source_html_file,
        "source_message_id": occurrence.source_message_id,
        "source_ordinal": occurrence.source_ordinal,
        **extra,
    }


def _parse_snapshot(
    root: Path,
    *,
    source_parent: Path,
    timezone: ZoneInfo,
    timezone_name: str,
    timezone_provenance: str,
) -> _Snapshot:
    pages = sorted(root.glob("messages*.html"), key=_page_number)
    if not pages:
        raise ValueError(f"Telegram HTML export has no messages*.html: {root}")
    label = root.relative_to(source_parent).as_posix()
    occurrences: list[_Occurrence] = []
    html_files: list[dict[str, Any]] = []
    malformed: list[dict[str, Any]] = []
    previous_author: tuple[dict[str, str | None], str] | None = None
    for page in pages:
        raw_bytes = page.read_bytes()
        try:
            source = raw_bytes.decode("utf-8-sig")
        except UnicodeDecodeError as error:
            raise ValueError(f"Telegram HTML page must be UTF-8: {page}") from error
        parser = _TelegramDocumentParser(source)
        parser.feed(source)
        parser.close()
        source_file = page.relative_to(source_parent).as_posix()
        html_files.append(
            {
                "bytes": len(raw_bytes),
                "sha256": _sha256_bytes(raw_bytes),
                "source_html_file": source_file,
            }
        )
        if parser.incomplete_fragment is not None:
            start, end = parser.incomplete_fragment
            malformed.append(
                {
                    "end_offset": end,
                    "raw_html_sha256": _sha256_bytes(source[start:end].encode("utf-8")),
                    "reason": "incomplete_message_fragment",
                    "source_html_file": source_file,
                    "start_offset": start,
                }
            )
        for ordinal, block in enumerate(parser.blocks, start=1):
            classes = block.node.classes
            record_type = "service" if "service" in classes else "ordinary"
            raw_id = block.node.attrs.get("id")
            id_match = _MESSAGE_ID.fullmatch(raw_id or "")
            source_message_id = id_match.group("id") if id_match is not None else None
            occurrence_key = f"{source_file}:{ordinal}"
            joined = "joined" in classes
            date_node = _first_by_class(block.node, "date")
            timestamp, timestamp_source = _timestamp(
                date_node.attrs.get("title") if date_node is not None else None,
                timezone=timezone,
                timezone_name=timezone_name,
                timezone_provenance=timezone_provenance,
            )
            author_identity: dict[str, str | None] | None = None
            author_key: str | None = None
            if record_type == "ordinary":
                author_identity, author_key = _author(
                    block.node,
                    joined=joined,
                    source_message_id=source_message_id,
                    occurrence_key=occurrence_key,
                    previous=previous_author,
                )
                if author_identity["status"] != "missing":
                    previous_author = (author_identity, author_key)
                elif not joined:
                    previous_author = None
            text_node = _first_by_class(block.node, "text") if record_type == "ordinary" else None
            reply_to, malformed_reply = _reply_target(block.node)
            forwarded = _first_by_class(block.node, "forwarded_from")
            service_body = _first_by_class(block.node, "body")
            occurrence = _Occurrence(
                snapshot_label=label,
                snapshot_root=root,
                source_html_file=source_file,
                source_ordinal=ordinal,
                start_line=block.start_line,
                start_offset=block.start_offset,
                end_offset=block.end_offset,
                raw_html_sha256=_sha256_bytes(block.fragment.encode("utf-8")),
                source_message_id=source_message_id,
                record_type=record_type,
                joined=joined,
                timestamp=timestamp,
                timestamp_source=timestamp_source,
                author_identity=author_identity,
                author_key=author_key,
                text_original=_text_content(text_node),
                links=_links(text_node),
                reply_to_message_id=reply_to,
                forwarded_from=_text_content(forwarded) or None,
                media=_media(block.node) if record_type == "ordinary" else [],
                service_text=_text_content(service_body) if record_type == "service" else "",
            )
            occurrences.append(occurrence)
            if record_type == "ordinary" and source_message_id is None:
                malformed.append(_quarantine(occurrence, "missing_source_message_id"))
            if record_type == "ordinary" and timestamp is None:
                malformed.append(_quarantine(occurrence, "missing_or_malformed_timestamp"))
            if record_type == "ordinary" and author_identity is not None:
                if author_identity["resolution"] == "joined_inheritance_failed":
                    malformed.append(_quarantine(occurrence, "joined_author_inheritance_failed"))
                elif author_identity["status"] == "missing":
                    malformed.append(_quarantine(occurrence, "missing_author"))
            if malformed_reply:
                malformed.append(_quarantine(occurrence, "malformed_reply_reference"))
    return _Snapshot(
        label=label,
        root=root,
        html_files=html_files,
        occurrences=occurrences,
        id_set=frozenset(
            occurrence.source_message_id
            for occurrence in occurrences
            if occurrence.source_message_id is not None
        ),
        malformed=malformed,
    )


def _semantic_signature(occurrence: _Occurrence) -> str:
    return _sha256_json(
        {
            "author_key": occurrence.author_key,
            "forwarded_from": occurrence.forwarded_from,
            "joined": occurrence.joined,
            "links": occurrence.links,
            "media": occurrence.media,
            "record_type": occurrence.record_type,
            "reply_to_message_id": occurrence.reply_to_message_id,
            "service_text": occurrence.service_text,
            "text_original": occurrence.text_original,
            "timestamp": occurrence.timestamp,
        }
    )


def _no_id_service_key(occurrence: _Occurrence) -> str:
    try:
        date_value = datetime.strptime(occurrence.service_text, "%d %B %Y").date().isoformat()
    except ValueError:
        return f"occurrence:{occurrence.source_html_file}:{occurrence.source_ordinal}"
    return f"date-divider:{date_value}"


def _maximal_snapshots(snapshots: Sequence[_Snapshot]) -> list[_Snapshot]:
    return [
        snapshot
        for snapshot in snapshots
        if not any(snapshot.id_set < other.id_set for other in snapshots if other is not snapshot)
    ]


def _select_occurrence(
    occurrences: Sequence[_Occurrence], maximal_labels: frozenset[str]
) -> _Occurrence:
    candidates = [item for item in occurrences if item.snapshot_label in maximal_labels]
    if not candidates:
        candidates = list(occurrences)
    return sorted(
        candidates,
        key=lambda item: (
            item.snapshot_label,
            _page_number(Path(item.source_html_file)),
            item.source_ordinal,
        ),
    )[0]


def _source_id_value(source_message_id: str) -> int | str:
    return int(source_message_id) if source_message_id.isdigit() else source_message_id


def _message_sort_key(occurrence: _Occurrence) -> tuple[int, int | str, str, int]:
    source_id = occurrence.source_message_id
    if source_id is not None and source_id.isdigit():
        return (0, int(source_id), occurrence.source_html_file, occurrence.source_ordinal)
    return (1, source_id or "", occurrence.source_html_file, occurrence.source_ordinal)


def _inventory(roots: Sequence[Path], source_parent: Path) -> tuple[list[dict[str, Any]], str]:
    root_records: list[dict[str, Any]] = []
    fingerprint_items: list[dict[str, Any]] = []
    for root in roots:
        file_count = 0
        total_bytes = 0
        for path in sorted(root.rglob("*")):
            if path.is_symlink():
                raise ValueError(f"source export must not contain symlinks: {path}")
            if not path.is_file():
                continue
            content = path.read_bytes()
            record = {
                "bytes": len(content),
                "path": path.relative_to(source_parent).as_posix(),
                "sha256": _sha256_bytes(content),
            }
            fingerprint_items.append(record)
            file_count += 1
            total_bytes += len(content)
        root_records.append(
            {
                "bytes": total_bytes,
                "file_count": file_count,
                "snapshot": root.relative_to(source_parent).as_posix(),
            }
        )
    return root_records, _sha256_json(fingerprint_items)


def _resolve_local_media(
    item: dict[str, Any],
    *,
    occurrence: _Occurrence,
    media_id: str,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    quarantine: list[dict[str, Any]] = []
    resolved = {
        "bytes": None,
        "exists": False,
        "href": item["href"],
        "kind": item["kind"],
        "local_path": item["local_path"],
        "media_id": media_id,
        "sha256": None,
        "source_html_file": occurrence.source_html_file,
        "source_message_id": occurrence.source_message_id,
        "status_text": item["status_text"],
        "thumbnail_bytes": None,
        "thumbnail_exists": False,
        "thumbnail_path": item["thumbnail_path"],
        "thumbnail_sha256": None,
    }
    for path_field, exists_field, bytes_field, hash_field in (
        ("local_path", "exists", "bytes", "sha256"),
        ("thumbnail_path", "thumbnail_exists", "thumbnail_bytes", "thumbnail_sha256"),
    ):
        relative = item[path_field]
        if relative is None:
            continue
        candidate = occurrence.snapshot_root / relative
        try:
            source_root = occurrence.snapshot_root.resolve(strict=True)
            real = candidate.resolve(strict=True)
            real.relative_to(source_root)
        except (FileNotFoundError, ValueError):
            reason = "missing_media_file" if not candidate.exists() else "unsafe_media_path"
            quarantine.append(
                _quarantine(occurrence, reason, media_id=media_id, media_path=relative)
            )
            continue
        if not real.is_file():
            quarantine.append(
                _quarantine(
                    occurrence,
                    "media_reference_is_not_regular_file",
                    media_id=media_id,
                    media_path=relative,
                )
            )
            continue
        content = real.read_bytes()
        resolved[exists_field] = True
        resolved[bytes_field] = len(content)
        resolved[hash_field] = _sha256_bytes(content)
    return resolved, quarantine


def _canonical_media_variants(
    occurrences: Sequence[_Occurrence],
    *,
    selected_occurrence: _Occurrence,
    message_id: str,
) -> tuple[list[str], list[dict[str, Any]], list[dict[str, Any]]]:
    by_signature: dict[str, list[tuple[_Occurrence, dict[str, Any]]]] = defaultdict(list)
    for occurrence in occurrences:
        for item in occurrence.media:
            by_signature[_sha256_json(item)].append((occurrence, item))
    media_ids: list[str] = []
    media_records: list[dict[str, Any]] = []
    quarantine: list[dict[str, Any]] = []
    for signature, candidates in sorted(by_signature.items()):
        media_id = _digest(
            "media_",
            {"message_id": message_id, "variant": signature},
            length=24,
        )
        resolved_candidates: list[tuple[int, bool, dict[str, Any], list[dict[str, Any]]]] = []
        for occurrence, item in candidates:
            record, issues = _resolve_local_media(
                item,
                occurrence=occurrence,
                media_id=media_id,
            )
            score = int(record["exists"]) + int(record["thumbnail_exists"])
            resolved_candidates.append((score, occurrence is selected_occurrence, record, issues))
        _, _, selected_record, selected_issues = max(
            resolved_candidates,
            key=lambda candidate: (candidate[0], candidate[1]),
        )
        selected_record["source_occurrences"] = [
            {
                "selected_message_occurrence": occurrence is selected_occurrence,
                "snapshot": occurrence.snapshot_label,
                "source_html_file": occurrence.source_html_file,
                "source_ordinal": occurrence.source_ordinal,
            }
            for occurrence, _ in sorted(
                candidates,
                key=lambda candidate: (
                    candidate[0].source_html_file,
                    candidate[0].source_ordinal,
                ),
            )
        ]
        media_ids.append(media_id)
        media_records.append(selected_record)
        quarantine.extend(selected_issues)
    return media_ids, media_records, quarantine


def _write_jsonl(path: Path, records: Sequence[dict[str, Any]]) -> None:
    content = "".join(
        json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
        for record in records
    )
    path.write_text(content, encoding="utf-8", newline="\n")


def _artifact_hashes(directory: Path, names: Sequence[str]) -> dict[str, str]:
    return {name: _sha256_bytes((directory / name).read_bytes()) for name in names}


def canonicalize_telegram_html_exports(
    input_roots: Sequence[str | Path],
    output_dir: str | Path,
    *,
    community_id: str,
    language: str,
    source_timezone: str,
    timezone_provenance: str,
    identity_salt: str,
) -> Path:
    """Create a create-only private dataset from one or more HTML export snapshots."""

    if not input_roots:
        raise ValueError("at least one Telegram HTML export root is required")
    required_values = (community_id, language, source_timezone, timezone_provenance)
    if not all(value.strip() for value in required_values):
        raise ValueError("community, language, timezone, and timezone provenance must be non-empty")
    if not identity_salt:
        raise ValueError("identity salt must be non-empty")
    try:
        timezone = ZoneInfo(source_timezone)
    except ZoneInfoNotFoundError as error:
        raise ValueError(f"unknown source timezone: {source_timezone}") from error

    roots = sorted(Path(value).expanduser().resolve(strict=True) for value in input_roots)
    if len(roots) != len(set(roots)):
        raise ValueError("Telegram HTML export roots must be unique")
    if any(not root.is_dir() for root in roots):
        raise ValueError("each Telegram HTML export root must be a directory")
    destination = Path(os.path.abspath(Path(output_dir).expanduser()))
    for root in roots:
        try:
            destination.relative_to(root)
        except ValueError:
            continue
        raise ValueError("canonical output must be outside source export roots")
    source_parent = Path(os.path.commonpath([str(root.parent) for root in roots])).resolve(
        strict=True
    )
    snapshots = [
        _parse_snapshot(
            root,
            source_parent=source_parent,
            timezone=timezone,
            timezone_name=source_timezone,
            timezone_provenance=timezone_provenance,
        )
        for root in roots
    ]
    maximal = _maximal_snapshots(snapshots)
    maximal_labels = frozenset(snapshot.label for snapshot in maximal)
    all_by_id: dict[str, list[_Occurrence]] = defaultdict(list)
    missing_id_ordinary: list[_Occurrence] = []
    no_id_services_by_key: dict[str, list[_Occurrence]] = defaultdict(list)
    for snapshot in snapshots:
        for occurrence in snapshot.occurrences:
            if occurrence.source_message_id is not None:
                all_by_id[occurrence.source_message_id].append(occurrence)
            elif occurrence.record_type == "ordinary" and snapshot.label in maximal_labels:
                missing_id_ordinary.append(occurrence)
            elif occurrence.record_type == "service":
                no_id_services_by_key[_no_id_service_key(occurrence)].append(occurrence)

    selected_by_id = {
        source_id: _select_occurrence(occurrences, maximal_labels)
        for source_id, occurrences in all_by_id.items()
    }
    selected_ordinary = sorted(
        [item for item in selected_by_id.values() if item.record_type == "ordinary"]
        + missing_id_ordinary,
        key=_message_sort_key,
    )
    selected_services = sorted(
        [item for item in selected_by_id.values() if item.record_type == "service"]
        + [
            _select_occurrence(occurrences, maximal_labels)
            for occurrences in no_id_services_by_key.values()
        ],
        key=_message_sort_key,
    )

    quarantine = [item for snapshot in snapshots for item in snapshot.malformed]
    duplicate_groups = {key: value for key, value in all_by_id.items() if len(value) > 1}
    conflicting_ids: list[str] = []
    for source_id, occurrences in sorted(
        duplicate_groups.items(), key=lambda item: _source_id_value(item[0])
    ):
        selected = selected_by_id[source_id]
        signatures = {_semantic_signature(item) for item in occurrences}
        if len(signatures) > 1:
            conflicting_ids.append(source_id)
            quarantine.append(
                {
                    "occurrence_hashes": sorted(item.raw_html_sha256 for item in occurrences),
                    "reason": "conflicting_duplicate_source_message_id",
                    "selected_source_html_file": selected.source_html_file,
                    "selected_source_ordinal": selected.source_ordinal,
                    "source_message_id": source_id,
                }
            )
        snapshots_for_id = Counter(item.snapshot_label for item in occurrences)
        if any(count > 1 for count in snapshots_for_id.values()):
            quarantine.append(
                {
                    "reason": "duplicate_source_message_id_within_snapshot",
                    "snapshots": sorted(
                        label for label, count in snapshots_for_id.items() if count > 1
                    ),
                    "source_message_id": source_id,
                }
            )

    canonical_ids = {
        item.source_message_id: _digest(
            "tg_",
            {"community": community_id, "message": _source_id_value(item.source_message_id)},
            length=24,
        )
        for item in selected_ordinary
        if item.source_message_id is not None
    }
    messages: list[dict[str, Any]] = []
    media_records: list[dict[str, Any]] = []
    for canonical_ordinal, occurrence in enumerate(selected_ordinary, start=1):
        source_id = occurrence.source_message_id
        message_id = canonical_ids.get(source_id)
        if message_id is None:
            message_id = _digest(
                "tg_",
                {
                    "community": community_id,
                    "occurrence": occurrence.source_html_file,
                    "ordinal": occurrence.source_ordinal,
                },
                length=24,
            )
        assert occurrence.author_identity is not None
        assert occurrence.author_key is not None
        anonymized_author_id = _digest(
            "usr_",
            {
                "community": community_id,
                "salt": identity_salt,
                "sender": occurrence.author_key,
            },
        )
        occurrence_group = all_by_id.get(source_id, [occurrence])
        media_ids, message_media, media_quarantine = _canonical_media_variants(
            occurrence_group,
            selected_occurrence=occurrence,
            message_id=message_id,
        )
        media_records.extend(message_media)
        quarantine.extend(media_quarantine)
        reply_to_source_id = occurrence.reply_to_message_id
        reply_to_canonical_id = canonical_ids.get(reply_to_source_id)
        content_payload = {
            "author_key": occurrence.author_key,
            "forwarded_from": occurrence.forwarded_from,
            "links": occurrence.links,
            "media_refs": media_ids,
            "reply_to_message_id": reply_to_source_id,
            "source_message_id": source_id,
            "text_original": occurrence.text_original,
            "timestamp": occurrence.timestamp,
        }
        messages.append(
            {
                "anonymized_author_id": anonymized_author_id,
                "author_identity": occurrence.author_identity,
                "canonical_ordinal": canonical_ordinal,
                "community_id": community_id,
                "community_source_identity": {
                    "identity_basis": "operator_supplied_community_id",
                    "source_platform": "telegram",
                },
                "content_hash": _sha256_json(content_payload),
                "forwarded_from": occurrence.forwarded_from,
                "language": language,
                "links": occurrence.links,
                "media_refs": media_ids,
                "message_id": message_id,
                "parser_version": PARSER_VERSION,
                "raw_content_hash": occurrence.raw_html_sha256,
                "reply_to_canonical_message_id": reply_to_canonical_id,
                "reply_to_message_id": reply_to_source_id,
                "source_html_file": occurrence.source_html_file,
                "source_message_id": source_id,
                "source_occurrences": [
                    item.provenance(selected=item is occurrence)
                    for item in sorted(
                        occurrence_group,
                        key=lambda value: (value.source_html_file, value.source_ordinal),
                    )
                ],
                "source_ordinal": occurrence.source_ordinal,
                "source_platform": "telegram",
                "text_original": occurrence.text_original,
                "timestamp": occurrence.timestamp,
                "timestamp_source": occurrence.timestamp_source,
            }
        )

    services: list[dict[str, Any]] = []
    for ordinal, occurrence in enumerate(selected_services, start=1):
        source_id = occurrence.source_message_id
        no_id_service_key = _no_id_service_key(occurrence) if source_id is None else None
        occurrence_group = (
            all_by_id[source_id]
            if source_id is not None
            else no_id_services_by_key[no_id_service_key]
        )
        service_id = _digest(
            "tg_service_",
            {
                "community": community_id,
                "message": _source_id_value(source_id) if source_id is not None else None,
                "no_id_service_key": no_id_service_key,
            },
            length=24,
        )
        services.append(
            {
                "canonical_ordinal": ordinal,
                "community_id": community_id,
                "content_hash": _sha256_json(
                    {"service_text": occurrence.service_text, "source_message_id": source_id}
                ),
                "parser_version": PARSER_VERSION,
                "raw_content_hash": occurrence.raw_html_sha256,
                "service_event_id": service_id,
                "service_text": occurrence.service_text,
                "source_html_file": occurrence.source_html_file,
                "source_message_id": source_id,
                "source_occurrences": [
                    item.provenance(selected=item is occurrence)
                    for item in sorted(
                        occurrence_group,
                        key=lambda value: (value.source_html_file, value.source_ordinal),
                    )
                ],
                "source_ordinal": occurrence.source_ordinal,
                "source_platform": "telegram",
                "timestamp": occurrence.timestamp,
                "timestamp_source": occurrence.timestamp_source,
            }
        )

    ordinary_id_set = {item["source_message_id"] for item in messages}
    reply_count = sum(item["reply_to_message_id"] is not None for item in messages)
    resolved_reply_count = sum(
        item["reply_to_message_id"] in ordinary_id_set
        for item in messages
        if item["reply_to_message_id"]
    )
    mode_counts = Counter(
        "mixed"
        if item["text_original"].strip() and item["media_refs"]
        else "text_only"
        if item["text_original"].strip()
        else "media_only"
        if item["media_refs"]
        else "empty"
        for item in messages
    )
    m1_records: list[MessageRecord] = []
    incompatible_reasons: Counter[str] = Counter()
    seen_compatible_ids: set[str] = set()
    m1_reply_links_not_projected = 0
    for item in messages:
        if item["timestamp"] is None:
            incompatible_reasons["missing_timestamp"] += 1
            continue
        if not item["text_original"].strip():
            incompatible_reasons["empty_text_not_allowed_by_m1"] += 1
            continue
        parent_id = item["reply_to_canonical_message_id"]
        projected_parent = parent_id if parent_id in seen_compatible_ids else None
        if item["reply_to_message_id"] is not None and projected_parent is None:
            m1_reply_links_not_projected += 1
        m1_records.append(
            MessageRecord(
                message_id=item["message_id"],
                community_id=community_id,
                language=language,
                user_id_hash=item["anonymized_author_id"],
                user_role="user",
                timestamp=datetime.fromisoformat(item["timestamp"].replace("Z", "+00:00")),
                text=item["text_original"],
                reply_to_message_id=projected_parent,
                campaign_id=None,
            )
        )
        seen_compatible_ids.add(item["message_id"])

    malformed_reasons = {
        "incomplete_message_fragment",
        "joined_author_inheritance_failed",
        "malformed_reply_reference",
        "missing_author",
        "missing_or_malformed_timestamp",
        "missing_source_message_id",
    }
    ordinary_occurrence_count = sum(
        item.record_type == "ordinary" for snapshot in snapshots for item in snapshot.occurrences
    )
    service_occurrence_count = sum(
        item.record_type == "service" for snapshot in snapshots for item in snapshot.occurrences
    )
    profile = {
        "canonical_html_file_count": sum(len(snapshot.html_files) for snapshot in maximal),
        "conflicting_duplicate_message_id_count": len(conflicting_ids),
        "deleted_account_message_count": sum(
            item["author_identity"]["status"] == "deleted_account" for item in messages
        ),
        "duplicate_message_id_count": len(duplicate_groups),
        "duplicate_occurrence_count_beyond_first": sum(
            len(items) - 1 for items in duplicate_groups.values()
        ),
        "earliest_timestamp": min(
            (item["timestamp"] for item in messages if item["timestamp"]), default=None
        ),
        "empty_message_count": mode_counts["empty"],
        "forwarded_message_count": sum(item["forwarded_from"] is not None for item in messages),
        "html_file_count": sum(len(snapshot.html_files) for snapshot in snapshots),
        "joined_author_inheritance_failure_count": sum(
            item["author_identity"]["resolution"] == "joined_inheritance_failed"
            for item in messages
        ),
        "joined_author_inheritance_success_count": sum(
            item["author_identity"]["resolution"] == "joined_inheritance" for item in messages
        ),
        "joined_message_count": sum(
            item["author_identity"]["resolution"].startswith("joined") for item in messages
        ),
        "latest_timestamp": max(
            (item["timestamp"] for item in messages if item["timestamp"]), default=None
        ),
        "malformed_message_count": sum(item["reason"] in malformed_reasons for item in quarantine),
        "media_kind_counts": dict(sorted(Counter(item["kind"] for item in media_records).items())),
        "media_only_message_count": mode_counts["media_only"],
        "mixed_message_count": mode_counts["mixed"],
        "ordinary_message_count": len(messages),
        "ordinary_message_occurrence_count": ordinary_occurrence_count,
        "parse_quarantine_count": len(quarantine),
        "parse_loss_count": sum(
            item["reason"] == "incomplete_message_fragment" for item in quarantine
        ),
        "reply_count": reply_count,
        "reply_resolution_rate": resolved_reply_count / reply_count if reply_count else 1.0,
        "resolved_reply_count": resolved_reply_count,
        "service_event_count": len(services),
        "service_event_occurrence_count": service_occurrence_count,
        "source_block_occurrence_count": ordinary_occurrence_count + service_occurrence_count,
        "source_media_occurrence_kind_counts": dict(
            sorted(
                Counter(
                    media["kind"]
                    for snapshot in snapshots
                    for occurrence in snapshot.occurrences
                    for media in occurrence.media
                ).items()
            )
        ),
        "text_only_message_count": mode_counts["text_only"],
        "unique_author_display_name_count": len(
            {
                item["author_identity"]["display_name"]
                for item in messages
                if item["author_identity"]["display_name"] is not None
            }
        ),
        "unique_anonymized_author_count": len({item["anonymized_author_id"] for item in messages}),
        "unique_source_message_ids": len(all_by_id),
        "unresolved_reply_count": reply_count - resolved_reply_count,
    }

    inventory, input_fingerprint = _inventory(roots, source_parent)
    m1_contents = data_artifact_contents(m1_records, [], [], [], [])
    m1_dataset_id = f"telegram-html-{input_fingerprint[:16]}-m1"
    m1_generation_id, m1_checksums = publication_metadata(m1_dataset_id, m1_contents)
    m1_generated_at = (
        max(record.timestamp for record in m1_records)
        if m1_records
        else datetime.fromtimestamp(0, tz=UTC)
    )
    m1_dataset = CommunityDataset(
        messages=m1_records,
        campaigns=[],
        claims=[],
        outcomes=[],
        annotations=[],
        manifest=DatasetManifest(
            dataset_id=m1_dataset_id,
            schema_version="1.1",
            synthetic=False,
            seed=None,
            message_count=len(m1_records),
            community_ids=[community_id] if m1_records else [],
            languages=[language] if m1_records else [],
            campaign_ids=[],
            scenarios={},
            generated_at=m1_generated_at,
            generation_id=m1_generation_id,
            artifact_checksums=m1_checksums,
            source_format="telegram_desktop_html_v1_m1_projection",
            source_sha256=input_fingerprint,
            limitations=[
                (
                    f"Projection excludes {len(messages) - len(m1_records)} textless message(s); "
                    "the complete records remain in the parent canonical messages.jsonl."
                ),
                (
                    f"Projection omits {m1_reply_links_not_projected} reply link(s) whose target "
                    "is unavailable or outside the text-bearing M1 projection."
                ),
                (
                    "HTML timestamps are normalized with the manifest's explicit source-timezone "
                    "assumption because Telegram HTML contains no timezone metadata."
                ),
                (
                    "HTML exports expose display names but no stable Telegram sender IDs; "
                    "author hashes use the private salt and documented conservative identity rules."
                ),
                "Imported roles default to user.",
            ],
        ),
    )

    destination.parent.mkdir(parents=True, exist_ok=True)
    if os.path.lexists(destination):
        raise FileExistsError(f"output path already exists: {destination}")
    staging = Path(tempfile.mkdtemp(dir=destination.parent, prefix=f".{destination.name}.staging-"))
    staging_stat = staging.lstat()
    try:
        quarantine.sort(
            key=lambda item: (
                item.get("source_message_id") or "",
                item["reason"],
                item.get("source_html_file") or "",
                item.get("source_ordinal") or 0,
            )
        )
        payload_names = (
            "messages.jsonl",
            "service_events.jsonl",
            "media_manifest.jsonl",
            "parse_quarantine.jsonl",
        )
        _write_jsonl(staging / payload_names[0], messages)
        _write_jsonl(staging / payload_names[1], services)
        _write_jsonl(staging / payload_names[2], media_records)
        _write_jsonl(staging / payload_names[3], quarantine)
        m1_output = write_dataset(m1_dataset, staging / "m1_dataset")
        artifact_sha256 = _artifact_hashes(staging, payload_names)
        m1_manifest = json.loads((m1_output / "manifest.json").read_text(encoding="utf-8"))
        output_fingerprint_payload = {
            "canonical_artifacts": artifact_sha256,
            "m1_projection_artifacts": m1_manifest["artifact_checksums"],
            "m1_projection_generation_id": m1_manifest["generation_id"],
        }
        manifest = {
            "artifact_sha256": artifact_sha256,
            "community_id": community_id,
            "html_inputs": sorted(
                (html_file for snapshot in snapshots for html_file in snapshot.html_files),
                key=lambda item: item["source_html_file"],
            ),
            "identity_salt_fingerprint": _sha256_bytes(identity_salt.encode("utf-8")),
            "input_fingerprint": input_fingerprint,
            "input_inventory": inventory,
            "language": language,
            "m1_compatibility": {
                "batch_mapping": {
                    "content_hash": input_fingerprint,
                    "message_count": len(m1_records),
                    "source_type": SOURCE_FORMAT,
                    "window_end": _utc_json(
                        max((record.timestamp for record in m1_records), default=None)
                    ),
                    "window_start": _utc_json(
                        min((record.timestamp for record in m1_records), default=None)
                    ),
                },
                "compatible_message_count": len(m1_records),
                "contract": "community_intelligence.models.MessageRecord@1.1",
                "evidence_mapping": {
                    "evidence_message_id_field": "message_id",
                    "material_claim_traceable_to_source_occurrence": True,
                    "provenance_sidecar": "messages.jsonl",
                },
                "incompatible_message_count": len(messages) - len(m1_records),
                "incompatible_reason_counts": dict(sorted(incompatible_reasons.items())),
                "projection_artifact_checksums": m1_manifest["artifact_checksums"],
                "projection_generation_id": m1_manifest["generation_id"],
                "projection_path": "m1_dataset",
                "reply_links_not_projected": m1_reply_links_not_projected,
                "status": "compatible_with_sidecar_retention"
                if len(m1_records) != len(messages)
                else "fully_compatible",
            },
            "maximal_snapshots": sorted(maximal_labels),
            "output_fingerprint": _sha256_json(output_fingerprint_payload),
            "parser_version": PARSER_VERSION,
            "profile": profile,
            "redundant_snapshots": sorted(
                snapshot.label for snapshot in snapshots if snapshot.label not in maximal_labels
            ),
            "schema_version": SCHEMA_VERSION,
            "source_format": SOURCE_FORMAT,
            "source_timezone": {
                "assumption": source_timezone,
                "html_metadata_present": False,
                "provenance": timezone_provenance,
            },
        }
        (staging / "dataset_manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        publish_directory_no_replace(staging, destination)
    finally:
        cleanup_private_directory(
            staging,
            expected_inode=staging_stat.st_ino,
            expected_device=staging_stat.st_dev,
        )
    return destination
