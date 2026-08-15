import { createClient } from "@/lib/supabase/server";

export type MacWatchStatus = {
  online: boolean;
  stale: boolean;
  last_heartbeat_at: string | null;
  last_drain_at: string | null;
  age_sec: number | null;
  label: string;
};

/** Mac KeepAlive watch の心拍（sync_meta.kurashift_job_watch）。 */
export async function readMacWatchStatus(
  staleSec = 120
): Promise<MacWatchStatus> {
  const supabase = await createClient();
  const { data } = await supabase
    .from("sync_meta")
    .select("value, updated_at")
    .eq("key", "kurashift_job_watch")
    .maybeSingle();

  let value: Record<string, unknown> | null = null;
  if (typeof data?.value === "string" && data.value) {
    try {
      value = JSON.parse(data.value) as Record<string, unknown>;
    } catch {
      value = null;
    }
  } else if (data?.value && typeof data.value === "object") {
    value = data.value as Record<string, unknown>;
  }

  const hb =
    (typeof value?.last_heartbeat_at === "string" && value.last_heartbeat_at) ||
    (typeof data?.updated_at === "string" ? data.updated_at : null);

  if (!hb) {
    return {
      online: false,
      stale: true,
      last_heartbeat_at: null,
      last_drain_at: null,
      age_sec: null,
      label:
        "Mac 常駐: 心拍なし（launchd KeepAlive 未起動／初回ドレイン待ち）",
    };
  }
  const t = Date.parse(hb);
  const ageSec = Number.isFinite(t)
    ? Math.floor((Date.now() - t) / 1000)
    : null;
  const stale = ageSec == null || ageSec > staleSec;
  const drain =
    typeof value?.last_drain_at === "string" ? value.last_drain_at : null;
  return {
    online: !stale,
    stale,
    last_heartbeat_at: hb,
    last_drain_at: drain,
    age_sec: ageSec,
    label: stale
      ? `Mac 常駐オフライン（スリープ／未起動の可能性・最終心拍 ${hb}）`
      : `Mac 常駐オンライン（最終心拍 ${ageSec}s 前）`,
  };
}
