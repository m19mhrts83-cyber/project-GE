/**
 * KURASHIFT の判断ログ（/decisions）を組み立てる純粋な部品。
 * 材料はアプリの表だけ（kurashift_money_ops.assist_payload.decision_log・kurashift_re_deal_events）。
 * owner_decisions（共有の判断ログ）は DB トリガーが写すので、ここでは読まない。
 */
import {
  MONEY_STATUS_LABEL,
  RETRO_QUALITY,
  tagLabel,
  type Retro,
  type RetroQuality,
} from "./kurashiftDecision";

export type DecisionKind = "money" | "deal";
export type Outcome = "take" | "ng" | "hesitate" | "later" | "note";

export type DecisionRow = {
  key: string;
  kind: DecisionKind;
  at: string;
  targetId: string;
  title: string;
  /** 例: 「承認」「見送り」 */
  label: string;
  outcome: Outcome;
  amountJpy: number | null;
  reasonTags: string[];
  reasonLabels: string[];
  note: string | null;
  always: boolean;
  by: string | null;
  /** 同じ種類の判断をまとめる鍵。例: money:approved / deal:pass */
  ctx: string;
  /** 資金移動の種類（bank_transfer など）。物件は null */
  subKind: string | null;
  /** 答え合わせの宛先（資金移動＝判断の時刻、物件＝イベント id） */
  refId: string;
  retro: Retro | null;
  decideMs: number | null;
};

type MoneyOp = {
  id: string;
  title: string | null;
  kind?: string | null;
  amount_jpy?: number | string | null;
  assist_payload?: unknown;
};

type DealEvent = {
  id: string;
  deal_id: string;
  event_type: string;
  actor?: string | null;
  occurred_at: string;
  payload?: unknown;
};

const MONEY_OUTCOME: Record<string, Outcome> = {
  approved: "take",
  done: "take",
  cancelled: "ng",
  consulting: "hesitate",
};

const DEAL_LABEL: Record<string, { label: string; outcome: Outcome }> = {
  confirm: { label: "候補に残す（問合せへ）", outcome: "take" },
  pass: { label: "見送り", outcome: "ng" },
  pursue_add: { label: "進行中に入れる", outcome: "take" },
  pursue_remove: { label: "進行中から外す", outcome: "later" },
  set_viewing: { label: "内見へ", outcome: "take" },
  set_offer: { label: "買付へ", outcome: "take" },
};

function obj(v: unknown): Record<string, unknown> {
  return v && typeof v === "object" ? (v as Record<string, unknown>) : {};
}

function tags(v: unknown): string[] {
  return Array.isArray(v) ? v.map((t) => String(t)).filter(Boolean) : [];
}

function retroOf(v: unknown): Retro | null {
  const r = obj(v);
  const q = String(r.quality || "");
  if (!(q in RETRO_QUALITY) || typeof r.at !== "string") return null;
  return {
    at: r.at,
    quality: q as RetroQuality,
    note: typeof r.note === "string" && r.note ? r.note : null,
  };
}

function num(v: unknown): number | null {
  if (v === null || v === undefined || v === "") return null;
  const n = Number(v);
  return Number.isFinite(n) ? n : null;
}

export function moneyRows(ops: MoneyOp[]): DecisionRow[] {
  const out: DecisionRow[] = [];
  for (const op of ops) {
    const log = obj(op.assist_payload).decision_log;
    if (!Array.isArray(log)) continue;
    log.forEach((raw, i) => {
      const e = obj(raw);
      const to = String(e.to || "");
      const outcome = MONEY_OUTCOME[to];
      if (!outcome) return; // 実行中へ・草案に戻すは判断ではない
      const t = tags(e.reason_tags);
      out.push({
        key: `m:${op.id}:${i}`,
        kind: "money",
        at: String(e.at || ""),
        targetId: op.id,
        title: op.title || "（無題の資金移動）",
        label: MONEY_STATUS_LABEL[to] || to,
        outcome,
        amountJpy: num(e.amount_jpy) ?? num(op.amount_jpy),
        reasonTags: t,
        reasonLabels: t.map(tagLabel),
        note: typeof e.note === "string" && e.note ? e.note : null,
        always: e.scope === "always",
        by: typeof e.by === "string" ? e.by : null,
        ctx: `money:${to}`,
        subKind: op.kind || null,
        refId: String(e.at || ""),
        retro: retroOf(e.retro),
        decideMs: num(e.decide_ms),
      });
    });
  }
  return out;
}

