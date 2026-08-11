"use server";

import { revalidatePath } from "next/cache";
import { createClient } from "@/lib/supabase/server";

/**
 * 静かな失敗向けの既知レシピを Mac Worker キューに載せる。
 * CHRLINE 自体はここでは実行しない（Worker が pause→init→backfill）。
 */
export async function queueOpenchatMacRecover(opts: {
  routeIds: string[];
}): Promise<{ ok: boolean; error?: string; message?: string }> {
  const routeIds = (opts.routeIds || [])
    .map((x) => String(x || "").trim())
    .filter(Boolean);
  if (!routeIds.length) {
    return { ok: false, error: "route_ids が空です" };
  }

  const supabase = await createClient();
  const { data: row, error } = await supabase
    .from("watch_status")
    .select("id,payload")
    .eq("id", "openchat_threads")
    .maybeSingle();
  if (error) return { ok: false, error: error.message };
  if (!row) return { ok: false, error: "openchat_threads ウォッチがありません" };

  const payload =
    row.payload && typeof row.payload === "object"
      ? ({ ...(row.payload as Record<string, unknown>) } as Record<
          string,
          unknown
        >)
      : {};
  const remediation =
    payload.remediation && typeof payload.remediation === "object"
      ? ({ ...(payload.remediation as Record<string, unknown>) } as Record<
          string,
          unknown
        >)
      : {};
  const prev =
    remediation.mac_recipe && typeof remediation.mac_recipe === "object"
      ? (remediation.mac_recipe as Record<string, unknown>)
      : {};
  const st = String(prev.status || "");
  if (st === "queued" || st === "running") {
    return { ok: false, error: `すでに ${st} です。完了を待ってください` };
  }

  const mac_recipe = {
    id: "openchat_init_bootstrap",
    route_ids: routeIds,
    label: "静かな失敗の --init discover＋バックフィル",
    status: "queued",
    requested_at: new Date().toISOString(),
    error: null,
    result: null,
  };
  remediation.mac_recipe = mac_recipe;
  payload.remediation = remediation;
  payload.mac_recipe = mac_recipe;

  const { error: upErr } = await supabase
    .from("watch_status")
    .update({
      payload,
      updated_at: new Date().toISOString(),
    })
    .eq("id", "openchat_threads");
  if (upErr) return { ok: false, error: upErr.message };

  revalidatePath("/openchat");
  revalidatePath("/situation");
  revalidatePath("/");
  return {
    ok: true,
    message:
      "Mac 復旧キューに入れました（Mac の recover worker が起動後に実行します）",
  };
}
