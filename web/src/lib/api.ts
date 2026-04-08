const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export interface TemplateField {
  name: string;
  label: string;
  type: "text" | "textarea";
  placeholder: string;
}

export interface Template {
  id: string;
  label: string;
  description: string;
  icon: string;
  fields: TemplateField[];
}

export interface DebateStartResponse {
  id: string;
  status: string;
}

export interface SSEEvent {
  type: "status" | "narration" | "advisor" | "complete" | "error" | "heartbeat";
  message?: string;
  /** Per-advisor live excerpt (speech bubble + transcript) */
  role?: string | null;
  title?: string;
  model?: string;
  round?: number;
  text?: string;
  /** 1-3 short debate phrases for speech bubbles (LLM-authored, 8 words max each) */
  quips?: string[];
  result?: DebateResult;
}

export interface DebateResult {
  verdict: string;
  confidence: number;
  headline: string;
  opportunities?: string[];
  risks?: string[];
  conditions?: string[];
  what_if_suggestions?: string[];
  model_votes: Record<string, string>;
  model_titles?: Record<string, string>;
  consensus: string;
  dissent: string | null;
  unique_catches?: string[];
  elapsed: number;
  mode: string;
  domain: string;
  models_used: string[];
  judge: string;
  usage: { prompt_tokens: number; completion_tokens: number; reasoning_tokens: number };
  cost: number;
}

export async function fetchTemplates(): Promise<Template[]> {
  const res = await fetch(`${API_BASE}/api/templates`);
  if (!res.ok) throw new Error("Failed to fetch templates");
  return res.json();
}

export async function startDebate(
  template: string,
  fields: Record<string, string>
): Promise<DebateStartResponse> {
  const res = await fetch(`${API_BASE}/api/debate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ template, fields }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: "Request failed" }));
    throw new Error(err.detail || "Failed to start debate");
  }
  return res.json();
}

export function streamDebate(
  debateId: string,
  onEvent: (event: SSEEvent) => void
): () => void {
  const eventSource = new EventSource(`${API_BASE}/api/debate/stream/${debateId}`);

  eventSource.onmessage = (e) => {
    try {
      const parsed: SSEEvent = JSON.parse(e.data);
      onEvent(parsed);
      if (parsed.type === "complete" || parsed.type === "error") {
        eventSource.close();
      }
    } catch {
      // skip unparseable
    }
  };

  eventSource.onerror = () => {
    eventSource.close();
    onEvent({ type: "error", message: "Connection lost" });
  };

  return () => eventSource.close();
}
