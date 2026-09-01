import * as Dialog from "@radix-ui/react-dialog"
import {
  Activity,
  BarChart3,
  BookOpenCheck,
  ChevronRight,
  CircleDotDashed,
  FileJson,
  FileSearch,
  FlaskConical,
  Gauge,
  Languages,
  LoaderCircle,
  Megaphone,
  Menu,
  MessageCircleReply,
  Network,
  Play,
  ShieldCheck,
  Upload,
  UsersRound,
  X,
} from "lucide-react"
import { lazy, Suspense, useRef, useState, type ComponentType } from "react"

import { apiClient } from "./api"
import type { ReportViewId } from "./ReportViews"
import type { AnalysisResponse, AppClient, EvidenceRecord } from "./types"

const ActiveReportView = lazy(() =>
  import("./ReportViews").then((module) => ({ default: module.ActiveReportView })),
)

type NavItem = {
  id: ReportViewId
  label: string
  icon: ComponentType<{ size?: number; strokeWidth?: number }>
}

const navItems: NavItem[] = [
  { id: "overview", label: "Overview", icon: Gauge },
  { id: "campaigns", label: "Campaigns", icon: Megaphone },
  { id: "communities", label: "Communities", icon: UsersRound },
  { id: "behaviors", label: "Behaviors", icon: Network },
  { id: "responses", label: "Response Patterns", icon: MessageCircleReply },
  { id: "metrics", label: "Metric Lab", icon: FlaskConical },
  { id: "evidence", label: "Evidence", icon: FileSearch },
]

export function AppShell({ client = apiClient }: { client?: AppClient }) {
  const [activeView, setActiveView] = useState<ReportViewId>("overview")
  const [mobileNavOpen, setMobileNavOpen] = useState(false)
  const [analysis, setAnalysis] = useState<AnalysisResponse | null>(null)
  const [evidence, setEvidence] = useState<EvidenceRecord[]>([])
  const [selectedEvidence, setSelectedEvidence] = useState<EvidenceRecord | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [methodsOpen, setMethodsOpen] = useState(false)
  const fileInput = useRef<HTMLInputElement>(null)

  const navigate = (id: ReportViewId) => {
    setActiveView(id)
    setMobileNavOpen(false)
  }

  const completeAnalysis = async (request: Promise<AnalysisResponse>) => {
    setLoading(true)
    setError(null)
    try {
      const result = await request
      const evidenceResult = await client.getEvidence(result.analysis_id)
      setAnalysis(result)
      setEvidence(evidenceResult.items)
      setActiveView("overview")
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "The local analysis could not be completed.")
    } finally {
      setLoading(false)
    }
  }

  const runDemo = () => completeAnalysis(client.runDemo())

  const importTelegram = (file: File) => completeAnalysis(client.importTelegram(file))

  const chooseImport = () => fileInput.current?.click()

  const onFileSelected = (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0]
    if (file) importTelegram(file)
    event.target.value = ""
  }

  const openEvidence = (evidenceId: string) => {
    const record = evidence.find((item) => item.evidence_id === evidenceId)
    if (record) setSelectedEvidence(record)
  }

  const sourceLabel = analysis
    ? `${analysis.report.data_status === "synthetic" ? "Synthetic" : "Imported"} · ${analysis.summary.message_count} msgs · ${analysis.summary.community_count} groups`
    : "No analysis loaded"

  return (
    <div className="app-frame">
      <aside className={`sidebar ${mobileNavOpen ? "sidebar--open" : ""}`}>
        <div className="brand-lockup">
          <div className="brand-mark" aria-hidden="true">
            <CircleDotDashed size={23} strokeWidth={1.8} />
          </div>
          <div>
            <span className="brand-name">Community</span>
            <span className="brand-name brand-name--accent">Intelligence</span>
          </div>
          <button className="icon-button sidebar-close" type="button" aria-label="Close navigation" onClick={() => setMobileNavOpen(false)}>
            <X size={20} />
          </button>
        </div>

        <nav className="primary-nav" aria-label="Primary">
          {navItems.map((item) => {
            const Icon = item.icon
            const active = activeView === item.id
            return (
              <button
                key={item.id}
                type="button"
                className={`nav-item ${active ? "nav-item--active" : ""}`}
                aria-current={active ? "page" : undefined}
                onClick={() => navigate(item.id)}
              >
                <Icon size={18} strokeWidth={1.9} />
                <span>{item.label}</span>
              </button>
            )
          })}
        </nav>

        <div className="sidebar-note">
          <ShieldCheck size={18} aria-hidden="true" />
          <p>Local-first. Source messages stay on this machine unless you choose otherwise.</p>
        </div>
      </aside>

      {mobileNavOpen ? (
        <button className="nav-backdrop" type="button" aria-label="Close navigation" onClick={() => setMobileNavOpen(false)} />
      ) : null}

      <main className="main-stage">
        <header className="topbar">
          <button className="icon-button menu-button" type="button" aria-label="Open navigation" onClick={() => setMobileNavOpen(true)}>
            <Menu size={20} />
          </button>
          <div className={`data-chip ${analysis ? "data-chip--loaded" : ""}`}>
            <span className="data-chip__dot" aria-hidden="true" />
            {sourceLabel}
          </div>
          {analysis ? (
            <div className="topbar-actions">
              <button className="quiet-link" type="button" onClick={runDemo} disabled={loading}>
                <Play size={15} /> New demo
              </button>
              <button className="quiet-link" type="button" onClick={chooseImport} disabled={loading}>
                <Upload size={15} /> Import JSON
              </button>
            </div>
          ) : null}
          <button className="quiet-link" type="button" onClick={() => setMethodsOpen(true)}>
            <BookOpenCheck size={17} />
            Data &amp; methods
          </button>
        </header>

        <input ref={fileInput} className="sr-only" type="file" accept=".json,application/json" aria-label="Select Telegram JSON" onChange={onFileSelected} />

        {error ? (
          <div className="global-alert" role="alert">
            <strong>Analysis stopped</strong>
            <span>{error}</span>
            <button type="button" aria-label="Dismiss error" onClick={() => setError(null)}><X size={16} /></button>
          </div>
        ) : null}

        <div className={`content-wrap ${analysis ? "content-wrap--report" : ""}`}>
          {loading ? <LoadingState /> : null}
          {!analysis && !loading ? <OverviewEmptyState onRunDemo={runDemo} onImport={chooseImport} /> : null}
          {analysis && !loading ? (
            <Suspense fallback={<LoadingState compact />}>
              <ActiveReportView view={activeView} report={analysis.report} evidence={evidence} onOpenEvidence={openEvidence} />
            </Suspense>
          ) : null}
        </div>
      </main>

      <EvidenceDialog evidence={selectedEvidence} onClose={() => setSelectedEvidence(null)} />
      <MethodsDialog open={methodsOpen} onOpenChange={setMethodsOpen} analysis={analysis} />
    </div>
  )
}

