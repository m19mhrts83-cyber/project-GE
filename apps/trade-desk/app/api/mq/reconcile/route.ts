import { createClient } from "@/lib/supabase/server";
import { NextResponse } from "next/server";
import type { EntityFilter } from "@/lib/mqAggregate";
import {
  aggregateRows,
  filterFactsYearActual,
  type MqFactRow,
} from "@/lib/mqAggregate";
import { fetchAllMqPeriodFacts } from "@/lib/mqFactsFetch";
import { pickNearestBs, yearEndDate, normalizeBs, type MqBsRow } from "@/lib/mqBs";
import { buildCashflowYearFromDb } from "@/lib/mqCashflowLoad";
import {
  buildReconcileDiffs,
  projectCashflowToMqBs,
} from "@/lib/mqCashflowProject";

export async function GET(req: Request) {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();
  if (!user) {
    return NextResponse.json({ error: "unauthorized" }, { status: 401 });
  }

  const url = new URL(req.url);
  const year = Number(url.searchParams.get("year") || new Date().getFullYear());
  const entity = (url.searchParams.get("entity") || "corporate") as EntityFilter;
  const line = (url.searchParams.get("line") || "realestate") as
    | "realestate"
    | "ai";

  if (!Number.isFinite(year)) {
    return NextResponse.json({ error: "year invalid" }, { status: 400 });
  }
  if (entity === "combined") {
    return NextResponse.json(
      { error: "entity must be personal or corporate" },
      { status: 400 }
    );
  }

  try {
    const built = await buildCashflowYearFromDb(supabase, {
      year,
      entity,
      businessLine: line,
    });
    const project = projectCashflowToMqBs({
      year,
      rows: built.rows,
      settings: built.settings,
    });

    const facts = (await fetchAllMqPeriodFacts(supabase)) as MqFactRow[];
    const subset = filterFactsYearActual(facts, line, entity, String(year));
    const agg = aggregateRows(subset, "year");

    const { data: bsRaw } = await supabase
      .from("kurashift_mq_bs_snapshots")
      .select("*")
      .eq("business_line", line)
      .eq("entity", entity)
      .order("as_of_date", { ascending: false })
      .limit(40);
    const asOf = yearEndDate(String(year));
    const nearest = pickNearestBs((bsRaw ?? []) as MqBsRow[], line, entity, asOf);
    const bsFields = nearest ? normalizeBs(nearest) : null;

    const diffs = buildReconcileDiffs({
      project,
      factsAnnual: {
        pq: agg.computed?.pq ?? null,
        vq: agg.computed?.vq ?? null,
        f: agg.computed?.f ?? null,
        cash_in: agg.cashIn,
        cash_out: agg.cashOut,
        cash_end: agg.cashEnd,
      },
      bsSnap: bsFields
        ? { cash: bsFields.cash, current_profit: bsFields.current_profit }
        : null,
    });

    return NextResponse.json({
      ok: true,
      year,
      entity,
      line,
      project,
      diffs,
      factsCount: subset.length,
      bsAsOf: nearest?.as_of_date ?? null,
      bsSource: nearest?.source ?? null,
    });
  } catch (e) {
    return NextResponse.json(
      { error: e instanceof Error ? e.message : String(e) },
      { status: 500 }
    );
  }
}
