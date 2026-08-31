from datetime import UTC, datetime, timedelta

import pytest

from community_intelligence.campaign import (
    CampaignClaimResource,
    CampaignResource,
    analyze_campaign,
)
from community_intelligence.models import CampaignRecord, ClaimRecord, MessageRecord

BASE_TIME = datetime(2026, 9, 1, tzinfo=UTC)


def campaign() -> CampaignRecord:
    return CampaignRecord(
        campaign_id="campaign_stake",
        campaign_name="Synthetic Staking Week",
        start_time=BASE_TIME,
        end_time=BASE_TIME + timedelta(days=7),
        campaign_brief="Synthetic brief for deterministic tests.",
    )


def claim(claim_id: str, text: str) -> ClaimRecord:
    return ClaimRecord(
        claim_id=claim_id,
        campaign_id="campaign_stake",
        claim_text=text,
        importance="critical",
    )


def message(message_id: str, text: str, *, seconds: int = 1) -> MessageRecord:
    return MessageRecord(
        message_id=message_id,
        community_id="community_a",
        language="zh",
        user_id_hash="usr_01",
        user_role="user",
        timestamp=BASE_TIME + timedelta(seconds=seconds),
        text=text,
        reply_to_message_id=None,
        campaign_id="campaign_stake",
    )


def resources() -> CampaignResource:
    return CampaignResource(
        campaign_id="campaign_stake",
        claims=(
            CampaignClaimResource(
                claim_id="c_deadline",
                aliases=("deadline is friday", "截止时间是星期五"),
                contradiction_patterns=("deadline is sunday", "截止时间是星期日"),
            ),
            CampaignClaimResource(
                claim_id="c_reward",
                aliases=("reward is 100 tokens", "奖励是 100 个代币"),
                contradiction_patterns=("reward is 50 tokens", "奖励是 50 个代币"),
            ),
            CampaignClaimResource(
                claim_id="c_eligibility",
                aliases=("verified members only", "仅限已验证成员"),
                contradiction_patterns=("open to everyone", "所有人都符合资格"),
            ),
            CampaignClaimResource(
                claim_id="c_support",
                aliases=("support is available", "提供支持"),
                contradiction_patterns=("support is unavailable", "不提供支持"),
            ),
        ),
    )


def test_claim_judgment_distinguishes_all_supported_statuses() -> None:
    claims = [
        claim("c_deadline", "The deadline is Friday."),
        claim("c_reward", "The reward is 100 tokens."),
        claim("c_eligibility", "Verified members only."),
        claim("c_support", "Support is available."),
    ]
    messages = [
        message("m_deadline", "官方确认：截止时间是星期五。", seconds=1),
        message("m_reward_wrong", "本地消息写的是奖励是 50 个代币。", seconds=2),
        message("m_eligible", "规则说明仅限已验证成员。", seconds=3),
        message("m_eligible_wrong", "但另一条说所有人都符合资格。", seconds=4),
    ]

    judgments = analyze_campaign(campaign(), claims, messages, resources())

    by_claim = {judgment.claim_id: judgment for judgment in judgments}
    assert by_claim["c_deadline"].status == "covered"
    assert by_claim["c_reward"].status == "incorrect"
    assert by_claim["c_eligibility"].status == "ambiguous"
    assert by_claim["c_support"].status == "missing"
    assert by_claim["c_reward"].evidence_message_ids == ("m_reward_wrong",)
    assert by_claim["c_reward"].evidence_texts == (
        "本地消息写的是奖励是 50 个代币。",
    )
    assert all(item.method == "curated_alias_baseline" for item in judgments)
    assert all(item.general_semantic_ai == "Not implemented" for item in judgments)


def test_confidence_is_deterministic_and_tied_to_match_strength() -> None:
    deadline_claim = claim("c_deadline", "The deadline is Friday.")
    exact = analyze_campaign(
        campaign(),
        [deadline_claim],
        [message("m1", "截止时间是星期五")],
        CampaignResource(
            campaign_id="campaign_stake",
            claims=(
                CampaignClaimResource(
                    claim_id="c_deadline",
                    aliases=("截止时间是星期五", "星期五"),
                    contradiction_patterns=("星期日",),
                ),
            ),
        ),
    )[0]
    partial = analyze_campaign(
        campaign(),
        [deadline_claim],
        [message("m1", "星期五")],
        CampaignResource(
            campaign_id="campaign_stake",
            claims=(
                CampaignClaimResource(
                    claim_id="c_deadline",
                    aliases=("截止时间是星期五", "星期五"),
                    contradiction_patterns=("星期日",),
                ),
            ),
        ),
    )[0]

    assert exact.confidence > partial.confidence > 0
    assert exact.match_strength == pytest.approx(1.0)
    assert partial.match_strength == pytest.approx(3 / 8)


def test_campaign_analysis_filters_scope_and_rejects_resource_mismatch() -> None:
    outside = message("m_outside", "截止时间是星期五")
    outside_data = outside.model_copy(update={"campaign_id": "campaign_other"})
    judgment = analyze_campaign(
        campaign(), [claim("c_deadline", "The deadline is Friday.")], [outside_data], resources()
    )[0]
    assert judgment.status == "missing"
    assert judgment.evidence_message_ids == ()

    wrong_resource = CampaignResource(campaign_id="campaign_other", claims=resources().claims)
    with pytest.raises(ValueError, match="resource campaign_id"):
        analyze_campaign(
            campaign(),
            [claim("c_deadline", "The deadline is Friday.")],
            [],
            wrong_resource,
        )


def test_campaign_judgment_never_uses_annotation_labels() -> None:
    assert "expected_status" not in MessageRecord.model_fields
    assert "expected_claim_status" not in MessageRecord.model_fields
