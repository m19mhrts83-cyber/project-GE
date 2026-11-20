import { NextResponse, type NextRequest } from "next/server";
import {
  fetchMailActionTriage,
  isMailActionTriageId,
  maOpSigOk,
  saveMailActionDraft,
} from "@/lib/mailActionSlackAction";
import { composeDraft, proofreadDraft, reviseDraft, type DraftEngine } from "@/lib/mailDraftCheck";
import { geminiPaidConfigured } from "@/lib/geminiPaid";
import { createServiceClient } from "@/lib/supabase/admin";
import { retrieveYoritooriForAsk } from "@/lib/onedrive/retrieveYoritoori";
import { commHistoryForReply } from "@/lib/commHistoryServer";

export const runtime = "nodejs";
// Mac の定額 AI を最大 55 秒待つ
export const maxDuration = 90;

/**
 * 判断デスク（loopware）の返信欄から呼ぶ（サーバ間・JSON・ログイン不要・HMAC `ma:{id}:lwdraft`）。
 *   op=compose   届いたメール＋最近のやり取り（台帳。無ければ md 末尾）＋松野さんの指示（声）から下書きを作る
 *   op=proofread 誤字脱字だけ直す（指示不要）
 *   op=revise    指示どおり書き直す
 *   op=context   最近のやり取り（台帳。無ければ md 末尾）を読むだけ（AI は使わない）
 *   op=status    Mac の定額 AI の係が動いているか（最後の生存報告から何秒か）。AI は使わない
 * engine=gemini は、Mac が応答しないときに松野さんが画面で1回ごとに了承したときだけ（従量課金）。
 * 作った下書きは triage_items.draft_text に保存（Slack の返信モーダルと同じ置き場所）。
 * AI は従量課金を使わず、Mac の定額 AI（lib/flatAi.ts）に頼む。
 */

type Body = { s?: string; op?: string; draft?: string; instruction?: string; engine?: string };

/** Mac の係（scripts/jarvis_flat_ai_worker.py）は 60 秒ごとに sync_meta へ生存報告する */
const HEARTBEAT_KEY = "flat_ai_worker_at";

const PENDING_RE = /作成中/;

function out(json: Record<string, unknown>, status = 200) {
  return NextResponse.json(json, { status, headers: { "cache-control": "private, no-store" } });
}

export async function POST(request: NextRequest, ctx: { params: Promise<{ id: string }> }) {
  const { id: raw } = await ctx.params;
  const id = decodeURIComponent(raw || "").trim();
  if (!id || !isMailActionTriageId(id)) return out({ ok: false, message: "triage_id が不正です" }, 400);
  let b: Body;
  try {
    b = (await request.json()) as Body;
  } catch {
    return out({ ok: false, message: "bad json" }, 400);
  }
  if (!maOpSigOk(id, "lwdraft", b.s)) return out({ ok: false, message: "署名が無効です" }, 401);

  const row = await fetchMailActionTriage(id);
  if (!row) return out({ ok: false, message: "対象のメールが見つかりません" }, 404);
  const op = String(b.op || "");
  const draft = String(b.draft || "").slice(0, 12000);
  const instruction = String(b.instruction || "").trim().slice(0, 2000);
  const engine: DraftEngine = b.engine === "gemini" ? "gemini" : "flat";

  // 背景は台帳（comm_items：チャネル横断の直近やり取り＋自分の過去の文面）を先に使い、
  // 台帳で相手が見つからない・空のときだけ OneDrive のやり取り md 末尾に切り替える。
  const history = async () => {
    const db = await commHistoryForReply({
      folder: row.folder,
      partner: row.partner,
      email: row.from_email,
    }).catch(() => null);
    if (db?.ok && db.promptBlock) return db;
    return mdHistory();
  };
  const mdHistory = async () =>
    retrieveYoritooriForAsk({
      lane: row.lane,
      title: row.subject,
      summary: row.summary,
      payload: { ...(row.payload || {}), partner: row.partner, folder: row.folder },
    }).catch(() => null);

  if (op === "status") {
    let ageSec: number | null = null;
    try {
      const sb = createServiceClient();
      const { data } = sb
        ? await sb.from("sync_meta").select("value,updated_at").eq("key", HEARTBEAT_KEY).maybeSingle()
        : { data: null };
      const t = Date.parse(String(data?.updated_at || String(data?.value || "").split(" ")[0] || ""));
      if (Number.isFinite(t)) ageSec = Math.max(0, Math.round((Date.now() - t) / 1000));
    } catch {
      ageSec = null;
    }
    return out({ ok: true, macAgeSec: ageSec, macAlive: ageSec !== null && ageSec < 180, gemini: geminiPaidConfigured() });
  }

  if (op === "context") {
    const h = await history();
    if (!h || !h.ok || !h.promptBlock) return out({ ok: true, log: null, message: h?.notice || "" });
    // 台帳の背景は最大 6000 字に整えてあるのでそのまま見せる。md は末尾 3500 字だけ
    const max = String(h.path || "").startsWith("台帳") ? 6000 : 3500;
    const tail = h.promptBlock.length > max ? `…\n${h.promptBlock.slice(-max)}` : h.promptBlock;
    return out({ ok: true, log: { folder: h.path || "", notice: h.notice, tail } });
  }

  if (String(row.status || "") === "sent") return out({ ok: false, message: "すでに送信済みです" }, 409);

  let r;
  let notice = "";
  if (op === "compose") {
    const h = await history();
    r = await composeDraft({
      who: String(row.partner || row.from_email || "相手"),
      subject: String(row.subject || ""),
      inbound: String(row.original_body || ""),
      history: h?.ok ? h.promptBlock : "",
      instruction,
      engine,
    });
    notice = h?.ok && h.chars ? "これまでのやり取りを踏まえた下書きです" : "届いたメールから作った下書きです（やり取り履歴なし）";
  } else if (op === "proofread") {
    r = await proofreadDraft(draft, engine);
  } else if (op === "revise") {
    r = await reviseDraft(draft, instruction, engine);
  } else {
    return out({ ok: false, message: "op が不正です" }, 400);
  }

  if (!r.ok) {
    const pending = engine === "flat" && PENDING_RE.test(r.error);
    return out({ ok: false, pending, message: r.error }, pending ? 200 : 502);
  }
  await saveMailActionDraft(id, r.text, `loopware_${op}`).catch(() => undefined);
  return out({ ok: true, text: r.text, changes: r.changes, message: notice, engine });
}

export async function HEAD() {
  return new NextResponse(null, { status: 200 });
}
