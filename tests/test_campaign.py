from datetime import UTC, datetime, timedelta
from typing import get_args

import pytest

from community_intelligence.campaign import (
    CampaignClaimResource,
    CampaignJudgmentStatus,
    CampaignResource,
    analyze_campaign,
    summarize_campaign,
)
from community_intelligence.models import CampaignRecord, ClaimRecord, MessageRecord

BASE_TIME = datetime(2026, 9, 1, tzinfo=UTC)
REQUIRED_STATUSES = {
    "covered",
    "partially_covered",
    "contradicted",
    "incorrect",
    "not_covered",
    "uncertain",
}


def campaign() -> CampaignRecord:
    return CampaignRecord(
        campaign_id="campaign_stake",
        campaign_name="Synthetic Staking Week",
        start_time=BASE_TIME,
        end_time=BASE_TIME + timedelta(days=7),
        campaign_brief="Synthetic brief for deterministic tests.",
    )


def claim(claim_id: str) -> ClaimRecord:
    return ClaimRecord(
        claim_id=claim_id,
        campaign_id="campaign_stake",
        claim_text=f"Atomic synthetic claim {claim_id}.",
        importance="critical",
    )


def message(
    message_id: str,
    text: str,
    *,
    community_id: str = "community_a",
    seconds: int = 1,
    campaign_id: str | None = "campaign_stake",
) -> MessageRecord:
    return MessageRecord(
        message_id=message_id,
        community_id=community_id,
        language="zh",
        user_id_hash="usr_01",
        user_role="user",
        timestamp=BASE_TIME + timedelta(seconds=seconds),
        text=text,
        reply_to_message_id=None,
        campaign_id=campaign_id,
    )


def resources() -> CampaignResource:
    return CampaignResource(
        campaign_id="campaign_stake",
        claims=(
            CampaignClaimResource(
                claim_id="c_covered",
                aliases=("截止时间是星期五",),
                contradiction_patterns=("并非星期五截止",),
            ),
            CampaignClaimResource(
                claim_id="c_partial",
                aliases=("已验证成员星期五前质押可得 100 个代币",),
                partial_aliases=("星期五前质押",),
                contradiction_patterns=("无需质押",),
            ),
            CampaignClaimResource(
                claim_id="c_contradicted",
                aliases=("必须完成身份验证",),
                contradiction_patterns=("不需要身份验证",),
            ),
            CampaignClaimResource(
                claim_id="c_incorrect",
                aliases=("奖励是 100 个代币",),
                incorrect_patterns=("奖励是 50 个代币",),
            ),
            CampaignClaimResource(
                claim_id="c_uncertain",
                aliases=("仅限已验证成员",),
                uncertain_patterns=("资格尚未确认",),
            ),
            CampaignClaimResource(
                claim_id="c_not_covered",
                aliases=("提供全天候支持",),
            ),
        ),
    )


def all_claims() -> list[ClaimRecord]:
    return [claim(item.claim_id) for item in resources().claims]


def status_messages(community_id: str = "community_a") -> list[MessageRecord]:
    return [
        message("m_covered", "官方确认：截止时间是星期五。", community_id=community_id, seconds=1),
        message("m_partial", "提醒大家星期五前质押。", community_id=community_id, seconds=2),
        message(
            "m_contradicted",
            "本次活动不需要身份验证。",
            community_id=community_id,
            seconds=3,
        ),
        message(
            "m_incorrect",
            "本地公告称奖励是 50 个代币。",
            community_id=community_id,
            seconds=4,
        ),
        message(
            "m_uncertain",
            "目前资格尚未确认。",
            community_id=community_id,
            seconds=5,
        ),
    ]


def test_public_contract_emits_all_required_statuses_and_fields() -> None:
    judgments = analyze_campaign(
        campaign(), all_claims(), status_messages(), resources()
    )
    by_claim = {judgment.claim_id: judgment for judgment in judgments}

    assert set(get_args(CampaignJudgmentStatus)) == REQUIRED_STATUSES
    assert {claim_id: item.status for claim_id, item in by_claim.items()} == {
        "c_covered": "covered",
        "c_partial": "partially_covered",
        "c_contradicted": "contradicted",
        "c_incorrect": "incorrect",
        "c_uncertain": "uncertain",
        "c_not_covered": "not_covered",
    }
    covered = by_claim["c_covered"]
    assert covered.campaign_id == "campaign_stake"
    assert covered.community_id == "community_a"
    assert covered.evidence_message_ids == ("m_covered",)
    assert covered.evidence_text == ("官方确认：截止时间是星期五。",)
    assert covered.translation is None
    assert covered.notes
    assert covered.method == "curated_alias_baseline"
    assert covered.review_status == "pending"
    assert covered.general_semantic_ai == "Not implemented"


