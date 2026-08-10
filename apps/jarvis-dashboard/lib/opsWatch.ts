/** Vercel / GHA / 「直したよ」— 問題時だけ出し、解決・確認で消す（アーカイブしない） */
export const OPS_EPHEMERAL_IDS = [
  "vercel_deploy",
  "gha_workflow_fail",
  "ops_fix_notice",
] as const;

export type OpsEphemeralId = (typeof OPS_EPHEMERAL_IDS)[number];

export function isOpsEphemeralId(id: string): id is OpsEphemeralId {
  return (OPS_EPHEMERAL_IDS as readonly string[]).includes(id);
}

type WatchLike = {
  id: string;
  level?: string | null;
  payload?: unknown;
};

/** ホーム／キュー／ピンに出すか（アーカイブではなく show_banner + level） */
export function opsWatchVisibleOnHome(w: WatchLike): boolean {
  if (!isOpsEphemeralId(String(w.id))) return false;
  const pl =
    w.payload && typeof w.payload === "object"
      ? (w.payload as Record<string, unknown>)
      : {};
  const level = String(w.level || "");
  if (w.id === "ops_fix_notice") {
    return pl.show_banner === true && level !== "ok";
  }
  // 失敗系: 要確認のときだけ。直したあとは level=ok で消える
  if (pl.show_banner === true) return true;
  return level === "attention" || level === "warn";
}

/** 状況ウォッチ詳細リストに載せるか（健全時は出さない） */
export function opsWatchVisibleOnSituation(w: WatchLike): boolean {
  return opsWatchVisibleOnHome(w);
}
