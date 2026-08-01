import Link from "next/link";
import Shell from "@/components/Shell";
import CardTriageActions, {
  type CardCommentRow,
} from "@/components/CardTriageActions";
import {
  queryLaneBoard,
  type NotionBoardSummary,
} from "@/lib/notionTasks";
import { createClient } from "@/lib/supabase/server";

type CardRow = {
  id: string;
  title: string;
  summary: string | null;
  status: string;
  kind: string;
  cursor_prompt: string | null;
  payload: Record<string, unknown> | null;
};

function BoardSection({ board }: { board: NotionBoardSummary }) {
  return (
    <section className="home-section" style={{ marginTop: 28 }}>
      <h2>Notion 看板</h2>
      {board.boardUrl ? (
        <p className="sub">
          <a href={board.boardUrl} target="_blank" rel="noreferrer" className="btn">
            Notion で開く
          </a>
        </p>
      ) : null}
      {!board.connected ? (
        <p className="empty">
          未接続
          {board.reason ? `（${board.reason}）` : ""}
          。`.env.jarvis_private` と Vercel に NOTION_API_TOKEN を設定し、対象 DB を
          Integration に接続してください。
        </p>
      ) : (
        <>
          <div className="stats">
            {Object.entries(board.byStatus).map(([k, n]) => (
              <div className="stat" key={k}>
                {k} <strong>{n}</strong>
              </div>
            ))}
          </div>
          <h3 style={{ fontSize: "1rem", marginTop: 16 }}>期限切れ</h3>
          {board.overdue.length === 0 ? (
            <p className="empty">期限切れはありません</p>
          ) : (
            <ul className="home-event-list">
              {board.overdue.map((t) => (
                <li key={t.id}>
                  <strong>{t.due}</strong> {t.status}{" "}
                  <a href={t.url} target="_blank" rel="noreferrer">
                    {t.title}
                  </a>
                </li>
              ))}
            </ul>
          )}
          {board.openSample.length > 0 ? (
            <>
              <h3 style={{ fontSize: "1rem", marginTop: 16 }}>進行中サンプル</h3>
              <ul className="home-event-list">
                {board.openSample.map((t) => (
                  <li key={t.id}>
                    {t.status}
                    {t.due ? ` · 期限 ${t.due}` : ""}{" "}
                    <a href={t.url} target="_blank" rel="noreferrer">
                      {t.title}
                    </a>
                  </li>
                ))}
              </ul>
            </>
          ) : null}
        </>
      )}
    </section>
  );
}

export default async function TriageKanbanLane({
  lane,
  title,
  active,
  subtitle,
  children,
}: {
  lane: string;
  title: string;
  active: string;
  subtitle?: string;
  children?: React.ReactNode;
}) {
  const supabase = await createClient();
  const { data: cards } = await supabase
    .from("cards")
    .select("id,title,summary,status,kind,cursor_prompt,payload")
    .eq("lane", lane)
    .order("updated_at", { ascending: false })
    .limit(120);

  const list = (cards || []) as CardRow[];
  const activeCards = list.filter((c) => c.status === "active");
  const promotedCards = list.filter((c) => c.status === "promoted");
  const archivedCount = list.filter((c) => c.status === "archived").length;

  const ids = [...activeCards, ...promotedCards].map((c) => c.id);
  const commentsByCard = new Map<string, CardCommentRow[]>();
  if (ids.length) {
    const { data: comments } = await supabase
      .from("card_comments")
      .select("id,card_id,role,body,created_at")
      .in("card_id", ids)
      .order("created_at", { ascending: true });
    for (const c of comments || []) {
      const row = c as CardCommentRow & { card_id: string };
      const arr = commentsByCard.get(row.card_id) || [];
      arr.push(row);
      commentsByCard.set(row.card_id, arr);
    }
  }

  const board = await queryLaneBoard(lane);

  return (
    <Shell active={active}>
      <h1>{title}</h1>
      <p className="sub">
        {subtitle ||
          "メール／メモから処置候補を要約 → スキップ or Notion 看板へ。以降のステータスは Notion で管理。"}{" "}
        アーカイブは{" "}
        <Link href="/archive" style={{ color: "var(--accent)", fontWeight: 600 }}>
          こちら
        </Link>
        。
      </p>

      {children}

      <div className="stats">
        <div className="stat">
          処置候補 <strong>{activeCards.length}</strong>
        </div>
        <div className="stat">
          Notion進行中 <strong>{promotedCards.length}</strong>
        </div>
        <div className="stat">
          スキップ済{" "}
          <strong>
            <Link href="/archive" style={{ color: "inherit" }}>
              {archivedCount}
            </Link>
          </strong>
        </div>
      </div>

      <h2>処置候補</h2>
      {!activeCards.length ? (
        <p className="empty">
          まだありません（`jarvis_dashboard_lanes.py --push` で要約生成）
        </p>
      ) : (
        activeCards.map((c) => (
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
            <CardTriageActions
              card={c}
              lane={lane}
              path={active}
              comments={commentsByCard.get(c.id) || []}
            />
          </article>
        ))
      )}

      {promotedCards.length > 0 ? (
        <>
          <h2>進行中（Notion管理）</h2>
          {promotedCards.map((c) => (
            <article key={c.id} className="card" style={{ opacity: 0.92 }}>
              <header>
                <span className="lvl">promoted</span>
                <strong>{c.title}</strong>
              </header>
              <p className="sum">{c.summary}</p>
              <CardTriageActions
                card={c}
                lane={lane}
                path={active}
                comments={commentsByCard.get(c.id) || []}
              />
            </article>
          ))}
        </>
      ) : null}

      <BoardSection board={board} />
    </Shell>
  );
}
