"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { useState } from "react";

/** 端末ごとに1回だけ鍵を入れる。次からは Cookie で入れる */
export default function LoginClient() {
  const sp = useSearchParams();
  const router = useRouter();
  const [key, setKey] = useState("");
  const [msg, setMsg] = useState("");
  const [busy, setBusy] = useState(false);
  const setup = sp.get("setup") === "1";
  const next = sp.get("next") || "/";
  const safeNext = next.startsWith("/") && !next.startsWith("//") ? next : "/";

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!key.trim() || busy) return;
    setBusy(true);
    setMsg("");
    try {
      const r = await fetch("/api/login", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ key }),
      });
      if (r.ok) {
        router.replace(safeNext);
        return;
      }
      setMsg(r.status === 503 ? "まだ鍵が設定されていません" : "鍵が違います");
    } catch {
      setMsg("つながりませんでした。もう一度");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="glass" style={{ padding: 20 }}>
      <div className="eyebrow acc">LOOPWARE</div>
      <p style={{ margin: "8px 0 4px", fontSize: 16, fontWeight: 700 }}>この端末で使い始める</p>
      {setup ? (
        <p className="meta">
          判断デスクには件名や相手の名前が出るため、鍵を決めてから開きます。Vercel の
          jarvis-loopware に LOOPWARE_ACCESS_KEY を設定してください。
        </p>
      ) : (
        <p className="meta">鍵を一度入れると、この端末では180日入力不要です。Slack のリンクからはそのまま入れます。</p>
      )}
      <form onSubmit={submit} style={{ marginTop: 12, display: "grid", gap: 10 }}>
        <input
          type="password"
          autoComplete="current-password"
          placeholder="鍵"
          value={key}
          onChange={(e) => setKey(e.target.value)}
          disabled={setup}
        />
        <div className="btn-row">
          <button className="primary" type="submit" disabled={setup || busy || !key.trim()}>
            {busy ? "確認中…" : "入る"}
          </button>
        </div>
        {msg ? <p className="meta" style={{ color: "var(--alert)" }}>{msg}</p> : null}
      </form>
    </div>
  );
}
