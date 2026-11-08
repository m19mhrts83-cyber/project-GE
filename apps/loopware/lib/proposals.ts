/** いろんなソースから Todoist へ提案するタスク候補（サンプル）。実データは /api/misses 等から差し替える。 */
export type Proposal = {
  id: string;
  source: string; // Slack / メール / Journal / やり取り …
  from: string; // 発言者・フォルダ
  snippet: string; // 元の発言・文面
  taskTitle: string; // Todoist に出すタスク案
  due?: string;
  project?: string;
  hypothesis?: string; // AIの推測（本人の理由と見た目で分ける）
};

export const SEED_PROPOSALS: Proposal[] = [
  {
    id: "p1",
    source: "Slack",
    from: "佐藤",
    snippet: "青葉社向けの見積書、来週火曜までにお願いできますか？",
    taskTitle: "青葉社向け見積書を送付する",
    due: "来週火曜",
    project: "営業",
    hypothesis: "依頼＋期限あり。既存タスクと重複なし",
  },
  {
    id: "p2",
    source: "メール",
    from: "ミニテック",
    snippet: "先日の件、ご確認のほどお願いいたします。",
    taskTitle: "ミニテックへ返事をする",
    project: "営業",
    hypothesis: "返信待ちのサイン。期限は不明",
  },
  {
    id: "p3",
    source: "Journal",
    from: "Obsidian",
    snippet: "そろそろ保険の見直しをしたい",
    taskTitle: "保険の見直しを調べる",
    project: "暮らし",
    hypothesis: "やりたいことの独り言。いつやるかは未定",
  },
  {
    id: "p4",
    source: "やり取り",
    from: "P104_LEAF",
    snippet: "管理会社より、退去立会いの日程候補をいただきました。",
    taskTitle: "退去立会いの日程を返信する",
    due: "今週中",
    project: "不動産",
    hypothesis: "返信が要る。期限は文面から推測",
  },
  {
    id: "p5",
    source: "Slack",
    from: "田中",
    snippet: "採用説明会、資料どうなってますか？",
    taskTitle: "田中さんへ進捗を返信する",
    project: "採用",
    hypothesis: "既存「説明会資料を送付」と同じ件の可能性",
  },
];

export type Verdict = "take" | "skip" | "hold";

export const VERDICTS: {
  id: Verdict;
  label: string;
  desc: string;
  icon: "check" | "x" | "pause";
}[] = [
  { id: "take", label: "採る", desc: "Todoist に提案する", icon: "check" },
  { id: "skip", label: "見送る", desc: "今回は入れない", icon: "x" },
  { id: "hold", label: "保留", desc: "あとで決める", icon: "pause" },
];

/** 見送り・保留は理由を分けて持つ（「知っている」「今は不要」「誤り」を同じ×にしない） */
export const WHY_TAGS: Record<"skip" | "hold", string[]> = {
  skip: ["知っている", "今は不要", "誤り", "合わない", "重複"],
  hold: ["相手待ち", "情報不足", "時期を待つ", "判断材料が足りない"],
};
