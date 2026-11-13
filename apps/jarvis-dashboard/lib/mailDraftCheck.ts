/**
 * 返信下書きの点検（Slack 返信モーダル用）
 * - 誤字脱字: 指示不要のワンボタン。言い回しは変えず、直した箇所を一覧で返す
 * - 見直し: フリーワード指示で書き直す
 */
import { geminiReply } from "@/lib/geminiReply";

export type DraftCheckResult =
  | { ok: true; text: string; changes: string[] }
  | { ok: false; error: string };

const TIMEOUT_MS = 25_000;

function stripFence(s: string): string {
  return s
    .trim()
    .replace(/^```(?:json|text)?\s*/i, "")
    .replace(/```\s*$/, "")
    .trim();
}

function proofreadPrompt(draft: string): string {
  return [
    "あなたはビジネス日本語メールの校正担当です。次の返信下書きを点検してください。",
    "直すのは誤字・脱字・変換ミス・助詞の誤り・敬語の誤り・表記ゆれだけです。",
    "言い回し、構成、改行、署名は変えないでください。直す必要がなければそのまま返してください。",
    "出力は JSON のみ: {\"text\": \"修正後の全文\", \"changes\": [\"誤→正（短い理由）\", ...]}",
    "",
    "【下書き】",
    draft,
  ].join("\n");
}

function revisePrompt(draft: string, instruction: string): string {
  return [
    "あなたはビジネス日本語のメール下書き担当です。指示に従って返信下書きを書き直してください。",
    "事実（日時・金額・物件名・人名）は変えないでください。",
    "出力は JSON のみ: {\"text\": \"書き直した全文\", \"changes\": [\"変えた点の要約\", ...]}",
    "",
    "【見直し指示】",
    instruction.trim(),
    "",
    "【現在の下書き】",
    draft,
  ].join("\n");
}

export function parseDraftCheckJson(raw: string, fallback: string): {
  text: string;
  changes: string[];
} {
  const cleaned = stripFence(raw);
  try {
    const j = JSON.parse(cleaned) as { text?: unknown; changes?: unknown };
    const text = typeof j.text === "string" && j.text.trim() ? j.text.trim() : fallback;
    const changes = Array.isArray(j.changes)
      ? j.changes.map((c) => String(c).trim()).filter(Boolean).slice(0, 10)
      : [];
    return { text, changes };
  } catch {
    // JSON で返らなかったときは本文そのものとして扱う
    return { text: cleaned || fallback, changes: [] };
  }
}

async function run(prompt: string, draft: string): Promise<DraftCheckResult> {
  const r = await geminiReply(prompt, { timeoutMs: TIMEOUT_MS, maxAttempts: 3 });
  if (!r.ok) return { ok: false, error: r.error };
  const parsed = parseDraftCheckJson(r.text, draft);
  return { ok: true, ...parsed };
}

export async function proofreadDraft(draft: string): Promise<DraftCheckResult> {
  if (!draft.trim()) return { ok: false, error: "本文が空です" };
  return run(proofreadPrompt(draft), draft);
}

export async function reviseDraft(
  draft: string,
  instruction: string,
): Promise<DraftCheckResult> {
  if (!draft.trim()) return { ok: false, error: "本文が空です" };
  if (!instruction.trim()) return { ok: false, error: "見直し指示を入力してください" };
  return run(revisePrompt(draft, instruction), draft);
}

/** 返信下書きを作る（「返信する」で本文が空のとき・1通1回） */
export function composePrompt(opts: {
  who: string;
  subject: string;
  inbound: string;
  history?: string;
  materials?: string[];
  /** 松野さんの見直し指示（本文が空のまま「指示で見直し」を押したとき） */
  instruction?: string;
  /** LINE／Chatwork などチャットでの返信（宛名・署名なしの短文） */
  chat?: string;
}): string {
  if (opts.chat) return composeChatPrompt({ ...opts, chat: opts.chat });
  const lines = [
    "あなたは株式会社リビングサポート松の代表・松野真治です。届いたメールへの返信下書きを書いてください。",
    "",
    "ルール:",
    "- 日本語。丁寧だが冗長にしない。",
    "- 冒頭は相手の呼び方に合わせる（〇〇様）。不明なら「ご担当者様」。",
    "- 末尾署名は「松野」のみ。",
    "- 約束・金額・日付を作らない。分からないことは確認の一文にする。",
    "- 件名・引用・「Re:」は書かない。本文のみ。",
  ];
  if (opts.materials?.length) {
    lines.push("- 資料を求められているので、添付して送る前提で一言添える（例: 下記の資料をお送りします）。");
  }
  lines.push(
    "",
    `相手: ${opts.who}`,
    `件名: ${opts.subject}`,
  );
  if (opts.history?.trim()) {
    lines.push("", "【これまでのやり取り（新しいものが末尾）】", opts.history.trim());
  }
  lines.push("", "【届いたメール】", (opts.inbound || "").slice(0, 4000));
  if (opts.instruction?.trim()) {
    lines.push("", "【松野さんの指示（最優先で従う）】", opts.instruction.trim());
  }
  lines.push("", "返信本文のみを出力してください。");
  return lines.join("\n");
}

/** チャット（LINE／Chatwork）向け: 貼り付けてそのまま送れる短文 */
function composeChatPrompt(opts: {
  who: string;
  inbound: string;
  history?: string;
  instruction?: string;
  chat: string;
}): string {
  const lines = [
    `あなたは株式会社リビングサポート松の代表・松野真治です。${opts.chat}で届いたメッセージへの返信文を書いてください。`,
    "",
    "ルール:",
    "- 日本語。丁寧語だが、チャットなので短く（2〜5行）。",
    "- 宛名（〇〇様）・署名・時候の挨拶・「お世話になっております」の重ねは付けない（冒頭の一言は可）。",
    "- 約束・金額・日付を作らない。分からないことは確認の一文にする。",
    "- そのまま貼り付けて送れる本文だけを書く。",
    "",
    `相手: ${opts.who}`,
  ];
  if (opts.history?.trim()) {
    lines.push("", "【これまでのやり取り（新しいものが末尾）】", opts.history.trim());
  }
  lines.push("", "【届いたメッセージ】", (opts.inbound || "").slice(0, 3000));
  if (opts.instruction?.trim()) {
    lines.push("", "【松野さんの指示（最優先で従う）】", opts.instruction.trim());
  }
  lines.push("", "返信本文のみを出力してください。");
  return lines.join("\n");
}

export async function composeDraft(opts: {
  who: string;
  subject: string;
  inbound: string;
  history?: string;
  materials?: string[];
  instruction?: string;
  chat?: string;
}): Promise<DraftCheckResult> {
  if (!opts.inbound.trim()) return { ok: false, error: "元のメール本文がありません" };
  const r = await geminiReply(composePrompt(opts), { timeoutMs: TIMEOUT_MS, maxAttempts: 3 });
  if (!r.ok) return { ok: false, error: r.error };
  const text = stripFence(r.text);
  if (!text) return { ok: false, error: "下書きが空でした" };
  return { ok: true, text, changes: [] };
}
