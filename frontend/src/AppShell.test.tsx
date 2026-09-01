import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"

import { AppShell } from "./AppShell"

const report = {
  schema_version: "1.0",
  data_status: "synthetic",
  dataset_id: "synthetic-test",
  generation_id: "generation-test",
  Overview: {
    message_count: 120,
    community_count: 4,
    language_counts: { en: 43, es: 30, zh: 25, ar: 22 },
    role_counts: { moderator: 67, user: 53 },
    campaign_count: 3,
    claim_count: 7,
    source: { format: "synthetic_generator_v1", limitations: [] },
  },
  capabilities: {
    community_analysis: { status: "available" },
    campaign_intelligence: { status: "available" },
    outcome_validation: { status: "available" },
    llm_behavior_interpretation: { status: "not_implemented" },
  },
  limitations: {
    association_not_causation: "Descriptive association, not causation.",
    human_review: "All candidate judgments remain pending review.",
  },
  analysis_methods: { campaign: "curated_alias_baseline" },
  Activation: [
    {
      community_id: "community_a",
      campaign_id: "campaign_launch",
      meaningful_interaction_ratio: 0.72,
      peer_support_ratio: 0.25,
      response_latency_seconds: 3600,
      user_to_user_interaction_ratio: 0.18,
      evidence_ids: ["evidence_001"],
      metadata: {},
    },
  ],
  Hygiene: [
    {
      community_id: "community_a",
      campaign_id: "campaign_launch",
      duplicate_ratio: 0.12,
      filler_ratio: 0.08,
      repetitive_content_ratio: 0.1,
      evidence_ids: ["evidence_001"],
      formula_metadata: {},
    },
  ],
  Campaign: {
    status: "available",
    method: "curated_alias_baseline",
    review_status: "pending",
    judgments: [
      {
        campaign_id: "campaign_launch",
        claim_id: "launch_date",
        community_id: "community_a",
        status: "covered",
        confidence: 1,
        confidence_semantics: "Deterministic evidence strength, not probability.",
        method: "curated_alias_baseline",
        review_status: "pending",
        evidence_ids: ["evidence_001"],
      },
    ],
    summaries: [],
  },
  Behavior: {
    selected_cluster_count: 1,
    selection_method: "silhouette",
    review_status: "pending",
    seed_labels: { negative_feedback: 9 },
    clusters: [
      {
        cluster_id: "cluster_01",
        message_count: 31,
        confidence: 0.62,
        method: "tfidf_kmeans",
        proposed_behavior_name: null,
        behavior_description: "Unsupervised cluster pending human naming.",
        top_terms: ["launch", "help", "date"],
        language_distribution: [["en", 21]],
        role_distribution: [["moderator", 27]],
        community_distribution: [["community_a", 31]],
        evidence_ids: ["evidence_001"],
        review_status: "pending",
      },
    ],
  },
  "Episodes/Response Patterns": [
    {
      episode_id: "episode:msg_001",
      community_id: "community_a",
      campaign_id: "campaign_launch",
      conversation_depth: 3,
      unique_participants: 3,
      question_count: 1,
      candidate_answered_question_count: 1,
      unanswered_question_count: 0,
      first_response_latency_seconds: 180,
      message_ids: ["msg_001", "msg_002"],
      evidence_ids: ["evidence_001"],
      review_status: "pending",
      interpretation_limit: "Descriptive reply-graph metrics; no causal claim.",
    },
  ],
  "Community Feedback": {
    review_status: "pending",
    seed_counts: {
      negative_feedback: {
        count: 9,
        evidence_available: true,
        evidence_ids: ["evidence_001"],
        method_status: "Implemented",
        observation_status: "Observed",
      },
    },
    capabilities: { stance: "Not implemented" },
    limitations: {},
  },
  "Metric Lab": {
    association_not_causation: "Association, not causation.",
    definitions: {
      campaign_discussion_share: {
        metric_name: "campaign_discussion_share",
        business_meaning: "Share of real-user messages discussing a campaign.",
        formula: "campaign-related / all real-user messages",
        numerator: "campaign-related real-user messages",
        denominator: "all real-user messages",
        unit_of_analysis: "community-campaign window",
        time_window: "explicit campaign window",
        required_fields: ["message_id", "campaign_id"],
        biases: ["Aliases may miss indirect references."],
        limitations: ["Volume does not establish persuasion."],
      },
    },
    observations: [
      {
        metric_name: "campaign_discussion_share",
        community_id: "community_a",
        campaign_id: "campaign_launch",
        value: 0.42,
        evidence_ids: ["evidence_001"],
      },
    ],
    validation: { status: "available", results: [] },
    outcome_validation: { status: "available" },
  },
}

