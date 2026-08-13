/** 申告サイクル（Asia/Tokyo）。個人は暦年、法人は5月決算。 */

export type TaxScope = "personal" | "corporate";

export type TaxCycle = {
  scope: TaxScope;
  year: number;
  label: string;
  window: boolean;
  windowLabel: string;
  jarvisPrompt: string;
};

function tokyoParts(now = new Date()): { year: number; month: number } {
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Tokyo",
    year: "numeric",
    month: "2-digit",
  }).formatToParts(now);
  return {
    year: Number(parts.find((p) => p.type === "year")?.value),
    month: Number(parts.find((p) => p.type === "month")?.value),
  };
}

/** 個人: 1〜3月は前年分の申告、4〜12月は当年分の準備。 */
export function personalTaxYear(now = new Date()): number {
  const { year, month } = tokyoParts(now);
  return month <= 3 ? year - 1 : year;
}

/** 法人: 5月決算。1〜8月は当年5月期、9〜12月は翌年5月期。 */
export function corporateTaxYear(now = new Date()): number {
  const { year, month } = tokyoParts(now);
  return month <= 8 ? year : year + 1;
}

/** 個人の取込窓: 12月締め〜2月申告。 */
export function isPersonalIngestWindow(now = new Date()): boolean {
  const { month } = tokyoParts(now);
  return month === 12 || month === 1 || month === 2;
}

/** 法人の取込窓: 決算後〜8月頃にまとまる。 */
export function isCorporateIngestWindow(now = new Date()): boolean {
  const { month } = tokyoParts(now);
  return month >= 6 && month <= 8;
}

export function personalCycle(now = new Date()): TaxCycle {
  const year = personalTaxYear(now);
  return {
    scope: "personal",
    year,
    label: `${year}年分`,
    window: isPersonalIngestWindow(now),
    windowLabel: "12月締め → 2月中旬〜下旬に申告",
    jarvisPrompt: `${year}年分の個人申告を回して。弥生CSVと税理士メールを取り込んでください。`,
  };
}

export function corporateCycle(now = new Date()): TaxCycle {
  const year = corporateTaxYear(now);
  return {
    scope: "corporate",
    year,
    label: `${year}年5月期`,
    window: isCorporateIngestWindow(now),
    windowLabel: "5月決算 → だいたい8月頃にまとまる",
    jarvisPrompt: `${year}年5月期の法人申告メール（Knees bee 大野さんのPDF）を取り込んでください。`,
  };
}
