import TriageKanbanLane from "@/components/TriageKanbanLane";
import Link from "next/link";

export default async function Page() {
  return (
    <TriageKanbanLane
      lane="kamiooya"
      title="神大家運営"
      active="/kamiooya"
      subtitle="やり取り／Journal からの処置候補 → Notion「神大家運営タスク」Kanban へ。"
    >
      <section className="home-section">
        <h2>作業項目と履歴</h2>
        <p>事前に決めた作業項目、項目ごとの実行結果、質問と回答、作業時間を確認できます。</p>
        <Link href="/kamiooya/history" className="btn">作業履歴を見る →</Link>
      </section>
    </TriageKanbanLane>
  );
}
