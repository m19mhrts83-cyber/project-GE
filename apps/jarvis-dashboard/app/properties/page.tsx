import LaneCardsPage from "@/components/LaneCards";

export default async function Page() {
  return await LaneCardsPage({
    lane: "properties",
    title: "3棟・物件",
    active: "/properties",
  });
}
