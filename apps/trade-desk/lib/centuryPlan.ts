/** Numbers「キャッシュフロー」シート（生涯CF）のダンプ解釈。単位は万円。 */

export const CENTURY_NAV_LABEL = "生涯CF";
export const CENTURY_PAGE_TITLE = "生涯キャッシュフロー";

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
  const blob = `${cells[2] || ""} ${cells[3] || ""} ${cells[1] || ""}`;
  if (/合計/.test(blob) || cells.slice(0, 5).some((c) => c === "合計")) return "合計";
  if (/マンシ/.test(blob)) return "マンション（19）";
  if (/予測生活費|変動費|使途不明/.test(blob)) return "変動費（生活）";
  if (/自動車|家電等/.test(blob)) return "自動車・家電（20）";
  if (/結婚・教育|学資/.test(blob)) return "教育・進学";
  if (/住宅ローン|頭金\/固定/.test(blob)) return "住居（ローン・維持）";
  if (/生命保険|火災保険/.test(blob)) return "保険";
  if (/旅行|帰省/.test(blob)) return "旅行・帰省";
  if (/財形|定期預金|インデックス|奨学金|会社費用/.test(blob)) {
    return "貯蓄・投資・返済";
  }
  if (/イベント|家計固定/.test(blob)) return "家計固定費・イベント";
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

export type LifeEventKind = "family" | "child" | "maint";

export type PersonAges = {
  name: string;
  ages: Record<number, number>;
};

export type LifeEventMark = {
  year: number;
  kind: LifeEventKind;
  source: string;
  person: string;
  text: string;
  planLabels: string[];
  planHint: string;
};

export type EventTrack = {
  person: string;
  hint: string;
  planLabels: string[];
  byYear: Record<number, string[]>;
};

export type CenturyMilestone = {
  key: "actuals" | "peak" | "age100";
  year: number;
  age: number | null;
  title: string;
  detail: string;
  value: number | null;
};

export type LifeEventModel = {
  years: number[];
  people: PersonAges[];
  marks: LifeEventMark[];
};

export type LifeplanNote = {
  kind: "check" | "history";
  item: string;
  category: string;
  date: string;
  body: string;
  result: string;
};

export type LineDelta = {
  year: number;
  before: number | null;
  after: number | null;
  delta: number | null;
};

const PEOPLE_NAMES = ["真治", "千景", "円香", "珠己", "紗和"];

function yearMapFromGrid(grid: DumpGridRow[]): Record<number, number> {
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
  const minCol = found[0].col;
  const yearAtMin = found[0].year;
  for (let col = minCol; col < cells.length; col++) {
    const y = yearAtMin + (col - minCol);
    if (y >= 2010 && y <= 2100) map[col] = y;
  }
  for (const f of found) map[f.col] = f.year;
  return map;
}

function parseAgeToken(raw: string): number | null {
  const t = raw.trim();
  if (!t) return null;
  const m = t.match(/^(\d+(?:\.\d+)?)歳?$/);
  if (!m) return null;
  const n = Number(m[1]);
  if (!Number.isFinite(n) || n < 0 || n > 120) return null;
  return Math.round(n);
}

function eventKind(label: string): LifeEventKind {
  if (label.includes("メンテナンス") || label.includes("メンテ")) return "maint";
  if (/円香|珠己|紗和/.test(label)) return "child";
  return "family";
}

function formatEventText(raw: string, kind: LifeEventKind): string {
  const t = raw.trim().replace(/\.0$/, "");
  if (!t || t === "missing value") return "";
  if (kind === "maint") {
    const n = Number(t.replace(/,/g, ""));
    if (Number.isFinite(n) && n > 0 && n < 1000) return `${n}万`;
  }
  return t;
}

function eventPerson(source: string): string {
  if (source.includes("メンテナンス") || source.includes("メンテ")) return "家";
  if (source.includes("家族")) return "家族";
  for (const n of PEOPLE_NAMES) {
    if (source.includes(n)) return n;
  }
  return source.replace(/イベント$/, "") || "家族";
}

export function linkEventToPlan(
  text: string,
  source: string,
  person: string
): { planLabels: string[]; planHint: string } {
  if (/^車/.test(text) || text === "家電") {
    return {
      planLabels: ["自動車/家電等"],
      planHint: "この年の支出「自動車/家電等」（表1の20）",
    };
  }
  if (text === "住宅新築") {
    return {
      planLabels: ["住宅ローン", "頭金/固定/維持費"],
      planHint: "住宅取得（ローン・頭金）",
    };
  }
  const who =
    ["円香", "珠己", "紗和"].find(
      (n) => person === n || source.includes(n) || text.includes(n)
    ) ?? "";
  if (who && /幼稚園|小学校|中学校|高校|大学|社会人|誕生/.test(text)) {
    return {
      planLabels: [`結婚・教育（${who}）`, `${who}学資等`],
      planHint: `${who}の進学・教育費`,
    };
  }
  if (source.includes("メンテナンス") || source.includes("メンテ")) {
    const item = source.replace(/^家メンテナンス：/, "");
    return {
      planLabels: ["頭金/固定/維持費"],
      planHint: `家のメンテナンス（${item}）`,
    };
  }
  return { planLabels: [], planHint: "" };
}

