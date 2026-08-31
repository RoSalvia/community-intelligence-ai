"""Deterministic multilingual synthetic dataset generation."""

from __future__ import annotations

import hashlib
import random
from datetime import UTC, datetime, timedelta

from community_intelligence.models import (
    AnnotationRecord,
    CampaignRecord,
    ClaimRecord,
    DatasetManifest,
    MessageRecord,
    OutcomeRecord,
    ScenarioName,
    SyntheticDataset,
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
    if message_count < len(COMMUNITIES):
        raise ValueError("message_count must be at least 4 to represent every community")
    remaining = message_count - len(COMMUNITIES)
    weights = (45, 25, 17, 13)
    counts = [1 + remaining * weight // 100 for weight in weights]
    for index in range(message_count - sum(counts)):
        counts[index % len(counts)] += 1
    return counts


def _scenario_message(
    scenario: ScenarioName,
    index: int,
    previous_id: str | None,
    question_id: str | None,
) -> tuple[str, str, str | None, list[str], str | None, str | None]:
    if scenario == "high_volume_filler_duplicates":
        texts = (
            "Synthetic update: great!",
            "Synthetic update: great!",
            "ok",
            "Synthetic campaign reminder.",
        )
        role = "moderator" if index % 8 else "user"
        reply_to = previous_id if index % 11 == 0 else None
        behavior = ["duplicate_promotion"] if index % 4 < 2 else ["filler"]
        return texts[index % len(texts)], role, reply_to, behavior, "not_covered", None

    if scenario == "healthy_replies":
        step = index % 5
        rows = (
            (
                "Campaña sintética: participa antes del viernes para recibir 100 tokens.",
                "moderator",
            ),
            ("¿La fecha límite de la campaña sintética es el viernes?", "user"),
            ("Sí, el viernes; participan los miembros verificados.", "moderator"),
            ("Gracias, ya entiendo las condiciones sintéticas.", "user"),
            ("También confirmo la fecha para otros usuarios.", "user"),
        )
        text, role = rows[step]
        if step == 0:
            reply_to = None
        elif step == 1:
            reply_to = previous_id
        elif step == 2:
            reply_to = question_id
        else:
            reply_to = previous_id
        status = "answered" if step in {1, 2} else None
        behavior = ["question_answering"] if step == 2 else ["meaningful_interaction"]
        return text, role, reply_to, behavior, "covered", status

    if scenario == "semantic_drift":
        rows = (
            ("合成活动奖励是 50 个代币，截止日期是周日。", "moderator"),
            ("我看到的合成说明写的是 100 个代币和星期五。", "user"),
            ("本地消息仍按 50 个代币和周日发布。", "moderator"),
            ("资格条件是不是也发生了变化？", "user"),
        )
        text, role = rows[index % len(rows)]
        reply_to = previous_id if index % len(rows) else None
        behavior = ["campaign_propagation"] if role == "moderator" else ["confusion"]
        return text, role, reply_to, behavior, "incorrect", None

    rows = (
        ("هل الموعد النهائي للحملة الاصطناعية يوم الجمعة؟", "user"),
        ("لم نحصل على إجابة واضحة حتى الآن.", "user"),
        ("لماذا تغيرت مكافأة الحملة الاصطناعية؟", "user"),
        ("التواصل غير واضح وهذا محبط.", "user"),
        ("سنراجع الأسئلة لاحقاً.", "moderator"),
    )
    text, role = rows[index % len(rows)]
    reply_to = previous_id if index % 5 in {1, 3} else None
    behavior = ["negative_feedback"] if index % 5 in {1, 3} else ["campaign_question"]
    question_status = "unanswered" if index % 5 in {0, 2} else None
    return text, role, reply_to, behavior, "not_covered", question_status


def _messages_and_annotations(
    seed: int,
    message_count: int,
    campaign_ids: list[str],
) -> tuple[list[MessageRecord], list[AnnotationRecord]]:
    rng = random.Random(seed)
    counts = _allocation(message_count)
    messages: list[MessageRecord] = []
    annotations: list[AnnotationRecord] = []
    sequence = 0

    for (community_id, language, scenario), count in zip(COMMUNITIES, counts, strict=True):
        previous_id: str | None = None
        question_id: str | None = None
        for local_index in range(count):
            sequence += 1
            message_id = f"msg_{sequence:06d}"
            text, role, reply_to, behaviors, claim_status, question_status = _scenario_message(
                scenario,
                local_index,
                previous_id,
                question_id,
            )
            campaign_id = campaign_ids[(local_index + rng.randrange(len(campaign_ids))) % 3]
            message = MessageRecord(
                message_id=message_id,
                community_id=community_id,
                language=language,
                user_id_hash=_hashed_user(seed, community_id, role, local_index),
                user_role=role,
                timestamp=BASE_TIME + timedelta(minutes=sequence * 3 + rng.randrange(3)),
                text=text,
                reply_to_message_id=reply_to,
                campaign_id=campaign_id,
            )
            messages.append(message)
            annotations.append(
                AnnotationRecord(
                    annotation_id=f"ann_{sequence:06d}",
                    message_id=message_id,
                    scenario=scenario,
                    expected_behaviors=behaviors,
                    expected_claim_status=claim_status,
                    expected_question_status=question_status,
                    notes="Synthetic reference annotation; not a production message field.",
                )
            )
            if scenario == "healthy_replies" and local_index % 5 == 1:
                question_id = message_id
            previous_id = message_id
    return messages, annotations


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
    messages, annotations = _messages_and_annotations(seed, message_count, campaign_ids)
    manifest = DatasetManifest(
        dataset_id=f"synthetic-community-intelligence-{seed}-{message_count}",
        schema_version="1.0",
        synthetic=True,
        seed=seed,
        message_count=message_count,
        community_ids=[community_id for community_id, _, _ in COMMUNITIES],
        languages=[language for _, language, _ in COMMUNITIES],
        campaign_ids=campaign_ids,
        scenarios=SCENARIO_DESCRIPTIONS,
        generated_at=BASE_TIME,
    )
    return SyntheticDataset(
        messages=messages,
        campaigns=campaigns,
        claims=_claims(),
        outcomes=_outcomes(seed, campaign_ids),
        annotations=annotations,
        manifest=manifest,
    )
