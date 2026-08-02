import TriageLanePage from "@/components/TriageLane";
import { parseLaneView } from "@/lib/laneView";

/** Cursor Cloud / Gemini 見直し・聞くの待ち時間用（vercel.json の functions 一括指定は使わない） */
export const maxDuration = 120;
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
