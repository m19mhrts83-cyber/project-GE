/**
 * 資料作成ループ（DX互助会などの説明資料）の純粋な部品。外部に依存しない。
 *
 * 流れ：エージェントが案を置く（sync_meta.loopware_slides）→ 人が選ぶ（slide_plan）
 * → 資料を作って人が直す（slide_fix はエージェントが記録）→ エージェントが直しを概念にまとめた反映案を置く
 * → 人が 採用／今回だけ／違う（slide_rule）→ 採用したものだけが次回の案づくりに効く。
 * アプリは AI を呼ばない（案づくり・まとめはエージェントの仕事）。
 */

export type SlidePlan = {
  id: string; // 例 "A"
  label: string; // 例 "事例中心"
  summary: string;
  outline: string[]; // スライドの流れ（見出し）
  applied: string[]; // この案で反映した前回の学び（採用ルールの id）
};

export type SlideAxis = {
  key: string; // 例 "volume"
  label: string; // 例 "分量"
  options: string[]; // 例 ["10枚", "15枚", "20枚"]
  recommended?: number; // 推し（0始まり）
};

export type SlideProposal = {
  id: string; // 例 "P1"（デッキの中で一意）
  text: string; // 次回に効かせる基準の文
  why: string; // 根拠（今回どう直したか）
  evidence?: string[]; // 直しの例（短く）
  concept?: string; // まとめた概念（例 "用語の言い換え"）
};

export type SlideDeck = {
  id: string; // 例 "2026-11-dx-gojokai"
  title: string;
  stage: "plan" | "review" | "done";
  created_at?: string;
  note?: string;
  plans: SlidePlan[];
  axes: SlideAxis[];
  proposals: SlideProposal[];
};

export type SlideRule = {
  key: string; // `${deckId}:${proposalId}`
  deckId: string;
  text: string;
  concept: string | null;
  at: string;
  reverted: boolean;
};

/** 作る前の観点の既定（エージェントが deck.axes を置かなかったとき） */
export const DEFAULT_AXES: SlideAxis[] = [
  { key: "volume", label: "分量", options: ["10枚", "15枚", "20枚"], recommended: 1 },
  { key: "tone", label: "トーン", options: ["やさしく", "標準", "専門寄り"], recommended: 0 },
  { key: "visual", label: "図の量", options: ["少なめ", "ふつう", "多め"], recommended: 1 },
  { key: "imamura", label: "今村さん課題", options: ["前回より易しく", "前回と同じ", "一段上"], recommended: 1 },
];

function str(v: unknown, n: number): string {
  return v === null || v === undefined ? "" : String(v).trim().slice(0, n);
}

function strList(v: unknown, n: number, max: number): string[] {
  if (!Array.isArray(v)) return [];
  return v.map((x) => str(x, n)).filter(Boolean).slice(0, max);
}

const ID_RE = /^[A-Za-z0-9_-]{1,40}$/;

/** sync_meta に置かれた JSON を検証して形を揃える。壊れていれば null */
export function parseDeck(raw: unknown): SlideDeck | null {
  let v: unknown = raw;
  if (typeof raw === "string") {
    try {
      v = JSON.parse(raw);
    } catch {
      return null;
    }
  }
  if (!v || typeof v !== "object") return null;
  const o = v as Record<string, unknown>;
  const id = str(o.id, 80);
  const title = str(o.title, 200);
  if (!/^[A-Za-z0-9_.-]{1,80}$/.test(id) || !title) return null;
  const stage = o.stage === "review" || o.stage === "done" ? o.stage : "plan";
  const plans: SlidePlan[] = (Array.isArray(o.plans) ? o.plans : [])
    .map((p) => {
      const x = (p || {}) as Record<string, unknown>;
      return {
        id: str(x.id, 40),
        label: str(x.label, 80),
        summary: str(x.summary, 600),
        outline: strList(x.outline, 120, 30),
        applied: strList(x.applied, 120, 10),
      };
    })
    .filter((p) => ID_RE.test(p.id) && p.label)
    .slice(0, 4);
  const axesIn: SlideAxis[] = (Array.isArray(o.axes) ? o.axes : [])
    .map((a) => {
      const x = (a || {}) as Record<string, unknown>;
      const options = strList(x.options, 40, 4);
      const rec = Number(x.recommended);
      return {
        key: str(x.key, 40),
        label: str(x.label, 40),
        options,
        recommended: Number.isInteger(rec) && rec >= 0 && rec < options.length ? rec : undefined,
      };
    })
    .filter((a) => ID_RE.test(a.key) && a.label && a.options.length >= 2)
    .slice(0, 6);
  const proposals: SlideProposal[] = (Array.isArray(o.proposals) ? o.proposals : [])
    .map((p) => {
      const x = (p || {}) as Record<string, unknown>;
      return {
        id: str(x.id, 40),
        text: str(x.text, 300),
        why: str(x.why, 600),
        evidence: strList(x.evidence, 200, 5),
        concept: str(x.concept, 60) || undefined,
      };
    })
    .filter((p) => ID_RE.test(p.id) && p.text)
    .slice(0, 8);
  return {
    id,
    title,
    stage,
    created_at: str(o.created_at, 40) || undefined,
    note: str(o.note, 600) || undefined,
    plans,
    axes: axesIn.length ? axesIn : DEFAULT_AXES,
    proposals,
  };
}

/** 反映案1件の判断の鍵（どのデッキのどの案か） */
export function ruleKey(deckId: string, proposalId: string): string {
  return `${deckId}:${proposalId}`;
}

type Row = { action: string; target_id: string; payload?: Record<string, unknown> | null; decided_at?: string | null };

/**
 * slide_rule の行（新しい順でも古い順でもよい）から、いま効いている「資料の基準」を作る。
 * 同じ反映案に判断が何度もあれば、いちばん新しいものを使う。取り消し（rule_revert）が後にあれば外す。
 */
export function adoptedSlideRules(rows: Row[]): SlideRule[] {
  const sorted = [...rows].sort((a, b) => String(a.decided_at || "").localeCompare(String(b.decided_at || "")));
  const last = new Map<string, Row>();
  for (const r of sorted) last.set(r.target_id, r);
  const out: SlideRule[] = [];
  for (const [key, r] of last) {
    if (r.action !== "rule_accept") continue;
    const pl = (r.payload || {}) as Record<string, unknown>;
    out.push({
      key,
      deckId: str(pl.deck_id, 80) || key.split(":")[0],
      text: str(pl.text, 300),
      concept: str(pl.concept, 60) || null,
      at: str(r.decided_at, 40),
      reverted: false,
    });
  }
  return out.sort((a, b) => b.at.localeCompare(a.at));
}

/** このデッキで、もう判断した反映案（key → action） */
export function decidedProposals(rows: Row[], deckId: string): Record<string, string> {
  const sorted = [...rows].sort((a, b) => String(a.decided_at || "").localeCompare(String(b.decided_at || "")));
  const out: Record<string, string> = {};
  for (const r of sorted) {
    if (r.target_id.startsWith(`${deckId}:`)) out[r.target_id.slice(deckId.length + 1)] = r.action;
  }
  return out;
}

/** 作る前の選択が揃ったか（案1つ＋全観点） */
export function planComplete(deck: SlideDeck, pick: { plan: string | null; axes: Record<string, number> }): boolean {
  if (deck.plans.length && !deck.plans.some((p) => p.id === pick.plan)) return false;
  return deck.axes.every((a) => Number.isInteger(pick.axes[a.key]) && pick.axes[a.key] >= 0 && pick.axes[a.key] < a.options.length);
}
