/** Home / properties 用の入居率・物件ヘルパ */

export type PropertyUnit = {
  id: string;
  property_id: string;
  property_name: string;
  room: string;
  status: string;
  rent: number | null;
  note: string | null;
  source?: string | null;
  payload?: Record<string, unknown> | null;
  updated_at?: string | null;
};

export type OccupancyEvent = {
  id: number;
  occurred_on: string;
  event_type: string;
  property_id: string;
  property_name: string | null;
  room: string;
  source: string;
  ref: string | null;
  note: string | null;
};

export type PropertyRentBreakdown = {
  rent: number | null;
  management_fee: number | null;
  total_rent: number | null;
};

export type UnitMemoEntry = {
  at: string;
  text: string;
  source: "ui" | "jarvis" | "excel" | "mail" | string;
};

export type UnitRentPlan = {
  rent_year1: number | null;
  rent_year2: number | null;
  management_fee: number | null;
  total_year1: number | null;
  total_year2: number | null;
  discount_yen: number | null;
  discount_rate: number | null;
  plan_note: string | null;
  campaign_until: string | null;
  memo_log: UnitMemoEntry[];
};

/** Grandole I/II 用フロア格子（欠番 204/104 は空セル） */
export const FLOOR_MAP_LAYOUTS: Record<
  string,
  { floors: { floor: number; rooms: string[] }[] }
> = {
  "grandole-i": {
    floors: [
      { floor: 2, rooms: ["201", "202", "203", "204", "205"] },
      { floor: 1, rooms: ["101", "102", "103", "104", "105"] },
    ],
  },
  "grandole-ii": {
    floors: [
      { floor: 2, rooms: ["201", "202", "203", "204", "205"] },
      { floor: 1, rooms: ["101", "102", "103", "104", "105"] },
    ],
  },
};

export function hasFloorMap(propertyId: string): boolean {
  return propertyId in FLOOR_MAP_LAYOUTS;
}

export type OccupancySummary = {
  total: number;
  occupied: number;
  vacant: number;
  rate_pct: number;
  vacant_labels: string[];
  by_property: {
    property_id: string;
    property_name: string;
    total: number;
    occupied: number;
    vacant: number;
    vacant_rooms: string[];
    rate_pct: number;
    rent_sum: number;
    mgmt_sum: number;
    total_rent_sum: number;
  }[];
};

export function shortLabel(unit: PropertyUnit): string {
  const short =
    (unit.payload && typeof unit.payload.short === "string"
      ? unit.payload.short
      : null) ||
    (unit.property_id === "grandole-ii"
      ? "II"
      : unit.property_id === "grandole-i"
        ? "I"
        : unit.property_id === "caramel"
          ? "C"
          : unit.property_name);
  return `${short}-${unit.room}`;
}

export function unitRentBreakdown(unit: PropertyUnit): PropertyRentBreakdown {
  const rent = unit.rent != null ? Number(unit.rent) : null;
  const mgmtRaw = unit.payload?.management_fee;
  const management_fee =
    typeof mgmtRaw === "number"
      ? mgmtRaw
      : typeof mgmtRaw === "string" && mgmtRaw !== ""
        ? Number(mgmtRaw)
        : null;
  const totalRaw = unit.payload?.total_rent;
  let total_rent =
    typeof totalRaw === "number"
      ? totalRaw
      : typeof totalRaw === "string" && totalRaw !== ""
        ? Number(totalRaw)
        : null;
  if (total_rent == null && rent != null) {
    total_rent = rent + (management_fee != null && !Number.isNaN(management_fee) ? management_fee : 0);
  }
  return {
    rent: rent != null && !Number.isNaN(rent) ? rent : null,
    management_fee:
      management_fee != null && !Number.isNaN(management_fee)
        ? management_fee
        : null,
    total_rent: total_rent != null && !Number.isNaN(total_rent) ? total_rent : null,
  };
}

export function groupUnitsByProperty(units: PropertyUnit[]): {
  property_id: string;
  property_name: string;
  units: PropertyUnit[];
  rent_sum: number;
  mgmt_sum: number;
  total_rent_sum: number;
  occupied: number;
  vacant: number;
}[] {
  const order: string[] = [];
  const map = new Map<
    string,
    {
      property_id: string;
      property_name: string;
      units: PropertyUnit[];
      rent_sum: number;
      mgmt_sum: number;
      total_rent_sum: number;
      occupied: number;
      vacant: number;
    }
  >();
  for (const u of units) {
    let g = map.get(u.property_id);
    if (!g) {
      g = {
        property_id: u.property_id,
        property_name: u.property_name,
        units: [],
        rent_sum: 0,
        mgmt_sum: 0,
        total_rent_sum: 0,
        occupied: 0,
        vacant: 0,
      };
      map.set(u.property_id, g);
      order.push(u.property_id);
    }
    g.units.push(u);
    const b = unitRentBreakdown(u);
    if (b.rent != null) g.rent_sum += b.rent;
    if (b.management_fee != null) g.mgmt_sum += b.management_fee;
    if (b.total_rent != null) g.total_rent_sum += b.total_rent;
    if (u.status === "vacant") g.vacant += 1;
    else g.occupied += 1;
  }
  for (const g of map.values()) {
    g.units.sort((a, b) => a.room.localeCompare(b.room, "ja"));
  }
  return order.map((id) => map.get(id)!);
}

