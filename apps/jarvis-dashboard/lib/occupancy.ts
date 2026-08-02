/** Home / properties 用の満室・物件ヘルパ */

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
