"use server";

import { revalidatePath } from "next/cache";
import { createClient } from "@/lib/supabase/server";

export async function setCardStatus(
  id: string,
  next: "active" | "archived",
  path: string
) {
  const supabase = await createClient();
  const patch =
    next === "archived"
      ? { status: "archived", archived_at: new Date().toISOString() }
      : { status: "active", archived_at: null };
  const { error } = await supabase.from("cards").update(patch).eq("id", id);
  if (error) throw new Error(error.message);
  revalidatePath(path);
  revalidatePath("/archive");
  revalidatePath("/");
}

export async function setWatchStatus(
  id: string,
  next: "active" | "archived",
  path = "/situation"
) {
  const supabase = await createClient();
  if (next === "archived") {
    const { data } = await supabase
      .from("watch_status")
      .select("payload")
      .eq("id", id)
      .maybeSingle();
    const payload =
      data?.payload && typeof data.payload === "object"
        ? (data.payload as Record<string, unknown>)
        : {};
    if (payload.never_archive) {
      throw new Error("この項目は常駐のためアーカイブできません");
    }
  }
  const patch =
    next === "archived"
      ? { status: "archived", archived_at: new Date().toISOString() }
      : { status: "active", archived_at: null };
  const { error } = await supabase
    .from("watch_status")
    .update(patch)
    .eq("id", id);
  if (error) throw new Error(error.message);
  revalidatePath(path);
  revalidatePath("/archive");
  revalidatePath("/situation");
  revalidatePath("/zaim");
  revalidatePath("/");
}

/** @deprecated use app/actions/triage.ts — 互換のため残す */
export async function setTriageStatus(
  id: string,
  next: "pending" | "done" | "sent" | "skipped" | "snoozed",
  path: string
) {
  const { setTriageStatus: setStatus } = await import("./triage");
  const r = await setStatus(id, next, path);
  if (!r.ok) throw new Error(r.error);
}
