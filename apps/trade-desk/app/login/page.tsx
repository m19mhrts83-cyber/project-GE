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
      email,
      password,
    });
    setBusy(false);
    if (error) {
      setMsg(error.message);
      return;
    }
    window.location.href = "/";
  }

  return (
    <div className="login-wrap">
      <div className="login-card">
        <h1>Trade Desk</h1>
        <p className="sub">株・資産。Jarvis ダッシュボードと同じログインです。</p>
        <form onSubmit={signInPassword}>
          <label className="meta">メール</label>
          <input
            type="email"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
          />
          <label className="meta">パスワード</label>
          <input
            type="password"
            required
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
          <button type="submit" className="btn primary" disabled={busy}>
            {busy ? "ログイン中…" : "ログイン"}
          </button>
        </form>
        {msg ? <p className="bad">{msg}</p> : null}
      </div>
    </div>
  );
}
