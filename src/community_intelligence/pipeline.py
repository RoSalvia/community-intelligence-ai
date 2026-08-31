"""Deterministic, evidence-linked offline report pipeline."""

from __future__ import annotations

import hashlib
import json
import math
import os
import shutil
import tempfile
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, fields, is_dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer

from community_intelligence.activation import analyze_activation
from community_intelligence.behavior import classify_seed_behaviors, discover_clusters
from community_intelligence.campaign import (
    CampaignClaimResource,
    CampaignResource,
    analyze_campaign,
    summarize_campaign,
)
from community_intelligence.episodes import build_episodes
from community_intelligence.hygiene import analyze_hygiene
from community_intelligence.io import read_dataset
from community_intelligence.message_rules import normalize_text
from community_intelligence.metrics import adapt_metric_source, metric_catalog, validate_metrics
from community_intelligence.models import ClaimRecord, MessageRecord, SyntheticDataset

REPORT_SCHEMA_VERSION = "1.0"
ASSOCIATION_LIMIT = (
    "All statistical results are descriptive associations, not causal effects; "
    "synthetic evidence requires human review and external validation."
)
REVIEW_STATUS = "pending"

_RESOURCE_PATTERNS: Mapping[str, Mapping[str, tuple[str, ...]]] = {
    "stake_deadline": {
        "aliases": ("before Friday", "antes del viernes", "星期五", "الجمعة"),
        "incorrect_patterns": ("周日", "Sunday"),
    },
    "stake_reward": {
        "aliases": ("100 synthetic tokens", "100 tokens", "100 个代币", "100 رمز"),
        "incorrect_patterns": ("50 个代币", "50 tokens"),
    },
    "stake_eligibility": {
        "aliases": ("verified members", "miembros verificados", "已验证成员"),
    },
    "referral_count": {
        "aliases": (
            "two eligible friends",
            "dos amigos elegibles",
            "两名合格好友",
            "صديقين مؤهلين",
        ),
        "incorrect_patterns": ("一名好友", "one friend"),
    },
    "referral_reward": {
        "aliases": ("25 synthetic tokens", "25 tokens", "25 个代币", "25 رمز"),
        "incorrect_patterns": ("10 个代币", "10 tokens"),
    },
    "launch_date": {
        "aliases": (
            "launches September 20",
            "lanza el 20 de septiembre",
            "9 月 20 日",
            "20 سبتمبر",
        ),
        "incorrect_patterns": ("9 月 25 日", "September 25"),
    },
    "launch_feedback": {
        "aliases": (
            "feedback is invited",
            "solicitan comentarios",
            "邀请反馈",
            "التعليقات مرحب بها",
        ),
        "contradiction_patterns": ("不再征集反馈", "feedback is closed"),
    },
}

_PIPELINE_METRIC_CONTRACTS: Mapping[str, Mapping[str, str]] = {
    "campaign_discussion_share": {
        "formula": "campaign-linked real-user messages / all real-user messages",
        "denominator": "all real-user messages in the explicit campaign window",
    },
    "community_response_latency": {
        "formula": (
            "sum first direct moderator reply latency seconds / answered eligible user messages"
        ),
        "denominator": "eligible real-user messages with a direct moderator reply",
    },
    "conversation_propagation_depth": {
        "formula": ("sum episode longest-path message-node counts / conversation episodes"),
        "denominator": ("all reply-graph conversation episodes in the community-campaign window"),
    },
    "meaningful_interaction_ratio": {
        "formula": "qualifying real-user messages / all real-user messages",
        "denominator": "all real-user messages in the community-campaign window",
    },
    "organic_project_mention_rate": {
        "formula": "organic project mentions / non-campaign real-user messages",
        "denominator": "all non-campaign real-user messages in the campaign window",
    },
    "peer_support_ratio": {
        "formula": "peer-first answered user questions / all answered user questions",
        "denominator": "all structurally answered user questions in the follow-up graph",
    },
    "semantic_campaign_coverage": {
        "formula": "(covered + 0.5 * partially_covered) / total_claims",
        "denominator": "all atomic claims for the campaign in this community",
    },
    "semantic_drift_rate": {
        "formula": "(contradicted + incorrect) claim judgments / total_claims",
        "denominator": "all atomic claims for the campaign in this community",
    },
    "unanswered_question_rate": {
        "formula": "unanswered detected user questions / all detected user questions",
        "denominator": "all detected user questions in the community-campaign episodes",
    },
    "user_to_user_interaction_ratio": {
        "formula": "direct different-user reply messages / all real-user messages",
        "denominator": "all real-user messages in the community-campaign window",
    },
}


