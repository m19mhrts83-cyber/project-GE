/**
 * 運用上の実CF（定常）を年次系列にする。
 * 定義: 家賃(19.1) − ローン − 毎月経費（特別支出除外）／月
 */

import {
  composeReSteadyBoard,
  type ReTxn,
} from "@/lib/reSteadyCf";
import type { PropertyUnitRow } from "@/lib/roiAssets";

export type OpsCfYearPoint = {
  year: number;
  /** 月次定常CF。データ無しは null */
  steadyCfMonth: number | null;
  specialYtd: number;
  rentYtd: number;
};

export function buildOpsCfSeries(
  txnsByYear: Map<number, ReTxn[]>,
  unitRows: PropertyUnitRow[],
  years: number[],
  opts?: { currentYear?: number; throughMonthCurrent?: number }
): OpsCfYearPoint[] {
  const currentYear =
    opts?.currentYear ?? new Date().getFullYear();
  const throughCurrent = opts?.throughMonthCurrent ?? 12;

  return years.map((year) => {
    const txns = txnsByYear.get(year) || [];
    const through =
      year === currentYear ? Math.max(1, throughCurrent) : 12;
    const board = composeReSteadyBoard(txns, unitRows, year, through);
    return {
      year,
      steadyCfMonth:
        board.steadyCfMonth == null
          ? null
          : Math.round(board.steadyCfMonth),
      specialYtd: Math.round(board.specialYtd),
      rentYtd: Math.round(board.rentYtd),
    };
  });
}
