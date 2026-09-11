#!/usr/bin/env python3
# ruff: noqa: E501
"""Build aggregate-only CN/ES JSON intake, structural profiles, and M3 handoff."""

from __future__ import annotations

import argparse
import csv
import json
import os
import secrets
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from community_intelligence.importers.telegram_json_structural import (
    StructuralProjection,
    build_structural_projection,
    calculate_shared_period,
)
from community_intelligence.io import write_dataset
from community_intelligence.structural_profile import (
    GRAINS,
    PROFILE_VERSION,
    TIMEZONE_NAME,
    _aggregate_window,
    _build_recommendations,
    _sha256,
    _temporally_diverse,
    build_blog_alignment,
    build_candidate_windows,
    build_timeline,
    prepare_structural_context,
)

TRACK_VERSION = "blum-multilingual-json-intake-v1.0.0"
BASE_COMMIT = "09fd2464dc536d33286d1d033db57d8aa7e8454f"
COMMUNITIES = {
    "blum-cn": {"language": "zh", "label": "CN"},
    "blum-es": {"language": "es", "label": "ES"},
}
TIMELINE_METRICS = (
    "message_count",
    "message_rate_per_minute",
    "high_confidence_identity_count",
    "resolved_reply_count",
    "unresolved_reply_count",
    "question_count",
    "question_with_resolved_reply_count",
    "response_latency_median_seconds",
    "exact_duplicate_message_count",
    "repetitive_content_message_count",
    "filler_message_count",
    "burst_message_count",
    "top_high_confidence_identity_concentration",
)


