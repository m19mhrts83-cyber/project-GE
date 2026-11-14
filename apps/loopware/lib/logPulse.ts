/**
 * 判断ログに残った瞬間の演出（LogCelebration）へ知らせる合図。
 * 各画面は「記録できた（ok）」ときだけ logged() を呼ぶ。失敗・端末預かりでは呼ばない。
 */
export type PulseBead = "take" | "ng" | "hesitate" | "none" | "later" | "note";

export type Pulse = {
  /** 今回の判断で落ちる粒（1判断＝1粒。まとめて確定したときは複数） */
  beads: PulseBead[];
  /** 演出の下に出す短い言葉（例：「採用」「資料の判断」） */
  label?: string;
  /** 区切りの判断（案を確定した・全部決め終えた）。大きめに祝う */
  big?: boolean;
  /** 連続で判断する画面（判断デスク）用。中央の演出を出さず、右上の瓶だけ動かす */
  compact?: boolean;
};

export const PULSE_EVENT = "nody:logged";

/** 区切り（10件ごと）をまたいだか。またいだ区切りの数を返す（またいでいなければ 0） */
export function crossedMilestone(prev: number, next: number, step = 10): number {
  if (!(step > 0) || next <= prev) return 0;
  const m = Math.floor(next / step) * step;
  return m > prev && m <= next ? m : 0;
}

export function logged(p: Pulse): void {
  if (typeof window === "undefined" || !p.beads.length) return;
  window.dispatchEvent(new CustomEvent<Pulse>(PULSE_EVENT, { detail: p }));
}
