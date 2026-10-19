/**
 * Slack Interactivity（block_actions / view_submission）用の業者返信処理
 *
 * 本線: consult-action の Signing Secret を再利用。Bot Token があれば
 * views.open / chat.update。無ければ ephemeral + 署名 URL フォールバック。
 */
import {
  applyVendorReplySlack,
  fetchVendorReplyTriage,
  isVendorReplyTriageId,
  parseVrAction,
  type VendorReplySlackAction,
  vrActionUrl,
} from "@/lib/vendorReplySlackAction";

export const VR_ACTION_IDS = {
  send: "vendor_reply_send",
  skip: "vendor_reply_skip",
  edit: "vendor_reply_edit",
} as const;

export const VR_MODAL_CALLBACK = "vendor_reply_edit_modal";

export type VrModalMeta = {
  id: string;
  channel?: string;
  message_ts?: string;
};

/** value 形式: vr:send:re-vendor-xxxx */
export function parseVrButtonValue(
  value: string,
): { action: VendorReplySlackAction; id: string } | null {
  const m = String(value || "")
    .trim()
    .match(/^vr:(send|skip|edit):(re-vendor-[0-9a-f]+)$/i);
  if (!m) return null;
  const action = parseVrAction(m[1]);
  const id = m[2];
  if (!action || !isVendorReplyTriageId(id)) return null;
  return { action, id };
}

export function parseVrModalMeta(raw: string): VrModalMeta | null {
  const s = String(raw || "").trim();
  if (!s) return null;
  if (isVendorReplyTriageId(s)) return { id: s };
  try {
    const j = JSON.parse(s) as Record<string, unknown>;
    const id = String(j.id || "").trim();
    if (!isVendorReplyTriageId(id)) return null;
    return {
      id,
      channel: String(j.channel || "").trim() || undefined,
      message_ts: String(j.message_ts || j.ts || "").trim() || undefined,
    };
  } catch {
    return null;
  }
}

