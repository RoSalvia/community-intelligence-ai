from datetime import UTC, datetime

import numpy as np

from community_intelligence.application.knowledge import KnowledgeService
from test_knowledge import knowledge as _knowledge
from test_knowledge import source

knowledge = _knowledge


def test_index_uses_structure_but_citation_body_is_original(knowledge):
    service, workspace = knowledge
    seen = []

    class Embedder:
        def embed(self, texts):
            seen.extend(texts)
            return np.array([[1.0, 0.0] for _ in texts])

    service.embedder = Embedder()
    document = (
        "# Protocol\n\n## Release 7\n\n### Queue limit?\n\nRead maxOperations in client.features."
    )
    revision = service.add_source(workspace, source(title="Atlas Manual", content=document))
    chunk = revision["chunks"][0]
    assert chunk["text"] == "Read maxOperations in client.features."
    assert chunk["section"] == "Queue limit?"
    assert chunk["parent_heading"] == "Protocol > Release 7 > Queue limit?"
    assert all(t in seen[0] for t in ("Atlas Manual", "Protocol", "Release 7", "Queue limit?"))
    assert service._lexical(["queue"], 20, workspace) == [chunk["chunk_id"]]
    assert service.get_chunk(chunk["chunk_id"])["text"] == chunk["text"]


def test_representation_change_reembeds_but_unchanged_revision_does_not(knowledge):
    service, workspace = knowledge
    batches = []

    class Embedder:
        def embed(self, texts):
            batches.append(texts)
            return np.array([[1.0, 0.0] for _ in texts])

    service.embedder = Embedder()
    first = service.add_source(workspace, source(title="Recovery"))
    service.add_revision(first["source_id"], source(title="Recovery"))
    assert len(batches) == 1
    service.add_source(workspace, source(title="Unrelated topic"))
    assert len(batches) == 2


def test_lexical_limit_is_within_workspace(knowledge):
    from sqlalchemy import insert

    from community_intelligence.infrastructure.database import workspaces

    service, workspace = knowledge
    with service.database.engine.begin() as con:
        original = con.execute(workspaces.select()).mappings().first()
        con.execute(insert(workspaces).values(**{**dict(original), "workspace_id": "other"}))
    service.add_source("other", source(content="Needle " * 10))
    own = service.add_source(workspace, source(content="Needle documentation."))
    assert service._lexical(["needle"], 1, workspace) == [own["chunks"][0]["chunk_id"]]


def test_policy_keeps_rrf_evidence_despite_lower_similarity(knowledge):
    service, workspace = knowledge
    revision = service.add_source(
        workspace,
        source(content="# Queue\n\nFirst related fragment.\n\nThe complete restriction is here."),
    )
    ids = [c["chunk_id"] for c in revision["chunks"]]
    service._lexical = lambda terms, limit, workspace_id=None: ids
    service._semantic = lambda query, workspace_id, limit: {ids[0]: 0.9, ids[1]: 0.48}
    result = service.query(workspace, "first related fragment restriction")
    assert [c["chunk_id"] for c in result["citations"]] == ids


def test_policy_does_not_hide_higher_rrf_inactive_evidence():
    candidates = [
        {
            "chunk_id": "old",
            "official_status": "verified_official",
            "status": "historical",
            "temporal_state": "inactive",
            "rrf_score": 0.03,
            "retrieval_channels": 2,
        },
        {
            "chunk_id": "current",
            "official_status": "verified_official",
            "status": "current",
            "temporal_state": "active",
            "rrf_score": 0.02,
            "retrieval_channels": 2,
        },
    ]

    selected = KnowledgeService._select_candidates(
        candidates, {"old": 0.03, "current": 0.02}, top_k=1
    )

    assert [item["chunk_id"] for item in selected] == ["old"]


def test_policy_preserves_rrf_order_within_temporal_group():
    candidates = [
        {
            "chunk_id": "second",
            "official_status": "verified_official",
            "status": "current",
            "temporal_state": "active",
            "rrf_score": 0.02,
            "retrieval_channels": 2,
        },
        {
            "chunk_id": "first",
            "official_status": "verified_official",
            "status": "current",
            "temporal_state": "active",
            "rrf_score": 0.03,
            "retrieval_channels": 2,
        },
    ]

    selected = KnowledgeService._select_candidates(
        candidates, {"second": 0.02, "first": 0.03}, top_k=2
    )

    assert [item["chunk_id"] for item in selected] == ["first", "second"]


