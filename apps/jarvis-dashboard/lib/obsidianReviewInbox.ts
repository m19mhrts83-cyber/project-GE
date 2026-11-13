import { timingSafeEqual } from "crypto";
import type { SupabaseClient } from "@supabase/supabase-js";

export type DailyReview = {
  review_id: string;
  date: string;
  raw_log: string;
  tactical_review: string;
};

export type ReviewValidation = { ok: true; value: DailyReview } | { ok: false; error: string };

export function validateDailyReview(input: Record<string, unknown>): ReviewValidation {
  const reviewId = typeof input.review_id === "string" ? input.review_id.trim() : "";
  const reviewDate = typeof input.date === "string" ? input.date.trim() : "";
  const rawLog = typeof input.raw_log === "string" ? input.raw_log : "";
  const tactical = typeof input.tactical_review === "string" ? input.tactical_review : "";
  if (!/^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(reviewId)) {
    return { ok: false, error: "review_id must be a UUID" };
  }
  const parsedDate = /^\d{4}-\d{2}-\d{2}$/.test(reviewDate) ? new Date(`${reviewDate}T00:00:00Z`) : null;
  if (!parsedDate || Number.isNaN(parsedDate.getTime()) || parsedDate.toISOString().slice(0, 10) !== reviewDate) {
    return { ok: false, error: "date must be YYYY-MM-DD" };
  }
  if (!rawLog.trim() || !tactical.trim() || rawLog.length > 180_000 || tactical.length > 60_000) {
    return { ok: false, error: "review content is empty or too long" };
  }
  return {
    ok: true,
    value: { review_id: reviewId, date: reviewDate, raw_log: rawLog, tactical_review: tactical },
  };
}

export function submitKeyMatches(supplied: string, envName = "OBSIDIAN_REVIEW_SUBMIT_KEY"): boolean {
  const expected = (process.env[envName] || "").trim();
  const otherKeys = [
    "OBSIDIAN_REVIEW_POLL_KEY",
    "OBSIDIAN_REVIEW_READ_KEY",
    "OBSIDIAN_VAULT_POLL_KEY",
    "OBSIDIAN_REVIEW_MONITOR_KEY",
  ];
  if (!expected || otherKeys.some((name) => expected === (process.env[name] || "").trim())) return false;
  const a = Buffer.from(expected);
  const b = Buffer.from(supplied.trim());
  return a.length === b.length && timingSafeEqual(a, b);
}

export async function enqueueDailyReview(
  supabase: SupabaseClient,
  review: DailyReview,
): Promise<{ accepted: boolean; duplicate: boolean }> {
  const { data, error } = await supabase
    .from("obsidian_review_inbox")
    .insert({
      review_id: review.review_id,
      review_date: review.date,
      raw_log: review.raw_log,
      tactical_review: review.tactical_review,
    })
    .select("review_id")
    .maybeSingle();
  if (error?.code === "23505") return { accepted: true, duplicate: true };
  if (error) throw new Error(error.code || "db_error");
  return { accepted: Boolean(data), duplicate: false };
}

/** Accept one monthly daily note, plus legacy two-file receipts during rollout. */
export function validSavedReviewPaths(reviewId: string, paths: unknown[]): boolean {
  if (paths.length === 1 && typeof paths[0] === "string") {
    const m = /^01_Journaling\/★Journal\/(\d{4}-\d{2})\/(\d{4}-\d{2}-\d{2})\.md$/.exec(paths[0]);
    if (!m || m[1] !== m[2].slice(0, 7)) return false;
    const date = new Date(`${m[2]}T00:00:00Z`);
    return !Number.isNaN(date.getTime()) && date.toISOString().slice(0, 10) === m[2];
  }
  if (paths.length !== 2 || paths.some((p) => typeof p !== "string")) return false;
  const suffix = reviewId.slice(0, 8);
  const first = paths[0] as string;
  const prefix = "01_Journaling/★Journal/日次レビュー/";
  const match = /^(\d{4}-\d{2}-\d{2})_/.exec(first.slice(prefix.length));
  if (!match) return false;
  const stem = `${prefix}${match[1]}_${suffix}`;
  return paths[0] === `${stem}_生ログ.md` && paths[1] === `${stem}_戦術レビュー.md`;
}
