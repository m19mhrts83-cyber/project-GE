/**
 * 案件ファネルの一覧ブロック判定。
 * - 進行中（詳細〜内見）: 問合せ進行 / viewing / 明示フォロー（pursue）
 * - 買い進め（買付・融資）: offer | loan | purchased のみ
 * 「確認した」(user_confirmed) だけではどちらにも入れない。
 *
 * クライアント（DealDetailDrawer 等）からも import されるため、
 * fs / YAML 読取（reInquiryAutoConfig）に依存しない。
 */
export type DealAttachmentInfo = {
  id?: string;
  filename: string;
  open_url?: string | null;
  mime_type?: string | null;
  size_bytes?: number | null;
  kind?: "maisoku" | "contract" | "evidence" | string | null;
};

export type YieldDisplayInfo = {
  type: "confirmed" | "estimated" | "none";
  label: string;
  rateStr?: string;
  notes?: string;
  monthlyRentStr?: string;
  badgeBg: string;
  badgeBorder: string;
  badgeColor: string;
};

export type LandValueDisplayInfo = {
  hasData: boolean;
  ratioStr: string;
  ratioNum?: number;
  appraisalManStr?: string;
  tsuboPriceStr?: string;
  landAreaStr?: string;
  method?: string;
  badgeLabel: string;
  badgeBg: string;
  badgeBorder: string;
  badgeColor: string;
  basisUrl?: string;
  notes?: string;
};

export type S3InvestigationData = {
  filename?: string;
  obsidian_path?: string;
  verdict?: "go" | "hold" | "pass" | string;
  verdict_label?: string;
  verdict_reason?: string;
  address?: string;
  city?: string;
  deal_id?: string | null;
  s5_persona_line?: string;
  persona?: {
    age?: string;
    layout?: string;
    parking?: string;
    rent_range?: string;
    target_class?: string;
  };
  expected_rent?: string;
  key_risk?: string;
  structure?: string;
  hearing_questions?: string[];
  portal_url?: string;
  updated_at?: string;
};

export type PursueDealFields = {
  id: string;
  title?: string | null;
  status?: string | null;
  area?: string | null;
  price_man?: number | null;
  yield_pct?: number | null;
  match_score?: number | null;
  inquiry_status?: string | null;
  source?: string | null;
  summary_json?: Record<string, unknown> | null;
  updated_at?: string | null;
};

const BUY_PUSH = new Set(["offer", "loan", "purchased"]);
const INQUIRY_ACTIVE = new Set([
  "sent",
  "sending",
  "awaiting_reply",
  "awaiting_grok",
  "has_reply",
]);

const UKETSUKE_MARKERS = ["※受付終了※", "＊受付終了＊", "*受付終了*"];
const NOISE_TITLE = [
  "業者開拓",
  "E2E-GROK-KURASHIFT",
  "[Grok部長] 日報",
  "日報 20",
];

function sjOf(d: PursueDealFields): Record<string, unknown> {
  const sj = d.summary_json;
  return sj && typeof sj === "object" ? sj : {};
}

function inquiryOf(d: PursueDealFields): string {
  const sj = sjOf(d);
  return (
    d.inquiry_status ||
    (typeof sj.inquiry_status === "string" ? sj.inquiry_status : "none") ||
    "none"
  );
}

export function isPursueNoiseTitle(title: string | null | undefined): boolean {
  const t = String(title || "");
  if (UKETSUKE_MARKERS.some((m) => t.includes(m))) return true;
  return NOISE_TITLE.some((n) => t.includes(n));
}

/** クライアント安全な本番フィルタ（E2E・受付終了など） */
function isProductionOk(d: PursueDealFields): boolean {
  if (isPursueNoiseTitle(d.title)) return false;
  const sj = sjOf(d);
  const grok =
    sj.grok && typeof sj.grok === "object"
      ? (sj.grok as Record<string, unknown>)
      : null;
  const blob = [
    String(d.title || ""),
    String(sj.e2e ?? ""),
    String(sj.report_id ?? ""),
    String(grok?.e2e ?? ""),
    String(grok?.report_id ?? ""),
  ].join("\n");
  if (blob.includes("E2E-GROK-KURASHIFT")) return false;
  return true;
}

