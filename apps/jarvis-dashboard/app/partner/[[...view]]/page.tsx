import TriageLanePage from "@/components/TriageLane";
import { parseLaneView } from "@/lib/laneView";

/** Cursor Cloud Agent 見直しの待ち時間用 */
export const maxDuration = 120;
export const dynamic = "force-dynamic";

export default async function PartnerPage({
  params,
  searchParams,
}: {
  params: Promise<{ view?: string[] }>;
  searchParams: Promise<{ i?: string; view?: string }>;
}) {
  const p = await params;
  const sp = await searchParams;
  // パス /partner/sent を優先。旧 ?view= も互換で受ける
  const fromPath = p.view?.[0];
  const view = parseLaneView(fromPath || sp.view);

  return await TriageLanePage({
    lane: "partner",
    title: "パートナー",
    active: "/partner",
    view,
    subtitle:
      "未返信インボックス（件名・相手・チャネル）。夜間は判定・下書きなし。処置は Gmail → パートナー確認。",
    searchParams: Promise.resolve(sp),
  });
}
