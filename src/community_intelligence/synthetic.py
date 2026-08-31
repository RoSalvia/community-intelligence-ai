"""Deterministic multilingual synthetic dataset generation."""

from __future__ import annotations

import hashlib
import random
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Literal

from community_intelligence.io import data_artifact_contents, publication_metadata
from community_intelligence.models import (
    AnnotationRecord,
    CampaignRecord,
    ClaimRecord,
    ClaimStatus,
    DatasetManifest,
    MessageRecord,
    OutcomeRecord,
    ScenarioName,
    SyntheticDataset,
    UserRole,
)

BASE_TIME = datetime(2026, 9, 1, 0, 0, tzinfo=UTC)

COMMUNITIES: tuple[tuple[str, str, ScenarioName], ...] = (
    ("community_a", "en", "high_volume_filler_duplicates"),
    ("community_b", "es", "healthy_replies"),
    ("community_c", "zh", "semantic_drift"),
    ("community_d", "ar", "unanswered_questions_negative_feedback"),
)

SCENARIO_DESCRIPTIONS = {
    "community_a": "High moderator volume with filler and duplicate synthetic posts.",
    "community_b": "Lower volume with timely answers and continued user replies.",
    "community_c": "Localized synthetic posts contain known reward and deadline drift.",
    "community_d": "User questions are often unanswered and negative feedback increases.",
}


@dataclass(frozen=True)
class MessageTemplate:
    text: str
    role: UserRole
    behaviors: tuple[str, ...]
    claim_status: ClaimStatus
    question_status: Literal["answered", "unanswered"] | None
    reply_to_template: int | None = None


SCENARIO_TEMPLATES: dict[ScenarioName, tuple[MessageTemplate, ...]] = {
    "high_volume_filler_duplicates": (
        MessageTemplate(
            text="{campaign_name} synthetic update: great!",
            role="moderator",
            behaviors=("duplicate_promotion",),
            claim_status="not_covered",
            question_status=None,
        ),
        MessageTemplate(
            text="{campaign_name} synthetic update: great!",
            role="moderator",
            behaviors=("duplicate_promotion",),
            claim_status="not_covered",
            question_status=None,
            reply_to_template=0,
        ),
        MessageTemplate(
            text="{campaign_name}: ok",
            role="moderator",
            behaviors=("filler",),
            claim_status="not_covered",
            question_status=None,
            reply_to_template=1,
        ),
        MessageTemplate(
            text="{campaign_name} correct reminder: {correct_fact_en}.",
            role="moderator",
            behaviors=("campaign_propagation",),
            claim_status="covered",
            question_status=None,
            reply_to_template=2,
        ),
        MessageTemplate(
            text="{campaign_name}: thanks for the synthetic update.",
            role="user",
            behaviors=("meaningful_interaction",),
            claim_status="not_covered",
            question_status=None,
            reply_to_template=3,
        ),
    ),
    "healthy_replies": (
        MessageTemplate(
            text="{campaign_name}: campaña sintética; {correct_fact_es}.",
            role="moderator",
            behaviors=("campaign_propagation",),
            claim_status="covered",
            question_status=None,
        ),
        MessageTemplate(
            text="{campaign_name}: ¿pueden confirmar las condiciones de la campaña sintética?",
            role="user",
            behaviors=("campaign_question",),
            claim_status="uncertain",
            question_status="answered",
            reply_to_template=0,
        ),
        MessageTemplate(
            text="{campaign_name}: sí; {correct_fact_es}.",
            role="moderator",
            behaviors=("question_answering",),
            claim_status="covered",
            question_status="answered",
            reply_to_template=1,
        ),
        MessageTemplate(
            text="{campaign_name}: gracias, ya entiendo las condiciones sintéticas.",
            role="user",
            behaviors=("meaningful_interaction",),
            claim_status="not_covered",
            question_status=None,
            reply_to_template=2,
        ),
        MessageTemplate(
            text="{campaign_name}: también confirmo que {correct_fact_es}.",
            role="user",
            behaviors=("peer_support",),
            claim_status="covered",
            question_status=None,
            reply_to_template=1,
        ),
    ),
    "semantic_drift": (
        MessageTemplate(
            text="{campaign_name}：本地错误版本写的是{drift_fact_zh}。",
            role="moderator",
            behaviors=("campaign_propagation",),
            claim_status="incorrect",
            question_status=None,
        ),
        MessageTemplate(
            text="{campaign_name}：我看到的合成说明写的是 {correct_fact_zh}。",
            role="user",
            behaviors=("correction",),
            claim_status="covered",
            question_status=None,
            reply_to_template=0,
        ),
        MessageTemplate(
            text="{campaign_name}：本地消息仍按{drift_fact_zh}发布。",
            role="moderator",
            behaviors=("campaign_propagation",),
            claim_status="incorrect",
            question_status=None,
            reply_to_template=1,
        ),
        MessageTemplate(
            text="{campaign_name}：资格条件是不是也发生了变化？",
            role="user",
            behaviors=("campaign_question", "confusion"),
            claim_status="uncertain",
            question_status="answered",
            reply_to_template=2,
        ),
        MessageTemplate(
            text=(
                "{campaign_name}：资格条件未变：{eligibility_fact_zh}；"
                "正确说明是 {correct_fact_zh}。"
            ),
            role="moderator",
            behaviors=("question_answering",),
            claim_status="covered",
            question_status="answered",
            reply_to_template=3,
        ),
    ),
    "unanswered_questions_negative_feedback": (
        MessageTemplate(
            text="{campaign_name}: هل يمكن توضيح شروط الحملة الاصطناعية؟",
            role="user",
            behaviors=("campaign_question",),
            claim_status="uncertain",
            question_status="unanswered",
        ),
        MessageTemplate(
            text="{campaign_name}: لم نحصل على إجابة واضحة حتى الآن.",
            role="user",
            behaviors=("negative_feedback",),
            claim_status="not_covered",
            question_status=None,
            reply_to_template=0,
        ),
        MessageTemplate(
            text="{campaign_name}: لماذا تبدو معلومات الحملة الاصطناعية غير واضحة؟",
            role="user",
            behaviors=("campaign_question",),
            claim_status="uncertain",
            question_status="unanswered",
            reply_to_template=1,
        ),
        MessageTemplate(
            text="{campaign_name}: التواصل غير واضح وهذا محبط.",
            role="user",
            behaviors=("negative_feedback",),
            claim_status="not_covered",
            question_status=None,
            reply_to_template=2,
        ),
        MessageTemplate(
            text="{campaign_name}: سنراجع الأسئلة لاحقاً وفق المعلومات الرسمية: {correct_fact_ar}.",
            role="moderator",
            behaviors=("moderator_follow_up",),
            claim_status="partially_covered",
            question_status=None,
            reply_to_template=3,
        ),
    ),
}


