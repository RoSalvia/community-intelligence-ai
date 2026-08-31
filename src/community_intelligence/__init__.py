"""Validated contracts and synthetic data for Community Intelligence AI."""

from community_intelligence.models import (
    AnnotationRecord,
    CampaignRecord,
    ClaimRecord,
    DatasetManifest,
    MessageRecord,
    OutcomeRecord,
    SyntheticDataset,
)
from community_intelligence.synthetic import generate_dataset

__all__ = [
    "AnnotationRecord",
    "CampaignRecord",
    "ClaimRecord",
    "DatasetManifest",
    "MessageRecord",
    "OutcomeRecord",
    "SyntheticDataset",
    "generate_dataset",
]

__version__ = "0.1.0"