/** ユーザーが明示除外（進行中から外す） */
export function isPursueExcluded(d: PursueDealFields): boolean {
  return sjOf(d).pursue_exclude === true;
}

/** 明示フォロー印（「進行中に入れる」）。user_confirmed だけでは false */
export function isExplicitFollowFlag(d: PursueDealFields): boolean {
  const sj = sjOf(d);
  if (sj.pursue_exclude === true) return false;
  if (sj.pursue === true) return true;
  if (typeof sj.pursue_at === "string" && sj.pursue_at) return true;
  return false;
}

/**
 * @deprecated 旧「買い進め」判定。user_confirmed を含むため新規は isInProgressDeal / isBuyPushDeal を使う。
 */
export function isUserPursueFlag(d: PursueDealFields): boolean {
  const sj = sjOf(d);
  if (sj.pursue_exclude === true) return false;
  if (isExplicitFollowFlag(d)) return true;
  if (sj.user_confirmed === true) return true;
  if (typeof sj.user_confirmed_at === "string" && sj.user_confirmed_at) {
    return true;
  }
  return false;
}

function baseOk(d: PursueDealFields): boolean {
  const st = String(d.status || "");
  if (st === "passed" || st === "archived") return false;
  if (!isProductionOk(d)) return false;
  if (isPursueExcluded(d)) return false;
  return true;
}

/** フェーズ5: 買付証明〜融資・購入 */
export function isBuyPushDeal(d: PursueDealFields): boolean {
  if (!baseOk(d)) return false;
  return BUY_PUSH.has(String(d.status || ""));
}

/**
 * Grok詳細調査済・内見＆相談検討ステージ。
 * Obsidian ☆Real_Estate_Pick に S3需給三次 / S5ペルソナ調査レポートが存在する案件。
 */
export function isDetailedInvestigationDeal(d: PursueDealFields): boolean {
  if (!baseOk(d)) return false;
  if (BUY_PUSH.has(String(d.status || ""))) return false;
  const sj = sjOf(d);
  if (sj.s3_investigation && typeof sj.s3_investigation === "object") {
    return true;
  }
  return false;
}

/**
 * 進行中（詳細問合せ中・返信待ち）。買い進め（offer以降）やS3調査済は含めない。
 * ユーザーの「In Progressは問合せ中の状態で置いておく」方針に適合。
 */
export function isInProgressDeal(d: PursueDealFields): boolean {
  if (!baseOk(d)) return false;
  const st = String(d.status || "");
  if (BUY_PUSH.has(st)) return false;
  if (isDetailedInvestigationDeal(d)) return false;

  if (st === "viewing") return true;
  if (INQUIRY_ACTIVE.has(inquiryOf(d))) return true;
  if (isExplicitFollowFlag(d) && (st === "info" || st === "viewing")) {
    return true;
  }
  return false;
}

/**
 * @deprecated 互換。買い進め＝買付以降のみに狭めた isBuyPushDeal を優先。
 */
export function isBuyProgressDeal(d: PursueDealFields): boolean {
  return isBuyPushDeal(d) || isDetailedInvestigationDeal(d) || isInProgressDeal(d);
}

export function filterDetailedInvestigationDeals<T extends PursueDealFields>(
  deals: T[]
): T[] {
  const list = deals.filter(isDetailedInvestigationDeal);
  list.sort((a, b) => {
    const sjA = sjOf(a).s3_investigation as S3InvestigationData | undefined;
    const sjB = sjOf(b).s3_investigation as S3InvestigationData | undefined;
    const dateA = sjA?.updated_at || "";
    const dateB = sjB?.updated_at || "";
    if (dateA !== dateB) return dateB.localeCompare(dateA);
    return (b.match_score ?? 0) - (a.match_score ?? 0);
  });
  return list;
}

