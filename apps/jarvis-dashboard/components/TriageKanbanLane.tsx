import Link from "next/link";
import Shell from "@/components/Shell";
import CardTriageActions, {
  type CardCommentRow,
} from "@/components/CardTriageActions";
import {
  queryLaneBoard,
  type NotionBoardSummary,
  type NotionTask,
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

function BoardColumns({ columns }: { columns: Record<string, NotionTask[]> }) {
  const entries = Object.entries(columns);
  if (!entries.length) return null;
  return (
    <div className="notion-board">
      {entries.map(([status, tasks]) => (
        <div className="notion-col" key={status}>
          <div className="notion-col-head">
            {status}{" "}
            <span className="notion-col-count">{tasks.length}</span>
          </div>
          <ul className="notion-col-list">
            {tasks.length === 0 ? (
              <li className="notion-col-empty">—</li>
            ) : (
              tasks.map((t) => (
                <li key={t.id} className={t.overdue ? "overdue" : undefined}>
                  <a href={t.url} target="_blank" rel="noreferrer">
                    {t.title}
                  </a>
                  {t.due ? (
                    <span className="notion-col-due">
                      {t.overdue ? "期限切れ " : ""}
                      {t.due}
                    </span>
                  ) : null}
                </li>
              ))
            )}
          </ul>
        </div>
      ))}
    </div>
  );
}

function BoardSection({ board }: { board: NotionBoardSummary }) {
  return (
    <section className="home-section" style={{ marginTop: 28 }}>
      <div className="notion-board-head">
        <h2 style={{ margin: 0 }}>Notion 看板</h2>
        {board.boardUrl ? (
          <a
            href={board.boardUrl}
            target="_blank"
            rel="noreferrer"
            className="btn primary"
          >
            Notion で開く ↗
          </a>
        ) : null}
      </div>
      <p className="sub" style={{ marginTop: 8 }}>
        タスク名をクリックすると Notion の該当ページへ。プライベート DB
        は iframe 埋め込み不可のため、API で看板を再現しています（編集・ドラッグは
        Notion 側）。
      </p>
      {!board.connected ? (
        <p className="empty">
          未接続
          {board.reason ? `（${board.reason}）` : ""}
          。`.env.jarvis_private` と Vercel に NOTION_API_TOKEN を設定し、対象 DB を
          Integration「Jarvisダッシュボード」に接続してください。
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
          <BoardColumns columns={board.columns || {}} />
          {board.overdue.length > 0 ? (
            <>
              <h3 style={{ fontSize: "1rem", marginTop: 16 }}>期限切れ</h3>
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
      <div className="page-title-row">
        <h1 style={{ margin: 0 }}>{title}</h1>
        {board.boardUrl ? (
          <a
            href={board.boardUrl}
            target="_blank"
            rel="noreferrer"
            className="btn"
          >
            Notion ↗
          </a>
        ) : null}
      </div>
      <p className="sub">
        {subtitle ||
          "ソースを要約した確認テーマ → 見送り or Notion タスク化。コメント可。履歴は OneDrive「Jarvis処置ログ/{レーン}/5.処置ログ.md」。"}{" "}
        アーカイブは{" "}
        <Link href="/archive" style={{ color: "var(--accent)", fontWeight: 600 }}>
          こちら
        </Link>
        。
      </p>

      {children}

      <div className="stats">
        <div className="stat">
          確認テーマ <strong>{activeCards.length}</strong>
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

      <h2>確認テーマ</h2>
      {!activeCards.length ? (
        <p className="empty">
          まだありません（`jarvis_lane_digest.py --push` で要約生成）
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
