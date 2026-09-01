import {
  AlertTriangle,
  ArrowUpRight,
  BadgeCheck,
  BarChart3,
  CircleHelp,
  FileSearch,
  FlaskConical,
  Languages,
  MessageCircleReply,
  Network,
  ShieldCheck,
  UsersRound,
} from "lucide-react"
import { useMemo, useState } from "react"
import { Bar, BarChart, CartesianGrid, Tooltip, XAxis, YAxis } from "recharts"

import type {
  CommunityReport,
  EvidenceRecord,
  MetricDefinition,
} from "./types"

export type EvidenceOpener = (evidenceId: string) => void

function titleCase(value: string) {
  return value.replaceAll("_", " ").replace(/\b\w/g, (letter) => letter.toUpperCase())
}

function percent(value: number | null | undefined) {
  return value == null ? "Not available" : `${Math.round(value * 100)}%`
}

function duration(value: number | null | undefined) {
  if (value == null) return "Not available"
  if (value < 60) return `${Math.round(value)} sec`
  if (value < 3600) return `${Math.round(value / 60)} min`
  return `${(value / 3600).toFixed(1)} hr`
}

function average<T extends object>(items: T[], key: keyof T): number | null {
  const values: number[] = []
  for (const item of items) {
    const value = item[key]
    if (typeof value === "number" && Number.isFinite(value)) values.push(value)
  }
  return values.length ? values.reduce((sum, value) => sum + value, 0) / values.length : null
}

function PageHeading({ eyebrow, title, description }: { eyebrow: string; title: string; description: string }) {
  return (
    <header className="report-heading">
      <div className="eyebrow">{eyebrow}</div>
      <h1>{title}</h1>
      <p>{description}</p>
    </header>
  )
}

function StatusBadge({ status }: { status: string }) {
  const normalized = status.toLowerCase().replaceAll(" ", "_")
  return <span className={`status-badge status-badge--${normalized}`}>{status}</span>
}

function EvidenceButton({ evidenceIds, onOpen }: { evidenceIds?: string[]; onOpen: EvidenceOpener }) {
  if (!evidenceIds?.length) return <span className="muted-label">No source evidence</span>
  const first = evidenceIds[0]
  return (
    <button className="evidence-link" type="button" onClick={() => onOpen(first)} aria-label={`Open ${first}`}>
      Evidence {evidenceIds.length > 1 ? `(${evidenceIds.length})` : ""}
      <ArrowUpRight size={14} />
    </button>
  )
}

