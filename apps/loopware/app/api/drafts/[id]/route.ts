import { NextResponse } from "next/server";
import { serviceClient } from "@/lib/supabase";
import { getDraft, logComment, logRevision, patchWithRetry, saveVersions } from "@/lib/draftStore";
import { currentVersion, nextLabel, type DraftComment, type DraftVersion, type ReviseRequest } from "@/lib/draftCore";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

type Ctx = { params: Promise<{ id: string }> };

export async function GET(_req: Request, ctx: Ctx) {
  const { id } = await ctx.params;
  const sb = serviceClient();
  if (!sb) return NextResponse.json({ ok: false, error: "supabase_unconfigured" }, { status: 503 });
  const row = await getDraft(sb, id);
  if (!row) return NextResponse.json({ ok: false, error: "not found" }, { status: 404 });
  return NextResponse.json({ ok: true, draft: row });
}

const TARGETS = new Set(["selection", "paragraph", "viewport", "whole"]);

function cleanComment(c: unknown): DraftComment | null {
  if (!c || typeof c !== "object") return null;
  const o = c as Record<string, unknown>;
  const text = String(o.text ?? "").trim().slice(0, 2000);
  if (!text) return null;
  const id = String(o.id ?? "").replace(/[^a-zA-Z0-9_-]/g, "").slice(0, 40);
  if (id.length < 6) return null;
  const num = (v: unknown) => (typeof v === "number" && Number.isFinite(v) ? Math.round(v) : undefined);
  return {
    id,
    quote: String(o.quote ?? "").slice(0, 1000),
    start: Number.isInteger(o.start) ? Number(o.start) : null,
    end: Number.isInteger(o.end) ? Number(o.end) : null,
    text,
    via: o.via === "voice" ? "voice" : "typed",
    target: TARGETS.has(String(o.target)) ? (String(o.target) as DraftComment["target"]) : "whole",
    version: String(o.version ?? "").slice(0, 10) || undefined,
    at: new Date().toISOString(),
    t_start: num(o.t_start),
    t_end: num(o.t_end),
  };
}

/**
 * 操作（どれも消さずに追記。版とダメ出しは判断ログ owner_decisions にも残る）
 *   op=comment  { comment }      … 箇所つきのダメ出しを1件、その場で保存
 *   op=uncomment { commentId }   … まだ直しに回していないダメ出しを取り消す
 *   op=revise                     … たまったダメ出しをまとめて直しに回す（Mac の Cursor が処理。従量課金の API は使わない）
 *   op=cancel                     … 直し待ちを取り消して、ダメ出しを戻す
 *   op=retry                      … 失敗した直しをもう一度
 *   op=manual  { text, updatedAt } … 手で直した文面を新しい版に
 *   op=revert  { updatedAt }       … いまの版を戻す（直しが違った）
 *   op=done / reopen
 */
