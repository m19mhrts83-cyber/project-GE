/** グルコン報告の共有型 */

export type GluconScheduleSource = "scraped" | "estimated" | "manual";

export type GluconScheduleRow = {
  glucon_date: string;
  report_deadline: string;
  title: string;
  source: GluconScheduleSource;
  comment_id?: string | null;
};

export type GluconReportKind = "activity" | "result";

export type GluconMemberHeaderStatus = {
  ok: boolean;
  missing: string[];
  preview: string;
};

export type ScoringSuggestion = {
  ruleId: string;
  mid: string;
  level: number;
  viewpoint: string;
  points: number;
  matchedKeywords: string[];
};

export type ResultScoringHints = {
  suggestions: ScoringSuggestion[];
  gaps: string[];
  disclaimer: string;
};

/** 投稿キュー投入時に payload へ残す目安点スナップ */
export type GluconScoringSnapshot = {
  estimated_points: number;
  suggestions: ScoringSuggestion[];
};

export type GluconDraftStatus =
  | "draft"
  | "ready"
  | "queued"
  | "posted"
  | "failed"
  | "skipped";

export type GluconCarryKindHint = "result" | "activity" | "either";

export type GluconCarryMemoStatus = "open" | "used" | "discarded";

/** 次月報告に回すメモ（下書き周期とは独立） */
export type GluconCarryMemo = {
  id: string;
  title: string;
  body: string;
  kind_hint: GluconCarryKindHint;
  status: GluconCarryMemoStatus;
  parked_period_key: string;
  available_from_period_key: string;
  used_in_period_key: string | null;
  created_at: string;
  updated_at: string;
};

export type GluconExample = {
  comment_id: string;
  author_name: string;
  posted_at: string | null;
  excerpt: string;
};

/** 成果報告フローのフェーズ */
export type GluconResultPhase = "facts" | "clarify" | "final";

export type GluconFactItem = {
  id: string;
  text: string;
  source: string;
  /** scoring_seed 中分類など（空室・修繕・融資…） */
  resultCandidateTag?: string | null;
  /** 成果報告側に載せる候補か */
  forResult?: boolean;
};

export type GluconClarifyItem = {
  id: string;
  question: string;
  answer: string;
};

export type GluconConsultTurn = {
  at: string;
  mode: "ask" | "revise";
  prompt: string;
  reply: string;
  revisedBody?: string | null;
};

export type GluconDraftPayload = {
  phase?: GluconResultPhase;
  facts?: GluconFactItem[];
  factsBody?: string;
  clarify?: GluconClarifyItem[];
  consult?: GluconConsultTurn[];
  /** 活動報告から除外する成果候補テキスト */
  resultCandidates?: string[];
  /** 成果報告の対象期間（前回報告以降〜今回） */
  covered_from?: string;
  covered_to?: string;
  /** 成果の神大家ポイント目安（投稿時スナップ。無ければ本文から再計算） */
  scoring?: GluconScoringSnapshot;
};

/** 前回投稿した成果報告のカバレッジ */
export type GluconLastResultCoverage = {
  covered_from: string | null;
  covered_to: string | null;
  posted_at: string | null;
  period_key: string | null;
};

/** 前回投稿した活動報告のカバレッジ（成果と同型 + 本文） */
export type GluconLastActivityCoverage = GluconLastResultCoverage & {
  body: string | null;
};

/** 次サイクルの目安（開催翌日以降にアクティブ） */
export type GluconNextCycleHint = {
  availableFrom: string;
  gluconDate: string;
  reportDeadline: string;
  periodKey: string;
};

export type GluconDraftRow = {
  id: string;
  period_key: string;
  kind: GluconReportKind;
  glucon_date: string | null;
  report_deadline: string | null;
  title: string;
  body: string;
  status: GluconDraftStatus;
  examples: GluconExample[];
  journal_day_count: number;
  post_error: string | null;
  posted_at: string | null;
  westudy_comment_id: string | null;
  payload: GluconDraftPayload;
  updated_at?: string;
};

export type GluconJournalDay = {
  recorded_at: string;
  excerpt: string;
  keywords: string[];
  char_count: number;
  synced_at?: string;
};

/** 画面プレビュー用の月次集約（やり取り・metrics・入退去） */
export type EarlyFillHint = {
  property_name: string;
  room: string;
  vacant_on: string;
  occupied_on: string;
  days: number;
  early: boolean;
};

export type GluconMonthlyDigestPreview = {
  from: string;
  to: string;
  yoritooriText: string;
  yoritooriCount: number;
  yoritooriOk: boolean;
  metricsText: string;
  metricsCount: number;
  occupancyText: string;
  occupancyCount: number;
  earlyFills: EarlyFillHint[];
  notices: string[];
};

export type GluconActiveCycle = {
  gluconDate: string;
  reportDeadline: string;
  periodKey: string;
  title: string;
  source: GluconScheduleSource;
  prevDeadline: string | null;
  journalFrom: string;
  journalTo: string;
  daysUntilDeadline: number;
  estimated: boolean;
};

export const WESTUDY_FORUM_URLS = {
  activity: "https://westudy.co.jp/forum/monthly_output",
  result: "https://westudy.co.jp/forum/results",
} as const;
