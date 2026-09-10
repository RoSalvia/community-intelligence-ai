"""Additive export-local identity projection for Telegram Desktop HTML.

The projection reads canonical v1.0 facts and raw HTML provenance, then writes a
separate private sidecar. It never mutates the canonical dataset and never emits
the raw Telegram Desktop avatar token.
"""

from __future__ import annotations

import json
import os
import re
import tempfile
from collections import Counter
from collections.abc import Sequence
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from community_intelligence.importers.telegram import _digest
from community_intelligence.importers.telegram_html import (
    PARSER_VERSION,
    SCHEMA_VERSION,
    SOURCE_FORMAT,
    _artifact_hashes,
    _inventory,
    _Occurrence,
    _parse_snapshot,
    _sha256_bytes,
    _sha256_json,
    _write_jsonl,
)
from community_intelligence.io import cleanup_private_directory, publish_directory_no_replace

IDENTITY_STRATEGY_VERSION = "telegram-html-author-identity-v1.1"
IDENTITY_SCHEMA_VERSION = "1.1.0"
METRIC_IDENTITY_CONTRACT_VERSION = "telegram-html-identity-metric-quality-v1.0"
CANONICAL_CONTRACT = "telegram-html-canonical-v1.0.0"

_AUTHOR_TOKEN = re.compile(r"author_([^/'\"?#<>]+)\.jpg(?:[?#][^'\"]*)?")
_CANONICAL_FILES = (
    "messages.jsonl",
    "service_events.jsonl",
    "media_manifest.jsonl",
    "parse_quarantine.jsonl",
    "dataset_manifest.json",
    "m1_dataset/messages.jsonl",
    "m1_dataset/campaigns.json",
    "m1_dataset/claims.json",
    "m1_dataset/outcomes.csv",
    "m1_dataset/annotations.jsonl",
    "m1_dataset/manifest.json",
)
_PAYLOAD_FILES = (
    "message_identities.jsonl",
    "reply_edges.jsonl",
    "metric_identity_contract.json",
)


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def _write_json(path: Path, value: object) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def _percent(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 12) if denominator else 0.0


def _canonical_hashes(root: Path) -> dict[str, str]:
    hashes: dict[str, str] = {}
    for relative in _CANONICAL_FILES:
        path = root / relative
        if path.is_symlink() or not path.is_file():
            raise ValueError(f"canonical v1.0 artifact missing or unsafe: {relative}")
        hashes[relative] = _sha256_bytes(path.read_bytes())
    return hashes


def _identity_signal(
    *,
    joined: bool,
    effective_token: str | None,
    author_status: str,
) -> tuple[str, str, str, bool]:
    if effective_token is not None:
        return (
            "joined_avatar_token" if joined else "avatar_token",
            "high",
            "resolved_export_local_token",
            True,
        )
    if author_status == "deleted_account":
        return (
            "joined_deleted_account_anchor" if joined else "deleted_account_anchor",
            "low",
            "conservative_unresolved",
            False,
        )
    if author_status == "missing":
        return (
            "joined_missing_author_anchor" if joined else "missing_author_anchor",
            "low",
            "conservative_unresolved",
            False,
        )
    return (
        "joined_conservative_anchor" if joined else "conservative_anchor",
        "medium",
        "conservative_unresolved",
        False,
    )


def _edge_confidence(child: str, parent: str) -> str:
    if child == parent == "high":
        return "high"
    if "low" in {child, parent}:
        return "low"
    return "medium"


def _latency_seconds(child_timestamp: str | None, parent_timestamp: str | None) -> float | None:
    if child_timestamp is None or parent_timestamp is None:
        return None
    child = datetime.fromisoformat(child_timestamp.replace("Z", "+00:00"))
    parent = datetime.fromisoformat(parent_timestamp.replace("Z", "+00:00"))
    seconds = (child - parent).total_seconds()
    return seconds if seconds >= 0 else None


