/**
 * Slack Interactivity — メール要対応（返信／見送り／Todoist）
 */
import {
  applyMailActionSlack,
  deleteSlackMaMessage,
  fetchMailActionTriage,
  isMailActionTriageId,
  maActionUrl,
  parseMaAction,
  type MailActionSlackAction,
} from "@/lib/mailActionSlackAction";

export const MA_ACTION_IDS = {
  reply: "mail_action_reply",
  skip: "mail_action_skip",
  todoist: "mail_action_todoist",
} as const;

export const MA_MODAL_CALLBACK = "mail_action_reply_modal";

export type MaModalMeta = {
  id: string;
  channel?: string;
  message_ts?: string;
};

/** value: ma:reply|skip|todoist:{triage_id} */
export function parseMaButtonValue(
  value: string,
): { action: MailActionSlackAction; id: string } | null {
  const m = String(value || "")
    .trim()
    .match(/^ma:(reply|skip|todoist):([a-zA-Z0-9_.:-]{6,80})$/i);
  if (!m) return null;
  const action = parseMaAction(m[1]);
  const id = m[2];
  if (!action || !isMailActionTriageId(id)) return null;
  return { action, id };
}

export function parseMaModalMeta(raw: string): MaModalMeta | null {
  const s = String(raw || "").trim();
  if (!s) return null;
  if (isMailActionTriageId(s)) return { id: s };
  try {
    const j = JSON.parse(s) as Record<string, unknown>;
    const id = String(j.id || "").trim();
    if (!isMailActionTriageId(id)) return null;
    return {
      id,
      channel: String(j.channel || "").trim() || undefined,
      message_ts: String(j.message_ts || j.ts || "").trim() || undefined,
    };
  } catch {
    return null;
  }
}

export function maDoneBlocks(title: string, detail: string, ok: boolean) {
  const icon = ok ? "✅" : "❌";
  return [
    {
      type: "section",
      text: {
        type: "mrkdwn" as const,
        text: `${icon} *${title}*\n${detail}`,
      },
    },
  ];
}

async function openReplyModal(opts: {
  token: string;
  triggerId: string;
  triageId: string;
  who: string;
  draft: string;
  inbound: string;
  channelId?: string;
  messageTs?: string;
}): Promise<{ ok: boolean; error?: string }> {
  const privateMeta: MaModalMeta = {
    id: opts.triageId,
    channel: opts.channelId,
    message_ts: opts.messageTs,
  };
  const inbound = (opts.inbound || "").slice(0, 1500);
  const body = {
    trigger_id: opts.triggerId,
    view: {
      type: "modal",
      callback_id: MA_MODAL_CALLBACK,
      private_metadata: JSON.stringify(privateMeta),
      title: { type: "plain_text", text: "メール返信" },
      submit: { type: "plain_text", text: "送信" },
      close: { type: "plain_text", text: "キャンセル" },
      blocks: [
        {
          type: "section",
          text: {
            type: "mrkdwn",
            text: `*宛先ヒント:* ${opts.who.slice(0, 80)}\n\`\`\`${inbound || "(本文なし)"}\`\`\``,
          },
        },
        {
          type: "input",
          block_id: "mail_reply_body_block",
          label: { type: "plain_text", text: "返信本文" },
          element: {
            type: "plain_text_input",
            action_id: "mail_reply_body",
            multiline: true,
            initial_value: opts.draft || "",
          },
        },
      ],
    },
  };
  const res = await fetch("https://slack.com/api/views.open", {
    method: "POST",
    headers: {
      Authorization: `Bearer ${opts.token}`,
      "Content-Type": "application/json; charset=utf-8",
    },
    body: JSON.stringify(body),
  });
  const j = (await res.json()) as { ok?: boolean; error?: string };
  if (!j.ok) return { ok: false, error: j.error || "views.open failed" };
  return { ok: true };
}

