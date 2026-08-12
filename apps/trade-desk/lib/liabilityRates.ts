/**
 * 負債金利・不動産正味利率の参考表示用。
 * 正本: config/liability_rates.yaml（リポ）→ apps/trade-desk/config/liability_rates.json
 * env: SONYLIFE_POLICY_LOAN_RATE_PCT 等で上書き可
 */
import fs from "fs";
import path from "path";

export type InsuranceLoanRate = {
  label?: string;
  rate_pct: number | null;
  rate_note?: string;
  source?: string;
};

export type RePropertyRate = {
  id: string;
  name: string;
  yield_pct?: number | null;
  mortgage_rate_pct?: number | null;
  net_rate_pct?: number | null;
};

type LiabilityRatesFile = {
  updated_at?: string;
  insurance_loans?: Record<string, InsuranceLoanRate>;
  real_estate?: {
    note?: string;
    properties?: RePropertyRate[];
  };
};

const ENV_RATE: Record<string, string> = {
  sony_life_policy_loan: "SONYLIFE_POLICY_LOAN_RATE_PCT",
  sony_life_chikage_policy_loan: "SONYLIFE_CHIKAGE_POLICY_LOAN_RATE_PCT",
  prudential_life_policy_loan: "PRUDENTIAL_POLICY_LOAN_RATE_PCT",
  prudential_life_chikage_policy_loan: "PRUDENTIAL_CHIKAGE_POLICY_LOAN_RATE_PCT",
};

function loadJson(): LiabilityRatesFile {
  const candidates = [
    path.join(process.cwd(), "config", "liability_rates.json"),
    path.join(process.cwd(), "config", "liability_rates.yaml"),
  ];
  for (const p of candidates) {
    try {
      if (!fs.existsSync(p)) continue;
      const raw = fs.readFileSync(p, "utf8");
      if (p.endsWith(".json")) {
        return JSON.parse(raw) as LiabilityRatesFile;
      }
    } catch {
      /* continue */
    }
  }
  return {};
}

function envPct(key: string): number | null {
  const raw = (process.env[key] || "").trim();
  if (!raw) return null;
  const n = Number(raw.replace(/%/g, ""));
  return Number.isFinite(n) ? n : null;
}

export function loadLiabilityRates(): {
  updated_at: string | null;
  insurance: Record<string, InsuranceLoanRate>;
  realEstateNote: string;
  realEstateProps: RePropertyRate[];
} {
  const data = loadJson();
  const insurance: Record<string, InsuranceLoanRate> = {
    ...(data.insurance_loans || {}),
  };
  for (const [aid, envKey] of Object.entries(ENV_RATE)) {
    const fromEnv = envPct(envKey);
    if (fromEnv == null) continue;
    insurance[aid] = {
      ...(insurance[aid] || {}),
      rate_pct: fromEnv,
      source: "env",
      rate_note: insurance[aid]?.rate_note,
    };
  }
  return {
    updated_at: data.updated_at || null,
    insurance,
    realEstateNote:
      data.real_estate?.note ||
      "物件利回り − ローン金利 ＝ 正味の利率イメージ（整備中）",
    realEstateProps: data.real_estate?.properties || [],
  };
}

export function fmtRatePct(rate: number | null | undefined): string {
  if (rate == null || !Number.isFinite(rate)) return "— 要確認";
  const t = Number.isInteger(rate) ? String(rate) : String(rate);
  return `${t}%`;
}