CAMPAIGN_FACTS = {
    "campaign_stake": {
        "correct_fact_en": "verified members stake before Friday for 100 synthetic tokens",
        "correct_fact_es": "los miembros verificados participan antes del viernes por 100 tokens",
        "correct_fact_zh": "100 个代币和星期五",
        "eligibility_fact_zh": "仅已验证成员符合资格",
        "correct_fact_ar": "الموعد الجمعة والمكافأة 100 رمز اصطناعي",
        "drift_fact_zh": "50 个代币和周日",
    },
    "campaign_referral": {
        "correct_fact_en": "two eligible friends are referred by September 15 for 25 tokens",
        "correct_fact_es": (
            "se recomiendan dos amigos elegibles antes del 15 de septiembre por 25 tokens"
        ),
        "correct_fact_zh": "推荐两名合格好友、9 月 15 日截止和 25 个代币",
        "eligibility_fact_zh": "仅合格好友推荐计入活动",
        "correct_fact_ar": "إحالة صديقين مؤهلين قبل 15 سبتمبر والمكافأة 25 رمزاً",
        "drift_fact_zh": "推荐一名好友、9 月 18 日截止和 10 个代币",
    },
    "campaign_launch": {
        "correct_fact_en": "the feature launches September 20 and feedback is invited",
        "correct_fact_es": "la función se lanza el 20 de septiembre y se solicitan comentarios",
        "correct_fact_zh": "9 月 20 日上线并邀请反馈",
        "eligibility_fact_zh": "所有社区成员均可提交反馈",
        "correct_fact_ar": "الإطلاق في 20 سبتمبر والتعليقات مرحب بها",
        "drift_fact_zh": "9 月 25 日上线且不再征集反馈",
    },
}

MIN_MESSAGE_COUNT = (
    len(COMMUNITIES)
    * len(CAMPAIGN_FACTS)
    * max(len(templates) for templates in SCENARIO_TEMPLATES.values())
)


