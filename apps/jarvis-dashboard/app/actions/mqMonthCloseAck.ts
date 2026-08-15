"use server";

import { createClient } from "@/lib/supabase/server";
import { revalidatePath } from "next/cache";
import { parseMqMonthCloseAck } from "@/lib/mqMonthCloseNotice";

const META_KEY = "mq_month_close";

function parseValue(raw: unknown): Record<string, unknown> {
  if (raw == null) return {};
  if (typeof raw === "object") return raw as Record<string, unknown>;
  if (typeof raw === "string") {
    try {
      const p = JSON.parse(raw);
      return p && typeof p === "object" ? (p as Record<string, unknown>) : {};
    } catch {
      return {};
    }
  }
  return {};
}

export async function ackMqMonthClose(month: string): Promise<{ ok: boolean; error?: string }> {
  if (!/^\d{4}-\d{2}$/.test(month)) {
    return { ok: false, error: "month invalid" };
  }
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();
  if (!user) return { ok: false, error: "unauthorized" };

  const { data: existing } = await supabase
    .from("sync_meta")
    .select("value")
    .eq("key", META_KEY)
    .maybeSingle();

  const prev = parseValue(existing?.value);
  const acked = {
    ...parseMqMonthCloseAck(prev),
    [month]: new Date().toISOString(),
  };
  const value = { ...prev, acked, updated_at: new Date().toISOString() };

  const { error } = await supabase.from("sync_meta").upsert(
    {
      key: META_KEY,
      value: JSON.stringify(value),
      updated_at: new Date().toISOString(),
    },
    { onConflict: "key" }
  );
  if (error) return { ok: false, error: error.message };
  revalidatePath("/");
  return { ok: true };
}
