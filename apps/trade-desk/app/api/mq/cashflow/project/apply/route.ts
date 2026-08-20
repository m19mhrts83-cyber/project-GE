import { createClient } from "@/lib/supabase/server";
import { NextResponse } from "next/server";
import type { EntityFilter } from "@/lib/mqAggregate";
import { buildCashflowYearFromDb } from "@/lib/mqCashflowLoad";
import { projectCashflowToMqBs } from "@/lib/mqCashflowProject";
import { fetchYearActualFacts } from "@/lib/mqIngestDb";

export async function POST(req: Request) {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();
  if (!user) {
    return NextResponse.json({ error: "unauthorized" }, { status: 401 });
  }

  const body = await req.json().catch(() => ({}));
  const year = Number(body.year);
  const entity = String(body.entity || "corporate") as EntityFilter;
  const line = String(body.businessLine || body.line || "realestate");
  const applyBs = body.applyBs !== false;
  const confirm = Boolean(body.confirm);

  if (!confirm) {
    return NextResponse.json(
      { error: "confirm required" },
      { status: 400 }
    );
  }
  if (!Number.isFinite(year) || year < 2000) {
    return NextResponse.json({ error: "year invalid" }, { status: 400 });
  }
  if (entity !== "personal" && entity !== "corporate") {
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

    const existing = await fetchYearActualFacts(supabase, year);
    const manualKeys = new Set(
      existing
        .filter(
          (r) =>
            r.source === "manual" &&
            r.business_line === line &&
            r.entity === entity
        )
        .map((r) => String(r.period_month).slice(0, 7))
    );

    let upserted = 0;
    let skippedManual = 0;
    for (const m of project.months) {
      const mo = m.period_month.slice(0, 7);
      if (manualKeys.has(mo)) {
        skippedManual += 1;
        continue;
      }
      const { error } = await supabase.from("kurashift_mq_period_facts").upsert(
        {
          business_line: line,
          entity,
          period_month: `${mo}-01`,
          scenario_kind: "actual",
          plan_variant_id: "",
          pq: m.pq,
          vq: m.vq,
          f: m.f,
          f_annual: m.f_annual,
          cash_in: m.cash_in,
          cash_out: m.cash_out,
          cash_end: m.cash_end,
          note: `${year} 資金繰り投影`,
          source: "cashflow",
          updated_at: new Date().toISOString(),
        },
        {
          onConflict:
            "business_line,entity,period_month,scenario_kind,plan_variant_id",
        }
      );
      if (error) {
        return NextResponse.json({ error: error.message }, { status: 500 });
      }
      upserted += 1;
    }

    let bsApplied = false;
    if (applyBs) {
      const { data: existingBs } = await supabase
        .from("kurashift_mq_bs_snapshots")
        .select("source")
        .eq("business_line", line)
        .eq("entity", entity)
        .eq("as_of_date", project.bs.as_of)
        .maybeSingle();
      if (existingBs?.source === "manual") {
        skippedManual += 1;
      } else {
        const { error: bsErr } = await supabase
          .from("kurashift_mq_bs_snapshots")
          .upsert(
            {
              business_line: line,
              entity,
              as_of_date: project.bs.as_of,
              cash: project.bs.cash,
              receivables: project.bs.receivables,
              inventory: project.bs.inventory,
              fixed_assets: project.bs.fixed_assets,
              liabilities_st: project.bs.liabilities_st,
              liabilities_lt: project.bs.liabilities_lt,
              capital: project.bs.capital,
              retained_earnings: project.bs.retained_earnings,
              current_profit: project.bs.current_profit,
              note: `${year} 資金繰り投影`,
              source: "cashflow_project",
              updated_at: new Date().toISOString(),
            },
            { onConflict: "business_line,entity,as_of_date" }
          );
        if (bsErr) {
          return NextResponse.json({ error: bsErr.message }, { status: 500 });
        }
        bsApplied = true;
      }
    }

    const { error: histErr } = await supabase
      .from("kurashift_mq_cashflow_projections")
      .insert({
        business_line: line,
        entity,
        fiscal_year: year,
        fact_months: upserted,
        skipped_manual: skippedManual,
        bs_applied: bsApplied,
        note: "apply from cashflow L1",
        payload: {
          annual: project.annual,
          g: project.computed.g,
          loanExcludedFromG: project.loanExcludedFromG,
        },
        created_by: user.id,
      });
    if (histErr) {
      return NextResponse.json({ error: histErr.message }, { status: 500 });
    }

    return NextResponse.json({
      ok: true,
      upserted,
      skippedManual,
      bsApplied,
      project,
    });
  } catch (e) {
    return NextResponse.json(
      { error: e instanceof Error ? e.message : String(e) },
      { status: 500 }
    );
  }
}