export function OverviewView({ report, onOpenEvidence }: { report: CommunityReport; onOpenEvidence: EvidenceOpener }) {
  const overview = report.Overview
  const languages = Object.entries(overview.language_counts).map(([language, count]) => ({ language: language.toUpperCase(), count }))
  const firstEvidence = report.Activation.flatMap((item) => item.evidence_ids)[0]
  const feedbackObserved = Object.values(report["Community Feedback"].seed_counts).reduce((sum, item) => sum + item.count, 0)
  const capabilities = [
    ["Community analysis", report.capabilities.community_analysis],
    ["Campaign-aware", report.capabilities.campaign_intelligence],
    ["Outcome-aware", report.capabilities.outcome_validation],
  ] as const

  return (
    <section className="report-page">
      <PageHeading eyebrow="Scope before interpretation" title="Overview" description="What was analyzed, which capabilities are available, and which evidence-backed signals deserve review." />
      <div className="scope-grid">
        <ScopeCard label="Messages" value={overview.message_count} suffix="messages" />
        <ScopeCard label="Communities" value={overview.community_count} suffix="communities" />
        <ScopeCard label="Languages" value={Object.keys(overview.language_counts).length} suffix="languages" />
        <ScopeCard label="Campaigns" value={overview.campaign_count} suffix="campaigns" />
      </div>

      <div className="capability-grid">
        {capabilities.map(([label, capability]) => (
          <article className="capability-card" key={label}>
            <span>{label}</span>
            <StatusBadge status={capability?.status ?? "not_available"} />
            {capability?.reason ? <small>{capability.reason}</small> : null}
          </article>
        ))}
      </div>

      <div className="report-grid report-grid--2">
        <article className="report-card chart-card">
          <div className="card-heading"><div><Languages size={18} /><h2>Language coverage</h2></div><span>{overview.message_count} total</span></div>
          <div className="chart-scroll" aria-label="Message count by language">
            <BarChart width={480} height={230} data={languages} margin={{ top: 10, right: 8, left: -18, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#dfe3dd" />
              <XAxis dataKey="language" tickLine={false} axisLine={false} />
              <YAxis tickLine={false} axisLine={false} allowDecimals={false} />
              <Tooltip cursor={{ fill: "#f1eee7" }} />
              <Bar dataKey="count" fill="#155d4b" radius={[5, 5, 0, 0]} />
            </BarChart>
          </div>
        </article>
        <article className="report-card">
          <div className="card-heading"><div><BarChart3 size={18} /><h2>Signals in this report</h2></div><span>Separate observations</span></div>
          <div className="signal-list">
            <SignalRow label="Meaningful interaction" value={percent(average(report.Activation, "meaningful_interaction_ratio"))} />
            <SignalRow label="Peer support" value={percent(average(report.Activation, "peer_support_ratio"))} />
            <SignalRow label="Duplicate content" value={percent(average(report.Hygiene, "duplicate_ratio"))} />
            <SignalRow label="Feedback observations" value={String(feedbackObserved)} />
          </div>
          {firstEvidence ? <EvidenceButton evidenceIds={[firstEvidence]} onOpen={onOpenEvidence} /> : null}
        </article>
      </div>

      <div className="boundary-note"><ShieldCheck size={20} /><div><strong>Message count is context, not quality.</strong><span>No composite moderator score is calculated. Each signal keeps its own method, denominator, evidence, and limitations.</span></div></div>
      <Limitations report={report} />
    </section>
  )
}

function ScopeCard({ label, value, suffix }: { label: string; value: number; suffix: string }) {
  return <article className="scope-card"><span>{label}</span><strong>{value}</strong><small>{value} {suffix}</small></article>
}

function SignalRow({ label, value }: { label: string; value: string }) {
  return <div className="signal-row"><span>{label}</span><strong>{value}</strong></div>
}

export function CampaignsView({ report, onOpenEvidence }: { report: CommunityReport; onOpenEvidence: EvidenceOpener }) {
  const judgments = report.Campaign.judgments
  const campaignIds = [...new Set(judgments.map((item) => item.campaign_id))].sort()
  const [campaignFilter, setCampaignFilter] = useState("all")
  const visibleJudgments =
    campaignFilter === "all"
      ? judgments
      : judgments.filter((item) => item.campaign_id === campaignFilter)
  return (
    <section className="report-page">
      <PageHeading eyebrow="Campaign-aware intelligence" title="Campaigns" description="Compare intended claims with what each community actually discussed. Deterministic coverage remains pending human review." />
      <div className="method-strip"><div><BadgeCheck size={18} /><span>Method: <strong>{report.Campaign.method}</strong></span></div><StatusBadge status={report.Campaign.review_status} /></div>
      {campaignIds.length > 1 ? (
        <div className="view-toolbar">
          <label>
            <span>Campaign</span>
            <select
              aria-label="Campaign filter"
              value={campaignFilter}
              onChange={(event) => setCampaignFilter(event.target.value)}
            >
              <option value="all">All campaigns</option>
              {campaignIds.map((campaignId) => (
                <option value={campaignId} key={campaignId}>{campaignId}</option>
              ))}
            </select>
          </label>
          <span>{visibleJudgments.length} judgments</span>
        </div>
      ) : null}
      {!judgments.length ? <UnavailableState title="No campaign data provided" detail="Community-only analysis remains available; import campaign records to enable this view." /> : (
        <div className="table-shell">
          <table><thead><tr><th>Campaign</th><th>Community</th><th>Claim</th><th>Coverage</th><th>Confidence</th><th>Review</th><th>Source</th></tr></thead>
            <tbody>{visibleJudgments.map((item, index) => <tr key={`${item.campaign_id}-${item.community_id}-${item.claim_id}-${index}`}><td>{item.campaign_id}</td><td>{item.community_id}</td><td><strong>{item.claim_id}</strong></td><td><StatusBadge status={item.status} /></td><td><span className="mono-value">{item.confidence.toFixed(2)}</span><small className="cell-note">evidence strength</small></td><td>{item.review_status}</td><td><EvidenceButton evidenceIds={item.evidence_ids} onOpen={onOpenEvidence} /></td></tr>)}</tbody>
          </table>
        </div>
      )}
      <div className="boundary-note boundary-note--warm"><CircleHelp size={20} /><div><strong>General multilingual semantic judgment: Not implemented.</strong><span>The current method is a transparent curated-alias baseline. Confidence is evidence strength, not a correctness probability.</span></div></div>
    </section>
  )
}

export function CommunitiesView({ report, onOpenEvidence }: { report: CommunityReport; onOpenEvidence: EvidenceOpener }) {
  const communityIds = [...new Set([...report.Activation.map((item) => item.community_id), ...report.Hygiene.map((item) => item.community_id)])].sort()
  return (
    <section className="report-page">
      <PageHeading eyebrow="Compare, do not score" title="Communities" description="Explore activation and hygiene as separate observations. Communities are not ranked and moderators do not receive a composite score." />
      {!communityIds.length ? <UnavailableState title="No community observations" detail="The loaded report does not contain comparable community records." /> : (
        <div className="table-shell"><table><thead><tr><th>Community</th><th>Meaningful interaction</th><th>Peer support</th><th>Response latency</th><th>Duplicate</th><th>Filler</th><th>Evidence</th></tr></thead><tbody>
          {communityIds.map((communityId) => {
            const activation = report.Activation.filter((item) => item.community_id === communityId)
            const hygiene = report.Hygiene.filter((item) => item.community_id === communityId)
            const evidenceIds = [...new Set([...activation.flatMap((item) => item.evidence_ids), ...hygiene.flatMap((item) => item.evidence_ids)])]
            return <tr key={communityId}><td><strong>{communityId}</strong><small className="cell-note">{activation.length || hygiene.length} scopes</small></td><td>{percent(average(activation, "meaningful_interaction_ratio"))}</td><td>{percent(average(activation, "peer_support_ratio"))}</td><td>{duration(average(activation, "response_latency_seconds"))}</td><td>{percent(average(hygiene, "duplicate_ratio"))}</td><td>{percent(average(hygiene, "filler_ratio"))}</td><td><EvidenceButton evidenceIds={evidenceIds} onOpen={onOpenEvidence} /></td></tr>
          })}
        </tbody></table></div>
      )}
      <div className="boundary-note"><UsersRound size={20} /><div><strong>Every value has its own denominator.</strong><span>Open evidence to review source messages. A low latency or high activity count does not by itself prove a useful response.</span></div></div>
    </section>
  )
}

export function BehaviorsView({ report, onOpenEvidence }: { report: CommunityReport; onOpenEvidence: EvidenceOpener }) {
  const clusters = report.Behavior.clusters
  const feedback = Object.entries(report["Community Feedback"].seed_counts)
  return (
    <section className="report-page">
      <PageHeading eyebrow="Candidate patterns, not final labels" title="Behaviors" description="Deterministic seed labels and unsupervised clusters stay separate so reviewers can see exactly what the system did." />
      <div className="section-label"><Network size={17} /><h2>Candidate clusters</h2><span>{clusters.length} selected by {report.Behavior.selection_method}</span></div>
      <div className="cluster-grid">{clusters.map((cluster) => <article className="cluster-card" key={cluster.cluster_id}><div className="card-heading"><strong>{cluster.cluster_id}</strong><StatusBadge status={cluster.review_status} /></div><h3>{cluster.proposed_behavior_name ?? "Unnamed candidate behavior"}</h3><p>{cluster.behavior_description}</p><div className="term-list">{cluster.top_terms.slice(0, 8).map((term) => <span key={term}>{term}</span>)}</div><dl className="compact-dl"><div><dt>Messages</dt><dd>{cluster.message_count}</dd></div><div><dt>Confidence</dt><dd>{cluster.confidence.toFixed(2)}</dd></div><div><dt>Method</dt><dd>{cluster.method}</dd></div></dl><p className="distribution-line">Languages: {cluster.language_distribution.map(([name, count]) => `${name} ${count}`).join(" · ") || "Not available"}</p><EvidenceButton evidenceIds={cluster.evidence_ids} onOpen={onOpenEvidence} /></article>)}</div>
      <div className="section-label section-label--spaced"><ShieldCheck size={17} /><h2>Deterministic feedback seeds</h2></div>
      <div className="seed-grid">{feedback.map(([name, item]) => <article className="seed-card" key={name}><span>{titleCase(name)}</span><strong>{item.count}</strong><small>{item.observation_status}</small>{item.evidence_ids.length ? <EvidenceButton evidenceIds={item.evidence_ids} onOpen={onOpenEvidence} /> : null}</article>)}</div>
      <div className="boundary-note boundary-note--warm"><AlertTriangle size={20} /><div><strong>Human review required.</strong><span>An unnamed cluster stays unnamed. LLM behavior interpretation is Not implemented and no polished label is invented.</span></div></div>
    </section>
  )
}

export function ResponsePatternsView({ report, onOpenEvidence }: { report: CommunityReport; onOpenEvidence: EvidenceOpener }) {
  const episodes = report["Episodes/Response Patterns"]
  return (
    <section className="report-page">
      <PageHeading eyebrow="How conversations unfold" title="Response Patterns" description="Reply-graph episodes show participation, questions, candidate answers, depth, and latency without claiming semantic resolution." />
      {!episodes.length ? <UnavailableState title="No reply episodes observed" detail="The method is available, but this dataset has no linked reply threads." /> : <div className="episode-grid">{episodes.map((episode) => <article className="episode-card" key={episode.episode_id}><div className="card-heading"><div><MessageCircleReply size={17} /><h2>{episode.episode_id}</h2></div><StatusBadge status={episode.review_status} /></div><p>{episode.community_id}{episode.campaign_id ? ` · ${episode.campaign_id}` : " · Community-only"}</p><dl className="episode-metrics"><div><dt>Depth</dt><dd>{episode.conversation_depth}</dd></div><div><dt>People</dt><dd>{episode.unique_participants}</dd></div><div><dt>Questions</dt><dd>{episode.question_count}</dd></div><div><dt>Candidate answers</dt><dd>{episode.candidate_answered_question_count}</dd></div><div><dt>Unanswered</dt><dd>{episode.unanswered_question_count}</dd></div><div><dt>First response</dt><dd>{duration(episode.first_response_latency_seconds)}</dd></div></dl><small className="interpretation-limit">{episode.interpretation_limit}</small><EvidenceButton evidenceIds={episode.evidence_ids} onOpen={onOpenEvidence} /></article>)}</div>}
      <div className="boundary-note"><MessageCircleReply size={20} /><div><strong>Structural candidate answer ≠ resolved issue.</strong><span>The product reports transparent reply relationships and never upgrades them into a semantic resolution claim.</span></div></div>
    </section>
  )
}

export function MetricLabView({ report, onOpenEvidence }: { report: CommunityReport; onOpenEvidence: EvidenceOpener }) {
  const definitions = Object.entries(report["Metric Lab"].definitions)
  const observations = report["Metric Lab"].observations
  return (
    <section className="report-page">
      <PageHeading eyebrow="Discover, then validate" title="Metric Lab" description="Inspect candidate formulas, denominators, data requirements, observed values, and limitations before deciding whether a metric is useful." />
      <div className="metric-layout"><div className="metric-list">{definitions.map(([id, definition]) => <MetricDefinitionCard key={id} id={id} definition={definition} />)}</div><aside className="observation-panel"><div className="card-heading"><div><FlaskConical size={18} /><h2>Observed metric records</h2></div><span>{observations.length}</span></div>{observations.length ? observations.slice(0, 20).map((item, index) => { const metricId = String(item.metric_name ?? item.metric_id ?? `observation_${index + 1}`); const value = typeof item.value === "number" ? item.value.toFixed(3) : "See record"; return <article className="observation-row" key={`${metricId}-${index}`}><div><strong>{metricId}</strong><small>{String(item.community_id ?? "all communities")}{item.campaign_id ? ` · ${String(item.campaign_id)}` : ""}</small></div><span>{value}</span>{item.evidence_ids?.length ? <EvidenceButton evidenceIds={item.evidence_ids} onOpen={onOpenEvidence} /> : null}</article> }) : <p className="muted-copy">No metric observations are available for this dataset.</p>}</aside></div>
      <div className="boundary-note boundary-note--warm"><AlertTriangle size={20} /><div><strong>Association, not causation.</strong><span>{report["Metric Lab"].association_not_causation}</span></div></div>
    </section>
  )
}

function MetricDefinitionCard({ id, definition }: { id: string; definition: MetricDefinition }) {
  return <article className="metric-card"><div className="card-heading"><strong>{id}</strong><StatusBadge status={definition.required_fields.length ? "defined" : "not_available"} /></div><p>{definition.business_meaning}</p><div className="formula-box">{definition.formula}</div><dl className="definition-dl"><div><dt>Denominator</dt><dd>{definition.denominator}</dd></div><div><dt>Unit</dt><dd>{definition.unit_of_analysis}</dd></div><div><dt>Window</dt><dd>{definition.time_window}</dd></div><div><dt>Required fields</dt><dd>{definition.required_fields.join(", ")}</dd></div></dl>{definition.limitations.length ? <small className="interpretation-limit">Limit: {definition.limitations[0]}</small> : null}</article>
}

export function EvidenceView({ evidence, onOpenEvidence }: { evidence: EvidenceRecord[]; onOpenEvidence: EvidenceOpener }) {
  const [query, setQuery] = useState("")
  const filtered = useMemo(() => {
    const needle = query.trim().toLowerCase()
    if (!needle) return evidence
    return evidence.filter((item) => JSON.stringify(item).toLowerCase().includes(needle))
  }, [evidence, query])
  return (
    <section className="report-page">
      <PageHeading eyebrow="Source-linked audit trail" title="Evidence" description="Filter the analytical claims and source messages behind the report. Imported content remains on this machine." />
      <label className="search-field"><FileSearch size={17} /><span className="sr-only">Filter evidence</span><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Filter by evidence ID, message, community, campaign, or method" /></label>
      <div className="table-shell"><table><thead><tr><th>Evidence ID</th><th>Type</th><th>Community</th><th>Campaign</th><th>Method</th><th>Review</th><th>Detail</th></tr></thead><tbody>{filtered.slice(0, 250).map((item) => <tr key={item.evidence_id}><td><strong>{item.evidence_id}</strong><small className="cell-note">{item.message_id ?? item.claim_id ?? "analysis scope"}</small></td><td>{item.evidence_type}</td><td>{item.community_id ?? "—"}</td><td>{item.analysis_campaign_id ?? item.source_campaign_id ?? "—"}</td><td>{item.method}</td><td>{item.review_status}</td><td><EvidenceButton evidenceIds={[item.evidence_id]} onOpen={onOpenEvidence} /></td></tr>)}</tbody></table></div>
      {!filtered.length ? <UnavailableState title="No evidence matches this filter" detail="Clear the filter to return to the complete audit trail." /> : null}
    </section>
  )
}

function Limitations({ report }: { report: CommunityReport }) {
  const items = Object.values(report.limitations)
  if (!items.length) return null
  return <details className="limitations-panel"><summary>Methods and limitations ({items.length})</summary><ul>{items.map((item, index) => <li key={`${index}-${item}`}>{item}</li>)}</ul></details>
}

function UnavailableState({ title, detail }: { title: string; detail: string }) {
  return <div className="unavailable-state"><CircleHelp size={26} /><strong>{title}</strong><p>{detail}</p></div>
}

export type ReportViewId = "overview" | "campaigns" | "communities" | "behaviors" | "responses" | "metrics" | "evidence"

export function ActiveReportView({ view, report, evidence, onOpenEvidence }: { view: ReportViewId; report: CommunityReport; evidence: EvidenceRecord[]; onOpenEvidence: EvidenceOpener }) {
  if (view === "campaigns") return <CampaignsView report={report} onOpenEvidence={onOpenEvidence} />
  if (view === "communities") return <CommunitiesView report={report} onOpenEvidence={onOpenEvidence} />
  if (view === "behaviors") return <BehaviorsView report={report} onOpenEvidence={onOpenEvidence} />
  if (view === "responses") return <ResponsePatternsView report={report} onOpenEvidence={onOpenEvidence} />
  if (view === "metrics") return <MetricLabView report={report} onOpenEvidence={onOpenEvidence} />
  if (view === "evidence") return <EvidenceView evidence={evidence} onOpenEvidence={onOpenEvidence} />
  return <OverviewView report={report} onOpenEvidence={onOpenEvidence} />
}
