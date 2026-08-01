import Shell from "@/components/Shell";
import StatusToggle from "@/components/StatusToggle";
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
    .order("updated_at", { ascending: false })
    .limit(120);

  const activeCards = (cards || []).filter((c) => c.status === "active");
  const archivedCards = (cards || []).filter((c) => c.status === "archived");

  return (
    <Shell active={active}>
      <h1>{title}</h1>
      <p className="sub">
        Mac のやり取り・Journal から集約。不要なカードはアーカイブできます。
      </p>
      <div className="stats">
        <div className="stat">
          アクティブ <strong>{activeCards.length}</strong>
        </div>
        <div className="stat">
          アーカイブ <strong>{archivedCards.length}</strong>
        </div>
      </div>
      <h2>アクティブ</h2>
      {!activeCards.length ? (
        <p className="empty">
          まだ push されていません（jarvis_dashboard_lanes.py --push）
        </p>
      ) : (
        activeCards.map((c) => (
          <article key={c.id} className="card">
            <header>
              <span className="lvl">{c.kind}</span>
              <strong>{c.title}</strong>
              <StatusToggle
                table="cards"
                id={c.id}
                status={c.status}
                path={active}
              />
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
      <h2>アーカイブ</h2>
      {!archivedCards.length ? (
        <p className="empty">なし</p>
      ) : (
        archivedCards.map((c) => (
          <article key={c.id} className="card">
            <header>
              <strong>{c.title}</strong>
              <StatusToggle
                table="cards"
                id={c.id}
                status={c.status}
                path={active}
              />
            </header>
            <p className="sum">{c.summary}</p>
          </article>
        ))
      )}
    </Shell>
  );
}
