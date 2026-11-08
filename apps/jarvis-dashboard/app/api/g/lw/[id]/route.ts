import { NextResponse, type NextRequest } from "next/server";
import { htmlPage, isMailActionTriageId, maSigOk, type MailActionSlackAction } from "@/lib/mailActionSlackAction";
import { loopwareHref } from "@/lib/loopwareLink";

export const runtime = "nodejs";

/**
 * Slack のメールカード → ループウェアの判断デスクへの中継。
 *   /api/g/lw/{triage_id}?s={hmac10}   （署名は ma:{id}:loopware、MAIL_ACTION_TOKEN）
 * ここで入場用の t=（LOOPWARE_ACCESS_KEY・7日）を付けて /desk?surface=triage&item= へ転送する。
 * 投稿スクリプト（GHA / Mac）にループウェアの鍵を持たせないため。
 */
export async function GET(request: NextRequest, ctx: { params: Promise<{ id: string }> }) {
  const { id } = await ctx.params;
  const tid = String(id || "").trim();
  if (!isMailActionTriageId(tid)) {
    return htmlPage("エラー", "ID が不正です", false);
  }
  const sig = request.nextUrl.searchParams.get("s");
  if (!maSigOk(tid, "loopware" as MailActionSlackAction, sig)) {
    return htmlPage("認証エラー", "リンクの署名が一致しません。Slack のカードから開き直してください", false);
  }
  if (!(process.env.LOOPWARE_ACCESS_KEY || "").trim()) {
    return htmlPage(
      "ループウェアの鍵が未設定です",
      "Jarvis ダッシュボードに LOOPWARE_ACCESS_KEY がまだ入っていません（scripts/loopware_env_setup.py）。それまでは Slack のボタンか Dashboard の詳細から判断してください",
      false,
    );
  }
  return NextResponse.redirect(loopwareHref("/desk", { surface: "triage", item: tid }), 302);
}
