import { LEVEL_LABEL, HomeLevel } from "@/lib/homeLevels";
import { createClient } from "@/lib/supabase/server";
import {
  OPS_EPHEMERAL_IDS,
  opsWatchVisibleOnHome,
} from "@/lib/opsWatch";
import OpsPinCard from "@/components/OpsPinCard";

const PIN_IDS = [
  "ops_fix_notice",
  "vercel_deploy",
  "gha_workflow_fail",
  "cursor_pro_plus_downgrade",
] as const;

function hrefFor(id: string, detail: string | null | undefined): {
  href: string;
  external: boolean;
} {
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

/** ホーム最上段ピン（運用お知らせ・Vercel Fail・Cursor 戻し 等） */
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
        const { href, external } = hrefFor(id, data.detail as string | null);
        const metaExtra =
          id === "cursor_pro_plus_downgrade"
            ? "期限 2026-08-24 · Cursor Settings で Schedule Downgrade · 状況ウォッチにも掲載"
            : id === "ops_fix_notice"
              ? "Jarvis が直した内容 · 「確認しました」で消えます"
              : "運用監視 · 直ったらホームのお知らせに切り替わります";
        return (
          <OpsPinCard
            key={id}
            id={id}
            level={level}
            levelLabel={LEVEL_LABEL[level]}
            title={String(data.title || id)}
            summary={String(data.summary || "")}
            meta={metaExtra}
            href={href}
            external={external}
            showAck={id === "ops_fix_notice"}
          />
        );
      })}
    </>
  );
}
