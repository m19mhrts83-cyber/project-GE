import Shell from "@/components/Shell";
import { createClient } from "@/lib/supabase/server";
import {
  notionTokenConfigured,
  queryKurashiftNotionBoards,
} from "@/lib/notionTasks";

export const dynamic = "force-dynamic";

export default async function NotionTasksPage() {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();

  const connected = notionTokenConfigured();
  const boards = connected ? await queryKurashiftNotionBoards() : [];

  return (
    <Shell active="/notion" email={user?.email ?? null}>
      <h1>Notion タスク</h1>
      <p className="sub">
        Internal Integration（API）で家族・戸建て・所有物件の未完了を表示します。MCP
        は使いません。正本トークンは{" "}
        <code>.env.jarvis_private</code> の <code>NOTION_API_TOKEN</code>。
      </p>

      {!connected ? (
        <div className="card">
          <p className="empty">
            未接続（NOTION_API_TOKEN 未設定）。Vercel / ローカル .env.local
            へ同期してください。
          </p>
        </div>
      ) : (
        boards.map((board) => (
          <section className="card" key={board.lane} style={{ marginBottom: 16 }}>
            <header
              style={{
                display: "flex",
                justifyContent: "space-between",
                gap: 12,
                alignItems: "baseline",
              }}
            >
              <strong>{board.title}</strong>
              <a href={board.boardUrl} target="_blank" rel="noreferrer">
                Notion で開く ↗
              </a>
            </header>
            {!board.connected ? (
              <p className="empty">未接続（{board.reason}）</p>
            ) : board.open.length === 0 ? (
              <p className="meta">未完了タスクはありません</p>
            ) : (
              <ul style={{ margin: "8px 0 0", paddingLeft: 18 }}>
                {board.open.map((t) => (
                  <li key={t.id} style={{ marginBottom: 6 }}>
                    <a href={t.url} target="_blank" rel="noreferrer">
                      {t.title}
                    </a>
                    <span className="meta">
                      {" "}
                      · {t.status}
                      {t.due ? ` · ${t.due}` : ""}
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </section>
        ))
      )}
    </Shell>
  );
}
