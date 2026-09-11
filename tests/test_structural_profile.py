from __future__ import annotations

from datetime import UTC, datetime

import pytest

import community_intelligence.structural_profile as PROFILE_MODULE

BLOG_ALIGNMENT_INTERPRETATION = PROFILE_MODULE.BLOG_ALIGNMENT_INTERPRETATION
_build_recommendations = PROFILE_MODULE._build_recommendations
build_blog_alignment = PROFILE_MODULE.build_blog_alignment
build_candidate_windows = PROFILE_MODULE.build_candidate_windows
build_timeline = PROFILE_MODULE.build_timeline


def _message(
    message_id: str,
    minute: int,
    *,
    text: str = "",
    links: list[str] | None = None,
    media_refs: list[str] | None = None,
    forwarded: bool = False,
) -> dict[str, object]:
    return {
        "message_id": message_id,
        "community_id": "community_blum_cn",
        "timestamp": datetime(2024, 4, 19, 0, minute, tzinfo=UTC),
        "text_original": text,
        "links": links or [],
        "media_refs": media_refs or [],
        "forwarded_from": "aggregate-only" if forwarded else None,
    }


def _identity(
    message_id: str,
    identity_id: str,
    confidence: str,
    reply_state: str,
) -> dict[str, str]:
    return {
        "message_id": message_id,
        "resolved_identity_id": identity_id,
        "identity_confidence": confidence,
        "reply_state": reply_state,
    }


def test_timeline_keeps_reply_identity_and_content_denominators_explicit() -> None:
    messages = [
        _message("m1", 0, text="怎么参与？", links=["https://example.test"]),
        _message("m2", 1, text="请看置顶说明", forwarded=True),
        _message("m3", 2, media_refs=["photo"]),
        _message("m4", 3, text="ok"),
    ]
    identities = {
        "m1": _identity("m1", "pid-a", "high", "non_reply"),
        "m2": _identity("m2", "pid-b", "high", "resolved_reply"),
        "m3": _identity("m3", "pid-c", "medium", "unresolved_reply"),
        "m4": _identity("m4", "pid-c", "medium", "non_reply"),
    }
    edges = [
        {
            "child_message_id": "m2",
            "parent_message_id": "m1",
            "child_resolved_identity_id": "pid-b",
            "parent_resolved_identity_id": "pid-a",
            "child_identity_confidence": "high",
            "parent_identity_confidence": "high",
            "author_relation": "cross_author",
            "response_latency_seconds": 60,
        }
    ]

    rows, summary = build_timeline(messages, identities, edges, grain_minutes=5)

    assert summary["nonempty_window_count"] == 1
    row = rows[0]
    assert row["message_count"] == 4
    assert row["text_bearing_count"] == 3
    assert row["media_only_count"] == 1
    assert row["resolved_reply_count"] == 1
    assert row["unresolved_reply_count"] == 1
    assert row["non_reply_count"] == 2
    assert row["reply_resolution_rate"] == pytest.approx(0.5)
    assert row["response_latency_median_seconds"] == 60
    assert row["response_latency_p90_seconds"] == 60
    assert row["high_confidence_identity_count"] == 2
    assert row["broader_pseudonymous_identity_count"] == 3
    assert row["identity_high_message_count"] == 2
    assert row["identity_medium_message_count"] == 2
    assert row["identity_low_message_count"] == 0
    assert row["high_confidence_responder_count"] == 1
    assert row["high_confidence_recipient_count"] == 1
    assert row["cross_author_reply_edge_count"] == 1
    assert row["self_reply_edge_count"] == 0
    assert row["uncertain_reply_edge_count"] == 0
    assert row["question_count"] == 1
    assert row["question_with_resolved_reply_count"] == 1
    assert row["forwarded_message_count"] == 1
    assert row["hyperlink_message_count"] == 1
    assert row["media_message_count"] == 1
    assert row["top_broader_pseudonymous_identity_concentration"] == pytest.approx(0.5)
    assert not any("pid-" in str(value) for value in row.values())


def test_candidate_ranking_has_trigger_facts_and_no_black_box_score() -> None:
    rows = []
    for hour, count in enumerate([5, 4, 6, 5, 40]):
        rows.append(
            {
                "window_start": f"2024-04-19T{hour:02d}:00:00+08:00",
                "window_end": f"2024-04-19T{hour + 1:02d}:00:00+08:00",
                "grain_minutes": 60,
                "message_count": count,
                "resolved_reply_count": 12 if hour == 4 else 1,
                "unresolved_reply_count": 1,
                "resolved_reply_share": (12 / count) if hour == 4 else (1 / count),
                "reply_resolution_rate": 12 / 13 if hour == 4 else 0.5,
                "question_count": 10 if hour == 4 else 1,
                "question_with_resolved_reply_count": 8 if hour == 4 else 0,
                "high_confidence_identity_count": 20 if hour == 4 else 3,
                "identity_high_message_coverage": 0.8,
                "top_high_confidence_identity_concentration": 0.2,
                "top_broader_pseudonymous_identity_concentration": 0.25,
                "exact_duplicate_rate": 0.05,
                "repetitive_content_rate": 0.05,
                "filler_rate": 0.05,
                "burst_message_rate": 0.1,
                "max_reply_chain_depth_edges": 4 if hour == 4 else 1,
            }
        )

    candidates = build_candidate_windows(rows, preceding_baseline_windows=4)

    assert candidates["activity_surge"][0]["window_start"].endswith("04:00:00+08:00")
    assert candidates["activity_surge"][0]["trigger_facts"]
    assert candidates["reply_heavy"][0]["trigger_facts"]
    assert all("score" not in item for items in candidates.values() for item in items)