export function doneBlocks(title: string, detail: string, ok: boolean) {
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

export async function handleVrBlockAction(opts: {
  action: VendorReplySlackAction;
  triageId: string;
  triggerId?: string;
  channelId?: string;
  messageTs?: string;
}): Promise<{
  kind: "replace" | "ephemeral" | "modal_opened" | "error";
  text: string;
  blocks?: ReturnType<typeof doneBlocks>;
}> {
  const { action, triageId, triggerId, channelId, messageTs } = opts;

  if (action === "edit") {
    const row = await fetchVendorReplyTriage(triageId);
    if (!row) {
      return { kind: "error", text: "対象の業者返信が見つかりません" };
    }
    const bot = (process.env.SLACK_BOT_TOKEN || "").trim();
    if (bot && triggerId) {
      const opened = await openEditModal({
        token: bot,
        triggerId,
        triageId,
        partner: String(row.partner || "業者"),
        draft: String(row.draft_text || ""),
        channelId,
        messageTs,
      });
      if (opened.ok) {
        return { kind: "modal_opened", text: "編集モーダルを開きました" };
      }
      return {
        kind: "ephemeral",
        text: `モーダルを開けませんでした（${opened.error}）。編集ページ: ${vrActionUrl(triageId, "edit")}`,
      };
    }
    return {
      kind: "ephemeral",
      text: `編集ページを開いてください: ${vrActionUrl(triageId, "edit")}`,
    };
  }

  const result = await applyVendorReplySlack(triageId, action, {
    source: "slack_block_actions",
  });
  const title =
    action === "send"
      ? result.ok
        ? "送信しました"
        : "送信失敗"
      : result.ok
        ? "返信なしにしました"
        : "更新失敗";
  return {
    kind: "replace",
    text: `${result.ok ? "✅" : "❌"} ${result.message}`,
    blocks: doneBlocks(title, result.message, result.ok),
  };
}

export async function handleVrModalSubmit(opts: {
  triageId: string;
  body: string;
  channelId?: string;
  messageTs?: string;
}): Promise<{
  ok: boolean;
  text: string;
  blocks: ReturnType<typeof doneBlocks>;
  response_action?: "clear" | "errors";
  errors?: Record<string, string>;
}> {
  const body = (opts.body || "").trim();
  if (!body) {
    return {
      ok: false,
      text: "本文が空です",
      blocks: doneBlocks("送信失敗", "本文が空です", false),
      response_action: "errors",
      errors: { vendor_reply_body: "本文を入力してください" },
    };
  }
  const result = await applyVendorReplySlack(opts.triageId, "send", {
    body,
    source: "slack_modal",
  });

  if (result.ok && opts.channelId && opts.messageTs) {
    const bot = (process.env.SLACK_BOT_TOKEN || "").trim();
    if (bot) {
      await chatUpdate({
        token: bot,
        channel: opts.channelId,
        ts: opts.messageTs,
        text: `✅ ${result.message}`,
        blocks: doneBlocks("送信しました", result.message, true),
      });
    }
  }

  return {
    ok: result.ok,
    text: result.message,
    blocks: doneBlocks(
      result.ok ? "送信しました" : "送信失敗",
      result.message,
      result.ok,
    ),
    response_action: result.ok ? "clear" : undefined,
  };
}

/** view_submission の state.values から本文を抜く */
export function extractVrModalBody(view: Record<string, unknown>): string {
  const state = (view.state || {}) as Record<string, unknown>;
  const values = (state.values || {}) as Record<
    string,
    Record<string, { value?: string }>
  >;
  const block = values.vendor_reply_body_block || {};
  const el = block.vendor_reply_body || Object.values(block)[0];
  return String(el?.value || "").trim();
}

async function openEditModal(opts: {
  token: string;
  triggerId: string;
  triageId: string;
  partner: string;
  draft: string;
  channelId?: string;
  messageTs?: string;
}): Promise<{ ok: boolean; error?: string }> {
  const meta: VrModalMeta = {
    id: opts.triageId,
    channel: opts.channelId,
    message_ts: opts.messageTs,
  };
  const view = {
    type: "modal",
    callback_id: VR_MODAL_CALLBACK,
    private_metadata: JSON.stringify(meta).slice(0, 3000),
    title: { type: "plain_text", text: "返信を編集" },
    submit: { type: "plain_text", text: "送信" },
    close: { type: "plain_text", text: "キャンセル" },
    blocks: [
      {
        type: "section",
        text: {
          type: "mrkdwn",
          text: `*${opts.partner}*\n編集して送信（＝了承）`,
        },
      },
      {
        type: "input",
        block_id: "vendor_reply_body_block",
        label: { type: "plain_text", text: "返信本文" },
        element: {
          type: "plain_text_input",
          action_id: "vendor_reply_body",
          multiline: true,
          initial_value: opts.draft.slice(0, 3000),
        },
      },
    ],
  };
  try {
    const res = await fetch("https://slack.com/api/views.open", {
      method: "POST",
      headers: {
        Authorization: `Bearer ${opts.token}`,
        "Content-Type": "application/json; charset=utf-8",
      },
      body: JSON.stringify({ trigger_id: opts.triggerId, view }),
    });
    const j = (await res.json()) as { ok?: boolean; error?: string };
    if (!j.ok) {
      return { ok: false, error: j.error || "views.open failed" };
    }
    return { ok: true };
  } catch (e) {
    return { ok: false, error: e instanceof Error ? e.message : String(e) };
  }
}

async function chatUpdate(opts: {
  token: string;
  channel: string;
  ts: string;
  text: string;
  blocks: ReturnType<typeof doneBlocks>;
}): Promise<void> {
  try {
    await fetch("https://slack.com/api/chat.update", {
      method: "POST",
      headers: {
        Authorization: `Bearer ${opts.token}`,
        "Content-Type": "application/json; charset=utf-8",
      },
      body: JSON.stringify({
        channel: opts.channel,
        ts: opts.ts,
        text: opts.text,
        blocks: opts.blocks,
      }),
    });
  } catch {
    /* ignore */
  }
}

/** response_url で元メッセージを置き換え（3秒超のとき用） */
export async function postResponseUrl(
  responseUrl: string,
  body: Record<string, unknown>,
): Promise<void> {
  if (!responseUrl) return;
  try {
    await fetch(responseUrl, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
  } catch {
    /* ignore */
  }
}
