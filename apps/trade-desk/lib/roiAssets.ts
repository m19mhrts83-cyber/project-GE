/** 買い物ごとの ROI 正本（Zaim 19 合計ではない）。金額は円。 */

export type RoiStatus = "owned" | "sold";

export type RoiAsset = {
  id: string;
  name: string;
  owner: string;
  status: RoiStatus;
  bought: string;
  soldNote?: string;
  /** 契約・図面の売買代金（本体） */
  bodyPrice: number | null;
  /** 購入時諸費用（手付・残金は本体側） */
  acquireCost: number | null;
  acquireCostComplete: boolean;
  acquireCostNote: string;
  /** 決済当日の支払合計（手付済なら本体全額ではない） */
  settlementPay: number | null;
  loan: number | null;
  rateBuy: string | null;
  monthlyPayBuy: number | null;
  monthlyPayNow: number | null;
  /** 購入時の満室年収（レントロール／図面） */
  fullRentBuy: number | null;
  fullRentBuyNote: string;
  equity: number | null;
  occBuy: string | null;
  occ2025: string | null;
  actualNote: string;
  /** property_units と突合する id。売却済みは null */
  unitPropertyId: string | null;
};

export const ROI_ASSETS: RoiAsset[] = [
  {
    id: "grandole-ii",
    name: "Grandole志賀本通II",
    owner: "個人",
    status: "owned",
    bought: "2022-09",
    bodyPrice: 69_800_000,
    acquireCost: 5_957_433,
    acquireCostComplete: true,
    acquireCostNote:
      "Zaim 購入費用（仲介 223万・オリックス手数料 246万・登記 94万・火災 30万ほか）。手付のアペザン 200万と残金振込 6,639万は本体側",
    settlementPay: null,
    loan: 65_000_000,
    rateBuy: "2.60%→3.50%",
    monthlyPayBuy: 272_539,
    monthlyPayNow: 300_746,
    fullRentBuy: 5_340_000,
    fullRentBuyNote: "図面満室 534万（経歴書 511.8万とは不一致。図面を採用）",
    equity: 4_800_000,
    occBuy: "87.5%（7/8）",
    occ2025: "76.2%（HP賃料 406.9万 / 図面534万）",
    actualNote: "2025-10 以降 3.5%・月 300,746円。いま満室",
    unitPropertyId: "grandole-ii",
  },
  {
    id: "grandole-i",
    name: "Grandole志賀本通I",
    owner: "法人",
    status: "owned",
    bought: "2025-02-28",
    bodyPrice: 68_532_000,
    acquireCost: 4_142_915,
    acquireCostComplete: true,
    acquireCostNote:
      "決済案内の諸費用ネット（仲介 221万・ローン事務 68万・登記 99万・固都税 33万 − 賃料精算 7万）",
    settlementPay: 65_214_215,
    loan: 61_700_000,
    rateBuy: "2.65%→2.90%",
    monthlyPayBuy: 262_928,
    monthlyPayNow: 262_928,
    fullRentBuy: 5_256_000,
    fullRentBuyNote:
      "2年目帯（キャンペーン終了後）家賃+管理費 月43.8万。現況は1年目混在で月41.6万→年499.2万。町費は含めない",
    equity: 7_535_531,
    occBuy: "19.5%（第1期）",
    occ2025: "第1期売上 973,104円（短縮決算）",
    actualNote:
      "計画 NET 388.6万 @稼働 77.4%。管理は LEAF / Tcell / ミニテック。1年目は号室により月4,000円引き",
    unitPropertyId: "grandole-i",
  },
  {
    id: "caramel",
    name: "キャラメル",
    owner: "個人",
    status: "owned",
    bought: "2025-12-25",
    bodyPrice: 46_000_000,
    acquireCost: 2_711_790,
    acquireCostComplete: false,
    acquireCostNote:
      "シャルア精算案内の仲介158.4万＋所有権司法書士73.8万、キャスト抵当25.8万、滋賀銀事務手数料13.2万。火災保険と売主精算戻し22.9万は未反映。諸費用ローン100万は支払手段のため含めない",
    settlementPay: null,
    loan: 45_000_000,
    rateBuy: "2.55%＋諸費用2.675%",
    monthlyPayBuy: 188_482,
    monthlyPayNow: 188_482,
    fullRentBuy: 3_560_808,
    fullRentBuyNote: "契約レントロール満室（駐車場込み）。号室合計とは差あり",
    equity: 1_000_000,
    occBuy: "100%（4/4）",
    occ2025: "決済12/26のためほぼ無し",
    actualNote: "Tcell 送金 267,962円/月はパック差引後 NET。入居率の分母に使わない",
    unitPropertyId: "caramel",
  },
  {
    id: "river-cross",
    name: "リバークロス",
    owner: "個人",
    status: "sold",
    bought: "—",
    soldNote: "ワンルーム3戸のうち。Numbers ROI表の履歴",
    bodyPrice: 14_800_000,
    acquireCost: null,
    acquireCostComplete: false,
    acquireCostNote: "売却済み。経費内訳は Numbers に無し",
    settlementPay: null,
    loan: null,
    rateBuy: null,
    monthlyPayBuy: 63_900,
    monthlyPayNow: null,
    fullRentBuy: 678_000,
    fullRentBuyNote: "Numbers 満室年収 67.8万",
    equity: null,
    occBuy: null,
    occ2025: null,
    actualNote: "売却済み。購入時 ROI −11.6%（Numbers）",
    unitPropertyId: null,
  },
  {
    id: "north-residence",
    name: "ノースレジデンス",
    owner: "個人",
    status: "sold",
    bought: "—",
    soldNote: "ワンルーム3戸のうち。Numbers ROI表の履歴",
    bodyPrice: 15_100_000,
    acquireCost: null,
    acquireCostComplete: false,
    acquireCostNote: "売却済み。経費内訳は Numbers に無し",
    settlementPay: null,
    loan: null,
    rateBuy: null,
    monthlyPayBuy: 60_300,
    monthlyPayNow: null,
    fullRentBuy: 897_600,
    fullRentBuyNote: "Numbers 満室年収 89.76万",
    equity: null,
    occBuy: null,
    occ2025: null,
    actualNote: "売却済み。購入時 ROI 24.0%（Numbers）",
    unitPropertyId: null,
  },
  {
    id: "la-doux",
    name: "ラ・ドゥー",
    owner: "個人",
    status: "sold",
    bought: "—",
    soldNote: "ワンルーム3戸のうち。Numbers ROI表の履歴",
    bodyPrice: 12_900_000,
    acquireCost: null,
    acquireCostComplete: false,
    acquireCostNote: "売却済み。経費内訳は Numbers に無し",
    settlementPay: null,
    loan: null,
    rateBuy: null,
    monthlyPayBuy: 50_700,
    monthlyPayNow: null,
    fullRentBuy: 811_200,
    fullRentBuyNote: "Numbers 満室年収 81.12万",
    equity: null,
    occBuy: null,
    occ2025: null,
    actualNote: "売却済み。購入時 ROI 33.3%（Numbers）",
    unitPropertyId: null,
  },
];

