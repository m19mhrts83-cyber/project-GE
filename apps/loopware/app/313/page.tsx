import Link from "next/link";
import { Suspense } from "react";
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
      <nav className="nav">
        <Link href="/">ハブ</Link>
        <span>／</span>
        <Link href="/312">312</Link>
        <span>／</span>
        <strong>313</strong>
      </nav>
      <h1>313 出口・片付ける</h1>
      <p className="sub">
        Slack 3択が本線。ここでは直す・一覧・閉じ漏れ。やめる＝完了＋コメント。
      </p>
      <Suspense fallback={<p className="meta">読み込み中…</p>}>
        <CleanupClient
          initialTaskId={taskId}
          initialTab={tab === "misses" ? "misses" : "cleanup"}
        />
      </Suspense>
    </main>
  );
}