export function summarizeUnits(units: PropertyUnit[]): OccupancySummary {
  const groups = groupUnitsByProperty(units);
  const vacant_labels: string[] = [];
  let occupied = 0;
  for (const u of units) {
    if (u.status === "vacant") vacant_labels.push(shortLabel(u));
    else occupied += 1;
  }
  const by_property = groups.map((g) => ({
    property_id: g.property_id,
    property_name: g.property_name,
    total: g.units.length,
    occupied: g.occupied,
    vacant: g.vacant,
    vacant_rooms: g.units.filter((u) => u.status === "vacant").map((u) => u.room),
    rate_pct: g.units.length
      ? Math.round((1000 * g.occupied) / g.units.length) / 10
      : 0,
    rent_sum: g.rent_sum,
    mgmt_sum: g.mgmt_sum,
    total_rent_sum: g.total_rent_sum,
  }));
  const total = units.length;
  return {
    total,
    occupied,
    vacant: total - occupied,
    rate_pct: total ? Math.round((1000 * occupied) / total) / 10 : 0,
    vacant_labels,
    by_property,
  };
}

export function parseOccupancySummary(
  raw: string | undefined,
): OccupancySummary | null {
  if (!raw) return null;
  try {
    const j = JSON.parse(raw) as OccupancySummary;
    if (typeof j.rate_pct !== "number") return null;
    return j;
  } catch {
    return null;
  }
}

export function fmtYen(n: number | null | undefined): string {
  if (n == null) return "—";
  return `${Math.round(n).toLocaleString("ja-JP")}円`;
}

function numOrNull(v: unknown): number | null {
  if (typeof v === "number" && Number.isFinite(v)) return v;
  if (typeof v === "string" && v.trim() !== "") {
    const n = Number(v.replace(/,/g, ""));
    return Number.isFinite(n) ? n : null;
  }
  return null;
}

export function parseMemoLog(raw: unknown): UnitMemoEntry[] {
  if (!Array.isArray(raw)) return [];
  const out: UnitMemoEntry[] = [];
  for (const item of raw) {
    if (!item || typeof item !== "object") continue;
    const o = item as Record<string, unknown>;
    const text = typeof o.text === "string" ? o.text.trim() : "";
    if (!text) continue;
    const at =
      typeof o.at === "string" && o.at
        ? o.at
        : new Date().toISOString();
    const source =
      typeof o.source === "string" && o.source ? o.source : "excel";
    out.push({ at, text, source });
  }
  return out;
}

/** payload から 1年目／2年目計画とメモ履歴を取り出す */
export function unitRentPlan(unit: PropertyUnit): UnitRentPlan {
  const p = unit.payload || {};
  const current = unitRentBreakdown(unit);
  const mgmt =
    numOrNull(p.mgmt_fee) ??
    numOrNull(p.management_fee) ??
    current.management_fee;

  let rent_year2 = numOrNull(p.rent_year2);
  let rent_year1 = numOrNull(p.rent_year1);
  let total_year2 = numOrNull(p.total_year2);
  let total_year1 = numOrNull(p.total_year1);
  let discount_yen = numOrNull(p.discount_yen);

  if (rent_year2 == null) rent_year2 = current.rent;
  if (total_year2 == null) {
    if (rent_year2 != null) {
      total_year2 = rent_year2 + (mgmt != null ? mgmt : 0);
    } else {
      total_year2 = current.total_rent;
    }
  }
  if (rent_year1 == null && rent_year2 != null && discount_yen != null) {
    rent_year1 = rent_year2 - discount_yen;
  }
  if (total_year1 == null) {
    if (rent_year1 != null) {
      total_year1 = rent_year1 + (mgmt != null ? mgmt : 0);
    } else if (total_year2 != null && discount_yen != null) {
      total_year1 = total_year2 - discount_yen;
    }
  }
  if (discount_yen == null && total_year2 != null && total_year1 != null) {
    discount_yen = total_year2 - total_year1;
  } else if (discount_yen == null && rent_year2 != null && rent_year1 != null) {
    discount_yen = rent_year2 - rent_year1;
  }

  let discount_rate = numOrNull(p.discount_rate);
  if (
    discount_rate == null &&
    discount_yen != null &&
    total_year2 != null &&
    total_year2 > 0
  ) {
    discount_rate = Math.round((1000 * discount_yen) / total_year2) / 10;
  }

  const plan_note =
    typeof p.plan_note === "string" && p.plan_note.trim()
      ? p.plan_note.trim()
      : null;
  const campaign_until =
    typeof p.campaign_until === "string" && p.campaign_until.trim()
      ? p.campaign_until.trim()
      : null;

  return {
    rent_year1,
    rent_year2,
    management_fee: mgmt,
    total_year1,
    total_year2,
    discount_yen,
    discount_rate,
    plan_note,
    campaign_until,
    memo_log: parseMemoLog(p.memo_log),
  };
}

export function fmtDiscount(
  plan: Pick<UnitRentPlan, "discount_yen" | "discount_rate">,
): string {
  if (plan.discount_yen == null || plan.discount_yen <= 0) return "—";
  const rate =
    plan.discount_rate != null ? `（${plan.discount_rate}%）` : "";
  return `▲${Math.round(plan.discount_yen).toLocaleString("ja-JP")}円${rate}`;
}

/** 先月（JST・カレンダー月） YYYY-MM */
export function previousYmJst(now = new Date()): string {
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Tokyo",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).formatToParts(now);
  const y = Number(parts.find((p) => p.type === "year")?.value);
  const m = Number(parts.find((p) => p.type === "month")?.value);
  if (m === 1) return `${y - 1}-12`;
  return `${y}-${String(m - 1).padStart(2, "0")}`;
}
