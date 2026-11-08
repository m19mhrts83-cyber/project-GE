export type DecisionRecord = {
  topicId: string;
  agentId: "312" | "313";
  choice: "use" | "edit_use" | "none_of_above" | "close" | "reschedule" | "drop";
  chosenIndex?: number;
  finalText?: string;
  beforeText?: string;
  afterText?: string;
  reasonTags: string[];
  freeNote?: string;
  decidedAt: string;
  decidedVia: "app" | "slack";
};

export type StoreV1 = {
  version: 1;
  decisions: DecisionRecord[];
};

const KEY = "loopware_v1";

export function loadStore(): StoreV1 {
  if (typeof window === "undefined") return { version: 1, decisions: [] };
  try {
    const raw = localStorage.getItem(KEY);
    if (!raw) return { version: 1, decisions: [] };
    const p = JSON.parse(raw) as StoreV1;
    if (p?.version !== 1 || !Array.isArray(p.decisions)) {
      return { version: 1, decisions: [] };
    }
    return p;
  } catch {
    return { version: 1, decisions: [] };
  }
}

export function saveStore(store: StoreV1) {
  localStorage.setItem(KEY, JSON.stringify(store));
}

export function upsertDecision(rec: DecisionRecord) {
  const store = loadStore();
  const next = store.decisions.filter(
    (d) => !(d.topicId === rec.topicId && d.agentId === rec.agentId),
  );
  next.unshift(rec);
  saveStore({ version: 1, decisions: next.slice(0, 200) });
}

export function formatDecisionMd(rec: DecisionRecord): string {
  return [
    `# loopware ${rec.agentId}`,
    `- topic: ${rec.topicId}`,
    `- choice: ${rec.choice}`,
    `- index: ${rec.chosenIndex ?? "-"}`,
    `- tags: ${(rec.reasonTags || []).join(", ") || "-"}`,
    `- note: ${rec.freeNote || "-"}`,
    `- at: ${rec.decidedAt}`,
    "",
    "## final",
    rec.finalText || rec.afterText || "(empty)",
  ].join("\n");
}
