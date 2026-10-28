import { NextResponse, type NextRequest } from "next/server";
import {
  applyMailActionSlack,
  editFormHtml,
  fetchMailActionTriage,
  htmlPage,
  isMailActionTriageId,
  maSigOk,
  parseMaAction,
} from "@/lib/mailActionSlackAction";

export const runtime = "nodejs";

/**
 * メール要対応 Slack 操作（ログイン不要・HMAC）
 *   返信フォーム: GET /api/g/ma/reply/{triage_id}?s=
 *   見送り/Todoist: GET は確認画面のみ（Slack のリンク展開で即実行されないようにする）
 *                   POST + intent=confirm で実行
 *   返信送信:     POST /api/g/ma/reply/{id}（body + intent=send）
 */

function confirmActionHtml(
  action: "skip" | "todoist" | "done",
  id: string,
  sig: string,
): string {
  const title =
    action === "skip" ? "見送りの確認" : action === "done" ? "返信済みの確認" : "Todoist追加の確認";
  const label =
    action === "skip" ? "見送りにする" : action === "done" ? "返信済みにする" : "Todoist に追加する";
  const note =
    action === "skip"
      ? "見送りにすると Slack カードは削除されます。"
      : action === "done"
        ? "LINE／Chatwork などアプリで返信した記録だけ残します（送信はしません）。"
        : "電話・ポータル等の手配用に Todoist へ起票します。";
  const esc = (s: string) =>
    String(s || "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  return `<!doctype html><html lang="ja"><meta charset="utf-8"/>
<title>${esc(title)}</title>
<body style="font-family:system-ui;padding:2rem;max-width:36rem;color:#111">
<h1 style="font-size:1.25rem">${esc(title)}</h1>
<p style="color:#4b5563">${esc(note)}</p>
<p style="color:#6b7280;font-size:0.85rem">id=${esc(id)}</p>
<form method="POST" action="">
<input type="hidden" name="s" value="${esc(sig)}"/>
<div style="margin-top:1.25rem;display:flex;gap:0.75rem;flex-wrap:wrap">
<button type="submit" name="intent" value="confirm" style="background:${action === "skip" ? "#b91c1c" : "#1d4ed8"};color:#fff;border:0;padding:0.65rem 1.1rem;border-radius:8px;font-weight:600">${esc(label)}</button>
<a href="?s=${encodeURIComponent(sig)}&amp;cancel=1" style="align-self:center;color:#6b7280">キャンセル</a>
</div>
</form>
<p style="margin-top:1.5rem;color:#9ca3af;font-size:0.8rem">リンクを開いただけでは実行しません（確認ボタン必須）。</p>
</body></html>`;
}

function resultPageForAction(
  action: "skip" | "todoist" | "reply" | "done",
  result: {
    ok: boolean;
    message: string;
    slack_deleted?: boolean;
    digest_deleted?: boolean;
    digest_updated?: boolean;
    digest_remaining?: number;
  },
) {
  const title =
    action === "skip" ? "見送り" : action === "todoist" ? "Todoist" : "完了";
  let msg = result.message;
  if (action === "skip" && result.ok) {
    if (result.slack_deleted) {
      msg += "\n\nSlack 上のカードは削除しました。";
    } else {
      msg +=
        "\n\n※ Slack カードの自動削除はできませんでした" +
        "（Bot 未設定／Webhook 投稿で ts 無し）。" +
        "チャンネル上のカードは手動で削除してください。";
    }
    if (result.digest_deleted) {
      msg += "\nダイジェストも削除しました。";
    } else if (result.digest_updated) {
      msg += `\nダイジェストを残 ${result.digest_remaining ?? "?"} 件に更新しました。`;
    }
  }
  return htmlPage(result.ok ? title : "失敗", msg, result.ok);
}

export async function GET(
  request: NextRequest,
  ctx: { params: Promise<{ action: string; id: string }> },
) {
  const { action: actionRaw, id: idRaw } = await ctx.params;
  const id = decodeURIComponent(idRaw || "").trim();
  const action = parseMaAction(actionRaw);
  if (!id || !isMailActionTriageId(id) || !action) {
    return htmlPage("エラー", "action または triage_id が不正です", false);
  }

  const sig = request.nextUrl.searchParams.get("s");
  if (!maSigOk(id, action, sig)) {
    return htmlPage(
      "認証エラー",
      "署名が無効です（リンクが古い／トークン不一致の可能性）",
      false,
    );
  }

  if (request.nextUrl.searchParams.get("cancel") === "1") {
    return htmlPage("キャンセル", "編集をキャンセルしました", true);
  }

  if (action === "reply") {
    const row = await fetchMailActionTriage(id);
    if (!row) {
      return htmlPage("エラー", "対象のメール要対応が見つかりません", false);
    }
    if (String(row.status) === "sent") {
      return htmlPage("送信済み", "すでに送信済みです", true);
    }
    return new NextResponse(editFormHtml(row, String(sig || "")), {
      status: 200,
      headers: {
        "Content-Type": "text/html; charset=utf-8",
        "Cache-Control": "private, no-store",
      },
    });
  }

  // skip / todoist: GET は確認のみ（Slack unfurl / プレビューで即実行しない）
  return new NextResponse(confirmActionHtml(action, id, String(sig || "")), {
    status: 200,
    headers: {
      "Content-Type": "text/html; charset=utf-8",
      "Cache-Control": "private, no-store",
    },
  });
}

export async function POST(
  request: NextRequest,
  ctx: { params: Promise<{ action: string; id: string }> },
) {
  const { action: actionRaw, id: idRaw } = await ctx.params;
  const id = decodeURIComponent(idRaw || "").trim();
  const action = parseMaAction(actionRaw);
  if (!id || !isMailActionTriageId(id) || !action) {
    return htmlPage("エラー", "action または triage_id が不正です", false);
  }

  const form = await request.formData();
  const sig = String(form.get("s") || "");
  if (!maSigOk(id, action, sig)) {
    return htmlPage("認証エラー", "署名が無効です", false);
  }

  if (action === "reply") {
    const body = String(form.get("body") || "");
    const intent = String(form.get("intent") || "send");
    if (intent !== "send") {
      return htmlPage("キャンセル", "送信しませんでした", true);
    }
    const result = await applyMailActionSlack(id, "reply", {
      body,
      source: "slack_edit_form",
    });
    return htmlPage(
      result.ok ? "送信完了" : "失敗",
      result.message,
      result.ok,
    );
  }

  const intent = String(form.get("intent") || "");
  if (intent !== "confirm") {
    return htmlPage("キャンセル", "実行しませんでした", true);
  }
  const result = await applyMailActionSlack(id, action, {
    source: "slack_short_link",
  });
  return resultPageForAction(action, result);
}

export async function HEAD() {
  return new NextResponse(null, { status: 200 });
}
