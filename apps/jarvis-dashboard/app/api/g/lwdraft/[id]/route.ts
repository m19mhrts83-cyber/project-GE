import { NextResponse, type NextRequest } from "next/server";
import {
  fetchMailActionTriage,
  isMailActionTriageId,
  maOpSigOk,
  saveMailActionDraft,
} from "@/lib/mailActionSlackAction";
import { composeDraft, proofreadDraft, reviseDraft } from "@/lib/mailDraftCheck";
import { retrieveYoritooriForAsk } from "@/lib/onedrive/retrieveYoritoori";

export const runtime = "nodejs";
// Mac の定額 AI を最大 55 秒待つ
export const maxDuration = 90;

/**
 * 判断デスク（loopware）の返信欄から呼ぶ（サーバ間・JSON・ログイン不要・HMAC `ma:{id}:lwdraft`）。
 *   op=compose   届いたメール＋やり取り md の末尾＋松野さんの指示（声）から下書きを作る
 *   op=proofread 誤字脱字だけ直す（指示不要）
 *   op=revise    指示どおり書き直す
 *   op=context   やり取り md の末尾を読むだけ（AI は使わない）
 * 作った下書きは triage_items.draft_text に保存（Slack の返信モーダルと同じ置き場所）。
 * AI は従量課金を使わず、Mac の定額 AI（lib/flatAi.ts）に頼む。
 */

type Body = { s?: string; op?: string; draft?: string; instruction?: string };

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

  const history = async () =>
    retrieveYoritooriForAsk({
      lane: row.lane,
      title: row.subject,
      summary: row.summary,
      payload: { ...(row.payload || {}), partner: row.partner, folder: row.folder },
    }).catch(() => null);

  if (op === "context") {
    const h = await history();
    if (!h || !h.ok || !h.promptBlock) return out({ ok: true, log: null, message: h?.notice || "" });
    const tail = h.promptBlock.length > 3500 ? `…\n${h.promptBlock.slice(-3500)}` : h.promptBlock;
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
    });
    notice = h?.ok && h.chars ? "これまでのやり取りを踏まえた下書きです" : "届いたメールから作った下書きです（やり取り履歴なし）";
  } else if (op === "proofread") {
    r = await proofreadDraft(draft);
  } else if (op === "revise") {
    r = await reviseDraft(draft, instruction);
  } else {
    return out({ ok: false, message: "op が不正です" }, 400);
  }

  if (!r.ok) {
    const pending = PENDING_RE.test(r.error);
    return out({ ok: false, pending, message: r.error }, pending ? 200 : 502);
  }
  await saveMailActionDraft(id, r.text, `loopware_${op}`).catch(() => undefined);
  return out({ ok: true, text: r.text, changes: r.changes, message: notice });
}

export async function HEAD() {
  return new NextResponse(null, { status: 200 });
}
