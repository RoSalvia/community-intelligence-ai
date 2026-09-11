#!/usr/bin/env python3
"""Aggregate-only deterministic structural profiling for private community corpora.

The command persists aggregate metrics, time windows, hashes, and a validation
report. It never persists message text, display names, or pseudonymous IDs.
"""

from __future__ import annotations

import argparse
import bisect
import csv
import hashlib
import json
import statistics
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping, Sequence
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from community_intelligence.episodes import (
    QUESTION_DETECTION_METHOD,
    QUESTION_RULE_ID,
    QUESTION_RULE_VERSION,
    is_question,
)
from community_intelligence.hygiene import (
    DEFAULT_BURST_MINIMUM_MESSAGES,
    DEFAULT_BURST_WINDOW_SECONDS,
    DEFAULT_REPEATED_CONTENT_MINIMUM,
    DEFAULT_SHORT_MESSAGE_MAX_CHARS,
    analyze_hygiene,
)
from community_intelligence.hygiene import (
    RULE_VERSION as HYGIENE_RULE_VERSION,
)
from community_intelligence.models import MessageRecord

PROFILE_VERSION = "deterministic-structural-profile-v1.1.0"
TIMEZONE_NAME = "Asia/Shanghai"
GRAINS = {"5m": 5, "15m": 15, "1h": 60, "1d": 1440}
BLOG_ALIGNMENT_INTERPRETATION = (
    "temporal correlation around a date-only official catalog event; no causal claim"
)
IDENTITY_INTERPRETATION = (
    "broader counts are export-local pseudonymous entities, not verified people; "
    "medium/low conservative anchors may over-split one person"
)


def _parse_timestamp(value: str | datetime) -> datetime:
    parsed = (
        datetime.fromisoformat(value.replace("Z", "+00:00")) if isinstance(value, str) else value
    )
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("message timestamp must be timezone-aware")
    return parsed.astimezone(UTC)


def _jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _stable_digest(value: str) -> str:
    return f"usr_{hashlib.sha256(value.encode()).hexdigest()}"


def _rate(numerator: int | float, denominator: int | float) -> float:
    return round(numerator / denominator, 12) if denominator else 0.0


def _nearest_rank(values: Sequence[int | float], percentile: float) -> int | float:
    if not values:
        return 0
    ordered = sorted(values)
    rank = max(1, int(len(ordered) * percentile + 0.999999999))
    return ordered[rank - 1]


def _median(values: Sequence[int | float]) -> int | float:
    return statistics.median(values) if values else 0


