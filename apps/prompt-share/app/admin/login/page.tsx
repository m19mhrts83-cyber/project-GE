"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { SiteHeader } from "@/components/SiteChrome";

export default function AdminLoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError("");
    const res = await fetch("/api/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, password })
    });
    const json = await res.json();
    setLoading(false);
    if (!res.ok) {
      setError(json.error || "ログインに失敗しました");
      return;
    }
    router.push("/admin");
  };

  return (
    <>
      <SiteHeader />
      <main className="container" style={{ padding: "2rem 0", maxWidth: 480 }}>
        <h1 className="h1">管理者ログイン</h1>
        <p className="muted">kamiooya-qa の admin ユーザーでログインします。</p>
        <form className="card" onSubmit={onSubmit}>
          <div className="field">
            <label>メールアドレス</label>
            <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} required />
          </div>
          <div className="field">
            <label>パスワード</label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
            />
          </div>
          {error ? <p className="error">{error}</p> : null}
          <button className="btn" type="submit" disabled={loading}>
            {loading ? "ログイン中…" : "ログイン"}
          </button>
        </form>
      </main>
    </>
  );
}
