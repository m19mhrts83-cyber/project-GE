import Link from "next/link";
import { Suspense } from "react";
import Icon from "@/components/Icon";
import TaskDedupeClient from "@/components/TaskDedupeClient";
import ProposeClient from "@/components/ProposeClient";

export default async function Page312({
  searchParams,
}: {
  searchParams?: Promise<{ topic?: string; tab?: string }>;
}) {
  const sp = (await searchParams) || {};
  const topicId = sp.topic || "";
  const tab = sp.tab === "misses" ? "misses" : "handle";

  return (
    <main>
      <div className="top">
        <Link className="back" href="/" aria-label="ハブへ戻る">
          <Icon name="back" size={22} />
        </Link>
        <div className="grow">
          <div className="eyebrow acc">312 ／ 入口</div>
          <h1>何を拾うか</h1>
        </div>
      </div>
      <div className="seg" style={{ marginBottom: 14 }}>
        <Link className={tab === "handle" ? "active" : ""} href="/312">
          扱いを決める
        </Link>
        <Link
          className={tab === "misses" ? "active" : ""}
          href="/312?tab=misses"
        >
          提案を仕分ける
        </Link>
      </div>
      <Suspense fallback={<p className="meta">読み込み中…</p>}>
        {tab === "misses" ? (
          <ProposeClient />
        ) : (
          <TaskDedupeClient initialTopicId={topicId} />
        )}
      </Suspense>
    </main>
  );
}
