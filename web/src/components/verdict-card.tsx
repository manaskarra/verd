"use client";

import { useState } from "react";
import { motion, AnimatePresence } from "motion/react";
import { CheckCircle2, AlertTriangle, XCircle, Lightbulb, Shield, Target, HelpCircle, RotateCcw, ChevronRight, Sparkles } from "lucide-react";
import type { DebateResult } from "@/lib/api";

const VERDICT_CONFIG: Record<string, { icon: React.ElementType; color: string; bg: string; border: string; label: string; sublabel: string }> = {
  PROCEED: {
    icon: CheckCircle2,
    color: "#0A7040",
    bg: "#EDFAF4",
    border: "#10B981",
    label: "PROCEED",
    sublabel: "Council recommends moving forward",
  },
  PROCEED_WITH_CONDITIONS: {
    icon: AlertTriangle,
    color: "#0060CC",
    bg: "#EBF4FF",
    border: "#007EFF",
    label: "CONDITIONAL",
    sublabel: "Proceed only with specific requirements met",
  },
  DO_NOT_PROCEED: {
    icon: XCircle,
    color: "#C0203C",
    bg: "#FFF0F3",
    border: "#F43F5E",
    label: "DO NOT PROCEED",
    sublabel: "Council recommends against this decision",
  },
};

const VOTE_STYLES: Record<string, { color: string; bg: string; border: string }> = {
  PROCEED: { color: "#0A7040", bg: "#EDFAF4", border: "#10B98140" },
  PROCEED_WITH_CONDITIONS: { color: "#0060CC", bg: "#EBF4FF", border: "#007EFF40" },
  DO_NOT_PROCEED: { color: "#C0203C", bg: "#FFF0F3", border: "#F43F5E40" },
};

const TABS = [
  { id: "opportunities", label: "Opportunities", icon: Target },
  { id: "risks", label: "Risks", icon: Shield },
  { id: "conditions", label: "Conditions", icon: CheckCircle2 },
  { id: "whatif", label: "What-If", icon: HelpCircle },
] as const;

type TabId = (typeof TABS)[number]["id"];

