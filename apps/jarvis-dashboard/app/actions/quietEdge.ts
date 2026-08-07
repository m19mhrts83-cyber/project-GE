"use server";

import { revalidatePath } from "next/cache";
import { createClient } from "@/lib/supabase/server";
import { geminiVisionJson } from "@/lib/geminiReply";

export type SnoreEvent = "通常日" | "治療当日" | "治療直後";

export type SnoreDailyInput = {
  recorded_at: string;
  score: number;
  count?: number | null;
  event?: SnoreEvent | string;
  sleep_time?: string | null;
  memo?: string | null;
  source?: string;
  payload?: Record<string, unknown>;
};

export type QuietEdgeResult = { ok: true } | { ok: false; error: string };

export type ParsedSnoreShot = {
  screen: "score" | "count" | "unknown";
  recorded_at: string | null;
  score: number | null;
  count: number | null;
  sleep_time: string | null;
  count_vs_avg_delta: number | null;
  count_vs_avg_pct: number | null;
  raw_note: string | null;
};

export type ParseSnoreResult =
  | {
      ok: true;
      merged: SnoreDailyInput;
      parts: ParsedSnoreShot[];
    }
  | { ok: false; error: string };

const DATE_RE = /^\d{4}-\d{2}-\d{2}$/;
const EVENTS = new Set(["通常日", "治療当日", "治療直後"]);

function normalizeDate(raw: string | null | undefined): string | null {
  if (!raw) return null;
  const s = String(raw).trim();
  if (DATE_RE.test(s)) return s;
  const m = s.match(/(\d{4})[\/\-年](\d{1,2})[\/\-月](\d{1,2})/);
  if (m) {
    return `${m[1]}-${m[2].padStart(2, "0")}-${m[3].padStart(2, "0")}`;
  }
  const m2 = s.match(/(\d{1,2})月\s*(\d{1,2})日/);
  if (m2) {
    const y = new Date().getFullYear();
    return `${y}-${m2[1].padStart(2, "0")}-${m2[2].padStart(2, "0")}`;
  }
  return null;
}

function revalidateQuietEdge() {
  revalidatePath("/quiet-edge");
}

export async function upsertSnoreDaily(
  input: SnoreDailyInput,
): Promise<QuietEdgeResult> {
  const recorded_at = normalizeDate(input.recorded_at);
  if (!recorded_at) return { ok: false, error: "日付が不正です" };
  const score = Number(input.score);
  if (!Number.isFinite(score)) return { ok: false, error: "スコアが不正です" };

  const event = EVENTS.has(String(input.event))
    ? String(input.event)
    : "通常日";
  const count =
    input.count == null || input.count === ("" as unknown)
      ? null
      : Number(input.count);
  if (count != null && !Number.isFinite(count)) {
    return { ok: false, error: "回数が不正です" };
  }

  const supabase = await createClient();
  const { data: existing } = await supabase
    .from("vital_snore_daily")
    .select("count,sleep_time,memo,payload,score")
    .eq("recorded_at", recorded_at)
    .maybeSingle();

  const prevPayload =
    existing?.payload && typeof existing.payload === "object"
      ? (existing.payload as Record<string, unknown>)
      : {};
  const payload = { ...prevPayload, ...(input.payload || {}) };

  const row = {
    recorded_at,
    score,
    count: count ?? existing?.count ?? null,
    event,
    sleep_time:
      (input.sleep_time && String(input.sleep_time).trim()) ||
      existing?.sleep_time ||
      null,
    memo:
      input.memo != null
        ? String(input.memo)
        : (existing?.memo as string | null) || null,
    source: input.source || "manual",
    payload,
    updated_at: new Date().toISOString(),
  };

  const { error } = await supabase
    .from("vital_snore_daily")
    .upsert(row, { onConflict: "recorded_at" });
  if (error) return { ok: false, error: error.message };

  revalidateQuietEdge();
  return { ok: true };
}

export async function deleteSnoreDaily(
  recordedAt: string,
): Promise<QuietEdgeResult> {
  const recorded_at = normalizeDate(recordedAt);
  if (!recorded_at) return { ok: false, error: "日付が不正です" };
  const supabase = await createClient();
  const { error } = await supabase
    .from("vital_snore_daily")
    .delete()
    .eq("recorded_at", recorded_at);
  if (error) return { ok: false, error: error.message };
  revalidateQuietEdge();
  return { ok: true };
}

