"use client";

import { motion } from "motion/react";
import { MapPin, Tag, Rocket, UserPlus, Handshake, MessageCircle, ArrowRight } from "lucide-react";

const ICON_MAP: Record<string, React.ElementType> = {
  "map-pin": MapPin,
  tag: Tag,
  rocket: Rocket,
  "user-plus": UserPlus,
  handshake: Handshake,
  "message-circle": MessageCircle,
};

const ACCENTS = [
  { border: "#FFBF00", bg: "#FFFBEA", icon: "#C49A1A", text: "#7A6010" },
  { border: "#007EFF", bg: "#EBF4FF", icon: "#0060CC", text: "#004499" },
  { border: "#8B5CF6", bg: "#F3EEFF", icon: "#7040D0", text: "#5030A0" },
  { border: "#F43F5E", bg: "#FFF0F3", icon: "#C0203C", text: "#901030" },
  { border: "#10B981", bg: "#EDFAF4", icon: "#0A9060", text: "#066040" },
  { border: "#6B5040", bg: "#F7F4F0", icon: "#4A3428", text: "#3A2418" },
];

interface TemplateInfo {
  id: string;
  label: string;
  description: string;
  icon: string;
}

export function TemplatePicker({
  templates,
  onSelect,
}: {
  templates: TemplateInfo[];
  onSelect: (id: string) => void;
}) {
  return (
    <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
      {templates.map((t, i) => {
        const Icon = ICON_MAP[t.icon] || MessageCircle;
        const accent = ACCENTS[i % ACCENTS.length];

        return (
          <motion.button
            key={t.id}
            onClick={() => onSelect(t.id)}
            className="group relative cursor-pointer overflow-hidden rounded-2xl border bg-white p-6 text-left shadow-sm shadow-[#2C1810]/4 transition-all hover:-translate-y-0.5 hover:shadow-md hover:shadow-[#2C1810]/8"
            style={{ borderColor: "#E8E0CC" }}
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.35, delay: 0.05 + i * 0.05 }}
            whileTap={{ scale: 0.99 }}
          >
            {/* Hover accent fill */}
            <div
              className="pointer-events-none absolute inset-0 opacity-0 transition-opacity duration-300 group-hover:opacity-100"
              style={{ background: `linear-gradient(135deg, ${accent.bg} 0%, white 100%)` }}
            />
            {/* Hover border color */}
            <div
              className="pointer-events-none absolute inset-0 rounded-2xl border-2 opacity-0 transition-opacity duration-300 group-hover:opacity-100"
              style={{ borderColor: accent.border }}
            />

            <div className="relative">
              {/* Icon */}
              <div
                className="mb-4 flex h-11 w-11 items-center justify-center rounded-xl border transition-all duration-300 group-hover:scale-105"
                style={{
                  borderColor: `${accent.border}40`,
                  backgroundColor: accent.bg,
                  color: accent.icon,
                }}
              >
                <Icon className="h-5 w-5" />
              </div>

              {/* Text */}
              <h3 className="mb-1.5 text-sm font-semibold leading-snug text-[#2C1810]">
                {t.label}
              </h3>
              <p className="text-xs leading-relaxed text-[#9A8060]">{t.description}</p>

              {/* Arrow */}
              <div className="mt-4 flex items-center gap-1 opacity-0 transition-all duration-300 group-hover:opacity-100">
                <span className="text-xs font-medium" style={{ color: accent.icon }}>
                  Select
                </span>
                <ArrowRight className="h-3.5 w-3.5 transition-transform duration-300 group-hover:translate-x-0.5" style={{ color: accent.icon }} />
              </div>
            </div>
          </motion.button>
        );
      })}
    </div>
  );
}
