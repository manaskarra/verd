"use client";

import { useState } from "react";
import { motion } from "motion/react";
import { ArrowLeft, ArrowRight, Building2 } from "lucide-react";

const PROMPTS = [
  "Monthly revenue and growth rate",
  "Headcount and key team gaps",
  "Current cash runway or budget",
  "Main competitors and market position",
  "Biggest constraint right now",
];

export function CompanyContext({
  savedContext,
  onContinue,
  onBack,
}: {
  savedContext: string;
  onContinue: (ctx: string) => void;
  onBack: () => void;
}) {
  const [value, setValue] = useState(savedContext);

  return (
    <div className="mx-auto w-full max-w-2xl">
      {/* Back */}
      <motion.button
        onClick={onBack}
        className="mb-8 flex items-center gap-2 text-sm text-[#9A8060] transition-colors hover:text-[#2C1810]"
        initial={{ opacity: 0, x: -8 }}
        animate={{ opacity: 1, x: 0 }}
      >
        <ArrowLeft className="h-4 w-4" />
        Back to scenarios
      </motion.button>

      <motion.div
        className="overflow-hidden rounded-3xl border border-[#E8E0CC] bg-white shadow-sm shadow-[#2C1810]/5"
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.4, delay: 0.05 }}
      >
        {/* Header */}
        <div className="border-b border-[#E8E0CC] bg-[#FFFDF5] px-8 py-7">
          <div className="mb-4 flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-xl border border-[#FFBF00]/40 bg-[#FFBF00]/15">
              <Building2 className="h-5 w-5 text-[#C49A1A]" />
            </div>
            <div>
              <p className="text-xs font-medium uppercase tracking-[0.18em] text-[#9A8060]" style={{ fontFamily: "var(--font-dm-mono)" }}>
                Step 1 of 2
              </p>
              <h2 className="text-xl font-bold text-[#2C1810]" style={{ fontFamily: "var(--font-playfair)" }}>
                Give the council your numbers
              </h2>
            </div>
          </div>
          <p className="text-sm leading-relaxed text-[#6B5040]">
            This is what separates verd from a generic AI. Paste the key facts about your company — the council will cite them directly when debating your decision.
          </p>
        </div>

        <div className="px-8 py-7">
          {/* Hint chips */}
          <div className="mb-4">
            <p className="mb-2.5 text-xs font-medium text-[#9A8060]">Include things like:</p>
            <div className="flex flex-wrap gap-2">
              {PROMPTS.map((p) => (
                <span
                  key={p}
                  className="rounded-full border border-[#E8E0CC] bg-[#FAFAF7] px-3 py-1 text-xs text-[#6B5040]"
                >
                  {p}
                </span>
              ))}
            </div>
          </div>

          <textarea
            value={value}
            onChange={(e) => setValue(e.target.value)}
            rows={8}
            placeholder={`Example:\n\nWe're a B2B SaaS company in Dubai, 3 years old, AED 220,000 MRR growing 12% MoM. 18 employees. 11 months runway at current burn (AED 180,000/month). Main competitor is Competitor X at 3x our price. Our biggest weakness is sales — founder-led so far. We serve 340 paying clients, 4% monthly churn.`}
            className="w-full resize-none rounded-xl border border-[#E8E0CC] bg-[#FAFAF7] p-4 text-sm leading-relaxed text-[#2C1810] placeholder:text-[#B0A090] focus:border-[#FFBF00] focus:outline-none focus:ring-2 focus:ring-[#FFBF00]/20 transition-all"
          />

          <div className="mt-3 flex items-start gap-2 rounded-xl border border-[#FFBF00]/25 bg-[#FFBF00]/8 px-4 py-3">
            <span className="mt-0.5 text-[#C49A1A]">ℹ</span>
            <p className="text-xs leading-relaxed text-[#7A6010]">
              You can skip this and the council will still debate your question — but the verdict will be less specific to your situation. You only need to paste this once per session.
            </p>
          </div>

          <div className="mt-6 flex gap-3">
            <button
              onClick={() => onContinue("")}
              className="rounded-xl border border-[#E8E0CC] bg-white px-5 py-3 text-sm font-medium text-[#9A8060] transition-colors hover:border-[#D0C8B4] hover:text-[#6B5040]"
            >
              Skip for now
            </button>
            <button
              onClick={() => onContinue(value)}
              className="flex flex-1 items-center justify-center gap-2.5 rounded-xl bg-[#2C1810] px-6 py-3 text-sm font-semibold text-[#FAFAF7] transition-all hover:bg-[#3D2418]"
            >
              Continue to decision
              <ArrowRight className="h-4 w-4" />
            </button>
          </div>
        </div>
      </motion.div>
    </div>
  );
}