export async function importSnoreRecords(
  records: SnoreDailyInput[],
): Promise<QuietEdgeResult & { imported?: number }> {
  if (!Array.isArray(records) || records.length === 0) {
    return { ok: false, error: "レコードが空です" };
  }
  let n = 0;
  for (const r of records) {
    const res = await upsertSnoreDaily({ ...r, source: r.source || "import" });
    if (!res.ok) return { ok: false, error: res.error };
    n += 1;
  }
  return { ok: true, imported: n };
}

const OCR_PROMPT = `あなたは AutoSnore（いびき計測アプリ）のスクリーンショット解析器です。
画像は次のいずれかです:
1) screen=score: 「イビガースコア」画面。大きな数値スコア(0-100)、日付（例: 8月7日）、睡眠時間帯（例: 22:45:29 - 6:02:19）
2) screen=count: 「検出」回数画面。円の中の大きな整数回数、「N月N日〜N月N日の間」「平均より±N回」「±N%」など

厳守:
- 診断や治療助言は書かない
- JSON のみ返す（解説文禁止）
- 記録日 recorded_at は起床側の暦日（回数画面が「木〜金」なら金の日付）を YYYY-MM-DD にする。年が無い場合は画像の文脈または 2026 年を仮定
- sleep_time は "HH:MM - HH:MM" 形式に正規化（秒は落とす）

出力スキーマ:
{
  "screen": "score" | "count" | "unknown",
  "recorded_at": "YYYY-MM-DD" | null,
  "score": number | null,
  "count": number | null,
  "sleep_time": string | null,
  "count_vs_avg_delta": number | null,
  "count_vs_avg_pct": number | null,
  "raw_note": string | null
}`;

function asNum(v: unknown): number | null {
  if (v == null || v === "") return null;
  const n = typeof v === "number" ? v : Number(String(v).replace(/,/g, ""));
  return Number.isFinite(n) ? n : null;
}

function parseShot(obj: Record<string, unknown>): ParsedSnoreShot {
  const screenRaw = String(obj.screen || "unknown");
  const screen =
    screenRaw === "score" || screenRaw === "count" ? screenRaw : "unknown";
  return {
    screen,
    recorded_at: normalizeDate(
      obj.recorded_at != null ? String(obj.recorded_at) : null,
    ),
    score: asNum(obj.score),
    count: asNum(obj.count),
    sleep_time: obj.sleep_time != null ? String(obj.sleep_time) : null,
    count_vs_avg_delta: asNum(obj.count_vs_avg_delta),
    count_vs_avg_pct: asNum(obj.count_vs_avg_pct),
    raw_note: obj.raw_note != null ? String(obj.raw_note) : null,
  };
}

export async function parseSnoreScreenshots(
  formData: FormData,
): Promise<ParseSnoreResult> {
  const files = formData.getAll("images").filter((f): f is File => f instanceof File);
  if (files.length === 0) {
    return { ok: false, error: "画像がありません" };
  }
  const toProcess = files.slice(0, 2);
  const parts: ParsedSnoreShot[] = [];

  for (const file of toProcess) {
    const buf = Buffer.from(await file.arrayBuffer());
    const mime = file.type || "image/jpeg";
    const b64 = buf.toString("base64");
    const vision = await geminiVisionJson(
      [{ mimeType: mime, base64: b64 }],
      OCR_PROMPT,
    );
    if (!vision.ok) return { ok: false, error: vision.error };
    parts.push(parseShot(vision.json));
  }

  let recorded_at: string | null = null;
  let score: number | null = null;
  let count: number | null = null;
  let sleep_time: string | null = null;
  const payload: Record<string, unknown> = {};
  const notes: string[] = [];

  for (const p of parts) {
    if (p.recorded_at) recorded_at = p.recorded_at;
    if (p.score != null) score = p.score;
    if (p.count != null) count = p.count;
    if (p.sleep_time) sleep_time = p.sleep_time;
    if (p.count_vs_avg_delta != null) {
      payload.count_vs_avg_delta = p.count_vs_avg_delta;
    }
    if (p.count_vs_avg_pct != null) {
      payload.count_vs_avg_pct = p.count_vs_avg_pct;
    }
    if (p.raw_note) notes.push(p.raw_note);
  }

  if (score == null) {
    return {
      ok: false,
      error:
        "イビガースコアを読み取れませんでした。スコア画面のスクショを含めてください。",
    };
  }
  if (!recorded_at) {
    return { ok: false, error: "日付を読み取れませんでした" };
  }

  return {
    ok: true,
    parts,
    merged: {
      recorded_at,
      score,
      count,
      event: "通常日",
      sleep_time,
      memo: notes.length ? `AI読取: ${notes.join(" / ")}` : "",
      source: "autosnore_ocr",
      payload,
    },
  };
}
