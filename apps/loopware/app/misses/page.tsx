import { Suspense } from "react";
import TriageMissesClient from "@/components/TriageMissesClient";

export const metadata = { title: "見落とし｜ループウェア" };
export const dynamic = "force-dynamic";

export default function MissesPage() {
  return (
    <main>
      <Suspense>
        <TriageMissesClient />
      </Suspense>
    </main>
  );
}
