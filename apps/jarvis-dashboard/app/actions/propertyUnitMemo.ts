"use server";

import { createClient } from "@/lib/supabase/server";
import { parseMemoLog, type UnitMemoEntry } from "@/lib/occupancy";
import { revalidatePath } from "next/cache";

export type AppendUnitMemoResult =
  | { ok: true; note: string }
  | { ok: false; error: string };

export type UpdateUnitTermsResult =
  | {
      ok: true;
      unit: {
        id: string;
        rent: number | null;
        status: string;
        note: string | null;
        payload: Record<string, unknown>;
      };
    }
  | { ok: false; error: string };

function nowIsoJst(): string {
  return new Date().toISOString();
}

function parseOptionalYen(raw: unknown): number | null | undefined {
  if (raw === undefined) return undefined;
  if (raw === null || raw === "") return null;
  if (typeof raw === "number") {
    return Number.isFinite(raw) ? raw : undefined;
  }
  const s = String(raw).replace(/,/g, "").trim();
  if (!s) return null;
  const n = Number(s);
  return Number.isFinite(n) ? n : undefined;
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
  if (text.length > 800)
    return { ok: false, error: "メモは800文字以内にしてください" };

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

/** 現状家賃・管理費・1年目/2年目などを手動修正（差の是正用） */
export async function updatePropertyUnitTerms(input: {
  unitId: string;
  rent?: number | string | null;
  management_fee?: number | string | null;
  rent_year1?: number | string | null;
  rent_year2?: number | string | null;
  campaign_until?: string | null;
  status?: "occupied" | "vacant" | null;
  reason?: string | null;
  source?: "ui" | "jarvis";
}): Promise<UpdateUnitTermsResult> {
  const unitId = String(input.unitId || "").trim();
  if (!unitId) return { ok: false, error: "号室IDがありません" };

  const rent = parseOptionalYen(input.rent);
  const mgmt = parseOptionalYen(input.management_fee);
  const y1 = parseOptionalYen(input.rent_year1);
  const y2 = parseOptionalYen(input.rent_year2);
  if (rent === undefined) return { ok: false, error: "現状家賃が不正です" };
  if (mgmt === undefined) return { ok: false, error: "管理費が不正です" };
  if (y1 === undefined) return { ok: false, error: "1年目家賃が不正です" };
  if (y2 === undefined) return { ok: false, error: "2年目家賃が不正です" };

  const status =
    input.status === "vacant" || input.status === "occupied"
      ? input.status
      : null;
  const campaignUntil =
    input.campaign_until != null
      ? String(input.campaign_until).trim().slice(0, 40)
      : null;
  const reason = String(input.reason || "").trim().slice(0, 200);
  const source = input.source === "jarvis" ? "jarvis" : "ui";

  const supabase = await createClient();
  const { data: row, error } = await supabase
    .from("property_units")
    .select("id,rent,status,note,payload")
    .eq("id", unitId)
    .maybeSingle();
  if (error) return { ok: false, error: error.message };
  if (!row) return { ok: false, error: "号室が見つかりません" };

  const payload =
    row.payload && typeof row.payload === "object" && !Array.isArray(row.payload)
      ? { ...(row.payload as Record<string, unknown>) }
      : {};

  const prevRent = row.rent != null ? Number(row.rent) : null;
  const prevMgmt =
    typeof payload.management_fee === "number"
      ? payload.management_fee
      : typeof payload.mgmt_fee === "number"
        ? payload.mgmt_fee
        : null;
  const prevY1 =
    typeof payload.rent_year1 === "number" ? payload.rent_year1 : null;
  const prevY2 =
    typeof payload.rent_year2 === "number" ? payload.rent_year2 : null;

  const nextRent = rent;
  const nextMgmt = mgmt;
  const nextY1 = y1;
  const nextY2 = y2;

  if (nextMgmt != null) {
    payload.management_fee = nextMgmt;
    payload.mgmt_fee = nextMgmt;
  } else {
    delete payload.management_fee;
    delete payload.mgmt_fee;
  }
  if (nextY1 != null) payload.rent_year1 = nextY1;
  else delete payload.rent_year1;
  if (nextY2 != null) payload.rent_year2 = nextY2;
  else delete payload.rent_year2;

  const totalCurrent =
    nextRent != null ? nextRent + (nextMgmt != null ? nextMgmt : 0) : null;
  const totalY1 =
    nextY1 != null ? nextY1 + (nextMgmt != null ? nextMgmt : 0) : null;
  const totalY2 =
    nextY2 != null ? nextY2 + (nextMgmt != null ? nextMgmt : 0) : null;
  if (totalCurrent != null) payload.total_rent = totalCurrent;
  if (totalY1 != null) payload.total_year1 = totalY1;
  else delete payload.total_year1;
  if (totalY2 != null) payload.total_year2 = totalY2;
  else delete payload.total_year2;

  if (nextY1 != null && nextY2 != null && nextY2 > nextY1) {
    const disc = nextY2 - nextY1;
    payload.discount_yen = disc;
    payload.discount_rate = Math.round((1000 * disc) / nextY2) / 10;
  } else if (totalY1 != null && totalY2 != null && totalY2 > totalY1) {
    const disc = totalY2 - totalY1;
    payload.discount_yen = disc;
    payload.discount_rate = Math.round((1000 * disc) / totalY2) / 10;
  }

  if (campaignUntil) payload.campaign_until = campaignUntil;
  else if (input.campaign_until === "") delete payload.campaign_until;

  const changes: string[] = [];
  const fmt = (n: number | null) =>
    n == null ? "—" : `${Math.round(n).toLocaleString("ja-JP")}`;
  if (prevRent !== nextRent)
    changes.push(`現状家賃 ${fmt(prevRent)}→${fmt(nextRent)}`);
  if (prevMgmt !== nextMgmt)
    changes.push(`管理費 ${fmt(prevMgmt)}→${fmt(nextMgmt)}`);
  if (prevY1 !== nextY1) changes.push(`1年目 ${fmt(prevY1)}→${fmt(nextY1)}`);
  if (prevY2 !== nextY2) changes.push(`2年目 ${fmt(prevY2)}→${fmt(nextY2)}`);
  if (status && status !== row.status) {
    changes.push(
      `状態 ${row.status === "vacant" ? "空室" : "入居"}→${
        status === "vacant" ? "空室" : "入居"
      }`,
    );
  }
  if (campaignUntil) changes.push(`期限 ${campaignUntil}`);

  const memoText = [
    "条件修正",
    changes.length ? changes.join(" / ") : "（値変更なし）",
    reason ? `理由: ${reason}` : "",
  ]
    .filter(Boolean)
    .join(" · ")
    .slice(0, 400);

  const log = parseMemoLog(payload.memo_log);
  log.push({ at: nowIsoJst(), text: memoText, source });
  payload.memo_log = log.slice(-80);

  const update: Record<string, unknown> = {
    rent: nextRent,
    note: memoText.slice(0, 500),
    payload,
    updated_at: nowIsoJst(),
    source: source === "jarvis" ? "jarvis" : "ui",
  };
  if (status) update.status = status;

  const { error: upErr } = await supabase
    .from("property_units")
    .update(update)
    .eq("id", unitId);
  if (upErr) return { ok: false, error: upErr.message };

  revalidatePath("/properties");
  revalidatePath("/");
  return {
    ok: true,
    unit: {
      id: unitId,
      rent: nextRent,
      status: status || row.status,
      note: memoText.slice(0, 500),
      payload,
    },
  };
}
