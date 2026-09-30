import TriageKanbanLane from "@/components/TriageKanbanLane";

export default async function Page() {
  return (
    <TriageKanbanLane
      lane="kanji"
      title="飲み会幹事"
      active="/kanji"
      subtitle="種村マニュアル・振り返り比較ログを土台に、申請→当日→レポート→次回を Notion Kanban で回す。資料リンクから OneDrive／Drive を開いて会話できる。"
    />
  );
}
