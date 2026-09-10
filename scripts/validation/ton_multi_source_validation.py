"""Prepare and run the locked TON multi-source M2 validation corpus."""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import time
from datetime import UTC, datetime
from pathlib import Path
from urllib.request import Request, urlopen

from community_intelligence.application.data_foundation import DataFoundationService
from community_intelligence.application.knowledge import ChunkConfig, KnowledgeService, SourceInput
from community_intelligence.application.knowledge_answer import JsonAnswerProvider
from community_intelligence.semantic import SentenceTransformerProvider


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def save(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def fetch(url: str) -> bytes:
    request = Request(url, headers={"User-Agent": "community-intelligence-validation/1"})
    with urlopen(request, timeout=30) as response:
        return response.read(2_000_001)


def telegram_text(raw: bytes) -> tuple[str, str]:
    page = raw.decode()
    body = re.search(
        r'<div class="tgme_widget_message_text[^\"]*"[^>]*>(.*?)</div>', page, re.S
    )
    timestamp = re.search(r'<time datetime="([^"]+)"', page)
    if body is None or timestamp is None:
        raise ValueError("Telegram source did not expose text and a precise timestamp")
    value = re.sub(r"<br\s*/?>", "\n", body.group(1), flags=re.I)
    value = html.unescape(re.sub(r"<[^>]+>", "", value))
    text = "\n".join(line.strip() for line in value.splitlines() if line.strip())
    return text, timestamp.group(1)


def source_content(item: dict, raw: bytes) -> tuple[str, dict]:
    if item["fetch_kind"] == "text":
        return raw.decode(), {}
    if item["fetch_kind"] == "github_release":
        release = json.loads(raw)
        if release["published_at"] != item["published_at"]:
            raise ValueError(f"release timestamp drift: {item['key']}")
        return f"# {release['name']}\n\n{release['body']}", {
            "tag_name": release["tag_name"],
            "target_commitish": release["target_commitish"],
        }
    text, timestamp = telegram_text(raw)
    expected_timestamp = item.get("published_at") or item.get("observed_at")
    if dt(timestamp) != dt(expected_timestamp):
        raise ValueError(f"Telegram timestamp drift: {item['key']}")
    return text, {"observed_post_timestamp": timestamp}


def prepare(corpus_path: Path, output: Path) -> None:
    corpus_bytes = corpus_path.read_bytes()
    corpus = json.loads(corpus_bytes)
    records = []
    for item in corpus["sources"]:
        raw = fetch(item["fetch_url"])
        if len(raw) > 2_000_000:
            raise ValueError("validation source exceeds 2 MB bound")
        content, extra = source_content(item, raw)
        raw_path = output / "raw" / f"{item['key']}.raw"
        content_path = output / "content" / f"{item['key']}.txt"
        raw_path.parent.mkdir(parents=True, exist_ok=True)
        content_path.parent.mkdir(parents=True, exist_ok=True)
        raw_path.write_bytes(raw)
        content_path.write_text(content)
        records.append(
            {
                "key": item["key"],
                "raw_sha256": sha(raw),
                "content_sha256": sha(content.encode()),
                "bytes": len(content.encode()),
                **extra,
            }
        )
    save(
        output / "corpus.lock.json",
        {
            "corpus_sha256": sha(corpus_bytes),
            "retrieved_at": datetime.now(UTC).isoformat(),
            "dataset_version": corpus["dataset_version"],
            "sources": records,
        },
    )


def dt(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value.replace("Z", "+00:00")) if value else None


def run(corpus_path: Path, queries_path: Path, output: Path, model_dir: Path) -> None:
    corpus_bytes = corpus_path.read_bytes()
    corpus = json.loads(corpus_bytes)
    queries_bytes = queries_path.read_bytes()
    queries = json.loads(queries_bytes)
    lock = json.loads((output / "corpus.lock.json").read_text())
    if lock["corpus_sha256"] != sha(corpus_bytes):
        raise ValueError("prepared corpus does not match the locked manifest")
    if queries["corpus_sha256"] != sha(corpus_bytes):
        raise ValueError("queries were not frozen against this corpus")
    if (output / "results.json").exists():
        raise ValueError("refusing to overwrite a completed validation")
    answerer = JsonAnswerProvider.configured()
    if answerer is None:
        raise ValueError("explicit answer provider configuration is required")
    now = datetime(2026, 9, 10, 9, 0, tzinfo=UTC)
    foundation = DataFoundationService(
        database_path=output / "evaluation.sqlite3",
        artifact_root=output / "runs",
        clock=lambda: now,
    )
    workspace = foundation.create_workspace("TON Multi-source External Validation")["workspace_id"]
    service = KnowledgeService(
        database=foundation.database,
        artifact_root=output / "knowledge",
        clock=lambda: now,
        embedder=SentenceTransformerProvider(model_dir),
        answerer=answerer,
        chunk_config=ChunkConfig(180, 30),
    )
    source_ids: dict[str, str] = {}
    source_meta = {}
    for item in corpus["sources"]:
        content = (output / "content" / f"{item['key']}.txt").read_text()
        supersedes = source_ids.get(item.get("supersedes_source_key", ""))
        record = service.add_source(
            workspace,
            SourceInput(
                title=item["title"],
                source_type=item["source_type"],
                source_channel=item["source_channel"],
                content=content,
                canonical_url=item["canonical_url"],
                platform=item.get("platform"),
                platform_content_id=item.get("platform_content_id"),
                author="TON official source",
                source_owner="TON official source",
                language="en",
                authority_level="official",
                official_status="verified_official",
                verification_method="human-confirmed source identity",
                published_at=dt(item.get("published_at")),
                updated_at=dt(item.get("updated_at")),
                effective_from=dt(item["effective_from"]),
                effective_until=dt(item.get("effective_until")),
                observed_at=dt(item.get("observed_at") or lock["retrieved_at"]),
                superseded_at=dt(item.get("superseded_at")),
                status=item["status"],
                supersedes_source_id=supersedes,
                source_timezone="UTC",
                metadata_provenance={
                    "source_type": "human-confirmed",
                    "authority_level": "human-confirmed",
                    "official_status": "human-confirmed",
                    "published_at": (
                        "source-provided" if item.get("published_at") else "human-confirmed"
                    ),
                    "validity": "human-confirmed",
                },
            ),
        )
        source_ids[item["key"]] = record["source_id"]
        source_meta[item["key"]] = {
            "source_id": record["source_id"],
            "revision_id": record["revision_id"],
            "chunk_count": len(record["chunks"]),
        }
    id_to_key = {value: key for key, value in source_ids.items()}
    rows = []
    for question in queries["queries"]:
        started = time.perf_counter()
        result = service.query(
            workspace,
            question["query"],
            as_of_time=dt(question.get("as_of_time")),
            top_k=5,
            neighbor_count=1,
        )
        selected = list(dict.fromkeys(id_to_key[c["source_id"]] for c in result["citations"]))
        chunk_sources = {
            context["chunk_id"]: id_to_key[citation["source_id"]]
            for citation in result["citations"]
            for context in citation["context"]
        }
        used = list(
            dict.fromkeys(
                chunk_sources[evidence["chunk_id"]]
                for claim in result["claims"]
                for evidence in claim["evidence"]
                if evidence["chunk_id"] in chunk_sources
            )
        )
        required = set(question.get("required_sources", []))
        forbidden = set(question.get("forbidden_sources", []))
        status_ok = result["answer_status"] == question["expected_status"]
        evaluated_sources = used or selected
        sources_ok = required <= set(evaluated_sources) and not (
            forbidden & set(evaluated_sources)
        )
        rows.append(
            {
                "id": question["id"],
                "dimension": question["dimension"],
                "query": question["query"],
                "as_of_time": question.get("as_of_time"),
                "expected_status": question["expected_status"],
                "actual_status": result["answer_status"],
                "selected_sources": selected,
                "evidence_sources": used,
                "status_ok": status_ok,
                "sources_ok": sources_ok,
                "pass": status_ok and sources_ok,
                "claims": result["claims"],
                "missing_facts": result["answerability"]["missing_facts"],
                "ranking": result["retrieval"]["ranking"],
                "reranker": result["retrieval"]["reranker"],
                "latency_ms": (time.perf_counter() - started) * 1000,
            }
        )
        print(question["id"], result["answer_status"], used, flush=True)
    save(output / "sources.json", source_meta)
    save(output / "queries.lock.json", queries)
    save(output / "results.json", rows)
    save(
        output / "summary.json",
        {
            "N": len(rows),
            "passed": sum(row["pass"] for row in rows),
            "status_accuracy": sum(row["status_ok"] for row in rows) / len(rows),
            "source_selection_accuracy": sum(row["sources_ok"] for row in rows) / len(rows),
            "by_dimension": {
                dimension: {
                    "N": len(items),
                    "passed": sum(row["pass"] for row in items),
                }
                for dimension in sorted({row["dimension"] for row in rows})
                if (items := [row for row in rows if row["dimension"] == dimension])
            },
            "query_sha256": sha(queries_bytes),
            "corpus_sha256": sha(corpus_bytes),
        },
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("prepare", "run"))
    parser.add_argument("--corpus", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--queries", type=Path)
    parser.add_argument("--model-dir", type=Path)
    args = parser.parse_args()
    if args.mode == "prepare":
        prepare(args.corpus.resolve(), args.output.resolve())
    elif args.queries is None or args.model_dir is None:
        parser.error("run requires --queries and --model-dir")
    else:
        run(
            args.corpus.resolve(),
            args.queries.resolve(),
            args.output.resolve(),
            args.model_dir.resolve(),
        )
