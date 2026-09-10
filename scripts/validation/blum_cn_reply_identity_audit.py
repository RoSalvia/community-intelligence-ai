#!/usr/bin/env python3
"""Aggregate-only Reply and export-local author-token quality audit.

This script deliberately does not persist raw display names, avatar tokens, or
message text. It evaluates structural identity signals without changing the
canonical Telegram HTML contract or identity policy.
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from community_intelligence.importers.telegram_html import _Occurrence, _parse_snapshot

_AUTHOR_TOKEN = re.compile(r"author_([^/'\"?#<>]+)\.jpg(?:[?#][^'\"]*)?")
_INITIALS_CLASS = re.compile(r'class=["\'][^"\']*\binitials\b[^"\']*["\']')


def _args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-parent", type=Path, required=True)
    parser.add_argument("--source-dir", type=Path, action="append", required=True)
    parser.add_argument("--canonical-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def _percent(numerator: int, denominator: int) -> float:
    return round(100.0 * numerator / denominator, 6) if denominator else 0.0


def _distribution(mapping: dict[str, set[str]]) -> dict[str, int]:
    return {
        "one_to_one_key_count": sum(len(values) == 1 for values in mapping.values()),
        "one_to_many_key_count": sum(len(values) > 1 for values in mapping.values()),
        "total_key_count": len(mapping),
    }


def _nearest_rank(values: list[int], percentile: float) -> int:
    if not values:
        return 0
    ordered = sorted(values)
    rank = max(1, int(len(ordered) * percentile + 0.999999))
    return ordered[rank - 1]


def _chain_depths(messages_by_source_id: dict[str, dict[str, Any]]) -> tuple[Counter[int], int]:
    memo: dict[str, int] = {}
    visiting: set[str] = set()
    cycle_count = 0

    def depth(source_id: str) -> int:
        nonlocal cycle_count
        if source_id in memo:
            return memo[source_id]
        if source_id in visiting:
            cycle_count += 1
            return 0
        visiting.add(source_id)
        message = messages_by_source_id[source_id]
        parent_id = message["reply_to_message_id"]
        value = 0
        if parent_id in messages_by_source_id:
            value = 1 + depth(parent_id)
        visiting.remove(source_id)
        memo[source_id] = value
        return value

    distribution = Counter(
        depth(source_id)
        for source_id, message in messages_by_source_id.items()
        if message["reply_to_message_id"] in messages_by_source_id
    )
    return distribution, cycle_count


def _identity_metrics(
    resolved_pairs: list[tuple[str, str]],
    identity_by_source_id: dict[str, str],
) -> dict[str, int]:
    edges = [
        (identity_by_source_id[child], identity_by_source_id[parent])
        for child, parent in resolved_pairs
    ]
    return {
        "cross_author_reply_count": sum(child != parent for child, parent in edges),
        "self_reply_count": sum(child == parent for child, parent in edges),
        "unique_directed_author_pair_count": len(set(edges)),
        "unique_recipient_count": len({parent for _, parent in edges}),
        "unique_responder_count": len({child for child, _ in edges}),
    }


def main() -> None:
    args = _args()
    timezone = ZoneInfo("Asia/Shanghai")
    snapshots = [
        _parse_snapshot(
            root.resolve(),
            source_parent=args.source_parent.resolve(),
            timezone=timezone,
            timezone_name="Asia/Shanghai",
            timezone_provenance="reply_identity_quality_audit_only",
        )
        for root in args.source_dir
    ]
    messages = _load_jsonl(args.canonical_root / "messages.jsonl")
    manifest = json.loads((args.canonical_root / "dataset_manifest.json").read_text())

    text_cache: dict[str, str] = {}
    occurrence_by_key: dict[tuple[str, int], _Occurrence] = {}
    direct_token_by_key: dict[tuple[str, int], str | None] = {}
    effective_token_by_key: dict[tuple[str, int], str | None] = {}
    initials_by_key: dict[tuple[str, int], bool] = {}
    ordinary_by_source_id: dict[str, list[_Occurrence]] = defaultdict(list)

    for snapshot in snapshots:
        previous_token: str | None = None
        for occurrence in snapshot.occurrences:
            key = (occurrence.source_html_file, occurrence.source_ordinal)
            occurrence_by_key[key] = occurrence
            if occurrence.record_type != "ordinary":
                continue
            source_path = args.source_parent / occurrence.source_html_file
            source = text_cache.get(occurrence.source_html_file)
            if source is None:
                source = source_path.read_text(encoding="utf-8-sig")
                text_cache[occurrence.source_html_file] = source
            fragment = source[occurrence.start_offset : occurrence.end_offset]
            token_match = _AUTHOR_TOKEN.search(fragment)
            direct_token = token_match.group(1) if token_match else None
            initials = bool(_INITIALS_CLASS.search(fragment))
            if occurrence.joined:
                effective_token = previous_token
            else:
                effective_token = direct_token
                previous_token = direct_token
            direct_token_by_key[key] = direct_token
            effective_token_by_key[key] = effective_token
            initials_by_key[key] = initials
            if occurrence.source_message_id is not None:
                ordinary_by_source_id[occurrence.source_message_id].append(occurrence)

    selected_rows: list[tuple[dict[str, Any], _Occurrence, str | None, str | None, bool]] = []
    for message in messages:
        key = (message["source_html_file"], message["source_ordinal"])
        occurrence = occurrence_by_key[key]
        selected_rows.append(
            (
                message,
                occurrence,
                direct_token_by_key[key],
                effective_token_by_key[key],
                initials_by_key[key],
            )
        )

    explicit_rows = [row for row in selected_rows if not row[1].joined]
    joined_rows = [row for row in selected_rows if row[1].joined]
    token_rows = [row for row in selected_rows if row[3] is not None]
    deleted_rows = [
        row for row in selected_rows if row[0]["author_identity"]["status"] == "deleted_account"
    ]

    selected_token_to_names: dict[str, set[str]] = defaultdict(set)
    selected_name_to_tokens: dict[str, set[str]] = defaultdict(set)
    selected_token_to_pages: dict[str, set[str]] = defaultdict(set)
    selected_token_to_statuses: dict[str, set[str]] = defaultdict(set)
    for message, _, _, effective_token, _ in selected_rows:
        name = message["author_identity"]["display_name"]
        if effective_token is None or name is None:
            continue
        selected_token_to_names[effective_token].add(name)
        selected_name_to_tokens[name].add(effective_token)
        selected_token_to_pages[effective_token].add(message["source_html_file"])
        selected_token_to_statuses[effective_token].add(message["author_identity"]["status"])

    all_token_to_names: dict[str, set[str]] = defaultdict(set)
    all_name_to_tokens: dict[str, set[str]] = defaultdict(set)
    all_token_to_snapshots: dict[str, set[str]] = defaultdict(set)
    for snapshot in snapshots:
        for occurrence in snapshot.occurrences:
            if occurrence.record_type != "ordinary" or occurrence.author_identity is None:
                continue
            key = (occurrence.source_html_file, occurrence.source_ordinal)
            token = effective_token_by_key[key]
            name = occurrence.author_identity["display_name"]
            if token is None or name is None:
                continue
            all_token_to_names[token].add(name)
            all_name_to_tokens[name].add(token)
            all_token_to_snapshots[token].add(snapshot.label)

    duplicated_ids = {
        source_id: occurrences
        for source_id, occurrences in ordinary_by_source_id.items()
        if len({item.snapshot_label for item in occurrences}) > 1
    }
    consistency_fields = (
        "multi_snapshot_source_id_count",
        "stable_token_count",
        "token_availability_mismatch_count",
        "token_availability_mismatch_photo_vs_initials_count",
        "token_availability_mismatch_same_display_name_count",
        "token_mismatch_count",
        "with_any_token_count",
        "with_token_in_all_occurrences_count",
    )
    duplicate_token_checks = Counter({field: 0 for field in consistency_fields})
    deleted_duplicate_token_checks = Counter({field: 0 for field in consistency_fields})
    for _source_id, occurrences in duplicated_ids.items():
        values = {
            effective_token_by_key[(item.source_html_file, item.source_ordinal)]
            for item in occurrences
        }
        non_null = values - {None}
        target = duplicate_token_checks
        if all(
            item.author_identity is not None and item.author_identity["status"] == "deleted_account"
            for item in occurrences
        ):
            target = deleted_duplicate_token_checks
        target["multi_snapshot_source_id_count"] += 1
        if non_null:
            target["with_any_token_count"] += 1
        if None not in values and non_null:
            target["with_token_in_all_occurrences_count"] += 1
        if len(non_null) == 1 and None not in values:
            target["stable_token_count"] += 1
        if len(non_null) > 1:
            target["token_mismatch_count"] += 1
        if None in values and non_null:
            target["token_availability_mismatch_count"] += 1
            names = {
                item.author_identity["display_name"]
                for item in occurrences
                if item.author_identity is not None
            }
            if len(names) == 1:
                target["token_availability_mismatch_same_display_name_count"] += 1
            if any(
                direct_token_by_key[(item.source_html_file, item.source_ordinal)] is not None
                for item in occurrences
            ) and any(
                initials_by_key[(item.source_html_file, item.source_ordinal)]
                for item in occurrences
            ):
                target["token_availability_mismatch_photo_vs_initials_count"] += 1

    current_identity_by_source_id = {
        message["source_message_id"]: message["anonymized_author_id"] for message in messages
    }
    candidate_identity_by_source_id: dict[str, str] = {}
    token_by_source_id: dict[str, str | None] = {}
    for message, _, _, effective_token, _ in selected_rows:
        source_id = message["source_message_id"]
        token_by_source_id[source_id] = effective_token
        if effective_token is not None:
            candidate_identity_by_source_id[source_id] = f"export-token:{effective_token}"
        else:
            anchor = message["author_identity"]["anchor_source_message_id"]
            candidate_identity_by_source_id[source_id] = f"conservative-anchor:{anchor}"

    messages_by_source_id = {message["source_message_id"]: message for message in messages}
    resolved_pairs = [
        (message["source_message_id"], message["reply_to_message_id"])
        for message in messages
        if message["reply_to_message_id"] in messages_by_source_id
    ]
    unresolved = [
        message
        for message in messages
        if message["reply_to_message_id"] is not None
        and message["reply_to_message_id"] not in messages_by_source_id
    ]
    non_reply_count = sum(message["reply_to_message_id"] is None for message in messages)
    cross_page = sum(
        messages_by_source_id[child]["source_html_file"]
        != messages_by_source_id[parent]["source_html_file"]
        for child, parent in resolved_pairs
    )
    latency_valid = 0
    latency_negative = 0
    for child, parent in resolved_pairs:
        child_ts = messages_by_source_id[child]["timestamp"]
        parent_ts = messages_by_source_id[parent]["timestamp"]
        if child_ts is not None and parent_ts is not None:
            latency_valid += 1
            if child_ts < parent_ts:
                latency_negative += 1

    depth_distribution, reply_cycles = _chain_depths(messages_by_source_id)
    depth_values = [depth for depth, count in depth_distribution.items() for _ in range(count)]
    both_endpoint_token = sum(
        token_by_source_id[child] is not None and token_by_source_id[parent] is not None
        for child, parent in resolved_pairs
    )
    child_token = sum(token_by_source_id[child] is not None for child, _ in resolved_pairs)
    parent_token = sum(token_by_source_id[parent] is not None for _, parent in resolved_pairs)

    multi_name_tokens = {key for key, values in selected_token_to_names.items() if len(values) > 1}
    multi_token_names = {key for key, values in selected_name_to_tokens.items() if len(values) > 1}
    token_split_impacted_messages = sum(
        effective_token in multi_name_tokens for _, _, _, effective_token, _ in selected_rows
    )
    name_merge_impacted_messages = sum(
        effective_token is not None
        and message["author_identity"]["display_name"] in multi_token_names
        for message, _, _, effective_token, _ in selected_rows
    )

    multi_page_tokens = {
        token for token, pages in selected_token_to_pages.items() if len(pages) > 1
    }
    multi_snapshot_tokens = {
        token for token, labels in all_token_to_snapshots.items() if len(labels) > 1
    }
    deleted_tokens = {
        effective_token
        for _, _, _, effective_token, _ in deleted_rows
        if effective_token is not None
    }

    output = {
        "audit_scope": {
            "canonical_root": str(args.canonical_root.resolve()),
            "identity_policy_changed": False,
            "message_content_persisted": False,
            "raw_identity_values_persisted": False,
            "semantic_analysis_performed": False,
            "source_dirs": len(args.source_dir),
        },
        "author_token_audit": {
            "canonical_message_count": len(messages),
            "direct_token_message_count": sum(row[2] is not None for row in selected_rows),
            "effective_token_message_count": len(token_rows),
            "effective_token_message_rate_percent": _percent(len(token_rows), len(messages)),
            "explicit_anchor_count": len(explicit_rows),
            "explicit_initials_only_count": sum(row[4] and row[2] is None for row in explicit_rows),
            "explicit_initials_only_rate_percent": _percent(
                sum(row[4] and row[2] is None for row in explicit_rows), len(explicit_rows)
            ),
            "explicit_neither_token_nor_initials_count": sum(
                row[2] is None and not row[4] for row in explicit_rows
            ),
            "joined_count": len(joined_rows),
            "joined_author_context_inheritance_success_count": sum(
                row[0]["author_identity"]["resolution"] == "joined_inheritance"
                for row in joined_rows
            ),
            "joined_effective_token_count": sum(row[3] is not None for row in joined_rows),
            "joined_token_inheritance_rate_percent": _percent(
                sum(row[3] is not None for row in joined_rows), len(joined_rows)
            ),
            "messages_without_reliable_token_count": len(messages) - len(token_rows),
            "messages_without_reliable_token_rate_percent": _percent(
                len(messages) - len(token_rows), len(messages)
            ),
            "selected_token_to_display_name": _distribution(selected_token_to_names),
            "selected_display_name_to_token": _distribution(selected_name_to_tokens),
            "all_snapshot_token_to_display_name": _distribution(all_token_to_names),
            "all_snapshot_display_name_to_token": _distribution(all_name_to_tokens),
            "token_with_multiple_display_names_count": len(multi_name_tokens),
            "token_rename_split_risk_impacted_message_count": token_split_impacted_messages,
            "display_name_with_multiple_tokens_count": len(multi_token_names),
            "display_name_overmerge_risk_impacted_message_count": name_merge_impacted_messages,
            "multi_page_token_count": len(multi_page_tokens),
            "multi_page_token_with_multiple_names_count": sum(
                token in multi_name_tokens for token in multi_page_tokens
            ),
            "multi_snapshot_token_count": len(multi_snapshot_tokens),
            "multi_snapshot_token_with_multiple_names_count": sum(
                len(all_token_to_names[token]) > 1 for token in multi_snapshot_tokens
            ),
            "non_deleted_duplicate_source_message_token_consistency": dict(duplicate_token_checks),
            "deleted_account": {
                "message_count": len(deleted_rows),
                "explicit_anchor_count": sum(not row[1].joined for row in deleted_rows),
                "joined_inherited_count": sum(row[1].joined for row in deleted_rows),
                "effective_token_message_count": sum(row[3] is not None for row in deleted_rows),
                "effective_token_message_rate_percent": _percent(
                    sum(row[3] is not None for row in deleted_rows), len(deleted_rows)
                ),
                "unique_token_count": len(deleted_tokens),
                "token_also_seen_with_available_name_count": sum(
                    selected_token_to_statuses[token] - {"deleted_account"} != set()
                    for token in deleted_tokens
                ),
                "duplicate_source_message_token_consistency": dict(deleted_duplicate_token_checks),
            },
            "identity_counts": {
                "current_display_name_strategy": len(set(current_identity_by_source_id.values())),
                "candidate_token_assisted_conservative_strategy": len(
                    set(candidate_identity_by_source_id.values())
                ),
                "difference_candidate_minus_current": len(
                    set(candidate_identity_by_source_id.values())
                )
                - len(set(current_identity_by_source_id.values())),
            },
        },
        "reply_audit": {
            "non_reply_count": non_reply_count,
            "reply_count": len(resolved_pairs) + len(unresolved),
            "resolved_reply_count": len(resolved_pairs),
            "unresolved_reply_count": len(unresolved),
            "resolved_reply_rate_percent": _percent(
                len(resolved_pairs), len(resolved_pairs) + len(unresolved)
            ),
            "resolved_cross_html_page_count": cross_page,
            "resolved_same_html_page_count": len(resolved_pairs) - cross_page,
            "resolved_child_author_parseable_count": len(resolved_pairs),
            "resolved_parent_author_parseable_count": len(resolved_pairs),
            "resolved_directed_message_edge_count": len(resolved_pairs),
            "resolved_both_endpoint_token_supported_count": both_endpoint_token,
            "resolved_both_endpoint_token_supported_rate_percent": _percent(
                both_endpoint_token, len(resolved_pairs)
            ),
            "resolved_child_token_supported_count": child_token,
            "resolved_parent_token_supported_count": parent_token,
            "response_latency_timestamp_pair_count": latency_valid,
            "response_latency_negative_order_count": latency_negative,
            "reply_cycle_count": reply_cycles,
            "reply_chain_depth_distribution": {
                str(depth): count for depth, count in sorted(depth_distribution.items())
            },
            "reply_chain_max_depth": max(depth_distribution, default=0),
            "reply_chain_median_depth": _nearest_rank(depth_values, 0.5),
            "reply_chain_p95_depth": _nearest_rank(depth_values, 0.95),
            "unresolved_child_author_parseable_count": len(unresolved),
            "unresolved_parent_author_available_count": 0,
            "current_display_name_strategy": _identity_metrics(
                resolved_pairs, current_identity_by_source_id
            ),
            "candidate_token_assisted_conservative_strategy": _identity_metrics(
                resolved_pairs, candidate_identity_by_source_id
            ),
        },
        "source_fingerprints": {
            "input_fingerprint": manifest["input_fingerprint"],
            "output_fingerprint": manifest["output_fingerprint"],
            "parser_version": manifest["parser_version"],
            "schema_version": manifest["schema_version"],
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(output, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(json.dumps(output, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
