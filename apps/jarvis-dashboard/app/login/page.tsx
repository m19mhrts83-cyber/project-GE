"use client";

import { useState } from "react";
import { createClient } from "@/lib/supabase/client";

export default function LoginPage() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [msg, setMsg] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function signInPassword(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setMsg(null);
    const supabase = createClient();
    const { error } = await supabase.auth.signInWithPassword({ email, password });
    setBusy(false);
    if (error) {
      setMsg(error.message);
      return;
    }
    window.location.href = "/";
  }

  async function signInGoogle() {
    setMsg(
      "Google ログインは OAuth クライアント設定後に有効になります。当面はメール＋パスワードを使ってください。"
    );
    const supabase = createClient();
    const origin =
      process.env.NEXT_PUBLIC_SITE_URL || window.location.origin;
    const { error } = await supabase.auth.signInWithOAuth({
      provider: "google",
      options: {
        redirectTo: `${origin}/auth/callback`,
        queryParams: { prompt: "select_account" },
      },
    });
    if (error) setMsg(error.message);
  }

  return (
    <div className="login-wrap">
      <div className="login-card">
        <h1>Jarvis Dashboard</h1>
        <p className="sub">自分用（運営提供 kamiooya-qa とは別）</p>
        <form onSubmit={signInPassword} style={{ textAlign: "left" }}>
          <label style={{ display: "block", fontSize: "0.85rem", marginBottom: 4 }}>
            メール
          </label>
          <input
            type="email"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            style={{
              width: "100%",
              padding: "8px 10px",
              marginBottom: 12,
              borderRadius: 8,
              border: "1px solid var(--line)",
            }}
          />
          <label style={{ display: "block", fontSize: "0.85rem", marginBottom: 4 }}>
            パスワード
          </label>
          <input
            type="password"
            required
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            style={{
              width: "100%",
              padding: "8px 10px",
              marginBottom: 16,
              borderRadius: 8,
              border: "1px solid var(--line)",
            }}
          />
          <button
            type="submit"
            className="btn primary"
            disabled={busy}
            style={{ width: "100%" }}
          >
            {busy ? "ログイン中…" : "ログイン"}
          </button>
        </form>
        <p className="sub" style={{ marginTop: 16 }}>
          パスワードは <code>.env.jarvis_private</code> の{" "}
          <code>JARVIS_DASHBOARD_PASSWORD</code>（Jarvis が設定済み）
        </p>
        <button
          type="button"
          className="btn"
          onClick={signInGoogle}
          style={{ marginTop: 8, width: "100%" }}
        >
          Google でログイン（準備中）
        </button>
        {msg ? (
          <p className="sub" style={{ color: "var(--high)", marginTop: 12 }}>
            {msg}
          </p>
        ) : null}
      </div>
    </div>
  );
}
