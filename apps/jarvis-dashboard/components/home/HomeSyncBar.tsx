import { createClient } from "@/lib/supabase/server";
import { fmtSync } from "./homeHelpers";

/** ホーム上部の同期行＋凡例（軽量） */
export default async function HomeSyncBar() {
  const supabase = await createClient();
  const { data: meta } = await supabase.from("sync_meta").select("key,value");
  const metaMap = Object.fromEntries((meta || []).map((m) => [m.key, m.value]));
  const cloudAt =
    metaMap.gha_triage_pushed_at ||
    metaMap.gha_watch_pushed_at ||
    metaMap.gha_heartbeat_at;
  const macMorningAt = metaMap.mac_morning_refreshed_at;
  const macMorningOk = metaMap.mac_morning_refresh_ok;

  return (
    <>
      <p className="home-sync" aria-label="最終同期">
        <span>
          最終同期 cloud <strong>{fmtSync(cloudAt)}</strong>
        </span>
        <span className="home-sync-sep">·</span>
        <span>
          mac_morning <strong>{fmtSync(macMorningAt)}</strong>
          {macMorningAt && macMorningOk === "0" ? (
            <span className="home-sync-warn">（一部失敗）</span>
          ) : null}
        </span>
      </p>

      <p className="home-legend" aria-label="優先度の凡例">
        <span className="home-legend-item">
          <span className="home-legend-swatch attention" />
          要確認
        </span>
        <span className="home-legend-item">
          <span className="home-legend-swatch warn" />
          注意
        </span>
        <span className="home-legend-item">
          <span className="home-legend-swatch info" />
          参考
        </span>
      </p>
    </>
  );
}
