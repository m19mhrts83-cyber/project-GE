/**
 * MQ会計（西研究所要素法）の企業方程式 — 単一ソース。
 * PQ = VQ + F + G / MQ = PQ - VQ / G = MQ - F / M = P - V
 */

export type MqInput = {
  pq: number;
  vq: number;
  f: number;
  /** 稼働戸月など。未入力なら単価は出さない */
  q: number | null;
};

/** 月次評価用: 月額F + 年額F÷12 */
export function monthlyAllocatedF(fMonthly: number, fAnnual: number): number {
  return (Number(fMonthly) || 0) + (Number(fAnnual) || 0) / 12;
}

/**
 * 年次に月次行を積み上げるとき、f_annual を12回足さない。
 * sum(f) + max(f_annual)（各月に同じ年額を書いた前提）
 */
export function yearlyFFromMonthlyRows(
  rows: { f: number; f_annual: number }[]
): number {
  let sumF = 0;
  let maxAnnual = 0;
  for (const r of rows) {
    sumF += Number(r.f) || 0;
    maxAnnual = Math.max(maxAnnual, Number(r.f_annual) || 0);
  }
  return sumF + maxAnnual;
}

export type MqComputed = {
  pq: number;
  vq: number;
  mq: number;
  f: number;
  g: number;
  q: number | null;
  p: number | null;
  v: number | null;
  m: number | null;
  mOverP: number | null;
  gOverPq: number | null;
  equationOk: boolean;
};

const EPS = 0.01;

export function computeMq(input: MqInput): MqComputed {
  const pq = Number(input.pq) || 0;
  const vq = Number(input.vq) || 0;
  const f = Number(input.f) || 0;
  const mq = pq - vq;
  const g = mq - f;
  const qRaw = input.q;
  const q =
    qRaw != null && Number.isFinite(Number(qRaw)) && Number(qRaw) > 0
      ? Number(qRaw)
      : null;
  const p = q != null ? pq / q : null;
  const v = q != null ? vq / q : null;
  const m = p != null && v != null ? p - v : null;
  const mOverP = pq !== 0 ? mq / pq : null;
  const gOverPq = pq !== 0 ? g / pq : null;
  const equationOk = Math.abs(pq - (vq + f + g)) < EPS;
  return { pq, vq, mq, f, g, q, p, v, m, mOverP, gOverPq, equationOk };
}

/** ローン元本などは G に入れない（cash_out のみ）。F に混ぜると粗利評価が歪む。 */
export function gainIgnoresPrincipalRepayment(
  base: MqInput,
  principalRepayment: number
): boolean {
  const g0 = computeMq(base).g;
  const g1 = computeMq({
    ...base,
    f: base.f + principalRepayment,
  }).g;
  // 元本を F に足すと G が減る → 禁止パターンを検知する用
  return Math.abs(g0 - g1) > EPS;
}

export function sumMqInputs(rows: MqInput[]): MqInput {
  let pq = 0;
  let vq = 0;
  let f = 0;
  let qSum = 0;
  let qAny = false;
  for (const r of rows) {
    pq += Number(r.pq) || 0;
    vq += Number(r.vq) || 0;
    f += Number(r.f) || 0;
    if (r.q != null && Number(r.q) > 0) {
      qSum += Number(r.q);
      qAny = true;
    }
  }
  return { pq, vq, f, q: qAny ? qSum : null };
}

export function formatRatio(r: number | null): string {
  if (r == null || !Number.isFinite(r)) return "—";
  return `${(r * 100).toFixed(1)}%`;
}
