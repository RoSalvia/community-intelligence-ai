#!/usr/bin/env python3
"""Validation-only parser/profile for the Sapienza XRP Telegram HTML archive."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter
from datetime import UTC, datetime
from html.parser import HTMLParser
from pathlib import Path
from zoneinfo import ZoneInfo

from community_intelligence.models import MessageRecord

COMMUNITY_ID = "community_validation_xrp_crowd_pump"
DEFAULT_PAGES = "1-5,40-44,80-84,116-120"
REPLY_ID = re.compile(r"#go_to_message(\d+)")
SPACE = re.compile(r"\s+")
WORD = re.compile(r"[\w']+", re.UNICODE)
SOURCE_HASH = re.compile(r"(?<![0-9a-f])[0-9a-f]{64}(?![0-9a-f])", re.IGNORECASE)
SOURCE_SENDER = re.compile(r"[0-9a-f]{64}\Z")

QUESTION = re.compile(
    r"\?|\b(how|what|when|where|why|who|can (i|we|you)|does anyone|help|which)\b",
    re.IGNORECASE,
)
SUPPORT = re.compile(
    r"\b(try|use|you can|buy on|available|works|worked|link|here|kraken|uphold|binance|"
    r"coinbase|wallet|exchange)\b",
    re.IGNORECASE,
)
PROJECT = re.compile(
    r"\b(xrp|ripple|sec|ledger|wallet|exchange|buy|hold|pump|price|february|feb|est)\b",
    re.IGNORECASE,
)
COMPLAINT = re.compile(
    r"\b(scam|fake|cannot|can't|cant|not working|doesn't work|problem|issue|lost|dump|"
    r"blocked|banned|admin|lock(ed)?)\b",
    re.IGNORECASE,
)
class TelegramHTMLParser(HTMLParser):
    """Read Telegram Desktop HTML without becoming a production importer."""

    def __init__(self, inherited_sender: str | None = None) -> None:
        super().__init__(convert_charrefs=True)
        self.records: list[dict[str, object]] = []
        self.last_sender = inherited_sender
        self.message: dict[str, object] | None = None
        self.depth = 0
        self.from_depth: int | None = None
        self.text_depth: int | None = None
        self.reply_depth: int | None = None
        self.message_nodes = 0
        self.textless = 0
        self.missing_sender = 0
        self.inherited_sender_count = 0
        self.reply_nodes = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        classes = set((values.get("class") or "").split())
        if tag == "div" and self.message is None and {"message", "default"} <= classes:
            source_id = (values.get("id") or "").removeprefix("message")
            self.message = {
                "source_id": source_id,
                "sender_parts": [],
                "text_parts": [],
                "timestamp_text": None,
                "reply_href": None,
                "joined": "joined" in classes,
            }
            self.depth = 1
            self.message_nodes += 1
            return
        if self.message is None:
            return
        if tag == "div":
            self.depth += 1
            if "from_name" in classes and not self.message["sender_parts"]:
                self.from_depth = self.depth
            elif "text" in classes:
                self.text_depth = self.depth
            elif "reply_to" in classes:
                self.reply_depth = self.depth
                self.reply_nodes += 1
            if {"date", "details"} <= classes:
                self.message["timestamp_text"] = values.get("title")
        elif tag == "a" and self.reply_depth is not None:
            self.message["reply_href"] = values.get("href")
        elif tag == "br" and self.text_depth is not None:
            self.message["text_parts"].append("\n")  # type: ignore[union-attr]

    def handle_endtag(self, tag: str) -> None:
        if self.message is None or tag != "div":
            return
        if self.from_depth == self.depth:
            self.from_depth = None
        if self.text_depth == self.depth:
            self.text_depth = None
        if self.reply_depth == self.depth:
            self.reply_depth = None
        self.depth -= 1
        if self.depth == 0:
            self._finish_message()

    def handle_data(self, data: str) -> None:
        if self.message is None:
            return
        if self.from_depth is not None:
            self.message["sender_parts"].append(data)  # type: ignore[union-attr]
        elif self.text_depth is not None:
            self.message["text_parts"].append(data)  # type: ignore[union-attr]

    def _finish_message(self) -> None:
        assert self.message is not None
        sender = SPACE.sub(" ", "".join(self.message["sender_parts"])).strip()
        if sender:
            self.last_sender = sender
        elif self.message["joined"] and self.last_sender:
            sender = self.last_sender
            self.inherited_sender_count += 1
        text = SPACE.sub(" ", "".join(self.message["text_parts"])).strip()
        if not text:
            self.textless += 1
        elif not sender:
            self.missing_sender += 1
        elif self.message["source_id"] and self.message["timestamp_text"]:
            reply_match = REPLY_ID.search(str(self.message["reply_href"] or ""))
            local_time = datetime.strptime(
                str(self.message["timestamp_text"]), "%d.%m.%Y %H:%M:%S"
            ).replace(tzinfo=ZoneInfo("Europe/Rome"))
            self.records.append(
                {
                    "source_id": str(self.message["source_id"]),
                    "source_sender": sender,
                    "timestamp": local_time.astimezone(UTC),
                    "text": text,
                    "source_reply_id": reply_match.group(1) if reply_match else None,
                    "cross_page_reply": bool(
                        self.message["reply_href"]
                        and str(self.message["reply_href"]).startswith("messages")
                    ),
                }
            )
        self.message = None
        self.from_depth = None
        self.text_depth = None
        self.reply_depth = None


def page_numbers(specification: str) -> list[int]:
    pages: set[int] = set()
    for part in specification.split(","):
        bounds = [int(value) for value in part.split("-", 1)]
        pages.update(range(bounds[0], bounds[-1] + 1))
    return sorted(pages)


def anonymize_sender(source_sender: str) -> str:
    digest = hashlib.sha256(f"xrp-validation-v1:{source_sender}".encode()).hexdigest()
    return f"usr_{digest}"


def parse_pages(
    input_dir: Path, pages: list[int]
) -> tuple[list[dict[str, object]], dict[str, int]]:
    records: list[dict[str, object]] = []
    counters: Counter[str] = Counter()
    last_page: int | None = None
    last_sender: str | None = None
    for page in pages:
        source = input_dir / f"messages{page}.html"
        if not source.is_file():
            raise FileNotFoundError(source)
        parser = TelegramHTMLParser(last_sender if last_page == page - 1 else None)
        parser.feed(source.read_text(encoding="utf-8"))
        records.extend(parser.records)
        counters.update(
            message_nodes=parser.message_nodes,
            textless=parser.textless,
            missing_sender=parser.missing_sender,
            inherited_sender=parser.inherited_sender_count,
            reply_nodes=parser.reply_nodes,
        )
        last_sender = parser.last_sender
        last_page = page
    return records, dict(counters)


def canonical_records(records: list[dict[str, object]]) -> list[MessageRecord]:
    selected_ids = {str(record["source_id"]) for record in records}
    if len(selected_ids) != len(records):
        raise ValueError("sample contains duplicate source message IDs")
    timestamps = {str(record["source_id"]): record["timestamp"] for record in records}
    canonical: list[MessageRecord] = []
    for record in records:
        source_id = str(record["source_id"])
        source_reply_id = record["source_reply_id"]
        source_sender = str(record["source_sender"])
        if SOURCE_SENDER.fullmatch(source_sender) is None:
            raise ValueError(f"message {source_id} has a non-anonymized source sender")
        reply_id = None
        if (
            source_reply_id in selected_ids
            and timestamps[str(source_reply_id)] <= record["timestamp"]
        ):
            reply_id = f"xrp_tg_{source_reply_id}"
        canonical.append(
            MessageRecord(
                message_id=f"xrp_tg_{source_id}",
                community_id=COMMUNITY_ID,
                language="und",
                user_id_hash=anonymize_sender(source_sender),
                user_role="user",
                timestamp=record["timestamp"],
                text=SOURCE_HASH.sub("[source-anonymized-id]", str(record["text"])),
                reply_to_message_id=reply_id,
                campaign_id=None,
            )
        )
    return canonical


def normalized_text(text: str) -> str:
    return SPACE.sub(" ", re.sub(r"[^\w\s]", " ", text.casefold())).strip()


def profile(
    source_records: list[dict[str, object]],
    canonical: list[MessageRecord],
    counters: dict[str, int],
    pages: list[int],
) -> dict[str, object]:
    users = Counter(message.user_id_hash for message in canonical)
    text_counts = Counter(normalized_text(message.text) for message in canonical)
    repeated = {text for text, count in text_counts.items() if text and count > 1}
    explicit_replies = sum(record["source_reply_id"] is not None for record in source_records)
    resolved_replies = sum(message.reply_to_message_id is not None for message in canonical)
    redactions = sum(
        len(SOURCE_HASH.findall(str(record["text"]))) for record in source_records
    )
    canonical_by_id = {message.message_id.removeprefix("xrp_tg_"): message for message in canonical}
    candidates: dict[str, list[str]] = {
        "question_help": [],
        "peer_support": [],
        "project_discussion": [],
        "complaint": [],
        "filler": [],
        "repetitive": [],
    }
    for source, message in zip(source_records, canonical, strict=True):
        text = message.text
        if QUESTION.search(text):
            candidates["question_help"].append(message.message_id)
        parent = canonical_by_id.get(str(source["source_reply_id"]))
        if parent and parent.user_id_hash != message.user_id_hash and SUPPORT.search(text):
            candidates["peer_support"].append(message.message_id)
        if PROJECT.search(text):
            candidates["project_discussion"].append(message.message_id)
        if COMPLAINT.search(text):
            candidates["complaint"].append(message.message_id)
        words = WORD.findall(text)
        if len(words) <= 3:
            candidates["filler"].append(message.message_id)
        if normalized_text(text) in repeated:
            candidates["repetitive"].append(message.message_id)
    message_count = len(canonical)
    candidate_counts = {name: len(message_ids) for name, message_ids in candidates.items()}
    return {
        "sample_pages": pages,
        "html_files": len(pages),
        "html_message_nodes": counters["message_nodes"],
        "parsed_text_messages": message_count,
        "textless_messages_skipped": counters["textless"],
        "missing_sender_skipped": counters["missing_sender"],
        "joined_messages_with_inherited_sender": counters["inherited_sender"],
        "canonical_validation_count": len(canonical),
        "unique_users": len(users),
        "start_utc": min(message.timestamp for message in canonical).isoformat(),
        "end_utc": max(message.timestamp for message in canonical).isoformat(),
        "explicit_reply_messages": explicit_replies,
        "explicit_reply_rate": explicit_replies / message_count,
        "reply_nodes_detected": counters["reply_nodes"],
        "reply_nodes_with_parsable_target": explicit_replies,
        "reply_target_parse_rate": explicit_replies / counters["reply_nodes"],
        "cross_page_reply_messages": sum(
            bool(record["cross_page_reply"]) for record in source_records
        ),
        "replies_resolved_within_sample": resolved_replies,
        "within_sample_reply_resolution_rate": (
            resolved_replies / explicit_replies if explicit_replies else None
        ),
        "top_sender_share": users.most_common(1)[0][1] / message_count,
        "top_10_sender_share": sum(count for _, count in users.most_common(10)) / message_count,
        "messages_in_repeated_text_groups": sum(
            count for text, count in text_counts.items() if text in repeated
        ),
        "repeated_text_message_rate": sum(
            count for text, count in text_counts.items() if text in repeated
        )
        / message_count,
        "source_identifier_text_redactions": redactions,
        "candidate_counts_not_ground_truth": candidate_counts,
        "candidate_rates_not_ground_truth": {
            name: count / message_count for name, count in candidate_counts.items()
        },
        "candidate_message_ids_not_ground_truth": candidates,
        "timestamp_assumption": "HTML local time interpreted as Europe/Rome, then converted to UTC",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-dir", type=Path, required=True)
    parser.add_argument("--pages", default=DEFAULT_PAGES)
    parser.add_argument("--summary-out", type=Path, required=True)
    parser.add_argument("--records-out", type=Path)
    args = parser.parse_args()

    pages = page_numbers(args.pages)
    source_records, counters = parse_pages(args.input_dir, pages)
    messages = canonical_records(source_records)
    summary = profile(source_records, messages, counters, pages)
    args.summary_out.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    if args.records_out:
        args.records_out.write_text(
            "".join(message.model_dump_json() + "\n" for message in messages),
            encoding="utf-8",
        )
    print(json.dumps({key: value for key, value in summary.items() if "ids" not in key}, indent=2))


if __name__ == "__main__":
    main()
