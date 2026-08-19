/**
 * MQ 年度実績を Zaim TXN から再集計して置換（service_role）
 *
 * Usage:
 *   cd apps/trade-desk && set -a && source ../../.env.jarvis_private && set +a
 *   npx tsx scripts/mqYearRefresh.ts --year 2026
 *   npx tsx scripts/mqYearRefresh.ts --year 2026 --dry-run
 *   npx tsx scripts/mqYearRefresh.ts --year 2026 --force
 */
import { createClient } from "@supabase/supabase-js";
import { applyMqYearIngest } from "../lib/mqIngestDb";
import type { MqAccountMapRow } from "../lib/mqZaimMap";

function arg(name: string): string | null {
  const i = process.argv.indexOf(name);
  if (i < 0) return null;
  return process.argv[i + 1] ?? null;
}

async function main() {
  const year = Number(arg("--year")) || new Date().getFullYear();
  const dryRun = process.argv.includes("--dry-run");
  const force = process.argv.includes("--force");

  const url = process.env.JARVIS_SUPABASE_URL || process.env.NEXT_PUBLIC_SUPABASE_URL;
  const key =
    process.env.JARVIS_SUPABASE_SERVICE_ROLE_KEY ||
    process.env.SUPABASE_SERVICE_ROLE_KEY;
  if (!url || !key) {
    throw new Error("JARVIS_SUPABASE_URL / JARVIS_SUPABASE_SERVICE_ROLE_KEY が必要です");
  }
  const sb = createClient(url, key);

  const { data: maps, error: mapErr } = await sb
    .from("kurashift_mq_account_map")
    .select("*")
    .eq("approved", true)
    .order("priority");
  if (mapErr) throw new Error(mapErr.message);

  const out = await applyMqYearIngest(sb, (maps ?? []) as MqAccountMapRow[], {
    year,
    force,
    dryRun,
  });
  console.log(JSON.stringify({ ok: true, ...out }, null, 2));
}

main().catch((e) => {
  console.error(e instanceof Error ? e.message : e);
  process.exit(1);
});
