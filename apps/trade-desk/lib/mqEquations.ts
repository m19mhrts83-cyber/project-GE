/**
 * MQ会計（西研究所要素法）の企業方程式 — 単一ソース。
 * 金額は万円。PQ = VQ + F + G / MQ = PQ - VQ / G = MQ - F / M = P - V
 */

import { roundMan, roundManOrNull } from "./mqUnits";

export type MqInput = {
  pq: number;
  vq: number;
  f: number;
  /** 稼働戸月など。未入力なら単価は出さない */
  q: number | null;
};

/** 月次評価用: 月額F + 年額F÷12（結果は四捨五入して万円） */
export function monthlyAllocatedF(fMonthly: number, fAnnual: number): number {
  return roundMan((Number(fMonthly) || 0) + (Number(fAnnual) || 0) / 12);
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
  return roundMan(sumF + maxAnnual);
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

const EPS = 0.5; // 万円整数後の検算余裕

export function computeMq(input: MqInput): MqComputed {
  const pq = roundMan(input.pq);
  const vq = roundMan(input.vq);
  const f = roundMan(input.f);
  const mq = roundMan(pq - vq);
  const g = roundMan(mq - f);
  const qRaw = input.q;
  const q =
    qRaw != null && Number.isFinite(Number(qRaw)) && Number(qRaw) > 0
      ? Number(qRaw)
      : null;
  const p = q != null ? roundMan(pq / q) : null;
  const v = q != null ? roundMan(vq / q) : null;
  const m = p != null && v != null ? roundMan(p - v) : null;
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
  return {
    pq: roundMan(pq),
    vq: roundMan(vq),
    f: roundMan(f),
    q: qAny ? qSum : null,
  };
}

export function formatRatio(r: number | null): string {
  if (r == null || !Number.isFinite(r)) return "—";
  return `${(r * 100).toFixed(1)}%`;
}

export { roundManOrNull };
