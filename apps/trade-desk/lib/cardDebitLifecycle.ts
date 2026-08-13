/** card_debit_watch 向け lifecycle を sync_meta に書く（Vercel → Mac runner 合流） */

export type CardDebitLifecyclePatch = {
  dueDate: string;
  planReady?: boolean;
  settled?: boolean;
  opId?: string;
};

function parseYmd(s: string): string | null {
  const t = s.trim().slice(0, 10);
  return /^\d{4}-\d{2}-\d{2}$/.test(t) ? t : null;
}

export async function writeCardDebitLifecycle(
  // Supabase client（select/upsert チェーン）
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  supabase: any,
  patch: CardDebitLifecyclePatch
): Promise<{ ok: boolean; error?: string }> {
  const due = parseYmd(patch.dueDate);
  if (!due) return { ok: false, error: "dueDate invalid" };

  const { data: row } = await supabase
    .from("sync_meta")
    .select("value")
    .eq("key", "card_debit_lifecycle")
    .maybeSingle();

  let prev: Record<string, unknown> = {};
  if (row?.value) {
    try {
      const parsed = JSON.parse(row.value);
      if (parsed && typeof parsed === "object") prev = parsed;
    } catch {
      prev = {};
    }
  }

  const next: Record<string, unknown> = {
    ...prev,
    updated_at: new Date().toISOString(),
  };
  if (patch.opId) next.source_op_id = patch.opId;
  if (patch.planReady) next.plan_ready_due = due;
  if (patch.settled) next.settled_due = due;

  const { error } = await supabase.from("sync_meta").upsert(
    {
      key: "card_debit_lifecycle",
      value: JSON.stringify(next),
      updated_at: new Date().toISOString(),
    },
    { onConflict: "key" }
  );
  if (error) return { ok: false, error: error.message };
  return { ok: true };
}
