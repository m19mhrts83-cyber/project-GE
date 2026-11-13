/**
 * UI/UX の好みループ（Nody /uiux）の純粋な部品。外部に依存しない。
 *
 * 流れ（資料作成ループ slidesCore.ts と同じ型）：
 *   エージェントが好み帳を読んで画面の案を置く（sync_meta.loopware_uiux）
 *   → 松野さんが案ごとに 良い／違う／迷う＋理由タグ、1つ選ぶ（uiux_plan）
 *   → 作った後の直し・「これいいね」はエージェントが記録（uiux_fix。scripts/jarvis_uiux_loop.py）
 *   → 土曜、直しをまとめた好みルール案を 採用／今回だけ／違う（uiux_rule）
 *   → 採用したものだけが好み帳（確定ルール）になり、次の案づくりで必ず読まれる。
 * アプリは AI を呼ばない。
 */

export const UIUX_APPS = ["dashboard", "kurashift", "loopware"] as const;
export type UiuxApp = (typeof UIUX_APPS)[number];

export const UIUX_APP_LABEL: Record<UiuxApp, string> = {
  dashboard: "ジャービスダッシュボード",
  kurashift: "KURASHIFT",
  loopware: "ループウェア（Nody）",
};

/** 案ごとの判断（迷うは違うに混ぜない） */
export const PLAN_VERDICTS = ["good", "wrong", "hesitated"] as const;
export type PlanVerdict = (typeof PLAN_VERDICTS)[number];

export type UiuxPlan = {
  id: string; // 例 "A"
  label: string;
  summary: string;
  image?: string; // https の URL、または "storage:<bucket内のパス>"（uiux-shots バケット。サーバが署名付き URL にする）
  points: string[]; // この案のポイント（短く）
  applied: string[]; // この案で使った好みルール（R800-xxx か ルール鍵）
};

export type UiuxProposal = {
  id: string; // 例 "P1"
  text: string; // 好みルールの文（次の画面づくりに効かせる）
  why: string; // 根拠（どの直しから）
  evidence?: string[];
  concept?: string; // 採点表の項目名（例 "情報の優先度"）
  app?: UiuxApp | "*"; // 効かせる範囲（既定は全アプリ）
};

export type UiuxRound = {
  id: string; // 例 "2026-11-14-home-reorder"
  title: string;
  app: UiuxApp | "*";
  screen?: string;
  pr?: number;
  stage: "plan" | "review" | "done";
  created_at?: string;
  note?: string;
  plans: UiuxPlan[];
  proposals: UiuxProposal[];
};

export type UiuxRule = {
  key: string; // `${roundId}:${proposalId}`
  roundId: string;
  text: string;
  concept: string | null;
  app: string;
  at: string;
};

function str(v: unknown, n: number): string {
  return v === null || v === undefined ? "" : String(v).trim().slice(0, n);
}

function strList(v: unknown, n: number, max: number): string[] {
  if (!Array.isArray(v)) return [];
  return v.map((x) => str(x, n)).filter(Boolean).slice(0, max);
}

const ID_RE = /^[A-Za-z0-9_-]{1,40}$/;
export const ROUND_RE = /^[A-Za-z0-9_.-]{1,80}$/;

function appOf(v: unknown): UiuxApp | "*" {
  const s = str(v, 20);
  return (UIUX_APPS as readonly string[]).includes(s) ? (s as UiuxApp) : "*";
}