const evidence = {
  evidence_id: "evidence_001",
  evidence_type: "source_message",
  message_id: "msg_001",
  claim_id: null,
  source_campaign_id: "campaign_launch",
  analysis_campaign_id: "campaign_launch",
  community_id: "community_a",
  source_text: "When is the launch date?",
  confidence: null,
  confidence_semantics: "Exact captured source message; not a probability.",
  method: "source_message",
  review_status: "pending",
}

function fakeClient() {
  return {
    runDemo: vi.fn().mockResolvedValue({
      analysis_id: "a".repeat(32),
      summary: {
        message_count: 120,
        community_count: 4,
        campaign_count: 3,
        evidence_count: 1,
        data_status: "synthetic",
        source_format: "synthetic_generator_v1",
      },
      report,
    }),
    importTelegram: vi.fn(),
    getEvidence: vi.fn().mockResolvedValue({ count: 1, items: [evidence] }),
  }
}

describe("AppShell", () => {
  it("explains the local product boundary before an analysis is loaded", () => {
    render(<AppShell client={fakeClient()} />)

    expect(
      screen.getByRole("heading", { name: /understand how communities respond/i }),
    ).toBeInTheDocument()
    expect(screen.getByText(/synthetic data until you import your own export/i)).toBeInTheDocument()
    expect(screen.getByRole("navigation", { name: "Primary" })).toBeInTheDocument()
  })

  it("loads one report into all seven user views", async () => {
    render(<AppShell client={fakeClient()} />)

    fireEvent.click(screen.getByRole("button", { name: /run synthetic demo/i }))
    expect(await screen.findByText("120 messages")).toBeInTheDocument()
    expect(screen.getByText("4 communities")).toBeInTheDocument()

    fireEvent.click(screen.getByRole("button", { name: "Campaigns" }))
    expect(screen.getByText("launch_date")).toBeInTheDocument()
    expect(screen.getByText("covered")).toBeInTheDocument()

    fireEvent.click(screen.getByRole("button", { name: "Communities" }))
    expect(screen.getByText("community_a")).toBeInTheDocument()
    expect(screen.getByText("72%")).toBeInTheDocument()

    fireEvent.click(screen.getByRole("button", { name: "Behaviors" }))
    expect(screen.getByText("cluster_01")).toBeInTheDocument()

    fireEvent.click(screen.getByRole("button", { name: "Response Patterns" }))
    expect(screen.getByText("episode:msg_001")).toBeInTheDocument()

    fireEvent.click(screen.getByRole("button", { name: "Metric Lab" }))
    expect(screen.getAllByText("campaign_discussion_share").length).toBeGreaterThan(0)

    fireEvent.click(screen.getByRole("button", { name: "Evidence" }))
    expect(screen.getByText("evidence_001")).toBeInTheDocument()
  })

  it("opens source-linked evidence without losing the current view", async () => {
    render(<AppShell client={fakeClient()} />)
    fireEvent.click(screen.getByRole("button", { name: /run synthetic demo/i }))
    await screen.findByText("120 messages")
    fireEvent.click(screen.getByRole("button", { name: "Campaigns" }))
    fireEvent.click(screen.getByRole("button", { name: /open evidence_001/i }))

    expect(await screen.findByRole("dialog", { name: /evidence detail/i })).toBeInTheDocument()
    expect(screen.getByText("When is the launch date?")).toBeInTheDocument()
    expect(screen.getByText(/not a probability/i)).toBeInTheDocument()
    fireEvent.click(screen.getByRole("button", { name: "Close evidence" }))
    await waitFor(() =>
      expect(screen.queryByRole("dialog", { name: /evidence detail/i })).not.toBeInTheDocument(),
    )
    expect(screen.getByRole("heading", { name: "Campaigns" })).toBeInTheDocument()
  })
})
