import { Suspense } from "react";
import { cookies } from "next/headers";
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
import HomeActivityBand from "@/components/home/HomeActivityBand";
import HomeSections, { type HomeSection } from "@/components/home/HomeSections";
import {
  HOME_DEFAULT_ORDER,
  HOME_ORDER_COOKIE,
  parseHomeOrder,
} from "@/lib/homeOrder";

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

export default async function HomePage() {
  const saved = parseHomeOrder((await cookies()).get(HOME_ORDER_COOKIE)?.value);

  /** 並べ替えできるカード（上の「いまやること」帯と最下部の詳細は固定） */
  const sections: HomeSection[] = [
    {
      id: "today_queue",
      label: "今日のキュー",
      node: (
        <Suspense fallback={<TodayQueueSkeleton />}>
          <HomeTodayQueue />
        </Suspense>
      ),
    },
    { id: "uiux", label: "UI/UX 3アプリの現在地", node: <HomeUiuxScoreBand /> },
    {
      id: "maturity",
      label: "AIエージェント運用の成熟度",
      node: (
        <Suspense fallback={null}>
          <HomeMaturityBand />
        </Suspense>
      ),
    },
    {
      id: "activity",
      label: "AI社員の週次稼働",
      node: (
        <Suspense fallback={null}>
          <HomeActivityBand />
        </Suspense>
      ),
    },
    {
      id: "loopware",
      label: "ループウェア（判断待ち）",
      node: (
        <Suspense fallback={null}>
          <HomeLoopwareBand />
        </Suspense>
      ),
    },
    {
      id: "partner",
      label: "パートナー",
      node: (
        <Suspense fallback={<BandSkeleton label="パートナー" />}>
          <HomePartnerBand />
        </Suspense>
      ),
    },
    {
      id: "metrics",
      label: "モチベーション数値",
      node: (
        <Suspense fallback={<BandSkeleton label="モチベーション数値" />}>
          <HomeMetricsBand />
        </Suspense>
      ),
    },
    {
      id: "kurashift",
      label: "KURASHIFT へのリンク",
      node: <HomeKurashiftLink />,
    },
    {
      id: "watch",
      label: "状況ウォッチ",
      node: (
        <Suspense fallback={<BandSkeleton label="状況ウォッチ" />}>
          <HomeWatchBand />
        </Suspense>
      ),
    },
    {
      id: "other",
      label: "その他メール",
      node: (
        <Suspense fallback={<BandSkeleton label="その他メール" />}>
          <HomeOtherBand />
        </Suspense>
      ),
    },
    {
      id: "openchat",
      label: "神大家オプチャまとめ",
      node: (
        <Suspense fallback={<BandSkeleton label="神大家オプチャまとめ" />}>
          <HomeOpenchatBand />
        </Suspense>
      ),
    },
  ];

  return (
    <Shell active="/">
      <div className="home-hero">
        <div>
          <div className="pb-eyebrow-t">{todayLabel()}</div>
          <h1>おかえりなさい、松野さん</h1>
        </div>
        <p className="sub">
          いまやること → 下のカードは「並べ替え」で好きな順に。号室表は{" "}
          <a href="/properties">所有物件</a>。⌘K で移動。
        </p>
      </div>

      <Suspense fallback={null}>
        <HomePinBanner />
      </Suspense>

      <Suspense fallback={null}>
        <HomeMqMonthClosePin />
      </Suspense>

      <Suspense
        fallback={
          <div
            className="skel-line"
            style={{ maxWidth: 360, marginBottom: 12 }}
          />
        }
      >
        <HomeSyncBar />
      </Suspense>

      <HomeSections
        sections={sections}
        initialOrder={saved}
        defaultOrder={HOME_DEFAULT_ORDER}
      />

      <Suspense fallback={null}>
        <HomeMetaDetails />
      </Suspense>
    </Shell>
  );
}
