"""Pydantic contracts for synthetic community intelligence data."""

from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

UserRole = Literal["moderator", "user", "bot"]
ScenarioName = Literal[
    "high_volume_filler_duplicates",
    "healthy_replies",
    "semantic_drift",
    "unanswered_questions_negative_feedback",
]
ClaimStatus = Literal[
    "covered",
    "partially_covered",
    "contradicted",
    "incorrect",
    "not_covered",
    "uncertain",
]

_HASHED_USER_ID = re.compile(r"usr_[0-9a-f]+\Z")


def _require_nonempty(value: str) -> str:
    if not value.strip():
        raise ValueError("value must not be empty")
    return value


def _require_optional_nonempty(value: str | None) -> str | None:
    if value is not None:
        _require_nonempty(value)
    return value


def _require_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamp must be timezone-aware UTC")
    if value.utcoffset() != timedelta(0):
        raise ValueError("timestamp must use UTC")
    return value


class ContractModel(BaseModel):
    """Base contract that rejects unrecognized fields."""

    model_config = ConfigDict(extra="forbid")


class MessageRecord(ContractModel):
    """A production message record without evaluation labels."""

    message_id: str
    community_id: str
    language: str
    user_id_hash: str
    user_role: UserRole
    timestamp: datetime
    text: str
    reply_to_message_id: str | None
    campaign_id: str | None

    _nonempty_required = field_validator(
        "message_id",
        "community_id",
        "language",
        "text",
    )(_require_nonempty)
    _nonempty_optional = field_validator(
        "reply_to_message_id",
        "campaign_id",
    )(_require_optional_nonempty)
    _utc_timestamp = field_validator("timestamp")(_require_utc)

    @field_validator("user_id_hash")
    @classmethod
    def validate_hashed_user_id(cls, value: str) -> str:
        if not _HASHED_USER_ID.fullmatch(value):
            raise ValueError("user_id_hash must match usr_ followed by lowercase hexadecimal")
        return value


class CampaignRecord(ContractModel):
    campaign_id: str
    campaign_name: str
    start_time: datetime
    end_time: datetime
    campaign_brief: str

    _nonempty = field_validator(
        "campaign_id",
        "campaign_name",
        "campaign_brief",
    )(_require_nonempty)
    _utc_times = field_validator("start_time", "end_time")(_require_utc)

    @model_validator(mode="after")
    def validate_time_window(self) -> CampaignRecord:
        if self.end_time <= self.start_time:
            raise ValueError("campaign end_time must be after start_time")
        return self


class ClaimRecord(ContractModel):
    claim_id: str
    campaign_id: str
    claim_text: str
    importance: Literal["critical", "high", "medium", "low"]

    _nonempty = field_validator("claim_id", "campaign_id", "claim_text")(_require_nonempty)


class OutcomeRecord(ContractModel):
    campaign_id: str
    community_id: str
    participants: int = Field(ge=0)
    conversion: float = Field(ge=0, le=1)
    new_users: int = Field(ge=0)
    retention: float = Field(ge=0, le=1)
    referrals: int = Field(ge=0)
    synthetic: bool = True

    _nonempty = field_validator("campaign_id", "community_id")(_require_nonempty)


class AnnotationRecord(ContractModel):
    """Synthetic reference labels kept separate from production messages."""

    annotation_id: str
    message_id: str
    scenario: ScenarioName
    expected_behaviors: list[str] = Field(default_factory=list)
    expected_claim_status: ClaimStatus | None = None
    expected_question_status: Literal["answered", "unanswered"] | None = None
    notes: str

    _nonempty = field_validator("annotation_id", "message_id", "notes")(_require_nonempty)


class DatasetManifest(ContractModel):
    dataset_id: str
    schema_version: str
    synthetic: bool
    seed: int
    message_count: int = Field(ge=0)
    community_ids: list[str]
    languages: list[str]
    campaign_ids: list[str]
    scenarios: dict[str, str]
    generated_at: datetime

    _nonempty = field_validator("dataset_id", "schema_version")(_require_nonempty)
    _generated_at_utc = field_validator("generated_at")(_require_utc)


class SyntheticDataset(ContractModel):
    messages: list[MessageRecord]
    campaigns: list[CampaignRecord]
    claims: list[ClaimRecord]
    outcomes: list[OutcomeRecord]
    annotations: list[AnnotationRecord]
    manifest: DatasetManifest

    @model_validator(mode="after")
    def validate_references(self) -> SyntheticDataset:
        message_ids = [message.message_id for message in self.messages]
        campaign_ids = [campaign.campaign_id for campaign in self.campaigns]

        if len(message_ids) != len(set(message_ids)):
            raise ValueError("message_id values must be unique")
        if len(campaign_ids) != len(set(campaign_ids)):
            raise ValueError("campaign_id values must be unique")
        if self.manifest.message_count != len(self.messages):
            raise ValueError("manifest message_count does not match messages")

        message_id_set = set(message_ids)
        campaign_id_set = set(campaign_ids)
        for message in self.messages:
            if message.reply_to_message_id not in message_id_set | {None}:
                raise ValueError("reply_to_message_id must reference a dataset message")
            if message.reply_to_message_id == message.message_id:
                raise ValueError("a message cannot reply to itself")
            if message.campaign_id not in campaign_id_set | {None}:
                raise ValueError("message campaign_id must reference a dataset campaign")
        if any(claim.campaign_id not in campaign_id_set for claim in self.claims):
            raise ValueError("claim campaign_id must reference a dataset campaign")
        if any(outcome.campaign_id not in campaign_id_set for outcome in self.outcomes):
            raise ValueError("outcome campaign_id must reference a dataset campaign")
        if any(annotation.message_id not in message_id_set for annotation in self.annotations):
            raise ValueError("annotation message_id must reference a dataset message")
        return self
