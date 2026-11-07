"use client";

import type { ReactNode } from "react";
import type { HomeLevel } from "@/lib/homeLevels";
import OpsFixAckButton from "@/components/OpsFixAckButton";
import Icon from "@/components/Icon";

type Props = {
  id: string;
  level: HomeLevel;
  levelLabel: string;
  title: string;
  summary: string;
  meta: string;
  href: string;
  external: boolean;
  showAck?: boolean;
  /** 未指定時は運用の「直したよ」確認ボタン */
  ackSlot?: ReactNode;
  /** ホームで最初の1枚＝「いまやること」として目立たせる */
  focus?: boolean;
};

/** ホームピン1枚（リンク＋確認ボタン） */
export default function OpsPinCard({
  id,
  level,
  levelLabel,
  title,
  summary,
  meta,
  href,
  external,
  showAck,
  ackSlot,
  focus,
}: Props) {
  // カード引落は支払い重要度のため常に alert トーン
  const bannerTone =
    id === "ops_fix_notice" || id === "zaim_quality"
      ? "home-pin-banner-info"
      : id === "card_debit_watch"
        ? "home-pin-banner-alert"
        : level === "info"
          ? "home-pin-banner-info"
          : "home-pin-banner-alert";

  return (
    <div
      className={`card watch-card level-${level} home-pin-banner ${bannerTone}${
        focus ? " is-focus" : ""
      }`}
    >
      {focus ? (
        <span className="pb-ficon" aria-hidden>
          <Icon name={id === "card_debit_watch" ? "card" : id === "zaim_quality" ? "wallet" : "alert"} size={22} />
        </span>
      ) : null}
      <a
        href={href}
        className="home-pin-banner-link"
        {...(external
          ? { target: "_blank", rel: "noopener noreferrer" }
          : {})}
      >
        {focus ? <div className="pb-eyebrow">Now · いまやること</div> : null}
        <header>
          <span className="lvl">{levelLabel}</span>
          <strong>{title}</strong>
        </header>
        <p className="sum">{summary}</p>
        <p className="meta">{meta}</p>
      </a>
      {showAck ? (
        <div className="home-pin-banner-actions">
          {ackSlot ?? <OpsFixAckButton />}
        </div>
      ) : null}
    </div>
  );
}
