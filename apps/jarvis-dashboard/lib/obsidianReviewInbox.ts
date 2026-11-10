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
  const a = Buffer.from(expected);
  const b = Buffer.from(supplied.trim());
  return a.length > 0 && a.length === b.length && timingSafeEqual(a, b);
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
