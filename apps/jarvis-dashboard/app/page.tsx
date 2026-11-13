import { Suspense } from "react";
import Shell from "@/components/Shell";
import { BandSkeleton, TodayQueueSkeleton } from "@/components/Skeletons";
import HomeTodayQueue from "@/components/home/HomeTodayQueue";
import HomeSyncBar from "@/components/home/HomeSyncBar";
import HomePinBanner from "@/components/home/HomePinBanner";
import HomeMqMonthClosePin from "@/components/home/HomeMqMonthClosePin";
import HomePartnerBand from "@/components/home/HomePartnerBand";
import HomeMetricsBand from "@/components/home/HomeMetricsBand";
import HomeWatchBand from "@/components/home/HomeWatchBand";
import HomeOtherBand from "@/components/home/HomeOtherBand";
import HomeOpenchatBand from "@/components/home/HomeOpenchatBand";
import HomeMetaDetails from "@/components/home/HomeMetaDetails";
import HomeKurashiftLink from "@/components/home/HomeKurashiftLink";
import HomeLoopwareBand from "@/components/home/HomeLoopwareBand";
import HomeUiuxScoreBand from "@/components/home/HomeUiuxScoreBand";
import HomeMaturityBand from "@/components/home/HomeMaturityBand";

/** 例: "SAT · 07 NOV 2026"（日本時間） */
function todayLabel(): string {
  const d = new Date();
  const parts = new Intl.DateTimeFormat("en-GB", {
    timeZone: "Asia/Tokyo",
    weekday: "short",
    day: "2-digit",
    month: "short",
    year: "numeric",
  }).formatToParts(d);
  const get = (t: string) => parts.find((p) => p.type === t)?.value ?? "";
  return `${get("weekday")} · ${get("day")} ${get("month")} ${get("year")}`;
}

export default function HomePage() {
  return (
    <Shell active="/">
      <div className="home-hero">
        <div>
          <div className="pb-eyebrow-t">{todayLabel()}</div>
          <h1>おかえりなさい、松野さん</h1>
        </div>
        <p className="sub">
          いまやること → 今日のキュー → パートナー → 数値 → 状況ウォッチ。号室表は{" "}
          <a href="/properties">所有物件</a>。⌘K で移動。
        </p>
      </div>

      <Suspense fallback={null}>
        <HomePinBanner />
      </Suspense>

      <Suspense fallback={null}>
        <HomeMqMonthClosePin />
      </Suspense>

      <Suspense fallback={<div className="skel-line" style={{ maxWidth: 360, marginBottom: 12 }} />}>
        <HomeSyncBar />
      </Suspense>

      <Suspense fallback={<TodayQueueSkeleton />}>
        <HomeTodayQueue />
      </Suspense>

      <Suspense fallback={null}>
        <HomeLoopwareBand />
      </Suspense>

      <Suspense fallback={<BandSkeleton label="パートナー" />}>
        <HomePartnerBand />
      </Suspense>

      <Suspense fallback={<BandSkeleton label="モチベーション数値" />}>
        <HomeMetricsBand />
      </Suspense>

      <HomeKurashiftLink />

      <Suspense fallback={<BandSkeleton label="状況ウォッチ" />}>
        <HomeWatchBand />
      </Suspense>

      <Suspense fallback={<BandSkeleton label="その他メール" />}>
        <HomeOtherBand />
      </Suspense>

      <Suspense fallback={<BandSkeleton label="神大家オプチャまとめ" />}>
        <HomeOpenchatBand />
      </Suspense>

      <HomeUiuxScoreBand />

      <Suspense fallback={null}>
        <HomeMaturityBand />
      </Suspense>

      <Suspense fallback={null}>
        <HomeMetaDetails />
      </Suspense>
    </Shell>
  );
}
