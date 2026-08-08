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

export type GluconDraftStatus =
  | "draft"
  | "ready"
  | "queued"
  | "posted"
  | "failed"
  | "skipped";

export type GluconExample = {
  comment_id: string;
  author_name: string;
  posted_at: string | null;
  excerpt: string;
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
  updated_at?: string;
};

export type GluconJournalDay = {
  recorded_at: string;
  excerpt: string;
  keywords: string[];
  char_count: number;
  synced_at?: string;
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
