import type { SupabaseClient } from "@supabase/supabase-js";
import { timingSafeEqual } from "crypto";

export function bearerMatches(request: Request, envName: string, distinctFrom: string[] = []): boolean {
  const supplied = (request.headers.get("authorization") || "").replace(/^Bearer\s+/i, "").trim();
  return secretMatches(supplied, envName, distinctFrom);
}

export function secretIsDistinct(envName: string, distinctFrom: string[]): boolean {
  const expected = (process.env[envName] || "").trim();
  return Boolean(expected) && !distinctFrom.some((other) => expected === (process.env[other] || "").trim());
}

export function secretMatches(suppliedValue: string | null, envName: string, distinctFrom: string[] = []): boolean {
  const expected = (process.env[envName] || "").trim();
  const supplied = (suppliedValue || "").trim();
  if (!secretIsDistinct(envName, distinctFrom)) return false;
  const a = Buffer.from(expected);
  const b = Buffer.from(supplied);
  return a.length === b.length && timingSafeEqual(a, b);
}

export async function recordMacPoll(supabase: SupabaseClient): Promise<string | null> {
  const now = new Date().toISOString();
  const { error } = await supabase
    .from("obsidian_review_agent_status")
    .upsert({ agent_id: "mac", last_poll_at: now, updated_at: now }, { onConflict: "agent_id" });
  return error?.code || null;
}

export function isAllowedVaultPath(value: string): boolean {
  if (!value || value.length > 420 || value.startsWith("/") || value.includes("\\")) return false;
  const parts = value.split("/");
  if (parts.some((part) => !part || part === "." || part === ".." || part.startsWith("."))) return false;
  if (!value.endsWith(".md")) return false;
  return value.startsWith("01_Journaling/★Journal/") || value.startsWith("04_Permanent Note/");
}

export function validateReadRequest(input: Record<string, unknown>):
  | { ok: true; requestType: "search" | "excerpt"; payload: Record<string, string | number | null> }
  | { ok: false; error: string } {
  if (input.type === "search") {
    const query = typeof input.query === "string" ? input.query.trim() : "";
    if (query.length > 200) return { ok: false, error: "query must be at most 200 characters" };
    const exactDate = input.date == null ? null : String(input.date);
    const fromDate = exactDate || (input.from_date == null ? null : String(input.from_date));
    const toDate = exactDate || (input.to_date == null ? null : String(input.to_date));
    const days = input.days == null ? null : Number(input.days);
    const validDate = (v: string | null) => {
      if (v === null) return true;
      if (!/^\d{4}-\d{2}-\d{2}$/.test(v)) return false;
      const parsed = new Date(`${v}T00:00:00Z`);
      return !Number.isNaN(parsed.getTime()) && parsed.toISOString().slice(0, 10) === v;
    };
    if (!validDate(fromDate) || !validDate(toDate)) return { ok: false, error: "dates must use YYYY-MM-DD" };
    if (exactDate && (!validDate(exactDate) || input.from_date != null || input.to_date != null)) {
      return { ok: false, error: "date cannot be combined with from_date/to_date" };
    }
    if (days !== null && ![7, 30].includes(days)) return { ok: false, error: "days must be 7 or 30" };
    if (days !== null && (exactDate || input.from_date != null || input.to_date != null)) {
      return { ok: false, error: "days cannot be combined with date ranges" };
    }
    if (!query && !fromDate && !toDate && days === null) return { ok: false, error: "provide a query or date range" };
    const limit = input.limit == null ? 6 : Number(input.limit);
    if (!Number.isInteger(limit) || limit < 1 || limit > 10) return { ok: false, error: "limit must be 1-10" };
    return {
      ok: true,
      requestType: "search",
      payload: { query, from_date: fromDate, to_date: toDate, days, limit },
    };
  }
  if (input.type === "excerpt") {
    const sourcePath = typeof input.source_path === "string" ? input.source_path : "";
    const heading = input.heading == null ? null : String(input.heading).trim();
    if (!isAllowedVaultPath(sourcePath)) return { ok: false, error: "source_path is outside the read allowlist" };
    if (heading && (heading.length > 160 || /[\r\n]/.test(heading))) return { ok: false, error: "invalid heading" };
    return { ok: true, requestType: "excerpt", payload: { source_path: sourcePath, heading } };
  }
  return { ok: false, error: "type must be search or excerpt" };
}
