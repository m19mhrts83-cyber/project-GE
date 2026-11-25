import Link from "next/link";
import { Suspense } from "react";
import Icon from "@/components/Icon";
import CleanupClient from "@/components/CleanupClient";
import CleanupBulkClient from "@/components/CleanupBulkClient";
import SegTabs from "@/components/SegTabs";

export default async function Page313({
  searchParams,
}: {
  searchParams?: Promise<{ task?: string; tab?: string }>;
}) {
  const sp = (await searchParams) || {};
  const taskId = sp.task || "";
  // 基本は「まとめて片付ける」。Slack の「アプリで開く」（task つき）は1件ずつへ
  const tab = sp.tab === "misses" ? "misses" : sp.tab === "cleanup" || taskId ? "cleanup" : "bulk";

  return (
    <main>
      <div className="top">
        <Link className="back" href="/" aria-label="ハブへ戻る">
          <Icon name="back" size={22} />
        </Link>
        <div className="grow">
          <div className="eyebrow acc">313 ／ 出口</div>
          <h1>片付ける</h1>
        </div>
      </div>
      <SegTabs
        tabs={[
          { href: "/313", label: "まとめて", key: "cleanup", active: tab === "bulk" },
          { href: "/313?tab=misses", label: "閉じ漏れ", key: "closeLeak", active: tab === "misses" },
          { href: "/313?tab=cleanup", label: "1件ずつ", key: null, active: tab === "cleanup" },
        ]}
      />
      <Suspense fallback={<p className="meta">読み込み中…</p>}>
        {tab === "bulk" ? (
          <CleanupBulkClient />
        ) : tab === "misses" ? (
          <div className="glass wk-empty">
            <b>閉じ漏れの検知結果は、まだこの画面に届いていません</b>
            <span className="meta">
              台帳で送信済み・PRマージ済み・「これ済んだ」と判断できたものを、Todoist に残っているタスクと照らして出す機能です。
              検知スクリプト（scripts/jarvis_todoist_313_done_elsewhere.py）はあり、結果をこの画面へ流す接続が未完了です。
              件数バッジが「—」でなく出るようになったら、ここに並びます。
            </span>
          </div>
        ) : (
          <CleanupClient initialTaskId={taskId} initialTab="cleanup" />
        )}
      </Suspense>
    </main>
  );
}