export async function POST(req: Request, ctx: Ctx) {
  const { id } = await ctx.params;
  let b: { op?: string; updatedAt?: string; comment?: unknown; commentId?: string; text?: string; note?: string };
  try {
    b = await req.json();
  } catch {
    return NextResponse.json({ ok: false, error: "bad json" }, { status: 400 });
  }
  const sb = serviceClient();
  if (!sb) return NextResponse.json({ ok: false, error: "supabase_unconfigured" }, { status: 503 });

  // ---- ダメ出し（声で続けて届くので、ロックは読み直しで吸収する）
  if (b.op === "comment") {
    const c = cleanComment(b.comment);
    if (!c) return NextResponse.json({ ok: false, error: "ダメ出しが空です" }, { status: 400 });
    const res = await patchWithRetry(sb, id, (row) => {
      if (row.status !== "open") return { error: "確定済みです" };
      const list = Array.isArray(row.pending_comments) ? row.pending_comments : [];
      if (list.some((x) => x.id === c.id)) return null; // 再送
      if (list.length >= 100) return { error: "ダメ出しが多すぎます。いったん直しに回してください" };
      const cur = currentVersion(row.versions || []);
      return { pending_comments: [...list, { ...c, version: c.version || cur?.label }] };
    });
    if (!res.ok) return NextResponse.json({ ok: false, error: res.error, draft: res.row }, { status: 409 });
    const saved = res.row.pending_comments.find((x) => x.id === c.id) || c;
    const log = await logComment(sb, res.row, saved);
    return NextResponse.json({ ok: true, draft: res.row, logged: log.ok && "persisted" in log && log.persisted });
  }

  if (b.op === "uncomment") {
    const cid = String(b.commentId || "");
    const res = await patchWithRetry(sb, id, (row) => {
      const list = Array.isArray(row.pending_comments) ? row.pending_comments : [];
      if (!list.some((x) => x.id === cid)) return null;
      return { pending_comments: list.filter((x) => x.id !== cid) };
    });
    if (!res.ok) return NextResponse.json({ ok: false, error: res.error }, { status: 409 });
    return NextResponse.json({ ok: true, draft: res.row });
  }

  if (b.op === "revise") {
    const res = await patchWithRetry(sb, id, (row) => {
      if (row.status !== "open") return { error: "確定済みです" };
      const rr = row.revise_request;
      if (rr && (rr.status === "queued" || rr.status === "running")) return { error: "いま直しています。終わるまでお待ちください" };
      const list = Array.isArray(row.pending_comments) ? row.pending_comments : [];
      if (!list.length) return { error: "ダメ出しを1つ以上入れてください" };
      const cur = currentVersion(row.versions || []);
      if (!cur) return { error: "版がありません" };
      const req: ReviseRequest = { status: "queued", base: cur.label, comments: list, requested_at: new Date().toISOString(), engine: "cursor" };
      return { revise_request: req, pending_comments: [] };
    });
    if (!res.ok) return NextResponse.json({ ok: false, error: res.error, draft: res.row }, { status: 409 });
    return NextResponse.json({ ok: true, draft: res.row });
  }

  if (b.op === "retry") {
    const res = await patchWithRetry(sb, id, (row) => {
      const rr = row.revise_request;
      if (!rr || rr.status !== "error") return { error: "やり直せる直しはありません" };
      return { revise_request: { ...rr, status: "queued", error: undefined, requested_at: new Date().toISOString() } };
    });
    if (!res.ok) return NextResponse.json({ ok: false, error: res.error, draft: res.row }, { status: 409 });
    return NextResponse.json({ ok: true, draft: res.row });
  }

  if (b.op === "cancel") {
    const res = await patchWithRetry(sb, id, (row) => {
      const rr = row.revise_request;
      if (!rr || (rr.status !== "queued" && rr.status !== "error")) return { error: "取り消せる直し待ちはありません" };
      const list = Array.isArray(row.pending_comments) ? row.pending_comments : [];
      return { revise_request: null, pending_comments: [...rr.comments, ...list] };
    });
    if (!res.ok) return NextResponse.json({ ok: false, error: res.error, draft: res.row }, { status: 409 });
    return NextResponse.json({ ok: true, draft: res.row });
  }

  // ---- 版を動かす操作は、画面が読んだ版と同じときだけ
  const row = await getDraft(sb, id);
  if (!row) return NextResponse.json({ ok: false, error: "not found" }, { status: 404 });
  if (b.updatedAt && b.updatedAt !== row.updated_at) {
    return NextResponse.json({ ok: false, error: "ほかの端末で更新されました。読み直しました", draft: row }, { status: 409 });
  }
  if (row.status !== "open" && b.op !== "reopen") {
    return NextResponse.json({ ok: false, error: "確定済みです" }, { status: 409 });
  }
  const versions: DraftVersion[] = Array.isArray(row.versions) ? [...row.versions] : [];
  const cur = currentVersion(versions);
  if (!cur) return NextResponse.json({ ok: false, error: "版がありません" }, { status: 400 });
  const now = new Date().toISOString();

  if (b.op === "manual") {
    const text = String(b.text || "");
    if (!text.trim() || text === cur.text) return NextResponse.json({ ok: false, error: "変わっていません" }, { status: 400 });
    const next: DraftVersion = { label: nextLabel(versions), text: text.slice(0, 20000), at: now, by: "owner", note: b.note?.slice(0, 1000) };
    versions.push(next);
    const saved = await saveVersions(sb, row, versions);
    if (!saved.ok) return NextResponse.json({ ok: false, error: saved.error }, { status: 409 });
    await logRevision(sb, saved.row, cur, next, "revise", { note: b.note || "手で直した" });
    return NextResponse.json({ ok: true, draft: saved.row });
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