@dataclass(frozen=True)
class EvidenceRecord:
    evidence_id: str
    message_id: str | None
    claim_id: str | None
    campaign_id: str | None
    community_id: str | None
    source_text: str
    translation: str | None
    confidence: float | None
    confidence_semantics: str
    method: str
    review_status: str


class _EvidenceCollector:
    def __init__(self, messages: Sequence[MessageRecord]) -> None:
        self._messages = {message.message_id: message for message in messages}
        self._records: dict[str, EvidenceRecord] = {}

    def add(
        self,
        message_id: str,
        *,
        method: str,
        claim_id: str | None = None,
        campaign_id: str | None = None,
        community_id: str | None = None,
        confidence: float | None = None,
        confidence_semantics: str = "deterministic rule evidence; not a calibrated probability",
        translation: str | None = None,
    ) -> str:
        message = self._messages[message_id]
        identity = {
            "message_id": message_id,
            "claim_id": claim_id,
            "campaign_id": campaign_id,
            "community_id": community_id or message.community_id,
            "method": method,
        }
        digest = hashlib.sha256(
            json.dumps(identity, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()[:24]
        evidence_id = f"evidence_{digest}"
        record = EvidenceRecord(
            evidence_id=evidence_id,
            message_id=message_id,
            claim_id=claim_id,
            campaign_id=campaign_id or message.campaign_id,
            community_id=community_id or message.community_id,
            source_text=message.text,
            translation=translation,
            confidence=confidence,
            confidence_semantics=confidence_semantics,
            method=method,
            review_status=REVIEW_STATUS,
        )
        existing = self._records.get(evidence_id)
        if existing is not None and existing != record:
            raise ValueError("evidence identifier collision")
        self._records[evidence_id] = record
        return evidence_id

    def add_many(self, message_ids: Sequence[str], **metadata: Any) -> list[str]:
        return [self.add(message_id, **metadata) for message_id in message_ids]

    @property
    def records(self) -> tuple[EvidenceRecord, ...]:
        return tuple(self._records[key] for key in sorted(self._records))


def _jsonable(value: Any) -> Any:
    if is_dataclass(value):
        return _jsonable(_record_dict(value))
    if isinstance(value, Mapping):
        return {str(key): _jsonable(value[key]) for key in sorted(value, key=str)}
    if isinstance(value, (tuple, list, set, frozenset)):
        return [_jsonable(item) for item in value]
    if isinstance(value, datetime):
        return value.isoformat().replace("+00:00", "Z")
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating, float)):
        number = float(value)
        return number if math.isfinite(number) else None
    if isinstance(value, np.bool_):
        return bool(value)
    return value


def _record_dict(value: Any) -> dict[str, Any]:
    return {field.name: getattr(value, field.name) for field in fields(value)}


def _json_text(value: Any) -> str:
    return (
        json.dumps(_jsonable(value), ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False)
        + "\n"
    )