def test_blog_alignment_uses_disclosed_date_only_anchor_and_separates_pre_post() -> None:
    messages = [
        _message("before", 0, text="before"),
        {
            **_message("after", 0, text="after"),
            "timestamp": datetime(2024, 4, 20, 0, 0, tzinfo=UTC),
        },
    ]
    identities = {
        "before": _identity("before", "pid-a", "high", "non_reply"),
        "after": _identity("after", "pid-b", "high", "non_reply"),
    }
    events = [
        {
            "official_catalog_publication_date": "2024-04-19",
            "official_catalog_title": "Synthetic official event",
            "official_catalog_category": "New Features",
        }
    ]

    rows = build_blog_alignment(messages, identities, [], events)

    assert rows[0]["analysis_anchor"] == "2024-04-19T12:00:00+08:00"
    assert rows[0]["anchor_is_actual_publication_time"] is False
    assert rows[0]["coverage_status"] == "insufficient_observed_activity"
    assert rows[0]["pm24h"]["before"]["message_count"] == 1
    assert rows[0]["pm24h"]["after"]["message_count"] == 1
    assert rows[0]["pm24h"]["comparison"]["message_count_delta"] == 0
    assert "question_with_resolved_reply_count_delta" in rows[0]["pm72h"]["comparison"]
    assert rows[0]["interpretation"] == BLOG_ALIGNMENT_INTERPRETATION
    assert "causal" in BLOG_ALIGNMENT_INTERPRETATION.casefold()


def _profile_row(
    start: str,
    *,
    message_count: int,
    resolved: int,
    high_coverage: float,
    burst_rate: float = 0.1,
) -> dict[str, object]:
    return {
        "window_start": start,
        "window_end": start,
        "grain_minutes": 60,
        "message_count": message_count,
        "resolved_reply_count": resolved,
        "unresolved_reply_count": 1,
        "resolved_reply_share": resolved / message_count,
        "reply_resolution_rate": resolved / (resolved + 1),
        "question_count": 2,
        "question_with_resolved_reply_count": 1,
        "high_confidence_identity_count": 4,
        "identity_high_message_coverage": high_coverage,
        "top_high_confidence_identity_concentration": 0.3,
        "top_broader_pseudonymous_identity_concentration": 0.4,
        "exact_duplicate_rate": 0.1,
        "repetitive_content_rate": 0.1,
        "filler_rate": 0.1,
        "burst_message_rate": burst_rate,
        "max_reply_chain_depth_edges": 3,
    }


def test_recommendations_filter_extreme_natural_and_weak_identity_hero_windows() -> None:
    normal = _profile_row(
        "2024-06-01T10:00:00+08:00",
        message_count=8,
        resolved=2,
        high_coverage=0.75,
    )
    burst_dominated = _profile_row(
        "2024-07-01T10:00:00+08:00",
        message_count=8,
        resolved=2,
        high_coverage=0.75,
        burst_rate=0.95,
    )
    low_identity_day = {
        **_profile_row(
            "2024-05-03T00:00:00+08:00",
            message_count=100,
            resolved=20,
            high_coverage=0.1,
        ),
        "window_end": "2024-05-04T00:00:00+08:00",
        "grain_minutes": 1440,
    }
    candidates = {
        "activity_surge": [],
        "reply_heavy": [],
        "question_support_heavy": [],
        "broad_participation": [],
        "repetition_dominated": [],
        "long_conversation_chain": [],
        "quiet_baseline": [
            {**normal, "trigger_facts": [], "metrics": normal},
            {**burst_dominated, "trigger_facts": [], "metrics": burst_dominated},
        ],
    }
    blog = [
        {
            "official_catalog_publication_date": "2024-05-03",
            "official_catalog_title": "Synthetic event",
            "official_catalog_category": "New Features",
            "candidate_event_window": True,
        }
    ]

    result = _build_recommendations([normal, burst_dominated], [low_identity_day], candidates, blog)

    natural_starts = {item["window_start"] for item in result["natural_behavior_validation"]}
    assert normal["window_start"] in natural_starts
    assert burst_dominated["window_start"] not in natural_starts
    assert result["hero_event_candidates"] == []
