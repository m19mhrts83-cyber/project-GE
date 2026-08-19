/**
 * MQ/Zaim ↔ 申告 科目ブリッジ（Phase F）
 * 正本: config/mq_tax_category_bridge.yaml
 */

import fs from "fs";
import path from "path";
import type { MqComputed } from "./mqEquations";
import type { MqTaxCompareRow } from "./mqTaxCompare";
import type { TaxYearMetricRow } from "./taxInsights";
import { yen } from "./taxInsights";
import { yenToMan } from "./mqUnits";

export type BridgeDef = {
  id: string;
  label: string;
  mq_element: string;
  tax_payload_key: string;
  hint?: string;
  emphasize?: boolean;
};

type BridgeConfig = { bridges: BridgeDef[] };

export function loadMqTaxCategoryBridge(): BridgeConfig {
  const candidates = [
    path.join(process.cwd(), "..", "..", "config", "mq_tax_category_bridge.yaml"),
    path.join(process.cwd(), "config", "mq_tax_category_bridge.yaml"),
    path.join(process.cwd(), "config", "mq_tax_category_bridge.json"),
  ];
  for (const p of candidates) {
    try {
      if (!fs.existsSync(p)) continue;
      const raw = fs.readFileSync(p, "utf8");
      if (p.endsWith(".yaml") || p.endsWith(".yml")) {
        // eslint-disable-next-line @typescript-eslint/no-require-imports
        const { parse } = require("yaml") as typeof import("yaml");
        return parse(raw) as BridgeConfig;
      }
      return JSON.parse(raw) as BridgeConfig;
    } catch {
      /* next */
    }
  }
  return { bridges: [] };
}

function mqValue(
  element: string,
  computed: MqComputed | null,
  depreciationMan: number | null
): number | null {
  if (!computed && depreciationMan == null) return null;
  switch (element) {
    case "pq":
      return computed?.pq ?? null;
    case "g":
      return computed?.g ?? null;
    case "depreciation":
      return depreciationMan;
    case "f_interest":
      return null;
    default:
      return null;
  }
}

function filedFromPayload(
  metric: TaxYearMetricRow | undefined,
  key: string
): number | null {
  if (!metric?.payload) return null;
  const v = (metric.payload as Record<string, unknown>)[key];
  if (v == null) return null;
  return yen(v as string | number);
}

export function buildCategoryRows(args: {
  computed: MqComputed | null;
  depreciationMan: number | null;
  metric: TaxYearMetricRow | undefined;
  limit?: number;
}): MqTaxCompareRow[] {
  const cfg = loadMqTaxCategoryBridge();
  const out: MqTaxCompareRow[] = [];

  for (const b of cfg.bridges) {
    const mqMan = mqValue(b.mq_element, args.computed, args.depreciationMan);
    const filedYen = filedFromPayload(args.metric, b.tax_payload_key);
    const filedMan = filedYen != null ? yenToMan(filedYen) : null;
    const diffMan =
      mqMan != null && filedMan != null ? mqMan - filedMan : null;
    if (mqMan == null && filedMan == null) continue;
    out.push({
      id: b.id,
      label: b.label,
      mqMan,
      filedMan,
      diffMan,
      hint: b.hint,
      emphasize: b.emphasize,
    });
  }

  const sorted = [...out].sort((a, b) => {
    const da = Math.abs(a.diffMan ?? 0);
    const db = Math.abs(b.diffMan ?? 0);
    return db - da;
  });

  return sorted.slice(0, args.limit ?? 3);
}
