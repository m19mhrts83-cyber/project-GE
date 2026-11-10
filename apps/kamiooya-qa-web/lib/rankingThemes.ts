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
    topic: str(x?.topic, 80), count: num(x?.count), chatbot: num(x?.chatbot), forum: num(x?.forum), openchat: num(x?.openchat),
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
    stats: { chatbot: num(s.chatbot), forum: num(s.forum), openchat: num(s.openchat), courses: num(s.courses) } };
}

export function decisionRow(userId: string, d: ThemeDecisionInput) {
  return { ...d, decided_by: userId, decided_at: new Date().toISOString() };
}
