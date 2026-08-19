/** ローカル Cursor へのハンドオフ・パッケージ */

export type HandoffComment = { role: string; body: string };

export function buildLocalHandoffPrompt(opts: {
  kind: "card" | "watch";
  id: string;
  title: string;
  summary?: string | null;
  detail?: string | null;
  question?: string | null;
  bullets?: string[];
  lane?: string | null;
  cursorPrompt?: string | null;
  comments?: HandoffComment[];
  lastUserMessage?: string | null;
  extraNote?: string | null;
}): string {
  const bullets = (opts.bullets || []).filter(Boolean).slice(0, 20);
  const thread = (opts.comments || [])
    .slice(-16)
    .map((c) => `[${c.role}] ${c.body}`)
    .join("\n");

  return [
    "【ローカル Cursor 用】Jarvis ダッシュボードからの引き継ぎ",
    `種別: ${opts.kind === "card" ? "タスク／確認テーマ" : "状況ウォッチ"}`,
    `id: ${opts.id}`,
    opts.lane ? `レーン: ${opts.lane}` : "",
    `タイトル: ${opts.title}`,
    opts.question ? `問い: ${opts.question}` : "",
    `要約:\n${opts.summary || "—"}`,
    opts.detail ? `詳細:\n${opts.detail}` : "",
    bullets.length
      ? `候補メモ:\n${bullets.map((l) => (l.startsWith("-") ? l : `- ${l}`)).join("\n")}`
      : "",
    opts.cursorPrompt
      ? `参考メモ:\n${String(opts.cursorPrompt).slice(0, 800)}`
      : "",
    thread ? `直近のやり取り:\n${thread}` : "直近のやり取り: （なし）",
    opts.lastUserMessage
      ? `今回のメッセージ:\n${opts.lastUserMessage}`
      : "",
    opts.extraNote?.trim()
      ? `ユーザー追記（不満・Macでやってほしいこと）:\n${opts.extraNote.trim()}`
      : "",
    "-----",
    "ローカル Cursor 用。必要ならファイル操作・Notion・CHRLINE 等を実行してよい。",
    "返答をダッシュボードに戻す場合は、カード／ウォッチのコメントとして短く要約してよい。",
  ]
    .filter(Boolean)
    .join("\n");
}

export type CursorAskState = {
  status: "queued" | "running" | "done" | "error";
  prompt?: string;
  question?: string;
  requested_at?: string;
  started_at?: string;
  finished_at?: string;
  error?: string;
  via?: string;
  reply?: string;
};