export function acquireTotal(a: RoiAsset): number | null {
  if (a.bodyPrice == null) return null;
  return a.bodyPrice + (a.acquireCost ?? 0);
}

export function costOnBodyPct(a: RoiAsset): number | null {
  if (a.bodyPrice == null || a.acquireCost == null || a.bodyPrice === 0) {
    return null;
  }
  return a.acquireCost / a.bodyPrice;
}

export function payYear(monthly: number | null | undefined): number | null {
  if (monthly == null) return null;
  return monthly * 12;
}

/** 表面利回り = 満室年収 ÷ 本体価格 */
export function surfaceYield(
  fullRent: number | null,
  bodyPrice: number | null
): number | null {
  if (fullRent == null || bodyPrice == null || bodyPrice === 0) return null;
  return fullRent / bodyPrice;
}

/** 取得合計ベースの利回り = 満室年収 ÷（本体＋経費） */
export function allInYield(
  fullRent: number | null,
  total: number | null
): number | null {
  if (fullRent == null || total == null || total === 0) return null;
  return fullRent / total;
}

/** Numbers 流 ROI =（満室年収 − 年返済）÷ 年返済。経費は引かない */
export function cfRoi(
  fullRent: number | null,
  annualPay: number | null
): number | null {
  if (fullRent == null || annualPay == null || annualPay === 0) return null;
  return (fullRent - annualPay) / annualPay;
}

