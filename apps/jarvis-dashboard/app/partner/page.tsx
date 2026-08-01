import TriageLanePage from "@/components/TriageLane";

export default async function PartnerPage() {
  return await TriageLanePage({
    lane: "partner",
    title: "パートナー",
    active: "/partner",
  });
}
