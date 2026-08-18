import { LEVEL_LABEL, HomeLevel } from "@/lib/homeLevels";
import { createClient } from "@/lib/supabase/server";
import {
  OPS_EPHEMERAL_IDS,
  opsWatchVisibleOnHome,
} from "@/lib/opsWatch";
import { zaimWatchVisibleOnHome } from "@/lib/zaimWatchPin";
import { KURASHIFT_URL } from "@/lib/nav";
import OpsPinCard from "@/components/OpsPinCard";
import ZaimReviewAckButton from "@/components/ZaimReviewAckButton";
import CardDebitAckButton from "@/components/CardDebitAckButton";

const PIN_IDS = [
  "card_debit_watch",
  "ops_fix_notice",
  "zaim_quality",
  "vercel_deploy",
  "gha_workflow_fail",
  "cursor_pro_plus_downgrade",
] as const;

function hrefFor(
  id: string,
  detail: string | null | undefined,
  payload: Record<string, unknown>
): {
  href: string;
  external: boolean;
} {
  if (id === "card_debit_watch") {
    const action =
      (typeof payload.action_url === "string" && payload.action_url) ||
      (typeof payload.href === "string" && payload.href.startsWith("http")
        ? payload.href
        : null) ||
      `${KURASHIFT_URL}/money-ops`;
    return { href: action, external: true };
  }
  if (id === "zaim_quality") return { href: "/zaim", external: false };
  if (id === "cursor_pro_plus_downgrade") {
    return { href: "https://www.cursor.com/settings", external: true };
  }
  if (detail && /^https?:\/\//.test(detail)) {
    return { href: detail, external: true };
  }
  return {
    href: `/situation?watch=${encodeURIComponent(id)}#watch-${encodeURIComponent(id)}`,
    external: false,
  };
}

function pinTitle(id: string, fallback: string): string {
  if (id === "card_debit_watch") return "Olive Infinite 引落 — 支払い準備";
  if (id === "zaim_quality") return "Jarvisが直したよ（財務）";
  return fallback || id;
}

/** ホーム最上段ピン（カード引落・運用お知らせ・財務直し 等） */
export default async function HomePinBanner() {
  const supabase = await createClient();
  const { data: rows } = await supabase
    .from("watch_status")
    .select("*")
    .eq("status", "active")
    .in("id", [...PIN_IDS]);

  const byId = new Map((rows || []).map((r) => [String(r.id), r]));
  const pins = PIN_IDS.map((id) => byId.get(id)).filter(Boolean) as Array<
    Record<string, unknown>
  >;

  const visible = pins.filter((data) => {
    const id = String(data.id);
    if ((OPS_EPHEMERAL_IDS as readonly string[]).includes(id)) {
      return opsWatchVisibleOnHome({
        id,
        level: data.level as string | null,
        payload: data.payload,
      });
    }
    const pl =
      data.payload && typeof data.payload === "object"
        ? (data.payload as Record<string, unknown>)
        : {};
    const level = String(data.level || "");
    if (id === "card_debit_watch") {
      return pl.show_banner === true;
    }
    if (id === "zaim_quality") {
      return zaimWatchVisibleOnHome(pl);
    }
    if (id === "cursor_pro_plus_downgrade") {
      return pl.show_banner === true || (level && level !== "ok");
    }
    return false;
  });

  if (!visible.length) return null;

  return (
    <>
      {visible.map((data) => {
        const id = String(data.id);
        const level = (
          ["attention", "warn", "info"].includes(String(data.level))
            ? data.level
            : "info"
        ) as HomeLevel;
        const pl =
          data.payload && typeof data.payload === "object"
            ? (data.payload as Record<string, unknown>)
            : {};
        const { href, external } = hrefFor(
          id,
          data.detail as string | null,
          pl
        );
        const batchId = String(pl.review_batch_id || "");
        const cardDue =
          typeof pl.due_date === "string"
            ? pl.due_date
            : pl.olive_infinite &&
                typeof pl.olive_infinite === "object" &&
                typeof (pl.olive_infinite as { due_date?: string }).due_date ===
                  "string"
              ? (pl.olive_infinite as { due_date: string }).due_date
              : "";
        const metaExtra =
          id === "card_debit_watch"
            ? "重要: 支払いを確実に · 処置は KURASHIFT 資金移動で · 「確認」はピン解除のみ（完了は money-ops done）"
            : id === "cursor_pro_plus_downgrade"
              ? "期限 2026-08-24 · Cursor Settings で Schedule Downgrade · 状況ウォッチにも掲載"
              : id === "ops_fix_notice"
                ? "Jarvis が直した内容 · 「確認しました」で消えます"
                : id === "zaim_quality"
                  ? "確認するまで残ります · 「確認した」で消えます · 詳細は /zaim"
                  : "運用監視 · 直ったらホームのお知らせに切り替わります";
        return (
          <OpsPinCard
            key={id}
            id={id}
            level={level}
            levelLabel={LEVEL_LABEL[level]}
            title={pinTitle(id, String(data.title || id))}
            summary={String(data.summary || "")}
            meta={metaExtra}
            href={href}
            external={external}
            showAck={
              id === "ops_fix_notice" ||
              id === "zaim_quality" ||
              id === "card_debit_watch"
            }
            ackSlot={
              id === "zaim_quality" ? (
                <ZaimReviewAckButton batchId={batchId} />
              ) : id === "card_debit_watch" ? (
                <CardDebitAckButton dueDate={cardDue} />
              ) : undefined
            }
          />
        );
      })}
    </>
  );
}
