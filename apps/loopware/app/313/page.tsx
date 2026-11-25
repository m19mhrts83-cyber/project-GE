import Link from "next/link";
import { Suspense } from "react";
import Icon from "@/components/Icon";
import CleanupClient from "@/components/CleanupClient";
import CleanupBulkClient from "@/components/CleanupBulkClient";
import CloseLeakClient from "@/components/CloseLeakClient";
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
          <CloseLeakClient />
        ) : (
          <CleanupClient initialTaskId={taskId} initialTab="cleanup" />
        )}
      </Suspense>
    </main>
  );
}