/** Numbers キャッシュフロー上部「表3.ライフイベント」。 */
export function parseLifeEvents(dumps: SheetDump[]): LifeEventModel | null {
  const dump = dumps.find((d) => d.table_name.includes("表3") || d.table_name.includes("ライフイベント"));
  if (!dump) return null;
  const grid = dump.payload?.grid ?? [];
  const colYears = yearMapFromGrid(grid);
  const years = [...new Set(Object.values(colYears))].sort((a, b) => a - b);
  if (!years.length) return null;
  const people: PersonAges[] = [];
  const marks: LifeEventMark[] = [];
  for (const row of grid) {
    const cells = (row.cells ?? []).map(cellText);
    if (isHeaderRow(cells)) continue;
    const name = (cells[0] || "").replace(/\s+/g, "");
    if (!name) continue;
    if (PEOPLE_NAMES.includes(name)) {
      const ages: Record<number, number> = {};
      for (const [colStr, year] of Object.entries(colYears)) {
        const age = parseAgeToken(cells[Number(colStr)] ?? "");
        if (age != null) ages[year] = age;
      }
      people.push({ name, ages });
      continue;
    }
    const kind = eventKind(name);
    const person = eventPerson(name);
    for (const [colStr, year] of Object.entries(colYears)) {
      const text = formatEventText(cells[Number(colStr)] ?? "", kind);
      if (!text || text === "新築") continue;
      const link = linkEventToPlan(text, name, person);
      marks.push({
        year,
        kind,
        source: name,
        person,
        text,
        planLabels: link.planLabels,
        planHint: link.planHint,
      });
    }
  }
  return { years, people, marks };
}

export function shinjiHorizon(
  events: LifeEventModel | null,
  nowYear = new Date().getFullYear()
): {
  nowAge: number | null;
  age100Year: number | null;
  startYear: number | null;
  endYear: number | null;
} {
  const shinji = events?.people.find((p) => p.name === "真治");
  const ages = shinji?.ages ?? {};
  const years = Object.keys(ages).map(Number).sort((a, b) => a - b);
  let age100Year: number | null = null;
  for (const y of years) {
    if (ages[y] === 100) age100Year = y;
  }
  return {
    nowAge: ages[nowYear] ?? null,
    age100Year,
    startYear: years[0] ?? null,
    endYear: years[years.length - 1] ?? age100Year,
  };
}

export function eventsForYear(events: LifeEventModel | null, year: number): LifeEventMark[] {
  if (!events) return [];
  return events.marks.filter((m) => m.year === year);
}

function noteDate(raw: string): string {
  const m = raw.match(/(20\d{2})年\s*(\d{1,2})月\s*(\d{1,2})日/);
  if (m) {
    return `${m[1]}-${m[2].padStart(2, "0")}-${m[3].padStart(2, "0")}`;
  }
  const y = raw.match(/(20\d{2})/);
  return y ? y[1] : raw.replace(/\s.*/, "").trim();
}

function parseNoteTable(
  dump: SheetDump | undefined,
  kind: LifeplanNote["kind"]
): LifeplanNote[] {
  if (!dump) return [];
  const grid = dump.payload?.grid ?? [];
  const out: LifeplanNote[] = [];
  for (const row of grid) {
    const cells = (row.cells ?? []).map(cellText);
    if (!cells.length) continue;
    const head = cells.join("");
    if (head.includes("項目") && (head.includes("確認") || head.includes("変更"))) continue;
    const item = cells[0] || "";
    const category = cells[1] || "";
    const date = noteDate(cells[2] || "");
    const body = (cells[3] || "").trim();
    const result = String((kind === "check" ? cells[4] : cells[5]) || "").trim();
    if (!item && !body) continue;
    out.push({ kind, item, category, date, body, result });
  }
  return out;
}

/** Numbers「要確認事項」「主要変更履歴」。閲覧専用。 */
export function parseLifeplanNotes(dumps: SheetDump[]): LifeplanNote[] {
  const checks = parseNoteTable(
    dumps.find((d) => d.table_name.includes("要確認") || d.sheet_name.includes("要確認")),
    "check"
  );
  const hist = parseNoteTable(
    dumps.find((d) => d.table_name.includes("変更履歴") || d.sheet_name.includes("変更履歴")),
    "history"
  );
  return [...checks, ...hist];
}

export function notesForLine(notes: LifeplanNote[], line: CenturyLine): LifeplanNote[] {
  const hay = `${line.label} ${line.group}`.replace(/\s+/g, "");
  return notes.filter((n) => {
    const item = (n.item || "").replace(/\s+/g, "");
    if (!item) return false;
    if (hay.includes(item) || item.includes(hay.slice(0, 8))) return true;
    const code = item.match(/0\.\d+/);
    if (code && hay.includes(code[0])) return true;
    const key = item.replace(/[0-9.／/]/g, "");
    return key.length >= 2 && hay.includes(key);
  });
}

