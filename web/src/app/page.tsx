"use client";

import { useCallback, useState } from "react";
import { motion, AnimatePresence } from "motion/react";
import { TemplatePicker } from "@/components/template-picker";
import { DebateForm } from "@/components/debate-form";
import { CompanyContext } from "@/components/company-context";
import { LiveDebate } from "@/components/live-debate";
import { VerdictCard } from "@/components/verdict-card";
import { startDebate, type DebateResult, type Template } from "@/lib/api";
import { ChevronRight, ArrowRight } from "lucide-react";

const TEMPLATES: Template[] = [
  {
    id: "location",
    label: "Should we expand to this location?",
    description: "Evaluate footprint expansion, new market entry, or a second site.",
    icon: "map-pin",
    fields: [
      { name: "decision", label: "What are you deciding?", type: "text", placeholder: "Open a second location in DIFC, Dubai" },
      { name: "location", label: "Location & why it matters", type: "text", placeholder: "Gate District, DIFC — near the financial towers" },
      { name: "budget", label: "Total investment budget", type: "text", placeholder: "AED 380,000 all-in" },
      { name: "competitors", label: "Competition in that area", type: "textarea", placeholder: "1 Starbucks, 2 artisan independents, Tom&Serg nearby" },
      { name: "target_customer", label: "Primary customer profile", type: "text", placeholder: "Finance professionals, 28-45, weekday lunch crowd" },
    ],
  },
  {
    id: "pricing",
    label: "Should we change our pricing?",
    description: "Model churn risk, revenue impact, and competitive positioning before you move.",
    icon: "tag",
    fields: [
      { name: "decision", label: "What pricing change are you considering?", type: "text", placeholder: "Raise SaaS from AED 299/mo to AED 499/mo" },
      { name: "current_price", label: "Current price", type: "text", placeholder: "AED 299/month" },
      { name: "proposed_price", label: "Proposed price", type: "text", placeholder: "AED 499/month" },
      { name: "competitor_pricing", label: "What competitors charge", type: "textarea", placeholder: "Competitor A: AED 399/mo, Competitor B: AED 199/mo freemium" },
      { name: "customer_base", label: "Current subscriber base & churn", type: "text", placeholder: "340 active, 4% monthly churn, mostly Dubai SMEs" },
    ],
  },
  {
    id: "launch",
    label: "Should we launch this product or service?",
    description: "Stress-test a new product, line extension, or service before committing capital.",
    icon: "rocket",
    fields: [
      { name: "decision", label: "What are you launching?", type: "text", placeholder: "Premium co-working space with specialty coffee" },
      { name: "target_market", label: "Who is this for?", type: "text", placeholder: "Freelancers and remote workers in Barcelona" },
      { name: "budget", label: "Launch budget", type: "text", placeholder: "€120,000" },
      { name: "timeline", label: "Timeline & break-even target", type: "text", placeholder: "3 months to open, break-even in 8 months" },
      { name: "differentiator", label: "Why will customers choose this over alternatives?", type: "textarea", placeholder: "Only venue combining co-working + specialty coffee + events" },
    ],
  },
  {
    id: "hire",
    label: "Should we make this hire?",
    description: "Evaluate whether a key role is the right move at the right time, with your numbers.",
    icon: "user-plus",
    fields: [
      { name: "decision", label: "What role are you hiring?", type: "text", placeholder: "Head of Sales at AED 45,000/month + 10% commission" },
      { name: "current_revenue", label: "Current monthly revenue", type: "text", placeholder: "AED 220,000/month" },
      { name: "expected_impact", label: "What does this hire unlock?", type: "textarea", placeholder: "Close 4 enterprise accounts in Q1, add AED 80K MRR in 6 months" },
      { name: "alternative", label: "The alternative if you don't hire", type: "text", placeholder: "Founder-led sales + part-time SDR at AED 8K/month" },
      { name: "runway", label: "Current cash runway", type: "text", placeholder: "11 months at current burn rate" },
    ],
  },
  {
    id: "partnership",
    label: "Should we take this deal or partnership?",
    description: "Evaluate terms, lock-in risk, and strategic fit of a deal before signing.",
    icon: "handshake",
    fields: [
      { name: "decision", label: "What is the deal?", type: "text", placeholder: "Exclusive distribution deal with a regional supplier" },
      { name: "terms", label: "Key deal terms", type: "textarea", placeholder: "2-year exclusive, 30% margin, minimum 500 units/month" },
      { name: "upside", label: "Best-case upside", type: "textarea", placeholder: "Guaranteed supply, 15% lower cost than current supplier" },
      { name: "downside", label: "Worst-case downside", type: "textarea", placeholder: "Locked in for 2 years, can't use alternatives" },
      { name: "alternative", label: "What happens if you walk away?", type: "text", placeholder: "Continue with 3 non-exclusive suppliers at current rates" },
    ],
  },
  {
    id: "freeform",
    label: "Custom decision",
    description: "Any strategic question — no template constraints, full flexibility.",
    icon: "message-circle",
    fields: [
      { name: "decision", label: "Describe the decision in full", type: "textarea", placeholder: "We run a 3-year-old logistics company in Dubai with AED 1.2M revenue. A PE firm has offered 25% equity for AED 600,000 at a AED 2.4M valuation with a 2x liquidation preference and board seat. We're profitable at 15% margin, growing 40% YoY, but cash-constrained. Should we take it?" },
      { name: "context", label: "Additional context", type: "textarea", placeholder: "Key constraints, stakeholder concerns, timing pressures..." },
    ],
  },
];

