import Shell from "@/components/Shell";
import LifeplanSheetsNav from "@/components/LifeplanSheetsNav";
import CenturyExplorer from "@/components/CenturyExplorer";
import { createClient } from "@/lib/supabase/server";
import {
  buildCenturyModel,
  diffEvalPlan,
  type SheetDump,
} from "@/lib/centuryPlan";
import { parseLifeplanMode } from "@/lib/lifeplanNotices";
import { redirect } from "next/navigation";

export const dynamic = "force-dynamic";

export default async function LifeplanCenturyPage({
  searchParams,
}: {
  searchParams: Promise<{ mode?: string }>;
}) {
  const sp = await searchParams;
  const mode = parseLifeplanMode(sp.mode);
  if (mode === "annual" || mode === "re_purchase") {
    redirect(`/lifeplan/budget?mode=${mode}`);
  }

  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();

  const { data: versions } = await supabase
    .from("kurashift_lifeplan_versions")
    .select("id, version_key, as_of, label, is_canonical")
    .order("as_of", { ascending: false })
    .limit(8);

  const canonical =
    (versions ?? []).find((v) => v.is_canonical) ?? (versions ?? [])[0] ?? null;
  const previous =
    (versions ?? []).find((v) => canonical && v.id !== canonical.id) ?? null;

  const ids = [canonical?.id, previous?.id].filter(Boolean) as string[];
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
        .eq("sheet_name", "キャッシュフロー")
        .in("version_id", ids)
    : { data: [] as DumpRow[] };

  const dumpsOf = (id: string | undefined): SheetDump[] =>
    ((dumps ?? []) as DumpRow[])
      .filter((d) => d.version_id === id)
      .map((d) => ({
        sheet_name: d.sheet_name,
        table_name: d.table_name,
        payload: d.payload,
      }));

  const current = canonical
    ? buildCenturyModel(dumpsOf(canonical.id), {
        versionKey: canonical.version_key,
        asOf: canonical.as_of,
        label: canonical.label || "100歳計画",
      })
    : null;
  const prevModel = previous
    ? buildCenturyModel(dumpsOf(previous.id), {
        versionKey: previous.version_key,
        asOf: previous.as_of,
        label: previous.label || previous.version_key,
      })
    : null;
  const diffs =
    current && prevModel
      ? diffEvalPlan(
          current,
          prevModel,
          current.years.filter((y) => y >= 2020 && y <= 2050)
        )
      : [];

  return (
    <Shell active="/lifeplan" email={user?.email ?? null}>
      <LifeplanSheetsNav current="century" />
      <h1>100歳計画</h1>
      <p className="sub">
        これまで Numbers で見ていたキャッシュフロー（〜100歳）です。最新版を閲覧し、年次更新の前後差もここで確認します。
      </p>
      {current ? (
        <CenturyExplorer current={current} previous={prevModel} diffs={diffs} />
      ) : (
        <div className="card">
          <p className="meta" style={{ margin: 0 }}>
            計画データの取り込みがまだありません。Jarvis に「ライフプラン履歴を取り込んで」と依頼してください。
          </p>
        </div>
      )}
      <p className="meta" style={{ marginTop: 18 }}>
        年次の予算づくりは <a href="/lifeplan/budget">予算編成</a>、支出内訳 αβγ は{" "}
        <a href="/lifeplan/abg">支出の見方</a> です。
      </p>
    </Shell>
  );
}
