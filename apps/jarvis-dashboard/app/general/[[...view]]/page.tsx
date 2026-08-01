import TriageLanePage from "@/components/TriageLane";
import { parseLaneView } from "@/lib/laneView";

export const dynamic = "force-dynamic";

export default async function GeneralPage({
  params,
  searchParams,
}: {
  params: Promise<{ view?: string[] }>;
  searchParams: Promise<{ i?: string; view?: string }>;
}) {
  const p = await params;
  const sp = await searchParams;
  const fromPath = p.view?.[0];
  const view = parseLaneView(fromPath || sp.view);

  return await TriageLanePage({
    lane: "general",
    title: "それ以外（admin Gmail）",
    active: "/general",
    subtitle: "ざざっと見て必要なものだけ開く。終わったら一括スキップ。",
    view,
    searchParams: Promise.resolve(sp),
  });
}