def test_campaign_judgments_are_isolated_per_claim_and_community() -> None:
    target_claim = claim("c_incorrect")
    community_a = message(
        "a_correct", "奖励是 100 个代币。", community_id="community_a", seconds=1
    )
    community_b = message(
        "b_wrong", "奖励是 50 个代币。", community_id="community_b", seconds=2
    )
    community_c_context = message(
        "c_context", "普通讨论，没有活动事实。", community_id="community_c", seconds=3
    )

    judgments = analyze_campaign(
        campaign(),
        [target_claim],
        [community_b, community_c_context, community_a],
        resources(),
    )
    by_community = {item.community_id: item for item in judgments}

    assert by_community["community_a"].status == "covered"
    assert by_community["community_a"].evidence_message_ids == ("a_correct",)
    assert by_community["community_b"].status == "incorrect"
    assert by_community["community_b"].evidence_message_ids == ("b_wrong",)
    assert by_community["community_c"].status == "not_covered"
    assert by_community["community_c"].evidence_message_ids == ()
    for judgment in judgments:
        prefix = judgment.community_id.removeprefix("community_") + "_"
        assert all(item.startswith(prefix) for item in judgment.evidence_message_ids)


def test_campaign_summary_has_explicit_formulas_and_denominators() -> None:
    judgments = analyze_campaign(
        campaign(), all_claims(), status_messages(), resources()
    )

    summary = summarize_campaign(judgments)[0]

    assert summary.campaign_id == "campaign_stake"
    assert summary.community_id == "community_a"
    assert summary.total_claims == 6
    assert summary.semantic_coverage == pytest.approx((1 + 0.5) / 6)
    assert summary.claim_completeness == pytest.approx(1 / 6)
    assert summary.accuracy_warning_count == 3
    assert summary.semantic_drift_count == 2
    assert summary.semantic_coverage_formula == (
        "(covered + 0.5 * partially_covered) / total_claims"
    )
    assert summary.claim_completeness_formula == "covered / total_claims"
    assert summary.denominator == "all atomic claims for the campaign in this community"


def test_confidence_is_deterministic_and_tied_to_match_strength() -> None:
    target_claim = claim("c_covered")
    exact = analyze_campaign(
        campaign(), [target_claim], [message("m1", "截止时间是星期五")], resources()
    )[0]
    partial_resource = CampaignResource(
        campaign_id="campaign_stake",
        claims=(
            CampaignClaimResource(
                claim_id="c_covered",
                aliases=("完整公告确认截止时间是星期五", "星期五"),
            ),
        ),
    )
    weak = analyze_campaign(
        campaign(), [target_claim], [message("m1", "星期五")], partial_resource
    )[0]

    assert exact.confidence > weak.confidence > 0
    assert exact.match_strength == pytest.approx(1.0)
    assert weak.match_strength < 1.0


def test_explicit_community_scope_supports_no_message_judgments() -> None:
    judgments = analyze_campaign(
        campaign(),
        [claim("c_not_covered")],
        [],
        resources(),
        community_ids=["community_empty"],
    )

    assert len(judgments) == 1
    assert judgments[0].community_id == "community_empty"
    assert judgments[0].status == "not_covered"


def test_campaign_analysis_rejects_resource_mismatch() -> None:
    wrong_resource = CampaignResource(campaign_id="campaign_other", claims=resources().claims)
    with pytest.raises(ValueError, match="resource campaign_id"):
        analyze_campaign(
            campaign(),
            [claim("c_covered")],
            [],
            wrong_resource,
            community_ids=["community_a"],
        )


def test_campaign_analysis_rejects_duplicate_claim_pairs() -> None:
    duplicate = claim("c_covered")

    with pytest.raises(ValueError, match="claim_id values must be unique"):
        analyze_campaign(
            campaign(),
            [duplicate, duplicate],
            [message("m1", "截止时间是星期五")],
            resources(),
        )


def test_campaign_judgment_never_uses_annotation_labels() -> None:
    assert "expected_status" not in MessageRecord.model_fields
    assert "expected_claim_status" not in MessageRecord.model_fields
