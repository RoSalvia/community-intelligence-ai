"""Privacy-safe structural projection for one frozen Telegram JSON chat object."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from community_intelligence.importers.telegram import (
    _digest,
    _flatten_text,
    _reject_duplicate_keys,
    _timestamp,
    import_telegram_export,
)
from community_intelligence.models import CommunityDataset

PROJECTION_VERSION = "telegram-json-structural-projection-v1.0.0"
_MEDIA_KEYS = frozenset(
    {
        "animation",
        "audio_file",
        "contact_information",
        "file",
        "location_information",
        "media_type",
        "photo",
        "place_name",
        "poll",
        "sticker_emoji",
        "thumbnail",
        "video_file",
        "video_message",
        "voice_message",
    }
)
_LINK_ENTITY_TYPES = frozenset({"email", "link", "text_link"})


@dataclass(frozen=True)
class StructuralProjection:
    messages: tuple[dict[str, Any], ...]
    identities: dict[str, dict[str, Any]]
    edges: tuple[dict[str, Any], ...]
    audit: dict[str, Any]
    dataset: CommunityDataset | None


def _ratio(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 12) if denominator else 0.0


def _iso(value: datetime) -> str:
    return value.astimezone(UTC).isoformat(timespec="seconds")


def _source_id_range(values: list[object]) -> dict[str, object | None]:
    if not values:
        return {"minimum": None, "maximum": None}
    if all(isinstance(value, int) for value in values):
        return {"minimum": min(values), "maximum": max(values)}
    ordered = sorted(str(value) for value in values)
    return {"minimum": ordered[0], "maximum": ordered[-1]}


def _link_count(record: dict[str, Any]) -> int:
    entities = record.get("text_entities")
    if not isinstance(entities, list):
        return 0
    return sum(
        isinstance(entity, dict) and entity.get("type") in _LINK_ENTITY_TYPES for entity in entities
    )


def _media_kinds(record: dict[str, Any]) -> list[str]:
    return sorted(key for key in _MEDIA_KEYS if record.get(key) not in (None, "", [], {}))


def _maximum_chain_depth(parent_by_child: dict[str, str]) -> int:
    memo: dict[str, int] = {}
    visiting: set[str] = set()

    def depth(message_id: str) -> int:
        if message_id in memo:
            return memo[message_id]
        if message_id in visiting:
            raise ValueError("reply graph must be acyclic")
        visiting.add(message_id)
        parent = parent_by_child.get(message_id)
        value = 0 if parent is None else 1 + depth(parent)
        visiting.remove(message_id)
        memo[message_id] = value
        return value

    return max((depth(message_id) for message_id in parent_by_child), default=0)


def build_structural_projection(
    input_path: str | Path,
    *,
    community_id: str,
    language: str,
    user_hash_salt: str,
    build_canonical_dataset: bool = True,
) -> StructuralProjection:
    """Build M1 canonical data plus an in-memory structural audit projection.

    The returned structures contain hashes and aggregate-ready flags only. Raw
    sender IDs, names, URLs, forward sources, and media paths are discarded.
    """

    if not user_hash_salt:
        raise ValueError("user_hash_salt must not be empty")
    source = Path(input_path).expanduser().resolve(strict=True)
    raw_source = source.read_bytes()
    value = json.loads(raw_source.decode("utf-8"), object_pairs_hook=_reject_duplicate_keys)
    if not isinstance(value, dict) or not isinstance(value.get("messages"), list):
        raise ValueError("frozen chat snapshot must contain a messages array")

    dataset = (
        import_telegram_export(
            source,
            language=language,
            community_id=community_id,
            user_hash_salt=user_hash_salt,
        )
        if build_canonical_dataset
        else None
    )
    ordinary_raw: list[dict[str, Any]] = []
    service_count = 0
    for position, record in enumerate(value["messages"]):
        if not isinstance(record, dict):
            raise ValueError(f"message at index {position} must be an object")
        if record.get("type") != "message":
            service_count += 1
            continue
        if record.get("id") is None:
            raise ValueError(f"ordinary message at index {position} has no id")
        ordinary_raw.append(record)

    raw_ids = [record["id"] for record in ordinary_raw]
    if len({str(value) for value in raw_ids}) != len(raw_ids):
        raise ValueError("ordinary message IDs must be unique")
    hashed_by_raw = {
        str(raw_id): _digest("tg_", {"community": community_id, "message": raw_id}, length=24)
        for raw_id in raw_ids
    }

    messages: list[dict[str, Any]] = []
    identities: dict[str, dict[str, Any]] = {}
    timestamps_by_raw: dict[str, datetime] = {}
    actor_by_raw: dict[str, str] = {}
    usable_actor_by_raw: dict[str, bool] = {}
    deleted_count = 0
    for record in ordinary_raw:
        raw_id = str(record["id"])
        message_id = hashed_by_raw[raw_id]
        timestamp = _timestamp(record)
        timestamps_by_raw[raw_id] = timestamp
        raw_sender = record.get("from_id")
        usable_actor = raw_sender not in (None, "")
        if usable_actor:
            actor_id = _digest(
                "usr_",
                {
                    "community": community_id,
                    "sender": str(raw_sender),
                    "salt": user_hash_salt,
                },
            )
        else:
            actor_id = _digest(
                "usr_",
                {
                    "community": community_id,
                    "missing_actor_message": raw_id,
                    "salt": user_hash_salt,
                },
            )
        actor_by_raw[raw_id] = actor_id
        usable_actor_by_raw[raw_id] = usable_actor
        deleted = record.get("from") == "Deleted Account"
        deleted_count += deleted
        text = _flatten_text(record.get("text", ""))
        media_kinds = _media_kinds(record)
        links = _link_count(record)
        messages.append(
            {
                "message_id": message_id,
                "source_message_id": record["id"],
                "community_id": community_id,
                "timestamp": timestamp,
                "text_original": text,
                "forwarded_from": True if record.get("forwarded_from") not in (None, "") else None,
                "links": [True] * links,
                "media_refs": media_kinds,
                "reaction_present": bool(record.get("reactions")),
                "edited_metadata_present": any(
                    record.get(key) not in (None, "")
                    for key in ("edited", "edited_unixtime", "edited_date")
                ),
                "webpage_preview_present": bool(record.get("webpage")),
            }
        )
        identities[message_id] = {
            "message_id": message_id,
            "resolved_identity_id": actor_id,
            "identity_confidence": "high" if usable_actor else "low",
            "usable_from_id": usable_actor,
            "deleted_account": deleted,
            "reply_state": "non_reply",
        }

    edges: list[dict[str, Any]] = []
    parent_by_child: dict[str, str] = {}
    unresolved = 0
    cross_boundary = 0
    reply_count = 0
    negative_latency = 0
    for record in ordinary_raw:
        raw_reply = record.get("reply_to_message_id")
        if raw_reply is None:
            continue
        reply_count += 1
        raw_id = str(record["id"])
        parent_raw_id = str(raw_reply)
        child_id = hashed_by_raw[raw_id]
        parent_id = hashed_by_raw.get(parent_raw_id)
        if parent_id is None:
            unresolved += 1
            cross_boundary += 1
            identities[child_id]["reply_state"] = "unresolved_reply"
            continue
        latency = (timestamps_by_raw[raw_id] - timestamps_by_raw[parent_raw_id]).total_seconds()
        if latency < 0:
            unresolved += 1
            negative_latency += 1
            identities[child_id]["reply_state"] = "unresolved_reply"
            continue
        identities[child_id]["reply_state"] = "resolved_reply"
        parent_by_child[child_id] = parent_id
        child_usable = usable_actor_by_raw[raw_id]
        parent_usable = usable_actor_by_raw[parent_raw_id]
        relation = (
            "uncertain"
            if not (child_usable and parent_usable)
            else ("self" if actor_by_raw[raw_id] == actor_by_raw[parent_raw_id] else "cross_author")
        )
        edges.append(
            {
                "child_message_id": child_id,
                "parent_message_id": parent_id,
                "response_latency_seconds": latency,
                "author_relation": relation,
                "child_resolved_identity_id": actor_by_raw[raw_id],
                "parent_resolved_identity_id": actor_by_raw[parent_raw_id],
                "child_identity_confidence": "high" if child_usable else "low",
                "parent_identity_confidence": "high" if parent_usable else "low",
            }
        )

    timestamps = list(timestamps_by_raw.values())
    ordinary_count = len(ordinary_raw)
    from_id_count = sum(usable_actor_by_raw.values())
    text_count = sum(bool(row["text_original"].strip()) for row in messages)
    media_only_count = sum(
        not row["text_original"].strip() and bool(row["media_refs"]) for row in messages
    )
    audit = {
        "projection_version": PROJECTION_VERSION,
        "community_id": community_id,
        "language": language,
        "timestamp_contract": "date_unixtime authoritative; normalized to UTC",
        "coverage": {
            "first_ordinary_message_timestamp": _iso(min(timestamps)) if timestamps else None,
            "last_ordinary_message_timestamp": _iso(max(timestamps)) if timestamps else None,
            "ordinary_message_count": ordinary_count,
            "service_event_count": service_count,
            "total_record_count": ordinary_count + service_count,
            "source_message_id_range": _source_id_range(raw_ids),
        },
        "identity": {
            "from_id_message_count": from_id_count,
            "from_id_coverage": _ratio(from_id_count, ordinary_count),
            "deleted_account_message_count": deleted_count,
            "deleted_account_message_coverage": _ratio(deleted_count, ordinary_count),
            "anonymized_stable_actor_message_count": from_id_count,
            "anonymized_stable_actor_coverage": _ratio(from_id_count, ordinary_count),
            "anonymized_stable_actor_entity_count": len(
                {actor_by_raw[key] for key, usable in usable_actor_by_raw.items() if usable}
            ),
            "messages_without_usable_actor_identity": ordinary_count - from_id_count,
            "interpretation": (
                "export-local salted pseudonymous entities, not verified unique humans"
            ),
        },
        "reply": {
            "messages_with_reply_to_message_id": reply_count,
            "resolved_reply_edges": len(edges),
            "unresolved_reply_edges": unresolved,
            "reply_resolution_rate": _ratio(len(edges), reply_count),
            "cross_boundary_replies": cross_boundary,
            "negative_latency_replies": negative_latency,
            "maximum_reply_chain_depth_edges": _maximum_chain_depth(parent_by_child),
            "response_latency_available_count": len(edges),
            "response_latency_availability": _ratio(len(edges), reply_count),
        },
        "content_structure": {
            "text_bearing_message_count": text_count,
            "media_only_message_count": media_only_count,
            "textless_without_media_metadata_count": ordinary_count - text_count - media_only_count,
            "forwarded_message_count": sum(row["forwarded_from"] is not None for row in messages),
            "link_message_count": sum(bool(row["links"]) for row in messages),
            "reaction_message_count": sum(row["reaction_present"] for row in messages),
            "edited_metadata_message_count": sum(
                row["edited_metadata_present"] for row in messages
            ),
            "webpage_preview_message_count": sum(
                row["webpage_preview_present"] for row in messages
            ),
        },
        "canonical_dataset": {
            "contract": "CommunityDataset schema 1.1 via existing Telegram JSON importer",
            "text_bearing_message_count": len(dataset.messages) if dataset else text_count,
            "source_sha256": (
                dataset.manifest.source_sha256
                if dataset
                else hashlib.sha256(raw_source).hexdigest()
            ),
        },
    }
    return StructuralProjection(
        messages=tuple(messages),
        identities=identities,
        edges=tuple(edges),
        audit=audit,
        dataset=dataset,
    )


def calculate_shared_period(
    first_audit: dict[str, Any], second_audit: dict[str, Any]
) -> dict[str, str]:
    starts = [
        datetime.fromisoformat(first_audit["coverage"]["first_ordinary_message_timestamp"]),
        datetime.fromisoformat(second_audit["coverage"]["first_ordinary_message_timestamp"]),
    ]
    ends = [
        datetime.fromisoformat(first_audit["coverage"]["last_ordinary_message_timestamp"]),
        datetime.fromisoformat(second_audit["coverage"]["last_ordinary_message_timestamp"]),
    ]
    start = max(starts)
    end = min(ends)
    if end < start:
        raise ValueError("communities have no shared ordinary-message period")
    return {
        "start": start.isoformat(timespec="seconds"),
        "end_inclusive": end.isoformat(timespec="seconds"),
        "derivation": "max(first ordinary timestamps) through min(last ordinary timestamps)",
    }
