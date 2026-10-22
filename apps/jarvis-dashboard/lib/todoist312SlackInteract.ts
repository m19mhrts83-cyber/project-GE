/**
 * Slack Interactivity — 312 起票／見送りボタン
 */
import {
  applyT312Action,
  parseT312ButtonValue,
  type Todoist312Action,
  type T312Proposal,
} from "@/lib/todoist312SlackAction";
import { postResponseUrl } from "@/lib/vendorReplySlackInteract";

export type T312BlockResult =
  | {
      kind: "ephemeral" | "error";
      text: string;
    }
  | {
      kind: "ok";
      text: string;
      blocks: Array<Record<string, unknown>>;
    };

export async function handleT312BlockAction(opts: {
  value: string;
  responseUrl?: string;
}): Promise<T312BlockResult> {
  const parsed = parseT312ButtonValue(opts.value);
  if (!parsed) {
    return { kind: "error", text: "312: ボタン値が不正または署名エラーです" };
  }
  const result = await applyT312Action({
    action: parsed.action,
    proposal: parsed.proposal,
    source: "slack_button",
  });
  const icon = result.ok ? "✅" : "❌";
  const title =
    parsed.action === "create"
      ? result.ok
        ? "起票しました"
        : "起票に失敗"
      : result.ok
        ? "見送りました"
        : "見送りに失敗";
  const text = `${icon} *312 ${title}*\n${result.message}`;

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

export function t312ConfirmHtml(opts: {
  action: Todoist312Action;
  proposal: T312Proposal;
  payloadB64: string;
  sig: string;
}): string {
  const esc = (s: string) =>
    String(s || "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  const isCreate = opts.action === "create";
  const title = isCreate ? "起票の確認" : "見送りの確認";
  const label = isCreate ? "起票する" : "見送る";
  const note = isCreate
    ? "Todoist にこの候補を起票します（コメント付き）。"
    : "この候補を見送りとして扱います（ローカル digest の dismiss は別途）。";
  return `<!doctype html><html lang="ja"><meta charset="utf-8"/>
<title>${esc(title)}</title>
<body style="font-family:system-ui;padding:2rem;max-width:36rem;color:#111">
<h1 style="font-size:1.25rem">${esc(title)}</h1>
<p style="color:#4b5563">${note}</p>
<p style="color:#6b7280;font-size:0.85rem">#${esc(String(opts.proposal.n || "?"))} · ${esc(opts.proposal.lane)}<br/>${esc(opts.proposal.title)}</p>
<form method="POST" action="">
<input type="hidden" name="s" value="${esc(opts.sig)}"/>
<input type="hidden" name="p" value="${esc(opts.payloadB64)}"/>
<div style="margin-top:1.25rem;display:flex;gap:0.75rem;flex-wrap:wrap">
<button type="submit" name="intent" value="confirm" style="background:${isCreate ? "#15803d" : "#6b7280"};color:#fff;border:0;padding:0.65rem 1.1rem;border-radius:8px;font-weight:600">${esc(label)}</button>
</div>
</form>
<p style="margin-top:1.5rem;color:#9ca3af;font-size:0.8rem">リンクを開いただけでは実行しません（確認ボタン必須）。</p>
</body></html>`;
}
