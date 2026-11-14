/**
 * メール要対応カードの「📄 全文を見る」モーダルと、返信モーダルに載せる受信本文。
 *
 * Slack の制約（2026-11-14 時点）:
 * - メッセージにもモーダルにも「開閉トグル」部品は無い → カードは要旨のまま、
 *   ボタンで全文モーダルを開く（ドリルダウン）。
 * - section の text は 3000 字まで、モーダルは 100 ブロックまで → 2800 字ずつに割って並べる。
 * - 取り込み時点で本文は 8000 字まで保存（jarvis_gha_gmail_triage / night_triage）。
 *   それ以上長いものの続きと添付ファイルの中身は Dashboard で見る。
 *
 * ここは Slack 依存のない組み立てだけ（tests/maFullTextView.test.mjs で確認）。
 */

export const MA_FULL_CALLBACK = "mail_action_full_modal";

/** 1 ブロックに載せる字数（section 上限 3000 の手前） */
const CHUNK = 2800;
/** モーダル 1 枚に載せる本文の上限（保存上限 8000 字＋余裕） */
export const FULL_TEXT_MAX = 12000;

/** 行の切れ目で size 字ずつに割る。長すぎる 1 行はそのまま切る。 */
export function splitBodyChunks(text: string, size = CHUNK, maxTotal = FULL_TEXT_MAX): {
  chunks: string[];
  truncated: boolean;
} {
  const src = String(text || "").replace(/\r\n?/g, "\n").replace(/\n{4,}/g, "\n\n\n").trim();
  const truncated = src.length > maxTotal;
  const body = truncated ? src.slice(0, maxTotal) : src;
  const chunks: string[] = [];
  let cur = "";
  for (const line of body.split("\n")) {
    let rest = line;
    while (rest.length > size) {
      if (cur) {
        chunks.push(cur);
        cur = "";
      }
      chunks.push(rest.slice(0, size));
      rest = rest.slice(size);
    }
    const next = cur ? `${cur}\n${rest}` : rest;
    if (next.length > size) {
      chunks.push(cur);
      cur = rest;
    } else {
      cur = next;
    }
  }
  if (cur.trim()) chunks.push(cur);
  return { chunks: chunks.filter((c) => c.trim()), truncated };
}

function mrkdwnEscape(s: string): string {
  return String(s || "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

/** 本文を plain_text の section に並べる（mrkdwn の * や _ で崩れないよう plain_text） */
export function bodyTextBlocks(text: string, opts: { maxTotal?: number; moreUrl?: string } = {}) {
  const { chunks, truncated } = splitBodyChunks(text, CHUNK, opts.maxTotal ?? FULL_TEXT_MAX);
  const blocks: Array<Record<string, unknown>> = chunks.length
    ? chunks.map((c) => ({ type: "section", text: { type: "plain_text", text: c, emoji: false } }))
    : [{ type: "section", text: { type: "plain_text", text: "(本文なし)", emoji: false } }];
  if (truncated) {
    blocks.push({
      type: "context",
      elements: [
        {
          type: "mrkdwn",
          text: opts.moreUrl
            ? `✂️ 長いので途中まで表示しています。続きは <${opts.moreUrl}|Dashboard> で`
            : "✂️ 長いので途中まで表示しています",
        },
      ],
    });
  }
  return blocks;
}

export type FullTextMeta = { id: string; channel?: string; message_ts?: string };

export type FullTextViewInput = {
  meta: FullTextMeta;
  who: string;
  subject: string;
  from?: string;
  received?: string;
  /** "メール" / "Chatwork" / "LINE" など */
  channelLabel: string;
  body: string;
  /** メールなら「返信する」で返信モーダルへ進める */
  canReply: boolean;
  /** チャットのアプリを開く URL（任意） */
  app?: { url: string; text: string } | null;
  /** Dashboard の詳細ページ（添付・長文の続き） */
  detailUrl?: string;
};

export function buildFullTextView(input: FullTextViewInput) {
  const headLines = [
    `*${mrkdwnEscape(input.who).slice(0, 80)}*（${mrkdwnEscape(input.channelLabel)}）`,
    `*件名:* ${mrkdwnEscape(input.subject || "(件名なし)").slice(0, 150)}`,
  ];
  if (input.from) headLines.push(`*From:* ${mrkdwnEscape(input.from).slice(0, 120)}`);
  if (input.received) headLines.push(`*受信:* ${mrkdwnEscape(input.received).slice(0, 40)}`);
  const blocks: Array<Record<string, unknown>> = [
    { type: "section", text: { type: "mrkdwn", text: headLines.join("\n") } },
    { type: "divider" },
    ...bodyTextBlocks(input.body, { moreUrl: input.detailUrl }),
    { type: "divider" },
  ];
  const elements: Array<Record<string, unknown>> = [];
  if (input.app?.url) {
    elements.push({
      type: "button",
      text: { type: "plain_text", text: input.app.text.slice(0, 30), emoji: true },
      url: input.app.url,
      action_id: "mail_action_open_app",
    });
  }
  if (input.detailUrl) {
    elements.push({
      type: "button",
      text: { type: "plain_text", text: "添付・履歴（Dashboard）", emoji: true },
      url: input.detailUrl,
      action_id: "mail_action_open_detail",
    });
  }
  if (elements.length) blocks.push({ type: "actions", elements });
  blocks.push({
    type: "context",
    elements: [
      {
        type: "mrkdwn",
        text: input.canReply
          ? "読んだら「返信する」で返信画面へ（下書き・誤字チェック・送信まで Slack で完結）。不要なら閉じてカードの「見送り」"
          : "読んだら閉じて、カードの「✍️ 返信案を作る」か「見送り」へ",
      },
    ],
  });
  return {
    type: "modal",
    callback_id: MA_FULL_CALLBACK,
    private_metadata: JSON.stringify(input.meta).slice(0, 2900),
    title: { type: "plain_text", text: "本文（全文）" },
    ...(input.canReply ? { submit: { type: "plain_text", text: "返信する" } } : {}),
    close: { type: "plain_text", text: "閉じる" },
    blocks: blocks.slice(0, 100),
  };
}
