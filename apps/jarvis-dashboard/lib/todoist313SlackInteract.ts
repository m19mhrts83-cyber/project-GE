/**
 * Slack Interactivity — 313 完了／期日延期ボタン
 */
import {
  applyT313Action,
  parseT313ButtonValue,
  type Todoist313Action,
} from "@/lib/todoist313SlackAction";
import { postResponseUrl } from "@/lib/vendorReplySlackInteract";

export type T313BlockResult =
  | {
      kind: "ephemeral" | "error";
      text: string;
    }
  | {
      kind: "ok";
      text: string;
      blocks: Array<Record<string, unknown>>;
    };

export async function handleT313BlockAction(opts: {
  value: string;
  responseUrl?: string;
}): Promise<T313BlockResult> {
  const parsed = parseT313ButtonValue(opts.value);
  if (!parsed) {
    return { kind: "error", text: "313: ボタン値が不正です" };
  }
  const result = await applyT313Action({
    action: parsed.action,
    taskId: parsed.taskId,
    due: parsed.due,
    source: "slack_button",
  });
  const icon = result.ok ? "✅" : "❌";
  const title =
    parsed.action === "close"
      ? result.ok
        ? "完了しました"
        : "完了に失敗"
      : result.ok
        ? "期日を延期しました"
        : "延期に失敗";
  const text = `${icon} *313 ${title}*\n${result.message}`;
  const blocks = [
    {
      type: "section",
      text: { type: "mrkdwn", text },
    },
  ];

  // 一覧メッセージ全体を消さない（他件のボタンを残す）→ ephemeral
  if (opts.responseUrl) {
    await postResponseUrl(opts.responseUrl, {
      response_type: "ephemeral",
      text: `${icon} ${title}\n${result.message}`,
      replace_original: false,
    });
  }

  if (!result.ok) {
    return { kind: "error", text: `${icon} ${title}\n${result.message}` };
  }
  return {
    kind: "ephemeral",
    text: `${icon} ${title}\n${result.message}`,
  };
}

export function t313ConfirmHtml(opts: {
  action: Todoist313Action;
  taskId: string;
  due?: string;
  sig: string;
}): string {
  const esc = (s: string) =>
    String(s || "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  const isClose = opts.action === "close";
  const title = isClose ? "完了の確認" : "期日延期の確認";
  const label = isClose ? "完了する" : `${opts.due || "?"} へ延期する`;
  const note = isClose
    ? "Todoist でこのタスクを完了（コメント付き）します。"
    : `期日を ${esc(opts.due || "")} に変更します（コメント付き）。`;
  const dueField = !isClose
    ? `<input type="hidden" name="due" value="${esc(opts.due || "")}"/>`
    : "";
  return `<!doctype html><html lang="ja"><meta charset="utf-8"/>
<title>${esc(title)}</title>
<body style="font-family:system-ui;padding:2rem;max-width:36rem;color:#111">
<h1 style="font-size:1.25rem">${esc(title)}</h1>
<p style="color:#4b5563">${note}</p>
<p style="color:#6b7280;font-size:0.85rem">task=${esc(opts.taskId)}</p>
<form method="POST" action="">
<input type="hidden" name="s" value="${esc(opts.sig)}"/>
${dueField}
<div style="margin-top:1.25rem;display:flex;gap:0.75rem;flex-wrap:wrap">
<button type="submit" name="intent" value="confirm" style="background:${isClose ? "#15803d" : "#1d4ed8"};color:#fff;border:0;padding:0.65rem 1.1rem;border-radius:8px;font-weight:600">${esc(label)}</button>
</div>
</form>
<p style="margin-top:1.5rem;color:#9ca3af;font-size:0.8rem">リンクを開いただけでは実行しません（確認ボタン必須）。</p>
</body></html>`;
}
