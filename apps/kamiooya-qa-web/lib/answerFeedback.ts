// (2) 回答の評価（いいね／悪いね／超いいね＋意見）。2026-11-10。
// 段階公開スイッチ answer_feedback が見える人だけが使える（requireFeature）。
// 質問と回答の本文はブラウザから受け取らず、サーバーが本人のチャットから引き直して保存する。
export const RATINGS = ['good', 'bad', 'great'] as const;
export type Rating = typeof RATINGS[number];
// 超いいね・悪いねの理由は決まった選択肢から複数選ぶ（11/10 松野さん）。分析で数えやすいよう英字コードで保存する。
// 悪いねの選択肢は、直す場所（知識・検索・答え方・書き方・出典）に1対1で対応させている。
export const REASONS: Record<string, readonly string[]> = {
  great: ['accurate', 'practical', 'clear', 'source', 'new_view'],
  bad: ['wrong', 'off_topic', 'vague', 'hard_to_read', 'no_source'],
  good: [],
};
export type FeedbackInput = { chat_id: string; message_id: string; rating: Rating; reasons: string[]; comment: string };
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
  const raw = input.reasons == null ? [] : input.reasons;
  if (!Array.isArray(raw) || raw.length > 10) throw new FeedbackError('invalid_feedback');
  const allowed = REASONS[rating];
  const reasons = [...new Set(raw.map(x => String(x)))];
  if (reasons.some(x => !allowed.includes(x))) throw new FeedbackError('invalid_feedback');
  // 選択肢の順にそろえる（同じ組み合わせが同じ並びで保存される）
  return { chat_id, message_id, rating: rating as Rating, reasons: allowed.filter(x => reasons.includes(x)), comment };
}

type Msg = { id?: unknown; role?: unknown; content?: unknown };
// 評価する回答と、その直前の質問を本人のチャットから探す。見つからなければ 404。
export function feedbackRow(userId: string, f: FeedbackInput, messages: Msg[]) {
  const i = messages.findIndex(m => String(m?.id ?? '') === f.message_id);
  if (i < 0 || messages[i].role !== 'assistant') throw new FeedbackError('answer_not_found', 404);
  let q = '';
  for (let j = i - 1; j >= 0; j--) if (messages[j].role === 'user') { q = String(messages[j].content ?? ''); break; }
  return { user_id: userId, chat_id: f.chat_id, message_id: f.message_id, rating: f.rating, reasons: f.reasons, comment: f.comment,
    question: q.slice(0, 2000), answer: String(messages[i].content ?? '').slice(0, 8000), updated_at: new Date().toISOString() };
}