export function VerdictCard({ result, onReset }: { result: DebateResult; onReset: () => void }) {
  const [activeTab, setActiveTab] = useState<TabId>("opportunities");
  const config = VERDICT_CONFIG[result.verdict] || VERDICT_CONFIG.DO_NOT_PROCEED;
  const Icon = config.icon;
  const pct = Math.round(result.confidence * 100);

  const tabContent: Record<TabId, string[]> = {
    opportunities: result.opportunities || [],
    risks: result.risks || [],
    conditions: result.conditions || [],
    whatif: result.what_if_suggestions || [],
  };

  return (
    <div className="mx-auto max-w-4xl space-y-5">
      {/* Verdict header */}
      <motion.div
        className="overflow-hidden rounded-3xl border-2 shadow-md"
        style={{ borderColor: config.border, backgroundColor: config.bg, boxShadow: `0 4px 24px ${config.border}20` }}
        initial={{ opacity: 0, scale: 0.97, y: 20 }}
        animate={{ opacity: 1, scale: 1, y: 0 }}
        transition={{ duration: 0.5, ease: [0.16, 1, 0.3, 1] }}
      >
        <div className="p-8 sm:p-10">
          <p className="mb-5 text-xs font-medium uppercase tracking-[0.25em] text-[#9A8060]" style={{ fontFamily: "var(--font-dm-mono)" }}>
            Council Verdict
          </p>

          <div className="flex flex-col gap-6 sm:flex-row sm:items-start sm:justify-between">
            <div className="flex items-start gap-5">
              <motion.div
                className="flex h-16 w-16 shrink-0 items-center justify-center rounded-2xl border-2 bg-white"
                style={{ borderColor: config.border }}
                initial={{ scale: 0, rotate: -12 }}
                animate={{ scale: 1, rotate: 0 }}
                transition={{ delay: 0.2, type: "spring", stiffness: 220, damping: 18 }}
              >
                <Icon className="h-8 w-8" style={{ color: config.color }} />
              </motion.div>
              <div>
                <motion.h2
                  className="text-3xl font-bold tracking-tight"
                  style={{ color: config.color, fontFamily: "var(--font-playfair)" }}
                  initial={{ opacity: 0, x: -10 }}
                  animate={{ opacity: 1, x: 0 }}
                  transition={{ delay: 0.25 }}
                >
                  {config.label}
                </motion.h2>
                <p className="mt-0.5 text-sm" style={{ color: config.color + "99" }}>{config.sublabel}</p>
                <motion.p
                  className="mt-3 text-base leading-relaxed text-[#2C1810]"
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  transition={{ delay: 0.35 }}
                >
                  {result.headline}
                </motion.p>
              </div>
            </div>

            {/* Confidence */}
            <motion.div
              className="flex shrink-0 flex-col items-center gap-2 rounded-2xl border border-[#E8E0CC] bg-white px-6 py-4"
              initial={{ opacity: 0, scale: 0.85 }}
              animate={{ opacity: 1, scale: 1 }}
              transition={{ delay: 0.3, type: "spring" }}
            >
              <span className="text-xs font-medium uppercase tracking-[0.18em] text-[#9A8060]" style={{ fontFamily: "var(--font-dm-mono)" }}>
                Confidence
              </span>
              <span className="text-4xl font-bold" style={{ color: config.color, fontFamily: "var(--font-playfair)" }}>
                {pct}%
              </span>
              <div className="h-1.5 w-28 overflow-hidden rounded-full bg-[#E8E0CC]">
                <motion.div
                  className="h-full rounded-full"
                  style={{ backgroundColor: config.color }}
                  initial={{ width: 0 }}
                  animate={{ width: `${pct}%` }}
                  transition={{ delay: 0.5, duration: 0.7, ease: "easeOut" }}
                />
              </div>
            </motion.div>
          </div>
        </div>
      </motion.div>

      {/* Two-column: votes + insights */}
      <div className="grid gap-4 sm:grid-cols-2">
        {/* Advisory panel votes */}
        <motion.div
          className="rounded-2xl border border-[#E8E0CC] bg-white p-6 shadow-sm"
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.45 }}
        >
          <div className="mb-4 flex items-center gap-2">
            <Sparkles className="h-4 w-4 text-[#C49A1A]" />
            <span className="text-xs font-medium uppercase tracking-[0.18em] text-[#9A8060]" style={{ fontFamily: "var(--font-dm-mono)" }}>
              Advisory Panel
            </span>
          </div>
          <div className="space-y-2">
            {Object.entries(result.model_votes || {}).map(([model, vote], i) => {
              const vs = VOTE_STYLES[vote] || { color: "#6B5040", bg: "#F7F4F0", border: "#E8E0CC" };
              // model key is now a role title (e.g. "Strategist") — use directly
              // fall back to model_titles lookup for backward compat, then slug cleanup
              const name = result.model_titles?.[model]
                ?? model;
              return (
                <motion.div
                  key={model}
                  className="flex items-center justify-between rounded-lg border px-3 py-2.5"
                  style={{ backgroundColor: vs.bg, borderColor: vs.border }}
                  initial={{ opacity: 0, x: -10 }}
                  animate={{ opacity: 1, x: 0 }}
                  transition={{ delay: 0.5 + i * 0.06 }}
                >
                  <span className="text-xs font-medium text-[#2C1810]">{name}</span>
                  <span className="text-xs font-semibold uppercase tracking-wide" style={{ color: vs.color, fontFamily: "var(--font-dm-mono)" }}>
                    {vote.replace(/_/g, " ")}
                  </span>
                </motion.div>
              );
            })}
          </div>
          {result.consensus && (
            <p className="mt-3 text-xs leading-relaxed text-[#9A8060]">{result.consensus}</p>
          )}
        </motion.div>

        {/* Key insights */}
        {result.unique_catches && result.unique_catches.length > 0 && (
          <motion.div
            className="rounded-2xl border border-[#E8E0CC] bg-white p-6 shadow-sm"
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.5 }}
          >
            <div className="mb-4 flex items-center gap-2">
              <Lightbulb className="h-4 w-4 text-[#C49A1A]" />
              <span className="text-xs font-medium uppercase tracking-[0.18em] text-[#9A8060]" style={{ fontFamily: "var(--font-dm-mono)" }}>
                Key Insights
              </span>
            </div>
            <ul className="space-y-3">
              {result.unique_catches.map((c, i) => (
                <motion.li
                  key={i}
                  className="flex items-start gap-2.5 text-sm text-[#2C1810]"
                  initial={{ opacity: 0, x: -8 }}
                  animate={{ opacity: 1, x: 0 }}
                  transition={{ delay: 0.55 + i * 0.05 }}
                >
                  <ChevronRight className="mt-0.5 h-4 w-4 shrink-0 text-[#C49A1A]" />
                  <span className="leading-relaxed">{c}</span>
                </motion.li>
              ))}
            </ul>
          </motion.div>
        )}
      </div>

      {/* Tabbed analysis */}
      <motion.div
        className="overflow-hidden rounded-2xl border border-[#E8E0CC] bg-white shadow-sm"
        initial={{ opacity: 0, y: 16 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.55 }}
      >
        <div className="flex border-b border-[#E8E0CC]">
          {TABS.map((tab) => {
            const TabIcon = tab.icon;
            const isActive = activeTab === tab.id;
            return (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id)}
                className="group relative flex flex-1 items-center justify-center gap-1.5 px-3 py-3.5 text-xs font-medium transition-colors"
                style={{ color: isActive ? "#2C1810" : "#9A8060" }}
              >
                {isActive && (
                  <motion.div
                    className="absolute inset-0 bg-[#FFFDF5]"
                    layoutId="tab-bg"
                    transition={{ type: "spring", stiffness: 400, damping: 30 }}
                  />
                )}
                {isActive && (
                  <motion.div
                    className="absolute bottom-0 left-0 h-0.5 w-full bg-[#FFBF00]"
                    layoutId="tab-line"
                    transition={{ type: "spring", stiffness: 400, damping: 30 }}
                  />
                )}
                <TabIcon className="relative h-3.5 w-3.5" />
                <span className="relative">{tab.label}</span>
              </button>
            );
          })}
        </div>
        <div className="p-6">
          <AnimatePresence mode="wait">
            <motion.div
              key={activeTab}
              initial={{ opacity: 0, y: 6 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -6 }}
              transition={{ duration: 0.18 }}
            >
              {tabContent[activeTab].length === 0 ? (
                <p className="text-sm italic text-[#B0A090]">Nothing identified for this category.</p>
              ) : (
                <ul className="space-y-3">
                  {tabContent[activeTab].map((item, i) => (
                    <motion.li
                      key={i}
                      className="flex items-start gap-3 text-sm text-[#2C1810]"
                      initial={{ opacity: 0, x: -8 }}
                      animate={{ opacity: 1, x: 0 }}
                      transition={{ delay: i * 0.04 }}
                    >
                      <span className="mt-2 h-1.5 w-1.5 shrink-0 rounded-full bg-[#FFBF00]" />
                      <span className="leading-relaxed">{item}</span>
                    </motion.li>
                  ))}
                </ul>
              )}
            </motion.div>
          </AnimatePresence>
        </div>
      </motion.div>

      {/* Dissent */}
      {result.dissent && (
        <motion.div
          className="rounded-2xl border border-[#E8E0CC] bg-[#FAFAF7] p-5"
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.65 }}
        >
          <p className="mb-2 text-xs font-medium uppercase tracking-[0.18em] text-[#9A8060]" style={{ fontFamily: "var(--font-dm-mono)" }}>
            Dissenting Opinion
          </p>
          <p className="text-sm leading-relaxed text-[#6B5040] italic">{result.dissent}</p>
        </motion.div>
      )}

      {/* Footer */}
      <motion.div
        className="flex flex-col items-center gap-4 sm:flex-row sm:justify-between"
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ delay: 0.75 }}
      >
        <div className="flex flex-wrap items-center gap-3 text-xs text-[#B0A090]" style={{ fontFamily: "var(--font-dm-mono)" }}>
          <span>{result.elapsed}s</span>
        </div>
        <button
          onClick={onReset}
          className="flex items-center gap-2 rounded-xl border border-[#E8E0CC] bg-white px-5 py-2.5 text-sm font-medium text-[#6B5040] shadow-sm transition-all hover:border-[#D0C8B4] hover:shadow-md"
        >
          <RotateCcw className="h-3.5 w-3.5" />
          New Decision
        </button>
      </motion.div>
    </div>
  );
}
