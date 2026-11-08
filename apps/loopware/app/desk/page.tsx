import { Suspense } from "react";
import DeskClient from "@/components/DeskClient";
import LeftClient from "@/components/LeftClient";

export const metadata = { title: "判断デスク｜ループウェア" };
export const dynamic = "force-dynamic";

export default async function DeskPage({ searchParams }: { searchParams: Promise<{ view?: string }> }) {
  const { view } = await searchParams;
  return (
    <main>
      <Suspense>{view === "left" ? <LeftClient /> : <DeskClient />}</Suspense>
    </main>
  );
}
