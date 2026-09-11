from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType


def _load_module() -> ModuleType:
    path = Path(__file__).parents[1] / "scripts" / "validation" / "blum_multilingual_json_intake.py"
    spec = importlib.util.spec_from_file_location("blum_multilingual_json_intake", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


MODULE = _load_module()
canonical_source_decision = MODULE.canonical_source_decision
pair_overlap_timelines = MODULE.pair_overlap_timelines


def test_pair_overlap_timelines_keeps_shared_axis_and_zero_fills_missing_side() -> None:
    cn = [{"window_start": "2024-05-16T16:00:00+00:00", "message_count": 3, "question_count": 1}]
    es = [{"window_start": "2024-05-16T17:00:00+00:00", "message_count": 4, "question_count": 2}]

    paired = pair_overlap_timelines(cn, es, metric_names=("message_count", "question_count"))

    assert paired == [
        {
            "window_start": "2024-05-16T16:00:00+00:00",
            "cn_message_count": 3,
            "es_message_count": 0,
            "cn_question_count": 1,
            "es_question_count": 0,
        },
        {
            "window_start": "2024-05-16T17:00:00+00:00",
            "cn_message_count": 0,
            "es_message_count": 4,
            "cn_question_count": 0,
            "es_question_count": 2,
        },
    ]


def test_preferred_source_decision_is_gate_based_not_a_composite_score() -> None:
    decision = canonical_source_decision(
        snapshot_stable=True,
        absolute_timestamps=True,
        json_identity_coverage=0.99,
        json_reply_resolution=0.95,
        html_reply_resolution=0.58,
    )

    assert decision["preferred_source"] == "telegram_desktop_json"
    assert decision["recommendation"] == "yes"
    assert decision["no_composite_score"] is True
    assert all(item["passed"] for item in decision["gates"])


def test_preferred_source_decision_abstains_when_identity_gate_fails() -> None:
    decision = canonical_source_decision(
        snapshot_stable=True,
        absolute_timestamps=True,
        json_identity_coverage=0.4,
        json_reply_resolution=0.95,
        html_reply_resolution=0.58,
    )

    assert decision["preferred_source"] == "undecided"
    assert decision["recommendation"] == "insufficient_evidence"
