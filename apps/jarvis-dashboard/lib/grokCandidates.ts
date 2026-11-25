/**
 * Grok 候補（S9 など）の一覧を作る部品。画面から切り離した純関数（テスト対象）。
 *
 * 材料は2つだけ（新しいテーブルは使わない）:
 *   - sync_meta(grok_candidates_snapshot) … Mac の取り込みが残した結果（新規／重複／判断待ち／送らない）
 *   - kurashift_re_mgmt_vendors（台帳） … 送信待ち／送信済み／見送りは、ここの status で決める
 * 状態は画面で毎回突き合わせて決める。スナップショットに「送信済み」などを焼き込まない
 * （台帳が正本。古い写しで状態を食い違わせないため）。
 */

export type GrokCand = {
  n: number;
  name: string;
  area?: string;
  pref?: string;
  city?: string;
  lane?: string;
  url?: string;
  cu?: string;
  em?: string;
  tel?: string;
  ch?: string;
  memo?: string;
  src?: string;
  dt?: string;
};

export type SnapshotItem = {
  key: string;
  kind: "add" | "dup" | "consult" | "drop";
  why: string;
  seen_at: string;
  md: string;
  cand: GrokCand;
  existing?: { name: string; status: string };
  upgraded?: boolean;
};

export type LedgerRow = {
  id?: string | null;
  name: string | null;
  status: string | null;
  source: string | null;
  discovered_at?: string | null;
  contacted_at?: string | null;
  area?: string | null;
  channel?: string | null;
};

/** 受け付け済みの採用／見送りジョブ（Mac worker が台帳へ反映する前）。 */
export type PendingJob = { name: string; decision: "adopt" | "skip" };

export type GrokState = "decide" | "queued" | "pending" | "sent" | "dup" | "skipped" | "drop";

export const STATE_LABEL: Record<GrokState, string> = {
  decide: "新規（判断待ち）",
  queued: "受付済み（台帳へ反映中）",
  pending: "送信待ち",
  sent: "送信済み",
  dup: "登録済み（重複）",
  skipped: "見送り",
  drop: "送らない",
};

/** 画面の並び順＝今見るべき順。 */
export const STATE_ORDER: GrokState[] = ["decide", "queued", "pending", "sent", "dup", "skipped", "drop"];

export type GrokView = {
  key: string;
  name: string;
  area: string;
  channel: string;
  state: GrokState;
  /** 重複・送らない・判断待ちの理由（無ければ空） */
  reason: string;
  /** 台帳に既にある同じ会社（重複の相手） */
  existingName: string;
  date: string;
  /** 採用／見送りボタンを出す（判断待ちのときだけ） */
  canDecide: boolean;
  fromLedgerOnly: boolean;
};

const CORP_WORDS = ["株式会社", "有限会社", "合同会社", "（株）", "(株)", "（有）", "(有)"];

/** Mac 側 _norm_name と同じ（会社形態・空白・括弧・中黒を除く）。 */
export function normName(s: string): string {
  let t = String(s || "");
  for (const w of CORP_WORDS) t = t.split(w).join("");
  return t.replace(/[\s・（）()]/g, "");
}

export const GROK_LEDGER_SOURCE_PREFIXES = ["s9_candidates_", "s9_slack_"];

export function isGrokLedgerSource(source: string | null | undefined): boolean {
  const s = String(source || "");
  return GROK_LEDGER_SOURCE_PREFIXES.some((p) => s.startsWith(p));
}

export function parseSnapshot(raw: unknown): { generatedAt: string; items: SnapshotItem[] } | null {
  if (typeof raw !== "string" || !raw.trim()) return null;
  let j: unknown;
  try {
    j = JSON.parse(raw);
  } catch {
    return null;
  }
  if (!j || typeof j !== "object") return null;
  const o = j as { generated_at?: unknown; items?: unknown };
  if (!Array.isArray(o.items)) return null;
  const items: SnapshotItem[] = [];
  for (const it of o.items) {
    if (!it || typeof it !== "object") continue;
    const x = it as Partial<SnapshotItem>;
    if (!x.key || !x.cand || !x.cand.name) continue;
    if (!["add", "dup", "consult", "drop"].includes(String(x.kind))) continue;
    items.push({
      key: String(x.key),
      kind: x.kind as SnapshotItem["kind"],
      why: String(x.why || ""),
      seen_at: String(x.seen_at || ""),
      md: String(x.md || ""),
      cand: x.cand as GrokCand,
      existing: x.existing ? { name: String(x.existing.name || ""), status: String(x.existing.status || "") } : undefined,
      upgraded: !!x.upgraded,
    });
  }
  return { generatedAt: String(o.generated_at || ""), items };
}

