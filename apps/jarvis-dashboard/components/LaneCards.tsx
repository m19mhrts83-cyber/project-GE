import Shell from "@/components/Shell";
import { createClient } from "@/lib/supabase/server";

export default async function LaneCardsPage({
  lane,
  title,
  active,
}: {
  lane: string;
  title: string;
  active: string;
}) {
  const supabase = await createClient();
  const { data: cards } = await supabase
    .from("cards")
    .select("*")
    .eq("lane", lane)
    .eq("status", "active")
    .order("updated_at", { ascending: false })
    .limit(80);

  return (
    <Shell active={active}>
      <h1>{title}</h1>
      <p className="sub">
        Mac のやり取り・Journal から集約。Cursor 調査用プロンプト付き。
      </p>
      <div className="stats">
        <div className="stat">
          カード <strong>{cards?.length ?? 0}</strong>
        </div>
      </div>
      {!cards?.length ? (
        <p className="empty">まだ push されていません（jarvis_dashboard_lanes.py --push）</p>
      ) : (
        cards.map((c) => (
          <article key={c.id} className="card">
            <header>
              <span className="lvl">{c.kind}</span>
              <strong>{c.title}</strong>
            </header>
            <p className="sum">{c.summary}</p>
            {c.cursor_prompt ? (
              <details>
                <summary>Cursorで調べる</summary>
                <pre
                  style={{
                    whiteSpace: "pre-wrap",
                    fontSize: "0.8rem",
                    background: "#fafaf9",
                    padding: 10,
                    borderRadius: 8,
                  }}
                >
                  {c.cursor_prompt}
                </pre>
              </details>
            ) : null}
          </article>
        ))
      )}
    </Shell>
  );
}
