// (4) 質問ランキング＋講座テーマ提案（2026-11-11）。段階公開スイッチ ranking_themes が見える管理者だけ。
// 週次の Actions（scripts/course_theme/weekly_round.py）が qa_theme_rounds に案を入れ、
// 運営分析で 採用／直して採用／不採用＋理由 を残す。次の回はその判断を読んで案を作る（ループウェア）。
export const CHOICES = ['adopt', 'revise', 'reject'] as const;
export type Choice = typeof CHOICES[number];
export class ThemeError extends Error {
  code: string; status: number;
  constructor(code: string, status = 400) { super(code); this.code = code; this.status = status; }
}
const ROUND = /^r[0-9]{8}[a-z0-9_-]{0,20}$/;
const THEME = /^t[0-9]{1,2}$/;

export type ThemeDecisionInput = { round_id: string; theme_id: string; choice: Choice; revised_title: string; reason: string };

export function parseThemeDecision(input: Record<string, unknown>): ThemeDecisionInput {
  const round_id = String(input.round_id ?? ''), theme_id = String(input.theme_id ?? ''), choice = String(input.choice ?? '');
  if (!ROUND.test(round_id) || !THEME.test(theme_id) || !(CHOICES as readonly string[]).includes(choice)) throw new ThemeError('invalid_request');
  const reason = typeof input.reason === 'string' ? input.reason.trim() : '';
  const revised_title = typeof input.revised_title === 'string' ? input.revised_title.trim() : '';
  if (reason.length > 1000 || revised_title.length > 200) throw new ThemeError('invalid_request');
  // 「直して採用」は直した題名が要る。ほかの選択では題名は持たない。
  if (choice === 'revise' && !revised_title) throw new ThemeError('invalid_request');
  return { round_id, theme_id, choice: choice as Choice, revised_title: choice === 'revise' ? revised_title : '', reason };
}

const str = (v: unknown, n: number) => String(v ?? '').slice(0, n);
const num = (v: unknown) => { const x = Number(v); return Number.isFinite(x) && x >= 0 ? Math.round(x) : 0; };

// DB の行を画面向けに整える（決まった項目だけ、長さも切る）。
export function shapeRound(r: any, decisions: any[]) {
  const ranking = (Array.isArray(r?.ranking) ? r.ranking : []).slice(0, 30).map((x: any) => ({
    // count＝Q&Aチャットで聞かれた回数、people＝聞いた人数（どちらも質問ログから数えた値。11/11 見直し）。
    // chatbot/forum/openchat は 11/11 朝の第1回（AI の目安）だけが持つ古い形。
    topic: str(x?.topic, 80), count: num(x?.count), people: x?.people == null ? null : num(x.people), variants: num(x?.variants),
    chatbot: num(x?.chatbot), forum: num(x?.forum), openchat: num(x?.openchat),
    examples: (Array.isArray(x?.examples) ? x.examples : []).slice(0, 3).map((e: unknown) => str(e, 140)),
  }));
  const byTheme = new Map<string, any>();
  for (const d of decisions || []) if (d && d.round_id === r?.id) byTheme.set(String(d.theme_id), d);
  const themes = (Array.isArray(r?.themes) ? r.themes : []).slice(0, 8).map((t: any) => {
    const d = byTheme.get(String(t?.id));
    return { id: str(t?.id, 4), title: str(t?.title, 120), why: str(t?.why, 400), evidence: str(t?.evidence, 400),
      format: str(t?.format, 120), target: str(t?.target, 120),
      decision: d ? { choice: d.choice, revised_title: str(d.revised_title, 200), reason: str(d.reason, 1000), decided_at: d.decided_at } : null };
  });
  const s = r?.stats && typeof r.stats === 'object' ? r.stats : {};
  return { id: str(r?.id, 40), created_at: r?.created_at ?? null, period_days: num(r?.period_days), model: str(r?.model, 60), ranking, themes,
    stats: { chatbot: num(s.chatbot), chatbot_users: num(s.chatbot_users), forum: num(s.forum), openchat: num(s.openchat), courses: num(s.courses) } };
}

export function decisionRow(userId: string, d: ThemeDecisionInput) {
  return { ...d, decided_by: userId, decided_at: new Date().toISOString() };
}

// 画面から作り直す（2026-11-23 松野さん「好きなタイミングで集計したい」）。
// 押すと GitHub Actions course-theme weekly を起動する（Gemini 従量）。重複して押されないよう、
// 作成中（依頼から RUNNING_MS 以内で、まだ新しい回ができていない）は受け付けない。1日の上限も持つ。
export const REBUILD_RUNNING_MS = 40 * 60 * 1000;
export const REBUILD_DAILY_LIMIT = 5;
export type RebuildRequest = { requested_by?: unknown; requested_at?: unknown; dispatched?: unknown };
const ms = (v: unknown) => { const t = Date.parse(String(v ?? '')); return Number.isFinite(t) ? t : 0; };

// 直近の依頼（新しい順）と最新の回の作成日時から、今の状態を決める。
//  idle: 作り直せる / running: 作成中 / limit: 今日の上限に達した
export function rebuildState(requests: RebuildRequest[], latestRoundAt: unknown, now: number) {
  const ok = (Array.isArray(requests) ? requests : []).filter(r => r && r.dispatched === true && ms(r.requested_at) > 0)
    .sort((a, b) => ms(b.requested_at) - ms(a.requested_at));
  const last = ok[0];
  const lastAt = last ? ms(last.requested_at) : 0;
  const running = !!last && now - lastAt < REBUILD_RUNNING_MS && ms(latestRoundAt) < lastAt;
  // 40分たっても新しい回ができていない時は、作れなかった可能性がある（もう一度押せる）。
  const stale = !!last && !running && ms(latestRoundAt) < lastAt;
  const today = ok.filter(r => now - ms(r.requested_at) < 24 * 60 * 60 * 1000).length;
  const state = running ? 'running' : today >= REBUILD_DAILY_LIMIT ? 'limit' : 'idle';
  return { state, last_requested_at: last ? new Date(lastAt).toISOString() : null, last_requested_by: last ? String(last.requested_by ?? '') : '', maybe_failed: stale, today };
}
