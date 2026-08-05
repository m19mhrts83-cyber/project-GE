import Link from "next/link";
import Shell from "@/components/Shell";
import CardSummaryBody from "@/components/CardSummaryBody";
import CardTriageActions, {
  type CardCommentRow,
} from "@/components/CardTriageActions";
import NotionBoardClient from "@/components/NotionBoardClient";
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

function BoardSection({
  board,
  lane,
  path,
}: {
  board: NotionBoardSummary;
  lane: string;
  path: string;
}) {
  const statusOrder =
    board.columnOrder?.length > 0
      ? board.columnOrder
      : Object.keys(board.byStatus || {});

  return (
    <section className="home-section notion-kanban-section">
      <div className="notion-board-head">
        <h2 style={{ margin: 0 }}>Kanban</h2>
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
        枠内で縦・横スクロールします（ページ全体を伸ばしません）。タスク名で
        Notion を開き、列の「移動」でステータスを変えられます。
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
            {statusOrder.map((k) => (
              <div className="stat" key={k}>
                {k} <strong>{board.byStatus[k] ?? 0}</strong>
              </div>
            ))}
          </div>
          <NotionBoardClient
            lane={lane}
            path={path}
            openStatuses={board.openStatuses || []}
            columnOrder={board.columnOrder || []}
            moveStatuses={board.moveStatuses || []}
            columns={board.columns || {}}
          />
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
  const hideSkipStat = lane === "properties";

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
          "ソースを要約した確認テーマです。コメントで方針を相談し、納得したら「タスク化する…」で内容確認のうえ Notion に1件登録。履歴は OneDrive「Jarvis処置ログ/{レーン}/5.処置ログ.md」。"}{" "}
        {hideSkipStat ? null : (
          <>
            アーカイブは{" "}
            <Link
              href="/archive"
              style={{ color: "var(--accent)", fontWeight: 600 }}
            >
              こちら
            </Link>
            。
          </>
        )}
      </p>

      <BoardSection board={board} lane={lane} path={active} />

      {children}

      <div className="stats">
        <div className="stat">
          確認テーマ <strong>{activeCards.length}</strong>
        </div>
        <div className="stat">
          Notion進行中 <strong>{promotedCards.length}</strong>
        </div>
        {hideSkipStat ? null : (
          <div className="stat">
            スキップ済{" "}
            <strong>
              <Link href="/archive" style={{ color: "inherit" }}>
                {archivedCount}
              </Link>
            </strong>
          </div>
        )}
      </div>

      <h2>確認テーマ</h2>
      {!activeCards.length ? (
        <p className="empty">
          まだありません（`jarvis_lane_digest.py --push` または
          `jarvis_dashboard_lanes.py --action-summary --push`）
        </p>
      ) : (
        activeCards.map((c) => (
          <article key={c.id} className="card digest-card">
            <header>
              <span className="lvl">確認</span>
              <strong>{c.title.replace(/^\[確認\]\s*/, "")}</strong>
            </header>
            <CardSummaryBody
              kind={c.kind}
              summary={c.summary}
              payload={c.payload}
            />
            {c.cursor_prompt ? (
              <details className="digest-cursor">
                <summary>Cursorで調べる</summary>
                <pre className="digest-cursor-pre">{c.cursor_prompt}</pre>
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
            <article
              key={c.id}
              className="card digest-card"
              style={{ opacity: 0.92 }}
            >
              <header>
                <span className="lvl">進行中</span>
                <strong>{c.title.replace(/^\[確認\]\s*/, "")}</strong>
              </header>
              <CardSummaryBody
                kind={c.kind === "digest" ? "digest" : c.kind}
                summary={c.summary}
                payload={c.payload}
              />
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
    </Shell>
  );
}