export function filterBuyPushDeals<T extends PursueDealFields>(deals: T[]): T[] {
  const list = deals.filter(isBuyPushDeal);
  const order = (s: string) => {
    if (s === "purchased") return 0;
    if (s === "loan") return 1;
    if (s === "offer") return 2;
    return 9;
  };
  list.sort((a, b) => {
    const oa = order(String(a.status || ""));
    const ob = order(String(b.status || ""));
    if (oa !== ob) return oa - ob;
    return (b.match_score ?? 0) - (a.match_score ?? 0);
  });
  return list;
}

export function filterInProgressDeals<T extends PursueDealFields>(
  deals: T[]
): T[] {
  const list = deals.filter(isInProgressDeal);
  const order = (s: string) => {
    if (s === "viewing") return 0;
    if (s === "info") return 1;
    return 9;
  };
  list.sort((a, b) => {
    const oa = order(String(a.status || ""));
    const ob = order(String(b.status || ""));
    if (oa !== ob) return oa - ob;
    const ia = INQUIRY_ACTIVE.has(inquiryOf(a)) ? 0 : 1;
    const ib = INQUIRY_ACTIVE.has(inquiryOf(b)) ? 0 : 1;
    if (ia !== ib) return ia - ib;
    return (b.match_score ?? 0) - (a.match_score ?? 0);
  });
  return list;
}

/** @deprecated filterInProgressDeals + filterBuyPushDeals を使う */
export function filterBuyProgressDeals<T extends PursueDealFields>(
  deals: T[]
): T[] {
  return [...filterBuyPushDeals(deals), ...filterInProgressDeals(deals)];
}

/**
 * 物件の利回り表示情報を解決する。
 * 1. 確定利回り (yield_pct または summary_json.yield_info.confirmed)
 * 2. S3想定家賃・価格からの試算利回り
 */
