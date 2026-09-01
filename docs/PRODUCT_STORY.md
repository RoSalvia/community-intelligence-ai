# Product Story

Community Intelligence AI began with a practical operating problem: how do you understand what is happening across more than ten multilingual Telegram communities without reading every message?

## From activity counts to the wrong incentives

The first management signal was message count. It was easy to collect and compare, but once volume became a target it could be optimized directly. Short replies, repeated phrases, filler, and artificial bursts all increased activity while saying little about whether users understood a campaign, received useful answers, or began meaningful discussions.

That experience made the first product boundary clear:

```text
Message count ≠ community quality
```

Message volume is still useful as analysis scope. It is not a quality score and should not become an automatic judgment about a moderator or community.

## Why keyword hit rate was not enough

A later workflow used keyword hit rate to check whether campaign terms appeared in local communities. This was closer to the real business question, but it broke down across languages. A correct translation may use none of the source words, while a message containing every keyword can still state the wrong amount, eligibility rule, or deadline.

Keyword presence also stops at publication. It does not show whether users asked questions, whether anyone answered, whether discussion spread to other members, or whether confusion remained unresolved.

The problem therefore changed from “did the moderator post enough?” to “what happened in the community, and what evidence supports that interpretation?”

## The Community Intelligence framing

The project now treats unstructured conversation as evidence for several connected questions: which behaviors appear, how communities respond, where activity looks artificial, whether users interact with one another, which campaign claims are present when campaign data exists, and which candidate metrics are worth evaluating.

The intended method is deliberately split across three roles:

```text
AI discovers candidate behaviors, patterns, and metrics
→ statistical analysis tests candidate signals
→ people make the final operational or product decision
```

This avoids replacing a weak activity KPI with an unexplained AI score. Important outputs retain source messages, evidence identifiers, method labels, confidence semantics, limitations, and review status. Statistical association is never presented as causation, and moderator evaluation remains a downstream use case rather than the product center.

## What V0.1 proves—and what it does not

The public alpha is a local-first, synthetic-first product. It can generate a reproducible multilingual demo or import a bounded Telegram Desktop JSON export, run deterministic community analysis, and connect seven report views back to evidence. It includes hygiene, activation, response episodes, behavior clustering, deterministic campaign baselines, and candidate metric/statistical validation.

V0.1 does not claim general multilingual semantic judgment or LLM-generated behavior naming. Those capabilities remain explicitly `Not implemented`. Real-time Telegram ingestion, accounts, hosted multi-user operation, and automated HR decisions are also outside the release.

The value of the alpha is the complete, inspectable workflow: start with conversation, derive reviewable signals, expose their evidence and limitations, and test whether candidate metrics deserve further attention.
