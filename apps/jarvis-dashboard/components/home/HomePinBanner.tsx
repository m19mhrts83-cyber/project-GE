import { LEVEL_LABEL } from "@/lib/homeLevels";
import { createClient } from "@/lib/supabase/server";

/** Cursor Pro Plus 戻し等、ホーム最上段のピン */
export default async function HomePinBanner() {
  const supabase = await createClient();
  const { data } = await supabase
    .from("watch_status")
    .select("*")
    .eq("id", "cursor_pro_plus_downgrade")
    .eq("status", "active")
    .maybeSingle();

  if (!data) return null;
  const pl =
    data.payload && typeof data.payload === "object"
      ? (data.payload as Record<string, unknown>)
      : {};
  const show =
    pl.show_banner === true || (data.level && data.level !== "ok");
  if (!show) return null;

  return (
    <a
      href="https://www.cursor.com/settings"
      className="card watch-card level-attention home-pin-banner"
      target="_blank"
      rel="noopener noreferrer"
    >
      <header>
        <span className="lvl">{LEVEL_LABEL.attention}</span>
        <strong>{data.title}</strong>
      </header>
      <p className="sum">{data.summary}</p>
      <p className="meta">
        期限 2026-08-24 · Cursor Settings で Schedule Downgrade · 状況ウォッチにも掲載
      </p>
    </a>
  );
}
