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
_LANGUAGE_CODE = re.compile(r"[a-z]{2,3}(?:-[a-z0-9]{2,8})*\Z")
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")


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

    model_config = ConfigDict(extra="forbid", frozen=True)


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

    @field_validator("language")
    @classmethod
    def validate_language_code(cls, value: str) -> str:
        if not _LANGUAGE_CODE.fullmatch(value):
            raise ValueError("language must be a lowercase BCP-47-like primary tag")
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
    seed: int | None
    message_count: int = Field(ge=0)
    community_ids: list[str]
    languages: list[str]
    campaign_ids: list[str]
    scenarios: dict[str, str]
    generated_at: datetime
    generation_id: str
    artifact_checksums: dict[str, str]
    source_format: str = "synthetic_generator_v1"
    source_sha256: str | None = None
    limitations: list[str] = Field(default_factory=list)

    _nonempty = field_validator("dataset_id", "schema_version", "source_format")(_require_nonempty)
    _generated_at_utc = field_validator("generated_at")(_require_utc)

    @field_validator("source_sha256")
    @classmethod
    def validate_source_sha256(cls, value: str | None) -> str | None:
        if value is not None and not _SHA256.fullmatch(value):
            raise ValueError("source_sha256 must be a lowercase SHA-256 digest")
        return value

    @field_validator("limitations")
    @classmethod
    def validate_limitations(cls, value: list[str]) -> list[str]:
        if any(not item.strip() for item in value):
            raise ValueError("manifest limitations must not contain empty values")
        return value

    @field_validator("generation_id")
    @classmethod
    def validate_generation_id(cls, value: str) -> str:
        if not _SHA256.fullmatch(value):
            raise ValueError("generation_id must be a lowercase SHA-256 digest")
        return value

    @field_validator("artifact_checksums")
    @classmethod
    def validate_artifact_checksums(cls, value: dict[str, str]) -> dict[str, str]:
        if not value or any(not _SHA256.fullmatch(checksum) for checksum in value.values()):
            raise ValueError("artifact checksums must be lowercase SHA-256 digests")
        return value


