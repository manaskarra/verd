"use client";

import { useEffect, useRef, useState } from "react";
import { motion, AnimatePresence } from "motion/react";
import { streamDebate, type DebateResult, type SSEEvent } from "@/lib/api";

/** Strip basic markdown formatting from text. */
function stripMd(text: string): string {
  return text
    .replace(/^#{1,6}\s+/gm, "")
    .replace(/\*{1,3}([^*]+)\*{1,3}/g, "$1")
    .replace(/_{1,3}([^_]+)_{1,3}/g, "$1")
    .replace(/`[^`]+`/g, "")
    .replace(/^>\s*/gm, "")
    .replace(/^[\s]*[-*+]\s+/gm, "")
    .replace(/^[\s]*\d+\.\s+/gm, "")
    .replace(/^---+$/gm, "")
    .replace(/\s+/g, " ")
    .trim();
}

/** Extract punchy 4-7 word phrases from a longer text for speech bubbles. */
function extractPhrases(text: string): string[] {
  if (!text) return [];

  // Split on sentence boundaries
  const sentences = stripMd(text)
    .split(/(?<=[.!?])\s+/)
    .map((s) => s.trim())
    .filter((s) => s.length > 10 && s.length < 200);

  const phrases: string[] = [];

  for (const sentence of sentences) {
    const words = sentence.split(/\s+/);
    if (words.length <= 10) {
      // Short enough — use as-is, but cap at ~60 chars
      const short = sentence.slice(0, 60).replace(/[.,;:!?]+$/, "");
      if (short.split(" ").length >= 3) phrases.push(short);
    } else {
      // Take the most punchy chunk: first 6-8 words
      const chunk = words.slice(0, 7).join(" ").replace(/[,;:]+$/, "");
      if (chunk.length > 8) phrases.push(chunk + "…");
    }
  }

  // Deduplicate and limit
  return [...new Set(phrases)].slice(0, 4);
}

type TranscriptLine =
  | { id: string; kind: "narration"; text: string }
  | {
      id: string;
      kind: "advisor";
      title: string;
      round: number;
      text: string;
      role: string;
    }
  | { id: string; kind: "status"; text: string };

function omitStatusFromFeed(msg: string): boolean {
  const m = msg.trim();
  if (m.startsWith("spawning ")) return true;
  if (m.includes("responded, initial positions")) return true;
  if (/^round \d+\/\d+/i.test(m)) return true;
  if (m.includes("delivering verdict")) return true;
  if (m.includes("failed, retrying") || m.includes("trying fallback")) return true;
  return false;
}

const STEPS = [
  "Convening the advisory council",
  "Round I — Opening statements",
  "Round II — Cross-examination",
  "Deliberating verdict",
];

const ADVISORS = [
  {
    role: "strategist",
    name: "Nadia",
    title: "Strategist",
    subtitle: "Market & Revenue",
    color: "#FFBF00",
    glow: "rgba(255,191,0,0.5)",
    shadowColor: "rgba(255,191,0,0.25)",
    initials: "NA",
    angle: 0,
  },
  {
    role: "devils_advocate",
    name: "Marcus",
    title: "Risk Hunter",
    subtitle: "Fatal Flaws",
    color: "#FF4444",
    glow: "rgba(255,68,68,0.5)",
    shadowColor: "rgba(255,68,68,0.25)",
    initials: "MA",
    angle: 72,
  },
  {
    role: "assumption_checker",
    name: "Sofia",
    title: "Assumption Auditor",
    subtitle: "Evidence Review",
    color: "#F59E0B",
    glow: "rgba(245,158,11,0.5)",
    shadowColor: "rgba(245,158,11,0.25)",
    initials: "SO",
    angle: 144,
  },
  {
    role: "fact_checker",
    name: "Cole",
    title: "Market Reality",
    subtitle: "Data Verification",
    color: "#007EFF",
    glow: "rgba(0,126,255,0.5)",
    shadowColor: "rgba(0,126,255,0.25)",
    initials: "CO",
    angle: 216,
  },
  {
    role: "pragmatist",
    name: "Elise",
    title: "Execution Realist",
    subtitle: "Operational Fit",
    color: "#8B5CF6",
    glow: "rgba(139,92,246,0.5)",
    shadowColor: "rgba(139,92,246,0.25)",
    initials: "EL",
    angle: 288,
  },
];

// Convert angle (0 = top, clockwise) to x,y percentage in a square container.
// r is % from center (50,50). Table occupies r=0..25, orbit ring at r=32, seats at r=37.
function angleToPos(angle: number, r = 37) {
  const rad = ((angle - 90) * Math.PI) / 180;
  return {
    x: 50 + r * Math.cos(rad),
    y: 50 + r * Math.sin(rad),
  };
}

function AdvisorSeat({
  advisor,
  active,
  index,
  bubblePhrase,
  bubbleKey,
}: {
  advisor: (typeof ADVISORS)[0];
  active: boolean;
  index: number;
  bubblePhrase?: string | null;
  bubbleKey?: number;
}) {
  const pos = angleToPos(advisor.angle);

  /* IMPORTANT: Orbit point must be the CENTER of the avatar circle only. */
  return (
    <motion.div
      className="absolute overflow-visible"
      style={{
        left: `${pos.x}%`,
        top: `${pos.y}%`,
        width: 64,
        height: 64,
        marginLeft: -32,
        marginTop: -32,
        zIndex: 10,
      }}
      initial={{ opacity: 0, scale: 0.3 }}
      animate={{ opacity: 1, scale: 1 }}
      transition={{ duration: 0.6, delay: 0.4 + index * 0.12, type: "spring", stiffness: 180, damping: 16 }}
    >
      {/* Speech bubble — shown only when this seat is the active speaker */}
      <AnimatePresence mode="wait">
        {bubblePhrase && (
          <motion.div
            key={bubbleKey}
            className="absolute bottom-full left-1/2 z-20 mb-3 -translate-x-1/2"
            style={{ width: "max-content", maxWidth: "min(160px,36vw)" }}
            initial={{ opacity: 0, y: 8, scale: 0.82 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: -5, scale: 0.9 }}
            transition={{ type: "spring", stiffness: 340, damping: 24 }}
          >
            <div
              className="relative rounded-xl border px-2.5 py-1.5 text-center"
              style={{
                borderColor: `${advisor.color}40`,
                backgroundColor: `${advisor.color}0E`,
                boxShadow: `0 4px 18px ${advisor.shadowColor}`,
              }}
            >
              <p
                className="text-[11px] font-semibold leading-snug"
                style={{ color: advisor.color, fontFamily: "var(--font-dm-sans)" }}
              >
                {bubblePhrase}
              </p>
              {/* Tail */}
              <div
                className="absolute left-1/2 top-full -translate-x-1/2"
                style={{
                  width: 0,
                  height: 0,
                  borderLeft: "5px solid transparent",
                  borderRight: "5px solid transparent",
                  borderTop: `5px solid ${advisor.color}40`,
                  marginTop: -1,
                }}
              />
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      <div className="relative h-full w-full">
        {/* Outer pulse ring — always on when active */}
        {active && (
          <>
            <motion.div
              className="pointer-events-none absolute rounded-full"
              style={{
                width: 100,
                height: 100,
                border: `1px solid ${advisor.color}`,
                top: "50%",
                left: "50%",
                transform: "translate(-50%, -50%)",
                opacity: 0,
              }}
              animate={{ scale: [0.7, 1.5], opacity: [0.6, 0] }}
              transition={{ duration: 2, repeat: Infinity, ease: "easeOut" }}
            />
            <motion.div
              className="pointer-events-none absolute rounded-full"
              style={{
                width: 100,
                height: 100,
                border: `1px solid ${advisor.color}`,
                top: "50%",
                left: "50%",
                transform: "translate(-50%, -50%)",
                opacity: 0,
              }}
              animate={{ scale: [0.7, 1.5], opacity: [0.6, 0] }}
              transition={{ duration: 2, repeat: Infinity, ease: "easeOut", delay: 0.7 }}
            />
          </>
        )}

        {/* Glow blob behind circle */}
        {active && (
          <motion.div
            className="pointer-events-none absolute rounded-full"
            style={{
              width: 80,
              height: 80,
              background: `radial-gradient(circle, ${advisor.glow} 0%, transparent 70%)`,
              top: "50%",
              left: "50%",
              transform: "translate(-50%, -50%)",
            }}
            animate={{ scale: [1, 1.3, 1], opacity: [0.8, 0.4, 0.8] }}
            transition={{ duration: 2.5, repeat: Infinity }}
          />
        )}

        {/* Main circle — geometric center = orbit anchor */}
        <motion.div
          className="relative flex h-16 w-16 items-center justify-center rounded-full text-sm font-bold tracking-wide"
          style={{
            border: `2px solid ${active ? advisor.color : "#E8E0CC"}`,
            backgroundColor: active ? `${advisor.color}18` : "#F7F4F0",
            color: active ? advisor.color : "#B0A090",
            boxShadow: active
              ? `0 0 20px ${advisor.shadowColor}, 0 4px 16px ${advisor.shadowColor}`
              : "0 1px 4px rgba(44,24,16,0.08)",
          }}
          animate={active ? { scale: [1, 1.06, 1] } : { scale: 1 }}
          transition={{ duration: 3, repeat: Infinity, ease: "easeInOut" }}
        >
          {advisor.name[0]}

          {active && (
            <motion.span
              className="absolute -right-1 -top-1 h-3.5 w-3.5 rounded-full border-2 border-[#FAFAF7]"
              style={{ backgroundColor: advisor.color }}
              animate={{ scale: [1, 1.3, 1] }}
              transition={{ duration: 1.2, repeat: Infinity }}
            />
          )}
        </motion.div>
      </div>

      {/* Labels sit below the circle; absolute so they do NOT shift the orbit anchor */}
      <div
        className="pointer-events-none absolute left-1/2 top-full z-10 mt-2 w-[110px] -translate-x-1/2 text-center"
      >
        <p
          className="text-[12px] font-bold leading-tight"
          style={{ color: active ? advisor.color : "#B0A090" }}
        >
          {advisor.name}
        </p>
        <p
          className="mt-0.5 text-[10px] font-medium leading-tight"
          style={{ color: active ? advisor.color : "#C0B090", opacity: 0.8 }}
        >
          {advisor.title}
        </p>
        <p className="mt-0.5 text-[9px] leading-tight text-[#9A8060]/50">{advisor.subtitle}</p>
      </div>
    </motion.div>
  );
}

/** Build a flat queue of { role, phrase } items from all quips, shuffled. */
function buildPhraseQueue(
  quips: Record<string, string[]>
): Array<{ role: string; phrase: string }> {
  const items: Array<{ role: string; phrase: string }> = [];
  for (const [role, phrases] of Object.entries(quips)) {
    for (const phrase of phrases) {
      if (phrase) items.push({ role, phrase });
    }
  }
  // Fisher-Yates shuffle
  for (let i = items.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [items[i], items[j]] = [items[j], items[i]];
  }
  return items;
}

function CouncilChamber({
  activeAdvisors,
  step,
  speeches,
  quips,
}: {
  activeAdvisors: Set<string>;
  step: number;
  speeches: Record<string, { text: string; key: number }>;
  quips: Record<string, string[]>;
}) {
  // Single global speaking slot: which role is showing a bubble right now
  const [speakingRole, setSpeakingRole] = useState<string | null>(null);
  const [speakingPhrase, setSpeakingPhrase] = useState<string | null>(null);
  const [bubbleKey, setBubbleKey] = useState(0);
  const queueRef = useRef<Array<{ role: string; phrase: string }>>([]);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Sequential light-up — cycles through advisors one at a time while debate is loading
  // Runs from step 0 (convening) through step 1 (opening), stops once advisors respond
  const [litIndex, setLitIndex] = useState(0);
  const litTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  useEffect(() => {
    if (activeAdvisors.size >= ADVISORS.length) return; // all responded, stop
    function cycle() {
      setLitIndex((i) => (i + 1) % ADVISORS.length);
      litTimerRef.current = setTimeout(cycle, 550 + Math.random() * 300);
    }
    litTimerRef.current = setTimeout(cycle, 300);
    return () => { if (litTimerRef.current) clearTimeout(litTimerRef.current); };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeAdvisors.size]);

  // Rebuild queue whenever quips change
  useEffect(() => {
    queueRef.current = buildPhraseQueue(quips);
  }, [quips]);

  // Drive the single-speaker loop
  useEffect(() => {
    const hasSpeech = Object.keys(quips).length > 0;
    if (!hasSpeech) return;

    function showNext() {
      let item = queueRef.current.shift();
      if (!item) {
        // Refill from quips and try once more, else wait
        queueRef.current = buildPhraseQueue(quips);
        item = queueRef.current.shift();
      }
      if (!item) {
        setSpeakingRole(null);
        setSpeakingPhrase(null);
        timerRef.current = setTimeout(showNext, 1500);
        return;
      }

      setSpeakingRole(item.role);
      setSpeakingPhrase(item.phrase);
      setBubbleKey((k) => k + 1);

      // Show this phrase for 2.2-3.4s, then silent gap of 0.6-1.4s
      const showDuration = 2200 + Math.random() * 1200;
      const gapDuration = 600 + Math.random() * 800;

      timerRef.current = setTimeout(() => {
        setSpeakingRole(null);
        setSpeakingPhrase(null);
        timerRef.current = setTimeout(showNext, gapDuration);
      }, showDuration);
    }

    // Small initial delay then start
    timerRef.current = setTimeout(showNext, 800);

    return () => {
      if (timerRef.current) clearTimeout(timerRef.current);
    };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [Object.keys(quips).join(",")]);

  return (
    // Square container so % x and % y map identically
    <div className="relative mx-auto" style={{ width: "min(560px, 90vw)", height: "min(560px, 90vw)" }}>
      {/* Background ambient glows for the whole chamber */}
      <div className="absolute inset-0 pointer-events-none">
        {ADVISORS.filter((a) => activeAdvisors.has(a.role)).map((advisor) => {
          const pos = angleToPos(advisor.angle);
          return (
            <motion.div
              key={advisor.role}
              className="absolute rounded-full"
              style={{
                width: 180,
                height: 180,
                left: `${pos.x}%`,
                top: `${pos.y}%`,
                transform: "translate(-50%, -50%)",
                background: `radial-gradient(circle, ${advisor.color}18 0%, transparent 70%)`,
                filter: "blur(24px)",
              }}
              animate={{ opacity: [0.5, 1, 0.5] }}
              transition={{ duration: 3 + Math.random() * 2, repeat: Infinity }}
            />
          );
        })}
      </div>

      {/* Table circle */}
      <div
        className="absolute"
        style={{
          left: "25%", top: "25%", right: "25%", bottom: "25%",
          borderRadius: "50%",
          background: "radial-gradient(ellipse at 40% 35%, #FFFDF5 0%, #F5EDD8 100%)",
          border: "2px solid #E8D8A0",
          boxShadow: "0 4px 32px rgba(196,154,26,0.12), inset 0 0 40px rgba(255,191,0,0.06)",
        }}
      />

      {/* Rotating orbit ring */}
      <motion.div
        className="absolute"
        style={{
          left: "21%", top: "21%", right: "21%", bottom: "21%",
          borderRadius: "50%",
          border: "1px dashed rgba(196,154,26,0.20)",
        }}
        animate={{ rotate: 360 }}
        transition={{ duration: 40, repeat: Infinity, ease: "linear" }}
      />


      {/* Center label */}
      <div className="absolute inset-0 flex items-center justify-center">
        <div className="flex flex-col items-center gap-2">
          <motion.div
            className="relative h-8 w-8 rounded-full border border-[#E8D8A0]"
            animate={{ rotate: [0, 90] }}
            transition={{ duration: 10, repeat: Infinity, ease: "linear" }}
          />
          <motion.p
            className="text-[10px] uppercase tracking-[0.28em] text-[#9A8060]"
            style={{ fontFamily: "var(--font-dm-mono)" }}
            animate={{ opacity: [0.4, 0.8, 0.4] }}
            transition={{ duration: 3, repeat: Infinity }}
          >
            Council Chamber
          </motion.p>
          <motion.div
            className="h-px w-10 bg-gradient-to-r from-transparent via-[#C49A1A]/50 to-transparent"
            animate={{ scaleX: [0.6, 1.2, 0.6] }}
            transition={{ duration: 2.5, repeat: Infinity }}
          />
          <p className="text-[9px] uppercase tracking-[0.22em] text-[#B0A090]" style={{ fontFamily: "var(--font-dm-mono)" }}>
            In Session
          </p>
        </div>
      </div>

      {/* Gavel — centered in table when deliberating verdict */}
      <AnimatePresence>
        {step === 3 && (
          <motion.div
            className="absolute pointer-events-none"
            style={{
              left: "50%", top: "50%",
              width: 0, height: 0,
              zIndex: 20,
            }}
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.3 }}
          >
            {/* Ripple rings centered on table */}
            {[0, 0.5].map((delay) => (
              <motion.div
                key={delay}
                className="absolute rounded-full"
                style={{
                  width: 48, height: 48,
                  marginLeft: -24, marginTop: -24,
                  border: "1px solid rgba(196,154,26,0.35)",
                }}
                animate={{ scale: [0.8, 2], opacity: [0.5, 0] }}
                transition={{ duration: 1.4, repeat: Infinity, ease: "easeOut", delay }}
              />
            ))}
            {/* Gavel — drawn horizontally (0° = head pointing right, handle pointing left).
                Pivot is the left tip of the handle (0,0 in SVG space).
                At rest/raised: rotate(-30deg) — head tilted up.
                Strike: rotate(0deg) — gavel flat, head hits table to the right. */}
            <motion.div
              style={{
                position: "absolute",
                marginLeft: -8,
                marginTop: -8,
                transformOrigin: "0px 8px",
              }}
              animate={{ rotate: [-30, 0, -30] }}
              transition={{
                duration: 0.25,
                times: [0, 0.35, 1],
                repeat: Infinity,
                repeatDelay: 1.5,
                ease: ["easeIn", "easeOut"],
              }}
            >
              {/* SVG: handle goes left→right, head at the right end.
                  Total width 48px, height 16px.
                  Handle: thin rect from x=0 to x=32, centered at y=6..10 (height 4).
                  Head: wide block from x=32 to x=48, y=0..16. */}
              <svg width="48" height="16" viewBox="0 0 48 16" fill="none">
                {/* Handle */}
                <rect x="0" y="6" width="32" height="4" rx="2" fill="#C49A1A" opacity="0.9" />
                {/* Head */}
                <rect x="30" y="1" width="18" height="14" rx="3" fill="#C49A1A" />
                {/* Shine */}
                <rect x="32" y="3" width="12" height="4" rx="1.5" fill="rgba(255,245,200,0.4)" />
              </svg>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Advisor seats */}
      {ADVISORS.map((advisor, i) => {
        const isSpeaking = speakingRole === advisor.role;
        const isActive = activeAdvisors.has(advisor.role);
        // Pulse advisors sequentially until they have actually responded
        const isSequentialLit = !isActive && litIndex === i;
        return (
          <AdvisorSeat
            key={advisor.role}
            advisor={advisor}
            active={isActive || isSequentialLit}
            index={i}
            bubblePhrase={isSpeaking ? speakingPhrase : null}
            bubbleKey={isSpeaking ? bubbleKey : undefined}
          />
        );
      })}

    </div>
  );
}

export function LiveDebate({
  debateId,
  onComplete,
}: {
  debateId: string;
  onComplete: (result: DebateResult) => void;
}) {
  const [lines, setLines] = useState<TranscriptLine[]>([]);
  const [speeches, setSpeeches] = useState<Record<string, { text: string; key: number }>>({});
  // quips[role] = array of LLM-generated debate quips for speech bubbles
  const [quips, setQuips] = useState<Record<string, string[]>>({});
  const [showTyping, setShowTyping] = useState(true);
  const [currentStep, setCurrentStep] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const feedRef = useRef<HTMLDivElement>(null);
  const lineIdRef = useRef(0);
  const nextLineId = () => {
    lineIdRef.current += 1;
    return `ln-${lineIdRef.current}`;
  };

  // Track which advisors have actually responded — only light up once their text arrives
  const activeAdvisors = new Set(
    lines
      .filter((l): l is Extract<TranscriptLine, { kind: "advisor" }> => l.kind === "advisor")
      .map((l) => l.role)
  );

  useEffect(() => {
    const cleanup = streamDebate(debateId, (event: SSEEvent) => {
      switch (event.type) {
        case "narration":
          if (event.text) {
            setShowTyping(false);
            const id = nextLineId();
            setLines((prev) => [...prev, { id, kind: "narration", text: event.text! }]);
          }
          break;
        case "advisor": {
          const role = event.role ?? "";
          const excerpt = (event.text || "").trim();
          const title = event.title || "Advisor";
          const round = typeof event.round === "number" ? event.round : 0;
          if (excerpt) {
            setShowTyping(false);
            const id = nextLineId();
            setLines((prev) => [
              ...prev,
              { id, kind: "advisor", title, round, text: excerpt, role },
            ]);
            if (role) {
              setSpeeches((prev) => ({
                ...prev,
                [role]: { text: excerpt, key: (prev[role]?.key ?? 0) + 1 },
              }));
              // Accumulate quips per role — each round brings up to 3 new phrases
              const incoming = (event.quips ?? []).filter((q) => q && q.trim());
              if (incoming.length > 0) {
                setQuips((prev) => ({
                  ...prev,
                  [role]: [...(prev[role] ?? []), ...incoming],
                }));
              }
            }
          }
          break;
        }
        case "status":
          if (event.message?.includes("spawning")) setCurrentStep(0);
          else if (event.message?.includes("initial positions")) setCurrentStep(1);
          else if (event.message?.includes("challenging") || event.message?.includes("pressure") || event.message?.includes("final")) setCurrentStep(2);
          else if (event.message?.includes("verdict") || event.message?.includes("delivering"))
            setCurrentStep(3);
          {
            const msg = event.message;
            if (msg && !omitStatusFromFeed(msg)) {
              const id = nextLineId();
              setLines((prev) => [...prev, { id, kind: "status", text: msg }]);
            }
          }
          break;
        case "complete":
          setShowTyping(false);
          if (event.result) onComplete(event.result);
          break;
        case "error":
          setShowTyping(false);
          setError(event.message || "Debate failed");
          break;
        default:
          break;
      }
    });
    return () => cleanup();
  }, [debateId, onComplete]);

  useEffect(() => {
    feedRef.current?.scrollTo({ top: feedRef.current.scrollHeight, behavior: "smooth" });
  }, [lines]);

  if (error) {
    return (
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        className="mx-auto max-w-2xl rounded-2xl border border-red-200 bg-red-50 p-10 text-center"
      >
        <p className="text-red-600">{error}</p>
      </motion.div>
    );
  }

  return (
    <div className="mx-auto w-full max-w-7xl px-4">
      {/* Top status bar — full width above the split */}
      <motion.div
        className="mb-6 text-center"
        initial={{ opacity: 0, y: -16 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.5 }}
      >
        <p className="text-[11px] uppercase tracking-[0.35em] text-[#9A8060]" style={{ fontFamily: "var(--font-dm-mono)" }}>
          Advisory Council · Live Session
        </p>

        <motion.h2
          key={currentStep}
          className="mt-2 text-2xl font-bold text-[#2C1810]"
          style={{ fontFamily: "var(--font-playfair)" }}
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.4 }}
        >
          {STEPS[currentStep]}
        </motion.h2>

        {/* Step pills */}
        <div className="mt-4 flex items-center justify-center gap-2">
          {STEPS.map((label, i) => (
            <motion.div
              key={i}
              title={label}
              className="h-1.5 rounded-full transition-all duration-700"
              style={{
                width: i === currentStep ? 36 : 8,
                backgroundColor: i <= currentStep ? "#C49A1A" : "#E8D8A0",
                boxShadow: i === currentStep ? "0 0 8px rgba(196,154,26,0.5)" : "none",
              }}
            />
          ))}
        </div>
      </motion.div>

      {/* Split layout: chamber left, transcript right */}
      <div className="flex flex-col gap-6 lg:flex-row lg:items-start">

        {/* LEFT — Council chamber, sticky so it stays in view while transcript scrolls */}
        <motion.div
          className="flex shrink-0 items-center justify-center lg:sticky lg:top-6"
          initial={{ opacity: 0, scale: 0.85 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ duration: 0.7, delay: 0.15, ease: [0.16, 1, 0.3, 1] }}
        >
          <CouncilChamber activeAdvisors={activeAdvisors} step={currentStep} speeches={speeches} quips={quips} />
        </motion.div>

        {/* RIGHT — Live transcript panel */}
        <motion.div
          className="min-w-0 flex-1"
          initial={{ opacity: 0, x: 24 }}
          animate={{ opacity: 1, x: 0 }}
          transition={{ delay: 0.4 }}
        >
          <div className="rounded-2xl border border-[#E8E0CC] bg-white shadow-sm">
            {/* Panel header */}
            <div className="flex items-center gap-2.5 border-b border-[#F0E8D4] px-5 py-3.5">
              <motion.span
                className="h-2 w-2 rounded-full bg-[#C49A1A]"
                animate={{ opacity: [1, 0.3, 1], scale: [1, 1.3, 1] }}
                transition={{ duration: 1.8, repeat: Infinity }}
              />
              <span
                className="text-[10px] uppercase tracking-[0.3em] text-[#9A8060]"
                style={{ fontFamily: "var(--font-dm-mono)" }}
              >
                Live Transcript
              </span>
            </div>

            {/* Scrollable feed */}
            <div
              ref={feedRef}
              className="space-y-3 overflow-y-auto p-5 pr-4"
              style={{ maxHeight: "min(64vh, 560px)" }}
            >
              <AnimatePresence initial={false}>
                {lines.map((line) => (
                  <motion.div
                    key={line.id}
                    layout
                    className="flex items-start gap-2.5"
                    initial={{ opacity: 0, x: -8, y: 4 }}
                    animate={{ opacity: 1, x: 0, y: 0 }}
                    transition={{ duration: 0.3 }}
                  >
                    {line.kind === "narration" && (
                      <>
                        <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-[#C49A1A]" />
                        <p
                          className="text-sm italic leading-relaxed text-[#5C4838]"
                          style={{ fontFamily: "var(--font-playfair)" }}
                        >
                          {line.text}
                        </p>
                      </>
                    )}
                    {line.kind === "advisor" && (
                      <>
                        <span
                          className="mt-1 h-2 w-2 shrink-0 rounded-full"
                          style={{
                            backgroundColor:
                              ADVISORS.find((a) => a.role === line.role)?.color || "#C49A1A",
                          }}
                        />
                        <div className="min-w-0 flex-1">
                          <p className="text-[11px] font-semibold text-[#2C1810]">
                            {line.title}
                            <span className="font-normal text-[#9A8060]">
                              {" "}· Round {line.round + 1}
                            </span>
                          </p>
                          <p className="mt-0.5 text-xs leading-relaxed text-[#4A3A30]">
                            "{stripMd(line.text)}"
                          </p>
                        </div>
                      </>
                    )}
                    {line.kind === "status" && (
                      <>
                        <span className="mt-1.5 h-1 w-1 shrink-0 rounded-full bg-[#D0C8B4]" />
                        <span
                          className="text-[10px] leading-relaxed text-[#9A8060]"
                          style={{ fontFamily: "var(--font-dm-mono)" }}
                        >
                          {line.text}
                        </span>
                      </>
                    )}
                  </motion.div>
                ))}
              </AnimatePresence>

              {showTyping && (
                <motion.div
                  className="flex items-center gap-2 pt-1"
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                >
                  <span
                    className="text-[10px] text-[#B0A090]"
                    style={{ fontFamily: "var(--font-dm-mono)" }}
                  >
                    Advisors thinking
                  </span>
                  <div className="flex gap-1">
                    {[0, 1, 2].map((i) => (
                      <motion.span
                        key={i}
                        className="h-1 w-1 rounded-full bg-[#C49A1A]/50"
                        animate={{ y: [0, -3, 0] }}
                        transition={{ duration: 0.8, repeat: Infinity, delay: i * 0.15 }}
                      />
                    ))}
                  </div>
                </motion.div>
              )}
            </div>
          </div>
        </motion.div>
      </div>
    </div>
  );
}