export function dealRows(
  events: DealEvent[],
  titles: Map<string, string>
): DecisionRow[] {
  const out: DecisionRow[] = [];
  // 答え合わせは別の行（payload.action=retro, ref_event_id）。新しいものを採る
  const retros = new Map<string, Retro>();
  for (const ev of events) {
    const p = obj(ev.payload);
    if (p.action !== "retro" || typeof p.ref_event_id !== "string") continue;
    const r = retroOf({ at: ev.occurred_at, quality: p.quality, note: p.note });
    const cur = retros.get(p.ref_event_id);
    if (r && (!cur || cur.at < r.at)) retros.set(p.ref_event_id, r);
  }
  for (const ev of events) {
    if ((ev.actor || "") !== "user") continue;
    const p = obj(ev.payload);
    const meta = DEAL_LABEL[String(p.action || "")];
    if (!meta) continue;
    const t = tags(p.reason_tags);
    out.push({
      key: `d:${ev.id}`,
      kind: "deal",
      at: ev.occurred_at,
      targetId: ev.deal_id,
      title: titles.get(ev.deal_id) || "（物件）",
      label: meta.label,
      outcome: meta.outcome,
      amountJpy: null,
      reasonTags: t,
      reasonLabels: t.map(tagLabel),
      note: typeof p.note === "string" && p.note ? p.note : null,
      always: p.scope === "always",
      by: typeof p.decided_by === "string" ? p.decided_by : null,
      ctx: `deal:${String(p.action)}`,
      subKind: null,
      refId: ev.id,
      retro: retros.get(ev.id) || null,
      decideMs: num(p.decide_ms),
    });
  }
  return out;
}

export type DecisionSummary = {
  total: number;
  take: number;
  ng: number;
  hesitate: number;
  later: number;
  /** 理由（タグかひとこと）が付いた割合 0〜1。0件なら null */
  reasonRate: number | null;
  /** 2件以上同じ理由（共通パターン）。1件だけのものは一般化しない */
  patterns: { tag: string; label: string; count: number; kind: DecisionKind; outcome: Outcome }[];
  /** 「次も同じに」が付いた判断（基準の候補） */
  ruleCandidates: DecisionRow[];
};

export function summarize(rows: DecisionRow[]): DecisionSummary {
  const s: DecisionSummary = {
    total: rows.length,
    take: 0,
    ng: 0,
    hesitate: 0,
    later: 0,
    reasonRate: null,
    patterns: [],
    ruleCandidates: [],
  };
  let withReason = 0;
  const counts = new Map<string, { count: number; kind: DecisionKind; outcome: Outcome; tag: string }>();
  for (const r of rows) {
    if (r.outcome === "take") s.take++;
    else if (r.outcome === "ng") s.ng++;
    else if (r.outcome === "hesitate") s.hesitate++;
    else if (r.outcome === "later") s.later++;
    if (r.reasonTags.length || r.note) withReason++;
    if (r.always) s.ruleCandidates.push(r);
    for (const t of r.reasonTags) {
      const k = `${r.kind}:${r.outcome}:${t}`;
      const cur = counts.get(k) || { count: 0, kind: r.kind, outcome: r.outcome, tag: t };
      cur.count++;
      counts.set(k, cur);
    }
  }
  s.reasonRate = rows.length ? withReason / rows.length : null;
  s.patterns = [...counts.values()]
    .filter((c) => c.count >= 2)
    .sort((a, b) => b.count - a.count)
    .map((c) => ({ ...c, label: tagLabel(c.tag) }));
  return s;
}

export function sortNewest(rows: DecisionRow[]): DecisionRow[] {
  return [...rows].sort((a, b) => (a.at < b.at ? 1 : a.at > b.at ? -1 : 0));
}

// ---------------------------------------------------------------- 判断メモへのヒント（過去の自分の判断を引く）

export type DecisionHints = {
  /** 同じ種類の判断の件数 */
  count: number;
  /** 理由タグの使用回数（多い順）。判断メモはこの順に並べる */
  tagCounts: { key: string; label: string; count: number }[];
  /** 前回の同じ種類の判断（理由かひとことがあるものだけ）。「前回と同じ」に使う */
  last: {
    at: string;
    title: string;
    reasonTags: string[];
    reasonLabels: string[];
    note: string | null;
  } | null;
  /** 「次も同じに」が付いた過去の判断の理由（自分で決めた基準の候補） */
  alwaysTags: string[];
  /** 答え合わせで「やり直したい」が付いた、同じ種類の判断（決める前の注意） */
  regrets: { at: string; title: string; note: string | null; reasonLabels: string[] }[];
};

/**
 * 同じ種類（ctx）の過去の判断から、判断メモに出すヒントを作る。
 * AI が理由を推測するのではなく、本人の過去の記録をそのまま引く（L09）。
 */
