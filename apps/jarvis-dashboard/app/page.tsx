import { Suspense } from "react";
import Shell from "@/components/Shell";
import { BandSkeleton, TodayQueueSkeleton } from "@/components/Skeletons";
import HomeTodayQueue from "@/components/home/HomeTodayQueue";
import HomeSyncBar from "@/components/home/HomeSyncBar";
import HomePinBanner from "@/components/home/HomePinBanner";
import HomePartnerBand from "@/components/home/HomePartnerBand";
import HomeMetricsBand from "@/components/home/HomeMetricsBand";
import HomeWatchBand from "@/components/home/HomeWatchBand";
import HomeOtherBand from "@/components/home/HomeOtherBand";
import HomeOpenchatBand from "@/components/home/HomeOpenchatBand";
import HomeMetaDetails from "@/components/home/HomeMetaDetails";
import HomeTradeDeskLink from "@/components/home/HomeTradeDeskLink";

export default function HomePage() {
  return (
    <Shell active="/">
      <h1>ホーム</h1>
      <p className="sub">
        今日のキュー → パートナー → モチベーション（入居率ヒーロー＋手残りCF） → 状況ウォッチ → その他メール → 神大家オプチャまとめの順。
        号室表・履歴は{" "}
        <a href="/properties" style={{ color: "var(--accent)", fontWeight: 600 }}>
          所有物件
        </a>
        。⌘K で画面移動。
      </p>

      <Suspense fallback={null}>
        <HomePinBanner />
      </Suspense>

      <Suspense fallback={<div className="skel-line" style={{ maxWidth: 360, marginBottom: 12 }} />}>
        <HomeSyncBar />
      </Suspense>

      <Suspense fallback={<TodayQueueSkeleton />}>
        <HomeTodayQueue />
      </Suspense>

      <Suspense fallback={<BandSkeleton label="パートナー" />}>
        <HomePartnerBand />
      </Suspense>

      <Suspense fallback={<BandSkeleton label="モチベーション数値" />}>
        <HomeMetricsBand />
      </Suspense>

      <HomeTradeDeskLink />

      <Suspense fallback={<BandSkeleton label="状況ウォッチ" />}>
        <HomeWatchBand />
      </Suspense>

      <Suspense fallback={<BandSkeleton label="その他メール" />}>
        <HomeOtherBand />
      </Suspense>

      <Suspense fallback={<BandSkeleton label="神大家オプチャまとめ" />}>
        <HomeOpenchatBand />
      </Suspense>

      <Suspense fallback={null}>
        <HomeMetaDetails />
      </Suspense>
    </Shell>
  );
}
