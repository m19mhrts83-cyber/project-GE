import fs from "fs";
import path from "path";

export type InsuranceFund = { name: string; pct: number };

export type InsuranceAccountAlloc = {
  label?: string;
  role?: string;
  monthly_yen?: number | null;
  funds?: InsuranceFund[];
  as_of?: string | null;
  source?: string | null;
  note?: string;
  value_jpy?: number;
};

export type InsuranceAllocations = {
  reference_account: string;
  advisor?: {
    name?: string;
    role?: string;
    policy?: string;
    related_accounts?: string[];
  };
  accounts: Record<string, InsuranceAccountAlloc>;
  snap_updated_at?: string | null;
};

const INSURANCE_ORDER = [
  "axa_life",
  "sony_life",
  "sony_life_chikage",
  "prudential_life",
  "prudential_life_chikage",
] as const;

function readJsonSafe(filePath: string): Record<string, unknown> | null {
  try {
    if (!fs.existsSync(filePath)) return null;
    return JSON.parse(fs.readFileSync(filePath, "utf8")) as Record<
      string,
      unknown
    >;
  } catch {
    return null;
  }
}

/** リポ正本 JSON + Mac snap（あれば）をマージ */
export function loadInsuranceAllocations(): InsuranceAllocations {
  const cwd = process.cwd();
  // apps/trade-desk 単体デプロイ／モノレポ両対応
  const roots = [
    cwd,
    path.resolve(cwd, "../.."),
    path.resolve(cwd, "../../.."),
  ];
  let base: InsuranceAllocations = {
    reference_account: "axa_life",
    accounts: {},
  };
  for (const root of roots) {
    const candidates = [
      path.join(root, "config/insurance_allocations.json"),
      path.join(root, "apps/trade-desk/config/insurance_allocations.json"),
    ];
    for (const c of candidates) {
      const cfg = readJsonSafe(c);
      if (cfg && cfg.accounts) {
        base = cfg as unknown as InsuranceAllocations;
        break;
      }
    }
    if (Object.keys(base.accounts).length) break;
  }

  let snap: {
    accounts?: Record<string, InsuranceAccountAlloc>;
    updated_at?: string;
  } | null = null;
  for (const root of roots) {
    const candidates = [
      path.join(root, ".jarvis_state/insurance_allocations_snap.json"),
      path.join(root, "../../.jarvis_state/insurance_allocations_snap.json"),
    ];
    for (const c of candidates) {
      const parsed = readJsonSafe(c);
      if (parsed && parsed.accounts) {
        snap = parsed as {
          accounts?: Record<string, InsuranceAccountAlloc>;
          updated_at?: string;
        };
        break;
      }
    }
    if (snap?.accounts) break;
  }

  const accounts: Record<string, InsuranceAccountAlloc> = {
    ...(base.accounts || {}),
  };
  if (snap?.accounts) {
    for (const [id, rec] of Object.entries(snap.accounts)) {
      const cur = { ...(accounts[id] || {}) };
      if (rec.funds && rec.funds.length) {
        cur.funds = rec.funds;
        cur.as_of = rec.as_of ?? cur.as_of;
        cur.source = rec.source || "web";
      }
      if (rec.monthly_yen != null) cur.monthly_yen = rec.monthly_yen;
      if (rec.value_jpy != null) cur.value_jpy = rec.value_jpy;
      accounts[id] = cur;
    }
  }

  return {
    reference_account: base.reference_account || "axa_life",
    advisor: base.advisor,
    accounts,
    snap_updated_at: snap?.updated_at ?? null,
  };
}

export function fundSummary(funds?: InsuranceFund[] | null): string {
  if (!funds?.length) return "—";
  return funds.map((f) => `${f.name} ${Number(f.pct)}%`).join(" / ");
}

export function compareToReference(
  refFunds: InsuranceFund[] | undefined,
  otherFunds: InsuranceFund[] | undefined,
  isReference: boolean
): string {
  if (isReference) return "参考（正）";
  if (!refFunds?.length) return "基準未取得";
  if (!otherFunds?.length) return "未取得";
  const refMap = Object.fromEntries(
    refFunds.map((f) => [f.name.trim(), Number(f.pct)])
  );
  const othMap = Object.fromEntries(
    otherFunds.map((f) => [f.name.trim(), Number(f.pct)])
  );
  const keys = new Set([...Object.keys(refMap), ...Object.keys(othMap)]);
  let maxD = 0;
  for (const k of keys) {
    maxD = Math.max(maxD, Math.abs((refMap[k] || 0) - (othMap[k] || 0)));
  }
  if (maxD <= 0.01) return "一致";
  if (maxD <= 1) return "ほぼ一致";
  return `ずれ(最大${Math.round(maxD)}pt)`;
}

export { INSURANCE_ORDER };
