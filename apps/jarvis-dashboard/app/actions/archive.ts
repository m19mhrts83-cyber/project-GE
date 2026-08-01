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
}
