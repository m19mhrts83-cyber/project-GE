import Shell from "@/components/Shell";
import LifeplanSheetsNav from "@/components/LifeplanSheetsNav";
import CenturyAnalyze from "@/components/CenturyAnalyze";
import { createClient } from "@/lib/supabase/server";
import {
  CENTURY_PAGE_TITLE,
  buildCenturyModel,
  evalTotalPlan,
  parseLifeEvents,
  type SheetDump,
} from "@/lib/centuryPlan";
import { fmtManUnit } from "@/lib/format";

export const dynamic = "force-dynamic";

export default async function LifeplanAnalyzePage() {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();

  const { data: versions } = await supabase
    .from("kurashift_lifeplan_versions")
    .select("id, version_key, as_of, label, is_canonical")
    .order("as_of", { ascending: false })
    .limit(6);

  const ordered = [...(versions ?? [])].sort((a, b) => {
    if (a.is_canonical === b.is_canonical) return 0;
    return a.is_canonical ? -1 : 1;
  });
  const ids = ordered.map((v) => v.id);
  type DumpRow = {
    version_id: string;
    sheet_name: string;
    table_name: string;
    payload: SheetDump["payload"];
  };
  const { data: dumps } = ids.length
    ? await supabase
        .from("kurashift_lifeplan_sheet_dumps")
        .select("version_id, sheet_name, table_name, payload")
        .in("sheet_name", ["キャッシュフロー"])
        .in("version_id", ids)
    : { data: [] as DumpRow[] };

  const dumpsOf = (id: string): SheetDump[] =>
    ((dumps ?? []) as DumpRow[])
      .filter((d) => d.version_id === id)
      .map((d) => ({
        sheet_name: d.sheet_name,
        table_name: d.table_name,
        payload: d.payload,
      }));

  const models = ordered.map((v) =>
    buildCenturyModel(dumpsOf(v.id), {
      versionKey: v.version_key,
      asOf: v.as_of,
      label: v.label || v.version_key,
    })
  );
  const events = ordered[0] ? parseLifeEvents(dumpsOf(ordered[0].id)) : null;
  const currentModel = models[0] ?? null;
  const currentYear = new Date().getFullYear();
  const fiveYearRows = currentModel
    ? currentModel.years
        .filter((y) => y >= currentYear && y <= currentYear + 5)
        .map((y) => ({
          year: y,
          value: evalTotalPlan(currentModel)?.values[y] ?? null,
        }))
    : [];
  const weakYears = fiveYearRows.filter((r) => r.value != null && r.value < 0);

  return (
    <Shell active="/lifeplan" email={user?.email ?? null}>
      <LifeplanSheetsNav current="analyze" />
      <h1>{CENTURY_PAGE_TITLE}・分析</h1>
      <p className="sub">
        閲覧用シートはそのままに、過去の計画版を重ねたり、実績のある年をグラフで見たりするページです。
      </p>
      <div className="card" style={{ marginTop: 12 }}>
        <header>
          <span className="lvl">5年耐性</span>
          <strong>今後5年の継続チェック</strong>
        </header>
        <p className="meta" style={{ marginTop: 6 }}>
          直近5年は「続けて投資してよいか」ではなく、「キャッシュが痩せる年がどこか」を先に見ます。
        </p>
        {fiveYearRows.length ? (
          <>
            <ul className="meta" style={{ marginTop: 8 }}>
              {fiveYearRows.map((r) => (
                <li key={r.year}>
                  {r.year}年: {fmtManUnit(r.value)}
                </li>
              ))}
            </ul>
            <p className="meta" style={{ marginTop: 8 }}>
              {weakYears.length
                ? `要注意年: ${weakYears.map((r) => r.year).join(" / ")}`
                : "今見えている5年は大きな資金ショート年なし"}
            </p>
          </>
        ) : (
          <p className="meta" style={{ marginTop: 8 }}>
            5年耐性を出す計画データがまだ不足しています。
          </p>
        )}
      </div>
      {models.length ? (
        <CenturyAnalyze models={models} events={events} />
      ) : (
        <div className="card">
          <p className="meta" style={{ margin: 0 }}>
            計画データの取り込みがまだありません。
          </p>
        </div>
      )}
    </Shell>
  );
}