/** 台帳の status → 画面の状態（pending/discovered は送信待ち、skip/invalid は見送り、それ以外は接触済み）。 */
export function stateFromLedgerStatus(status: string | null | undefined): GrokState {
  const s = String(status || "pending");
  if (s === "pending" || s === "discovered") return "pending";
  if (s === "skip" || s === "invalid") return "skipped";
  return "sent";
}

function ledgerIndex(ledger: LedgerRow[]): Map<string, LedgerRow> {
  const m = new Map<string, LedgerRow>();
  for (const r of ledger) {
    const k = normName(r.name || "");
    if (k && !m.has(k)) m.set(k, r);
  }
  return m;
}

const EXISTING_STATE_TEXT: Record<GrokState, string> = {
  decide: "",
  queued: "",
  pending: "送信待ち",
  sent: "送信済み",
  dup: "",
  skipped: "見送り",
  drop: "",
};

export function buildViews(
  snapshotItems: SnapshotItem[],
  ledger: LedgerRow[],
  jobs: PendingJob[] = [],
): GrokView[] {
  const idx = ledgerIndex(ledger);
  const jobBy = new Map<string, PendingJob>();
  for (const j of jobs) {
    const k = normName(j.name);
    if (k && !jobBy.has(k)) jobBy.set(k, j);
  }
  const views: GrokView[] = [];
  const seen = new Set<string>();

  for (const it of snapshotItems) {
    const key = normName(it.cand.name) || it.key;
    seen.add(key);
    const led = idx.get(key);
    let state: GrokState;
    let reason = it.why;
    let existingName = it.existing?.name || "";
    if (it.kind === "drop") {
      state = "drop";
    } else if (it.kind === "dup") {
      state = "dup";
      // 相手の最新の状態は台帳から（取り込み時点の写しより新しい）
      const exLed = idx.get(normName(existingName));
      const exState = stateFromLedgerStatus(exLed?.status ?? it.existing?.status);
      const st = EXISTING_STATE_TEXT[exState];
      if (existingName) reason = `${reason || "台帳に既存"}${st ? `／台帳では${st}` : ""}`;
    } else if (it.kind === "add") {
      state = led ? stateFromLedgerStatus(led.status) : "pending";
    } else if (led) {
      // 判断待ちだった候補が台帳に入っている＝採用／見送り済み
      state = stateFromLedgerStatus(led.status);
      reason = "";
    } else if (jobBy.has(key)) {
      state = "queued";
      reason = jobBy.get(key)!.decision === "adopt" ? "採用で受付済み" : "見送りで受付済み";
    } else {
      state = "decide";
    }
    views.push({
      key,
      name: it.cand.name,
      area: it.cand.area || "",
      channel: it.cand.ch || "",
      state,
      reason,
      existingName: it.kind === "dup" ? existingName : "",
      date: it.cand.dt || it.seen_at.slice(0, 10),
      canDecide: state === "decide",
      fromLedgerOnly: false,
    });
  }

  // スナップショットが無い（導入前）取り込み分は、台帳の出どころ印から補う。判断ボタンは付けない。
  for (const r of ledger) {
    if (!isGrokLedgerSource(r.source)) continue;
    const key = normName(r.name || "");
    if (!key || seen.has(key)) continue;
    seen.add(key);
    views.push({
      key,
      name: String(r.name || ""),
      area: String(r.area || ""),
      channel: String(r.channel || ""),
      state: stateFromLedgerStatus(r.status),
      reason: "",
      existingName: "",
      date: String(r.discovered_at || "").slice(0, 10),
      canDecide: false,
      fromLedgerOnly: true,
    });
  }

  const rank = (s: GrokState) => STATE_ORDER.indexOf(s);
  views.sort((a, b) => rank(a.state) - rank(b.state) || b.date.localeCompare(a.date));
  return views;
}

export function countByState(views: GrokView[]): Record<GrokState, number> {
  const c = Object.fromEntries(STATE_ORDER.map((s) => [s, 0])) as Record<GrokState, number>;
  for (const v of views) c[v.state] += 1;
  return c;
}
