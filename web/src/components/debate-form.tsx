"use client";

import { useState } from "react";
import { motion } from "motion/react";
import { ArrowLeft, Play } from "lucide-react";
import type { Template } from "@/lib/api";

export function DebateForm({
  template,
  companyContext,
  onSubmit,
  onBack,
  loading,
}: {
  template: Template;
  companyContext: string;
  onSubmit: (fields: Record<string, string>) => void;
  onBack: () => void;
  loading: boolean;
}) {
  const [values, setValues] = useState<Record<string, string>>({});

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    onSubmit(values);
  };

  const isValid = template.fields.some(
    (f) => f.name === "decision" && values[f.name]?.trim()
  );

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
        Back
      </motion.button>

      <motion.div
        className="overflow-hidden rounded-3xl border border-[#E8E0CC] bg-white shadow-sm shadow-[#2C1810]/5"
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.4, delay: 0.05 }}
      >
        {/* Header */}
        <div className="border-b border-[#E8E0CC] bg-[#FFFDF5] px-8 py-6">
          <p className="mb-1 text-xs font-medium uppercase tracking-[0.18em] text-[#9A8060]" style={{ fontFamily: "var(--font-dm-mono)" }}>
            Step 2 of 2
          </p>
          <h2 className="text-xl font-bold text-[#2C1810]" style={{ fontFamily: "var(--font-playfair)" }}>
            {template.label}
          </h2>
          <p className="mt-1 text-sm text-[#6B5040]">{template.description}</p>

          {/* Company context indicator */}
          {companyContext && (
            <div className="mt-3 flex items-center gap-2 rounded-lg border border-[#FFBF00]/30 bg-[#FFBF00]/8 px-3 py-2">
              <span className="h-1.5 w-1.5 rounded-full bg-[#C49A1A]" />
              <span className="text-xs text-[#7A6010]">Company context loaded — council will cite your numbers</span>
            </div>
          )}
        </div>

        {/* Form */}
        <form onSubmit={handleSubmit} className="px-8 py-7">
          <div className="space-y-5">
            {template.fields.map((field, i) => (
              <motion.div
                key={field.name}
                className="space-y-1.5"
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.3, delay: 0.15 + i * 0.04 }}
              >
                <label
                  htmlFor={field.name}
                  className="block text-sm font-medium text-[#2C1810]"
                >
                  {field.label}
                </label>
                {field.type === "textarea" ? (
                  <textarea
                    id={field.name}
                    placeholder={field.placeholder}
                    value={values[field.name] || ""}
                    onChange={(e) => setValues((v) => ({ ...v, [field.name]: e.target.value }))}
                    rows={3}
                    className="w-full resize-none rounded-xl border border-[#E8E0CC] bg-[#FAFAF7] px-4 py-3 text-sm text-[#2C1810] placeholder:text-[#B0A090] focus:border-[#FFBF00] focus:outline-none focus:ring-2 focus:ring-[#FFBF00]/20 transition-all"
                  />
                ) : (
                  <input
                    id={field.name}
                    type="text"
                    placeholder={field.placeholder}
                    value={values[field.name] || ""}
                    onChange={(e) => setValues((v) => ({ ...v, [field.name]: e.target.value }))}
                    className="w-full rounded-xl border border-[#E8E0CC] bg-[#FAFAF7] px-4 py-3 text-sm text-[#2C1810] placeholder:text-[#B0A090] focus:border-[#FFBF00] focus:outline-none focus:ring-2 focus:ring-[#FFBF00]/20 transition-all"
                  />
                )}
              </motion.div>
            ))}
          </div>

          <motion.div
            className="mt-8"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ delay: 0.4 }}
          >
            <button
              type="submit"
              disabled={!isValid || loading}
              className="flex w-full items-center justify-center gap-2.5 rounded-xl bg-[#2C1810] px-6 py-4 text-sm font-semibold text-[#FAFAF7] transition-all hover:bg-[#3D2418] hover:shadow-lg hover:shadow-[#2C1810]/15 disabled:cursor-not-allowed disabled:opacity-40"
            >
              {loading ? (
                <>
                  <span className="h-4 w-4 animate-spin rounded-full border-2 border-[#FAFAF7]/30 border-t-[#FAFAF7]" />
                  Convening council...
                </>
              ) : (
                <>
                  <Play className="h-4 w-4" />
                  Convene the Council
                </>
              )}
            </button>
            <p className="mt-3 text-center text-xs text-[#9A8060]">
              5 AI advisors · 3 debate rounds · ~3–5 minutes
            </p>
          </motion.div>
        </form>
      </motion.div>
    </div>
  );
}