const COUNCIL = [
  {
    role: "strategist",
    name: "Nadia",
    title: "Strategist",
    subtitle: "Market & Revenue",
    initials: "NA",
    color: "#C49A1A",
    oneliner: "Builds the financial case. TAM, unit economics, break-even. If the numbers don't work, I'll say so first.",
  },
  {
    role: "devils_advocate",
    name: "Marcus",
    title: "Risk Hunter",
    subtitle: "Fatal Flaws",
    initials: "MA",
    color: "#E03E52",
    oneliner: "My job is to kill the idea. If there's a scenario that ends the business, I'll find it and name it.",
  },
  {
    role: "assumption_checker",
    name: "Sofia",
    title: "Assumption Auditor",
    subtitle: "Evidence Review",
    initials: "SO",
    color: "#FFBF00",
    oneliner: "Every plan rests on assumptions. I rate each one and flag the ones that will bite you.",
  },
  {
    role: "fact_checker",
    name: "Cole",
    title: "Market Reality",
    subtitle: "Data Verification",
    initials: "CO",
    color: "#007EFF",
    oneliner: "I verify claims against real data. Competitor counts, actual pricing, regulatory requirements — not guesses.",
  },
  {
    role: "pragmatist",
    name: "Elise",
    title: "Execution Realist",
    subtitle: "Operational Fit",
    initials: "EL",
    color: "#8B5CF6",
    oneliner: "Can your team actually pull this off? I look at the gap between the plan and what execution really takes.",
  },
];

const WHY_DIFFERENT = [
  {
    number: "01",
    title: "Your data, not generic assumptions",
    body: "Paste your real numbers — revenue, churn, runway, headcount. The council debates your actual situation, not a hypothetical.",
  },
  {
    number: "02",
    title: "Adversarial by design",
    body: "Five specialists are forced to disagree. The Risk Hunter's job is to kill the idea. The Strategist's job is to defend it. You get both sides stress-tested.",
  },
  {
    number: "03",
    title: "A verdict you can show your board",
    body: "Structured PROCEED / CONDITIONAL / DO NOT PROCEED with confidence score, conditions, and dissenting opinion. A paper trail ChatGPT can't produce.",
  },
];

type Stage = "pick" | "context" | "form" | "debate" | "result";

