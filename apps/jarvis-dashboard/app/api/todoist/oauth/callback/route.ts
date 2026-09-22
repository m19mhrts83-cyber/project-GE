import { NextResponse, type NextRequest } from "next/server";

export const runtime = "nodejs";

/**
 * GET /api/todoist/oauth/callback
 * Todoist App Console の OAuth リダイレクト先。
 * Webhook 有効化のための承認完了を受け取る（code は表示のみ・トークン交換は任意）。
 */
export async function GET(request: NextRequest) {
  const code = request.nextUrl.searchParams.get("code");
  const error = request.nextUrl.searchParams.get("error");
  const state = request.nextUrl.searchParams.get("state");

  if (error) {
    return new NextResponse(
      `<!doctype html><html lang="ja"><meta charset="utf-8"/><title>Todoist OAuth</title>
<body style="font-family:system-ui;padding:2rem">
<h1>承認が拒否／失敗しました</h1>
<p>error=${escapeHtml(error)}</p>
<p>App Console に戻ってやり直してください。</p>
</body></html>`,
      { status: 400, headers: { "Content-Type": "text/html; charset=utf-8" } },
    );
  }

  if (!code) {
    return new NextResponse(
      `<!doctype html><html lang="ja"><meta charset="utf-8"/><title>Todoist OAuth</title>
<body style="font-family:system-ui;padding:2rem">
<h1>Todoist OAuth コールバック</h1>
<p>code がありません。承認URLから開いてください。</p>
</body></html>`,
      { status: 400, headers: { "Content-Type": "text/html; charset=utf-8" } },
    );
  }

  // Webhook 配信のためには「ユーザーが承認した」こと自体が重要。
  // アクセストークンは既存 TODOIST_API_TOKEN 本線のため、ここでは交換しない。
  return new NextResponse(
    `<!doctype html><html lang="ja"><meta charset="utf-8"/><title>Todoist OAuth OK</title>
<body style="font-family:system-ui;padding:2rem;max-width:40rem">
<h1>Jarvis Webhook — 承認完了</h1>
<p>Todoist アプリの OAuth が通りました。このタブは閉じてOKです。</p>
<p style="color:#666;font-size:0.9rem">state=${escapeHtml(state || "-")} / code 受信済（トークンはチャット・画面に出していません）</p>
<p>Jarvis に「承認した」と一声ください。受信テストをします。</p>
</body></html>`,
    { status: 200, headers: { "Content-Type": "text/html; charset=utf-8" } },
  );
}

function escapeHtml(s: string): string {
  return s
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}