function OverviewEmptyState({ onRunDemo, onImport }: { onRunDemo: () => void; onImport: () => void }) {
  return (
    <section className="overview-hero" aria-labelledby="overview-title">
      <div className="hero-copy">
        <div className="eyebrow"><Activity size={15} aria-hidden="true" />Evidence-first, multilingual, local</div>
        <h1 id="overview-title">Understand how communities respond—not just how much they talk.</h1>
        <p className="hero-lede">Turn Telegram conversations into traceable patterns across campaigns, behaviors, activation, hygiene, feedback, and candidate metrics.</p>
        <div className="hero-actions">
          <button className="button button--primary" type="button" onClick={onRunDemo}><Play size={17} fill="currentColor" />Run synthetic demo</button>
          <button className="button button--secondary" type="button" onClick={onImport}><FileJson size={17} />Import Telegram JSON</button>
        </div>
        <p className="data-boundary"><Languages size={17} aria-hidden="true" />Synthetic data until you import your own export. No hidden cloud upload.</p>
      </div>

      <div className="signal-board" aria-label="Analysis model preview">
        <div className="signal-board__header"><span>From conversation to evidence</span><span className="status-pill">Local V1</span></div>
        <div className="signal-flow">
          <SignalStep number="01" label="Messages" meta="Telegram JSON / synthetic" />
          <SignalStep number="02" label="Patterns" meta="Behavior + response" />
          <SignalStep number="03" label="Evidence" meta="Source + confidence" />
          <SignalStep number="04" label="Decision" meta="Human-reviewed" isLast />
        </div>
        <div className="principle-card"><BarChart3 size={20} aria-hidden="true" /><div><strong>Message count is context, not quality.</strong><span>Every important interpretation stays connected to evidence.</span></div></div>
      </div>
    </section>
  )
}

