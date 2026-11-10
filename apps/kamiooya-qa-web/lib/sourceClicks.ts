// (2) 判断ログの補足: 会員が答えの根拠を開いた記録（2026-11-10 松野さん）。
// 「本文を見る」「元動画ページを開く」「講座を開く」などを押したら、どの根拠を参考にしたかを残す。
// スイッチ answer_feedback が見える人だけ。引用の一覧はブラウザ側にしか無いため、根拠の名前は画面から受け取り、長さを切って保存する。
// 質問はサーバーが本人のチャットから引き直す。
export const SOURCE_KINDS = ['comment', 'openchat', 'lesson', 'video_chunk'] as const;
export const SOURCE_ACTIONS = ['open_text', 'open_link', 'jump'] as const;
export type SourceClick = { chat_id: string; message_id: string; kind: string; source_key: string; action: string; title: string; label: string };
export class SourceClickError extends Error {
  code: string; status: number;
  constructor(code: string, status = 400) { super(code); this.code = code; this.status = status; }
}
const ID = /^[a-zA-Z0-9_-]{1,100}$/;

export function parseSourceClick(input: Record<string, unknown>): SourceClick {
  const chat_id = String(input.chat_id ?? ''), message_id = String(input.message_id ?? '');
  const kind = String(input.kind ?? ''), source_key = String(input.source_key ?? '').trim(), action = String(input.action ?? '');
  if (!ID.test(chat_id) || !ID.test(message_id) || !(SOURCE_KINDS as readonly string[]).includes(kind)
    || !source_key || source_key.length > 300 || !(SOURCE_ACTIONS as readonly string[]).includes(action)) throw new SourceClickError('invalid_request');
  const title = String(input.title ?? '').replace(/\s+/g, ' ').trim().slice(0, 300) || source_key.slice(0, 300);
  const label = String(input.label ?? '').trim().slice(0, 50);
  return { chat_id, message_id, kind, source_key, action, title, label };
}

type Msg = { id?: unknown; role?: unknown; content?: unknown };
// 押した回答が本人のチャットにあるかを確かめて、保存する行を作る。無ければ 404。
export function sourceClickRow(userId: string, s: SourceClick, messages: Msg[]) {
  const i = messages.findIndex(m => String(m?.id ?? '') === s.message_id);
  if (i < 0 || messages[i].role !== 'assistant') throw new SourceClickError('answer_not_found', 404);
  let q = '';
  for (let j = i - 1; j >= 0; j--) if (messages[j].role === 'user') { q = String(messages[j].content ?? ''); break; }
  return { user_id: userId, chat_id: s.chat_id, message_id: s.message_id, kind: s.kind, source_key: s.source_key.slice(0, 300),
    title: s.title, label: s.label, action: s.action,
    question: q.slice(0, 2000), clicked_at: new Date().toISOString() };
}

// 運営分析用: 評価に「開いた根拠」を付け、よく参考にされた根拠を多い順に数える。会員のIDは外に出さない。
type ClickRow = { user_id?: unknown; chat_id?: unknown; message_id?: unknown; kind?: unknown; source_key?: unknown; title?: unknown; label?: unknown };
export function summarizeSourceClicks(clicks: ClickRow[], limit = 20) {
  const byMessage = new Map<string, { kind: string; title: string; label: string }[]>();
  const counts = new Map<string, { kind: string; title: string; people: Set<string>; answers: Set<string> }>();
  for (const r of clicks) {
    const msg = String(r.chat_id ?? '') + '/' + String(r.message_id ?? '');
    const kind = String(r.kind ?? ''), title = String(r.title ?? ''), key = kind + '\0' + String(r.source_key ?? '');
    const list = byMessage.get(msg) || [];
    if (!list.some(x => x.kind === kind && x.title === title)) list.push({ kind, title, label: String(r.label ?? '') });
    byMessage.set(msg, list);
    const c = counts.get(key) || { kind, title, people: new Set<string>(), answers: new Set<string>() };
    c.people.add(String(r.user_id ?? '')); c.answers.add(msg);
    counts.set(key, c);
  }
  const top = [...counts.values()].map(c => ({ kind: c.kind, title: c.title, people: c.people.size, answers: c.answers.size }))
    .sort((a, b) => b.people - a.people || b.answers - a.answers || a.title.localeCompare(b.title)).slice(0, limit);
  return { byMessage, top };
}
