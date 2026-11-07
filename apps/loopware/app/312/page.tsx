import Link from "next/link";
import { Suspense } from "react";
import TaskDedupeClient from "@/components/TaskDedupeClient";
import MissesClient from "@/components/MissesClient";

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
      <nav className="nav">
        <Link href="/">ハブ</Link>
        <span>／</span>
        <strong>312</strong>
        <span>／</span>
        <Link href="/313">313</Link>
      </nav>
      <h1>312 入口・何を拾うか</h1>
      <p className="sub">
        S05: 3案から選ぶ・直して使う・どれも違う＋一言。多ソース材料。
      </p>
      <div className="tabs">
        <Link
          className={`tab ${tab === "handle" ? "active" : ""}`}
          href="/312"
        >
          扱いを決める
        </Link>
        <Link
          className={`tab ${tab === "misses" ? "active" : ""}`}
          href="/312?tab=misses"
        >
          漏れ確認
        </Link>
      </div>
      <Suspense fallback={<p className="meta">読み込み中…</p>}>
        {tab === "misses" ? (
          <MissesClient />
        ) : (
          <TaskDedupeClient initialTopicId={topicId} />
        )}
      </Suspense>
    </main>
  );
}