def _hashed_user(seed: int, community_id: str, role: str, index: int) -> str:
    source = f"synthetic:{seed}:{community_id}:{role}:{index % 17}".encode()
    return f"usr_{hashlib.sha256(source).hexdigest()[:12]}"


def _campaigns() -> list[CampaignRecord]:
    return [
        CampaignRecord(
            campaign_id="campaign_stake",
            campaign_name="Synthetic Staking Week",
            start_time=BASE_TIME,
            end_time=BASE_TIME + timedelta(days=7),
            campaign_brief=(
                "Synthetic brief: verified members stake before Friday for a 100-token reward."
            ),
        ),
        CampaignRecord(
            campaign_id="campaign_referral",
            campaign_name="Synthetic Referral Sprint",
            start_time=BASE_TIME + timedelta(days=8),
            end_time=BASE_TIME + timedelta(days=15),
            campaign_brief=(
                "Synthetic brief: refer two eligible friends by September 15 for 25 tokens."
            ),
        ),
        CampaignRecord(
            campaign_id="campaign_launch",
            campaign_name="Synthetic Product Launch",
            start_time=BASE_TIME + timedelta(days=16),
            end_time=BASE_TIME + timedelta(days=23),
            campaign_brief=(
                "Synthetic brief: the demo feature launches September 20 and feedback is invited."
            ),
        ),
    ]


def _claims() -> list[ClaimRecord]:
    claim_data = (
        ("stake_deadline", "campaign_stake", "The staking deadline is Friday.", "critical"),
        ("stake_reward", "campaign_stake", "The reward is 100 synthetic tokens.", "critical"),
        ("stake_eligibility", "campaign_stake", "Verified members are eligible.", "high"),
        ("referral_count", "campaign_referral", "Two eligible referrals are required.", "high"),
        ("referral_reward", "campaign_referral", "The reward is 25 synthetic tokens.", "high"),
        (
            "launch_date",
            "campaign_launch",
            "The synthetic feature launches September 20.",
            "critical",
        ),
        ("launch_feedback", "campaign_launch", "Community feedback is invited.", "medium"),
    )
    return [
        ClaimRecord(
            claim_id=claim_id,
            campaign_id=campaign_id,
            claim_text=text,
            importance=importance,
        )
        for claim_id, campaign_id, text, importance in claim_data
    ]