export function buildHints(rows: DecisionRow[], ctx: string): DecisionHints {
  const same = sortNewest(rows.filter((r) => r.ctx === ctx));
  const counts = new Map<string, number>();
  const always = new Set<string>();
  for (const r of same) {
    for (const t of r.reasonTags) {
      counts.set(t, (counts.get(t) || 0) + 1);
      if (r.always) always.add(t);
    }
  }
  const lastRow = same.find((r) => r.reasonTags.length || r.note) || null;
  return {
    count: same.length,
    tagCounts: [...counts.entries()]
      .sort((a, b) => b[1] - a[1])
      .map(([key, count]) => ({ key, label: tagLabel(key), count })),
    last: lastRow
      ? {
          at: lastRow.at,
          title: lastRow.title,
          reasonTags: lastRow.reasonTags,
          reasonLabels: lastRow.reasonLabels,
          note: lastRow.note,
        }
      : null,
    alwaysTags: [...always],
    regrets: same
      .filter((r) => r.retro?.quality === "regret")
      .slice(0, 2)
      .map((r) => ({
        at: r.at,
        title: r.title,
        note: r.retro?.note || null,
        reasonLabels: r.reasonLabels,
      })),
  };
}

// ---------------------------------------------------------------- 答え合わせ（S21）

/**
 * 答え合わせを付けられる判断か。進めた判断のうち、判断そのもの（承認・内見・買付）だけ。
 * 資金移動の「完了」や物件の「候補に残す・進行中に入れる」は進み具合なので対象外。
 */
export function canRetro(r: DecisionRow): boolean {
  return (
    r.outcome === "take" &&
    r.ctx !== "money:done" &&
    r.ctx !== "deal:confirm" &&
    r.ctx !== "deal:pursue_add"
  );
}

/** 進めた判断のうち、日数が経って答え合わせがまだのもの（古い順） */
export function retroCandidates(
  rows: DecisionRow[],
  now: Date,
  minDays = 14
): DecisionRow[] {
  const limit = new Date(now.getTime() - minDays * 86400_000).toISOString();
  return rows
    .filter((r) => canRetro(r) && !r.retro && r.at && r.at <= limit)
    .sort((a, b) => (a.at < b.at ? -1 : 1));
}

export type RetroSummary = { total: number; good: number; meh: number; regret: number };

export function summarizeRetro(rows: DecisionRow[]): RetroSummary {
  const s: RetroSummary = { total: 0, good: 0, meh: 0, regret: 0 };
  for (const r of rows) {
    if (!r.retro) continue;
    s.total++;
    s[r.retro.quality]++;
  }
  return s;
}

// ---------------------------------------------------------------- チャットの AI に渡す文章（学びはツールの外）

/** 件数に合わせたお願い（Nody /review と同じ段階） */
export function aiStage(total: number): string {
  if (total <= 3) return "まだ件数が少ないので、一般化せず、今回の判断の振り返りだけ手伝ってください。";
  if (total <= 10) return "参照例として読み、次に似た判断をするときに確かめるべき点を挙げてください。基準にはまだしないでください。";
  if (total <= 30) return "進めた群と見送った群を比べ、共通点を「基準の候補」として最大3つ出してください。私が承認したものだけ基準にします。";
  return "基準の候補に加えて、確認の順番や見落としやすい点を提案してください。答え合わせ（後日の結果）と食い違う基準は見直し候補として挙げてください。";
}

export function toAiBrief(rows: DecisionRow[]): string {
  const s = summarize(rows);
  const lines: string[] = [
    "# KURASHIFT お金の判断ログ",
    "",
    `件数 ${s.total}（進めた ${s.take}／見送った ${s.ng}／迷った ${s.hesitate}／後で ${s.later}）。理由は本人が付けたものだけです。空欄を推測で埋めないでください。`,
    "",
    `お願い: ${aiStage(s.total)}`,
    "",
    "| 日時 | 種類 | 判断 | 対象 | 金額 | 理由 | ひとこと | 次も同じ | 答え合わせ |",
    "|---|---|---|---|---|---|---|---|---|",
  ];
  for (const r of sortNewest(rows)) {
    const cell = (v: string | null) => (v ? v.replace(/\|/g, "／").replace(/\n/g, " ") : "");
    lines.push(
      `| ${r.at.slice(0, 10)} | ${r.kind === "money" ? "資金移動" : "物件"} | ${r.label} | ${cell(r.title)} | ${
        r.amountJpy !== null ? `${Math.round(r.amountJpy).toLocaleString("ja-JP")}円` : ""
      } | ${r.reasonLabels.join("・")} | ${cell(r.note)} | ${r.always ? "はい" : ""} | ${
        r.retro ? `${RETRO_QUALITY[r.retro.quality]}${r.retro.note ? `：${cell(r.retro.note)}` : ""}` : ""
      } |`
    );
  }
  return lines.join("\n");
}
