import TriageKanbanLane from "@/components/TriageKanbanLane";

export default async function Page() {
  return (
    <TriageKanbanLane
      lane="ai_raimo"
      title="AI・Raimo"
      active="/ai-raimo"
      subtitle="処置候補 → Todoist「業務まとめ」（ai_raimo）。本線は Todoist Board。ダッシュボードは参考投影。"
    />
  );
}
