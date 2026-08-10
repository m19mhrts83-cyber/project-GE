import { LEVEL_LABEL, HomeLevel } from "@/lib/homeLevels";
import { createClient } from "@/lib/supabase/server";

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
    const pl =
      data.payload && typeof data.payload === "object"
        ? (data.payload as Record<string, unknown>)
        : {};
    const level = String(data.level || "");
    if (pl.show_banner === true) return true;
    if (data.id === "ops_fix_notice") return level !== "ok";
    if (data.id === "vercel_deploy" || data.id === "gha_workflow_fail") {
      return level === "attention" || level === "warn";
    }
    if (data.id === "cursor_pro_plus_downgrade") {
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
              ? "Jarvis が直した内容 · 状況ウォッチにも掲載"
              : "運用監視 · 状況ウォッチにも掲載";
        return (
          <a
            key={id}
            href={href}
            className={`card watch-card level-${level} home-pin-banner`}
            {...(external
              ? { target: "_blank", rel: "noopener noreferrer" }
              : {})}
          >
            <header>
              <span className="lvl">{LEVEL_LABEL[level]}</span>
              <strong>{String(data.title || id)}</strong>
            </header>
            <p className="sum">{String(data.summary || "")}</p>
            <p className="meta">{metaExtra}</p>
          </a>
        );
      })}
    </>
  );
}
