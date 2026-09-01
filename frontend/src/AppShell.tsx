import {
  Activity,
  BarChart3,
  BookOpenCheck,
  ChevronRight,
  CircleDotDashed,
  FileSearch,
  FlaskConical,
  Gauge,
  Languages,
  Megaphone,
  Menu,
  MessageCircleReply,
  Network,
  Play,
  ShieldCheck,
  UsersRound,
  X,
} from "lucide-react"
import { useState, type ComponentType } from "react"

type ViewId =
  | "overview"
  | "campaigns"
  | "communities"
  | "behaviors"
  | "responses"
  | "metrics"
  | "evidence"

type NavItem = {
  id: ViewId
  label: string
  icon: ComponentType<{ size?: number; strokeWidth?: number }>
  eyebrow: string
  description: string
}

const navItems: NavItem[] = [
  {
    id: "overview",
    label: "Overview",
    icon: Gauge,
    eyebrow: "Community health at a glance",
    description: "See the scope, data readiness, and the strongest evidence-backed signals.",
  },
  {
    id: "campaigns",
    label: "Campaigns",
    icon: Megaphone,
    eyebrow: "Campaign-aware intelligence",
    description: "Compare what each community discussed with the claims a campaign intended to convey.",
  },
  {
    id: "communities",
    label: "Communities",
    icon: UsersRound,
    eyebrow: "Community-level comparison",
    description: "Explore activation, hygiene, languages, and response quality without reducing people to a score.",
  },
  {
    id: "behaviors",
    label: "Behaviors",
    icon: Network,
    eyebrow: "Behavior discovery",
    description: "Inspect candidate behavior groups, their supporting messages, confidence, and review status.",
  },
  {
    id: "responses",
    label: "Response Patterns",
    icon: MessageCircleReply,
    eyebrow: "How conversations unfold",
    description: "Trace questions, replies, participation, latency, and unanswered conversation paths.",
  },
  {
    id: "metrics",
    label: "Metric Lab",
    icon: FlaskConical,
    eyebrow: "Metric discovery and validation",
    description: "Review formulas, denominators, observed associations, uncertainty, and limitations.",
  },
  {
    id: "evidence",
    label: "Evidence",
    icon: FileSearch,
    eyebrow: "Every claim back to source",
    description: "Open the evidence trail behind a judgment, including source messages and review status.",
  },
]

export function AppShell() {
  const [activeView, setActiveView] = useState<ViewId>("overview")
  const [mobileNavOpen, setMobileNavOpen] = useState(false)
  const [demoMessage, setDemoMessage] = useState<string | null>(null)
  const current = navItems.find((item) => item.id === activeView) ?? navItems[0]

  const navigate = (id: ViewId) => {
    setActiveView(id)
    setMobileNavOpen(false)
  }

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
          <button
            className="icon-button sidebar-close"
            type="button"
            aria-label="Close navigation"
            onClick={() => setMobileNavOpen(false)}
          >
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
          <p>
            Local-first. Source messages stay on this machine unless you choose otherwise.
          </p>
        </div>
      </aside>

      {mobileNavOpen ? (
        <button
          className="nav-backdrop"
          type="button"
          aria-label="Close navigation"
          onClick={() => setMobileNavOpen(false)}
        />
      ) : null}

      <main className="main-stage">
        <header className="topbar">
          <button
            className="icon-button menu-button"
            type="button"
            aria-label="Open navigation"
            onClick={() => setMobileNavOpen(true)}
          >
            <Menu size={20} />
          </button>
          <div className="data-chip">
            <span className="data-chip__dot" aria-hidden="true" />
            No analysis loaded
          </div>
          <button className="quiet-link" type="button">
            <BookOpenCheck size={17} />
            Data &amp; methods
          </button>
        </header>

        <div className="content-wrap">
          {activeView === "overview" ? (
            <OverviewEmptyState
              demoMessage={demoMessage}
              onRunDemo={() =>
                setDemoMessage("The local demo connection is the next implementation step.")
              }
            />
          ) : (
            <SectionEmptyState item={current} onRunDemo={() => navigate("overview")} />
          )}
        </div>
      </main>
    </div>
  )
}

function OverviewEmptyState({
  demoMessage,
  onRunDemo,
}: {
  demoMessage: string | null
  onRunDemo: () => void
}) {
  return (
    <section className="overview-hero" aria-labelledby="overview-title">
      <div className="hero-copy">
        <div className="eyebrow">
          <Activity size={15} aria-hidden="true" />
          Evidence-first, multilingual, local
        </div>
        <h1 id="overview-title">Understand how communities respond—not just how much they talk.</h1>
        <p className="hero-lede">
          Turn Telegram conversations into traceable patterns across campaigns, behaviors,
          activation, hygiene, feedback, and candidate metrics.
        </p>

        <div className="hero-actions">
          <button className="button button--primary" type="button" onClick={onRunDemo}>
            <Play size={17} fill="currentColor" />
            Run synthetic demo
          </button>
          <button className="button button--secondary" type="button">
            Import Telegram JSON
          </button>
        </div>

        <p className="data-boundary">
          <Languages size={17} aria-hidden="true" />
          Synthetic data until you import your own export. No hidden cloud upload.
        </p>
        {demoMessage ? (
          <p className="inline-notice" role="status">
            {demoMessage}
          </p>
        ) : null}
      </div>

      <div className="signal-board" aria-label="Analysis model preview">
        <div className="signal-board__header">
          <span>From conversation to evidence</span>
          <span className="status-pill">Local V1</span>
        </div>
        <div className="signal-flow">
          <SignalStep number="01" label="Messages" meta="Telegram JSON / synthetic" />
          <SignalStep number="02" label="Patterns" meta="Behavior + response" />
          <SignalStep number="03" label="Evidence" meta="Source + confidence" />
          <SignalStep number="04" label="Decision" meta="Human-reviewed" isLast />
        </div>
        <div className="principle-card">
          <BarChart3 size={20} aria-hidden="true" />
          <div>
            <strong>Message count is context, not quality.</strong>
            <span>Every important interpretation stays connected to evidence.</span>
          </div>
        </div>
      </div>
    </section>
  )
}

function SignalStep({
  number,
  label,
  meta,
  isLast = false,
}: {
  number: string
  label: string
  meta: string
  isLast?: boolean
}) {
  return (
    <div className="signal-step">
      <span className="signal-step__number">{number}</span>
      <div>
        <strong>{label}</strong>
        <span>{meta}</span>
      </div>
      {!isLast ? <ChevronRight size={18} aria-hidden="true" /> : null}
    </div>
  )
}

function SectionEmptyState({ item, onRunDemo }: { item: NavItem; onRunDemo: () => void }) {
  const Icon = item.icon
  return (
    <section className="section-empty" aria-labelledby={`${item.id}-title`}>
      <div className="section-empty__icon">
        <Icon size={28} strokeWidth={1.7} />
      </div>
      <div className="eyebrow">{item.eyebrow}</div>
      <h1 id={`${item.id}-title`}>{item.label}</h1>
      <p>{item.description}</p>
      <div className="empty-panel">
        <CircleDotDashed size={28} aria-hidden="true" />
        <strong>No analysis loaded</strong>
        <span>Run a demo or import data to populate this view with traceable results.</span>
        <button className="button button--secondary" type="button" onClick={onRunDemo}>
          Return to overview
        </button>
      </div>
    </section>
  )
}
