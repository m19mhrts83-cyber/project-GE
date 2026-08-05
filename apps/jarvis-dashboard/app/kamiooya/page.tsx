import TriageKanbanLane from "@/components/TriageKanbanLane";

export default async function Page() {
  return (
    <TriageKanbanLane
      lane="kamiooya"
      title="神大家運営"
      active="/kamiooya"
      subtitle="やり取り／Journal からの処置候補 → Notion「神大家運営タスク」Kanban へ。"
    />
  );
}
