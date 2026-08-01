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

export function summarizeUnits(units: PropertyUnit[]): OccupancySummary {
  const byProp = new Map<
    string,
    OccupancySummary["by_property"][number]
  >();
  const vacant_labels: string[] = [];
  let occupied = 0;
  for (const u of units) {
    const b = byProp.get(u.property_id) || {
      property_id: u.property_id,
      property_name: u.property_name,
      total: 0,
      occupied: 0,
      vacant: 0,
      vacant_rooms: [] as string[],
      rate_pct: 0,
    };
    b.total += 1;
    if (u.status === "vacant") {
      b.vacant += 1;
      b.vacant_rooms.push(u.room);
      vacant_labels.push(shortLabel(u));
    } else {
      b.occupied += 1;
      occupied += 1;
    }
    byProp.set(u.property_id, b);
  }
  const by_property = [...byProp.values()].map((b) => ({
    ...b,
    rate_pct: b.total ? Math.round((1000 * b.occupied) / b.total) / 10 : 0,
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