def _jsonl_text(values: Sequence[Any]) -> str:
    return "".join(
        json.dumps(
            _jsonable(value),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
        + "\n"
        for value in values
    )


def _write_text(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8", newline="")


def _resource_for_claim(claim: ClaimRecord) -> CampaignClaimResource:
    configured = _RESOURCE_PATTERNS.get(claim.claim_id)
    if configured is None:
        return CampaignClaimResource(claim_id=claim.claim_id, aliases=(claim.claim_text,))
    return CampaignClaimResource(
        claim_id=claim.claim_id,
        aliases=configured["aliases"],
        partial_aliases=configured.get("partial_aliases", ()),
        contradiction_patterns=configured.get("contradiction_patterns", ()),
        incorrect_patterns=configured.get("incorrect_patterns", ()),
        uncertain_patterns=configured.get("uncertain_patterns", ()),
    )


def _campaign_analysis(
    dataset: SyntheticDataset, collector: _EvidenceCollector
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[tuple[str, str], Any]]:
    claims_by_campaign: dict[str, list[ClaimRecord]] = defaultdict(list)
    for claim in dataset.claims:
        claims_by_campaign[claim.campaign_id].append(claim)
    judgments_output: list[dict[str, Any]] = []
    summaries_output: list[dict[str, Any]] = []
    summaries_by_key: dict[tuple[str, str], Any] = {}
    for campaign in sorted(dataset.campaigns, key=lambda item: item.campaign_id):
        claims = sorted(claims_by_campaign[campaign.campaign_id], key=lambda item: item.claim_id)
        resource = CampaignResource(
            campaign_id=campaign.campaign_id,
            claims=tuple(_resource_for_claim(claim) for claim in claims),
        )
        judgments = analyze_campaign(
            campaign,
            claims,
            dataset.messages,
            resource,
            community_ids=sorted(dataset.manifest.community_ids),
        )
        summaries = summarize_campaign(
            judgments, expected_claim_ids=[claim.claim_id for claim in claims]
        )
        for judgment in judgments:
            evidence_ids = collector.add_many(
                judgment.evidence_message_ids,
                method=judgment.method,
                claim_id=judgment.claim_id,
                campaign_id=judgment.campaign_id,
                community_id=judgment.community_id,
                confidence=judgment.confidence,
                confidence_semantics=judgment.confidence_semantics,
            )
            judgment_record = _record_dict(judgment)
            judgment_record.pop("evidence_message_ids")
            judgment_record.pop("evidence_text")
            judgments_output.append({**judgment_record, "evidence_ids": evidence_ids})
        for summary in summaries:
            summaries_by_key[(summary.campaign_id, summary.community_id)] = summary
            summaries_output.append(_record_dict(summary))
    judgments_output.sort(
        key=lambda item: (item["campaign_id"], item["community_id"], item["claim_id"])
    )
    summaries_output.sort(key=lambda item: (item["campaign_id"], item["community_id"]))
    return judgments_output, summaries_output, summaries_by_key


def _scope_rows(dataset: SyntheticDataset) -> list[tuple[Any, str, list[MessageRecord]]]:
    rows: list[tuple[Any, str, list[MessageRecord]]] = []
    for campaign in sorted(dataset.campaigns, key=lambda item: item.campaign_id):
        for community_id in sorted(dataset.manifest.community_ids):
            scoped = [
                message
                for message in dataset.messages
                if message.community_id == community_id
                and campaign.start_time <= message.timestamp < campaign.end_time
            ]
            rows.append((campaign, community_id, scoped))
    return rows


def _metric_value(numerator: float, denominator: int) -> tuple[float | None, str]:
    if denominator == 0:
        return None, "zero_denominator"
    return numerator / denominator, "observed"


def _adapt_single_metric(metric_name: str, source: Mapping[str, Any]) -> tuple[float | None, str]:
    adapted = adapt_metric_source(
        metric_name,
        pd.DataFrame([{"observation_id": "row", **source}]),
        observation_key_columns=("observation_id",),
    )
    value = adapted.iloc[0][metric_name]
    return (
        None if pd.isna(value) else float(value),
        str(adapted.iloc[0]["adapter_diagnostic_reason"]),
    )


def _peer_support_counts(
    episodes: Sequence[Any], message_by_id: Mapping[str, MessageRecord]
) -> tuple[int, int]:
    answered = 0
    peer_first = 0
    for episode in episodes:
        candidates: dict[str, list[str]] = defaultdict(list)
        for item in episode.candidate_answer_evidence:
            candidates[item.question_id].append(item.candidate_answer_id)
        for question_id, answer_ids in candidates.items():
            answered += 1
            first_id = min(
                answer_ids,
                key=lambda message_id: (
                    message_by_id[message_id].timestamp,
                    message_id,
                ),
            )
            question = message_by_id[question_id]
            answer = message_by_id[first_id]
            if answer.user_role == "user" and answer.user_id_hash != question.user_id_hash:
                peer_first += 1
    return peer_first, answered


def _select_cluster_count(messages: Sequence[MessageRecord]) -> int:
    if not messages:
        return 0
    texts = [normalize_text(message.text) for message in messages]
    try:
        matrix = TfidfVectorizer(
            analyzer="char", ngram_range=(2, 4), lowercase=True, sublinear_tf=True
        ).fit_transform(texts)
    except ValueError:
        return 0
    distinct_vectors = len(np.unique(matrix.toarray(), axis=0))
    size_target = max(1, int(round(math.sqrt(len(messages) / 2))))
    return min(8, size_target, distinct_vectors)


def _build_report(dataset: SyntheticDataset) -> tuple[dict[str, Any], tuple[EvidenceRecord, ...]]:
    collector = _EvidenceCollector(dataset.messages)
    message_by_id = {message.message_id: message for message in dataset.messages}
    campaign_judgments, campaign_summaries, campaign_summary_by_key = _campaign_analysis(
        dataset, collector
    )

    hygiene_rows: list[dict[str, Any]] = []
    activation_rows: list[dict[str, Any]] = []
    episode_rows: list[dict[str, Any]] = []
    metric_wide_rows: list[dict[str, Any]] = []
    metric_long_rows: list[dict[str, Any]] = []
    language_by_community = {
        community_id: next(
            message.language for message in dataset.messages if message.community_id == community_id
        )
        for community_id in dataset.manifest.community_ids
    }

    for campaign, community_id, scoped in _scope_rows(dataset):
        observation_id = f"{campaign.campaign_id}:{community_id}"
        hygiene = analyze_hygiene(scoped)
        activation = analyze_activation(scoped)
        episodes = build_episodes(scoped)

        hygiene_evidence_ids: list[str] = []
        for evidence in hygiene.evidence:
            hygiene_evidence_ids.extend(
                collector.add_many(
                    evidence.supporting_message_ids,
                    method=f"hygiene:{evidence.rule_id}",
                    campaign_id=campaign.campaign_id,
                    community_id=community_id,
                )
            )
        hygiene_rows.append(
            {
                "observation_id": observation_id,
                "campaign_id": campaign.campaign_id,
                "community_id": community_id,
                "duplicate_ratio": hygiene.duplicate_ratio,
                "filler_ratio": hygiene.filler_ratio,
                "repetitive_content_ratio": hygiene.repetitive_content_ratio,
                "burst_events": hygiene.burst_events,
                "formula_metadata": hygiene.metadata,
                "method": "deterministic_hygiene_rules",
                "review_status": REVIEW_STATUS,
                "evidence_ids": sorted(set(hygiene_evidence_ids)),
            }
        )

        activation_evidence_ids: list[str] = []
        for evidence in activation.evidence:
            activation_evidence_ids.extend(
                collector.add_many(
                    evidence.supporting_message_ids,
                    method=f"activation:{evidence.rule_id}",
                    campaign_id=campaign.campaign_id,
                    community_id=community_id,
                )
            )
        activation_rows.append(
            {
                "observation_id": observation_id,
                **_record_dict(activation),
                "campaign_id": campaign.campaign_id,
                "community_id": community_id,
                "method": "deterministic_activation_rules",
                "review_status": REVIEW_STATUS,
                "evidence_ids": sorted(set(activation_evidence_ids)),
            }
        )

        episode_evidence_ids: list[str] = []
        for episode in episodes:
            ids = collector.add_many(
                episode.message_ids,
                method="reply_graph_episode",
                campaign_id=campaign.campaign_id,
                community_id=community_id,
            )
            episode_evidence_ids.extend(ids)
            episode_rows.append(
                {
                    **_record_dict(episode),
                    "campaign_id": campaign.campaign_id,
                    "method": "deterministic_reply_graph",
                    "review_status": REVIEW_STATUS,
                    "evidence_ids": ids,
                }
            )

        users = [message for message in scoped if message.user_role == "user"]
        campaign_users = [
            message for message in users if message.campaign_id == campaign.campaign_id
        ]
        noncampaign_users = [message for message in users if message.campaign_id is None]
        campaign_discussion, campaign_discussion_reason = _metric_value(
            len(campaign_users), len(users)
        )
        organic_mentions = sum(
            "project" in normalize_text(message.text) for message in noncampaign_users
        )
        organic_rate, organic_reason = _metric_value(organic_mentions, len(noncampaign_users))
        peer_first, answered_questions = _peer_support_counts(episodes, message_by_id)
        peer_support, peer_reason = _adapt_single_metric(
            "peer_support_ratio",
            {
                "peer_first_answered_question_count": peer_first,
                "answered_user_question_count": answered_questions,
            },
        )
        total_questions = sum(episode.question_count for episode in episodes)
        unanswered_questions = sum(episode.unanswered_question_count for episode in episodes)
        unanswered_rate, unanswered_reason = _metric_value(unanswered_questions, total_questions)
        if episodes:
            adapted_depths = adapt_metric_source(
                "conversation_propagation_depth",
                pd.DataFrame(
                    [
                        {
                            "episode_id": episode.episode_id,
                            "conversation_depth": episode.conversation_depth,
                        }
                        for episode in episodes
                    ]
                ),
                observation_key_columns=("episode_id",),
            )
            propagation_depth = float(adapted_depths["conversation_propagation_depth"].mean())
            propagation_reason = "observed_episode_mean"
        else:
            propagation_depth = None
            propagation_reason = "zero_denominator"
        summary = campaign_summary_by_key[(campaign.campaign_id, community_id)]
        drift_rate, drift_reason = _metric_value(summary.semantic_drift_count, summary.total_claims)
        response_latency, response_reason = _adapt_single_metric(
            "community_response_latency",
            {
                "response_latency_seconds": activation.response_latency_seconds,
                "response_latency_denominator_count": activation.metadata[
                    "response_latency_seconds"
                ].denominator_count,
            },
        )
        status_counts = dict(summary.status_counts)
        semantic_coverage, semantic_coverage_reason = _adapt_single_metric(
            "semantic_campaign_coverage",
            {
                "covered": status_counts.get("covered", 0),
                "partially_covered": status_counts.get("partially_covered", 0),
                "total_claims": summary.total_claims,
            },
        )
        meaningful_value, meaningful_reason = _metric_value(
            activation.metadata["meaningful_interaction_ratio"].numerator_value,
            activation.metadata["meaningful_interaction_ratio"].denominator_count,
        )
        user_interaction_value, user_interaction_reason = _metric_value(
            activation.metadata["user_to_user_interaction_ratio"].numerator_value,
            activation.metadata["user_to_user_interaction_ratio"].denominator_count,
        )
        metric_values: dict[str, tuple[float | None, str]] = {
            "campaign_discussion_share": (campaign_discussion, campaign_discussion_reason),
            "community_response_latency": (response_latency, response_reason),
            "conversation_propagation_depth": (propagation_depth, propagation_reason),
            "meaningful_interaction_ratio": (meaningful_value, meaningful_reason),
            "organic_project_mention_rate": (organic_rate, organic_reason),
            "peer_support_ratio": (peer_support, peer_reason),
            "semantic_campaign_coverage": (
                semantic_coverage,
                semantic_coverage_reason,
            ),
            "semantic_drift_rate": (drift_rate, drift_reason),
            "unanswered_question_rate": (unanswered_rate, unanswered_reason),
            "user_to_user_interaction_ratio": (
                user_interaction_value,
                user_interaction_reason,
            ),
        }
        wide_row: dict[str, Any] = {
            "observation_id": observation_id,
            "campaign_id": campaign.campaign_id,
            "community_id": community_id,
            "language": language_by_community[community_id],
        }
        catalog = metric_catalog()
        for metric_name in sorted(catalog):
            value, diagnostic = metric_values[metric_name]
            wide_row[metric_name] = value
            metric_long_rows.append(
                {
                    "observation_id": observation_id,
                    "campaign_id": campaign.campaign_id,
                    "community_id": community_id,
                    "language": language_by_community[community_id],
                    "metric_name": metric_name,
                    "value": value,
                    "diagnostic": diagnostic,
                    "formula": _PIPELINE_METRIC_CONTRACTS[metric_name]["formula"],
                    "denominator": _PIPELINE_METRIC_CONTRACTS[metric_name]["denominator"],
                    "method": "canonical_deterministic_adapter",
                    "review_status": REVIEW_STATUS,
                    "evidence_ids": sorted(
                        set(
                            episode_evidence_ids
                            if metric_name
                            in {
                                "peer_support_ratio",
                                "conversation_propagation_depth",
                                "unanswered_question_rate",
                            }
                            else activation_evidence_ids
                            if metric_name
                            in {
                                "community_response_latency",
                                "meaningful_interaction_ratio",
                                "user_to_user_interaction_ratio",
                            }
                            else []
                        )
                    ),
                }
            )
        metric_wide_rows.append(wide_row)

    seed_labels = classify_seed_behaviors(dataset.messages)
    seed_output: list[dict[str, Any]] = []
    for message_id in sorted(seed_labels):
        label = seed_labels[message_id]
        evidence_ids = collector.add_many(
            label.evidence_message_ids,
            method=f"{label.method}:{label.rule_id}:{label.message_id}",
            confidence=label.confidence,
            confidence_semantics=label.confidence_semantics,
        )
        label_record = _record_dict(label)
        label_record.pop("evidence_message_ids")
        label_record.pop("evidence_texts")
        seed_output.append({**label_record, "evidence_ids": evidence_ids})

    cluster_count = _select_cluster_count(dataset.messages)
    clusters = (
        discover_clusters(dataset.messages, cluster_count=cluster_count, random_state=0)
        if cluster_count
        else ()
    )
    cluster_output: list[dict[str, Any]] = []
    for cluster in clusters:
        evidence_ids = collector.add_many(
            cluster.representative_message_ids,
            method=cluster.method,
            confidence=cluster.confidence,
        )
        cluster_record = _record_dict(cluster)
        cluster_record.pop("representative_message_ids")
        cluster_record.pop("representative_messages")
        cluster_output.append({**cluster_record, "evidence_ids": evidence_ids})

    metric_frame = pd.DataFrame(metric_wide_rows)
    outcome_frame = pd.DataFrame(
        [outcome.model_dump(mode="python") for outcome in dataset.outcomes]
    ).drop(columns=["synthetic"])
    validation = validate_metrics(
        metric_frame,
        outcome_frame,
        observation_key_columns=("campaign_id", "community_id"),
        metric_columns=tuple(sorted(metric_catalog())),
        outcome_columns=("conversion", "new_users", "participants", "referrals", "retention"),
        minimum_sample_size=5,
        minimum_group_size=2,
        synthetic=True,
    )

    role_counts = Counter(message.user_role for message in dataset.messages)
    language_counts = Counter(message.language for message in dataset.messages)
    report: dict[str, Any] = {
        "data_status": "synthetic",
        "schema_version": REPORT_SCHEMA_VERSION,
        "dataset_schema_version": dataset.manifest.schema_version,
        "generation_id": dataset.manifest.generation_id,
        "dataset_id": dataset.manifest.dataset_id,
        "analysis_methods": {
            "campaign": "curated_alias_baseline",
            "behavior": ["deterministic_seed_rule", "tfidf_kmeans"],
            "metrics": "canonical_deterministic_adapter + bounded_statistical_validation",
        },
        "limitations": {
            "general_multilingual_semantic_ai": "Not implemented",
            "association_not_causation": ASSOCIATION_LIMIT,
            "human_review": "All AI-like judgments and behavior clusters remain pending review.",
        },
        "Overview": {
            "message_count": len(dataset.messages),
            "community_count": len(dataset.manifest.community_ids),
            "campaign_count": len(dataset.campaigns),
            "claim_count": len(dataset.claims),
            "language_counts": dict(sorted(language_counts.items())),
            "role_counts": dict(sorted(role_counts.items())),
            "source_artifact_checksums": dataset.manifest.artifact_checksums,
        },
        "Campaign": {
            "judgments": campaign_judgments,
            "summaries": campaign_summaries,
            "resource_source": "explicit synthetic constants independent of annotations",
            "resource_patterns": _RESOURCE_PATTERNS,
            "method": "curated_alias_baseline",
            "review_status": REVIEW_STATUS,
        },
        "Hygiene": hygiene_rows,
        "Activation": activation_rows,
        "Episodes/Response Patterns": episode_rows,
        "Behavior": {
            "seed_labels": seed_output,
            "clusters": cluster_output,
            "selected_cluster_count": cluster_count,
            "selection_method": "min(8, sqrt(message_count/2), distinct_tfidf_vectors)",
            "review_status": REVIEW_STATUS,
        },
        "Metric Lab": {
            "observations": [
                {
                    **row,
                    "method": "canonical_deterministic_adapter",
                    "review_status": REVIEW_STATUS,
                    "diagnostics": {
                        record["metric_name"]: record["diagnostic"]
                        for record in metric_long_rows
                        if record["observation_id"] == row["observation_id"]
                    },
                }
                for row in metric_wide_rows
            ],
            "metric_records": sorted(
                metric_long_rows,
                key=lambda item: (item["metric_name"], item["observation_id"]),
            ),
            "definitions": metric_catalog(),
            "pipeline_contracts": _PIPELINE_METRIC_CONTRACTS,
            "validation": validation,
            "association_not_causation": ASSOCIATION_LIMIT,
        },
    }
    return report, collector.records


def _evidence_references(value: Any) -> set[str]:
    references: set[str] = set()
    if isinstance(value, Mapping):
        for key, item in value.items():
            if key == "evidence_ids":
                references.update(item)
            else:
                references.update(_evidence_references(item))
    elif isinstance(value, (list, tuple)):
        for item in value:
            references.update(_evidence_references(item))
    return references


def _validate_publication(report: dict[str, Any], evidence: Sequence[EvidenceRecord]) -> None:
    evidence_ids = [record.evidence_id for record in evidence]
    if len(evidence_ids) != len(set(evidence_ids)):
        raise ValueError("evidence IDs must be unique")
    if _evidence_references(report) != set(evidence_ids):
        raise ValueError("report/evidence referential integrity failure")


def _publish(output_path: Path, report: dict[str, Any], evidence: Sequence[EvidenceRecord]) -> Path:
    if os.path.lexists(output_path):
        raise FileExistsError(f"output path already exists: {output_path}")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(dir=output_path.parent, prefix=f".{output_path.name}.staging-"))
    reserved = False
    try:
        _write_text(staging / "report.json", _json_text(report))
        _write_text(staging / "evidence.jsonl", _jsonl_text(evidence))
        json.loads((staging / "report.json").read_text(encoding="utf-8"))
        for line in (staging / "evidence.jsonl").read_text(encoding="utf-8").splitlines():
            json.loads(line)
        os.mkdir(output_path)
        reserved = True
        for name in ("evidence.jsonl", "report.json"):
            os.rename(staging / name, output_path / name)
        return output_path
    except BaseException:
        if reserved and output_path.is_dir() and not output_path.is_symlink():
            shutil.rmtree(output_path)
        raise
    finally:
        if staging.exists():
            shutil.rmtree(staging)


def run_pipeline(dataset_dir: str | Path, output_dir: str | Path) -> Path:
    """Validate a six-artifact dataset and publish a deterministic report directory."""

    input_path = Path(dataset_dir).expanduser().resolve()
    output_path = Path(os.path.abspath(Path(output_dir).expanduser()))
    if os.path.lexists(output_path):
        raise FileExistsError(f"output path already exists: {output_path}")
    dataset = read_dataset(input_path)
    report, evidence = _build_report(dataset)
    _validate_publication(report, evidence)
    return _publish(output_path, report, evidence)
