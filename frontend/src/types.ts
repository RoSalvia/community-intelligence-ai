export type Capability = {
  status: "available" | "not_available" | "not_implemented" | string
  reason?: string
}

export type EvidenceRecord = {
  evidence_id: string
  evidence_type: string
  message_id: string | null
  claim_id: string | null
  source_campaign_id: string | null
  analysis_campaign_id: string | null
  community_id: string | null
  source_text: string | null
  message_count?: number | null
  denominator_facts?: Record<string, number> | null
  translation?: string | null
  confidence: number | null
  confidence_semantics: string
  method: string
  review_status: string
}

export type ActivationObservation = {
  community_id: string
  campaign_id: string | null
  meaningful_interaction_ratio?: number | null
  peer_support_ratio?: number | null
  response_latency_seconds?: number | null
  user_to_user_interaction_ratio?: number | null
  evidence_ids: string[]
  metadata?: Record<string, unknown>
}

export type HygieneObservation = {
  community_id: string
  campaign_id: string | null
  duplicate_ratio?: number | null
  filler_ratio?: number | null
  repetitive_content_ratio?: number | null
  evidence_ids: string[]
  formula_metadata?: Record<string, unknown>
}

export type CampaignJudgment = {
  campaign_id: string
  claim_id: string
  community_id: string
  status: string
  confidence: number
  confidence_semantics: string
  method: string
  review_status: string
  evidence_ids: string[]
  notes?: string
}

export type BehaviorCluster = {
  cluster_id: string
  message_count: number
  confidence: number
  method: string
  proposed_behavior_name: string | null
  behavior_description: string
  top_terms: string[]
  language_distribution: [string, number][]
  role_distribution: [string, number][]
  community_distribution: [string, number][]
  evidence_ids: string[]
  review_status: string
}

export type Episode = {
  episode_id: string
  community_id: string
  campaign_id: string | null
  conversation_depth: number
  unique_participants: number
  question_count: number
  candidate_answered_question_count: number
  unanswered_question_count: number
  first_response_latency_seconds: number | null
  message_ids: string[]
  evidence_ids: string[]
  review_status: string
  interpretation_limit: string
}

export type MetricDefinition = {
  metric_name: string
  business_meaning: string
  formula: string
  numerator?: string
  denominator: string
  unit_of_analysis: string
  time_window: string
  required_fields: string[]
  biases: string[]
  limitations: string[]
  why_it_may_matter?: string
}

export type MetricObservation = {
  metric_name?: string
  metric_id?: string
  community_id?: string
  campaign_id?: string
  value?: number | null
  evidence_ids?: string[]
  [key: string]: unknown
}

export type CommunityReport = {
  schema_version: string
  data_status: string
  dataset_id: string
  generation_id: string
  Overview: {
    message_count: number
    community_count: number
    language_counts: Record<string, number>
    role_counts: Record<string, number>
    campaign_count: number
    claim_count: number
    source: { format: string; limitations: string[] }
  }
  capabilities: Record<string, Capability>
  limitations: Record<string, string>
  analysis_methods: Record<string, unknown>
  Activation: ActivationObservation[]
  Hygiene: HygieneObservation[]
  Campaign: {
    status: string
    method: string
    review_status: string
    judgments: CampaignJudgment[]
    summaries: Record<string, unknown>[]
  }
  Behavior: {
    selected_cluster_count: number
    selection_method: string
    review_status: string
    seed_labels: Record<string, number>
    clusters: BehaviorCluster[]
  }
  "Episodes/Response Patterns": Episode[]
  "Community Feedback": {
    review_status: string
    seed_counts: Record<
      string,
      {
        count: number
        evidence_available: boolean
        evidence_ids: string[]
        method_status: string
        observation_status: string
      }
    >
    capabilities: Record<string, string>
    limitations: Record<string, string>
  }
  "Metric Lab": {
    association_not_causation: string
    definitions: Record<string, MetricDefinition>
    observations: MetricObservation[]
    validation: Record<string, unknown>
    outcome_validation: Record<string, unknown>
  }
}

export type AnalysisSummary = {
  message_count: number
  community_count: number
  campaign_count: number
  evidence_count: number
  data_status: string
  source_format: string
}

export type AnalysisResponse = {
  analysis_id: string
  summary: AnalysisSummary
  report: CommunityReport
}

export type EvidenceResponse = {
  count: number
  items: EvidenceRecord[]
}

export type AppClient = {
  runDemo: () => Promise<AnalysisResponse>
  importTelegram: (file: File, language?: string) => Promise<AnalysisResponse>
  getEvidence: (analysisId: string) => Promise<EvidenceResponse>
}