/** 画像の指定を検証する。https か storage: のみ通す */
export function cleanImage(v: unknown): string | undefined {
  const s = str(v, 500);
  if (/^https:\/\/[^\s"'<>]+$/.test(s)) return s;
  if (/^storage:[A-Za-z0-9_./-]{1,200}$/.test(s) && !s.includes("..")) return s;
  return undefined;
}

/** sync_meta に置かれた JSON を検証して形を揃える。壊れていれば null */
export function parseRound(raw: unknown): UiuxRound | null {
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
  if (!ROUND_RE.test(id) || !title) return null;
  const stage = o.stage === "review" || o.stage === "done" ? o.stage : "plan";
  const pr = Number(o.pr);
  const plans: UiuxPlan[] = (Array.isArray(o.plans) ? o.plans : [])
    .map((p) => {
      const x = (p || {}) as Record<string, unknown>;
      return {
        id: str(x.id, 40),
        label: str(x.label, 80),
        summary: str(x.summary, 600),
        image: cleanImage(x.image),
        points: strList(x.points, 120, 8),
        applied: strList(x.applied, 120, 10),
      };
    })
    .filter((p) => ID_RE.test(p.id) && p.label)
    .slice(0, 4);
  const proposals: UiuxProposal[] = (Array.isArray(o.proposals) ? o.proposals : [])
    .map((p) => {
      const x = (p || {}) as Record<string, unknown>;
      return {
        id: str(x.id, 40),
        text: str(x.text, 300),
        why: str(x.why, 600),
        evidence: strList(x.evidence, 200, 5),
        concept: str(x.concept, 60) || undefined,
        app: appOf(x.app),
      };
    })
    .filter((p) => ID_RE.test(p.id) && p.text)
    .slice(0, 8);
  return {
    id,
    title,
    app: appOf(o.app),
    screen: str(o.screen, 80) || undefined,
    pr: Number.isInteger(pr) && pr > 0 ? pr : undefined,
    stage,
    created_at: str(o.created_at, 40) || undefined,
    note: str(o.note, 600) || undefined,
    plans,
    proposals,
  };
}

export function ruleKey(roundId: string, proposalId: string): string {
  return `${roundId}:${proposalId}`;
}

type Row = { action: string; target_id: string; payload?: Record<string, unknown> | null; decided_at?: string | null };

function byTime(rows: Row[]): Row[] {
  return [...rows].sort((a, b) => String(a.decided_at || "").localeCompare(String(b.decided_at || "")));
}

/** uiux_rule の行から、いま効いている好みルール（新しい判断が勝つ。取り消しは外す） */
export function adoptedUiuxRules(rows: Row[]): UiuxRule[] {
  const last = new Map<string, Row>();
  for (const r of byTime(rows)) last.set(r.target_id, r);
  const out: UiuxRule[] = [];
  for (const [key, r] of last) {
    if (r.action !== "rule_accept") continue;
    const pl = (r.payload || {}) as Record<string, unknown>;
    out.push({
      key,
      roundId: str(pl.round_id, 80) || key.split(":")[0],
      text: str(pl.text, 300),
      concept: str(pl.concept, 60) || null,
      app: str(pl.app, 20) || "*",
      at: str(r.decided_at, 40),
    });
  }
  return out.sort((a, b) => b.at.localeCompare(a.at));
}

/** このラウンドで判断済みのルール案（proposalId → action） */
export function decidedProposals(rows: Row[], roundId: string): Record<string, string> {
  const out: Record<string, string> = {};
  for (const r of byTime(rows)) {
    if (r.target_id.startsWith(`${roundId}:`)) out[r.target_id.slice(roundId.length + 1)] = r.action;
  }
  return out;
}

export type PlanPick = {
  chosen: string | null; // 選んだ案。null は「どれも違う」
  verdicts: Record<string, PlanVerdict>;
  tags: Record<string, string[]>;
};

/** 送れる状態か：案を1つ選ぶ、または「どれも違う」（全案に何か判断がある） */
export function pickComplete(round: UiuxRound, pick: PlanPick): boolean {
  if (!round.plans.length) return false;
  if (pick.chosen) return round.plans.some((p) => p.id === pick.chosen);
  return round.plans.every((p) => pick.verdicts[p.id] === "wrong" || pick.verdicts[p.id] === "hesitated");
}

/** 判断ログの action：選んだら adopt、どれも違うなら none_fit（NG）、全部迷うなら hesitated */
export function pickAction(round: UiuxRound, pick: PlanPick): "adopt" | "reject" | "hesitated" {
  if (pick.chosen) return "adopt";
  return round.plans.every((p) => pick.verdicts[p.id] === "hesitated") ? "hesitated" : "reject";
}
