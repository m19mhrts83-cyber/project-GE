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
