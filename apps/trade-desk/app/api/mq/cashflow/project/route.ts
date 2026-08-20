import { createClient } from "@/lib/supabase/server";
import { NextResponse } from "next/server";
import type { EntityFilter } from "@/lib/mqAggregate";
import { buildCashflowYearFromDb } from "@/lib/mqCashflowLoad";
import { projectCashflowToMqBs } from "@/lib/mqCashflowProject";

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
  const line = url.searchParams.get("line") || "realestate";

  if (!Number.isFinite(year) || year < 2000) {
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
    return NextResponse.json({
      ok: true,
      project,
      openingCashMan: built.openingCashMan,
    });
  } catch (e) {
    return NextResponse.json(
      { error: e instanceof Error ? e.message : String(e) },
      { status: 500 }
    );
  }
}
