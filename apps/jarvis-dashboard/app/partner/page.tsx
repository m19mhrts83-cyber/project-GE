import TriageLanePage from "@/components/TriageLane";

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
