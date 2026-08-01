import TriageKanbanLane from "@/components/TriageKanbanLane";

export default async function Page() {
  return (
    <TriageKanbanLane
      lane="kazoku"
      title="家族"
      active="/kazoku"
      subtitle="家族の用事・予定 → Notion「家族タスク」看板へ。"
    />
  );
}
