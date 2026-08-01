import TriageLanePage from "@/components/TriageLane";

export const dynamic = "force-dynamic";

export default async function GeneralPage({
  searchParams,
}: {
  searchParams: Promise<{ i?: string; view?: string }>;
}) {
  const sp = await searchParams;
  return await TriageLanePage({
    lane: "general",
    title: "それ以外（admin Gmail）",
    active: "/general",
    searchParams: Promise.resolve(sp),
  });
}
