/**
 * いろんなソースから Todoist へ提案するタスク候補。
 * 設計書「依頼のタスク化」「完了条件つきタスク」の例をサンプルにしている（実データは /api/misses 等から差し替える）。
 * 担当者・期限・依頼された箇所は、原文に無ければ「記載なし」と出す（AIが補わない）。
 */
export type Proposal = {
  id: string;
  group: string; // 同じ原文から出た候補は同じ group
  source: string; // Slack / メール / 日誌 / やり取り …
  from: string; // 発言者・フォルダ
  sourceText: string; // 原文（group の最初のカードにだけ出す）
  taskTitle: string;
  doneWhen?: string; // 完了条件（ここまでできたら完了）
  requested?: string; // 依頼された箇所（原文の引用）
  related?: string; // 関連する原文
  assignee?: string;
  due?: string;
  status?: string; // 原文の作業状況（修正済み など）
  project?: string;
  hypothesis?: string; // AIの推測（本人の理由と見た目で分ける）
};

export const NONE = "記載なし";

export const SEED_PROPOSALS: Proposal[] = [
  {
    id: "p1a",
    group: "g1",
    source: "Slack",
    from: "11/9 佐伯",
    sourceText:
      "11/13までに見積表を確認してもらえますか。価格差の理由は営業に確認中です。打合せは私が設定します。",
    taskTitle: "見積表の内容を確認する",
    doneWhen: "共有された見積表を読み、確認が必要な箇所を整理したら完了",
    requested: "「見積表を確認してもらえますか」",
    assignee: "私（宛先）",
    due: "11/13",
    hypothesis: "依頼＋期限が明記されている",
  },
  {
    id: "p1b",
    group: "g1",
    source: "Slack",
    from: "11/9 佐伯",
    sourceText: "",
    taskTitle: "営業に見積表の価格差の理由を確認する",
    doneWhen: "営業への確認状況を確かめ、結果をメモに残したら完了",
    related: "「価格差の理由は営業に確認中です」",
    hypothesis: "営業が確認中。自分の作業かは不明",
  },
  {
    id: "p1c",
    group: "g1",
    source: "Slack",
    from: "11/9 佐伯",
    sourceText: "",
    taskTitle: "見積表の打合せを設定する",
    related: "「打合せは私が設定します」",
    assignee: "佐伯（原文の「私」）",
    hypothesis: "原文の「私」は発言者。他人の担当の可能性",
  },
  {
    id: "p2a",
    group: "g2",
    source: "メール",
    from: "11/10 森",
    sourceText:
      "説明資料の誤字確認を11/12までにお願いします。最新版は共有フォルダに置きました。顧客への送付日は次回相談させてください。",
    taskTitle: "説明資料の最新版の誤字を確認する",
    doneWhen: "共有フォルダの最新版を開き、誤字を確認したら完了",
    requested: "「説明資料の誤字確認を11/12までにお願いします」",
    assignee: "私（宛先）",
    due: "11/12",
  },
  {
    id: "p2b",
    group: "g2",
    source: "メール",
    from: "11/10 森",
    sourceText: "",
    taskTitle: "共有フォルダにある説明資料の最新版を確認する",
    related: "「最新版は共有フォルダに置きました」",
    hypothesis: "場所の共有だけ。独立した作業ではない可能性",
  },
  {
    id: "p3a",
    group: "g3",
    source: "日誌",
    from: "11/10 自分の記録",
    sourceText:
      "月次集計に30分かかった。自動化できるか調べたい。入力漏れは今日修正済み。来月の様式変更は田中さんが検討中。",
    taskTitle: "月次集計を自動化できるか調べる",
    doneWhen: "手順を確認し、自動化できそうな部分をメモに残したら完了",
    related: "「自動化できるか調べたい」",
    assignee: "自分（日誌の記入者）",
  },
  {
    id: "p3b",
    group: "g3",
    source: "日誌",
    from: "11/10 自分の記録",
    sourceText: "",
    taskTitle: "月次集計の入力漏れを修正する",
    related: "「入力漏れは今日修正済み」",
    assignee: "自分（日誌の記入者）",
    status: "修正済み",
    hypothesis: "完了済みの作業を再提案している可能性",
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
  { id: "hold", label: "保留", desc: "まだ判断できない", icon: "pause" },
];

/**
 * 見送り・保留の理由（任意）。「知っている」「今は不要」「誤り」を同じ×にしない。
 * 先頭の4つ／3つは設計書「依頼のタスク化」の決め手。
 */
export const WHY_TAGS: Record<"skip" | "hold", string[]> = {
  skip: [
    "自分の担当ではない",
    "共有だけ",
    "まだ依頼ではない",
    "対応不要",
    "知っている",
    "今は不要",
    "誤り",
    "重複",
  ],
  hold: ["担当確認待ち", "判断材料不足", "先に確認が必要", "相手待ち", "時期を待つ"],
};

/** 採るタスクを直したときの理由（設計書「完了条件つきタスク」）。任意。 */
export const EDIT_TAGS = ["範囲が広い", "終わりが曖昧", "先に確認が必要"];
