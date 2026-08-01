import LaneCardsPage from "@/components/LaneCards";

export default async function Page() {
  return await LaneCardsPage({
    lane: "ai_raimo",
    title: "AI・Raimo",
    active: "/ai-raimo",
  });
}
