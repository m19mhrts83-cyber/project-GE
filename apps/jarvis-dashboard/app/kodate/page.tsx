import LaneCardsPage from "@/components/LaneCards";

export default async function Page() {
  return await LaneCardsPage({
    lane: "kodate",
    title: "戸建てアクション",
    active: "/kodate",
  });
}