export function planDeltasForLine(
  current: CenturyLine,
  previous: CenturyModel | null
): Record<number, LineDelta> {
  if (!previous || current.series !== "plan") return {};
  const ov = previous.lines.find(
    (l) =>
      l.section === current.section &&
      l.series === "plan" &&
      l.label === current.label
  );
  if (!ov) return {};
  const out: Record<number, LineDelta> = {};
  const years = new Set(
    [...Object.keys(current.values), ...Object.keys(ov.values)].map(Number)
  );
  for (const year of years) {
    const after = current.values[year] ?? null;
    const before = ov.values[year] ?? null;
    if (after == null && before == null) continue;
    const delta = after != null && before != null ? after - before : null;
    if (delta == null || Math.abs(delta) < 1) continue;
    out[year] = { year, before, after, delta };
  }
  return out;
}

export function yearsWithActuals(model: CenturyModel): number[] {
  const set = new Set<number>();
  for (const line of model.lines) {
    if (line.series !== "actual") continue;
    for (const [y, v] of Object.entries(line.values)) {
      if (v != null) set.add(Number(y));
    }
  }
  return [...set].sort((a, b) => a - b);
}

export function shinjiAgeInYear(
  events: LifeEventModel | null,
  year: number
): number | null {
  const ages = events?.people.find((p) => p.name === "真治")?.ages ?? {};
  if (ages[year] != null) return ages[year];
  const known = Object.keys(ages)
    .map(Number)
    .sort((a, b) => a - b);
  if (!known.length) return null;
  const base = known[0];
  return ages[base] + (year - base);
}

export function centuryMilestones(
  model: CenturyModel,
  events: LifeEventModel | null
): CenturyMilestone[] {
  const actualYears = yearsWithActuals(model);
  const total = evalTotalPlan(model);
  let peakYear: number | null = null;
  let peakVal = -Infinity;
  for (const y of model.years) {
    const v = total?.values[y];
    if (v != null && v > peakVal) {
      peakVal = v;
      peakYear = y;
    }
  }
  const horizon = shinjiHorizon(events);
  const items: CenturyMilestone[] = [];
  if (actualYears[0] != null) {
    items.push({
      key: "actuals",
      year: actualYears[0],
      age: shinjiAgeInYear(events, actualYears[0]),
      title: "実績の開始",
      detail: "実績が載っている最初の年",
      value: null,
    });
  }
  if (peakYear != null) {
    items.push({
      key: "peak",
      year: peakYear,
      age: shinjiAgeInYear(events, peakYear),
      title: "ピーク",
      detail: "合計・計画の貯蓄可能額が最大の年",
      value: peakVal,
    });
  }
  if (horizon.age100Year != null) {
    items.push({
      key: "age100",
      year: horizon.age100Year,
      age: 100,
      title: "100歳",
      detail: "真治が100歳になる年",
      value: null,
    });
  }
  return items;
}

const EVENT_TRACK_ORDER = ["家族", "真治", "千景", "円香", "珠己", "紗和", "家"];

export function eventTracks(events: LifeEventModel | null): EventTrack[] {
  if (!events) return [];
  const map = new Map<string, EventTrack>();
  for (const mark of events.marks) {
    let track = map.get(mark.person);
    if (!track) {
      track = { person: mark.person, hint: "", planLabels: [], byYear: {} };
      map.set(mark.person, track);
    }
    const list = track.byYear[mark.year] ?? [];
    if (!list.includes(mark.text)) list.push(mark.text);
    track.byYear[mark.year] = list;
    for (const lab of mark.planLabels) {
      if (!track.planLabels.includes(lab)) track.planLabels.push(lab);
    }
    if (mark.planHint && !track.hint.includes(mark.planHint)) {
      track.hint = track.hint ? `${track.hint}／${mark.planHint}` : mark.planHint;
    }
  }
  return EVENT_TRACK_ORDER.map((p) => map.get(p)).filter(
    (t): t is EventTrack => t != null
  );
}

export function lineLinkedAtYear(
  line: CenturyLine,
  events: LifeEventModel | null,
  year: number
): boolean {
  if (!events || line.section !== "expense") return false;
  return events.marks.some(
    (m) =>
      m.year === year &&
      m.planLabels.some(
        (lab) => line.label.includes(lab) || lab.includes(line.label)
      )
  );
}

export function lifeExpenseGaps(model: CenturyModel): string[] {
  const hay = model.lines
    .filter((l) => l.section === "expense")
    .map((l) => `${l.group} ${l.label}`)
    .join(" ");
  const gaps: string[] = [];
  if (!/マンシ/.test(hay)) {
    gaps.push(
      "表1の「19 マンションローン・管理費」は生活CF（表5）に独立行がありません。不動産の収支は不動産シートで見ます。"
    );
  }
  return gaps;
}
