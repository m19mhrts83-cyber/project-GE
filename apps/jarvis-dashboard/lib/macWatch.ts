/**
 * Mac 見張りの判定（/api/mac-watch から使う純関数）。
 * 2026-11-28 松野さん承認: 瞬断での連投を避けるため、止まり判定を 15 分に緩め、
 * 2 回連続（pg_cron 5 分ごと）で止まりと判定された時だけ 🔴 を出す。復旧は 1 回で 🟢。
 */
export const STALE_MS = 15 * 60 * 1000;
export const OFFLINE_CONFIRM_COUNT = 2;

export type WatchState = "unknown" | "online" | "offline";

export function isStale(iso: string | null, now: number, staleMs = STALE_MS): boolean {
  if (!iso) return true;
  const t = Date.parse(iso);
  return !Number.isFinite(t) || now - t > staleMs;
}

export type Decision = {
  /** 保存する通知済みの状態（確定した状態だけ。疑い段階では前の状態のまま） */
  state: WatchState;
  /** 連続で止まりと判定された回数（online なら 0） */
  streak: number;
  /** 出す通知。null は出さない（初回の online は無言） */
  notify: "down" | "up" | null;
};

export function decide(before: WatchState, streak: number, stale: boolean, confirm = OFFLINE_CONFIRM_COUNT): Decision {
  if (!stale) {
    return { state: "online", streak: 0, notify: before === "offline" ? "up" : null };
  }
  const next = streak + 1;
  if (next >= confirm) {
    return { state: "offline", streak: next, notify: before === "offline" ? null : "down" };
  }
  return { state: before, streak: next, notify: null };
}