def _metric_contract(profile: dict[str, Any]) -> dict[str, Any]:
    return {
        "contract_version": METRIC_IDENTITY_CONTRACT_VERSION,
        "identity_strategy_version": IDENTITY_STRATEGY_VERSION,
        "metric_classes": {
            "message_level": {
                "identity_required": False,
                "metrics": {
                    "reply_count": {
                        "allowed_reply_states": [
                            "resolved_reply",
                            "unresolved_reply",
                            "non_reply",
                        ],
                        "rule": "keep all three source-observed states disjoint",
                    },
                    "response_latency": {
                        "allowed_reply_states": ["resolved_reply"],
                        "available_edge_count": profile["response_latency_available_edge_count"],
                        "rule": "requires child and resolved parent timestamps, not identity",
                    },
                },
            },
            "high_confidence_identity": {
                "identity_required": True,
                "required_identity_confidence": "high",
                "requires_both_reply_endpoints": True,
                "must_report_identity_coverage": True,
                "available_reply_edge_count": profile["reply_edge_confidence_counts"]["high"],
                "metrics": [
                    "unique_responders",
                    "unique_recipients",
                    "self_reply",
                    "cross_author_reply",
                    "user_to_user_network",
                    "user_to_mod_network",
                    "peer_support",
                ],
            },
            "broader_identity_dependent": {
                "identity_required": True,
                "fallback_allowed": True,
                "must_report_identity_coverage": True,
                "must_report_confidence_distribution": True,
                "must_label_counts_as_pseudonymous_entities": True,
                "self_cross_is_uncertain_if_any_endpoint_is_not_high": True,
                "metrics": [
                    "unique_users",
                    "unique_responders",
                    "unique_recipients",
                    "reply_network",
                ],
            },
        },
        "additional_metric_dependencies": {
            "reviewed_role_labels_required_for": [
                "user_to_user_network",
                "user_to_mod_network",
                "mod_to_user_network",
                "per_mod_response",
                "contributor_metrics_excluding_mods_and_bots",
            ],
            "semantic_labels_required_for": ["peer_support", "behavior_segmented_metrics"],
            "status": "not_produced_by_identity_projection",
        },
        "coverage_reporting_requirements": {
            "always_report": [
                "identity_strategy_version",
                "identity_scope",
                "identity_confidence_distribution",
                "eligible_numerator",
                "eligible_denominator",
                "token_supported_coverage",
                "uncertain_count",
            ],
            "single_unique_user_number_without_quality_context_allowed": False,
        },
        "prohibited_interpretations": {
            "avatar_token_is_telegram_global_user_id": True,
            "conservative_anchor_equals_real_user": True,
            "identity_count_equals_unique_people": True,
            "unresolved_identity_silently_becomes_new_real_user": True,
            "unresolved_reply_equals_non_reply": True,
        },
        "reply_graph_quality": profile["reply_graph"],
    }


