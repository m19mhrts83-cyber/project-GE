// (2) 回答の評価（いいね／悪いね／超いいね＋意見）。2026-11-10。
// 段階公開スイッチ answer_feedback が見える人だけが使える（requireFeature）。
// 質問と回答の本文はブラウザから受け取らず、サーバーが本人のチャットから引き直して保存する。
export const RATINGS = ['good', 'bad', 'great'] as const;
export type Rating = typeof RATINGS[number];
export type FeedbackInput = { chat_id: string; message_id: string; rating: Rating; comment: string };
export class FeedbackError extends Error {
  code: string; status: number;
  constructor(code: string, status = 400) { super(code); this.code = code; this.status = status; }
}
const ID = /^[a-zA-Z0-9_-]{1,100}$/;

export function parseFeedback(input: Record<string, unknown>): FeedbackInput {
  const chat_id = String(input.chat_id ?? ''), message_id = String(input.message_id ?? ''), rating = String(input.rating ?? '');
  if (!ID.test(chat_id) || !ID.test(message_id) || !(RATINGS as readonly string[]).includes(rating)) throw new FeedbackError('invalid_feedback');
  const comment = typeof input.comment === 'string' ? input.comment.trim() : '';
  if (comment.length > 1000) throw new FeedbackError('invalid_feedback');
  return { chat_id, message_id, rating: rating as Rating, comment };
}

type Msg = { id?: unknown; role?: unknown; content?: unknown };
// 評価する回答と、その直前の質問を本人のチャットから探す。見つからなければ 404。
export function feedbackRow(userId: string, f: FeedbackInput, messages: Msg[]) {
  const i = messages.findIndex(m => String(m?.id ?? '') === f.message_id);
  if (i < 0 || messages[i].role !== 'assistant') throw new FeedbackError('answer_not_found', 404);
  let q = '';
  for (let j = i - 1; j >= 0; j--) if (messages[j].role === 'user') { q = String(messages[j].content ?? ''); break; }
  return { user_id: userId, chat_id: f.chat_id, message_id: f.message_id, rating: f.rating, comment: f.comment,
    question: q.slice(0, 2000), answer: String(messages[i].content ?? '').slice(0, 8000), updated_at: new Date().toISOString() };
}
