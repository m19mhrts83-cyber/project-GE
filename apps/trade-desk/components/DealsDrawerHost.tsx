"use client";

import { usePathname, useRouter, useSearchParams } from "next/navigation";
import DealDetailDrawer from "@/components/DealDetailDrawer";

export default function DealsDrawerHost({ dealId }: { dealId: string | null }) {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();

  if (!dealId) return null;

  return (
    <DealDetailDrawer
      dealId={dealId}
      onClose={() => {
        const sp = new URLSearchParams(searchParams.toString());
        sp.delete("deal");
        const q = sp.toString();
        router.push(q ? `${pathname}?${q}` : pathname);
      }}
    />
  );
}
