"use server";

import { revalidatePath } from "next/cache";
import { listPropertySelectOptions } from "@/lib/notionTasks";
import { updateTaskStatus } from "@/lib/taskBoard";

export async function updateNotionTaskStatusAction(
  lane: string,
  pageId: string,
  status: string,
  path: string,
): Promise<{ ok: true } | { ok: false; error: string }> {
  const r = await updateTaskStatus(lane, pageId, status);
  if (!r.ok) return r;
  revalidatePath(path);
  return { ok: true };
}

export async function fetchPropertySelectOptionsAction(
  lane: string,
): Promise<{ ok: true; options: string[] } | { ok: false; error: string }> {
  return listPropertySelectOptions(lane);
}
