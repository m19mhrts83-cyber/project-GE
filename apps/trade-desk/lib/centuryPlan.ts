/** Numbers「キャッシュフロー」シート（100歳計画）のダンプ解釈。単位は万円。 */

export type DumpCell = string | number | null;
export type DumpGridRow = { r?: number | string; cells?: DumpCell[] };
export type SheetDump = {
  sheet_name: string;
  table_name: string;
  payload?: { grid?: DumpGridRow[] } | null;
};

export type SeriesKind = "plan" | "actual" | "unknown";

export type CenturyLine = {
  id: string;
  section: "income" | "expense" | "eval";
  group: string;
  label: string;
  series: SeriesKind;
  isTotal: boolean;
  values: Record<number, number | null>;
};

export type CenturyModel = {
  versionKey: string;
  asOf: string;
  label: string;
  years: number[];
  lines: CenturyLine[];
};

export type CenturyDiff = {
  year: number;
  label: string;
  before: number | null;
  after: number | null;
  delta: number | null;
};

function cellText(v: DumpCell | undefined): string {
  if (v == null) return "";
  return String(v).trim();
}

function parseYearToken(raw: string): number | null {
  const t = raw.trim();
  if (!t) return null;
  const m = t.match(/(20\d{2})/);
  if (m) {
    const y = Number(m[1]);
    if (y >= 2010 && y <= 2100) return y;
  }
  const n = Number(t.replace(/,/g, ""));
  if (Number.isFinite(n) && n >= 2010 && n <= 2100) return Math.round(n);
  return null;
}

function parseMan(raw: string): number | null {
  const t = raw.trim().replace(/,/g, "").replace(/円/g, "");
  if (!t || t === "ERR" || t === "missing value") return null;
  const n = Number(t);
  if (!Number.isFinite(n)) return null;
  return n;
}

function detectSeries(cells: string[]): SeriesKind | null {
  const head = cells.slice(0, 6).join(" ");
  if (!head) return null;
  if (head.includes("実績")) return "actual";
  if (head.includes("計画")) return "plan";
  return null;
}

function isHeaderRow(cells: string[]): boolean {
  const years = cells.filter((c) => parseYearToken(c) != null);
  return years.length >= 8 && detectSeries(cells) == null;
}

function itemLabel(cells: string[], section: CenturyLine["section"]): string {
  if (section === "eval") {
    return cells[0] || cells[1] || "評価";
  }
  if (section === "income") {
    return cells[1] || cells[0] || "収入";
  }
  return cells[3] || cells[2] || cells[1] || "支出";
}

function groupLabel(cells: string[], section: CenturyLine["section"]): string {
  if (section === "eval") return "収支評価";
  if (section === "income") return cells[0] || "生活収入";
  return (cells[2] || cells[1] || cells[0] || "生活支出").replace(/\s+/g, " ");
}

/** 表5の年ヘッダを正とし、空列は連続年で埋める。 */
export function yearMapFromDumps(dumps: SheetDump[]): Record<number, number> {
  const expense = dumps.find((d) => d.table_name.includes("表5"));
  const grid = expense?.payload?.grid ?? [];
  const header = grid.find((row) => isHeaderRow((row.cells ?? []).map(cellText)));
  const cells = (header?.cells ?? []).map(cellText);
  const found: { col: number; year: number }[] = [];
  cells.forEach((c, i) => {
    const y = parseYearToken(c);
    if (y != null) found.push({ col: i, year: y });
  });
  const map: Record<number, number> = {};
  if (!found.length) return map;
  found.sort((a, b) => a.col - b.col);
  const minCol = Math.min(...found.map((x) => x.col));
  const yearAtMin = found.find((x) => x.col === minCol)!.year;
  for (let col = Math.max(0, minCol - 4); col < cells.length; col++) {
    const y = yearAtMin + (col - minCol);
    if (y >= 2010 && y <= 2100) map[col] = y;
  }
  for (const f of found) map[f.col] = f.year;
  return map;
}

