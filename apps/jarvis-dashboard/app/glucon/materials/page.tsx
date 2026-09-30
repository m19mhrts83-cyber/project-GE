import Shell from "@/components/Shell";
import GluconMaterialsList from "@/components/glucon/GluconMaterialsList";
import { getGluconMaterialsPageState } from "@/app/actions/glucon";

export const maxDuration = 60;

type SearchParams = Promise<{
  tab?: string;
  period_key?: string;
  status?: string;
}>;

export default async function GluconMaterialsPage({
  searchParams,
}: {
  searchParams: SearchParams;
}) {
  const sp = await searchParams;
  const tab = sp.tab === "result" ? "result" : "activity";
  const state = await getGluconMaterialsPageState({
    tab,
    periodKey: sp.period_key || undefined,
    status: sp.status || undefined,
  });

  return (
    <Shell active="/glucon">
      <h1>グルコン材料・下書き一覧</h1>
      <p className="meta">
        ホークが Drive に置いた活動・成果材料と、月次下書きをいつでも確認できます。投稿の有無に関わらず参照できます。
      </p>

      {state.loadError ? (
        <p className="qe-err">読み込みエラー: {state.loadError}</p>
      ) : null}

      <GluconMaterialsList
        tab={tab}
        materials={state.materials}
        drafts={state.drafts}
        periodKeys={state.periodKeys}
        periodKey={sp.period_key}
        status={sp.status}
      />
    </Shell>
  );
}
