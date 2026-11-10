/**
 * 313 片付け — 押した件のボタンを「報告済み」表示に差し替える（純関数）。
 * 他の件のボタンは残す。押したことが一覧の上で分かるようにする（Slack FB 2026-11-10）。
 */
export type SlackBlock = Record<string, unknown>;

export function t313DoneLabel(
  action: "close" | "reschedule" | "drop",
  ok: boolean,
  due?: string,
): string {
  if (!ok) {
    return action === "close"
      ? "❌ 完了に失敗（もう一度押すかアプリで）"
      : action === "drop"
        ? "❌ やめるに失敗（もう一度押すかアプリで）"
        : "❌ 延期に失敗（もう一度押すかアプリで）";
  }
  if (action === "close") return "✅ 報告済み — 済んだ（Todoist 完了）";
  if (action === "drop") return "🗑 報告済み — やめる（完了＋コメント）";
  return `📅 報告済み — ${due || "?"} へ延期`;
}

/**
 * blockId の actions ブロックを context ブロックに置き換えた新しい配列を返す。
 * 失敗時はボタンを残し、直後に失敗の一言を足す。見つからなければ null。
 */
export function markT313RowDone(
  blocks: SlackBlock[],
  blockId: string,
  label: string,
  ok: boolean,
): SlackBlock[] | null {
  if (!Array.isArray(blocks) || !blockId) return null;
  const noteId = `${blockId}_done`.slice(0, 255);
  // 前回の失敗メモは消してから付け直す（同じ行に重ならない）
  blocks = blocks.filter((b) => !(b && b.block_id === noteId));
  const idx = blocks.findIndex(
    (b) => b && b.type === "actions" && b.block_id === blockId,
  );
  if (idx < 0) return null;
  const note: SlackBlock = {
    type: "context",
    block_id: noteId,
    elements: [{ type: "mrkdwn", text: `*${label}*` }],
  };
  const out = blocks.slice();
  if (ok) {
    out.splice(idx, 1, note);
  } else {
    out.splice(idx + 1, 0, note);
  }
  return out;
}