def test_source_diversity_replaces_only_one_lowest_dominant_candidate():
    base = [
        {"chunk_id": f"a{index}", "source_id": "a"}
        for index in range(12)
    ] + [
        {"chunk_id": f"b{index}", "source_id": "b"}
        for index in range(8)
    ]
    deeper = base + [{"chunk_id": "c0", "source_id": "c"}]

    selected = KnowledgeService._source_diverse_candidates(base, deeper, 20)

    assert [item["chunk_id"] for item in selected[:5]] == [f"a{index}" for index in range(5)]
    assert len(selected) == 20
    assert {item["chunk_id"] for item in base} - {item["chunk_id"] for item in selected} == {
        "a11"
    }
    assert selected[11]["chunk_id"] == "c0"


def test_source_diversity_leaves_non_majority_pool_unchanged():
    base = [
        {"chunk_id": f"a{index}", "source_id": "a"}
        for index in range(10)
    ] + [
        {"chunk_id": f"b{index}", "source_id": "b"}
        for index in range(10)
    ]

    assert KnowledgeService._source_diverse_candidates(
        base, base + [{"chunk_id": "c0", "source_id": "c"}], 20
    ) == base


def test_source_diversity_preserves_original_rrf_order_on_deeper_pool():
    base = [
        {"chunk_id": f"a{index}", "source_id": "a"}
        for index in range(12)
    ] + [
        {"chunk_id": f"b{index}", "source_id": "b"}
        for index in range(8)
    ]
    deeper = [base[3], base[1], {"chunk_id": "c0", "source_id": "c"}, *base]

    selected = KnowledgeService._source_diverse_candidates(base, deeper, 20)

    assert selected[:11] == base[:11]
    assert selected[11]["chunk_id"] == "c0"
    assert selected[12:] == base[12:]


def test_future_source_is_not_outdated_evidence(knowledge):
    service, workspace = knowledge
    service.add_source(workspace, source())
    result = service.query(
        workspace, "recovery phrase", as_of_time=datetime(2024, 1, 1, tzinfo=UTC)
    )
    assert result["answer_status"] == "no_authoritative_source"
    assert result["citations"] == []
    assert result["retrieval"]["ranking"] == "rrf"
    assert result["retrieval"]["reranker"] == {
        "status": "not_run",
        "fallback": False,
        "candidate_count": 0,
        "evidence_chars": 0,
    }


def test_explicit_reindex_preserves_source_chunk_identity_and_is_incremental(knowledge):
    from sqlalchemy import text, update

    from community_intelligence.infrastructure.database import knowledge_chunks, knowledge_revisions

    service, workspace = knowledge
    original = service.add_source(
        workspace, source(content="# Parent\n\n## Child\n\nOriginal body.")
    )
    cid = original["chunks"][0]["chunk_id"]
    with service.database.engine.begin() as con:
        con.execute(
            update(knowledge_chunks)
            .where(knowledge_chunks.c.chunk_id == cid)
            .values(parent_heading="Child")
        )
        con.execute(update(knowledge_revisions).values(index_version="sqlite-fts5-rrf-v1"))
        con.execute(
            text("UPDATE knowledge_chunks_fts SET text='Original body.' WHERE chunk_id=:id"),
            {"id": cid},
        )
    blocked = service.query(workspace, "body")
    assert blocked["retrieval"]["status"] == "reindex_required"
    assert blocked["retrieval"]["stale_revision_ids"] == [original["revision_id"]]
    result = service.reindex_revision(original["revision_id"])
    assert result["reindexed"] is True
    assert service.get_chunk(cid)["parent_heading"] == "Parent > Child"
    assert service.get_chunk(cid)["text"] == "Original body."
    assert service.get_revision(original["revision_id"])["content_hash"] == original["content_hash"]
    assert service._lexical(["parent"], 5, workspace) == [cid]
    assert service.reindex_revision(original["revision_id"])["reindexed"] is False


def test_bounded_packet_includes_selected_hit_before_large_previous_neighbor(knowledge):
    service, workspace = knowledge
    revision = service.add_source(
        workspace, source(content="# Bounds\n\n" + "x" * 300 + "\n\nAnswer fact.")
    )
    service._lexical = lambda terms, limit, workspace_id=None: [revision["chunks"][1]["chunk_id"]]
    result = service.query(workspace, "answer fact", max_context_chars=40)
    context = result["citations"][0]["context"]
    assert any(c["text"] == "Answer fact." for c in context)
    assert sum(len(c["text"]) for c in context) <= 40


