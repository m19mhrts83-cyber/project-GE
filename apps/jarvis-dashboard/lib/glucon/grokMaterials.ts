/** Grok Drive → glucon_material_items の読取（下書き注入） */

import { createClient } from "@/lib/supabase/server";

export type GluconMaterialItem = {
  id: string;
  period_key: string | null;
  kind: string;
  title: string;
  body: string;
  source: string;
  for_result: boolean;
  status: string;
  recorded_at: string | null;
};

export async function loadPendingGluconMaterials(args: {
  periodKey: string;
  kind: "activity" | "result";
}): Promise<GluconMaterialItem[]> {
  const supabase = await createClient();
  const { data, error } = await supabase
    .from("glucon_material_items")
    .select(
      "id,period_key,kind,title,body,source,for_result,status,recorded_at",
    )
    .eq("status", "pending")
    .or(
      `period_key.eq.${args.periodKey},period_key.is.null`,
    )
    .order("recorded_at", { ascending: false })
    .limit(30);

  if (error || !data) return [];

  return (data as GluconMaterialItem[]).filter((row) => {
    if (args.kind === "result") {
      return row.kind === "result" || row.kind === "either" || row.for_result;
    }
    return row.kind === "activity" || row.kind === "either" || !row.for_result;
  });
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