export function getYieldDisplayInfo(d: PursueDealFields): YieldDisplayInfo {
  const sj = sjOf(d);
  const s3 = (sj.s3_investigation as S3InvestigationData) || {};
  const yi = sj.yield_info as Record<string, unknown> | undefined;

  // 1. 確定利回り（マイソクや募集条件で明記）
  if (d.yield_pct != null && d.yield_pct > 0) {
    const isConfirmedMaisoku =
      yi?.type === "confirmed" ||
      String(sj.agent_reply ? "has_maisoku" : "").length > 0;
    return {
      type: "confirmed",
      label: `表面 ${d.yield_pct}%`,
      rateStr: `${d.yield_pct}%`,
      notes: isConfirmedMaisoku ? "マイソク記載確定" : "登録表面利回り",
      monthlyRentStr:
        typeof yi?.monthly_rent_yen === "number"
          ? `${(yi.monthly_rent_yen / 10000).toFixed(1)}万円/月`
          : undefined,
      badgeBg: "#ecfdf5",
      badgeBorder: "#10b981",
      badgeColor: "#047857",
    };
  }

  // 2. summary_json に yield_info が保存されている場合
  if (yi && typeof yi.label === "string" && yi.label) {
    const isConfirmed = yi.type === "confirmed";
    return {
      type: isConfirmed ? "confirmed" : "estimated",
      label: String(yi.label),
      rateStr: String(yi.yield_range || yi.yield_pct || ""),
      notes: typeof yi.source === "string" ? yi.source : "S3需給試算",
      monthlyRentStr:
        typeof yi.monthly_rent_range === "string"
          ? yi.monthly_rent_range
          : typeof yi.monthly_rent_yen === "number"
          ? `${(yi.monthly_rent_yen / 10000).toFixed(1)}万円/月`
          : undefined,
      badgeBg: isConfirmed ? "#ecfdf5" : "#f0fdf4",
      badgeBorder: isConfirmed ? "#10b981" : "#86efac",
      badgeColor: isConfirmed ? "#047857" : "#15803d",
    };
  }

  // 3. 価格と S3 想定家賃テキストからの動的試算
  const price = d.price_man;
  const rentText = s3.expected_rent || "";

  // テキスト内に "表面18.94%" のような表記があるかチェック
  const pctMatch = rentText.match(/表面\s*([\d.]+)%/);
  if (pctMatch && pctMatch[1]) {
    return {
      type: "estimated",
      label: `表面 ${pctMatch[1]}% (机上)`,
      rateStr: `${pctMatch[1]}%`,
      notes: "S3記載机上利回り",
      badgeBg: "#f0fdf4",
      badgeBorder: "#86efac",
      badgeColor: "#15803d",
    };
  }

  if (price && price > 0 && rentText) {
    // 例: "5.0–5.5万" や "5.0-6.0万"
    const rangeMatch = rentText.match(/([\d.]+)\s*[–〜~\-]\s*([\d.]+)万/);
    if (rangeMatch) {
      const minRent = parseFloat(rangeMatch[1]);
      const maxRent = parseFloat(rangeMatch[2]);
      if (!isNaN(minRent) && !isNaN(maxRent) && minRent > 0) {
        const minYield = ((minRent * 12) / price) * 100;
        const maxYield = ((maxRent * 12) / price) * 100;
        return {
          type: "estimated",
          label: `想定 ${minYield.toFixed(1)}%〜${maxYield.toFixed(1)}%`,
          rateStr: `${minYield.toFixed(1)}%〜${maxYield.toFixed(1)}%`,
          notes: `需給試算 (家賃${minRent}〜${maxRent}万/月)`,
          monthlyRentStr: `${minRent}〜${maxRent}万円/月`,
          badgeBg: "#f0fdf4",
          badgeBorder: "#86efac",
          badgeColor: "#15803d",
        };
      }
    }

    // 例: "本線5.0万" や "2.5万"
    const singleMatch = rentText.match(/(?:本線|合計)?\s*([\d.]+)万/);
    if (singleMatch) {
      const rent = parseFloat(singleMatch[1]);
      if (!isNaN(rent) && rent > 0) {
        const y = ((rent * 12) / price) * 100;
        return {
          type: "estimated",
          label: `想定 ${y.toFixed(1)}%`,
          rateStr: `${y.toFixed(1)}%`,
          notes: `需給試算 (家賃${rent}万/月)`,
          monthlyRentStr: `${rent}万円/月`,
          badgeBg: "#f0fdf4",
          badgeBorder: "#86efac",
          badgeColor: "#15803d",
        };
      }
    }
  }

  return {
    type: "none",
    label: "利回り未算定",
    badgeBg: "#f1f5f9",
    badgeBorder: "#cbd5e1",
    badgeColor: "#64748b",
  };
}

/**
 * 物件の土地値（路線価等による積算額、比率、坪単価）情報を解決する。
 */
