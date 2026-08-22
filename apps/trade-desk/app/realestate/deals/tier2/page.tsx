import Shell from "@/components/Shell";
import DealInquiryTier2BatchClient from "@/components/DealInquiryTier2BatchClient";
import RealEstateLaneNav from "@/components/RealEstateLaneNav";
import { createClient } from "@/lib/supabase/server";
import Link from "next/link";

export const dynamic = "force-dynamic";

export default async function Tier2InquiryBatchPage() {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();

  return (
    <Shell active="/realestate" email={user?.email ?? null}>
      <RealEstateLaneNav active="b-funnel" />
      <p className="page-kicker">③-B · Tier2</p>
      <h1>送信待ち — 一括問合せ</h1>
      <p className="sub">
        Grok「聞く」+ スコア高めの案件をまとめて確認し、estate から第一問合せを送ります。
        送信前に必ず本文を確認してください（1日上限あり）。
      </p>
      <p className="meta" style={{ marginBottom: 16 }}>
        <Link href="/realestate/deals?tab=candidates">← 千三つ候補一覧</Link>
        {" · "}
        初級者向け: git `docs/KURASHIFT_Tier1_問合せ_初級者手順.md`
      </p>
      <DealInquiryTier2BatchClient />
    </Shell>
  );
}