class CommunityDataset(ContractModel):
    """Message-first dataset with optional Campaign and Outcome capabilities."""

    messages: list[MessageRecord]
    campaigns: list[CampaignRecord]
    claims: list[ClaimRecord]
    outcomes: list[OutcomeRecord]
    annotations: list[AnnotationRecord]
    manifest: DatasetManifest

    @model_validator(mode="after")
    def validate_references(self) -> CommunityDataset:
        message_ids = [message.message_id for message in self.messages]
        campaign_ids = [campaign.campaign_id for campaign in self.campaigns]
        claim_ids = [claim.claim_id for claim in self.claims]
        annotation_ids = [annotation.annotation_id for annotation in self.annotations]

        if len(message_ids) != len(set(message_ids)):
            raise ValueError("message_id values must be unique")
        if len(campaign_ids) != len(set(campaign_ids)):
            raise ValueError("campaign_id values must be unique")
        if len(claim_ids) != len(set(claim_ids)):
            raise ValueError("claim_id values must be unique")
        if len(annotation_ids) != len(set(annotation_ids)):
            raise ValueError("annotation_id values must be unique")
        if self.manifest.message_count != len(self.messages):
            raise ValueError("manifest message_count does not match messages")

        message_id_set = set(message_ids)
        campaign_id_set = set(campaign_ids)
        community_id_set = {message.community_id for message in self.messages}
        language_set = {message.language for message in self.messages}
        if (
            len(self.manifest.community_ids) != len(set(self.manifest.community_ids))
            or set(self.manifest.community_ids) != community_id_set
        ):
            raise ValueError("manifest community_ids do not match messages")
        if (
            len(self.manifest.languages) != len(set(self.manifest.languages))
            or set(self.manifest.languages) != language_set
        ):
            raise ValueError("manifest languages do not match messages")
        if (
            len(self.manifest.campaign_ids) != len(set(self.manifest.campaign_ids))
            or set(self.manifest.campaign_ids) != campaign_id_set
        ):
            raise ValueError("manifest campaign_ids do not match campaigns")
        if self.manifest.scenarios and set(self.manifest.scenarios) != community_id_set:
            raise ValueError("manifest scenarios do not match communities")

        message_by_id = {message.message_id: message for message in self.messages}
        for message in self.messages:
            if message.reply_to_message_id not in message_id_set | {None}:
                raise ValueError("reply_to_message_id must reference a dataset message")
            if message.reply_to_message_id == message.message_id:
                raise ValueError("a message cannot reply to itself")
            if message.campaign_id not in campaign_id_set | {None}:
                raise ValueError("message campaign_id must reference a dataset campaign")

        reply_state: dict[str, int] = {}

        def visit_reply(message_id: str) -> None:
            state = reply_state.get(message_id, 0)
            if state == 1:
                raise ValueError("reply graph must be acyclic")
            if state == 2:
                return
            reply_state[message_id] = 1
            parent_id = message_by_id[message_id].reply_to_message_id
            if parent_id is not None:
                visit_reply(parent_id)
            reply_state[message_id] = 2

        for message_id in message_ids:
            visit_reply(message_id)

        message_position = {message_id: index for index, message_id in enumerate(message_ids)}
        for message in self.messages:
            parent_id = message.reply_to_message_id
            if parent_id is None:
                continue
            parent = message_by_id[parent_id]
            if message_position[parent_id] >= message_position[message.message_id]:
                raise ValueError("reply must reference an earlier message")
            if message.timestamp < parent.timestamp:
                raise ValueError("reply timestamp must not be before parent timestamp")
            if message.community_id != parent.community_id:
                raise ValueError("replies must remain within a community")
            if (
                message.campaign_id is not None
                and parent.campaign_id is not None
                and message.campaign_id != parent.campaign_id
            ):
                raise ValueError("replies must remain within a campaign")

        if any(claim.campaign_id not in campaign_id_set for claim in self.claims):
            raise ValueError("claim campaign_id must reference a dataset campaign")
        if any(outcome.campaign_id not in campaign_id_set for outcome in self.outcomes):
            raise ValueError("outcome campaign_id must reference a dataset campaign")
        if any(outcome.community_id not in community_id_set for outcome in self.outcomes):
            raise ValueError("outcome community_id must reference a dataset community")
        if any(outcome.synthetic != self.manifest.synthetic for outcome in self.outcomes):
            raise ValueError("outcome synthetic flags must match the dataset manifest")
        outcome_pairs = [(outcome.community_id, outcome.campaign_id) for outcome in self.outcomes]
        if len(outcome_pairs) != len(set(outcome_pairs)):
            raise ValueError("outcome community/campaign pairs must be unique")
        if any(annotation.message_id not in message_id_set for annotation in self.annotations):
            raise ValueError("annotation message_id must reference a dataset message")
        return self


class SyntheticDataset(CommunityDataset):
    """Strict synthetic demo contract layered over the production dataset."""

    @model_validator(mode="before")
    @classmethod
    def require_synthetic_manifest(cls, value: object) -> object:
        if isinstance(value, dict):
            manifest = value.get("manifest")
            synthetic = (
                manifest.synthetic
                if isinstance(manifest, DatasetManifest)
                else manifest.get("synthetic")
                if isinstance(manifest, dict)
                else None
            )
            if synthetic is not True:
                raise ValueError("manifest synthetic must be true")
        return value

    @model_validator(mode="after")
    def validate_synthetic_contract(self) -> SyntheticDataset:
        community_ids = set(self.manifest.community_ids)
        campaign_ids = {campaign.campaign_id for campaign in self.campaigns}
        if set(self.manifest.scenarios) != community_ids:
            raise ValueError("manifest scenarios do not match communities")
        outcome_pairs = {(outcome.community_id, outcome.campaign_id) for outcome in self.outcomes}
        expected_outcome_pairs = {
            (community_id, campaign_id)
            for community_id in community_ids
            for campaign_id in campaign_ids
        }
        if outcome_pairs != expected_outcome_pairs:
            raise ValueError("outcomes must cover every community/campaign pair")
        return self
