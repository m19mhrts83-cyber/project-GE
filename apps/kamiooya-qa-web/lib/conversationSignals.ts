// うまくいかなかった可能性のある会話を、評価（いいね/悪いね）が無くても操作の記録から拾う（2026-11-11）。
// AI は使わない。質問の記録（qa_answer_jobs）・根拠のクリック・評価を、チャットごとに並べて目印を数えるだけ。
export type SignalJob = { user_id: string; chat_id: string; mode: string; query: string; status: string; error_code?: string | null; created_at: string; answer?: string | null };
export type SignalCode = 'rephrase' | 'followup' | 'deep_retry' | 'refusal' | 'failed' | 'bad_rating' | 'no_source_open';
export const SIGNAL_LABELS: Record<SignalCode, string> = {
  rephrase: 'すぐに似た質問で言い直し',
  followup: '「もっと詳しく」「違う」などの続きの質問',
  deep_retry: '答えの後に「より詳しく調べる」で聞き直し',
  refusal: '「確証が取れない」と断った答え',
  failed: '答えを作れなかった（時間切れ・失敗）',
  bad_rating: '悪いねが付いた',
  no_source_open: '1回で終わり、根拠を1つも開いていない',
};
// 重み。強い目印ほど上に並ぶ。「1回で終わり・根拠を開かない」は満足して終わった場合もあるので弱め。
const WEIGHT: Record<SignalCode, number> = { rephrase: 3, followup: 2, deep_retry: 3, refusal: 3, failed: 2, bad_rating: 4, no_source_open: 1 };

const FOLLOWUP = /もっと|詳しく|くわしく|違う|ちがう|そうじゃな|そうではな|わから|分から|意味が|もう一度|再度|ほかに|他に|具体的に|さっき|先ほど|前の/;
const REFUSAL = /確証が取れない|お答えすることができません/;

const bigrams = (s: string) => {
  const t = String(s || '').replace(/[\s、。！？!?「」（）()・,.]/g, '');
  const out = new Set<string>();
  for (let i = 0; i < t.length - 1; i++) out.add(t.slice(i, i + 2));
  return out;
};
export function similarity(a: string, b: string): number {
  const x = bigrams(a), y = bigrams(b);
  if (!x.size || !y.size) return 0;
  let both = 0;
  x.forEach(g => { if (y.has(g)) both++; });
  return both / (x.size + y.size - both);
}

export type FlaggedTurn = { at: string; mode: string; question: string; answer: string; signals: SignalCode[] };
export type FlaggedChat = { chat_id: string; user_id: string; score: number; signals: SignalCode[]; last_at: string; turns: FlaggedTurn[] };

export function findTroubledChats(jobs: SignalJob[], clicks: { chat_id?: string }[] = [], feedback: { chat_id?: string; rating?: string }[] = [], limit = 50): FlaggedChat[] {
  const clicked = new Set(clicks.map(c => String(c?.chat_id || '')));
  const bad = new Set(feedback.filter(f => f?.rating === 'bad').map(f => String(f?.chat_id || '')));
  const byChat = new Map<string, SignalJob[]>();
  for (const j of jobs) {
    if (!j || !j.chat_id || !j.query || j.status === 'running') continue;
    const list = byChat.get(j.chat_id) || [];
    list.push(j); byChat.set(j.chat_id, list);
  }
  const out: FlaggedChat[] = [];
  byChat.forEach((list, chatId) => {
    list.sort((a, b) => Date.parse(a.created_at) - Date.parse(b.created_at));
    const turns: FlaggedTurn[] = list.map((j, i) => {
      const s: SignalCode[] = [];
      const prev = list[i - 1];
      const gap = prev ? (Date.parse(j.created_at) - Date.parse(prev.created_at)) / 60000 : Infinity;
      if (prev && gap <= 15 && similarity(prev.query, j.query) >= 0.45) s.push('rephrase');
      if (prev && gap <= 60 && j.query.length <= 60 && FOLLOWUP.test(j.query)) s.push('followup');
      if (prev && gap <= 60 && j.mode === 'deep' && prev.mode !== 'deep') s.push('deep_retry');
      if (j.status === 'failed') s.push('failed');
      else if (REFUSAL.test(String(j.answer || '')) && String(j.answer || '').length < 200) s.push('refusal');
      return { at: j.created_at, mode: j.mode, question: j.query.slice(0, 300), answer: String(j.answer || '').slice(0, 300), signals: s };
    });
    const chatSignals: SignalCode[] = [];
    if (bad.has(chatId)) chatSignals.push('bad_rating');
    // 「1回で終わり・根拠を開かない」は、ほかの目印が無いときだけ付ける（重複して数えない）。
    if (!turns.some(t => t.signals.length) && !chatSignals.length && list.length === 1 && list[0].status === 'done' && !clicked.has(chatId)) chatSignals.push('no_source_open');
    const all = [...turns.flatMap(t => t.signals), ...chatSignals];
    if (!all.length) return;
    const score = all.reduce((n, c) => n + WEIGHT[c], 0);
    out.push({ chat_id: chatId, user_id: list[0].user_id, score, signals: [...new Set(all)], last_at: list[list.length - 1].created_at, turns });
  });
  // 弱い目印（1回で終わり）だけの会話は数が多くなるので、強い目印のある会話を先に、同点は新しい順。
  return out.sort((a, b) => b.score - a.score || Date.parse(b.last_at) - Date.parse(a.last_at)).slice(0, limit);
}

export function summarizeSignals(chats: FlaggedChat[]) {
  const counts: Record<string, number> = {};
  chats.forEach(c => c.signals.forEach(s => { counts[s] = (counts[s] || 0) + 1; }));
  return counts;
}
