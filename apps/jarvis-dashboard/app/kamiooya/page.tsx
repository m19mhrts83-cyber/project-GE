import LaneCardsPage from "@/components/LaneCards";

export default async function Page() {
  return await LaneCardsPage({
    lane: "kamiooya",
    title: "神大家運営",
    active: "/kamiooya",
  });
}
