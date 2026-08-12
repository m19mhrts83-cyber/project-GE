"use client";

import type { ReactNode } from "react";
import type { HomeLevel } from "@/lib/homeLevels";
import OpsFixAckButton from "@/components/OpsFixAckButton";

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
}: Props) {
  const tone =
    id === "ops_fix_notice" || id === "zaim_quality" || level === "info"
      ? "home-pin-banner-info"
      : "home-pin-banner-alert";

  return (
    <div className={`card watch-card level-${level} home-pin-banner ${tone}`}>
      <a
        href={href}
        className="home-pin-banner-link"
        {...(external
          ? { target: "_blank", rel: "noopener noreferrer" }
          : {})}
      >
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