export function extractMaModalBody(
  payload: Record<string, unknown>,
): string {
  const view = (payload.view || {}) as Record<string, unknown>;
  const state = (view.state || {}) as Record<string, unknown>;
  const values = (state.values || {}) as Record<string, Record<string, unknown>>;
  const block = (values.mail_reply_body_block || {}) as Record<
    string,
    Record<string, unknown>
  >;
  const el = block.mail_reply_body || {};
  return String(el.value || "").trim();
}

export async function handleMaModalSubmit(opts: {
  triageId: string;
  body: string;
  channelId?: string;
  messageTs?: string;
}): Promise<{
  ok: boolean;
  text: string;
  errors?: Record<string, string>;
}> {
  if (!opts.body.trim()) {
    return {
      ok: false,
      text: "本文が空です",
      errors: { mail_reply_body: "返信本文を入力してください" },
    };
  }
  const result = await applyMailActionSlack(opts.triageId, "reply", {
    body: opts.body,
    source: "slack_modal",
  });
  if (!result.ok) {
    return {
      ok: false,
      text: result.message,
      errors: { mail_reply_body: result.message.slice(0, 100) },
    };
  }
  const bot = (process.env.SLACK_BOT_TOKEN || "").trim();
  if (bot && opts.channelId && opts.messageTs) {
    await fetch("https://slack.com/api/chat.update", {
      method: "POST",
      headers: {
        Authorization: `Bearer ${bot}`,
        "Content-Type": "application/json; charset=utf-8",
      },
      body: JSON.stringify({
        channel: opts.channelId,
        ts: opts.messageTs,
        text: `✅ ${result.message}`,
        blocks: maDoneBlocks("返信を送信しました", result.message, true),
      }),
    });
  }
  return { ok: true, text: result.message };
}

export async function handleMaBlockAction(opts: {
  action: MailActionSlackAction;
  triageId: string;
  triggerId?: string;
  channelId?: string;
  messageTs?: string;
}): Promise<{
  kind: "replace" | "delete" | "ephemeral" | "modal_opened" | "error";
  text: string;
  blocks?: ReturnType<typeof maDoneBlocks>;
  slack_deleted?: boolean;
}> {
  const { action, triageId, triggerId, channelId, messageTs } = opts;

  if (action === "reply") {
    const row = await fetchMailActionTriage(triageId);
    if (!row) {
      return { kind: "error", text: "対象のメール要対応が見つかりません" };
    }
    const bot = (process.env.SLACK_BOT_TOKEN || "").trim();
    if (bot && triggerId) {
      const opened = await openReplyModal({
        token: bot,
        triggerId,
        triageId,
        who: String(row.partner || row.from_email || "相手"),
        draft: String(row.draft_text || ""),
        inbound: String(row.original_body || ""),
        channelId,
        messageTs,
      });
      if (opened.ok) {
        return { kind: "modal_opened", text: "返信モーダルを開きました" };
      }
      return {
        kind: "ephemeral",
        text: `モーダルを開けませんでした（${opened.error}）。編集ページ: ${maActionUrl(triageId, "reply")}`,
      };
    }
    return {
      kind: "ephemeral",
      text: `返信ページを開いてください: ${maActionUrl(triageId, "reply")}`,
    };
  }

  const result = await applyMailActionSlack(triageId, action, {
    source: "slack_block_actions",
  });

  // 見送り成功 → カードをチャットから削除（残す必要なし）
  if (action === "skip" && result.ok) {
    const deletedNow = await deleteSlackMaMessage({
      channel: channelId,
      ts: messageTs,
    });
    return {
      kind: "delete",
      text: result.message,
      slack_deleted: deletedNow || result.slack_deleted,
    };
  }

  const title = result.ok ? "Todoist 登録" : "Todoist 登録失敗";
  return {
    kind: result.ok ? "replace" : "error",
    text: result.message,
    blocks: maDoneBlocks(title, result.message, result.ok),
  };
}