/**
 * 返済比率 = 年返済 ÷ 年収。
 * MG会計研修の目安は 50%前後（会話では 50〜60% も言及）。
 * DSCR（家賃÷返済）の逆数に近いが、投資家側の「家賃の何割が返済か」を見る。
 */
export const REPAYMENT_RATIO_GUIDE = 0.5;
export const REPAYMENT_RATIO_SOFT_MAX = 0.6;

export function repaymentRatio(
  annualPay: number | null,
  annualIncome: number | null
): number | null {
  if (annualPay == null || annualIncome == null || annualIncome === 0) {
    return null;
  }
  return annualPay / annualIncome;
}

export function repaymentRatioLabel(r: number | null): string {
  if (r == null || !Number.isFinite(r)) return "—";
  if (r <= REPAYMENT_RATIO_GUIDE) return "目安内";
  if (r <= REPAYMENT_RATIO_SOFT_MAX) return "目安帯";
  if (r < 1) return "高め";
  return "持ち出し";
}

export function repaymentRatioTone(
  r: number | null
): "ok" | "mid" | "high" | "out" | null {
  if (r == null || !Number.isFinite(r)) return null;
  if (r <= REPAYMENT_RATIO_GUIDE) return "ok";
  if (r <= REPAYMENT_RATIO_SOFT_MAX) return "mid";
  if (r < 1) return "high";
  return "out";
}

export function fullCf(
  fullRent: number | null,
  annualPay: number | null
): number | null {
  if (fullRent == null || annualPay == null) return null;
  return fullRent - annualPay;
}

/** キャッシュオンキャッシュ = 満室CF ÷ 自己資金 */
export function cashOnCash(
  cf: number | null,
  equity: number | null
): number | null {
  if (cf == null || equity == null || equity === 0) return null;
  return cf / equity;
}

export type PropertyUnitRow = {
  property_id: string;
  property_name: string;
  room: string;
  status: string;
  rent: number | null;
  note: string | null;
  payload: Record<string, unknown> | null;
};

export type UnitLive = {
  propertyId: string;
  name: string;
  occupied: number;
  total: number;
  rentMonth: number;
  totalRentMonth: number;
  occupiedRentMonth: number;
  units: {
    room: string;
    status: string;
    rent: number | null;
    mgmt: number | null;
    totalRent: number | null;
    note: string | null;
  }[];
};

export function unitBreakdown(u: PropertyUnitRow): {
  rent: number | null;
  mgmt: number | null;
  totalRent: number | null;
} {
  const rent = u.rent != null ? Number(u.rent) : null;
  const mgmtRaw = u.payload?.management_fee;
  const mgmt =
    typeof mgmtRaw === "number"
      ? mgmtRaw
      : typeof mgmtRaw === "string" && mgmtRaw !== ""
        ? Number(mgmtRaw)
        : null;
  const totalRaw = u.payload?.total_rent;
  let totalRent =
    typeof totalRaw === "number"
      ? totalRaw
      : typeof totalRaw === "string" && totalRaw !== ""
        ? Number(totalRaw)
        : null;
  if (totalRent == null && rent != null) {
    totalRent = rent + (mgmt != null && !Number.isNaN(mgmt) ? mgmt : 0);
  }
  return {
    rent: rent != null && !Number.isNaN(rent) ? rent : null,
    mgmt: mgmt != null && !Number.isNaN(mgmt) ? mgmt : null,
    totalRent: totalRent != null && !Number.isNaN(totalRent) ? totalRent : null,
  };
}

