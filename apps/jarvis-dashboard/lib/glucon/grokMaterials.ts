/** Grok Drive → glucon_material_items の読取・ライフサイクル */

import { createClient } from "@/lib/supabase/server";
import { periodKeyFromGluconDate, ymdJst } from "@/lib/glucon/schedule";

export type GluconMaterialStatus =
  | "pending"
  | "used"
  | "skipped"
  | "cycle_closed";

export type GluconMaterialItem = {
  id: string;
  period_key: string | null;
  kind: string;
  title: string;
  body: string;
  source: string;
  for_result: boolean;
  status: GluconMaterialStatus;
  used_in_period_key: string | null;
  recorded_at: string | null;
  created_at?: string;
  updated_at?: string;
};

const MATERIAL_SELECT =
  "id,period_key,kind,title,body,source,for_result,status,used_in_period_key,recorded_at,created_at,updated_at";

function matchesKind(
  row: GluconMaterialItem,
  kind: "activity" | "result",
): boolean {
  if (kind === "result") {
    return row.kind === "result" || row.kind === "either" || row.for_result;
  }
  return row.kind === "activity" || row.kind === "either" || !row.for_result;
}

export async function loadPendingGluconMaterials(args: {
  periodKey: string;
  kind: "activity" | "result";
}): Promise<GluconMaterialItem[]> {
  const supabase = await createClient();
  const { data, error } = await supabase
    .from("glucon_material_items")
    .select(MATERIAL_SELECT)
    .eq("status", "pending")
    .or(`period_key.eq.${args.periodKey},period_key.is.null`)
    .order("recorded_at", { ascending: false })
    .limit(30);

  if (error || !data) return [];

  return (data as GluconMaterialItem[]).filter((row) =>
    matchesKind(row, args.kind),
  );
}

export async function loadAllGluconMaterials(filters?: {
  kind?: "activity" | "result";
  periodKey?: string;
  status?: GluconMaterialStatus;
}): Promise<GluconMaterialItem[]> {
  const supabase = await createClient();
  let q = supabase
    .from("glucon_material_items")
    .select(MATERIAL_SELECT)
    .order("recorded_at", { ascending: false })
    .limit(200);

  if (filters?.periodKey) {
    q = q.eq("period_key", filters.periodKey);
  }
  if (filters?.status) {
    q = q.eq("status", filters.status);
  }

  const { data, error } = await q;
  if (error || !data) return [];

  let rows = data as GluconMaterialItem[];
  if (filters?.kind) {
    rows = rows.filter((row) => matchesKind(row, filters.kind!));
  }
  return rows;
}

/** グルコン日経過の activity 材料を cycle_closed に（Q6） */
export async function closeExpiredGluconMaterials(
  today = ymdJst(),
): Promise<number> {
  const supabase = await createClient();
  const { data: schedules } = await supabase
    .from("glucon_schedule")
    .select("glucon_date")
    .lt("glucon_date", today);

  if (!schedules?.length) return 0;

  const periodKeys = [
    ...new Set(
      schedules.map((s) =>
        periodKeyFromGluconDate(String(s.glucon_date || "")),
      ),
    ),
  ].filter(Boolean);

  let closed = 0;
  const now = new Date().toISOString();
  for (const pk of periodKeys) {
    const { data, error } = await supabase
      .from("glucon_material_items")
      .update({
        status: "cycle_closed",
        updated_at: now,
      })
      .eq("period_key", pk)
      .in("kind", ["activity", "either"])
      .eq("status", "pending")
      .select("id");
    if (!error && data) closed += data.length;
  }
  return closed;
}

/** 投稿完了時に注入済み材料を used に */
export async function markGluconMaterialsUsed(args: {
  materialIds: string[];
  periodKey: string;
}): Promise<void> {
  const ids = args.materialIds.filter(Boolean);
  if (!ids.length) return;

  const supabase = await createClient();
  const now = new Date().toISOString();
  await supabase
    .from("glucon_material_items")
    .update({
      status: "used",
      used_in_period_key: args.periodKey,
      updated_at: now,
    })
    .in("id", ids)
    .eq("status", "pending");
}

export function formatGluconMaterialsBlock(
  items: GluconMaterialItem[],
): string {
  if (!items.length) return "";
  const lines = items.map(
    (m) =>
      `- [${m.source}] ${m.title}: ${m.body.replace(/\s+/g, " ").trim().slice(0, 400)}`,
  );
  return `
【Grok Bot 活躍・材料（Drive 40_glucon_materials）】
- 神大家・不動産・AI推進（神大家関連）として使える事実だけ採用する。
- 捏造しない。ここに無い詳細は書かない。
${lines.join("\n")}
`;
}
