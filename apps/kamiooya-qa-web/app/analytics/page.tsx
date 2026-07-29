"use client";

import { FormEvent, useMemo, useState, type CSSProperties } from "react";

type Overview = {
  ok: boolean;
  range_days: number;
  totals: {
    total: number;
    normal: number;
    semantic: number;
    semantic_ratio: number;
    normal_ratio: number;
  };
  daily: Array<{ day: string; normal: number; semantic: number; total: number }>;
  top_queries: Array<{ query: string; count: number; semantic: number; normal: number }>;
  recent_events: Array<{
    id: number;
    created_at: string;
    search_mode: string;
    query_text: string;
    comment_hit_count?: number | null;
    chunk_hit_count?: number | null;
  }>;
};

const SECRET_KEY = "qa_analytics_secret_v1";

export default function AnalyticsPage() {
  const [secret, setSecret] = useState(() => {
    if (typeof window === "undefined") return "";
    return sessionStorage.getItem(SECRET_KEY) || "";
  });
  const [days, setDays] = useState(14);
  const [data, setData] = useState<Overview | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const maxDaily = useMemo(() => {
    if (!data?.daily?.length) return 1;
    return Math.max(1, ...data.daily.map((d) => d.total));
  }, [data]);

  async function load(e?: FormEvent) {
    if (e) e.preventDefault();
    setLoading(true);
    setError("");
    try {
      const res = await fetch(`/api/analytics/overview?days=${days}`, {
        headers: { "x-analytics-secret": secret },
      });
      const json = await res.json();
      if (!res.ok) throw new Error(json.errorMessage || `HTTP ${res.status}`);
      sessionStorage.setItem(SECRET_KEY, secret);
      setData(json);
    } catch (err) {
      setData(null);
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }

  return (
    <main
      style={{
        maxWidth: 1100,
        margin: "0 auto",
        padding: "28px 18px 60px",
        color: "#e5e7eb",
      }}
    >
      <header style={{ marginBottom: 24 }}>
        <p style={{ margin: 0, color: "#93c5fd", fontSize: 13 }}>Phase 13 · 運営分析</p>
        <h1 style={{ margin: "6px 0 8px", fontSize: 28 }}>Q&A 検索ダッシュボード</h1>
        <p style={{ margin: 0, color: "#9ca3af", fontSize: 14, lineHeight: 1.6 }}>
          通常検索と意味検索の利用比率・日次推移・質問傾向を確認できます。
          秘密鍵は <code>SEMANTIC_SEARCH_SHARED_SECRET</code>（または{" "}
          <code>ANALYTICS_DASHBOARD_SECRET</code>）です。
        </p>
      </header>

      <form
        onSubmit={load}
        style={{
          display: "flex",
          flexWrap: "wrap",
          gap: 10,
          alignItems: "end",
          marginBottom: 22,
          padding: 14,
          border: "1px solid #1f2937",
          borderRadius: 12,
          background: "#111827",
        }}
      >
        <label style={{ display: "grid", gap: 6, flex: "1 1 240px" }}>
          <span style={{ fontSize: 12, color: "#9ca3af" }}>アクセス秘密鍵</span>
          <input
            type="password"
            value={secret}
            onChange={(e) => setSecret(e.target.value)}
            required
            style={inputStyle}
            placeholder="shared secret"
          />
        </label>
        <label style={{ display: "grid", gap: 6, width: 120 }}>
          <span style={{ fontSize: 12, color: "#9ca3af" }}>期間（日）</span>
          <select
            value={days}
            onChange={(e) => setDays(Number(e.target.value))}
            style={inputStyle}
          >
            {[7, 14, 30, 60, 90].map((d) => (
              <option key={d} value={d}>
                {d}
              </option>
            ))}
          </select>
        </label>
        <button type="submit" disabled={loading} style={buttonStyle}>
          {loading ? "読み込み中…" : "表示する"}
        </button>
      </form>

      {error ? (
        <p style={{ color: "#fca5a5", marginBottom: 16 }}>エラー: {error}</p>
      ) : null}

      {!data ? (
        <p style={{ color: "#9ca3af" }}>秘密鍵を入力して表示してください。</p>
      ) : (
        <>
          <section
            style={{
              display: "grid",
              gridTemplateColumns: "repeat(auto-fit, minmax(160px, 1fr))",
              gap: 12,
              marginBottom: 22,
            }}
          >
            <StatCard label="合計" value={String(data.totals.total)} />
            <StatCard
              label="通常検索"
              value={String(data.totals.normal)}
              sub={`${(data.totals.normal_ratio * 100).toFixed(1)}%`}
            />
            <StatCard
              label="意味検索"
              value={String(data.totals.semantic)}
              sub={`${(data.totals.semantic_ratio * 100).toFixed(1)}%`}
              accent
            />
            <StatCard label="集計日数" value={String(data.range_days)} />
          </section>

          <section style={panelStyle}>
            <h2 style={h2Style}>日次推移（通常 / 意味）</h2>
            {data.daily.length === 0 ? (
              <p style={{ color: "#9ca3af" }}>この期間のデータはありません。</p>
            ) : (
              <div style={{ display: "grid", gap: 10 }}>
                {data.daily.map((d) => (
                  <div key={d.day}>
                    <div
                      style={{
                        display: "flex",
                        justifyContent: "space-between",
                        fontSize: 12,
                        marginBottom: 4,
                        color: "#9ca3af",
                      }}
                    >
                      <span>{d.day}</span>
                      <span>
                        通常 {d.normal} / 意味 {d.semantic}（計 {d.total}）
                      </span>
                    </div>
                    <div
                      style={{
                        display: "flex",
                        height: 14,
                        borderRadius: 999,
                        overflow: "hidden",
                        background: "#0b1220",
                        border: "1px solid #1f2937",
                      }}
                    >
                      <div
                        title={`通常 ${d.normal}`}
                        style={{
                          width: `${(d.normal / maxDaily) * 100}%`,
                          background: "#64748b",
                        }}
                      />
                      <div
                        title={`意味 ${d.semantic}`}
                        style={{
                          width: `${(d.semantic / maxDaily) * 100}%`,
                          background: "#3b82f6",
                        }}
                      />
                    </div>
                  </div>
                ))}
              </div>
            )}
          </section>

          <section style={{ ...panelStyle, marginTop: 16 }}>
            <h2 style={h2Style}>よくある質問（上位）</h2>
            <div style={{ overflowX: "auto" }}>
              <table style={tableStyle}>
                <thead>
                  <tr>
                    <th style={thStyle}>質問</th>
                    <th style={thStyle}>合計</th>
                    <th style={thStyle}>通常</th>
                    <th style={thStyle}>意味</th>
                  </tr>
                </thead>
                <tbody>
                  {data.top_queries.map((q) => (
                    <tr key={q.query}>
                      <td style={tdStyle}>{q.query}</td>
                      <td style={tdStyle}>{q.count}</td>
                      <td style={tdStyle}>{q.normal}</td>
                      <td style={tdStyle}>{q.semantic}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>

          <section style={{ ...panelStyle, marginTop: 16 }}>
            <h2 style={h2Style}>直近イベント</h2>
            <div style={{ overflowX: "auto" }}>
              <table style={tableStyle}>
                <thead>
                  <tr>
                    <th style={thStyle}>日時</th>
                    <th style={thStyle}>モード</th>
                    <th style={thStyle}>質問</th>
                    <th style={thStyle}>hit</th>
                  </tr>
                </thead>
                <tbody>
                  {data.recent_events.map((ev) => (
                    <tr key={ev.id}>
                      <td style={tdStyle}>
                        {String(ev.created_at || "").replace("T", " ").slice(0, 19)}
                      </td>
                      <td style={tdStyle}>
                        {ev.search_mode === "semantic" ? "意味" : "通常"}
                      </td>
                      <td style={tdStyle}>{ev.query_text}</td>
                      <td style={tdStyle}>
                        C{ev.comment_hit_count ?? "-"} / K{ev.chunk_hit_count ?? "-"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        </>
      )}
    </main>
  );
}

function StatCard({
  label,
  value,
  sub,
  accent,
}: {
  label: string;
  value: string;
  sub?: string;
  accent?: boolean;
}) {
  return (
    <div
      style={{
        padding: 14,
        borderRadius: 12,
        border: "1px solid #1f2937",
        background: accent ? "#172554" : "#111827",
      }}
    >
      <div style={{ fontSize: 12, color: "#9ca3af" }}>{label}</div>
      <div style={{ fontSize: 28, fontWeight: 700, marginTop: 4 }}>{value}</div>
      {sub ? <div style={{ fontSize: 12, color: "#93c5fd", marginTop: 2 }}>{sub}</div> : null}
    </div>
  );
}

const inputStyle: CSSProperties = {
  width: "100%",
  boxSizing: "border-box",
  padding: "10px 12px",
  borderRadius: 8,
  border: "1px solid #334155",
  background: "#0b1220",
  color: "#e5e7eb",
};

const buttonStyle: CSSProperties = {
  padding: "10px 16px",
  borderRadius: 8,
  border: "none",
  background: "#2563eb",
  color: "#fff",
  fontWeight: 600,
  cursor: "pointer",
};

const panelStyle: CSSProperties = {
  padding: 16,
  borderRadius: 12,
  border: "1px solid #1f2937",
  background: "#111827",
};

const h2Style: CSSProperties = {
  margin: "0 0 12px",
  fontSize: 16,
};

const tableStyle: CSSProperties = {
  width: "100%",
  borderCollapse: "collapse",
  fontSize: 13,
};

const thStyle: CSSProperties = {
  textAlign: "left",
  padding: "8px 6px",
  borderBottom: "1px solid #1f2937",
  color: "#9ca3af",
  fontWeight: 600,
};

const tdStyle: CSSProperties = {
  padding: "8px 6px",
  borderBottom: "1px solid #1f2937",
  verticalAlign: "top",
};