function parseTable(
  dump: SheetDump | undefined,
  section: CenturyLine["section"],
  colYears: Record<number, number>
): CenturyLine[] {
  if (!dump) return [];
  const lines: CenturyLine[] = [];
  const grid = dump.payload?.grid ?? [];
  for (const row of grid) {
    const cells = (row.cells ?? []).map(cellText);
    if (isHeaderRow(cells)) continue;
    const series = detectSeries(cells);
    if (!series) continue;
    const label = itemLabel(cells, section).replace(/\s+/g, " ").trim();
    const isTotal = /合計/.test(label) || cells.slice(0, 5).some((c) => c === "合計");
    const values: Record<number, number | null> = {};
    for (const [colStr, year] of Object.entries(colYears)) {
      const col = Number(colStr);
      const v = parseMan(cells[col] ?? "");
      values[year] = v;
    }
    const hasAny = Object.values(values).some((v) => v != null);
    if (!hasAny && !isTotal) continue;
    lines.push({
      id: `${section}-${row.r ?? lines.length}-${series}-${label}`,
      section,
      group: groupLabel(cells, section).replace(/\s+/g, " ").trim(),
      label,
      series,
      isTotal,
      values,
    });
  }
  return lines;
}

export function buildCenturyModel(
  dumps: SheetDump[],
  meta: { versionKey: string; asOf: string; label: string }
): CenturyModel {
  const colYears = yearMapFromDumps(dumps);
  const years = [...new Set(Object.values(colYears))].sort((a, b) => a - b);
  const income = parseTable(
    dumps.find((d) => d.table_name.includes("表4")),
    "income",
    colYears
  );
  const expense = parseTable(
    dumps.find((d) => d.table_name.includes("表5")),
    "expense",
    colYears
  );
  const evalLines = parseTable(
    dumps.find((d) => d.table_name.includes("表8")),
    "eval",
    colYears
  );
  return {
    versionKey: meta.versionKey,
    asOf: meta.asOf,
    label: meta.label,
    years,
    lines: [...income, ...expense, ...evalLines],
  };
}

export function evalTotalPlan(model: CenturyModel): CenturyLine | undefined {
  return model.lines.find(
    (l) =>
      l.section === "eval" &&
      l.series === "plan" &&
      (l.label.includes("合計") || l.label === "合計")
  );
}

export function evalHouseholdPlan(model: CenturyModel): CenturyLine | undefined {
  return model.lines.find(
    (l) =>
      l.section === "eval" &&
      l.series === "plan" &&
      l.label.includes("生活収入")
  );
}

export function diffEvalPlan(
  current: CenturyModel,
  previous: CenturyModel | null,
  years: number[]
): CenturyDiff[] {
  if (!previous) return [];
  const after = evalTotalPlan(current);
  const before = evalTotalPlan(previous);
  const afterH = evalHouseholdPlan(current);
  const beforeH = evalHouseholdPlan(previous);
  const out: CenturyDiff[] = [];
  for (const year of years) {
    const a = after?.values[year] ?? null;
    const b = before?.values[year] ?? null;
    if (a == null && b == null) continue;
    const delta = a != null && b != null ? a - b : null;
    out.push({
      year,
      label: "合計・計画（貯蓄可能額）",
      before: b,
      after: a,
      delta,
    });
  }
  if (afterH && beforeH) {
    for (const year of years) {
      const a = afterH.values[year] ?? null;
      const b = beforeH.values[year] ?? null;
      if (a == null && b == null) continue;
      const delta = a != null && b != null ? a - b : null;
      if (delta == null || Math.abs(delta) < 1) continue;
      out.push({
        year,
        label: "生活収支・計画",
        before: b,
        after: a,
        delta,
      });
    }
  }
  return out;
}

export function significantDiffs(diffs: CenturyDiff[], limit = 8): CenturyDiff[] {
  const totals = diffs.filter((d) => d.label.startsWith("合計"));
  return [...totals]
    .filter((d) => d.delta != null && Math.abs(d.delta) >= 5)
    .sort((a, b) => Math.abs(b.delta ?? 0) - Math.abs(a.delta ?? 0))
    .slice(0, limit);
}

export function defaultYearWindow(nowYear = new Date().getFullYear()): {
  start: number;
  end: number;
} {
  return { start: nowYear - 2, end: nowYear + 12 };
}

export function decadesFromYears(years: number[]): number[] {
  const set = new Set(years.map((y) => Math.floor(y / 10) * 10));
  return [...set].sort((a, b) => a - b);
}
