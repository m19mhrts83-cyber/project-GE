"use server";

import { createClient } from "@/lib/supabase/server";
import { parseMemoLog, type UnitMemoEntry } from "@/lib/occupancy";
import { revalidatePath } from "next/cache";

export type AppendUnitMemoResult =
  | { ok: true; note: string }
  | { ok: false; error: string };

function nowIsoJst(): string {
  return new Date().toISOString();
}

export async function appendPropertyUnitMemo(input: {
  unitId: string;
  text: string;
  source?: "ui" | "jarvis";
}): Promise<AppendUnitMemoResult> {
  const unitId = String(input.unitId || "").trim();
  const text = String(input.text || "").trim();
  if (!unitId) return { ok: false, error: "号室IDがありません" };
  if (!text) return { ok: false, error: "メモが空です" };
  if (text.length > 800) return { ok: false, error: "メモは800文字以内にしてください" };

  const supabase = await createClient();
  const { data: row, error } = await supabase
    .from("property_units")
    .select("id,note,payload")
    .eq("id", unitId)
    .maybeSingle();
  if (error) return { ok: false, error: error.message };
  if (!row) return { ok: false, error: "号室が見つかりません" };

  const payload =
    row.payload && typeof row.payload === "object" && !Array.isArray(row.payload)
      ? { ...(row.payload as Record<string, unknown>) }
      : {};
  const log = parseMemoLog(payload.memo_log);
  const entry: UnitMemoEntry = {
    at: nowIsoJst(),
    text: text.slice(0, 400),
    source: input.source === "jarvis" ? "jarvis" : "ui",
  };
  const nextLog = [...log, entry].slice(-80);
  payload.memo_log = nextLog;
  const note = text.slice(0, 500);

  const { error: upErr } = await supabase
    .from("property_units")
    .update({
      note,
      payload,
      updated_at: nowIsoJst(),
    })
    .eq("id", unitId);
  if (upErr) return { ok: false, error: upErr.message };

  revalidatePath("/properties");
  revalidatePath("/");
  return { ok: true, note };
}
