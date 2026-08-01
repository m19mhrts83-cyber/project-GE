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
    searchParams,
  });
}
