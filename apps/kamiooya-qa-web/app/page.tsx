/* eslint-disable @next/next/no-html-link-for-pages */
"use client";

import { useMemo, useState } from "react";

type Citation = {
  commentId: string;
  postedAt: string | null;
  authorName: string | null;
  sourceType: string | null;
  snippet: string;
};

export default function Page() {
  const [q, setQ] = useState("");
  const [loading, setLoading] = useState(false);
  const [answer, setAnswer] = useState<string | null>(null);
  const [citations, setCitations] = useState<Citation[]>([]);
  const [usedAI, setUsedAI] = useState<boolean | null>(null);

  const canAsk = useMemo(() => q.trim().length > 0 && !loading, [q, loading]);

  async function ask() {
    const message = q.trim();
    if (!message) return;
    setLoading(true);
    setAnswer(null);
    setCitations([]);
    setUsedAI(null);
    try {
      const res = await fetch("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message })
      });
      const json = (await res.json().catch(() => null)) as any;
      setAnswer(String(json?.answer ?? ""));
      setCitations(Array.isArray(json?.citations) ? json.citations : []);
      setUsedAI(Boolean(json?.usedAI));
    } finally {
      setLoading(false);
    }
  }

  return (
    <main style={{ minHeight: "100vh", display: "flex", justifyContent: "center" }}>
      <div style={{ width: "min(980px, 100%)", padding: 20 }}>
        <div
          style={{
            background: "linear-gradient(180deg, #101b33 0%, #0b1220 100%)",
            border: "1px solid rgba(148,163,184,0.18)",
            borderRadius: 16,
            padding: 18
          }}
        >
          <div style={{ display: "flex", gap: 12, alignItems: "baseline", flexWrap: "wrap" }}>
            <h1 style={{ fontSize: 20, margin: 0, fontWeight: 800 }}>神・大家さん倶楽部 情報Q&A</h1>
            <span style={{ fontSize: 12, color: "#94a3b8" }}>
              参照ファイル（CSV）を根拠に回答します
            </span>
          </div>

          <div style={{ marginTop: 14, display: "flex", gap: 10 }}>
            <input
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder="例: WeStudyの差分CSVの作り方は？ / 取込の列名は？"
              onKeyDown={(e) => {
                if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) ask();
              }}
              style={{
                flex: 1,
                padding: "12px 12px",
                borderRadius: 12,
                border: "1px solid rgba(148,163,184,0.25)",
                background: "rgba(2,6,23,0.55)",
                color: "#e5e7eb",
                outline: "none"
              }}
            />
            <button
              onClick={ask}
              disabled={!canAsk}
              style={{
                padding: "12px 14px",
                borderRadius: 12,
                border: "1px solid rgba(148,163,184,0.25)",
                background: canAsk ? "#2563eb" : "rgba(37,99,235,0.35)",
                color: "white",
                cursor: canAsk ? "pointer" : "not-allowed",
                fontWeight: 700
              }}
              title="送信（Ctrl+Enter / Cmd+Enter）"
            >
              {loading ? "回答中…" : "質問する"}
            </button>
          </div>

          <div style={{ marginTop: 10, fontSize: 12, color: "#94a3b8" }}>
            Ctrl+Enter（MacはCmd+Enter）で送信。Vercel上でAI回答を使う場合は環境変数
            <code style={{ marginLeft: 6 }}>OPENAI_API_KEY</code> を設定してください。
          </div>
        </div>

        <section style={{ marginTop: 16 }}>
          <div
            style={{
              borderRadius: 16,
              border: "1px solid rgba(148,163,184,0.18)",
              background: "rgba(15,23,42,0.55)",
              padding: 16
            }}
          >
            <div style={{ display: "flex", justifyContent: "space-between", gap: 12 }}>
              <h2 style={{ fontSize: 14, margin: 0, color: "#e2e8f0" }}>回答</h2>
              {usedAI !== null && (
                <span style={{ fontSize: 12, color: "#94a3b8" }}>
                  {usedAI ? "AI回答（参照ベース）" : "検索結果（AIなし）"}
                </span>
              )}
            </div>

            <pre
              style={{
                margin: "12px 0 0",
                whiteSpace: "pre-wrap",
                lineHeight: 1.6,
                fontSize: 13,
                color: answer ? "#e5e7eb" : "#94a3b8"
              }}
            >
              {answer ?? "ここに回答が表示されます。"}
            </pre>
          </div>
        </section>

        <section style={{ marginTop: 14 }}>
          <div
            style={{
              borderRadius: 16,
              border: "1px solid rgba(148,163,184,0.18)",
              background: "rgba(2,6,23,0.35)",
              padding: 16
            }}
          >
            <h2 style={{ fontSize: 14, margin: 0, color: "#e2e8f0" }}>参照（上位一致）</h2>
            {citations.length === 0 ? (
              <div style={{ marginTop: 10, fontSize: 12, color: "#94a3b8" }}>
                回答後に、根拠として使った（または一致した）箇所がここに表示されます。
              </div>
            ) : (
              <div style={{ marginTop: 10, display: "grid", gap: 10 }}>
                {citations.map((c) => (
                  <div
                    key={c.commentId}
                    style={{
                      borderRadius: 12,
                      border: "1px solid rgba(148,163,184,0.18)",
                      background: "rgba(15,23,42,0.55)",
                      padding: 12
                    }}
                  >
                    <div style={{ fontSize: 12, color: "#94a3b8" }}>
                      [{c.sourceType ?? "不明"}] {c.postedAt ?? ""} {c.authorName ?? ""} #{c.commentId}
                    </div>
                    <div style={{ marginTop: 6, fontSize: 13, color: "#e5e7eb" }}>{c.snippet}</div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </section>

        <footer style={{ marginTop: 18, paddingBottom: 30, color: "#64748b", fontSize: 12 }}>
          このアプリは「参照データ（CSV）」をもとに回答します。個人情報・機密情報を含むデータを公開する場合は、公開前に必ず内容を精査してください。
        </footer>
      </div>
    </main>
  );
}

