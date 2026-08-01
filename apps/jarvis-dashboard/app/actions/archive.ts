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
