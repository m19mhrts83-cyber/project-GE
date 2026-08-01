import TriageKanbanLane from "@/components/TriageKanbanLane";

export default async function Page() {
  return (
    <TriageKanbanLane
      lane="kodate"
      title="戸建て"
      active="/kodate"
      subtitle="新規購入の処置候補 → Notion「戸建て購入タスク」看板へ。"
    />
  );
}
