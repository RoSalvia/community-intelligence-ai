"""Score locked external runs using separately recorded rubric adjudication."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from knowledge_external_validation import ROOT, baseline_hashes, save, sha


def summarize(base: Path, run_name: str, gold: Path, judgments: Path, output: Path):
    rows = json.loads((base / run_name / "results.json").read_text())
    grades = json.loads(judgments.read_text())["cases"]
    receipt = json.loads((base / run_name / "receipt.json").read_text())
    assert receipt["query_sha256"] == sha(gold.read_bytes())
    assert receipt["baseline"]["product_hashes"] == baseline_hashes()
    assert set(grades) == {r["question"]["id"] for r in rows}
    positives = [r for r in rows if r["question"]["gold"]]

    def complete(r):
        return grades[r["question"]["id"]]["grade"] == "complete"

    def average(subset):
        return {
            metric: sum(r["metrics"][metric] for r in subset) / len(subset)
            for metric in ("recall_at_5", "mrr_at_5", "ndcg_at_5", "hit_at_5")
        }

    def status_accuracy(kind):
        subset = [r for r in rows if r["question"]["type"] == kind]
        return {"correct": sum(r["status_correct"] for r in subset), "N": len(subset)}

    grounded = [r for r in rows if r["result"]["answer_status"] == "grounded"]
    quote_count = sum(len(c["evidence"]) for r in rows for c in r["result"]["claims"])
    chunks = json.loads((base / run_name / "chunks.json").read_text())
    # Validate every displayed claim quote against original source chunk, not its model status.
    for r in rows:
        for c in r["result"]["claims"]:
            for e in c["evidence"]:
                assert e["quote"].strip()
                assert " ".join(e["quote"].split()) in " ".join(
                    chunks[e["chunk_id"]]["text"].split()
                )
    metric = {
        "N": len(rows),
        "answerable_N": len(positives),
        "language_distribution": dict(Counter(r["question"]["language"] for r in rows)),
        "query_type_distribution": dict(Counter(r["question"]["type"] for r in rows)),
        "retrieval": average(positives),
        "by_language": {
            language: {"N": len(sub), **average(sub), "complete_answers": sum(map(complete, sub))}
            for language in ("en", "zh", "es")
            if (sub := [r for r in positives if r["question"]["language"] == language])
        },
        "cross_language": average([r for r in positives if r["question"]["language"] != "en"]),
        "complete_answer": {"correct": sum(map(complete, positives)), "N": len(positives)},
        "grades": dict(Counter(grades[r["question"]["id"]]["grade"] for r in positives)),
        "false_grounded_strict": {
            "count": sum(not complete(r) for r in grounded),
            "N": len(grounded),
            "definition": (
                "Grounded output that does not satisfy every locked rubric detail. "
                "Includes omissions, not only fabricated claims."
            ),
        },
        "false_no_answer": {
            "count": sum(
                r["result"]["answer_status"] in {"insufficient_evidence", "no_authoritative_source"}
                for r in positives
            ),
            "N": len(positives),
        },
        "insufficient_accuracy": status_accuracy("insufficient"),
        "no_answer_accuracy": status_accuracy("no_answer"),
        "historical_abstention_diagnostic": status_accuracy("historical_diagnostic"),
        "citation_integrity": {
            "valid": sum(sum(r["citation_valid"]) for r in rows),
            "N": sum(len(r["citation_valid"]) for r in rows),
        },
        "displayed_claim_quote_integrity": {"valid": quote_count, "N": quote_count},
        "queries_rejected_by_quote_validation": [
            r["question"]["id"] for r in rows if r["result"]["grounding"]["citation_valid"] is False
        ],
        "any_gold_in_candidate_pool": {
            "count": sum(
                any(c["ref"] in r["question"]["gold"] for c in r["candidate_pool"])
                for r in positives
            ),
            "N": len(positives),
        },
        "any_gold_in_rrf_top20": {
            "count": sum(
                any(c["ref"] in r["question"]["gold"] for c in r["candidate_pool"][:20])
                for r in positives
            ),
            "N": len(positives),
        },
        "all_required_context": {
            "count": sum(r["required_context_complete"] is True for r in positives),
            "N": sum(r["required_context_complete"] is not None for r in positives),
        },
        "remote_calls": sum(bool(r["answer_provider"]) for r in rows),
        "max_evidence_chars_sent": max(r["answer_provider"].get("evidence_chars", 0) for r in rows),
        "token_usage": sum(
            r["answer_provider"].get("usage", {}).get("total_tokens", 0) for r in rows
        ),
    }
    cases = []
    book = [
        "# Per-query failure and regression review",
        "",
        "Retrieval scores refer to unchanged original query; no rewrite or reranker. "
        "Raw source/answer bodies remain in ignored local run artifacts.",
        "",
    ]
    corpus = json.loads((base / "corpus.lock.json").read_text())["spec"]
    source_base = f"{corpus['repository_url']}/blob/{corpus['commit_sha']}"
    for r in rows:
        q = r["question"]
        grade = grades[q["id"]]
        tags = []
        candidate_refs = {c["ref"] for c in r["candidate_pool"]}
        if q["gold"] and not (set(q["gold"]) & candidate_refs):
            tags.append("candidate_retrieval_miss")
        elif q["gold"] and r["metrics"]["hit_at_5"] == 0:
            tags.append("correct_candidate_low_rank")
        if q["language"] != "en" and tags:
            tags.append("cross_language_ranking")
        if grade["grade"] == "partial":
            tags.append("strict_rubric_omission")
        if r["result"]["grounding"]["citation_valid"] is False:
            tags.append("citation_generation_failure")
        if grade["grade"] == "abstain":
            tags.append("false_no_answer")
        if q["id"] == "H18":
            tags.append("answerability_overdecomposition")
        if grade["grade"] != "complete" and q["gold"] and r["expanded_gold_recall"] < 1:
            tags.append("incomplete_selected_context")
        case = {
            "question": q,
            "grade": grade,
            "taxonomy": tags,
            "actual_top_k": r["actual_top_k"],
            "expected_diagnostics": r["expected_diagnostics"],
            "candidate_pool": r["candidate_pool"],
            "metrics": r["metrics"],
            "expanded_gold_recall": r["expanded_gold_recall"],
            "returned_status": r["result"]["answer_status"],
            "answerability": r["result"]["answerability"],
        }
        cases.append(case)
        book.extend(
            [
                f"## {q['id']} — {grade['grade']}",
                "",
                q["query"],
                "",
                f"Expected: `{', '.join(q['gold'] or q.get('related', [])) or 'none'}` "
                f"· {q['expected_status']}",
                "",
                f"Returned: {r['result']['answer_status']} "
                f"· Recall@5 {r['metrics']['recall_at_5']}",
                "",
                grade["reason"],
                "",
                "Taxonomy: " + (", ".join(tags) or "none"),
                "",
                "| Actual Top-K | Section | BM25 | Lex rank | Cosine "
                "| Semantic rank | Raw RRF rank | RRF score |",
                "|---|---|---:|---:|---:|---:|---:|---:|",
            ]
        )
        for c in r["actual_top_k"]:
            section = (c["section"] or "—").replace("|", "/")
            book.append(
                f"| {c['ref']} | {section} | {c['bm25']} | {c['lexical_rank']} "
                f"| {c['semantic_similarity']:.4f} | {c['semantic_rank']} "
                f"| {c['rrf_rank']} | {c['rrf_score']} |"
            )
        book.extend(["", "Expected evidence diagnostics:", ""])
        for c in r["expected_diagnostics"]:
            book.append(
                f"- `{c['ref']}` / {c['section']}: lexical {c['lexical_rank']} "
                f"(BM25 {c['bm25']}), semantic {c['semantic_rank']} "
                f"({c['semantic_similarity']:.4f}), RRF {c['rrf_rank']}; "
                f"[pinned source]({source_base}/{c['path']})."
            )
        book.append("")
    save(
        output / "results.json",
        {
            "metrics": metric,
            "receipt": receipt,
            "adjudication_sha256": sha(judgments.read_bytes()),
            "cases": cases,
        },
    )
    (output / "CASEBOOK.md").write_text("\n".join(book))
    print(output.name, json.dumps(metric, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    summarize(
        ROOT / "data/generated/validation/ton-docs-v1",
        "m2-1-regression-run-1",
        ROOT / "docs/validation/ton-docs-v1/queries.json",
        ROOT / "docs/validation/m2-1/regression_adjudication.json",
        ROOT / "docs/validation/m2-1/regression",
    )
    summarize(
        ROOT / "data/generated/validation/ton-docs-holdout-v1",
        "m2-1-holdout-run-1",
        ROOT / "docs/validation/ton-docs-holdout-v1/queries.json",
        ROOT / "docs/validation/ton-docs-holdout-v1/adjudication.json",
        ROOT / "docs/validation/m2-1/holdout",
    )
