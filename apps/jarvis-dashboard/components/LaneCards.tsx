import Link from "next/link";
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
        Mac のやり取り・Journal から集約。不要なカードはアーカイブできます。復元は{" "}
        <Link href="/archive" style={{ color: "var(--accent)", fontWeight: 600 }}>
          アーカイブ
        </Link>
        メニューから。
      </p>
      <div className="stats">
        <div className="stat">
          アクティブ <strong>{activeCards.length}</strong>
        </div>
        <div className="stat">
          アーカイブ{" "}
          <strong>
            <Link href="/archive" style={{ color: "inherit" }}>
              {archivedCards.length}
            </Link>
          </strong>
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
                    color: "var(--ink)",
                  }}
                >
                  {c.cursor_prompt}
                </pre>
              </details>
            ) : null}
          </article>
        ))
      )}
      {archivedCards.length > 0 ? (
        <p className="sub" style={{ marginTop: 24 }}>
          このレーンのアーカイブ {archivedCards.length}件 →{" "}
          <Link href="/archive" className="btn">
            アーカイブを見る
          </Link>
        </p>
      ) : null}
    </Shell>
  );
}