def derive_telegram_html_identity_projection(
    canonical_input: str | Path,
    input_roots: Sequence[str | Path],
    output_dir: str | Path,
    *,
    identity_salt: str,
) -> Path:
    """Create a deterministic, create-only identity sidecar for canonical v1.0."""

    if not input_roots:
        raise ValueError("at least one Telegram HTML export root is required")
    if not identity_salt:
        raise ValueError("identity salt must be non-empty")
    canonical_root = Path(canonical_input).expanduser().resolve(strict=True)
    if not canonical_root.is_dir():
        raise ValueError("canonical input must be a directory")
    roots = sorted(Path(value).expanduser().resolve(strict=True) for value in input_roots)
    if len(roots) != len(set(roots)):
        raise ValueError("Telegram HTML export roots must be unique")
    if any(not root.is_dir() for root in roots):
        raise ValueError("each Telegram HTML export root must be a directory")

    destination = Path(os.path.abspath(Path(output_dir).expanduser()))
    for protected_root in (*roots, canonical_root):
        try:
            destination.relative_to(protected_root)
        except ValueError:
            continue
        raise ValueError("identity projection must be outside raw and canonical input roots")

    canonical_before = _canonical_hashes(canonical_root)
    manifest = json.loads((canonical_root / "dataset_manifest.json").read_text(encoding="utf-8"))
    if manifest.get("source_format") != SOURCE_FORMAT:
        raise ValueError("identity projection requires Telegram HTML canonical input")
    if manifest.get("parser_version") != PARSER_VERSION or manifest.get("schema_version") != (
        SCHEMA_VERSION
    ):
        raise ValueError("identity projection requires canonical parser/schema v1.0.0")

    timezone_metadata = manifest.get("source_timezone") or {}
    timezone_name = timezone_metadata.get("assumption")
    timezone_provenance = timezone_metadata.get("provenance")
    if not isinstance(timezone_name, str) or not isinstance(timezone_provenance, str):
        raise ValueError("canonical source timezone provenance is missing")
    try:
        timezone = ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError as error:
        raise ValueError(f"unknown canonical source timezone: {timezone_name}") from error

    source_parent = Path(os.path.commonpath([str(root.parent) for root in roots])).resolve(
        strict=True
    )
    snapshots = [
        _parse_snapshot(
            root,
            source_parent=source_parent,
            timezone=timezone,
            timezone_name=timezone_name,
            timezone_provenance=timezone_provenance,
        )
        for root in roots
    ]
    _, raw_input_fingerprint = _inventory(roots, source_parent)
    if raw_input_fingerprint != manifest.get("input_fingerprint"):
        raise ValueError("raw HTML inputs do not match canonical input fingerprint")

    text_cache: dict[str, str] = {}
    occurrence_by_key: dict[tuple[str, int], _Occurrence] = {}
    direct_token_by_key: dict[tuple[str, int], str | None] = {}
    effective_token_by_key: dict[tuple[str, int], str | None] = {}
    for snapshot in snapshots:
        previous_token: str | None = None
        for occurrence in snapshot.occurrences:
            if occurrence.record_type != "ordinary":
                continue
            key = (occurrence.source_html_file, occurrence.source_ordinal)
            occurrence_by_key[key] = occurrence
            source = text_cache.get(occurrence.source_html_file)
            if source is None:
                source = (source_parent / occurrence.source_html_file).read_text(
                    encoding="utf-8-sig"
                )
                text_cache[occurrence.source_html_file] = source
            fragment = source[occurrence.start_offset : occurrence.end_offset]
            tokens = set(_AUTHOR_TOKEN.findall(fragment))
            if len(tokens) > 1:
                raise ValueError(
                    "ordinary message contains multiple distinct export-local author tokens: "
                    f"{occurrence.source_html_file}:{occurrence.source_ordinal}"
                )
            direct_token = next(iter(tokens), None)
            if occurrence.joined:
                effective_token = previous_token
            else:
                effective_token = direct_token
                previous_token = direct_token
            direct_token_by_key[key] = direct_token
            effective_token_by_key[key] = effective_token

    messages = _read_jsonl(canonical_root / "messages.jsonl")
    message_identities: list[dict[str, Any]] = []
    identity_by_message_id: dict[str, dict[str, Any]] = {}
    message_by_id = {message["message_id"]: message for message in messages}
    for message in messages:
        key = (message["source_html_file"], message["source_ordinal"])
        occurrence = occurrence_by_key.get(key)
        if occurrence is None:
            raise ValueError(f"canonical provenance does not match raw HTML occurrence: {key}")
        effective_token = effective_token_by_key[key]
        direct_token = direct_token_by_key[key]
        author = message["author_identity"]
        signal, confidence, resolution_status, stable = _identity_signal(
            joined=occurrence.joined,
            effective_token=effective_token,
            author_status=author["status"],
        )
        anchor = author["anchor_source_message_id"] or (
            f"{message['source_html_file']}:{message['source_ordinal']}"
        )
        identity_basis = (
            {"kind": "avatar_token", "value": effective_token}
            if effective_token is not None
            else {"kind": "conservative_anchor", "value": anchor}
        )
        resolved_identity_id = _digest(
            "tg_html_identity_",
            {
                "community": manifest["community_id"],
                "identity_basis": identity_basis,
                "salt": identity_salt,
                "strategy": IDENTITY_STRATEGY_VERSION,
            },
            length=24,
        )
        reply_target = message["reply_to_message_id"]
        reply_state = (
            "non_reply"
            if reply_target is None
            else "resolved_reply"
            if message["reply_to_canonical_message_id"] in message_by_id
            else "unresolved_reply"
        )
        record = {
            "canonical_anonymized_author_id": message["anonymized_author_id"],
            "display_name_metadata": {
                "source": "canonical_author_identity",
                "used_for_global_merge": False,
                "value": author["display_name"],
            },
            "identity_confidence": confidence,
            "identity_is_stable_within_export": stable,
            "identity_resolution_status": resolution_status,
            "identity_scope": "export_local",
            "identity_signal": signal,
            "identity_strategy_version": IDENTITY_STRATEGY_VERSION,
            "message_id": message["message_id"],
            "raw_avatar_token_persisted": False,
            "reply_state": reply_state,
            "reply_to_message_id": reply_target,
            "resolved_identity_id": resolved_identity_id,
            "source_html_file": message["source_html_file"],
            "source_message_id": message["source_message_id"],
            "source_ordinal": message["source_ordinal"],
            "token_observation": (
                "direct"
                if direct_token is not None
                else "joined_inheritance"
                if effective_token is not None
                else "unavailable"
            ),
        }
        message_identities.append(record)
        identity_by_message_id[message["message_id"]] = record

    reply_edges: list[dict[str, Any]] = []
    latency_available = 0
    for message in messages:
        parent_message_id = message["reply_to_canonical_message_id"]
        if parent_message_id is None:
            continue
        child_identity = identity_by_message_id[message["message_id"]]
        parent_identity = identity_by_message_id.get(parent_message_id)
        parent_message = message_by_id.get(parent_message_id)
        if parent_identity is None or parent_message is None:
            raise ValueError("resolved canonical reply is missing its parent record")
        confidence = _edge_confidence(
            child_identity["identity_confidence"], parent_identity["identity_confidence"]
        )
        latency = _latency_seconds(message["timestamp"], parent_message["timestamp"])
        if latency is not None:
            latency_available += 1
        author_relation = (
            "self"
            if confidence == "high"
            and child_identity["resolved_identity_id"] == parent_identity["resolved_identity_id"]
            else "cross_author"
            if confidence == "high"
            else "uncertain"
        )
        reply_edges.append(
            {
                "author_relation": author_relation,
                "child_identity_confidence": child_identity["identity_confidence"],
                "child_message_id": message["message_id"],
                "child_resolved_identity_id": child_identity["resolved_identity_id"],
                "identity_edge_confidence": confidence,
                "identity_scope": "export_local",
                "identity_strategy_version": IDENTITY_STRATEGY_VERSION,
                "parent_identity_confidence": parent_identity["identity_confidence"],
                "parent_message_id": parent_message_id,
                "parent_resolved_identity_id": parent_identity["resolved_identity_id"],
                "reply_edge_id": _digest(
                    "reply_edge_",
                    {"child": message["message_id"], "parent": parent_message_id},
                    length=24,
                ),
                "response_latency_seconds": latency,
            }
        )

    confidence_counts = Counter(record["identity_confidence"] for record in message_identities)
    reply_state_counts = Counter(record["reply_state"] for record in message_identities)
    edge_confidence_counts = Counter(edge["identity_edge_confidence"] for edge in reply_edges)
    author_relation_counts = Counter(edge["author_relation"] for edge in reply_edges)
    child_identities = {edge["child_resolved_identity_id"] for edge in reply_edges}
    parent_identities = {edge["parent_resolved_identity_id"] for edge in reply_edges}
    high_child_edges = [edge for edge in reply_edges if edge["child_identity_confidence"] == "high"]
    high_parent_edges = [
        edge for edge in reply_edges if edge["parent_identity_confidence"] == "high"
    ]
    high_child_identities = {edge["child_resolved_identity_id"] for edge in high_child_edges}
    high_parent_identities = {edge["parent_resolved_identity_id"] for edge in high_parent_edges}
    reply_graph = {
        "high_confidence_identity_edge_count": edge_confidence_counts["high"],
        "high_confidence_identity_edge_coverage": _percent(
            edge_confidence_counts["high"], len(reply_edges)
        ),
        "lower_confidence_identity_edge_count": len(reply_edges) - edge_confidence_counts["high"],
        "self_cross_classification": dict(
            sorted(
                {
                    "cross_author": author_relation_counts["cross_author"],
                    "self": author_relation_counts["self"],
                    "uncertain": author_relation_counts["uncertain"],
                }.items()
            )
        ),
        "total_resolved_edge_count": len(reply_edges),
        "unique_recipients": {
            "broader_pseudonymous_identity_count": len(parent_identities),
            "high_confidence_endpoint_edge_count": len(high_parent_edges),
            "high_confidence_endpoint_edge_coverage": _percent(
                len(high_parent_edges), len(reply_edges)
            ),
            "high_confidence_pseudonymous_identity_count": len(high_parent_identities),
        },
        "unique_responders": {
            "broader_pseudonymous_identity_count": len(child_identities),
            "high_confidence_endpoint_edge_count": len(high_child_edges),
            "high_confidence_endpoint_edge_coverage": _percent(
                len(high_child_edges), len(reply_edges)
            ),
            "high_confidence_pseudonymous_identity_count": len(high_child_identities),
        },
    }
    profile = {
        "identity_confidence_message_counts": {
            level: confidence_counts[level] for level in ("high", "low", "medium")
        },
        "identity_confidence_message_coverage": {
            level: _percent(confidence_counts[level], len(message_identities))
            for level in ("high", "low", "medium")
        },
        "message_count": len(message_identities),
        "pseudonymous_identity_count": len(
            {record["resolved_identity_id"] for record in message_identities}
        ),
        "reply_edge_confidence_counts": {
            level: edge_confidence_counts[level] for level in ("high", "low", "medium")
        },
        "reply_graph": reply_graph,
        "reply_state_counts": {
            state: reply_state_counts[state]
            for state in ("non_reply", "resolved_reply", "unresolved_reply")
        },
        "response_latency_available_edge_count": latency_available,
        "self_cross_classification_counts": reply_graph["self_cross_classification"],
    }
    if profile["reply_state_counts"]["resolved_reply"] != len(reply_edges):
        raise ValueError("reply state and resolved edge counts disagree")
    canonical_profile = manifest.get("profile") or {}
    expected_reply_counts = {
        "resolved_reply": canonical_profile.get("resolved_reply_count"),
        "unresolved_reply": canonical_profile.get("unresolved_reply_count"),
    }
    if any(
        expected_reply_counts[state] != profile["reply_state_counts"][state]
        for state in expected_reply_counts
    ):
        raise ValueError("identity projection reply counts regress canonical v1.0 facts")

    metric_contract = _metric_contract(profile)
    if canonical_before != _canonical_hashes(canonical_root):
        raise ValueError("canonical v1.0 artifacts changed during identity projection")

    destination.parent.mkdir(parents=True, exist_ok=True)
    if os.path.lexists(destination):
        raise FileExistsError(f"output path already exists: {destination}")
    staging = Path(tempfile.mkdtemp(dir=destination.parent, prefix=f".{destination.name}.staging-"))
    staging_stat = staging.lstat()
    try:
        _write_jsonl(staging / "message_identities.jsonl", message_identities)
        _write_jsonl(staging / "reply_edges.jsonl", reply_edges)
        _write_json(staging / "metric_identity_contract.json", metric_contract)
        artifact_sha256 = _artifact_hashes(staging, _PAYLOAD_FILES)
        output_fingerprint = _sha256_json(
            {
                "artifacts": artifact_sha256,
                "canonical_output_fingerprint": manifest["output_fingerprint"],
                "identity_salt_fingerprint": _sha256_bytes(identity_salt.encode("utf-8")),
                "identity_strategy_version": IDENTITY_STRATEGY_VERSION,
            }
        )
        identity_manifest = {
            "artifact_sha256": artifact_sha256,
            "canonical_artifact_sha256": canonical_before,
            "canonical_contract": CANONICAL_CONTRACT,
            "canonical_input_fingerprint": manifest["output_fingerprint"],
            "canonical_raw_facts_unchanged": True,
            "identity_salt_fingerprint": _sha256_bytes(identity_salt.encode("utf-8")),
            "identity_schema_version": IDENTITY_SCHEMA_VERSION,
            "identity_scope": "export_local",
            "identity_strategy_version": IDENTITY_STRATEGY_VERSION,
            "metric_identity_contract_version": METRIC_IDENTITY_CONTRACT_VERSION,
            "output_fingerprint": output_fingerprint,
            "privacy": {
                "display_name_metadata_private": True,
                "raw_avatar_token_persisted": False,
                "resolved_identity_id_is_salted_pseudonym": True,
            },
            "profile": profile,
            "raw_input_fingerprint": raw_input_fingerprint,
            "source_timezone": {
                "html_metadata_present": bool(
                    timezone_metadata.get("html_metadata_present", False)
                ),
                "source_timezone": timezone_name,
                "timezone_not_declared_by_source_html": not bool(
                    timezone_metadata.get("html_metadata_present", False)
                ),
                "timezone_provenance": timezone_provenance,
            },
        }
        _write_json(staging / "identity_manifest.json", identity_manifest)
        publish_directory_no_replace(staging, destination)
    finally:
        cleanup_private_directory(
            staging,
            expected_inode=staging_stat.st_ino,
            expected_device=staging_stat.st_dev,
        )
    return destination
