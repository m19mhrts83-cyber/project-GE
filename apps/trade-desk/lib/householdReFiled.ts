/**
 * 家計B/Sの確定申告ベース家賃収入。
 * 正本: config/kurashift_tax_year_metrics.yaml → kurashift_tax_year_metrics
 * 詳細: docs/KURASHIFT_家計BS_不動産フロー.md
 */
import fs from "fs";
import path from "path";
import { yen, type TaxYearMetricRow } from "@/lib/taxInsights";

export type HouseholdFiledRe = {
  personalRevenueJpy: number | null;
  personalSource: string | null;
  corporateRevenueJpy: number | null;
  corporateSource: string | null;
  useFiledInTotals: boolean;
};

export function householdFiledReFromMetrics(
  metrics: TaxYearMetricRow[] | undefined,
  year: number
): HouseholdFiledRe {
  const rows = metrics ?? [];
  const personal = rows.find(
    (m) => m.scope === "personal" && Number(m.fiscal_year) === year
  );
  const corporate = rows.find(
    (m) => m.scope === "corporate" && Number(m.fiscal_year) === year
  );
  const personalRev =
    personal && (personal.filing_status || "").toLowerCase() === "filed"
      ? yen(personal.payload?.re_revenue_jpy)
      : null;
  const corpRev =
    corporate && (corporate.filing_status || "").toLowerCase() === "filed"
      ? yen(corporate.revenue_jpy)
      : null;
  const personalSource =
    typeof personal?.payload?.source_pdf === "string"
      ? personal.payload.source_pdf
      : null;
  const corporateSource =
    typeof corporate?.payload?.source_pdf === "string"
      ? corporate.payload.source_pdf
      : corporate?.note ?? null;

  return {
    personalRevenueJpy: personalRev,
    personalSource,
    corporateRevenueJpy: corpRev,
    corporateSource,
    useFiledInTotals: personalRev != null && personalRev > 0,
  };
}

export function loadTaxYearMetricsFromCatalog(): TaxYearMetricRow[] {
  const candidates = [
    path.join(process.cwd(), "..", "..", "config", "kurashift_tax_year_metrics.yaml"),
    path.join(process.cwd(), "config", "kurashift_tax_year_metrics.yaml"),
  ];
  for (const p of candidates) {
    try {
      if (!fs.existsSync(p)) continue;
      const { parse } = require("yaml") as typeof import("yaml");
      const data = parse(fs.readFileSync(p, "utf8")) as {
        personal?: Record<string, unknown>[];
        corporate?: Record<string, unknown>[];
      };
      const out: TaxYearMetricRow[] = [];
      for (const item of data.personal ?? []) {
        out.push({
          scope: "personal",
          fiscal_year: Number(item.fiscal_year),
          filing_status: String(item.filing_status ?? "filed"),
          filed_on: (item.filed_on as string) ?? null,
          note: (item.note as string) ?? null,
          source: "catalog",
          taxable_income_jpy: (item.taxable_income_jpy as number) ?? null,
          income_tax_jpy: (item.income_tax_jpy as number) ?? null,
          refund_or_pay: (item.refund_or_pay as string) ?? null,
          revenue_jpy: null,
          ordinary_income_jpy: null,
          corporate_tax_jpy: null,
          tax_payable_jpy: null,
          payload: (item.payload as TaxYearMetricRow["payload"]) ?? null,
        });
      }
      for (const item of data.corporate ?? []) {
        out.push({
          scope: "corporate",
          fiscal_year: Number(item.fiscal_year),
          filing_status: String(item.filing_status ?? "filed"),
          filed_on: (item.filed_on as string) ?? null,
          note: (item.note as string) ?? null,
          source: "catalog",
          taxable_income_jpy: null,
          income_tax_jpy: null,
          refund_or_pay: null,
          revenue_jpy: (item.revenue_jpy as number) ?? null,
          ordinary_income_jpy: (item.ordinary_income_jpy as number) ?? null,
          corporate_tax_jpy: (item.corporate_tax_jpy as number) ?? null,
          tax_payable_jpy: (item.tax_payable_jpy as number) ?? null,
          payload: (item.payload as TaxYearMetricRow["payload"]) ?? null,
        });
      }
      return out;
    } catch {
      /* try next */
    }
  }
  return [];
}