def test_relevance_without_answer_model_does_not_claim_grounded(knowledge):
    service, workspace = knowledge
    service.add_source(workspace, source(content="# Exact gas fee\n\nExact gas fee: TBD."))
    result = service.query(workspace, "exact gas fee")
    assert result["answer_status"] == "insufficient_evidence"
    assert result["answerability"]["status"] == "unavailable"


def test_answer_uses_all_required_facts_and_neighbor_citations(knowledge):
    service, workspace = knowledge
    revision = service.add_source(
        workspace,
        source(content="# Retries\n\nThe delay is two seconds.\n\nThe retry limit is three."),
    )
    first, second = revision["chunks"]
    service._lexical = lambda terms, limit, workspace_id=None: [first["chunk_id"]]

    class Answerer:
        def assess(self, query, evidence):
            assert {e["chunk_id"] for e in evidence} == {first["chunk_id"], second["chunk_id"]}
            return {
                "relevance": "related",
                "requirements": [
                    {"id": "r1", "fact_needed": "delay", "status": "supported"},
                    {"id": "r2", "fact_needed": "limit", "status": "supported"},
                ],
                "claims": [
                    {
                        "requirement_id": f"r{n}",
                        "text": c["text"],
                        "evidence": [{"chunk_id": c["chunk_id"], "quote": c["text"]}],
                    }
                    for n, c in enumerate([first, second], 1)
                ],
            }

    service.answerer = Answerer()
    result = service.query(workspace, "What are the retry delay and limit?")
    assert result["answer_status"] == "grounded"
    assert "two seconds" in result["answer"] and "three" in result["answer"]
    assert result["grounding"]["citation_valid"] is True


def test_missing_fact_or_invented_citation_cannot_be_grounded(knowledge):
    service, workspace = knowledge
    revision = service.add_source(workspace, source(content="Fee: TBD."))
    chunk = revision["chunks"][0]

    class Answerer:
        def assess(self, query, evidence):
            return {
                "relevance": "related",
                "requirements": [
                    {"id": "r1", "fact_needed": "precise fee", "status": "unsupported"}
                ],
                "claims": [],
            }

    service.answerer = Answerer()
    assert service.query(workspace, "precise fee")["answer_status"] == "insufficient_evidence"

    class InventedAnswerer:
        def assess(self, query, evidence):
            return {
                "relevance": "related",
                "requirements": [{"id": "r1", "fact_needed": "precise fee", "status": "supported"}],
                "claims": [
                    {
                        "requirement_id": "r1",
                        "text": "Fee is 1 token.",
                        "evidence": [{"chunk_id": chunk["chunk_id"], "quote": "Fee is 1 token."}],
                    }
                ],
            }

    service.answerer = InventedAnswerer()
    result = service.query(workspace, "precise fee")
    assert result["answer_status"] == "insufficient_evidence"
    assert result["grounding"]["citation_valid"] is False


def test_conflict_requires_two_original_sources_and_no_silent_reconciliation(knowledge):
    service, workspace = knowledge
    a = service.add_source(workspace, source(content="Maintenance starts at 10:00 UTC."))
    b = service.add_source(workspace, source(content="Maintenance starts at 11:00 UTC."))

    class Answerer:
        def assess(self, query, evidence):
            return {
                "relevance": "related",
                "requirements": [
                    {"id": "time", "fact_needed": "maintenance time", "status": "conflict"}
                ],
                "claims": [
                    {
                        "requirement_id": "time",
                        "text": e["text"],
                        "evidence": [{"chunk_id": e["chunk_id"], "quote": e["text"]}],
                    }
                    for e in evidence
                ],
            }

    service.answerer = Answerer()
    result = service.query(workspace, "maintenance time")
    assert result["answer_status"] == "conflict"
    assert {c["source_id"] for c in result["citations"]} == {a["source_id"], b["source_id"]}
    assert "10:00" in result["answer"] and "11:00" in result["answer"]


def test_outdated_evidence_cannot_support_current_answer(knowledge):
    service, workspace = knowledge
    service.add_source(
        workspace,
        source(content="Limit is 10 tokens.", effective_until=datetime(2026, 2, 1, tzinfo=UTC)),
    )

    class Answerer:
        def assess(self, query, evidence):
            e = evidence[0]
            return {
                "relevance": "related",
                "requirements": [{"id": "r", "fact_needed": "limit", "status": "supported"}],
                "claims": [
                    {
                        "requirement_id": "r",
                        "text": e["text"],
                        "evidence": [{"chunk_id": e["chunk_id"], "quote": e["text"]}],
                    }
                ],
            }

    service.answerer = Answerer()
    assert service.query(workspace, "limit")["answer_status"] == "outdated_only"


