import { NextResponse, type NextRequest } from "next/server";

export const runtime = "nodejs";

const REDIRECT_URI =
  "https://jarvis-dashboard-amber.vercel.app/api/todoist/oauth/callback";

/**
 * GET /api/todoist/oauth/callback
 * Todoist App Console の OAuth リダイレクト先。
 * code → access_token 交換まで行う（Webhook は交換完了でユーザーに有効化される）。
 * 取得トークンは画面・ログに出さない。API 本線は既存 TODOIST_API_TOKEN。
 */
export async function GET(request: NextRequest) {
  const code = request.nextUrl.searchParams.get("code");
  const error = request.nextUrl.searchParams.get("error");
  const state = request.nextUrl.searchParams.get("state");

  if (error) {
    return htmlPage(
      "承認が拒否／失敗しました",
      `<p>error=${escapeHtml(error)}</p>
<p>App Console に戻ってやり直してください。</p>`,
      400,
    );
  }

  if (!code) {
    return htmlPage(
      "Todoist OAuth コールバック",
      `<p>code がありません。承認URLから開いてください。</p>`,
      400,
    );
  }

  const clientId = (process.env.TODOIST_APP_CLIENT_ID || "").trim();
  const clientSecret = (process.env.TODOIST_APP_CLIENT_SECRET || "").trim();
  if (!clientId || !clientSecret) {
    return htmlPage(
      "設定不足",
      `<p>Vercel に TODOIST_APP_CLIENT_ID / TODOIST_APP_CLIENT_SECRET がありません。</p>
<p>Jarvis に「シークレット同期して」と依頼してください。</p>`,
      503,
    );
  }

  let exchangeOk = false;
  let exchangeDetail = "";
  try {
    const body = new URLSearchParams({
      client_id: clientId,
      client_secret: clientSecret,
      code,
      redirect_uri: REDIRECT_URI,
    });
    const res = await fetch("https://api.todoist.com/oauth/access_token", {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body,
    });
    const text = await res.text();
    if (res.ok) {
      // token は破棄（Webhook 有効化が目的。値は扱わない）
      exchangeOk = true;
      try {
        const json = JSON.parse(text) as { token_type?: string };
        exchangeDetail = json.token_type ? `token_type=${json.token_type}` : "ok";
      } catch {
        exchangeDetail = "ok";
      }
    } else {
      exchangeDetail = `HTTP ${res.status}`;
      console.error("todoist oauth exchange failed", res.status, text.slice(0, 200));
    }
  } catch (e) {
    exchangeDetail = e instanceof Error ? e.name : "error";
    console.error("todoist oauth exchange", e);
  }

  if (!exchangeOk) {
    return htmlPage(
      "トークン交換に失敗しました",
      `<p>Webhook はまだ有効化されていません（${escapeHtml(exchangeDetail)}）。</p>
<p>承認URLからもう一度開き直してください。繰り返し失敗するときは Jarvis に伝えてください。</p>
<p style="color:#666;font-size:0.9rem">state=${escapeHtml(state || "-")}</p>`,
      502,
    );
  }

  return htmlPage(
    "Jarvis Webhook — 承認完了",
    `<p>Todoist アプリの OAuth（トークン交換）が通りました。このタブは閉じてOKです。</p>
<p style="color:#666;font-size:0.9rem">state=${escapeHtml(state || "-")} / ${escapeHtml(exchangeDetail)}（トークンは画面に出していません）</p>
<p>Jarvis に「承認した」と一声ください。受信テストをします。</p>`,
    200,
    "Todoist OAuth OK",
  );
}

function htmlPage(
  heading: string,
  bodyInner: string,
  status: number,
  title = "Todoist OAuth",
) {
  return new NextResponse(
    `<!doctype html><html lang="ja"><meta charset="utf-8"/><title>${escapeHtml(title)}</title>
<body style="font-family:system-ui;padding:2rem;max-width:40rem">
<h1>${escapeHtml(heading)}</h1>
${bodyInner}
</body></html>`,
    { status, headers: { "Content-Type": "text/html; charset=utf-8" } },
  );
}

function escapeHtml(s: string): string {
  return s
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}