function SignalStep({ number, label, meta, isLast = false }: { number: string; label: string; meta: string; isLast?: boolean }) {
  return (
    <div className="signal-step">
      <span className="signal-step__number">{number}</span>
      <div><strong>{label}</strong><span>{meta}</span></div>
      {!isLast ? <ChevronRight size={18} aria-hidden="true" /> : null}
    </div>
  )
}

function LoadingState({ compact = false }: { compact?: boolean }) {
  return (
    <section className={`loading-state ${compact ? "loading-state--compact" : ""}`} aria-live="polite">
      <LoaderCircle size={30} className="spin" />
      <h1>Building the evidence trail</h1>
      <p>Normalizing messages, running deterministic analysis, and joining source evidence.</p>
    </section>
  )
}

function EvidenceDialog({ evidence, onClose }: { evidence: EvidenceRecord | null; onClose: () => void }) {
  return (
    <Dialog.Root open={Boolean(evidence)} onOpenChange={(open) => { if (!open) onClose() }}>
      <Dialog.Portal>
        <Dialog.Overlay className="dialog-overlay" />
        <Dialog.Content className="evidence-dialog" aria-describedby="evidence-description">
          <div className="dialog-header">
            <div>
              <span className="dialog-eyebrow">Source-linked audit trail</span>
              <Dialog.Title>Evidence detail</Dialog.Title>
            </div>
            <Dialog.Close asChild><button className="icon-button" type="button" aria-label="Close evidence"><X size={20} /></button></Dialog.Close>
          </div>
          {evidence ? (
            <>
              <p className="evidence-id">{evidence.evidence_id}</p>
              <Dialog.Description id="evidence-description">{evidence.evidence_type} · {evidence.review_status}</Dialog.Description>
              <div className="source-message">
                <span>Original source</span>
                <p>{evidence.source_text ?? "No source text is attached to this scope-level evidence record."}</p>
                <small>{evidence.message_id ?? evidence.claim_id ?? "Analysis scope"}{evidence.community_id ? ` · ${evidence.community_id}` : ""}</small>
              </div>
              <dl className="evidence-metadata">
                <div><dt>Method</dt><dd>{evidence.method}</dd></div>
                <div><dt>Campaign</dt><dd>{evidence.analysis_campaign_id ?? evidence.source_campaign_id ?? "Not applicable"}</dd></div>
                <div><dt>Confidence</dt><dd>{evidence.confidence ?? "Not scored"}</dd></div>
                <div><dt>Review</dt><dd>{evidence.review_status}</dd></div>
              </dl>
              <div className="confidence-note"><strong>How to read confidence</strong><p>{evidence.confidence_semantics}</p></div>
            </>
          ) : null}
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  )
}

function MethodsDialog({ open, onOpenChange, analysis }: { open: boolean; onOpenChange: (open: boolean) => void; analysis: AnalysisResponse | null }) {
  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="dialog-overlay" />
        <Dialog.Content className="methods-dialog">
          <div className="dialog-header">
            <div><span className="dialog-eyebrow">Product boundary</span><Dialog.Title>Data &amp; methods</Dialog.Title></div>
            <Dialog.Close asChild><button className="icon-button" type="button" aria-label="Close methods"><X size={20} /></button></Dialog.Close>
          </div>
          <Dialog.Description>Community Intelligence runs locally and keeps analytical claims connected to evidence.</Dialog.Description>
          <div className="methods-list">
            <article><ShieldCheck size={18} /><div><strong>Local by default</strong><p>Uploaded Telegram JSON is normalized and analyzed on this machine.</p></div></article>
            <article><Network size={18} /><div><strong>AI discovers candidates</strong><p>Behavior clusters and campaign judgments remain pending human review.</p></div></article>
            <article><FlaskConical size={18} /><div><strong>Statistics validate</strong><p>Reported relationships are descriptive associations, never causal effects.</p></div></article>
          </div>
          {analysis ? <div className="loaded-contract"><span>Loaded source</span><strong>{analysis.summary.source_format}</strong><small>Dataset {analysis.report.dataset_id} · schema {analysis.report.schema_version}</small></div> : null}
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  )
}