export default function Home() {
  const [stage, setStage] = useState<Stage>("pick");
  const [selectedTemplate, setSelectedTemplate] = useState<Template | null>(null);
  const [companyContext, setCompanyContext] = useState<string>("");
  const [debateId, setDebateId] = useState<string | null>(null);
  const [result, setResult] = useState<DebateResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSelectTemplate = (id: string) => {
    const tmpl = TEMPLATES.find((t) => t.id === id);
    if (tmpl) {
      setSelectedTemplate(tmpl);
      setStage("context");
    }
  };

  const handleContextDone = (ctx: string) => {
    setCompanyContext(ctx);
    setStage("form");
  };

  const handleSubmit = async (fields: Record<string, string>) => {
    if (!selectedTemplate) return;
    setLoading(true);
    setError(null);
    try {
      // Inject company context into the decision fields
      const enrichedFields = companyContext
        ? { ...fields, company_context: companyContext }
        : fields;
      const resp = await startDebate(selectedTemplate.id, enrichedFields);
      setDebateId(resp.id);
      setStage("debate");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to start debate");
    } finally {
      setLoading(false);
    }
  };

  const handleComplete = useCallback((res: DebateResult) => {
    setResult(res);
    setStage("result");
  }, []);

  const handleReset = () => {
    setStage("pick");
    setSelectedTemplate(null);
    setDebateId(null);
    setResult(null);
    setError(null);
  };

  return (
    <div className="relative flex min-h-screen flex-col bg-[#FAFAF7]">
      {/* Subtle warm grid */}
      <div className="pointer-events-none fixed inset-0 z-0 dot-grid opacity-60" />

      {/* Nav */}
      <header className="relative z-50 border-b border-[#E8E0CC] bg-[#FAFAF7]/90 px-6 py-4 backdrop-blur-md">
        <div className="mx-auto flex max-w-6xl items-center justify-between">
          <button
            type="button"
            onClick={handleReset}
            className="group flex items-center gap-3 text-left"
          >
            <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl border-2 border-[#C49A1A] bg-[#FFBF00]">
              <span className="font-serif text-sm font-bold text-[#2C1810]">v</span>
            </div>
            <div className="flex min-w-0 flex-col items-start leading-none">
              <span className="font-serif text-base font-bold tracking-tight text-[#2C1810]">verd</span>
              <span className="text-[9px] uppercase tracking-[0.2em] text-[#9A8060]" style={{ fontFamily: "var(--font-dm-mono)" }}>
                Decision Council
              </span>
            </div>
          </button>

          {/* Breadcrumb for sub-stages */}
          {stage !== "pick" && (
            <motion.div
              className="hidden items-center gap-2 text-sm text-[#9A8060] sm:flex"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
            >
              <button onClick={handleReset} className="hover:text-[#2C1810] transition-colors">
                Decisions
              </button>
              <ChevronRight className="h-3.5 w-3.5" />
              <span className="text-[#2C1810]">
                {stage === "context" ? "Company Context" :
                 stage === "form" ? selectedTemplate?.label :
                 stage === "debate" ? "In Session" : "Verdict"}
              </span>
            </motion.div>
          )}

          <a
            href="https://github.com/manaskarra/verd"
            className="text-xs text-[#9A8060] transition-colors hover:text-[#2C1810]"
            target="_blank"
            rel="noreferrer"
            style={{ fontFamily: "var(--font-dm-mono)" }}
          >
            GitHub ↗
          </a>
        </div>
      </header>

      <main className="relative z-10 flex-1">
        <AnimatePresence mode="wait">
          {/* ── PICK STAGE ── */}
          {stage === "pick" && (
            <motion.div
              key="pick"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0, y: -16 }}
              transition={{ duration: 0.4 }}
            >
              {/* Hero */}
              <section className="relative overflow-hidden border-b border-[#E8E0CC] bg-[#FAFAF7] px-6 pb-20 pt-24">
                {/* Warm amber glow top-right */}
                <div className="pointer-events-none absolute right-0 top-0 h-[480px] w-[480px] translate-x-1/3 -translate-y-1/4 rounded-full bg-[#FFBF00]/20 blur-[120px]" />
                <div className="pointer-events-none absolute bottom-0 left-0 h-[300px] w-[300px] -translate-x-1/3 translate-y-1/3 rounded-full bg-[#007EFF]/10 blur-[100px]" />

                <div className="relative mx-auto max-w-5xl">
                  {/* Eyebrow */}
                  <motion.div
                    className="mb-6 inline-flex items-center gap-2.5 rounded-full border border-[#FFBF00]/40 bg-[#FFBF00]/10 px-4 py-1.5"
                    initial={{ opacity: 0, y: 12 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ delay: 0.1 }}
                  >
                    <span className="h-1.5 w-1.5 rounded-full bg-[#C49A1A]" />
                    <span className="text-xs font-medium uppercase tracking-[0.2em] text-[#7A6010]" style={{ fontFamily: "var(--font-dm-mono)" }}>
                      AI Decision Council
                    </span>
                  </motion.div>

                  {/* Headline */}
                  <motion.h1
                    className="max-w-3xl text-5xl font-bold leading-[1.1] tracking-tight text-[#2C1810] sm:text-6xl lg:text-7xl"
                    style={{ fontFamily: "var(--font-playfair)" }}
                    initial={{ opacity: 0, y: 16 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ delay: 0.15, duration: 0.6 }}
                  >
                    Your biggest decisions deserve more than{" "}
                    <em className="italic text-[#C49A1A]">one opinion.</em>
                  </motion.h1>

                  <motion.p
                    className="mt-6 max-w-2xl text-lg leading-relaxed text-[#6B5040]"
                    initial={{ opacity: 0, y: 12 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ delay: 0.25 }}
                  >
                    Paste your company numbers. Five specialist AI advisors debate your decision across three rounds — surfacing risks ChatGPT won't, producing a board-ready verdict in minutes.
                  </motion.p>

                  <motion.button
                    className="mt-10 inline-flex items-center gap-3 rounded-2xl bg-[#2C1810] px-8 py-4 text-base font-semibold text-[#FAFAF7] transition-all hover:bg-[#3D2418] hover:shadow-lg hover:shadow-[#2C1810]/15"
                    initial={{ opacity: 0, y: 12 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ delay: 0.35 }}
                    onClick={() => document.getElementById("scenarios")?.scrollIntoView({ behavior: "smooth" })}
                  >
                    Bring your decision
                    <ArrowRight className="h-4 w-4" />
                  </motion.button>
                </div>
              </section>

              {/* Why different */}
              <section className="border-b border-[#E8E0CC] px-6 py-16">
                <div className="mx-auto max-w-5xl">
                  <div className="grid grid-cols-1 gap-8 sm:grid-cols-3">
                    {WHY_DIFFERENT.map((item, i) => (
                      <motion.div
                        key={item.number}
                        className="space-y-3"
                        initial={{ opacity: 0, y: 16 }}
                        animate={{ opacity: 1, y: 0 }}
                        transition={{ delay: 0.4 + i * 0.1 }}
                      >
                        <span className="text-sm font-medium text-[#FFBF00]" style={{ fontFamily: "var(--font-dm-mono)" }}>
                          {item.number}
                        </span>
                        <h3 className="text-base font-semibold text-[#2C1810]">{item.title}</h3>
                        <p className="text-sm leading-relaxed text-[#6B5040]">{item.body}</p>
                      </motion.div>
                    ))}
                  </div>
                </div>
              </section>

              {/* Meet the Council */}
              <section className="border-b border-[#E8E0CC] bg-[#FAFAF7] px-6 py-16">
                <div className="mx-auto max-w-5xl">
                  <motion.div
                    className="mb-10"
                    initial={{ opacity: 0, y: 12 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ delay: 0.45 }}
                  >
                    <p className="mb-1 text-xs font-medium uppercase tracking-[0.2em] text-[#9A8060]" style={{ fontFamily: "var(--font-dm-mono)" }}>
                      The advisory council
                    </p>
                    <h2 className="text-3xl font-bold text-[#2C1810]" style={{ fontFamily: "var(--font-playfair)" }}>
                      Five specialists. Forced to disagree.
                    </h2>
                    <p className="mt-3 max-w-xl text-sm leading-relaxed text-[#6B5040]">
                      Each advisor brings a distinct lens. They debate independently, challenge each other across rounds, and vote on your outcome.
                    </p>
                  </motion.div>

                  <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-5">
                    {COUNCIL.map((advisor, i) => (
                      <motion.div
                        key={advisor.role}
                        className="group relative overflow-hidden rounded-2xl border border-[#E8E0CC] bg-white p-5"
                        initial={{ opacity: 0, y: 20 }}
                        animate={{ opacity: 1, y: 0 }}
                        transition={{ delay: 0.5 + i * 0.07, duration: 0.4 }}
                        whileHover={{ y: -2 }}
                      >
                        {/* Hover color wash */}
                        <div
                          className="pointer-events-none absolute inset-0 opacity-0 transition-opacity duration-300 group-hover:opacity-100"
                          style={{ background: `linear-gradient(135deg, ${advisor.color}0C 0%, transparent 60%)` }}
                        />
                        {/* Top bar accent */}
                        <div className="mb-4 h-0.5 w-8 rounded-full" style={{ backgroundColor: advisor.color }} />
                        {/* Avatar */}
                        <div
                          className="mb-3 flex h-10 w-10 items-center justify-center rounded-full text-sm font-bold"
                          style={{
                            border: `1.5px solid ${advisor.color}`,
                            color: advisor.color,
                            backgroundColor: `${advisor.color}12`,
                          }}
                        >
                          {advisor.name[0]}
                        </div>
                        {/* Name + role */}
                        <p className="text-sm font-bold leading-tight text-[#2C1810]">{advisor.name}</p>
                        <p className="mt-0.5 text-xs font-medium leading-tight" style={{ color: advisor.color }}>{advisor.title}</p>
                        <p className="mt-0.5 text-[10px] uppercase tracking-[0.15em] text-[#9A8060]" style={{ fontFamily: "var(--font-dm-mono)" }}>
                          {advisor.subtitle}
                        </p>
                        {/* One-liner */}
                        <p className="mt-3 text-xs leading-relaxed text-[#6B5040]">{advisor.oneliner}</p>
                      </motion.div>
                    ))}
                  </div>
                </div>
              </section>

              {/* Template picker */}
              <section id="scenarios" className="px-6 py-16">
                <div className="mx-auto max-w-5xl">
                  <motion.div
                    className="mb-10"
                    initial={{ opacity: 0, y: 12 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ delay: 0.5 }}
                  >
                    <p className="mb-1 text-xs font-medium uppercase tracking-[0.2em] text-[#9A8060]" style={{ fontFamily: "var(--font-dm-mono)" }}>
                      Choose a scenario
                    </p>
                    <h2
                      className="text-3xl font-bold text-[#2C1810]"
                      style={{ fontFamily: "var(--font-playfair)" }}
                    >
                      What are you deciding?
                    </h2>
                  </motion.div>
                  <TemplatePicker templates={TEMPLATES} onSelect={handleSelectTemplate} />
                </div>
              </section>
            </motion.div>
          )}

          {/* ── COMPANY CONTEXT STAGE ── */}
          {stage === "context" && (
            <motion.div
              key="context"
              className="px-6 py-16"
              initial={{ opacity: 0, x: 30 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: -30 }}
              transition={{ duration: 0.35 }}
            >
              <CompanyContext
                savedContext={companyContext}
                onContinue={handleContextDone}
                onBack={() => setStage("pick")}
              />
            </motion.div>
          )}

          {/* ── FORM STAGE ── */}
          {stage === "form" && selectedTemplate && (
            <motion.div
              key="form"
              className="px-6 py-16"
              initial={{ opacity: 0, x: 30 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: -30 }}
              transition={{ duration: 0.35 }}
            >
              <DebateForm
                template={selectedTemplate}
                companyContext={companyContext}
                onSubmit={handleSubmit}
                onBack={() => setStage("context")}
                loading={loading}
              />
            </motion.div>
          )}

          {/* ── DEBATE STAGE ── */}
          {stage === "debate" && debateId && (
            <motion.div
              key="debate"
              className="px-6 py-16"
              initial={{ opacity: 0, scale: 0.98 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.4 }}
            >
              <LiveDebate debateId={debateId} onComplete={handleComplete} />
            </motion.div>
          )}

          {/* ── RESULT STAGE ── */}
          {stage === "result" && result && (
            <motion.div
              key="result"
              className="px-6 py-16"
              initial={{ opacity: 0, y: 24 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.5 }}
            >
              <VerdictCard result={result} onReset={handleReset} />
            </motion.div>
          )}
        </AnimatePresence>

        {error && (
          <div className="px-6 pb-8 text-center text-sm text-red-600">{error}</div>
        )}
      </main>

      <footer className="relative z-10 border-t border-[#E8E0CC] bg-[#FAFAF7] px-6 py-6">
        <div className="mx-auto flex max-w-6xl flex-col items-center gap-3 sm:flex-row sm:justify-between">
          <div className="flex items-center gap-2.5">
            <div className="flex h-6 w-6 items-center justify-center rounded-lg border-2 border-[#C49A1A] bg-[#FFBF00]">
              <span className="font-serif text-[10px] font-bold text-[#2C1810]">v</span>
            </div>
            <span className="text-xs text-[#9A8060]">verd — AI Decision Council</span>
          </div>
          <span className="text-xs text-[#B0A090]">&copy; {new Date().getFullYear()} verd</span>
        </div>
      </footer>
    </div>
  );
}
