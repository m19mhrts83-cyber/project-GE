// (2) 回答の評価に「どのAIで作った答えか」を結び付ける（2026-11-11 松野さん）。
// 答えを作ったとき（使い回したときも）に qa_answer_meta へ1行書き、評価のときに答えの本文のハッシュで引く。
// 本文そのものは持たない。読めない・書けないときは評価も回答も止めない（空＝不明として残る）。
export type AnswerMeta = { mode: 'normal' | 'fast' | 'semantic' | 'deep'; tier: 'lite' | 'standard'; model: string; reused: boolean };
// 通常・高速は Raimo の YAML（sendMessage / sendMessageFast）の固定モデル。YAML を変えたらここも変える。
export const RAIMO_ANSWER_MODEL = 'gemini-3-flash-preview';

export async function answerHash(answer: string): Promise<string> {
  const bytes = new Uint8Array(await crypto.subtle.digest('SHA-256', new TextEncoder().encode('qa-answer-v1\u0000' + String(answer || '').trim())));
  return Array.from(bytes, b => b.toString(16).padStart(2, '0')).join('');
}

const MODEL = /^[a-z0-9.\-]{1,80}$/;
export function cleanMeta(m: Partial<AnswerMeta> | null | undefined): AnswerMeta | null {
  if (!m || !['normal', 'fast', 'semantic', 'deep'].includes(String(m.mode))) return null;
  return { mode: m.mode as AnswerMeta['mode'], tier: m.tier === 'lite' ? 'lite' : 'standard',
    model: MODEL.test(String(m.model || '')) ? String(m.model) : '', reused: m.reused === true };
}

// 評価の行に足す列。meta が無ければ何も足さない（移行前でも評価の保存は今までどおり通る）。
export function feedbackMetaColumns(m: AnswerMeta | null) {
  return m ? { answer_mode: m.mode, answer_tier: m.tier, answer_model: m.model || null, answer_reused: m.reused } : {};
}