def test_outdated_evidence_survives_unrelated_active_candidate(knowledge):
    service, workspace = knowledge
    old = service.add_source(
        workspace,
        source(
            title="Legacy batching",
            content="Legacy batches ran every fifteen minutes.",
            effective_until=datetime(2026, 2, 1, tzinfo=UTC),
            status="historical",
        ),
    )
    current = service.add_source(workspace, source(content="Current finality is eight blocks."))
    old_chunk = old["chunks"][0]
    current_chunk = current["chunks"][0]
    service._lexical = lambda terms, limit, workspace_id=None: [
        old_chunk["chunk_id"],
        current_chunk["chunk_id"],
    ]

    class Answerer:
        def assess(self, query, evidence):
            assert {item["temporal_state"] for item in evidence} == {"active", "inactive"}
            return {
                "relevance": "related",
                "requirements": [
                    {"id": "interval", "fact_needed": "legacy interval", "status": "supported"}
                ],
                "claims": [
                    {
                        "requirement_id": "interval",
                        "text": old_chunk["text"],
                        "evidence": [
                            {
                                "chunk_id": old_chunk["chunk_id"],
                                "quote": old_chunk["text"],
                            }
                        ],
                    }
                ],
            }

    service.answerer = Answerer()
    result = service.query(workspace, "legacy fifteen minute interval")
    assert result["answer_status"] == "outdated_only"
    assert result["claims"][0]["evidence"][0]["chunk_id"] == old_chunk["chunk_id"]


def test_confirmed_historical_without_end_is_background_for_current_but_valid_as_of(
    knowledge,
):
    service, workspace = knowledge
    old = service.add_source(
        workspace,
        source(
            title="Historical routing note",
            content="Routing is always instant.",
            published_at=datetime(2022, 1, 1, tzinfo=UTC),
            effective_from=datetime(2022, 1, 1, tzinfo=UTC),
            status="historical",
        ),
    )
    current = service.add_source(
        workspace,
        source(
            title="Current routing docs",
            content="Routing can be delayed during congestion.",
            published_at=datetime(2026, 1, 1, tzinfo=UTC),
            effective_from=datetime(2026, 1, 1, tzinfo=UTC),
        ),
    )
    old_chunk = old["chunks"][0]
    current_chunk = current["chunks"][0]
    service._lexical = lambda terms, limit, workspace_id=None: [
        old_chunk["chunk_id"],
        current_chunk["chunk_id"],
    ]

    class Answerer:
        def assess(self, query, evidence):
            return {
                "relevance": "related",
                "requirements": [
                    {"id": "routing", "fact_needed": "routing delay", "status": "supported"}
                ],
                "claims": [
                    {
                        "requirement_id": "routing",
                        "text": item["text"],
                        "evidence": [
                            {"chunk_id": item["chunk_id"], "quote": item["text"]}
                        ],
                    }
                    for item in evidence
                ],
            }

    service.answerer = Answerer()
    present = service.query(workspace, "routing delay")
    historical = service.query(
        workspace,
        "routing delay",
        as_of_time=datetime(2023, 1, 1, tzinfo=UTC),
    )

    assert present["answer_status"] == "grounded"
    assert [claim["text"] for claim in present["claims"]] == [current_chunk["text"]]
    assert historical["answer_status"] == "grounded"
    assert [claim["text"] for claim in historical["claims"]] == [old_chunk["text"]]


def test_system_derived_historical_status_does_not_lower_current_priority(knowledge):
    service, workspace = knowledge
    inferred_provenance = source().metadata_provenance | {"validity": "system-derived"}
    old = service.add_source(
        workspace,
        source(
            title="Unconfirmed historical label",
            content="Limit is 10 tokens.",
            published_at=datetime(2025, 1, 1, tzinfo=UTC),
            effective_from=datetime(2025, 1, 1, tzinfo=UTC),
            status="historical",
            metadata_provenance=inferred_provenance,
        ),
    )
    current = service.add_source(workspace, source(content="Limit is 20 tokens."))
    chunks = [old["chunks"][0], current["chunks"][0]]
    service._lexical = lambda terms, limit, workspace_id=None: [
        item["chunk_id"] for item in chunks
    ]

    class Answerer:
        def assess(self, query, evidence):
            assert {item["temporal_state"] for item in evidence} == {"active"}
            return {
                "relevance": "related",
                "requirements": [
                    {"id": "limit", "fact_needed": "limit", "status": "conflict"}
                ],
                "claims": [
                    {
                        "requirement_id": "limit",
                        "text": item["text"],
                        "evidence": [
                            {"chunk_id": item["chunk_id"], "quote": item["text"]}
                        ],
                    }
                    for item in evidence
                ],
            }

    service.answerer = Answerer()

    assert service.query(workspace, "limit")["answer_status"] == "conflict"


