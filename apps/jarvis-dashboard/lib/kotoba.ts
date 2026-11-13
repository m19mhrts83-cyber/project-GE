/**
 * ことばの棚（/kotoba）の部品。外部に依存しない（テストは tests/kotoba.test.mjs）。
 * 設計: Claude Doc「ことばの棚 設計案」／表: supabase/migrations/20261111_kotoba_cards.sql
 */

/** 棚（テーマ）。最初は7つ。足りなければ後から足す */
export const SHELVES = [
  "不動産購入・融資・契約",
  "賃貸経営・パートナー",
  "神大家・DX互助会",
  "AI・仕組みづくり",
  "働き方・心の持ち方",
  "お金・資産運用",
  "家族",
] as const;

export const KIND_LABEL: Record<string, string> = {
  insight: "知見",
  cheer: "励まし",
  criterion: "判断基準",
  question: "問い",
  self_note: "自分の気づき",
};

export const STATUS_LABEL: Record<string, string> = {
  candidate: "未判断",
  kept: "残す",
  dropped: "いらない",
  hesitated: "迷う",
};

export type KotobaVerdict = "keep" | "drop" | "hesitate" | "comment";

/** 画面の判断 → カードの状態と判断ログの action（契約 v1 の語） */
export const VERDICT: Record<KotobaVerdict, { status: string | null; action: string }> = {
  keep: { status: "kept", action: "accept" },
  drop: { status: "dropped", action: "reject" },
  hesitate: { status: "hesitated", action: "hesitated" },
  comment: { status: null, action: "comment" },
};

export type KotobaCard = {
  id: string;
  body: string;
  speaker: string | null;
  speaker_guess: boolean;
  where_label: string | null;
  occurred_on: string | null;
  at_label: string | null;
  source: string;
  source_ref: Record<string, unknown> | null;
  background: string | null;
  kind: string;
  shelves: string[];
  is_summary: boolean;
  status: string;
  created_at: string;
};

export type KotobaNote = {
  id: number;
  card_id: string | null;
  shelf: string | null;
  kind: string;
  body: string;
  created_at: string;
};

const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

export function isCardId(id: unknown): id is string {
  return typeof id === "string" && UUID_RE.test(id);
}

export function isShelf(s: unknown): s is string {
  return typeof s === "string" && (SHELVES as readonly string[]).includes(s);
}

/** 「誰が／どこで」の1行 */
export function whoWhere(c: Pick<KotobaCard, "speaker" | "speaker_guess" | "where_label" | "occurred_on" | "at_label">): string {
  const who = c.speaker ? `${c.speaker}${c.speaker_guess ? "（推定）" : ""}` : "話者不明";
  const date = c.occurred_on ? c.occurred_on.slice(5).replace("-", "/").replace(/^0/, "").replace("/0", "/") : "";
  const where = [date, c.where_label, c.at_label].filter(Boolean).join(" ");
  return where ? `${who}／${where}` : who;
}

export type ShelfGroup = { shelf: string; cards: KotobaCard[]; counts: Record<string, number> };

/**
 * 棚ごとに並べる。1枚が複数の棚に入ることがある。
 * 棚が付いていないカードは「未分類」にまとめる。並びは SHELVES の順、未分類は最後。
 */
export function groupByShelf(cards: KotobaCard[]): ShelfGroup[] {
  const map = new Map<string, KotobaCard[]>();
  for (const c of cards) {
    const shelves = (c.shelves || []).filter(Boolean);
    for (const s of shelves.length ? shelves : ["未分類"]) {
      if (!map.has(s)) map.set(s, []);
      map.get(s)!.push(c);
    }
  }
  const order = [...SHELVES, ...[...map.keys()].filter((k) => !(SHELVES as readonly string[]).includes(k) && k !== "未分類").sort(), "未分類"];
  return order
    .filter((s) => map.has(s))
    .map((shelf) => {
      const list = map.get(shelf)!;
      const counts: Record<string, number> = { candidate: 0, kept: 0, dropped: 0, hesitated: 0 };
      for (const c of list) counts[c.status] = (counts[c.status] || 0) + 1;
      return { shelf, cards: list, counts };
    });
}

/** 表示する状態の絞り込み。既定は「いらない」以外 */
export function filterByStatus(cards: KotobaCard[], view: string | undefined): KotobaCard[] {
  if (view === "all") return cards;
  if (view && view in STATUS_LABEL) return cards.filter((c) => c.status === view);
  return cards.filter((c) => c.status !== "dropped");
}