def _bucket_start(value: datetime, minutes: int, timezone: ZoneInfo) -> datetime:
    local = value.astimezone(timezone)
    midnight = datetime.combine(local.date(), time.min, tzinfo=timezone)
    elapsed_minutes = local.hour * 60 + local.minute
    return midnight + timedelta(minutes=(elapsed_minutes // minutes) * minutes)


def _iso(value: datetime) -> str:
    return value.isoformat(timespec="seconds")


def _validate_inputs(
    messages: Sequence[Mapping[str, Any]],
    identities: Mapping[str, Mapping[str, Any]],
    edges: Sequence[Mapping[str, Any]],
) -> None:
    message_ids = [str(row["message_id"]) for row in messages]
    if len(message_ids) != len(set(message_ids)):
        raise ValueError("canonical message IDs must be unique")
    if set(message_ids) != set(identities):
        raise ValueError("identity sidecar must join one-to-one to canonical messages")
    allowed_states = {"resolved_reply", "unresolved_reply", "non_reply"}
    allowed_confidence = {"high", "medium", "low"}
    for message_id, row in identities.items():
        if row["reply_state"] not in allowed_states:
            raise ValueError(f"invalid reply state for {message_id}")
        if row["identity_confidence"] not in allowed_confidence:
            raise ValueError(f"invalid identity confidence for {message_id}")
        if not row.get("resolved_identity_id"):
            raise ValueError(f"missing pseudonymous identity for {message_id}")
    edge_children: set[str] = set()
    for edge in edges:
        child = str(edge["child_message_id"])
        parent = str(edge["parent_message_id"])
        if child in edge_children:
            raise ValueError("resolved reply child IDs must be unique")
        edge_children.add(child)
        if child not in identities or parent not in identities:
            raise ValueError("resolved reply edges must join to canonical messages")
        if identities[child]["reply_state"] != "resolved_reply":
            raise ValueError("resolved reply edge child must have resolved_reply state")
        if float(edge["response_latency_seconds"]) < 0:
            raise ValueError("response latency must be non-negative")
    resolved_children = {
        message_id
        for message_id, row in identities.items()
        if row["reply_state"] == "resolved_reply"
    }
    if edge_children != resolved_children:
        raise ValueError("every resolved reply must have exactly one reply edge")


def _hygiene_flags(
    messages: Sequence[Mapping[str, Any]], identities: Mapping[str, Mapping[str, Any]]
) -> dict[str, Any]:
    text_records: list[MessageRecord] = []
    timestamp_by_id: dict[str, datetime] = {}
    for row in messages:
        text_value = str(row.get("text_original") or "")
        if not text_value.strip():
            continue
        message_id = str(row["message_id"])
        timestamp = _parse_timestamp(row["timestamp"])
        timestamp_by_id[message_id] = timestamp
        identity_id = str(identities[message_id]["resolved_identity_id"])
        text_records.append(
            MessageRecord(
                message_id=message_id,
                community_id=str(row["community_id"]),
                language="zh",
                user_id_hash=_stable_digest(identity_id),
                user_role="user",
                timestamp=timestamp,
                text=text_value,
                reply_to_message_id=None,
                campaign_id=None,
            )
        )

    result = analyze_hygiene(text_records)
    duplicate_messages: set[str] = set()
    filler_messages: set[str] = set()
    repetitive_messages: set[str] = set()
    for evidence in result.evidence:
        ids = list(evidence.supporting_message_ids)
        if evidence.rule_id == "exact_duplicate.v1":
            ids.sort(key=lambda message_id: (timestamp_by_id[message_id], message_id))
            duplicate_messages.update(ids[1:])
        elif evidence.rule_id == "filler_or_short.v1":
            filler_messages.update(ids)
        elif evidence.rule_id == "repeated_content.v1":
            repetitive_messages.update(ids)

    burst_messages: set[str] = set()
    burst_starts: list[datetime] = []
    for event in result.burst_events:
        burst_messages.update(event.message_ids)
        burst_starts.append(event.started_at)
    return {
        "eligible_text_message_count": len(text_records),
        "duplicate_messages": duplicate_messages,
        "filler_messages": filler_messages,
        "repetitive_messages": repetitive_messages,
        "burst_messages": burst_messages,
        "burst_starts": sorted(burst_starts),
        "rule_version": HYGIENE_RULE_VERSION,
    }


def _chain_depths(
    messages: Sequence[Mapping[str, Any]], edges: Sequence[Mapping[str, Any]]
) -> dict[str, int]:
    parent_by_child = {
        str(edge["child_message_id"]): str(edge["parent_message_id"]) for edge in edges
    }
    message_ids = {str(row["message_id"]) for row in messages}
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

    return {message_id: depth(message_id) for message_id in message_ids}


def prepare_structural_context(
    messages: Sequence[Mapping[str, Any]],
    identities: Mapping[str, Mapping[str, Any]],
    edges: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    _validate_inputs(messages, identities, edges)
    message_by_id = {str(row["message_id"]): row for row in messages}
    question_ids = {
        message_id
        for message_id, row in message_by_id.items()
        if is_question(str(row.get("text_original") or ""))
    }
    replied_question_ids = {
        str(edge["parent_message_id"])
        for edge in edges
        if str(edge["parent_message_id"]) in question_ids
    }
    return {
        "message_by_id": message_by_id,
        "edges_by_child": {str(edge["child_message_id"]): edge for edge in edges},
        "question_ids": question_ids,
        "question_with_resolved_reply": replied_question_ids,
        "chain_depths": _chain_depths(messages, edges),
        "hygiene": _hygiene_flags(messages, identities),
    }


def _top_concentration(ids: Iterable[str]) -> float:
    counts = Counter(ids)
    return _rate(max(counts.values()), sum(counts.values())) if counts else 0.0


def _aggregate_window(
    rows: Sequence[Mapping[str, Any]],
    identities: Mapping[str, Mapping[str, Any]],
    context: Mapping[str, Any],
    *,
    start: datetime,
    end: datetime,
    grain_minutes: int,
) -> dict[str, Any]:
    message_ids = [str(row["message_id"]) for row in rows]
    id_rows = [identities[message_id] for message_id in message_ids]
    edge_rows = [
        context["edges_by_child"][message_id]
        for message_id in message_ids
        if message_id in context["edges_by_child"]
    ]
    message_count = len(rows)
    state_counts = Counter(str(row["reply_state"]) for row in id_rows)
    confidence_counts = Counter(str(row["identity_confidence"]) for row in id_rows)
    high_ids = {
        str(row["resolved_identity_id"]) for row in id_rows if row["identity_confidence"] == "high"
    }
    broader_ids = {str(row["resolved_identity_id"]) for row in id_rows}
    high_message_ids = [
        str(row["resolved_identity_id"]) for row in id_rows if row["identity_confidence"] == "high"
    ]
    broader_message_ids = [str(row["resolved_identity_id"]) for row in id_rows]
    resolved = state_counts["resolved_reply"]
    unresolved = state_counts["unresolved_reply"]
    latencies = [float(edge["response_latency_seconds"]) for edge in edge_rows]
    relations = Counter(str(edge["author_relation"]) for edge in edge_rows)
    hygiene = context["hygiene"]
    id_set = set(message_ids)
    duplicate_count = len(id_set & hygiene["duplicate_messages"])
    repetitive_count = len(id_set & hygiene["repetitive_messages"])
    filler_count = len(id_set & hygiene["filler_messages"])
    burst_message_count = len(id_set & hygiene["burst_messages"])
    question_count = len(id_set & context["question_ids"])
    replied_questions = len(id_set & context["question_with_resolved_reply"])
    text_bearing_count = sum(bool(str(row.get("text_original") or "").strip()) for row in rows)
    media_only_count = sum(
        not str(row.get("text_original") or "").strip() and bool(row.get("media_refs"))
        for row in rows
    )
    high_responders = {
        str(edge["child_resolved_identity_id"])
        for edge in edge_rows
        if edge["child_identity_confidence"] == "high"
    }
    high_recipients = {
        str(edge["parent_resolved_identity_id"])
        for edge in edge_rows
        if edge["parent_identity_confidence"] == "high"
    }
    broader_responders = {str(edge["child_resolved_identity_id"]) for edge in edge_rows}
    broader_recipients = {str(edge["parent_resolved_identity_id"]) for edge in edge_rows}
    depths = [int(context["chain_depths"][message_id]) for message_id in message_ids]
    burst_starts = hygiene["burst_starts"]
    start_utc = start.astimezone(UTC)
    end_utc = end.astimezone(UTC)
    burst_event_count = bisect.bisect_left(burst_starts, end_utc) - bisect.bisect_left(
        burst_starts, start_utc
    )
    forwarded_count = sum(row.get("forwarded_from") is not None for row in rows)
    hyperlink_message_count = sum(bool(row.get("links")) for row in rows)
    media_message_count = sum(bool(row.get("media_refs")) for row in rows)
    reaction_message_count = sum(bool(row.get("reaction_present")) for row in rows)
    edited_metadata_message_count = sum(bool(row.get("edited_metadata_present")) for row in rows)
    return {
        "window_start": _iso(start),
        "window_end": _iso(end),
        "grain_minutes": grain_minutes,
        "message_count": message_count,
        "message_rate_per_minute": _rate(message_count, grain_minutes),
        "text_bearing_count": text_bearing_count,
        "media_only_count": media_only_count,
        "resolved_reply_count": resolved,
        "unresolved_reply_count": unresolved,
        "non_reply_count": state_counts["non_reply"],
        "resolved_reply_share": _rate(resolved, message_count),
        "reply_resolution_rate": _rate(resolved, resolved + unresolved),
        "response_latency_median_seconds": _median(latencies) if latencies else None,
        "response_latency_p90_seconds": _nearest_rank(latencies, 0.9) if latencies else None,
        "high_confidence_identity_count": len(high_ids),
        "broader_pseudonymous_identity_count": len(broader_ids),
        "identity_high_message_count": confidence_counts["high"],
        "identity_medium_message_count": confidence_counts["medium"],
        "identity_low_message_count": confidence_counts["low"],
        "identity_high_message_coverage": _rate(confidence_counts["high"], message_count),
        "identity_medium_message_coverage": _rate(confidence_counts["medium"], message_count),
        "identity_low_message_coverage": _rate(confidence_counts["low"], message_count),
        "high_confidence_responder_count": len(high_responders),
        "broader_pseudonymous_responder_count": len(broader_responders),
        "high_confidence_recipient_count": len(high_recipients),
        "broader_pseudonymous_recipient_count": len(broader_recipients),
        "self_reply_edge_count": relations["self"],
        "cross_author_reply_edge_count": relations["cross_author"],
        "uncertain_reply_edge_count": relations["uncertain"],
        "question_count": question_count,
        "question_with_resolved_reply_count": replied_questions,
        "question_structural_reply_rate": _rate(replied_questions, question_count),
        "exact_duplicate_message_count": duplicate_count,
        "exact_duplicate_rate": _rate(duplicate_count, message_count),
        "repetitive_content_message_count": repetitive_count,
        "repetitive_content_rate": _rate(repetitive_count, message_count),
        "filler_message_count": filler_count,
        "filler_rate": _rate(filler_count, message_count),
        "burst_event_count": burst_event_count,
        "burst_message_count": burst_message_count,
        "burst_message_rate": _rate(burst_message_count, message_count),
        "top_high_confidence_identity_concentration": _top_concentration(high_message_ids),
        "top_broader_pseudonymous_identity_concentration": _top_concentration(broader_message_ids),
        "forwarded_message_count": forwarded_count,
        "forwarded_message_rate": _rate(forwarded_count, message_count),
        "hyperlink_message_count": hyperlink_message_count,
        "hyperlink_message_rate": _rate(hyperlink_message_count, message_count),
        "hyperlink_count": sum(len(row.get("links") or []) for row in rows),
        "media_message_count": media_message_count,
        "media_message_rate": _rate(media_message_count, message_count),
        "media_reference_count": sum(len(row.get("media_refs") or []) for row in rows),
        "reaction_message_count": reaction_message_count,
        "reaction_message_rate": _rate(reaction_message_count, message_count),
        "edited_metadata_message_count": edited_metadata_message_count,
        "edited_metadata_message_rate": _rate(edited_metadata_message_count, message_count),
        "max_reply_chain_depth_edges": max(depths, default=0),
    }


def build_timeline(
    messages: Sequence[Mapping[str, Any]],
    identities: Mapping[str, Mapping[str, Any]],
    edges: Sequence[Mapping[str, Any]],
    *,
    grain_minutes: int,
    timezone_name: str = TIMEZONE_NAME,
    include_empty: bool = False,
    context: Mapping[str, Any] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if grain_minutes <= 0 or 1440 % grain_minutes:
        raise ValueError("grain_minutes must be a positive divisor of one day")
    if not messages:
        return [], {
            "total_window_count": 0,
            "nonempty_window_count": 0,
            "empty_window_count": 0,
        }
    timezone = ZoneInfo(timezone_name)
    structural = context or prepare_structural_context(messages, identities, edges)
    grouped: dict[datetime, list[Mapping[str, Any]]] = defaultdict(list)
    for row in messages:
        start = _bucket_start(_parse_timestamp(row["timestamp"]), grain_minutes, timezone)
        grouped[start].append(row)
    first = min(grouped)
    last = max(grouped)
    cursor = first
    timeline: list[dict[str, Any]] = []
    total = 0
    while cursor <= last:
        end = cursor + timedelta(minutes=grain_minutes)
        bucket_rows = grouped.get(cursor, [])
        total += 1
        if bucket_rows or include_empty:
            timeline.append(
                _aggregate_window(
                    bucket_rows,
                    identities,
                    structural,
                    start=cursor,
                    end=end,
                    grain_minutes=grain_minutes,
                )
            )
        cursor = end
    nonempty = len(grouped)
    return timeline, {
        "grain_minutes": grain_minutes,
        "timezone": timezone_name,
        "coverage_start": _iso(first),
        "coverage_end": _iso(last + timedelta(minutes=grain_minutes)),
        "total_window_count": total,
        "nonempty_window_count": nonempty,
        "empty_window_count": total - nonempty,
        "serialized_window_policy": "all" if include_empty else "nonempty_only",
    }


def _fact(metric: str, operator: str, threshold: Any, actual: Any) -> dict[str, Any]:
    return {"metric": metric, "operator": operator, "threshold": threshold, "actual": actual}


def _candidate(row: Mapping[str, Any], facts: list[dict[str, Any]]) -> dict[str, Any]:
    metric_names = (
        "message_count",
        "resolved_reply_count",
        "unresolved_reply_count",
        "resolved_reply_share",
        "reply_resolution_rate",
        "question_count",
        "question_with_resolved_reply_count",
        "high_confidence_identity_count",
        "identity_high_message_coverage",
        "top_high_confidence_identity_concentration",
        "top_broader_pseudonymous_identity_concentration",
        "exact_duplicate_rate",
        "repetitive_content_rate",
        "filler_rate",
        "burst_message_rate",
        "max_reply_chain_depth_edges",
    )
    return {
        "window_start": row["window_start"],
        "window_end": row["window_end"],
        "grain_minutes": row["grain_minutes"],
        "trigger_facts": facts,
        "metrics": {name: row.get(name) for name in metric_names},
    }


def _thresholds(nonempty: Sequence[Mapping[str, Any]]) -> dict[str, int | float]:
    def values(name: str) -> list[float]:
        return [float(row.get(name, 0) or 0) for row in nonempty]

    return {
        "message_p25": _nearest_rank(values("message_count"), 0.25),
        "message_p50": _nearest_rank(values("message_count"), 0.50),
        "message_p75": _nearest_rank(values("message_count"), 0.75),
        "message_p90": _nearest_rank(values("message_count"), 0.90),
        "resolved_p75": _nearest_rank(values("resolved_reply_count"), 0.75),
        "resolved_p90": _nearest_rank(values("resolved_reply_count"), 0.90),
        "reply_share_p50": _nearest_rank(values("resolved_reply_share"), 0.50),
        "question_p90": _nearest_rank(values("question_count"), 0.90),
        "high_identity_p90": _nearest_rank(values("high_confidence_identity_count"), 0.90),
        "high_coverage_p50": _nearest_rank(values("identity_high_message_coverage"), 0.50),
        "high_concentration_p50": _nearest_rank(
            values("top_high_confidence_identity_concentration"), 0.50
        ),
        "broader_concentration_p90": _nearest_rank(
            values("top_broader_pseudonymous_identity_concentration"), 0.90
        ),
        "duplicate_p90": _nearest_rank(values("exact_duplicate_rate"), 0.90),
        "repetition_p90": _nearest_rank(values("repetitive_content_rate"), 0.90),
        "filler_p90": _nearest_rank(values("filler_rate"), 0.90),
        "burst_p90": _nearest_rank(values("burst_message_rate"), 0.90),
        "depth_p90": _nearest_rank(values("max_reply_chain_depth_edges"), 0.90),
    }


def build_candidate_windows(
    timeline_rows: Sequence[Mapping[str, Any]], *, preceding_baseline_windows: int = 24
) -> dict[str, list[dict[str, Any]]]:
    """Rank category candidates lexicographically; never calculate a composite score."""

    if preceding_baseline_windows < 1:
        raise ValueError("preceding_baseline_windows must be positive")
    nonempty = [row for row in timeline_rows if int(row.get("message_count", 0)) > 0]
    thresholds = _thresholds(nonempty)
    candidates: dict[str, list[dict[str, Any]]] = {
        "activity_surge": [],
        "reply_heavy": [],
        "question_support_heavy": [],
        "broad_participation": [],
        "repetition_dominated": [],
        "long_conversation_chain": [],
        "quiet_baseline": [],
    }

    for index, row in enumerate(timeline_rows):
        count = int(row.get("message_count", 0))
        if not count:
            continue
        baseline_rows = timeline_rows[max(0, index - preceding_baseline_windows) : index]
        baseline = _median([int(item.get("message_count", 0)) for item in baseline_rows])

        if baseline_rows and count >= thresholds["message_p90"]:
            ratio = _rate(count, baseline) if baseline else None
            if (baseline and ratio >= 2.0) or (not baseline and count >= thresholds["message_p90"]):
                facts = [
                    _fact("message_count", ">= nonempty p90", thresholds["message_p90"], count),
                    _fact(
                        "message_count / preceding_baseline_median",
                        ">= 2.0 or baseline is zero",
                        2.0,
                        ratio,
                    ),
                    _fact(
                        "preceding_baseline_window_count",
                        "= requested lookback unless series start",
                        preceding_baseline_windows,
                        len(baseline_rows),
                    ),
                ]
                item = _candidate(row, facts)
                item["preceding_baseline_median_message_count"] = baseline
                item["activity_surge_ratio"] = ratio
                candidates["activity_surge"].append(item)

        resolved = int(row.get("resolved_reply_count", 0))
        reply_share = float(row.get("resolved_reply_share", 0) or 0)
        if resolved >= thresholds["resolved_p90"] and reply_share >= thresholds["reply_share_p50"]:
            candidates["reply_heavy"].append(
                _candidate(
                    row,
                    [
                        _fact(
                            "resolved_reply_count",
                            ">= nonempty p90",
                            thresholds["resolved_p90"],
                            resolved,
                        ),
                        _fact(
                            "resolved_reply_share",
                            ">= nonempty median",
                            thresholds["reply_share_p50"],
                            reply_share,
                        ),
                    ],
                )
            )

        questions = int(row.get("question_count", 0))
        replied_questions = int(row.get("question_with_resolved_reply_count", 0))
        if questions >= thresholds["question_p90"] and resolved > 0:
            candidates["question_support_heavy"].append(
                _candidate(
                    row,
                    [
                        _fact(
                            "question_count",
                            ">= nonempty p90",
                            thresholds["question_p90"],
                            questions,
                        ),
                        _fact("resolved_reply_count", "> 0", 0, resolved),
                        _fact(
                            "question_with_resolved_reply_count",
                            "observed",
                            None,
                            replied_questions,
                        ),
                    ],
                )
            )

        high_identities = int(row.get("high_confidence_identity_count", 0))
        high_coverage = float(row.get("identity_high_message_coverage", 0) or 0)
        concentration = float(row.get("top_high_confidence_identity_concentration", 0) or 0)
        if (
            high_identities >= thresholds["high_identity_p90"]
            and high_coverage >= thresholds["high_coverage_p50"]
            and concentration <= thresholds["high_concentration_p50"]
        ):
            candidates["broad_participation"].append(
                _candidate(
                    row,
                    [
                        _fact(
                            "high_confidence_identity_count",
                            ">= nonempty p90",
                            thresholds["high_identity_p90"],
                            high_identities,
                        ),
                        _fact(
                            "identity_high_message_coverage",
                            ">= nonempty median",
                            thresholds["high_coverage_p50"],
                            high_coverage,
                        ),
                        _fact(
                            "top_high_confidence_identity_concentration",
                            "<= nonempty median",
                            thresholds["high_concentration_p50"],
                            concentration,
                        ),
                    ],
                )
            )

        repetition_facts = []
        for name, threshold_name in (
            ("repetitive_content_rate", "repetition_p90"),
            ("exact_duplicate_rate", "duplicate_p90"),
            ("filler_rate", "filler_p90"),
            ("burst_message_rate", "burst_p90"),
            (
                "top_broader_pseudonymous_identity_concentration",
                "broader_concentration_p90",
            ),
        ):
            actual = float(row.get(name, 0) or 0)
            threshold = thresholds[threshold_name]
            if actual >= threshold and actual > 0:
                repetition_facts.append(_fact(name, ">= nonempty p90", threshold, actual))
        if count >= thresholds["message_p75"] and repetition_facts:
            candidates["repetition_dominated"].append(
                _candidate(
                    row,
                    [
                        _fact(
                            "message_count",
                            ">= nonempty p75",
                            thresholds["message_p75"],
                            count,
                        ),
                        *repetition_facts,
                    ],
                )
            )

        depth = int(row.get("max_reply_chain_depth_edges", 0))
        depth_threshold = max(3, int(thresholds["depth_p90"]))
        if depth >= depth_threshold:
            candidates["long_conversation_chain"].append(
                _candidate(
                    row,
                    [
                        _fact(
                            "max_reply_chain_depth_edges",
                            ">= depth threshold",
                            depth_threshold,
                            depth,
                        )
                    ],
                )
            )

        if thresholds["message_p25"] <= count <= thresholds["message_p50"] and baseline_rows:
            stability_delta = abs(count - baseline)
            stability_limit = max(2, 0.5 * float(baseline))
            if stability_delta <= stability_limit:
                item = _candidate(
                    row,
                    [
                        _fact(
                            "message_count",
                            "between nonempty p25 and p50",
                            [thresholds["message_p25"], thresholds["message_p50"]],
                            count,
                        ),
                        _fact(
                            "absolute delta from preceding baseline median",
                            "<= stability limit",
                            stability_limit,
                            stability_delta,
                        ),
                    ],
                )
                item["preceding_baseline_median_message_count"] = baseline
                item["absolute_baseline_delta"] = stability_delta
                candidates["quiet_baseline"].append(item)

    candidates["activity_surge"].sort(
        key=lambda item: (
            item["activity_surge_ratio"] is None,
            item["activity_surge_ratio"] or 0,
            item["metrics"]["message_count"],
        ),
        reverse=True,
    )
    candidates["reply_heavy"].sort(
        key=lambda item: (
            item["metrics"]["resolved_reply_count"],
            item["metrics"]["resolved_reply_share"],
        ),
        reverse=True,
    )
    candidates["question_support_heavy"].sort(
        key=lambda item: (
            item["metrics"]["question_count"],
            item["metrics"]["question_with_resolved_reply_count"],
        ),
        reverse=True,
    )
    candidates["broad_participation"].sort(
        key=lambda item: (
            -item["metrics"]["high_confidence_identity_count"],
            item["metrics"]["top_high_confidence_identity_concentration"],
        )
    )
    candidates["repetition_dominated"].sort(
        key=lambda item: (
            item["metrics"]["repetitive_content_rate"],
            item["metrics"]["exact_duplicate_rate"],
            item["metrics"]["top_broader_pseudonymous_identity_concentration"],
            item["metrics"]["message_count"],
        ),
        reverse=True,
    )
    candidates["long_conversation_chain"].sort(
        key=lambda item: (
            item["metrics"]["max_reply_chain_depth_edges"],
            item["metrics"]["resolved_reply_count"],
        ),
        reverse=True,
    )
    candidates["quiet_baseline"].sort(
        key=lambda item: (
            item["absolute_baseline_delta"],
            -item["metrics"]["high_confidence_identity_count"],
            item["window_start"],
        )
    )
    return {name: items[:25] for name, items in candidates.items()}


def _period_metrics(
    messages: Sequence[Mapping[str, Any]],
    identities: Mapping[str, Mapping[str, Any]],
    context: Mapping[str, Any],
    start: datetime,
    end: datetime,
) -> dict[str, Any]:
    selected = [
        row
        for row in messages
        if start.astimezone(UTC) <= _parse_timestamp(row["timestamp"]) < end.astimezone(UTC)
    ]
    aggregate = _aggregate_window(
        selected,
        identities,
        context,
        start=start,
        end=end,
        grain_minutes=int((end - start).total_seconds() / 60),
    )
    keep = (
        "message_count",
        "resolved_reply_count",
        "unresolved_reply_count",
        "reply_resolution_rate",
        "high_confidence_identity_count",
        "broader_pseudonymous_identity_count",
        "identity_high_message_coverage",
        "question_count",
        "question_with_resolved_reply_count",
        "repetitive_content_rate",
        "exact_duplicate_rate",
        "filler_rate",
        "burst_message_rate",
        "top_broader_pseudonymous_identity_concentration",
    )
    return {
        "window_start": _iso(start),
        "window_end": _iso(end),
        **{name: aggregate[name] for name in keep},
    }


def _period_comparison(
    before: Mapping[str, Any], after: Mapping[str, Any]
) -> dict[str, int | float | None]:
    count_fields = (
        "message_count",
        "resolved_reply_count",
        "unresolved_reply_count",
        "high_confidence_identity_count",
        "broader_pseudonymous_identity_count",
        "question_count",
        "question_with_resolved_reply_count",
    )
    rate_fields = (
        "reply_resolution_rate",
        "identity_high_message_coverage",
        "repetitive_content_rate",
        "exact_duplicate_rate",
        "filler_rate",
        "burst_message_rate",
        "top_broader_pseudonymous_identity_concentration",
    )
    comparison: dict[str, int | float | None] = {
        f"{name}_delta": int(after[name]) - int(before[name]) for name in count_fields
    }
    comparison.update(
        {
            f"{name}_delta": round(float(after[name]) - float(before[name]), 12)
            for name in rate_fields
        }
    )
    comparison["message_count_ratio"] = (
        _rate(int(after["message_count"]), int(before["message_count"]))
        if before["message_count"]
        else None
    )
    return comparison


def build_blog_alignment(
    messages: Sequence[Mapping[str, Any]],
    identities: Mapping[str, Mapping[str, Any]],
    edges: Sequence[Mapping[str, Any]],
    events: Sequence[Mapping[str, Any]],
    *,
    timezone_name: str = TIMEZONE_NAME,
    context: Mapping[str, Any] | None = None,
) -> list[dict[str, Any]]:
    timezone = ZoneInfo(timezone_name)
    structural = context or prepare_structural_context(messages, identities, edges)
    output: list[dict[str, Any]] = []
    for event in events:
        publication_date = date.fromisoformat(str(event["official_catalog_publication_date"]))
        anchor = datetime.combine(publication_date, time(hour=12), tzinfo=timezone)
        windows: dict[str, Any] = {}
        trigger_facts: list[dict[str, Any]] = []
        for hours in (24, 72):
            delta = timedelta(hours=hours)
            before = _period_metrics(messages, identities, structural, anchor - delta, anchor)
            after = _period_metrics(messages, identities, structural, anchor, anchor + delta)
            comparison = _period_comparison(before, after)
            windows[f"pm{hours}h"] = {
                "before": before,
                "after": after,
                "comparison": comparison,
            }
            if hours == 72:
                if after["message_count"] >= max(30, 1.75 * before["message_count"]):
                    trigger_facts.append(
                        _fact(
                            "post_72h_message_count",
                            ">= max(30, 1.75x pre_72h)",
                            max(30, 1.75 * before["message_count"]),
                            after["message_count"],
                        )
                    )
                for metric, threshold in (
                    ("resolved_reply_count", 15),
                    ("high_confidence_identity_count", 10),
                    ("question_count", 15),
                    ("question_with_resolved_reply_count", 10),
                ):
                    actual = int(comparison[f"{metric}_delta"])
                    if actual >= threshold:
                        trigger_facts.append(
                            _fact(
                                f"post_minus_pre_72h_{metric}", f">= {threshold}", threshold, actual
                            )
                        )
                burst_delta_72h = float(comparison["burst_message_rate_delta"])
                if burst_delta_72h >= 0.1:
                    trigger_facts.append(
                        _fact(
                            "post_minus_pre_72h_burst_message_rate",
                            ">= 0.1",
                            0.1,
                            burst_delta_72h,
                        )
                    )
                continue
            if hours != 24:
                continue
            if after["message_count"] >= max(10, 2 * before["message_count"]):
                trigger_facts.append(
                    _fact(
                        "post_24h_message_count",
                        ">= max(10, 2x pre_24h)",
                        max(10, 2 * before["message_count"]),
                        after["message_count"],
                    )
                )
            resolved_delta = after["resolved_reply_count"] - before["resolved_reply_count"]
            if resolved_delta >= 5:
                trigger_facts.append(
                    _fact("post_minus_pre_24h_resolved_reply_count", ">= 5", 5, resolved_delta)
                )
            identity_delta = (
                after["high_confidence_identity_count"] - before["high_confidence_identity_count"]
            )
            if identity_delta >= 5:
                trigger_facts.append(
                    _fact(
                        "post_minus_pre_24h_high_confidence_identity_count",
                        ">= 5",
                        5,
                        identity_delta,
                    )
                )
            question_delta = after["question_count"] - before["question_count"]
            if question_delta >= 5:
                trigger_facts.append(
                    _fact("post_minus_pre_24h_question_count", ">= 5", 5, question_delta)
                )
            burst_delta = after["burst_message_rate"] - before["burst_message_rate"]
            if burst_delta >= 0.1:
                trigger_facts.append(
                    _fact(
                        "post_minus_pre_24h_burst_message_rate",
                        ">= 0.1",
                        0.1,
                        round(burst_delta, 12),
                    )
                )
        observed_pm72 = (
            windows["pm72h"]["before"]["message_count"] + windows["pm72h"]["after"]["message_count"]
        )
        if observed_pm72 == 0:
            coverage_status = "no_observed_messages"
        elif observed_pm72 < 10:
            coverage_status = "insufficient_observed_activity"
        else:
            coverage_status = "evaluated"
        if coverage_status != "evaluated":
            trigger_facts = []
        output.append(
            {
                "official_catalog_publication_date": publication_date.isoformat(),
                "official_catalog_title": event.get("official_catalog_title"),
                "official_catalog_category": event.get("official_catalog_category"),
                "analysis_anchor": _iso(anchor),
                "anchor_policy": (
                    "date-only official catalog value anchored at 12:00 Asia/Shanghai "
                    "for symmetric comparison"
                ),
                "anchor_is_actual_publication_time": False,
                "coverage_status": coverage_status,
                "observed_message_count_pm72h": observed_pm72,
                **windows,
                "candidate_event_window": bool(trigger_facts),
                "candidate_trigger_facts": trigger_facts,
                "interpretation": BLOG_ALIGNMENT_INTERPRETATION,
            }
        )
    return output


def _load_source_artifacts(
    canonical_root: Path, identity_root: Path
) -> tuple[
    list[dict[str, Any]],
    dict[str, dict[str, Any]],
    list[dict[str, Any]],
    dict[str, Any],
    dict[str, Any],
]:
    canonical_manifest_path = canonical_root / "dataset_manifest.json"
    identity_manifest_path = identity_root / "identity_manifest.json"
    canonical_manifest = json.loads(canonical_manifest_path.read_text(encoding="utf-8"))
    identity_manifest = json.loads(identity_manifest_path.read_text(encoding="utf-8"))
    source_paths = {
        "canonical_messages": canonical_root / "messages.jsonl",
        "identity_messages": identity_root / "message_identities.jsonl",
        "identity_edges": identity_root / "reply_edges.jsonl",
    }
    actual_hashes = {name: _sha256(path) for name, path in source_paths.items()}
    expected_hashes = {
        "canonical_messages": canonical_manifest["artifact_sha256"]["messages.jsonl"],
        "identity_messages": identity_manifest["artifact_sha256"]["message_identities.jsonl"],
        "identity_edges": identity_manifest["artifact_sha256"]["reply_edges.jsonl"],
    }
    if actual_hashes != expected_hashes:
        raise ValueError(
            f"source artifact hash mismatch: expected={expected_hashes}, actual={actual_hashes}"
        )

    messages = _jsonl(source_paths["canonical_messages"])
    for row in messages:
        row["timestamp"] = _parse_timestamp(row["timestamp"])
    identity_rows = _jsonl(source_paths["identity_messages"])
    identities = {str(row["message_id"]): row for row in identity_rows}
    edges = _jsonl(source_paths["identity_edges"])
    expected_count = int(canonical_manifest["profile"]["ordinary_message_count"])
    if len(messages) != expected_count:
        raise ValueError("canonical message count does not match dataset manifest")
    if len(messages) != int(identity_manifest["profile"]["message_count"]):
        raise ValueError("identity message count does not match identity manifest")
    _validate_inputs(messages, identities, edges)
    return messages, identities, edges, canonical_manifest, identity_manifest


def _write_json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _write_csv(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    if not rows:
        raise ValueError(f"refusing to write empty timeline: {path.name}")
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def _window_key(item: Mapping[str, Any]) -> str:
    return str(item["window_start"])


def _candidate_dates(candidates: Mapping[str, Sequence[Mapping[str, Any]]]) -> set[str]:
    return {
        str(item["window_start"])[:10]
        for items in candidates.values()
        for item in items
        if isinstance(item, Mapping) and "window_start" in item
    }


def _temporally_diverse(
    items: Sequence[Mapping[str, Any]], limit: int, *, max_per_month: int = 2
) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    month_counts: Counter[str] = Counter()
    used: set[str] = set()
    for item in items:
        key = _window_key(item)
        month = key[:7]
        if key in used or month_counts[month] >= max_per_month:
            continue
        selected.append(dict(item))
        month_counts[month] += 1
        used.add(key)
        if len(selected) == limit:
            return selected
    for item in items:
        key = _window_key(item)
        if key in used:
            continue
        selected.append(dict(item))
        used.add(key)
        if len(selected) == limit:
            break
    return selected


def _build_recommendations(
    dense_hourly: Sequence[Mapping[str, Any]],
    daily_rows: Sequence[Mapping[str, Any]],
    candidates: Mapping[str, Sequence[Mapping[str, Any]]],
    blog_alignment: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    strong_keys = {
        _window_key(item)
        for category, items in candidates.items()
        if category != "quiet_baseline"
        for item in items
    }
    nonempty = [row for row in dense_hourly if int(row["message_count"]) > 0]
    message_thresholds = _thresholds(nonempty)

    def natural_eligible(item: Mapping[str, Any]) -> bool:
        metrics = item.get("metrics", item)
        return (
            int(metrics["message_count"]) >= max(5, message_thresholds["message_p25"])
            and float(metrics["identity_high_message_coverage"] or 0) >= 0.5
            and float(metrics["exact_duplicate_rate"] or 0) <= 0.5
            and float(metrics["repetitive_content_rate"] or 0) <= 0.5
            and float(metrics["filler_rate"] or 0) <= 0.5
            and float(metrics["burst_message_rate"] or 0) <= 0.8
            and float(metrics["top_broader_pseudonymous_identity_concentration"] or 0) <= 0.8
        )

    natural_pool = [item for item in candidates["quiet_baseline"] if natural_eligible(item)]
    for row in nonempty:
        key = _window_key(row)
        count = int(row["message_count"])
        if (
            key in strong_keys
            or not natural_eligible(row)
            or not (message_thresholds["message_p25"] <= count <= message_thresholds["message_p75"])
        ):
            continue
        natural_pool.append(
            _candidate(
                row,
                [
                    _fact(
                        "message_count",
                        "between nonempty p25 and p75",
                        [
                            message_thresholds["message_p25"],
                            message_thresholds["message_p75"],
                        ],
                        count,
                    ),
                    _fact("extreme_candidate_category", "not present", None, False),
                ],
            )
        )
    natural = _temporally_diverse(natural_pool, 8)

    challenge_pool: list[Mapping[str, Any]] = []
    challenge_categories = (
        "reply_heavy",
        "question_support_heavy",
        "long_conversation_chain",
        "broad_participation",
    )
    for rank in range(25):
        for category in challenge_categories:
            items = candidates[category]
            if rank >= len(items):
                continue
            item = dict(items[rank])
            item["challenge_category"] = category
            if float(item["metrics"]["identity_high_message_coverage"] or 0) < 0.5 or int(
                item["metrics"]["resolved_reply_count"]
            ) < max(5, int(message_thresholds["resolved_p75"])):
                continue
            challenge_pool.append(item)
    challenge = _temporally_diverse(challenge_pool, 8, max_per_month=3)

    blog_by_date = {str(item["official_catalog_publication_date"]): item for item in blog_alignment}
    candidate_dates = _candidate_dates(candidates)
    daily_nonempty = [row for row in daily_rows if int(row["message_count"]) > 0]
    daily_thresholds = _thresholds(daily_nonempty)
    hero_pool: list[dict[str, Any]] = []
    for row in daily_nonempty:
        local_date = str(row["window_start"])[:10]
        blog = blog_by_date.get(local_date)
        if float(row["identity_high_message_coverage"] or 0) < 0.5:
            continue
        facts: list[dict[str, Any]] = []
        if int(row["message_count"]) >= daily_thresholds["message_p90"]:
            facts.append(
                _fact(
                    "daily_message_count",
                    ">= nonempty daily p90",
                    daily_thresholds["message_p90"],
                    row["message_count"],
                )
            )
        if int(row["resolved_reply_count"]) >= daily_thresholds["resolved_p90"]:
            facts.append(
                _fact(
                    "daily_resolved_reply_count",
                    ">= nonempty daily p90",
                    daily_thresholds["resolved_p90"],
                    row["resolved_reply_count"],
                )
            )
        if int(row["high_confidence_identity_count"]) >= daily_thresholds["high_identity_p90"]:
            facts.append(
                _fact(
                    "daily_high_confidence_identity_count",
                    ">= nonempty daily p90",
                    daily_thresholds["high_identity_p90"],
                    row["high_confidence_identity_count"],
                )
            )
        if local_date in candidate_dates:
            facts.append(_fact("contains_ranked_hourly_candidate", "is true", True, True))
        if blog and blog["candidate_event_window"]:
            facts.append(_fact("blog_date_alignment_candidate", "is true", True, True))
        if len(facts) < 2:
            continue
        hero_pool.append(
            {
                "window_start": row["window_start"],
                "window_end": row["window_end"],
                "selection_tier": (
                    "official_blog_aligned_structural_candidate"
                    if blog and blog["candidate_event_window"]
                    else "structural_candidate_without_blog_alignment"
                ),
                "structural_evidence": facts,
                "metrics": {
                    "message_count": row["message_count"],
                    "resolved_reply_count": row["resolved_reply_count"],
                    "unresolved_reply_count": row["unresolved_reply_count"],
                    "question_count": row["question_count"],
                    "high_confidence_identity_count": row["high_confidence_identity_count"],
                    "identity_high_message_coverage": row["identity_high_message_coverage"],
                    "repetitive_content_rate": row["repetitive_content_rate"],
                    "max_reply_chain_depth_edges": row["max_reply_chain_depth_edges"],
                },
                "official_blog_event": (
                    {
                        "publication_date": blog["official_catalog_publication_date"],
                        "title": blog["official_catalog_title"],
                        "category": blog["official_catalog_category"],
                        "temporal_correlation_only": True,
                    }
                    if blog
                    else None
                ),
            }
        )
    hero_pool.sort(
        key=lambda item: (
            item["selection_tier"] == "official_blog_aligned_structural_candidate",
            item["metrics"]["resolved_reply_count"],
            item["metrics"]["high_confidence_identity_count"],
            item["metrics"]["message_count"],
        ),
        reverse=True,
    )
    hero = _temporally_diverse(hero_pool, 5, max_per_month=2)
    return {
        "natural_behavior_validation": natural,
        "challenge_reply_validation": challenge,
        "hero_event_candidates": hero,
        "selection_contract": {
            "no_composite_score": True,
            "natural": (
                "quiet-baseline rank first, then non-extreme p25-p75 hourly windows; "
                "require >=50% high-confidence identity coverage and exclude extreme "
                "hygiene/concentration ratios; temporal spread caps two selections per "
                "month before fallback"
            ),
            "challenge": (
                "round-robin reply, question/reply, long-chain, and broad-participation "
                "ranks; require >=50% high-confidence identity message coverage and "
                f"resolved replies >= max(5, hourly p75={message_thresholds['resolved_p75']})"
            ),
            "hero": (
                "daily window requires >=50% high-confidence identity message coverage and "
                "at least two explicit structural triggers; Blog-aligned candidate tier sorts "
                "first, then resolved replies, high-confidence identity breadth, and message "
                "count lexicographically"
            ),
        },
    }


def _fmt_rate(value: float | int | None) -> str:
    return "n/a" if value is None else f"{100 * float(value):.1f}%"


def _window_table(items: Sequence[Mapping[str, Any]], metric_names: Sequence[str]) -> str:
    if not items:
        return "未发现满足显式阈值的窗口。"
    headers = ["窗口", *metric_names]
    lines = ["| " + " | ".join(headers) + " |", "|" + "---|" * len(headers)]
    for item in items:
        metrics = item.get("metrics", item)
        values = [str(item["window_start"])]
        for name in metric_names:
            value = metrics.get(name)
            if name.endswith("rate") or name.endswith("coverage") or name.endswith("concentration"):
                values.append(_fmt_rate(value))
            else:
                values.append("n/a" if value is None else str(value))
        lines.append("| " + " | ".join(values) + " |")
    return "\n".join(lines)


def _render_report(
    profile: Mapping[str, Any],
    candidates: Mapping[str, Sequence[Mapping[str, Any]]],
    blog_alignment: Sequence[Mapping[str, Any]],
    recommendations: Mapping[str, Any],
) -> str:
    overall = profile["overall"]
    distribution = profile["activity_reply_distribution"]
    aligned = [item for item in blog_alignment if item["candidate_event_window"]]
    natural = recommendations["natural_behavior_validation"]
    challenge = recommendations["challenge_reply_validation"]
    hero = recommendations["hero_event_candidates"]
    blog_dates = ", ".join(item["official_catalog_publication_date"] for item in aligned)
    coverage_counts = Counter(item["coverage_status"] for item in blog_alignment)
    activity_table = _window_table(
        candidates["activity_surge"][:5],
        ("message_count", "resolved_reply_count", "high_confidence_identity_count"),
    )
    reply_table = _window_table(
        candidates["reply_heavy"][:5],
        ("resolved_reply_count", "resolved_reply_share", "identity_high_message_coverage"),
    )
    quiet_table = _window_table(
        candidates["quiet_baseline"][:5],
        ("message_count", "resolved_reply_count", "high_confidence_identity_count"),
    )
    natural_table = _window_table(
        natural,
        ("message_count", "resolved_reply_count", "high_confidence_identity_count"),
    )
    challenge_table = _window_table(
        challenge,
        (
            "resolved_reply_count",
            "question_count",
            "max_reply_chain_depth_edges",
            "identity_high_message_coverage",
        ),
    )
    hero_table = _window_table(
        hero,
        (
            "message_count",
            "resolved_reply_count",
            "high_confidence_identity_count",
            "max_reply_chain_depth_edges",
        ),
    )
    return f"""# Blum CN Structural Profiling / Event Window Discovery

状态：**DETERMINISTIC STRUCTURAL PROFILING COMPLETE / REVIEW GATE**

本 Track 在 base `{profile["base_commit"]}` 上分析 canonical v1.0.0 与 identity v1.1.0 的
{overall["message_count"]:,} 条真实消息。没有运行 Topic、Behavior classifier、RAG、Signal、
LLM 或远程 provider；没有修改 production contract、M3/M4，也没有合并或推送。

## 1. 整体 CN community structural profile

- 时间范围：`{profile["coverage"]["start"]}` ～ `{profile["coverage"]["end"]}`，统一按
  `Asia/Shanghai` 分桶。
- text-bearing {overall["text_bearing_count"]:,}；media-only
  {overall["media_only_count"]:,}。
- reply 三分法：resolved {overall["resolved_reply_count"]:,}；unresolved
  {overall["unresolved_reply_count"]:,}；non-reply {overall["non_reply_count"]:,}；reply
  resolution rate {_fmt_rate(overall["reply_resolution_rate"])}。
- resolved latency：median {overall["response_latency_median_seconds"]:.0f}s；p90
  {overall["response_latency_p90_seconds"]:.0f}s。
- 全期 message rate {overall["message_rate_per_minute"]:.3f}/min（仅作结构性基线）；broader
  top-author concentration {_fmt_rate(overall["top_broader_pseudonymous_identity_concentration"])}，
  high-confidence subset concentration
  {_fmt_rate(overall["top_high_confidence_identity_concentration"])}。
- high-confidence pseudonymous identities
  {overall["high_confidence_identity_count"]:,}；broader export-local pseudonymous identities
  {overall["broader_pseudonymous_identity_count"]:,}。后者不是“真实人数”；message coverage 为
  high {_fmt_rate(overall["identity_high_message_coverage"])} / medium
  {_fmt_rate(overall["identity_medium_message_coverage"])} / low
  {_fmt_rate(overall["identity_low_message_coverage"])}。
- resolved edges：self {overall["self_reply_edge_count"]:,} / cross-author
  {overall["cross_author_reply_edge_count"]:,} / uncertain
  {overall["uncertain_reply_edge_count"]:,}。低/中置信 endpoint 不被强行判为 self/cross。
- unique responders：high-confidence {overall["high_confidence_responder_count"]:,} / broader
  pseudonymous {overall["broader_pseudonymous_responder_count"]:,}；unique recipients：
  high-confidence {overall["high_confidence_recipient_count"]:,} / broader pseudonymous
  {overall["broader_pseudonymous_recipient_count"]:,}。
- deterministic text/structure facts：question {overall["question_count"]:,}；有至少一个 resolved
  child 的 question {overall["question_with_resolved_reply_count"]:,}；exact duplicate
  {_fmt_rate(overall["exact_duplicate_rate"])}；repetitive
  {_fmt_rate(overall["repetitive_content_rate"])}；filler
  {_fmt_rate(overall["filler_rate"])}；burst-message
  {_fmt_rate(overall["burst_message_rate"])}。
- forwarded {_fmt_rate(overall["forwarded_message_rate"])}；hyperlink-message
  {_fmt_rate(overall["hyperlink_message_rate"])}；media-message
  {_fmt_rate(overall["media_message_rate"])}。

这些指标描述结构与数据覆盖，不把 message volume 解释为 community health。

## 2. Activity / reply 时间分布

已生成 5min、15min、1hour、1day 四套 sparse non-empty aggregate timeline；空桶数量保留在
`timeline_summary.json`，因此 quiet baseline 不会因 sparse 导出而丢失。

本地小时分布中，message count 最高的 hour-of-day 是
`{distribution["peak_message_local_hour"]:02d}:00`，resolved replies 最高的是
`{distribution["peak_resolved_reply_local_hour"]:02d}:00`。这只是跨日期聚合，不代表健康度或
人员表现。

## 3. 代表性 surge / reply-heavy / quiet windows

Activity Surge（按“前序 24 个 1h 桶 median + 显式倍数阈值”）：

{activity_table}

Reply-heavy：

{reply_table}

Quiet baseline：

{quiet_table}

每个候选在 `candidate_windows.json` 保留 trigger facts。排序为类别内显式 lexicographic
ordering；没有综合 score。

## 4. Historical Blog 日期周围的结构变化

读取 `blum-knowledge-acquisition@9335b3f` 的 Historical Blog aggregate/report，只使用 10 个
date-only 官方 catalog event 做时间对齐。由于没有 precise publication time，分析把日期锚定在
北京时间 12:00，再对称比较 ±24h 与 ±72h；该锚点不是实际发布时间。

其中 {coverage_counts["evaluated"]}/10 个日期有足够 ±72h observed activity 可评估；
{coverage_counts["insufficient_observed_activity"]} 个日期因观测消息少于 10 条标为 insufficient，
{coverage_counts["no_observed_messages"]} 个日期完全无观测消息。{len(aligned)}/10 个日期触发至少一个
预注册的 post-vs-pre 24h 结构条件。触发日期：
{blog_dates or "无"}。完整 pre/post activity、reply、identity breadth、question/reply、
repetition/burst facts 见 `blog_event_alignment.json`。

这是 temporal correlation，不能声称 Blog announcement 造成聊天变化。

## 5. 推荐给 M3 的 ZH validation windows

### A. Natural Behavior Validation

共 {len(natural)} 个普通真实 1h 窗口，优先稳定 quiet baseline，再按 p25～p75 非极端窗口补齐；
要求 high-confidence identity coverage ≥50%，并过滤极端 hygiene/concentration 比例。先限制每月
最多 2 个以保留时间跨度。没有人工读取正文挑“漂亮样本”。

{natural_table}

### B. Challenge / Reply Validation

共 {len(challenge)} 个 1h 窗口，从 reply-heavy、question/reply、long-chain、broad participation
四类轮转选择，并要求 high-confidence identity message coverage ≥50%、resolved replies 至少为
5 且不低于 hourly p75。

{challenge_table}

这些窗口只提供后续 M3 validation input；本 Track 没有运行 M3。

## 6. Hero Event candidates

共 {len(hero)} 个 1day 候选。每个要求 high-confidence identity message coverage ≥50% 且至少满足
两个结构 trigger；Blog-aligned candidate tier 优先，其后按 resolved replies、high-confidence
identity breadth、message count 依次排序，没有综合分。

{hero_table}

每个候选的官方 Blog 对应关系（若有）、结构 evidence 与选择层级保存在
`recommended_windows.json`。

## 7. 数据结构限制

- `resolved reply` 只证明 parent 在 canonical corpus 中，不证明问题在语义上已解决。
- Blog 只有 date-only publication metadata；12:00 anchor 是对称比较约定，不是发布时间。
- broader pseudonymous identity count 受 medium/low conservative anchors 影响，可能 over-split，
  不能称为真实人数。
- role labels 未评审，因此 User↔User、Mod↔User、per-Mod 和 contributor 指标 **Not implemented**。
- spam 没有可直接复用的 deterministic rule，本 Track 标为 **Not implemented**。
- question/support-heavy 只使用 punctuation/phrase question rule 与 resolved reply structure，不能
  推断 support quality、topic、sentiment、intent 或 correctness。
- hygiene text rules 只在 {profile["rule_contract"]["hygiene_eligible_text_message_count"]:,}
  条 text-bearing message 上复用；media-only 不会被误判为 filler/duplicate/repetitive。
- Historical Blog archive snapshot 来自 2025–2026，不能证明正文自 2024 publication 起未变。

## Reproducibility / privacy gate

- 输入 hash、规则版本、base commit、timeline 覆盖与 output hashes 见
  `profile_manifest.json` / `SHA256SUMS`。
- Git aggregate 中不包含聊天正文、真实用户名、display-name metadata 或 pseudonymous identity ID。
- private per-message intermediate 保持仓库外/ignored。
- 下一步是人工 review；本 Track 到此停止。
"""


def _hour_distribution(hourly_rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[int, Counter[str]] = defaultdict(Counter)
    for row in hourly_rows:
        hour = datetime.fromisoformat(str(row["window_start"])).hour
        grouped[hour]["message_count"] += int(row["message_count"])
        grouped[hour]["resolved_reply_count"] += int(row["resolved_reply_count"])
        grouped[hour]["unresolved_reply_count"] += int(row["unresolved_reply_count"])
    return [
        {
            "local_hour": hour,
            "message_count": grouped[hour]["message_count"],
            "resolved_reply_count": grouped[hour]["resolved_reply_count"],
            "unresolved_reply_count": grouped[hour]["unresolved_reply_count"],
        }
        for hour in range(24)
    ]


def _artifact_hashes(output_dir: Path, names: Sequence[str]) -> dict[str, str]:
    return {name: _sha256(output_dir / name) for name in names}


def _args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--canonical-root", type=Path, required=True)
    parser.add_argument("--identity-root", type=Path, required=True)
    parser.add_argument("--blog-events", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--base-commit", required=True)
    return parser.parse_args()


def main() -> None:
    args = _args()
    (
        messages,
        identities,
        edges,
        canonical_manifest,
        identity_manifest,
    ) = _load_source_artifacts(args.canonical_root, args.identity_root)
    events_document = json.loads(args.blog_events.read_text(encoding="utf-8"))
    events = events_document["events"]
    context = prepare_structural_context(messages, identities, edges)
    args.output_dir.mkdir(parents=True, exist_ok=True)

    timelines: dict[str, list[dict[str, Any]]] = {}
    timeline_summary: dict[str, Any] = {}
    dense_hourly: list[dict[str, Any]] = []
    for label, grain_minutes in GRAINS.items():
        rows, summary = build_timeline(
            messages,
            identities,
            edges,
            grain_minutes=grain_minutes,
            include_empty=label == "1h",
            context=context,
        )
        if label == "1h":
            dense_hourly = rows
            rows = [row for row in rows if row["message_count"] > 0]
            summary["serialized_window_policy"] = "nonempty_only"
        timelines[label] = rows
        timeline_summary[label] = summary

    candidates = build_candidate_windows(dense_hourly, preceding_baseline_windows=24)
    blog_alignment = build_blog_alignment(messages, identities, edges, events, context=context)
    recommendations = _build_recommendations(
        dense_hourly, timelines["1d"], candidates, blog_alignment
    )

    timezone = ZoneInfo(TIMEZONE_NAME)
    coverage_start = min(_parse_timestamp(row["timestamp"]) for row in messages).astimezone(
        timezone
    )
    coverage_end = max(_parse_timestamp(row["timestamp"]) for row in messages).astimezone(timezone)
    overall = _aggregate_window(
        messages,
        identities,
        context,
        start=coverage_start,
        end=coverage_end + timedelta(seconds=1),
        grain_minutes=max(1, int((coverage_end - coverage_start).total_seconds() / 60)),
    )
    hour_distribution = _hour_distribution(timelines["1h"])
    peak_message_hour = max(
        hour_distribution,
        key=lambda row: (row["message_count"], -row["local_hour"]),
    )["local_hour"]
    peak_reply_hour = max(
        hour_distribution,
        key=lambda row: (row["resolved_reply_count"], -row["local_hour"]),
    )["local_hour"]
    profile = {
        "profile_version": PROFILE_VERSION,
        "base_commit": args.base_commit,
        "coverage": {
            "start": _iso(coverage_start),
            "end": _iso(coverage_end),
            "timezone": TIMEZONE_NAME,
        },
        "overall": overall,
        "activity_reply_distribution": {
            "local_hour_of_day": hour_distribution,
            "peak_message_local_hour": peak_message_hour,
            "peak_resolved_reply_local_hour": peak_reply_hour,
            "top_activity_1h": sorted(
                timelines["1h"], key=lambda row: row["message_count"], reverse=True
            )[:10],
            "top_resolved_reply_1h": sorted(
                timelines["1h"],
                key=lambda row: row["resolved_reply_count"],
                reverse=True,
            )[:10],
            "top_activity_1d": sorted(
                timelines["1d"], key=lambda row: row["message_count"], reverse=True
            )[:10],
        },
        "identity_interpretation": IDENTITY_INTERPRETATION,
        "blog_alignment_interpretation": BLOG_ALIGNMENT_INTERPRETATION,
        "rule_contract": {
            "question_rule_id": QUESTION_RULE_ID,
            "question_rule_version": QUESTION_RULE_VERSION,
            "question_detection_method": QUESTION_DETECTION_METHOD,
            "hygiene_rule_version": HYGIENE_RULE_VERSION,
            "short_message_max_chars": DEFAULT_SHORT_MESSAGE_MAX_CHARS,
            "repeated_content_minimum": DEFAULT_REPEATED_CONTENT_MINIMUM,
            "burst_minimum_messages": DEFAULT_BURST_MINIMUM_MESSAGES,
            "burst_window_seconds": DEFAULT_BURST_WINDOW_SECONDS,
            "hygiene_eligible_text_message_count": context["hygiene"][
                "eligible_text_message_count"
            ],
            "spam": "Not implemented: no existing deterministic spam rule is reusable",
        },
        "input_hashes": {
            "canonical_messages_sha256": _sha256(args.canonical_root / "messages.jsonl"),
            "canonical_manifest_sha256": _sha256(args.canonical_root / "dataset_manifest.json"),
            "identity_messages_sha256": _sha256(args.identity_root / "message_identities.jsonl"),
            "identity_edges_sha256": _sha256(args.identity_root / "reply_edges.jsonl"),
            "identity_manifest_sha256": _sha256(args.identity_root / "identity_manifest.json"),
            "blog_event_input_sha256": _sha256(args.blog_events),
        },
        "data_quality": {
            "canonical_message_count_matches_manifest": (
                len(messages) == canonical_manifest["profile"]["ordinary_message_count"]
            ),
            "identity_message_count_matches_manifest": (
                len(identities) == identity_manifest["profile"]["message_count"]
            ),
            "identity_join_coverage": _rate(len(identities), len(messages)),
            "resolved_edge_count": len(edges),
            "negative_latency_count": sum(
                float(edge["response_latency_seconds"]) < 0 for edge in edges
            ),
            "private_message_text_persisted": False,
            "display_name_metadata_persisted": False,
            "pseudonymous_identity_ids_persisted": False,
        },
    }

    _write_json(args.output_dir / "structural_profile.json", profile)
    _write_json(args.output_dir / "timeline_summary.json", timeline_summary)
    _write_json(args.output_dir / "candidate_windows.json", candidates)
    _write_json(args.output_dir / "blog_event_alignment.json", blog_alignment)
    _write_json(args.output_dir / "recommended_windows.json", recommendations)
    for label, rows in timelines.items():
        _write_csv(args.output_dir / f"timeline_{label}.csv", rows)

    report = _render_report(profile, candidates, blog_alignment, recommendations)
    (args.output_dir / "VALIDATION_REPORT.md").write_text(report, encoding="utf-8")
    artifact_names = [
        "VALIDATION_REPORT.md",
        "blog_event_alignment.json",
        "candidate_windows.json",
        "recommended_windows.json",
        "structural_profile.json",
        "timeline_15m.csv",
        "timeline_1d.csv",
        "timeline_1h.csv",
        "timeline_5m.csv",
        "timeline_summary.json",
    ]
    manifest = {
        "profile_version": PROFILE_VERSION,
        "base_commit": args.base_commit,
        "status": "complete_stopped_at_review_gate",
        "source_contracts": {
            "canonical": "telegram-html-canonical-v1.0.0",
            "identity": "telegram-html-author-identity-v1.1",
            "historical_blog": events_document["version"],
        },
        "input_hashes": profile["input_hashes"],
        "timeline_summary": timeline_summary,
        "artifact_sha256": _artifact_hashes(args.output_dir, artifact_names),
        "privacy": profile["data_quality"],
        "not_implemented": [
            "spam deterministic rule",
            "Topic",
            "Behavior classifier",
            "RAG",
            "Signal",
            "LLM",
            "role-dependent User-Mod metrics",
        ],
    }
    _write_json(args.output_dir / "profile_manifest.json", manifest)
    checksum_names = [*artifact_names, "BLOG_EVENT_INPUT.json", "profile_manifest.json"]
    checksum_lines = [
        f"{digest}  {name}"
        for name, digest in sorted(_artifact_hashes(args.output_dir, checksum_names).items())
    ]
    (args.output_dir / "SHA256SUMS").write_text("\n".join(checksum_lines) + "\n", encoding="utf-8")
    print(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
