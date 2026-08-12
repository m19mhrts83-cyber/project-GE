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
    const { error } = await supabase.auth.signInWithPassword({
      email: email.trim(),
      password: password.trim(),
    });
    setBusy(false);
    if (error) {
      const raw = error.message || "";
      if (/invalid login credentials/i.test(raw)) {
        setMsg(
          "メールまたはパスワードが違います。新しいサイトなので自動入力が Gmail 用になっていることがあります。正本は .env.jarvis_private の JARVIS_DASHBOARD_PASSWORD です。"
        );
        return;
      }
      setMsg(raw);
      return;
    }
    window.location.href = "/";
  }

  return (
    <div className="login-wrap">
      <div className="login-card">
        <h1>KURASHIFT</h1>
        <p className="sub">
          暮らしを整え、資産を動かす。Jarvis ダッシュボードと同じアカウントです（クッキーは共有しません）。
        </p>
        <form onSubmit={signInPassword} autoComplete="on">
          <label className="meta">メール</label>
          <input
            type="email"
            name="email"
            autoComplete="username"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
          />
          <label className="meta">パスワード</label>
          <input
            type="password"
            name="password"
            autoComplete="current-password"
            required
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
          <button type="submit" className="btn primary" disabled={busy}>
            {busy ? "ログイン中…" : "ログイン"}
          </button>
        </form>
        <p className="meta" style={{ marginTop: 14 }}>
          正本: <code>JARVIS_DASHBOARD_LOGIN_EMAIL</code> ＋{" "}
          <code>JARVIS_DASHBOARD_PASSWORD</code>
        </p>
        {msg ? <p className="bad">{msg}</p> : null}
      </div>
    </div>
  );
}