def _json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def _write_json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _write_csv(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    if not rows:
        raise ValueError(f"refusing to write empty CSV: {path.name}")
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def _parse(value: str | datetime) -> datetime:
    parsed = datetime.fromisoformat(value) if isinstance(value, str) else value
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("timestamp must be timezone-aware")
    return parsed.astimezone(UTC)


def _rate(numerator: int | float, denominator: int | float) -> float:
    return round(numerator / denominator, 12) if denominator else 0.0


def _safe_public_provenance(private: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "source_path": private["source_path"],
        "extraction_timestamp": private["extraction_timestamp"],
        "extraction_method_version": private["extraction_method_version"],
        "source_file_size_at_extraction": private["source_file_size_at_extraction"],
        "source_file_mtime_ns_at_extraction": private["source_file_mtime_ns_at_extraction"],
        "snapshot_sha256": private["snapshot_sha256"],
        "included_chats": [
            {
                "snapshot_key": item["snapshot_key"],
                "name": item["name"],
                "source_byte_range": item["source_byte_range"],
                "source_byte_range_sha256": item["source_byte_range_sha256"],
                "snapshot_sha256": item["snapshot_sha256"],
            }
            for item in private["included_chats"]
        ],
        "stability": private["stability"],
        "privacy_note": "raw chat IDs remain in ignored private provenance only",
    }


def _salt(path: Path) -> str:
    if path.exists():
        value = path.read_text(encoding="utf-8").strip()
        if not value:
            raise ValueError("identity salt file is empty")
        return value
    path.parent.mkdir(parents=True, exist_ok=True)
    value = secrets.token_hex(32)
    descriptor = os.open(
        path,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_CLOEXEC", 0),
        0o600,
    )
    try:
        os.write(descriptor, f"{value}\n".encode())
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    return value


def _publish_or_validate_canonical(projection: StructuralProjection, destination: Path) -> None:
    if not destination.exists():
        if projection.dataset is None:
            raise ValueError("canonical dataset was not built for first publication")
        write_dataset(projection.dataset, destination)
        return
    observed = _json(destination / "manifest.json")
    expected = projection.audit["canonical_dataset"]
    if observed["source_sha256"] != expected["source_sha256"]:
        raise ValueError(f"existing canonical dataset has a different source hash: {destination}")
    if observed["message_count"] != expected["text_bearing_message_count"]:
        raise ValueError(f"existing canonical dataset has a different message count: {destination}")


def _filter_messages(
    projection: StructuralProjection, start: datetime, end_inclusive: datetime
) -> list[dict[str, Any]]:
    return [
        row for row in projection.messages if start <= _parse(row["timestamp"]) <= end_inclusive
    ]


def _overall(
    rows: Sequence[Mapping[str, Any]],
    projection: StructuralProjection,
    context: Mapping[str, Any],
) -> dict[str, Any]:
    if not rows:
        raise ValueError("cannot aggregate an empty message set")
    start_utc = min(_parse(row["timestamp"]) for row in rows)
    end_utc = max(_parse(row["timestamp"]) for row in rows) + timedelta(seconds=1)
    timezone = ZoneInfo(TIMEZONE_NAME)
    start = start_utc.astimezone(timezone)
    end = end_utc.astimezone(timezone)
    return _aggregate_window(
        rows,
        projection.identities,
        context,
        start=start,
        end=end,
        grain_minutes=max(1, int((end - start).total_seconds() / 60)),
    )


def pair_overlap_timelines(
    cn_rows: Sequence[Mapping[str, Any]],
    es_rows: Sequence[Mapping[str, Any]],
    *,
    metric_names: Sequence[str] = TIMELINE_METRICS,
) -> list[dict[str, Any]]:
    """Join sparse timelines onto one axis and zero-fill an absent community bucket."""

    by_community = [
        {str(row["window_start"]): row for row in cn_rows},
        {str(row["window_start"]): row for row in es_rows},
    ]
    starts = sorted(set(by_community[0]) | set(by_community[1]))
    output: list[dict[str, Any]] = []
    for start in starts:
        row: dict[str, Any] = {"window_start": start}
        for metric in metric_names:
            row[f"cn_{metric}"] = by_community[0].get(start, {}).get(metric, 0)
            row[f"es_{metric}"] = by_community[1].get(start, {}).get(metric, 0)
        output.append(row)
    return output


def canonical_source_decision(
    *,
    snapshot_stable: bool,
    absolute_timestamps: bool,
    json_identity_coverage: float,
    json_reply_resolution: float,
    html_reply_resolution: float,
) -> dict[str, Any]:
    """Make an explicit gate decision without collapsing facts into a score."""

    gates = [
        {"gate": "stable closed-object snapshot", "passed": snapshot_stable},
        {"gate": "authoritative absolute timestamps", "passed": absolute_timestamps},
        {
            "gate": "usable from_id coverage >= 95%",
            "passed": json_identity_coverage >= 0.95,
            "actual": json_identity_coverage,
            "threshold": 0.95,
        },
        {
            "gate": "reply resolution not worse than HTML on exact matched cohort",
            "passed": json_reply_resolution >= html_reply_resolution,
            "json": json_reply_resolution,
            "html": html_reply_resolution,
        },
    ]
    passed = all(item["passed"] for item in gates)
    return {
        "preferred_source": "telegram_desktop_json" if passed else "undecided",
        "recommendation": "yes" if passed else "insufficient_evidence",
        "fallback_source": "telegram_desktop_html",
        "gates": gates,
        "no_composite_score": True,
        "interpretation": (
            "JSON is preferred for Blum when all gates pass; HTML remains a fallback and "
            "historical comparison source."
        ),
    }


def _profile_scope(
    rows: Sequence[Mapping[str, Any]],
    projection: StructuralProjection,
    context: Mapping[str, Any],
) -> dict[str, Any]:
    overall = _overall(rows, projection, context)
    return {
        "overall": overall,
        "unresolved_question_interpretation": (
            "question messages without a resolved direct reply edge; structural candidate only"
        ),
        "unresolved_question_count": overall["question_count"]
        - overall["question_with_resolved_reply_count"],
        "spam": "Not implemented: no existing deterministic spam rule is reusable",
    }


def _candidate_key_set(candidates: Mapping[str, Sequence[Mapping[str, Any]]]) -> set[str]:
    return {
        str(item["window_start"])
        for items in candidates.values()
        for item in items
        if "window_start" in item
    }


def _matched_html_json_cohort(
    projection: StructuralProjection,
    html_messages_path: Path,
    html_identities_path: Path,
) -> dict[str, Any]:
    """Compare the exact HTML canonical message-ID cohort without persisting rows."""

    html_messages = _jsonl(html_messages_path)
    html_identities = {str(row["source_message_id"]): row for row in _jsonl(html_identities_path)}
    json_by_source = {str(row["source_message_id"]): row for row in projection.messages}
    matched = [row for row in html_messages if str(row["source_message_id"]) in json_by_source]
    timestamp_deltas: list[float] = []
    text_matches = 0
    reply_partition_matches = 0
    json_reply_count = 0
    json_resolved_count = 0
    html_resolved_count = 0
    html_unresolved_count = 0
    usable_actor_count = 0
    for html_row in matched:
        source_id = str(html_row["source_message_id"])
        json_row = json_by_source[source_id]
        identity = projection.identities[str(json_row["message_id"])]
        html_identity = html_identities[source_id]
        timestamp_deltas.append(
            (_parse(json_row["timestamp"]) - _parse(html_row["timestamp"])).total_seconds()
        )
        text_matches += json_row["text_original"] == html_row["text_original"]
        usable_actor_count += bool(identity["usable_from_id"])
        json_state = str(identity["reply_state"])
        html_state = str(html_identity["reply_state"])
        reply_partition_matches += json_state == html_state
        json_reply_count += json_state != "non_reply"
        json_resolved_count += json_state == "resolved_reply"
        html_resolved_count += html_state == "resolved_reply"
        html_unresolved_count += html_state == "unresolved_reply"
    matched_count = len(matched)
    html_count = len(html_messages)
    return {
        "html_message_count": html_count,
        "matched_message_count": matched_count,
        "matched_message_coverage": _rate(matched_count, html_count),
        "html_messages_missing_from_json": html_count - matched_count,
        "timestamp_exact_match_count": sum(delta == 0 for delta in timestamp_deltas),
        "timestamp_exact_match_rate": _rate(
            sum(delta == 0 for delta in timestamp_deltas), matched_count
        ),
        "timestamp_max_absolute_delta_seconds": max(
            (abs(delta) for delta in timestamp_deltas), default=None
        ),
        "text_exact_match_count": text_matches,
        "text_exact_match_rate": _rate(text_matches, matched_count),
        "reply_partition_exact_match_count": reply_partition_matches,
        "reply_partition_exact_match_rate": _rate(reply_partition_matches, matched_count),
        "html_resolved_reply_count": html_resolved_count,
        "html_unresolved_reply_count": html_unresolved_count,
        "html_reply_resolution_rate": _rate(
            html_resolved_count, html_resolved_count + html_unresolved_count
        ),
        "json_resolved_reply_count": json_resolved_count,
        "json_unresolved_reply_count": json_reply_count - json_resolved_count,
        "json_reply_resolution_rate": _rate(json_resolved_count, json_reply_count),
        "json_from_id_coverage": _rate(usable_actor_count, matched_count),
        "interpretation": "exact source-message-ID cohort; aggregate results only",
        "input_sha256": {
            "html_canonical_messages": _sha256(html_messages_path),
            "html_identity_messages": _sha256(html_identities_path),
        },
    }


def _html_comparison(
    html_profile: Mapping[str, Any],
    html_recommendations: Mapping[str, Any],
    cn_projection: StructuralProjection,
    cn_full_profile: Mapping[str, Any],
    cn_hourly: Sequence[Mapping[str, Any]],
    cn_candidates: Mapping[str, Sequence[Mapping[str, Any]]],
    cn_recommendations: Mapping[str, Any],
    *,
    matched_cohort: Mapping[str, Any],
    html_profile_sha256: str,
    html_recommendations_sha256: str,
) -> dict[str, Any]:
    json_overall = cn_full_profile["overall"]
    html_overall = html_profile["overall"]
    html_start = _parse(html_profile["coverage"]["start"])
    html_end = _parse(html_profile["coverage"]["end"])
    json_start = _parse(cn_projection.audit["coverage"]["first_ordinary_message_timestamp"])
    json_end = _parse(cn_projection.audit["coverage"]["last_ordinary_message_timestamp"])
    hourly_by_start = {str(row["window_start"]): row for row in cn_hourly}
    json_candidate_keys = _candidate_key_set(cn_candidates)
    json_recommended_challenge = {
        str(item["window_start"]) for item in cn_recommendations["challenge_reply_validation"]
    }
    challenge_review = []
    for item in html_recommendations.get("challenge_reply_validation", []):
        start = str(item["window_start"])
        row = hourly_by_start.get(start)
        challenge_review.append(
            {
                "window_start": start,
                "json_window_present": row is not None,
                "json_candidate_triggered": start in json_candidate_keys,
                "json_recommended_again": start in json_recommended_challenge,
                "json_metrics": (
                    {
                        name: row.get(name)
                        for name in (
                            "message_count",
                            "resolved_reply_count",
                            "unresolved_reply_count",
                            "question_count",
                            "high_confidence_identity_count",
                            "max_reply_chain_depth_edges",
                        )
                    }
                    if row
                    else None
                ),
            }
        )
    json_hero_dates = {
        str(item["window_start"])[:10] for item in cn_recommendations["hero_event_candidates"]
    }
    html_hero_dates = {
        str(item["window_start"])[:10]
        for item in html_recommendations.get("hero_event_candidates", [])
    }
    return {
        "html_evidence": {
            "profile_sha256": html_profile_sha256,
            "recommendations_sha256": html_recommendations_sha256,
            "profile_version": html_profile.get("profile_version"),
        },
        "exact_matched_cohort": matched_cohort,
        "coverage": {
            "html_start": html_profile["coverage"]["start"],
            "html_end": html_profile["coverage"]["end"],
            "json_start": cn_projection.audit["coverage"]["first_ordinary_message_timestamp"],
            "json_end": cn_projection.audit["coverage"]["last_ordinary_message_timestamp"],
            "json_minus_html_start_seconds": (json_start - html_start).total_seconds(),
            "json_minus_html_end_seconds": (json_end - html_end).total_seconds(),
        },
        "message_count": {
            "html": html_overall["message_count"],
            "json": json_overall["message_count"],
            "difference": json_overall["message_count"] - html_overall["message_count"],
        },
        "timestamp": {
            "html_contract": "local Asia/Shanghai inference confirmed for the HTML export",
            "json_contract": "date_unixtime authoritative absolute UTC timestamp",
            "improvement": "JSON removes the HTML timezone-inference dependency",
        },
        "reply_resolution": {
            "html_resolved": html_overall["resolved_reply_count"],
            "html_unresolved": html_overall["unresolved_reply_count"],
            "html_rate": html_overall["reply_resolution_rate"],
            "json_resolved": json_overall["resolved_reply_count"],
            "json_unresolved": json_overall["unresolved_reply_count"],
            "json_rate": json_overall["reply_resolution_rate"],
            "rate_delta": round(
                json_overall["reply_resolution_rate"] - html_overall["reply_resolution_rate"],
                12,
            ),
            "comparison_limit": (
                "full exports have different coverage; use exact_matched_cohort for source "
                "quality and this block for whole-snapshot facts"
            ),
        },
        "identity": {
            "html_high_confidence_message_coverage": html_overall["identity_high_message_coverage"],
            "json_from_id_message_coverage": cn_projection.audit["identity"]["from_id_coverage"],
            "coverage_delta": round(
                cn_projection.audit["identity"]["from_id_coverage"]
                - html_overall["identity_high_message_coverage"],
                12,
            ),
            "interpretation": "both are export-local pseudonymous identities, not verified people",
        },
        "selected_window_review": {
            "html_challenge_windows": challenge_review,
            "html_hero_dates": sorted(html_hero_dates),
            "json_hero_dates": sorted(json_hero_dates),
            "hero_date_intersection": sorted(html_hero_dates & json_hero_dates),
        },
    }


def _sampling_fit(recommendations: Mapping[str, Any], language: str) -> dict[str, Any]:
    challenge = recommendations["challenge_reply_validation"]
    high = recommendations["high_activity_validation"]
    hero = recommendations["hero_event_candidates"]
    natural = recommendations["natural_behavior_validation"]

    def windows(items: Sequence[Mapping[str, Any]]) -> list[dict[str, str]]:
        return [
            {"start": str(item["window_start"]), "end": str(item["window_end"])} for item in items
        ]

    return {
        f"real_{language}_behavior_validation": windows([*natural, *challenge, *hero]),
        "peer_support": windows(
            [
                item
                for item in challenge
                if item.get("challenge_category") in {"reply_heavy", "question_support_heavy"}
            ]
        ),
        "question_confusion": windows(
            [
                item
                for item in challenge
                if item.get("challenge_category") == "question_support_heavy"
            ]
        ),
        "content_creation_advocacy": {
            "windows": windows(hero),
            "limit": "structure supports sampling only; no semantic label has been assigned",
        },
        "reply_context_evaluation": windows(
            [
                item
                for item in challenge
                if item.get("challenge_category") in {"reply_heavy", "long_conversation_chain"}
            ]
        ),
        "scalability_high_activity_evaluation": windows(high),
    }


def _render_report(
    provenance: Mapping[str, Any],
    audits: Mapping[str, Mapping[str, Any]],
    shared: Mapping[str, Any],
    profiles: Mapping[str, Any],
    comparison: Mapping[str, Any],
    decision: Mapping[str, Any],
    recommendations: Mapping[str, Any],
) -> str:
    matched = comparison["exact_matched_cohort"]
    lines = [
        "# Blum CN + ES Telegram JSON Intake & Structural Profiling",
        "",
        "**Status:** Complete; stopped at review gate. No Topic, Behavior, RAG, Signal, LLM, M3, or M4 execution.",
        "",
        "## Snapshot freeze",
        "",
        f"- Stability checks: {provenance['stability']['checks']} (stable={str(provenance['stability']['stable']).lower()}, source growth observed={str(provenance['stability']['observed_source_growth']).lower()})",
        f"- Combined snapshot SHA256: `{provenance['snapshot_sha256']}`",
        "- Real chat text, raw sender IDs, media, and per-message canonical data remain under ignored `data/private/`.",
        "",
        "## Exact intake facts",
        "",
        "| Community | First ordinary UTC | Last ordinary UTC | Ordinary | Service | Shared-period ordinary | from_id coverage | Resolved / reply |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for key in ("blum-cn", "blum-es"):
        audit = audits[key]
        label = COMMUNITIES[key]["label"]
        overlap_count = profiles["overlap"][key]["overall"]["message_count"]
        lines.append(
            f"| {label} | {audit['coverage']['first_ordinary_message_timestamp']} | "
            f"{audit['coverage']['last_ordinary_message_timestamp']} | "
            f"{audit['coverage']['ordinary_message_count']} | "
            f"{audit['coverage']['service_event_count']} | {overlap_count} | "
            f"{audit['identity']['from_id_coverage']:.2%} | "
            f"{audit['reply']['resolved_reply_edges']} / "
            f"{audit['reply']['messages_with_reply_to_message_id']} "
            f"({audit['reply']['reply_resolution_rate']:.2%}) |"
        )
    lines.extend(
        [
            "",
            f"Shared period: **{shared['start']} → {shared['end_inclusive']}** (inclusive), derived from observed ordinary-message timestamps.",
            "",
            "## JSON versus HTML",
            "",
            f"- CN ordinary messages: JSON {comparison['message_count']['json']:,}; HTML {comparison['message_count']['html']:,}; difference {comparison['message_count']['difference']:+,}.",
            f"- Exact 33,380-message cohort reply resolution: JSON {matched['json_reply_resolution_rate']:.2%}; HTML {matched['html_reply_resolution_rate']:.2%}; reply partitions match {matched['reply_partition_exact_match_rate']:.2%}.",
            f"- Full JSON snapshot reply resolution is {comparison['reply_resolution']['json_rate']:.2%}; its wider coverage and denominator are not directly comparable with the shorter HTML export.",
            f"- Stable sender coverage: JSON from_id {comparison['identity']['json_from_id_message_coverage']:.2%}; HTML high-confidence identity {comparison['identity']['html_high_confidence_message_coverage']:.2%}.",
            f"- Preferred canonical source: **{decision['recommendation']} — {decision['preferred_source']}**. HTML remains fallback.",
            "",
            "## Validation-window handoff",
            "",
        ]
    )
    for key in ("blum-cn", "blum-es"):
        label = COMMUNITIES[key]["label"]
        item = recommendations[key]
        lines.append(
            f"- {label}: Natural {len(item['natural_behavior_validation'])}; "
            f"Challenge/Reply {len(item['challenge_reply_validation'])}; "
            f"High Activity {len(item['high_activity_validation'])}; "
            f"Hero {len(item['hero_event_candidates'])}."
        )
    lines.extend(
        [
            "",
            "Candidate selection is deterministic and lexicographic with visible trigger facts; no opaque score is used. Official event dates provide temporal alignment only, never causation. `unresolved question` means a rule-detected question without a resolved direct reply edge, not a semantic judgment.",
            "",
            "## Limitations",
            "",
            "- Salted actor entities are export-local pseudonyms, not verified unique humans.",
            "- Telegram JSON does not reliably encode moderator roles; no role-dependent claims are made.",
            "- Most textless records do not include downloadable media/file metadata in this export; they remain separately counted rather than inferred as media-only.",
            "- Spam is `Not implemented` because no reusable deterministic spam contract exists.",
            "- Content Creation / Advocacy, Peer Support, and Question / Confusion entries are sampling suitability only; no semantic gold label was assigned.",
            "",
        ]
    )
    return "\n".join(lines)


def _args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--snapshot-root", type=Path, required=True)
    parser.add_argument("--private-root", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--event-input", type=Path, required=True)
    parser.add_argument("--html-profile", type=Path, required=True)
    parser.add_argument("--html-recommendations", type=Path, required=True)
    parser.add_argument("--html-canonical-messages", type=Path, required=True)
    parser.add_argument("--html-identity-messages", type=Path, required=True)
    return parser.parse_args()


def main() -> None:
    args = _args()
    snapshot_root = args.snapshot_root.resolve(strict=True)
    private_root = args.private_root.absolute()
    output_dir = args.output_dir.absolute()
    output_dir.mkdir(parents=True, exist_ok=True)
    salt = _salt(private_root / "identity_salt.txt")

    projections: dict[str, StructuralProjection] = {}
    for key, config in COMMUNITIES.items():
        canonical_destination = private_root / "canonical-v1.0.0" / key
        projection = build_structural_projection(
            snapshot_root / key / "result.json",
            community_id=key,
            language=config["language"],
            user_hash_salt=salt,
            build_canonical_dataset=not canonical_destination.exists(),
        )
        projections[key] = projection
        _publish_or_validate_canonical(projection, canonical_destination)

    audits = {key: projection.audit for key, projection in projections.items()}
    shared = calculate_shared_period(audits["blum-cn"], audits["blum-es"])
    shared_start = _parse(shared["start"])
    shared_end = _parse(shared["end_inclusive"])
    overlap_rows = {
        key: _filter_messages(projection, shared_start, shared_end)
        for key, projection in projections.items()
    }
    contexts = {
        key: prepare_structural_context(
            projection.messages, projection.identities, projection.edges
        )
        for key, projection in projections.items()
    }

    profiles = {
        "version": TRACK_VERSION,
        "base_commit": BASE_COMMIT,
        "profile_contract": PROFILE_VERSION,
        "full": {
            key: _profile_scope(projection.messages, projection, contexts[key])
            for key, projection in projections.items()
        },
        "overlap": {
            key: _profile_scope(overlap_rows[key], projection, contexts[key])
            for key, projection in projections.items()
        },
        "comparison_limit": "facts and differences only; no community health conclusion",
    }

    full_sparse: dict[str, dict[str, list[dict[str, Any]]]] = {}
    overlap_sparse: dict[str, dict[str, list[dict[str, Any]]]] = {}
    overlap_dense: dict[str, dict[str, list[dict[str, Any]]]] = {}
    timeline_summaries: dict[str, Any] = {}
    for key, projection in projections.items():
        context = contexts[key]
        full_sparse[key] = {}
        overlap_sparse[key] = {}
        overlap_dense[key] = {}
        timeline_summaries[key] = {"full": {}, "overlap": {}}
        for grain, minutes in GRAINS.items():
            rows, summary = build_timeline(
                projection.messages,
                projection.identities,
                projection.edges,
                grain_minutes=minutes,
                context=context,
            )
            full_sparse[key][grain] = rows
            timeline_summaries[key]["full"][grain] = summary
            _write_csv(output_dir / f"timeline_{key}_{grain}.csv", rows)

            sparse, overlap_summary = build_timeline(
                overlap_rows[key],
                projection.identities,
                projection.edges,
                grain_minutes=minutes,
                context=context,
            )
            dense, _ = build_timeline(
                overlap_rows[key],
                projection.identities,
                projection.edges,
                grain_minutes=minutes,
                context=context,
                include_empty=True,
            )
            overlap_sparse[key][grain] = sparse
            overlap_dense[key][grain] = dense
            timeline_summaries[key]["overlap"][grain] = overlap_summary

    for grain in GRAINS:
        paired = pair_overlap_timelines(
            overlap_sparse["blum-cn"][grain], overlap_sparse["blum-es"][grain]
        )
        _write_csv(output_dir / f"timeline_overlap_cn_es_{grain}.csv", paired)

    event_input = _json(args.event_input)
    _write_json(output_dir / "OFFICIAL_EVENT_INPUT.json", event_input)
    events = event_input["events"]
    candidates: dict[str, Any] = {}
    recommendations: dict[str, Any] = {}
    event_alignment: dict[str, Any] = {}
    for key, projection in projections.items():
        hourly_dense = overlap_dense[key]["1h"]
        community_candidates = build_candidate_windows(hourly_dense)
        candidates[key] = community_candidates
        alignment = build_blog_alignment(
            overlap_rows[key],
            projection.identities,
            projection.edges,
            events,
            context=contexts[key],
        )
        event_alignment[key] = alignment
        selected = _build_recommendations(
            hourly_dense,
            overlap_sparse[key]["1d"],
            community_candidates,
            alignment,
        )
        selected["high_activity_validation"] = _temporally_diverse(
            community_candidates["activity_surge"], 8, max_per_month=3
        )
        selected["hero_event_candidates"] = [
            item
            for item in selected["hero_event_candidates"]
            if str(item["window_start"])[5:7] in {"06", "07", "08"}
        ][:5]
        recommendations[key] = selected

    html_profile = _json(args.html_profile)
    html_recommendations = _json(args.html_recommendations)
    matched_cohort = _matched_html_json_cohort(
        projections["blum-cn"],
        args.html_canonical_messages,
        args.html_identity_messages,
    )
    html_comparison = _html_comparison(
        html_profile,
        html_recommendations,
        projections["blum-cn"],
        profiles["full"]["blum-cn"],
        full_sparse["blum-cn"]["1h"],
        candidates["blum-cn"],
        recommendations["blum-cn"],
        matched_cohort=matched_cohort,
        html_profile_sha256=_sha256(args.html_profile),
        html_recommendations_sha256=_sha256(args.html_recommendations),
    )
    private_provenance = _json(snapshot_root / "provenance.json")
    public_provenance = _safe_public_provenance(private_provenance)
    decision = canonical_source_decision(
        snapshot_stable=bool(public_provenance["stability"]["stable"]),
        absolute_timestamps=all(
            "date_unixtime authoritative" in audit["timestamp_contract"]
            for audit in audits.values()
        ),
        json_identity_coverage=audits["blum-cn"]["identity"]["from_id_coverage"],
        json_reply_resolution=matched_cohort["json_reply_resolution_rate"],
        html_reply_resolution=matched_cohort["html_reply_resolution_rate"],
    )
    html_comparison["preferred_source_decision"] = decision
    handoff = {
        "status": "ready_for_m3_sampling_review_not_m3_execution",
        "snapshot_references": {
            item["snapshot_key"]: {
                "private_relative_path": f"frozen-v1.0.0/{item['snapshot_key']}/result.json",
                "sha256": item["snapshot_sha256"],
            }
            for item in public_provenance["included_chats"]
        },
        "shared_period": shared,
        "identity_reply_coverage": {
            key: {"identity": audit["identity"], "reply": audit["reply"]}
            for key, audit in audits.items()
        },
        "recommended_windows": recommendations,
        "sampling_fit": {
            "blum-cn": _sampling_fit(recommendations["blum-cn"], "ZH"),
            "blum-es": _sampling_fit(recommendations["blum-es"], "ES"),
        },
        "known_limitations": [
            "sampling suitability is structural, not a semantic gold label",
            "pseudonymous actor entities are export-local and are not verified people",
            "moderator roles are unavailable in the Telegram JSON contract",
            "spam deterministic rule is Not implemented",
        ],
        "prohibited_in_this_track": ["Topic", "Behavior", "RAG", "Signal", "LLM", "M3", "M4"],
    }

    _write_json(output_dir / "snapshot_provenance_public.json", public_provenance)
    _write_json(output_dir / "data_integrity_audit.json", audits)
    _write_json(output_dir / "shared_period.json", shared)
    _write_json(output_dir / "structural_profiles.json", profiles)
    _write_json(output_dir / "timeline_summary.json", timeline_summaries)
    _write_json(output_dir / "candidate_windows.json", candidates)
    _write_json(output_dir / "recommended_windows.json", recommendations)
    _write_json(output_dir / "official_event_alignment.json", event_alignment)
    _write_json(output_dir / "html_json_comparison.json", html_comparison)
    _write_json(output_dir / "m3_sampling_handoff.json", handoff)
    (output_dir / "VALIDATION_REPORT.md").write_text(
        _render_report(
            public_provenance,
            audits,
            shared,
            profiles,
            html_comparison,
            decision,
            recommendations,
        ),
        encoding="utf-8",
    )

    generated_names = sorted(
        path.name
        for path in output_dir.iterdir()
        if path.is_file() and path.name not in {"SHA256SUMS", "profile_manifest.json"}
    )
    artifact_hashes = {name: _sha256(output_dir / name) for name in generated_names}
    manifest = {
        "status": "complete_stopped_at_review_gate",
        "track_version": TRACK_VERSION,
        "base_commit": BASE_COMMIT,
        "source_contracts": {
            "snapshot": public_provenance["extraction_method_version"],
            "canonical": "CommunityDataset schema 1.1 via telegram_desktop_json_v0.1",
            "structural_profile": PROFILE_VERSION,
            "official_events": event_input["version"],
        },
        "snapshot_sha256": public_provenance["snapshot_sha256"],
        "shared_period": shared,
        "artifact_sha256": artifact_hashes,
        "privacy": {
            "raw_sender_ids_persisted": False,
            "message_text_persisted": False,
            "pseudonymous_actor_ids_persisted": False,
            "media_paths_persisted": False,
            "per_message_records_persisted": False,
        },
        "not_implemented": [
            "spam deterministic rule",
            "Topic",
            "Behavior classifier",
            "RAG",
            "Signal",
            "LLM",
            "M3",
            "M4",
        ],
    }
    _write_json(output_dir / "profile_manifest.json", manifest)
    checksum_names = [*generated_names, "profile_manifest.json"]
    checksum_lines = [f"{_sha256(output_dir / name)}  {name}" for name in sorted(checksum_names)]
    (output_dir / "SHA256SUMS").write_text("\n".join(checksum_lines) + "\n", encoding="utf-8")
    print(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
