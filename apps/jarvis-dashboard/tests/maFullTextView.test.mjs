import { test } from "node:test";
import assert from "node:assert/strict";
import {
  MA_FULL_CALLBACK,
  bodyTextBlocks,
  buildFullTextView,
  splitBodyChunks,
} from "../lib/maFullTextView.ts";

test("短い本文は1ブロック・切り詰めなし", () => {
  const { chunks, truncated } = splitBodyChunks("松野様\nお世話になります。");
  assert.equal(chunks.length, 1);
  assert.equal(truncated, false);
});

test("長い本文は2800字以下のブロックに割り、全文を失わない", () => {
  const line = "あ".repeat(100);
  const body = Array.from({ length: 70 }, () => line).join("\n"); // 7069 字
  const { chunks, truncated } = splitBodyChunks(body);
  assert.equal(truncated, false);
  assert.ok(chunks.length >= 3);
  for (const c of chunks) assert.ok(c.length <= 2800);
  assert.equal(chunks.join("\n"), body);
});

test("改行のない長い1行も切って載せる", () => {
  const { chunks } = splitBodyChunks("x".repeat(6000));
  assert.deepEqual(chunks.map((c) => c.length), [2800, 2800, 400]);
});

test("上限を超えたら切り詰めて続きの案内を出す", () => {
  const blocks = bodyTextBlocks("y".repeat(13000), { moreUrl: "https://example.com/mail/1" });
  const last = blocks[blocks.length - 1];
  assert.equal(last.type, "context");
  assert.match(last.elements[0].text, /続き/);
});

test("空の本文は（本文なし）", () => {
  const blocks = bodyTextBlocks("");
  assert.equal(blocks.length, 1);
  assert.equal(blocks[0].text.text, "(本文なし)");
});

test("全文モーダル: メールは「返信する」で進める・チャットは閉じるだけ", () => {
  const base = {
    meta: { id: "abc123", channel: "C1", message_ts: "1.2" },
    who: "テスト商事 <担当>",
    subject: "見積の件",
    channelLabel: "メール",
    body: "本文です *太字にしない*",
    detailUrl: "https://example.com/mail/abc123",
  };
  const mail = buildFullTextView({ ...base, canReply: true });
  assert.equal(mail.callback_id, MA_FULL_CALLBACK);
  assert.equal(mail.submit.text, "返信する");
  assert.ok(mail.title.text.length <= 24);
  assert.deepEqual(JSON.parse(mail.private_metadata), base.meta);
  // 相手名の < > はエスケープ、本文は plain_text のまま
  assert.match(mail.blocks[0].text.text, /&lt;担当&gt;/);
  assert.ok(mail.blocks.some((b) => b.text?.type === "plain_text" && b.text.text.includes("*太字にしない*")));
  // 同じ view 内で action_id が重ならない
  const ids = mail.blocks.flatMap((b) => (b.elements || []).map((e) => e.action_id)).filter(Boolean);
  assert.equal(new Set(ids).size, ids.length);

  const chat = buildFullTextView({
    ...base,
    channelLabel: "Chatwork",
    canReply: false,
    app: { url: "https://www.chatwork.com/#!rid1", text: "Chatworkで返信" },
  });
  assert.equal(chat.submit, undefined);
  const chatIds = chat.blocks.flatMap((b) => (b.elements || []).map((e) => e.action_id)).filter(Boolean);
  assert.equal(new Set(chatIds).size, chatIds.length);
});