def _rerank_fixture(service, workspace):
    revisions = [
        service.add_source(workspace, source(title=f"Guide {n}", content=f"Fact number {n}."))
        for n in range(6)
    ]
    ids = [revision["chunks"][0]["chunk_id"] for revision in revisions]
    service._lexical = lambda terms, limit, workspace_id=None: ids
    service._semantic = lambda query, workspace_id, limit: {
        chunk_id: 1 - index / 10 for index, chunk_id in enumerate(ids)
    }
    return ids


def test_configured_reranker_reorders_only_policy_candidates(knowledge):
    service, workspace = knowledge
    ids = _rerank_fixture(service, workspace)

    class Answerer:
        def rerank(self, query, candidates):
            assert query == "fact"
            assert [item["chunk_id"] for item in candidates] == ids
            assert all(
                set(item)
                == {
                    "chunk_id",
                    "title",
                    "source_type",
                    "section",
                    "parent_heading",
                    "text",
                    "temporal_state",
                }
                for item in candidates
            )
            return list(reversed(ids)), {
                "latency_ms": 12.0,
                "usage": {"prompt_tokens": 20, "completion_tokens": 6, "total_tokens": 26},
                "evidence_chars": 84,
            }

        def assess(self, query, evidence):
            return {"relevance": "unrelated", "requirements": [], "claims": []}

    service.answerer = Answerer()
    result = service.query(workspace, "fact")

    assert [item["chunk_id"] for item in result["citations"]] == list(reversed(ids))[:5]
    assert result["retrieval"]["ranking"] == "multilingual_reranker"
    assert result["retrieval"]["reranker"]["status"] == "applied"
    assert result["retrieval"]["reranker"]["fallback"] is False


def test_invalid_reranker_ids_fall_back_to_original_rrf_order(knowledge):
    service, workspace = knowledge
    ids = _rerank_fixture(service, workspace)

    class Answerer:
        def rerank(self, query, candidates):
            return [ids[1], ids[1], "unknown", *ids[2:5]], {"latency_ms": 1.0}

        def assess(self, query, evidence):
            return {"relevance": "unrelated", "requirements": [], "claims": []}

    service.answerer = Answerer()
    result = service.query(workspace, "fact")

    assert [item["chunk_id"] for item in result["citations"]] == ids[:5]
    assert result["retrieval"]["ranking"] == "rrf"
    assert result["retrieval"]["reranker"]["status"] == "invalid_response"
    assert result["retrieval"]["reranker"]["fallback"] is True


def test_reranker_provider_failure_falls_back_to_original_rrf_order(knowledge):
    service, workspace = knowledge
    ids = _rerank_fixture(service, workspace)

    class Answerer:
        def rerank(self, query, candidates):
            raise RuntimeError("timeout")

        def assess(self, query, evidence):
            return {"relevance": "unrelated", "requirements": [], "claims": []}

    service.answerer = Answerer()
    result = service.query(workspace, "fact")

    assert [item["chunk_id"] for item in result["citations"]] == ids[:5]
    assert result["retrieval"]["ranking"] == "rrf"
    assert result["retrieval"]["reranker"]["status"] == "provider_error"
    assert result["retrieval"]["reranker"]["fallback"] is True


def test_unconfigured_remote_provider_keeps_rrf_top_five(knowledge):
    service, workspace = knowledge
    ids = _rerank_fixture(service, workspace)
    service.answerer = None

    result = service.query(workspace, "fact")

    assert [item["chunk_id"] for item in result["citations"]] == ids[:5]
    assert result["retrieval"]["ranking"] == "rrf"
    assert result["retrieval"]["reranker"] == {
        "status": "not_configured",
        "fallback": True,
        "candidate_count": 6,
        "evidence_chars": 84,
    }