def _allocation(message_count: int) -> list[int]:
    if message_count < MIN_MESSAGE_COUNT:
        raise ValueError(f"message_count must be at least {MIN_MESSAGE_COUNT}")
    minimum_per_community = MIN_MESSAGE_COUNT // len(COMMUNITIES)
    remaining = message_count - MIN_MESSAGE_COUNT
    weights = (45, 25, 17, 13)
    counts = [minimum_per_community + remaining * weight // 100 for weight in weights]
    for index in range(message_count - sum(counts)):
        counts[index % len(counts)] += 1
    return counts


def _messages_and_annotations(
    seed: int,
    message_count: int,
    campaigns: list[CampaignRecord],
) -> tuple[list[MessageRecord], list[AnnotationRecord]]:
    community_counts = dict(
        zip(
            (community_id for community_id, _, _ in COMMUNITIES),
            _allocation(message_count),
            strict=True,
        )
    )
    episode_counts = {
        (community_id, campaign.campaign_id): count
        for community_id, total in community_counts.items()
        for campaign, count in zip(
            campaigns,
            _balanced_counts(total, len(campaigns)),
            strict=True,
        )
    }
    messages: list[MessageRecord] = []
    annotations: list[AnnotationRecord] = []
    sequence = 0

    for campaign_index, campaign in enumerate(campaigns):
        campaign_total = sum(
            episode_counts[(community_id, campaign.campaign_id)]
            for community_id, _, _ in COMMUNITIES
        )
        campaign_ordinal = 0
        for community_id, language, scenario in COMMUNITIES:
            count = episode_counts[(community_id, campaign.campaign_id)]
            templates = SCENARIO_TEMPLATES[scenario]
            cycle_message_ids: list[str] = []
            for local_index in range(count):
                template_index = local_index % len(templates)
                template = templates[template_index]
                if (
                    local_index == count - 1
                    and template.question_status == "answered"
                    and "campaign_question" in template.behaviors
                ):
                    template_index = 0
                    template = templates[template_index]
                if template_index == 0:
                    cycle_message_ids = []
                sequence += 1
                campaign_ordinal += 1
                message_id = f"msg_{sequence:06d}"
                reply_to = (
                    cycle_message_ids[template.reply_to_template]
                    if template.reply_to_template is not None
                    else None
                )
                timestamp = campaign.start_time + (
                    (campaign.end_time - campaign.start_time)
                    * campaign_ordinal
                    / (campaign_total + 1)
                )
                text = template.text.format(
                    campaign_name=campaign.campaign_name,
                    **CAMPAIGN_FACTS[campaign.campaign_id],
                )
                messages.append(
                    MessageRecord(
                        message_id=message_id,
                        community_id=community_id,
                        language=language,
                        user_id_hash=_hashed_user(
                            seed,
                            community_id,
                            template.role,
                            campaign_index * 10_000 + local_index,
                        ),
                        user_role=template.role,
                        timestamp=timestamp,
                        text=text,
                        reply_to_message_id=reply_to,
                        campaign_id=campaign.campaign_id,
                    )
                )
                annotations.append(
                    AnnotationRecord(
                        annotation_id=f"ann_{sequence:06d}",
                        message_id=message_id,
                        scenario=scenario,
                        expected_behaviors=list(template.behaviors),
                        expected_claim_status=template.claim_status,
                        expected_question_status=template.question_status,
                        notes="Synthetic reference annotation; not a production message field.",
                    )
                )
                cycle_message_ids.append(message_id)
    return messages, annotations


def _balanced_counts(total: int, buckets: int) -> list[int]:
    base, remainder = divmod(total, buckets)
    return [base + (index < remainder) for index in range(buckets)]


def _outcomes(seed: int, campaign_ids: list[str]) -> list[OutcomeRecord]:
    rng = random.Random(seed + 991)
    profiles = {
        "community_a": (16, 0.03, 3, 0.24, 1),
        "community_b": (82, 0.18, 21, 0.73, 19),
        "community_c": (44, 0.08, 10, 0.46, 7),
        "community_d": (29, 0.04, 5, 0.31, 2),
    }
    outcomes: list[OutcomeRecord] = []
    for community_id, _, _ in COMMUNITIES:
        participants, conversion, new_users, retention, referrals = profiles[community_id]
        for campaign_id in campaign_ids:
            outcomes.append(
                OutcomeRecord(
                    campaign_id=campaign_id,
                    community_id=community_id,
                    participants=participants + rng.randrange(-2, 3),
                    conversion=round(min(1, max(0, conversion + rng.uniform(-0.01, 0.01))), 4),
                    new_users=max(0, new_users + rng.randrange(-1, 2)),
                    retention=round(min(1, max(0, retention + rng.uniform(-0.02, 0.02))), 4),
                    referrals=max(0, referrals + rng.randrange(-1, 2)),
                    synthetic=True,
                )
            )
    return outcomes


def generate_dataset(seed: int = 20260901, message_count: int = 1200) -> SyntheticDataset:
    """Generate a deterministic, explicitly synthetic multilingual dataset."""

    campaigns = _campaigns()
    campaign_ids = [campaign.campaign_id for campaign in campaigns]
    messages, annotations = _messages_and_annotations(seed, message_count, campaigns)
    claims = _claims()
    outcomes = _outcomes(seed, campaign_ids)
    dataset_id = f"synthetic-community-intelligence-{seed}-{message_count}"
    generation_id, artifact_checksums = publication_metadata(
        dataset_id,
        data_artifact_contents(messages, campaigns, claims, outcomes, annotations),
    )
    manifest = DatasetManifest(
        dataset_id=dataset_id,
        schema_version="1.0",
        synthetic=True,
        seed=seed,
        message_count=message_count,
        community_ids=[community_id for community_id, _, _ in COMMUNITIES],
        languages=[language for _, language, _ in COMMUNITIES],
        campaign_ids=campaign_ids,
        scenarios=SCENARIO_DESCRIPTIONS,
        generated_at=BASE_TIME,
        generation_id=generation_id,
        artifact_checksums=artifact_checksums,
    )
    return SyntheticDataset(
        messages=messages,
        campaigns=campaigns,
        claims=claims,
        outcomes=outcomes,
        annotations=annotations,
        manifest=manifest,
    )