export function getLandValueDisplayInfo(d: PursueDealFields): LandValueDisplayInfo {
  const sj = sjOf(d);
  const grok = (sj.grok as Record<string, unknown>) || {};
  const s3 = (sj.s3_investigation as S3InvestigationData) || {};
  const price = d.price_man || (typeof grok.price_man === "number" ? grok.price_man : undefined);

  // 1. 土地値比率
  const rawRatio = grok.land100_ratio ?? grok.land_ratio ?? sj.land100_ratio;
  let ratioNum: number | undefined;
  let ratioStr = "";

  if (rawRatio != null) {
    if (typeof rawRatio === "number" && Number.isFinite(rawRatio)) {
      ratioNum = rawRatio <= 3 ? Math.round(rawRatio * 100) : Math.round(rawRatio);
      ratioStr = `${ratioNum}%`;
    } else if (typeof rawRatio === "string") {
      const m = rawRatio.match(/(\d+(?:\.\d+)?)\s*%/);
      if (m) {
        ratioNum = Math.round(parseFloat(m[1]));
        ratioStr = `${ratioNum}%`;
      }
    }
  }

  // S3テキストからのフォールバック
  if (!ratioStr && s3) {
    const blob = JSON.stringify(s3);
    const m = blob.match(/土地値\s*(\d+(?:\.\d+)?)\s*%/);
    if (m) {
      ratioNum = Math.round(parseFloat(m[1]));
      ratioStr = `${ratioNum}%`;
    }
  }

  // 2. 土地積算額 (万円)
  const rawAppraisal = grok.land_appraisal_man ?? sj.land_appraisal_man;
  let appraisalManStr: string | undefined;
  if (rawAppraisal != null) {
    const m = String(rawAppraisal).match(/([\d,]+(?:\.\d+)?)/);
    if (m) {
      const val = parseFloat(m[1].replace(/,/g, ""));
      if (!isNaN(val) && val > 0) {
        appraisalManStr = `${Math.round(val).toLocaleString()}万円`;
      }
    }
  } else if (ratioNum && price && price > 0) {
    const calc = Math.round((ratioNum / 100) * price);
    appraisalManStr = `${calc.toLocaleString()}万円`;
  }

  // 3. 路線価・坪単価
  const rawTsubo = grok.route_price_tsubo;
  let tsuboPriceStr: string | undefined;
  if (rawTsubo != null) {
    const s = String(rawTsubo).trim();
    const mt = s.match(/(約?[\d.]+)万?.*?（([0-9]+[A-Za-z])=/);
    if (mt) {
      tsuboPriceStr = `${mt[1]}万/坪 (${mt[2]})`;
    } else {
      tsuboPriceStr = s.length > 20 ? s.slice(0, 19) + "…" : s;
    }
  }

  // 4. 土地面積
  const landAreaStr = typeof grok.land_area === "string" ? grok.land_area : undefined;

  // 5. 算出方式
  const method = typeof grok.land_method === "string" ? grok.land_method : "路線価";
  const basisUrl = typeof grok.land_basis_url === "string" ? grok.land_basis_url : undefined;

  if (ratioStr || appraisalManStr) {
    let badgeBg = "#ecfdf5";
    let badgeBorder = "#10b981";
    let badgeColor = "#047857";

    if (ratioNum != null && ratioNum >= 150) {
      badgeBg = "#fef3c7";
      badgeBorder = "#f59e0b";
      badgeColor = "#b45309";
    } else if (ratioNum != null && ratioNum >= 100) {
      badgeBg = "#ecfdf5";
      badgeBorder = "#10b981";
      badgeColor = "#047857";
    } else if (ratioNum != null && ratioNum >= 60) {
      badgeBg = "#eff6ff";
      badgeBorder = "#3b82f6";
      badgeColor = "#1d4ed8";
    } else if (ratioNum != null) {
      badgeBg = "#f8fafc";
      badgeBorder = "#cbd5e1";
      badgeColor = "#475569";
    }

    const badgeLabel = ratioStr ? `土地値 ${ratioStr}` : `積算 ${appraisalManStr}`;
    const notesParts: string[] = [];
    if (appraisalManStr) notesParts.push(`積算 ${appraisalManStr}`);
    if (tsuboPriceStr) notesParts.push(tsuboPriceStr);

    return {
      hasData: true,
      ratioStr: ratioStr || "不明",
      ratioNum,
      appraisalManStr,
      tsuboPriceStr,
      landAreaStr,
      method,
      badgeLabel,
      badgeBg,
      badgeBorder,
      badgeColor,
      basisUrl,
      notes: notesParts.join(" / "),
    };
  }

  return {
    hasData: false,
    ratioStr: "不明",
    badgeLabel: "土地値未算定",
    badgeBg: "#f1f5f9",
    badgeBorder: "#cbd5e1",
    badgeColor: "#64748b",
  };
}

/**
 * 添付資料の安全な一覧取得
 */
export function getDealAttachments(d: PursueDealFields): DealAttachmentInfo[] {
  const sj = sjOf(d);
  if (Array.isArray(sj.attachments)) {
    return sj.attachments as DealAttachmentInfo[];
  }
  return [];
}

