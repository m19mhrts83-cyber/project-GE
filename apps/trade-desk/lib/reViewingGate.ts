/**
 * ③-B 内見GO判定（机上）と指値ライン。
 *
 * 内見GO は「机上で否定材料がない」で出す。現地・地場仲介でしか分からないこと
 * （室内・傾き・駐車可否・成約家賃）は内見で確かめる項目に回し、保留の理由にしない。
 * 正本: docs/KURASHIFT_不動産フェーズ定義.md
 *
 *   指値ライン（万円）= 保守の想定家賃（万円/月）× 12 ÷ 目標利回り − 修繕概算（万円）
 *
 * 記録と表示だけ。仲介への送信はしない。
 */
// reDealStages から import されるため、ここからは import しない（循環回避）
type ViewingLike = {
  step?: string;
  date?: string | null;
  desk_rent_man?: number | null;
  repair_man?: number | null;
};

function getViewing(d: GateDeal): ViewingLike {
  const v = d.summary_json && typeof d.summary_json === "object" ? d.summary_json.viewing : null;
  return v && typeof v === "object" ? (v as ViewingLike) : {};
}

function todayJst(now: Date = new Date()): string {
  return new Date(now.getTime() + 9 * 3600 * 1000).toISOString().slice(0, 10);
}

/** 戸建の交渉後利回り 15〜20% の下限 */
export const TARGET_YIELD = 0.15;

/** 内見のペース目安: 内見候補（机上GO）を常に3件、月2件内見 */
export const VIEWING_PACE = { candidates: 3, perMonth: 2 } as const;

type GateDeal = {
  status?: string | null;
  price_man?: number | string | null;
  summary_json?: Record<string, unknown> | null;
};

export type DeskGate = {
  verdict: "go" | "over" | "unknown";
  /** 保守の想定家賃（万円/月） */
  rentMan: number | null;
  rentSource: "manual" | "s3" | "s3_text" | null;
  repairMan: number;
  /** 指値ライン（万円） */
  lineMan: number | null;
  priceMan: number | null;
  /** 掲載価格から指値ラインまでの値下げ率（%）。over のときだけ */
  cutPct: number | null;
  label: string;
};

function num(v: unknown): number | null {
  if (v == null || v === "") return null;
  const n = Number(v);
  return Number.isFinite(n) ? n : null;
}

function plausibleRent(n: number | null): number | null {
  return n != null && n >= 0.5 && n <= 300 ? n : null;
}

/**
 * S3 の想定家賃テキストから保守側（万円/月）を取る。
 * 「保守5.0万」→ 5.0、「5.0–5.5万」→ 5.0（下限）、「6.0万」→ 6.0。
 */
export function parseConservativeRentMan(text: string | null | undefined): number | null {
  if (!text) return null;
  const t = String(text)
    .replace(/\*/g, "")
    .replace(/[０-９．]/g, (c) => String.fromCharCode(c.charCodeAt(0) - 0xfee0));
  const cons = t.match(/保守\s*([\d.]+)\s*万/);
  if (cons) return plausibleRent(num(cons[1]));
  const range = t.match(/([\d.]+)\s*[–\-〜~～]\s*([\d.]+)\s*万/);
  if (range) return plausibleRent(num(range[1]));
  const one = t.match(/([\d.]+)\s*万/);
  if (one) return plausibleRent(num(one[1]));
  return null;
}

/** 指値ライン（万円・切り捨て） */
export function offerLineMan(rentMan: number, repairMan = 0, targetYield = TARGET_YIELD): number {
  return Math.floor((rentMan * 12) / targetYield - repairMan);
}

export function deskGate(d: GateDeal): DeskGate {
  const sj = d.summary_json && typeof d.summary_json === "object" ? d.summary_json : {};
  const s3 =
    sj.s3_investigation && typeof sj.s3_investigation === "object"
      ? (sj.s3_investigation as Record<string, unknown>)
      : {};
  const v = getViewing(d);
  const priceMan = num(d.price_man);
  const repairMan = num(v.repair_man) ?? 0;

  let rentMan: number | null = plausibleRent(num(v.desk_rent_man));
  let rentSource: DeskGate["rentSource"] = rentMan != null ? "manual" : null;
  if (rentMan == null) {
    rentMan = plausibleRent(num(s3.rent_conservative_man));
    if (rentMan != null) rentSource = "s3";
  }
  if (rentMan == null) {
    rentMan = parseConservativeRentMan(s3.expected_rent as string | undefined);
    if (rentMan != null) rentSource = "s3_text";
  }

  if (rentMan == null) {
    return {
      verdict: "unknown",
      rentMan: null,
      rentSource: null,
      repairMan,
      lineMan: null,
      priceMan,
      cutPct: null,
      label: "保守の想定家賃を入れると指値ラインが出ます",
    };
  }
  const lineMan = offerLineMan(rentMan, repairMan);
  if (priceMan == null || priceMan <= 0) {
    return {
      verdict: "unknown",
      rentMan,
      rentSource,
      repairMan,
      lineMan,
      priceMan: null,
      cutPct: null,
      label: `指値ライン ${lineMan}万円（掲載価格が未登録）`,
    };
  }
  if (priceMan <= lineMan) {
    return {
      verdict: "go",
      rentMan,
      rentSource,
      repairMan,
      lineMan,
      priceMan,
      cutPct: null,
      label: `机上GO: 掲載${priceMan}万 ≦ 指値ライン${lineMan}万`,
    };
  }
  const cutPct = Math.ceil(((priceMan - lineMan) / priceMan) * 100);
  return {
    verdict: "over",
    rentMan,
    rentSource,
    repairMan,
    lineMan,
    priceMan,
    cutPct,
    label: `掲載${priceMan}万 → 指値ライン${lineMan}万（${cutPct}%下げが必要）`,
  };
}

export type ViewingPace = {
  /** まだ内見を依頼していない机上GO の件数 */
  goCandidates: number;
  /** 今月（JST）に内見日がある件数 */
  thisMonth: number;
  candidatesShort: number;
  monthShort: number;
};

export function viewingPace<T extends GateDeal>(deals: T[], today: string = todayJst()): ViewingPace {
  const month = today.slice(0, 7);
  let goCandidates = 0;
  let thisMonth = 0;
  for (const d of deals) {
    const v = getViewing(d);
    if ((!v.step || v.step === "candidate") && deskGate(d).verdict === "go") goCandidates++;
    if (v.date && v.date.slice(0, 7) === month && (v.step === "scheduled" || v.step === "done")) {
      thisMonth++;
    }
  }
  return {
    goCandidates,
    thisMonth,
    candidatesShort: Math.max(0, VIEWING_PACE.candidates - goCandidates),
    monthShort: Math.max(0, VIEWING_PACE.perMonth - thisMonth),
  };
}
