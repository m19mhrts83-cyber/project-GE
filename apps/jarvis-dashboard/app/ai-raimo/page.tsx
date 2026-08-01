import TriageKanbanLane from "@/components/TriageKanbanLane";

export default async function Page() {
  return (
    <TriageKanbanLane
      lane="ai_raimo"
      title="AI・Raimo"
      active="/ai-raimo"
      subtitle="処置候補 → Notion「Cursorタスク」看板へ。Cursor に依頼する流れ。"
    />
  );
}
