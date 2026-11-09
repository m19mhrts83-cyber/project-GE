import { NextResponse } from "next/server";
import { serviceClient } from "@/lib/supabase";
import { geminiText } from "@/lib/gemini";
import { getDraft, logRevision, saveVersions } from "@/lib/draftStore";
import {
  buildRevisePrompt,
  currentVersion,
  nextLabel,
  parseRevise,
  type DraftComment,
  type DraftVersion,
} from "@/lib/draftCore";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";
export const maxDuration = 60;

type Ctx = { params: Promise<{ id: string }> };

export async function GET(_req: Request, ctx: Ctx) {
  const { id } = await ctx.params;
  const sb = serviceClient();
  if (!sb) return NextResponse.json({ ok: false, error: "supabase_unconfigured" }, { status: 503 });
  const row = await getDraft(sb, id);
  if (!row) return NextResponse.json({ ok: false, error: "not found" }, { status: 404 });
  return NextResponse.json({ ok: true, draft: row });
}

function cleanComments(raw: unknown): DraftComment[] {
  if (!Array.isArray(raw)) return [];
  return raw
    .filter((c): c is Record<string, unknown> => !!c && typeof c === "object")
    .map((c) => ({
      quote: String(c.quote ?? "").slice(0, 1000),
      start: Number.isInteger(c.start) ? Number(c.start) : null,
      end: Number.isInteger(c.end) ? Number(c.end) : null,
      text: String(c.text ?? "").trim().slice(0, 2000),
      via: (c.via === "voice" ? "voice" : "typed") as DraftComment["via"],
    }))
    .filter((c) => c.text)
    .slice(0, 30);
}

/**
 * 版を進める。body.updatedAt は画面が読んだときの値（同時編集の確認）。
 *   op=revise  { comments }       … ダメ出しを AI に渡して直す → 新しい版
 *   op=manual  { text, comments? } … 手で直した文面を新しい版に
 *   op=revert                      … いまの版を戻す（AI の直しが違った）
 *   op=done                        … これで確定
 */
export async function POST(req: Request, ctx: Ctx) {
  const { id } = await ctx.params;
  let b: { op?: string; updatedAt?: string; comments?: unknown; text?: string; note?: string };
  try {
    b = await req.json();
  } catch {
    return NextResponse.json({ ok: false, error: "bad json" }, { status: 400 });
  }
  const sb = serviceClient();
  if (!sb) return NextResponse.json({ ok: false, error: "supabase_unconfigured" }, { status: 503 });
  const row = await getDraft(sb, id);
  if (!row) return NextResponse.json({ ok: false, error: "not found" }, { status: 404 });
  if (b.updatedAt && b.updatedAt !== row.updated_at) {
    return NextResponse.json({ ok: false, error: "ほかの端末で更新されました。読み直してください", draft: row }, { status: 409 });
  }
  if (row.status !== "open" && b.op !== "reopen") {
    return NextResponse.json({ ok: false, error: "確定済みです" }, { status: 409 });
  }
  const versions: DraftVersion[] = Array.isArray(row.versions) ? [...row.versions] : [];
  const cur = currentVersion(versions);
  if (!cur) return NextResponse.json({ ok: false, error: "版がありません" }, { status: 400 });
  const now = new Date().toISOString();

  if (b.op === "revise" || b.op === "manual") {
    const comments = cleanComments(b.comments);
    let next: DraftVersion;
    let ruleHint = "";
    if (b.op === "revise") {
      if (!comments.length) return NextResponse.json({ ok: false, error: "ダメ出しを1つ以上入れてください" }, { status: 400 });
      const gen = await geminiText(
        buildRevisePrompt({ text: cur.text, comments, recipient: row.recipient, channel: row.channel, context: row.context }),
      );
      if (!gen.ok) return NextResponse.json({ ok: false, error: gen.error }, { status: 502 });
      const parsed = parseRevise(gen.text);
      if (!parsed) return NextResponse.json({ ok: false, error: "AI の返事を読めませんでした。もう一度押してください" }, { status: 502 });
      if (parsed.text === cur.text) {
        return NextResponse.json({ ok: false, error: "AI が何も直しませんでした。言い方を変えてもう一度どうぞ" }, { status: 422 });
      }
      ruleHint = parsed.ruleHint;
      next = { label: nextLabel(versions), text: parsed.text, at: now, by: "ai", comments, changes: parsed.changes };
    } else {
      const text = String(b.text || "");
      if (!text.trim() || text === cur.text) return NextResponse.json({ ok: false, error: "変わっていません" }, { status: 400 });
      next = { label: nextLabel(versions), text: text.slice(0, 20000), at: now, by: "owner", comments, note: b.note?.slice(0, 1000) };
    }
    versions.push(next);
    const saved = await saveVersions(sb, row, versions);
    if (!saved.ok) return NextResponse.json({ ok: false, error: saved.error }, { status: 409 });
    const log = await logRevision(sb, saved.row, cur, next, "revise", { comments, ruleHint, note: b.note });
    return NextResponse.json({ ok: true, draft: saved.row, ruleHint, logged: log.ok && "persisted" in log && log.persisted });
  }

  if (b.op === "revert") {
    const idx = versions.lastIndexOf(cur);
    if (idx <= 0) return NextResponse.json({ ok: false, error: "最初の版は戻せません" }, { status: 400 });
    versions[idx] = { ...cur, reverted: true };
    const prev = currentVersion(versions.slice(0, idx));
    const saved = await saveVersions(sb, row, versions);
    if (!saved.ok) return NextResponse.json({ ok: false, error: saved.error }, { status: 409 });
    if (prev && cur.by === "ai") {
      await logRevision(sb, saved.row, prev, cur, "wrong", { comments: cur.comments, note: b.note || "AI の直しを戻した" });
    }
    return NextResponse.json({ ok: true, draft: saved.row });
  }

  if (b.op === "done") {
    const first = versions[0];
    const saved = await saveVersions(sb, row, versions, "done");
    if (!saved.ok) return NextResponse.json({ ok: false, error: saved.error }, { status: 409 });
    if (first && first !== cur) {
      await logRevision(sb, saved.row, first, cur, "adopt", { note: b.note || `確定（${first.label}→${cur.label}）` });
    }
    return NextResponse.json({ ok: true, draft: saved.row });
  }

  if (b.op === "reopen") {
    const saved = await saveVersions(sb, row, versions, "open");
    if (!saved.ok) return NextResponse.json({ ok: false, error: saved.error }, { status: 409 });
    return NextResponse.json({ ok: true, draft: saved.row });
  }

  return NextResponse.json({ ok: false, error: "unknown op" }, { status: 400 });
}
