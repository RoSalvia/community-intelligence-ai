#!/usr/bin/env python3
"""Validation only: pin a small GitHub corpus; never change product ingestion."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.request import Request, urlopen

from community_intelligence.evaluation import retrieval_metrics

ROOT = Path(__file__).resolve().parents[2]


def baseline_hashes() -> dict[str, str]:
    paths = sorted((ROOT / "src").rglob("*.py")) + [ROOT / "pyproject.toml", ROOT / "uv.lock"]
    return {str(p.relative_to(ROOT)): sha(p.read_bytes()) for p in paths}


def source_input(item: dict, lock: dict, output: Path):
    from community_intelligence.application.knowledge import SourceInput

    at = datetime.fromisoformat(lock["retrieved_at"])
    raw = (output / "raw" / item["path"]).read_bytes()
    assert sha(raw) == next(f["sha256"] for f in lock["files"] if f["path"] == item["path"])
    body = raw.decode("utf-8")
    title_match = re.search(r"^title:\s*(.+)$", body, re.M)
    if title_match is None:
        raise ValueError(f"Validation source has no frontmatter title: {item['path']}")
    title = title_match.group(1).strip().strip("\"'")
    return SourceInput(
        title=title,
        source_type=item["source_type"],
        source_channel="github",
        content=body,
        canonical_url=f"{lock['spec']['repository_url']}/blob/{lock['spec']['commit_sha']}/{item['path']}",
        platform="github",
        platform_content_id=lock["spec"]["commit_sha"] + ":" + item["path"],
        language="en",
        project_scope="external-validation",
        source_owner="TON Docs contributors",
        published_at=at,
        effective_from=at,
        observed_at=at,
        source_timezone="UTC",
        status=item["status"],
        authority_level="official",
        official_status="verified_official",
        verification_method=(
            "Pinned official repository; evaluation-only snapshot availability, "
            "official publication/effectivity UNKNOWN"
        ),
        metadata_provenance={
            "source_type": "system-derived",
            "authority_level": "source-provided",
            "official_status": "source-provided",
            "published_at": "system-derived",
            "validity": "system-derived",
        },
    )


def prepare(output: Path) -> None:
    from community_intelligence.application.data_foundation import DataFoundationService
    from community_intelligence.application.knowledge import ChunkConfig, KnowledgeService

    lock = json.loads((output / "corpus.lock.json").read_text())
    destination = output / "prepared"
    if destination.exists():
        raise SystemExit("Refusing to overwrite frozen preparation")
    destination.mkdir()
    foundation = DataFoundationService(
        database_path=destination / "preview.sqlite3", artifact_root=destination / "artifacts"
    )
    service = KnowledgeService(
        database=foundation.database,
        artifact_root=destination / "knowledge",
        chunk_config=ChunkConfig(180, 30),
    )
    all_chunks = {}
    for item in lock["spec"]["sources"]:
        source = source_input(item, lock, output)
        chunks = service._chunk(
            service._extract_content(source), source.source_type, source.language
        )
        all_chunks[item["key"]] = chunks
        print(
            item["key"],
            len(chunks),
            "chunks",
            sum(c["token_count"] for c in chunks),
            "whitespace tokens",
        )
    save(destination / "chunks.json", all_chunks)
    save(
        destination / "baseline.lock.json",
        {
            "prepared_at": datetime.now(UTC).isoformat(),
            "corpus_lock_sha256": sha((output / "corpus.lock.json").read_bytes()),
            "product_hashes": baseline_hashes(),
            "config": {
                "strategy": "structure-v1",
                "max_tokens": 180,
                "overlap_tokens": 30,
                "neighbors": 1,
                "max_context_chars": 4000,
                "top_k": 5,
                "candidate_limit_per_method": 20,
                "rrf_k": 60,
            },
        },
    )


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def save(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def acquire(spec_path: Path, output: Path) -> None:
    spec_bytes = spec_path.read_bytes()
    spec = json.loads(spec_bytes)
    if output.exists():
        raise SystemExit("Refusing to overwrite an acquired corpus")
    output.mkdir(parents=True)
    repo = spec["repository_url"].removeprefix("https://github.com/")
    commit = spec["commit_sha"]
    assert len(commit) == 40 and all(c in "0123456789abcdef" for c in commit)
    records = []
    for relative in ["README.md", "LICENSE-docs", "LICENSE-code"] + [
        s["path"] for s in spec["sources"]
    ]:
        assert not Path(relative).is_absolute() and ".." not in Path(relative).parts
        url = f"https://raw.githubusercontent.com/{repo}/{commit}/{relative}"
        with urlopen(
            Request(url, headers={"User-Agent": "Community-Intelligence-Local-Validation"}),
            timeout=60,
        ) as response:
            raw = response.read()
        destination = output / "raw" / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(raw)
        records.append({"path": relative, "sha256": sha(raw), "bytes": len(raw), "url": url})
        print(relative, len(raw), flush=True)
    save(
        output / "corpus.lock.json",
        {
            "spec": spec,
            "spec_sha256": sha(spec_bytes),
            "retrieved_at": datetime.now(UTC).isoformat(),
            "license": {
                "documentation": "CC-BY-SA-4.0",
                "code_snippets": "MIT",
                "attribution": (
                    "TON Docs contributors; preserve original author notices and license files"
                ),
            },
            "files": records,
        },
    )
    print("Corpus sealed:", sha((output / "corpus.lock.json").read_bytes()))


def run(
    output: Path, queries_path: Path, model: Path, run_name: str, *, quality_fix: bool = False
) -> None:
    import numpy as np
    from sqlalchemy import select, text

    from community_intelligence.application.data_foundation import DataFoundationService
    from community_intelligence.application.knowledge import ChunkConfig, KnowledgeService, _terms
    from community_intelligence.infrastructure.database import knowledge_embeddings
    from community_intelligence.semantic import (
        MODEL_ID,
        MODEL_REVISION,
        SentenceTransformerProvider,
    )

    # Observers capture the actual calls; no rewritten queries or alternative retrieval path.
    class EmbeddingObserver:
        def __init__(self):
            self.provider = SentenceTransformerProvider(model)

        def embed(self, texts):
            result = self.provider.embed(texts)
            self.last = result
            return result

    class RetrievalObserver(KnowledgeService):
        def _lexical(self, terms, limit, workspace_id=None):
            self.lexical = (
                super()._lexical(terms, limit, workspace_id)
                if workspace_id
                else super()._lexical(terms, limit)
            )
            return self.lexical

        def _semantic(self, query, workspace_id, limit):
            self.semantic = super()._semantic(query, workspace_id, limit)
            return self.semantic

    baseline = json.loads((output / "prepared/baseline.lock.json").read_text())
    if quality_fix:
        from community_intelligence.application.knowledge_answer import JsonAnswerProvider

        assert JsonAnswerProvider.configured() is not None, (
            "Real answer provider must be explicitly configured"
        )
        baseline = {
            **baseline,
            "prepared_at": datetime.now(UTC).isoformat(),
            "product_hashes": baseline_hashes(),
            "quality_fix": True,
            "runner_sha256": sha(Path(__file__).read_bytes()),
        }
    assert baseline_hashes() == baseline["product_hashes"], "Product changed after baseline freeze"
    lock = json.loads((output / "corpus.lock.json").read_text())
    questions = json.loads(queries_path.read_bytes())
    assert questions["corpus_lock_sha256"] == sha((output / "corpus.lock.json").read_bytes())
    assert len({q["id"] for q in questions["queries"]}) == len(questions["queries"])
    prepared = json.loads((output / "prepared/chunks.json").read_text())
    for q in questions["queries"]:
        for ref in q["gold"] + q.get("required_context", []) + q.get("related", []):
            key, ordinal = ref.split(":")
            assert prepared[key][int(ordinal)]["ordinal"] == int(ordinal)
    destination = output / run_name
    if destination.exists():
        raise SystemExit("Refusing to overwrite experiment")
    destination.mkdir()
    save(destination / "queries.lock.json", questions)
    receipt = {
        "started_at": datetime.now(UTC).isoformat(),
        "query_sha256": sha(queries_path.read_bytes()),
        "corpus_lock_sha256": questions["corpus_lock_sha256"],
        "baseline": baseline,
        "embedding_model": MODEL_ID,
        "embedding_revision": MODEL_REVISION,
        "run_name": run_name,
    }
    save(destination / "receipt.json", receipt)
    now = datetime.fromisoformat(lock["retrieved_at"]) + timedelta(seconds=1)
    foundation = DataFoundationService(
        database_path=destination / "eval.sqlite3",
        artifact_root=destination / "runs",
        clock=lambda: now,
    )
    workspace = foundation.create_workspace("External Knowledge Validation")["workspace_id"]
    embedder = EmbeddingObserver()
    service = RetrievalObserver(
        database=foundation.database,
        artifact_root=destination / "knowledge",
        clock=lambda: now,
        embedder=embedder,
        chunk_config=ChunkConfig(180, 30),
    )
    chunks, revisions = {}, {}
    for item in lock["spec"]["sources"]:
        source = service.add_source(workspace, source_input(item, lock, output))
        record = service.get_source(source["source_id"])
        revision = service.get_revision(record["revisions"][0]["revision_id"])
        revisions[revision["revision_id"]] = revision
        for c, preview in zip(revision["chunks"], prepared[item["key"]], strict=True):
            assert c["text"] == preview["text"] and c["section"] == preview["section"]
            chunks[c["chunk_id"]] = {
                **c,
                "ref": item["key"] + ":" + str(c["ordinal"]),
                "path": item["path"],
            }
        print("Indexed", item["key"], len(revision["chunks"]), flush=True)
    save(destination / "chunks.json", chunks)
    with service.database.engine.connect() as con:
        vectors = {
            r.content_hash: np.asarray(json.loads(r.vector_json))
            for r in con.execute(select(knowledge_embeddings))
        }
    rows = []
    for q in questions["queries"]:
        when = (
            datetime.fromisoformat(q["as_of_time"].replace("Z", "+00:00"))
            if q.get("as_of_time")
            else now
        )
        if quality_fix:
            service.answerer.last_receipt = {}
        result = service.query(
            workspace,
            q["query"],
            as_of_time=when,
            top_k=5,
            neighbor_count=1,
            max_context_chars=4000,
        )
        fused = service._rrf(service.lexical, list(service.semantic))
        ranked = sorted(fused, key=lambda cid: -fused[cid])
        semantic_vector = np.asarray(embedder.last[0], dtype=float)
        semantic_all = {
            cid: float(
                vectors[
                    sha(
                        (
                            "title-heading-body-v1\n"
                            + service._retrieval_text(
                                c, service.get_source(c["source_id"])["title"]
                            )
                            if quality_fix
                            else c["text"]
                        ).encode()
                    )
                ]
                @ semantic_vector
            )
            for cid, c in chunks.items()
        }
        semantic_rank = {
            cid: r
            for r, cid in enumerate(sorted(semantic_all, key=lambda c: (-semantic_all[c], c)), 1)
        }
        expression = " OR ".join('"' + t.replace('"', "") + '"' for t in _terms(q["query"]))
        with service.database.engine.connect() as con:
            lexical_all = (
                dict(
                    con.execute(
                        text(
                            "SELECT chunk_id, bm25(knowledge_chunks_fts) "
                            "FROM knowledge_chunks_fts WHERE knowledge_chunks_fts MATCH :query "
                            "ORDER BY bm25(knowledge_chunks_fts)"
                        ),
                        {"query": expression},
                    ).all()
                )
                if expression
                else {}
            )
        lexical_rank = {cid: r for r, cid in enumerate(lexical_all, 1)}

        def diagnostic(
            cid,
            lexical_all=lexical_all,
            lexical_rank=lexical_rank,
            semantic_all=semantic_all,
            semantic_rank=semantic_rank,
            fused=fused,
            ranked=ranked,
        ):
            c = chunks[cid]
            return {
                "ref": c["ref"],
                "section": c["section"],
                "path": c["path"],
                "chunk_id": cid,
                "revision_id": c["revision_id"],
                "text_sha256": sha(c["text"].encode()),
                "bm25": lexical_all.get(cid),
                "lexical_rank": lexical_rank.get(cid),
                "semantic_similarity": semantic_all[cid],
                "semantic_rank": semantic_rank[cid],
                "semantic_in_top20": cid in service.semantic,
                "rrf_score": fused.get(cid),
                "rrf_rank": ranked.index(cid) + 1 if cid in ranked else None,
            }

        top = [diagnostic(c["chunk_id"]) for c in result["citations"]]
        raw_top = [diagnostic(cid) for cid in ranked[:5]]
        context_ids = {c["chunk_id"] for hit in result["citations"] for c in hit["context"]}
        expanded = [chunks[cid]["ref"] for cid in context_ids]
        valid = []
        for c in result["citations"]:
            stored = chunks[c["chunk_id"]]
            valid.append(
                stored["text"] == c["text"]
                and stored["revision_id"] == c["revision_id"]
                and stored["source_id"] == c["source_id"]
                and stored["section"] == c["section"]
                and lock["spec"]["commit_sha"] in c["canonical_url"]
                and all(
                    chunks[n["chunk_id"]]["text"].startswith(n["text"])
                    and chunks[n["chunk_id"]]["revision_id"] == c["revision_id"]
                    for n in c["context"]
                )
            )
        row = {
            "question": q,
            "result": result,
            "actual_top_k": top,
            "prepolicy_rrf_top5": raw_top,
            "expected_diagnostics": [
                diagnostic(cid)
                for cid, c in chunks.items()
                if c["ref"] in q["gold"] + q.get("related", [])
            ],
            "candidate_pool": [diagnostic(cid) for cid in ranked],
            "metrics": retrieval_metrics(q["gold"], [c["ref"] for c in top]),
            "prepolicy_metrics": retrieval_metrics(q["gold"], [c["ref"] for c in raw_top]),
            "expanded_gold_recall": len(set(q["gold"]) & set(expanded)) / len(q["gold"])
            if q["gold"]
            else None,
            "required_context_complete": set(q.get("required_context", [])) <= set(expanded)
            if q.get("required_context")
            else None,
            "citation_valid": valid,
            "status_correct": q["expected_status"] == result["answer_status"],
            **({"answer_provider": service.answerer.last_receipt.copy()} if quality_fix else {}),
        }
        rows.append(row)
        save(destination / "cases" / (q["id"] + ".json"), row)
        print(q["id"], result["answer_status"], [c["ref"] for c in top], flush=True)
    receipt["completed_at"] = datetime.now(UTC).isoformat()
    receipt["product_unchanged"] = baseline_hashes() == baseline["product_hashes"]
    assert receipt["product_unchanged"]
    save(destination / "receipt.json", receipt)
    save(destination / "results.json", rows)


def summarize(output: Path, review: Path, run_name: str) -> None:
    rows = json.loads((output / run_name / "results.json").read_text())
    judgments = json.loads((review / "adjudication.json").read_text())
    assert set(judgments["cases"]) == {r["question"]["id"] for r in rows}
    receipt = json.loads((output / run_name / "receipt.json").read_text())
    assert receipt["query_sha256"] == sha((review / "queries.json").read_bytes())
    assert baseline_hashes() == receipt["baseline"]["product_hashes"]
    positives = [r for r in rows if r["question"]["gold"]]

    def average(subset, key="metrics"):
        return {
            m: sum(r[key][m] for r in subset) / len(subset)
            for m in ("recall_at_5", "mrr_at_5", "ndcg_at_5", "hit_at_5")
        }

    def complete(r):
        return judgments["cases"][r["question"]["id"]]["grade"] == "complete"

    metrics = {
        "N": len(rows),
        "answerable_N": len(positives),
        "retrieval": average(positives),
        "prepolicy_rrf": average(positives, "prepolicy_metrics"),
    }
    metrics["language_distribution"] = dict(Counter(r["question"]["language"] for r in rows))
    metrics["type_distribution"] = dict(Counter(r["question"]["type"] for r in rows))
    metrics["by_language"] = {
        lang: {"N": len(s), **average(s), "complete_answer_count": sum(map(complete, s))}
        for lang in ("en", "zh", "es")
        if (s := [r for r in positives if r["question"]["language"] == lang])
    }
    metrics["cross_language"] = average([r for r in positives if r["question"]["language"] != "en"])
    metrics["citation_validity"] = {
        "valid": sum(sum(r["citation_valid"]) for r in rows),
        "N": sum(len(r["citation_valid"]) for r in rows),
    }
    metrics["grounded_answer_accuracy"] = {
        "correct": sum(map(complete, positives)),
        "N": len(positives),
    }
    metrics["answer_grades_answerable"] = dict(
        Counter(judgments["cases"][r["question"]["id"]]["grade"] for r in positives)
    )
    metrics["grounded_status_accuracy_only"] = {
        "correct": sum(r["status_correct"] for r in positives),
        "N": len(positives),
    }
    for kind in ("no_answer", "insufficient"):
        subset = [r for r in rows if r["question"]["type"] == kind]
        metrics[kind + "_status_accuracy"] = {
            "correct": sum(r["status_correct"] for r in subset),
            "N": len(subset),
        }
    negatives = [r for r in rows if r["question"]["type"] in {"insufficient", "no_answer"}]
    metrics["safe_abstention"] = {
        "correct": sum(r["result"]["answer_status"] != "grounded" for r in negatives),
        "N": len(negatives),
    }
    grounded = [r for r in rows if r["result"]["answer_status"] == "grounded"]
    metrics["grounded_output_complete_precision"] = {
        "correct": sum(map(complete, grounded)),
        "N": len(grounded),
    }
    context = [r for r in positives if r["question"].get("required_context")]
    metrics["multi_unit_context"] = {
        "N": len(context),
        "all_required_chunks_available": sum(r["required_context_complete"] for r in context),
        "complete_answers": sum(map(complete, context)),
    }
    metrics["primary_outcomes"] = dict(Counter(j["primary"] for j in judgments["cases"].values()))
    metrics["historical_truth_accuracy"] = {
        "value": None,
        "reason": (
            "No defensible offset-aware publication/effectivity history; "
            "T32 is a separate future-availability diagnostic."
        ),
    }
    safe_rows = []
    book = [
        "# TON Docs External Validation — casebook",
        "",
        "34 个原始问题全部保留；未经优化的 baseline-run-1。"
        "Complete 是严格完整答案；partial 不等于全部错误。"
        "AI 人工式审读，尚未经 Product Owner 独立标注。",
        "",
        "`source-key:ordinal` 对应固定 commit 的 source / section / chunk。"
        "下表 bm25 越小越好（SQLite 负值）；semantic 为余弦相似度，"
        "RRF rank 是后处理之前排名；空值表示未匹配或未进入 20+20 候选池，"
        "不是 0 分。完整 UUID/hash 位于 results.json。",
        "",
    ]
    for r in rows:
        q = r["question"]
        j = judgments["cases"][q["id"]]
        safe_rows.append(
            {
                "question": q,
                "judgment": j,
                "returned_status": r["result"]["answer_status"],
                "actual_top_k": r["actual_top_k"],
                "expected_diagnostics": r["expected_diagnostics"],
                "prepolicy_rrf_top5": r["prepolicy_rrf_top5"],
                "metrics": r["metrics"],
                "required_context_complete": r["required_context_complete"],
                "citation_valid": r["citation_valid"],
            }
        )
        book += [
            "## " + q["id"] + " — " + j["primary"],
            "",
            q["query"],
            "",
            "Expected: `"
            + q["expected_status"]
            + "`; returned: `"
            + r["result"]["answer_status"]
            + "`; answer: **"
            + j["grade"]
            + "**.",
            "",
            "验收事实：" + q["rubric"],
            "",
            "判定：" + j["reason"],
            "",
            "分类：" + ", ".join(j["tags"] or ["success"]),
            "",
        ]
        if q.get("as_of_time"):
            book += ["as_of_time: `" + q["as_of_time"] + "`", ""]
        for label, diagnostics in [
            ("Expected source / section（无答案题为 related-only）", r["expected_diagnostics"]),
            ("Actual Top-K（后处理后）", r["actual_top_k"]),
        ]:
            book += [
                "### " + label,
                "",
                "| Rank | Chunk / section | BM25 | Lexical rank "
                "| Semantic | Semantic rank | RRF score / rank |",
                "|---:|---|---:|---:|---:|---:|---|",
            ]
            for rank, d in enumerate(diagnostics, 1):

                def score(n):
                    return "—" if n is None else f"{n:.6f}"

                section = (d["section"] or "(no section)").replace("|", "/").replace("\n", " ")
                book.append(
                    f"| {rank} | {d['ref']} / {section} | {score(d['bm25'])} "
                    f"| {d['lexical_rank'] or '—'} | {d['semantic_similarity']:.6f} "
                    f"| {d['semantic_rank']} | {score(d['rrf_score'])} "
                    f"/ {d['rrf_rank'] or '—'} |"
                )
            if not diagnostics:
                book += ["| — | 无可证明答案的 chunk | — | — | — | — | — |"]
            book += [""]
        book += ["原始 RRF Top-5: " + ", ".join(d["ref"] for d in r["prepolicy_rrf_top5"]), ""]
    lock = json.loads((output / "corpus.lock.json").read_text())
    safe = {
        "dataset_version": lock["spec"]["dataset_version"],
        "repository": lock["spec"]["repository_url"],
        "commit_sha": lock["spec"]["commit_sha"],
        "retrieved_at": lock["retrieved_at"],
        "license": lock["license"],
        "receipt": receipt,
        "metrics": metrics,
        "adjudication_method": judgments["method"],
        "cases": safe_rows,
    }
    save(review / "results.json", safe)
    (review / "CASEBOOK.md").write_text("\n".join(book), encoding="utf-8")
    print(json.dumps(metrics, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("spec", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--prepare", action="store_true")
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--quality-fix", action="store_true")
    parser.add_argument("--summarize", action="store_true")
    parser.add_argument("--queries", type=Path)
    parser.add_argument("--run-name", default="baseline-run-1")
    parser.add_argument(
        "--model",
        type=Path,
        default=ROOT / "data/generated/models/paraphrase-multilingual-MiniLM-L12-v2-e8f8c211",
    )
    args = parser.parse_args()
    assert retrieval_metrics(["a", "b"], ["x", "a", "b"])["mrr_at_5"] == 0.5
    assert retrieval_metrics(["a", "b"], ["a", "b"])["ndcg_at_5"] == 1
    if args.summarize:
        summarize(args.output, args.spec.parent, args.run_name)
    elif args.run:
        run(args.output, args.queries, args.model, args.run_name, quality_fix=args.quality_fix)
    elif args.prepare:
        prepare(args.output)
    else:
        acquire(args.spec, args.output)
