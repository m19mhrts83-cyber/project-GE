"use client";

import { createClient } from "@/lib/supabase/client";

export default function LoginPage() {
  async function signInGoogle() {
    const supabase = createClient();
    const origin =
      process.env.NEXT_PUBLIC_SITE_URL || window.location.origin;
    await supabase.auth.signInWithOAuth({
      provider: "google",
      options: {
        redirectTo: `${origin}/auth/callback`,
        queryParams: { prompt: "select_account" },
      },
    });
  }

  return (
    <div className="login-wrap">
      <div className="login-card">
        <h1>Jarvis Dashboard</h1>
        <p className="sub">自分用（運営提供 kamiooya-qa とは別プロジェクト）</p>
        <button type="button" className="btn primary" onClick={signInGoogle}>
          Google でログイン
        </button>
        <p className="sub" style={{ marginTop: 16 }}>
          Supabase Auth で Google プロバイダを有効にし、リダイレクト URL に
          <code> /auth/callback </code>
          を追加してください。
        </p>
      </div>
    </div>
  );
}
