export type DecisionRecord = {
  topicId: string;
  agentId: "312" | "313";
  choice: "use" | "edit_use" | "none_of_above" | "close" | "reschedule" | "drop" | "take" | "skip" | "hold";
  chosenIndex?: number;
  finalText?: string;
  beforeText?: string;
  afterText?: string;
  reasonTags: string[];
  freeNote?: string;
  decidedAt: string;
  decidedVia: "app" | "slack";
  /** 「今回だけ」か「次も同じに」か。既定は once。次も同じに＝基準の候補（本人が承認するまで基準にしない） */
  scope?: "once" | "rule";
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

/** 決定を取り消す（もう一度選べるようにする）。サーバ側の判断ログは履歴として残る */
export function removeDecision(topicId: string, agentId: "312" | "313") {
  const store = loadStore();
  saveStore({
    version: 1,
    decisions: store.decisions.filter(
      (d) => !(d.topicId === topicId && d.agentId === agentId),
    ),
  });
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

/* ---- 音声（・文字）コメント：どのカードへのコメントかを targetId で持つ ---- */
export type VoiceComment = {
  id: string;
  agentId: "312" | "313";
  targetId: string;
  targetLabel: string;
  text: string;
  at: string;
  via: "voice" | "text";
  synced: boolean | null; // null=送信中, true=Supabase保存済み, false=端末のみ
  /** 話し始めた時刻（at は話し終えた時刻）。見ながら言う：発話の開始時点に見ていた場所に結び付ける */
  startedAt?: string;
  mode?: "follow" | "pin";
  /** 話し終えたときに見ていた場所が違った場合（前のカードの話かもしれない）。あとで「こちらへ移す」で付け替えられる */
  alt?: { id: string; label: string };
};

const VKEY = "loopware_voice_v1";

export function loadVoice(): VoiceComment[] {
  if (typeof window === "undefined") return [];
  try {
    const p = JSON.parse(localStorage.getItem(VKEY) || "[]");
    return Array.isArray(p) ? p : [];
  } catch {
    return [];
  }
}

export function saveVoice(list: VoiceComment[]) {
  try {
    localStorage.setItem(VKEY, JSON.stringify(list.slice(0, 300)));
  } catch {
    /* ignore */
  }
}