export function groupUnitsLive(rows: PropertyUnitRow[]): Map<string, UnitLive> {
  const map = new Map<string, UnitLive>();
  for (const u of rows) {
    const b = unitBreakdown(u);
    let g = map.get(u.property_id);
    if (!g) {
      g = {
        propertyId: u.property_id,
        name: u.property_name,
        occupied: 0,
        total: 0,
        rentMonth: 0,
        totalRentMonth: 0,
        occupiedRentMonth: 0,
        units: [],
      };
      map.set(u.property_id, g);
    }
    g.total += 1;
    if (u.status === "occupied") {
      g.occupied += 1;
      g.occupiedRentMonth += b.totalRent ?? 0;
    }
    g.rentMonth += b.rent ?? 0;
    g.totalRentMonth += b.totalRent ?? 0;
    g.units.push({
      room: u.room,
      status: u.status,
      rent: b.rent,
      mgmt: b.mgmt,
      totalRent: b.totalRent,
      note: u.note,
    });
  }
  return map;
}

export function occRate(live: UnitLive | undefined): number | null {
  if (!live || live.total === 0) return null;
  return live.occupied / live.total;
}

/** 物件以外の「大きな買い物」（ペーパー）。CF-ROI ではなく単純ROI＋クーポン収入。 */
export type PaperRoiPurchase = {
  id: string;
  accountId: string;
  name: string;
  bought: string;
  /** 画面フォールバック用の取得原価（週次で cost_jpy が入れば DB 優先） */
  costFallbackJpy: number;
  couponPct: number;
  faceUsd: number;
  maturity: string;
  couponSchedule: string;
  policy: string;
  note: string;
};

export const PAPER_ROI_PURCHASES: PaperRoiPurchase[] = [
  {
    id: "akatsuki-gs-subordinated",
    accountId: "akatsuki_bond",
    name: "あかつき証券・GS劣後債（L0354）",
    bought: "購入済み（保有継続）",
    costFallbackJpy: 7_266_704,
    couponPct: 5.15,
    faceUsd: 51_000,
    maturity: "2045-05-22",
    couponSchedule: "年2回（5/22・11/22）",
    policy: "売らない・これ以上増やさない。成長は株式側。",
    note:
      "取得金額はあかつきマイページの「取得金額」。単純ROI＝（評価−取得）÷取得。クーポン収入利回り＝額面×利率×想定為替÷取得。",
  },
];

/** 単純ROI =（評価 − 取得）÷ 取得 */
export function simpleRoi(
  value: number | null,
  cost: number | null
): number | null {
  if (value == null || cost == null || cost === 0) return null;
  return (value - cost) / cost;
}

/**
 * クーポン収入の取得原価に対する利回り（概算）。
 * 年クーポン円 = 額面USD × 利率 × 為替。為替未取得時は 評価÷額面 を使う。
 */
export function couponIncomeYieldOnCost(
  cost: number | null,
  faceUsd: number,
  couponPct: number,
  valueJpy: number | null,
  fxJpyPerUsd: number | null = null
): number | null {
  if (cost == null || cost === 0 || faceUsd <= 0 || couponPct <= 0) return null;
  const fx =
    fxJpyPerUsd != null && fxJpyPerUsd > 0
      ? fxJpyPerUsd
      : valueJpy != null && valueJpy > 0
        ? valueJpy / faceUsd
        : null;
  if (fx == null) return null;
  const annualCouponJpy = faceUsd * (couponPct / 100) * fx;
  return annualCouponJpy / cost;
}
