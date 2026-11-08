import Link from "next/link";
import { Suspense } from "react";
import Icon from "@/components/Icon";
import CleanupClient from "@/components/CleanupClient";

export default async function Page313({
  searchParams,
}: {
  searchParams?: Promise<{ task?: string; tab?: string }>;
}) {
  const sp = (await searchParams) || {};
  const taskId = sp.task || "";
  const tab = sp.tab === "misses" ? "misses" : "cleanup";

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
      <Suspense fallback={<p className="meta">読み込み中…</p>}>
        <CleanupClient
          initialTaskId={taskId}
          initialTab={tab === "misses" ? "misses" : "cleanup"}
        />
      </Suspense>
    </main>
  );
}
