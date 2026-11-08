import { Suspense } from "react";
import DeskClient from "@/components/DeskClient";

export const metadata = { title: "判断デスク｜ループウェア" };
export const dynamic = "force-dynamic";

export default function DeskPage() {
  return (
    <main>
      <Suspense>
        <DeskClient />
      </Suspense>
    </main>
  );
}
