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
  /** shared = 共有DB（Supabase）に保存できた／local = この端末だけ。未送信は undefined */
  sync?: "shared" | "local";
  syncReason?: string;
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

export function updateDecisionSync(
  rec: DecisionRecord,
  sync: "shared" | "local",
  reason?: string,
) {
  const store = loadStore();
  const next = store.decisions.map((d) =>
    d.topicId === rec.topicId && d.agentId === rec.agentId && d.decidedAt === rec.decidedAt
      ? { ...d, sync, syncReason: sync === "local" ? reason : undefined }
      : d,
  );
  saveStore({ version: 1, decisions: next });
}

export function syncBadge(rec: DecisionRecord): string {
  if (rec.sync === "shared") return "共有DB";
  if (rec.sync === "local") return "端末のみ（共有DB未保存）";
  return "送信中／未確認";
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
    `- saved: ${syncBadge(rec)}`,
    "",
    "## final",
    rec.finalText || rec.afterText || "(empty)",
  ].join("\n");
}
