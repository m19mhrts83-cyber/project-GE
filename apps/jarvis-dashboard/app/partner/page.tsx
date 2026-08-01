import TriageLanePage from "@/components/TriageLane";

/** Cursor Cloud Agent 見直しの待ち時間用 */
export const maxDuration = 120;

export default async function PartnerPage({
  searchParams,
}: {
  searchParams: Promise<{ i?: string }>;
}) {
  return await TriageLanePage({
    lane: "partner",
    title: "パートナー",
    active: "/partner",
    subtitle:
      "初稿は OneDrive「5.やり取り.md」の直近を踏まえて夜間に用意。見直し（こう直して）はいまの下書き＋指示のみで、やり取りは再読しません。",
    searchParams,
  });
}
