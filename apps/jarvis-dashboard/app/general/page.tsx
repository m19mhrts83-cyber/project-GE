import TriageLanePage from "@/components/TriageLane";

export default async function GeneralPage() {
  return await TriageLanePage({
    lane: "general",
    title: "それ以外（admin Gmail）",
    active: "/general",
  });
}
