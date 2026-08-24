/**
 * 不動産事業 BS・PL 合成（現行保有 × Zaim許可リスト × loan × master）
 */

import type { FinanceTxnLite } from "./mqZaimMap";
import {
  matchBusinessAllowlist,
} from "./mqCashflowBusinessAllowlist";
import {
  classifyExpenseTxnHeuristic,
  txnTextBlob,
} from "./mqCashflowClassify";
import {
  RE_PROPERTY_MASTER,
  loansForProperty,
  type RePropertyMaster,
} from "./rePropertyMaster";
import {
  balanceEquity,
  computeRatios,
  currentAssets,
  currentLiab,
  emptyPlColumn,
  finalizePlColumn,
  fixedAssetsSum,
  fixedLiab,
  netBookMan,
  straightLineDepMan,
  sumPlColumns,
  totalAssets,
  totalLiab,
  yearsElapsed,
} from "./reBusinessPlMath";
import {
  DEFAULT_TAX_RATE,
  sourced,
  yenToMan,
  type ReBsColumn,
  type ReBusinessPlModel,
  type RePlColumn,
  type RePlEntity,
} from "./reBusinessPlTypes";

export type RePlLoanLite = {
  id: string;
  name: string | null;
  balance_jpy?: number | string | null;
  monthly_payment_jpy?: number | string | null;
  rate_pct?: number | string | null;
  category_major?: string | null;
  tags?: string[] | null;
  payload?: Record<string, unknown> | null;
};

export type RePlEntityOverride = {
  cashMan?: number | null;
  receivablesMan?: number | null;
  payablesMan?: number | null;
  depositsMan?: number | null;
  investmentsMan?: number | null;
  capitalMan?: number | null;
  retainedMan?: number | null;
};

export type RePlOverrides = {
  taxRate?: number;
  entity?: Partial<Record<"personal" | "corporate", RePlEntityOverride>>;
};

export type RePlMqBsCash = {
  personal: number | null;
  corporate: number | null;
};

const UNALLOCATED = "_unallocated";

function includesCI(hay: string, needle: string): boolean {
  return hay.toLowerCase().includes(needle.toLowerCase());
}

function resolveTxnEntity(
  txn: FinanceTxnLite
): "personal" | "corporate" | null {
  if (txn.entity === "personal" || txn.entity === "corporate") {
    return txn.entity;
  }
  const hit = matchBusinessAllowlist(txn);
  return hit?.defaultEntity ?? null;
}

function matchPropertyId(
  txn: FinanceTxnLite,
  props: RePropertyMaster[]
): string | null {
  const blob = txnTextBlob(txn);
  for (const p of props) {
    for (const h of p.matchHints) {
      if (h.length >= 2 && includesCI(blob, h)) return p.id;
    }
  }
  // 名義だけ分かれば個人物件は合算側に寄せず unallocated
  return null;
}

function expenseBucketToPl(
  bucket: string | null
): "management" | "taxPublic" | "repair" | "other" {
  if (bucket === "management") return "management";
  if (bucket === "annualTax" || bucket === "taxAccountant") return "taxPublic";
  if (bucket === "repair") return "repair";
  return "other";
}

type Acc = {
  rent: number;
  management: number;
  taxPublic: number;
  repair: number;
  other: number;
};

function emptyAcc(): Acc {
  return { rent: 0, management: 0, taxPublic: 0, repair: 0, other: 0 };
}

function loanInterestAndPrincipal(
  loans: RePlLoanLite[]
): { interestMan: number | null; principalMan: number | null; balanceMan: number | null; stMan: number | null } {
  if (loans.length === 0) {
    return {
      interestMan: null,
      principalMan: null,
      balanceMan: null,
      stMan: null,
    };
  }
  let interestYen = 0;
  let principalYen = 0;
  let balanceYen = 0;
  let hasRate = false;
  let hasPay = false;

  for (const l of loans) {
    const bal = Number(l.balance_jpy) || 0;
    const pay = Number(l.monthly_payment_jpy) || 0;
    const rate = Number(l.rate_pct);
    balanceYen += bal;
    if (Number.isFinite(rate) && rate > 0) {
      hasRate = true;
      interestYen += bal * (rate / 100);
    }
    if (pay > 0) {
      hasPay = true;
      const annualPay = pay * 12;
      if (Number.isFinite(rate) && rate > 0) {
        const estInterest = bal * (rate / 100);
        principalYen += Math.max(0, annualPay - estInterest);
      } else {
        // 利率不明時は返済額の70%を元金概算
        principalYen += annualPay * 0.7;
        interestYen += annualPay * 0.3;
      }
    }
  }

  const stYen = hasPay
    ? loans.reduce((s, l) => {
        const pay = Number(l.monthly_payment_jpy) || 0;
        const rate = Number(l.rate_pct);
        const bal = Number(l.balance_jpy) || 0;
        if (pay <= 0) return s;
        if (Number.isFinite(rate) && rate > 0) {
          return s + Math.max(0, pay * 12 - bal * (rate / 100));
        }
        return s + pay * 12 * 0.7;
      }, 0)
    : null;

  return {
    interestMan: hasRate || hasPay ? yenToMan(interestYen) : null,
    principalMan: hasPay ? yenToMan(principalYen) : null,
    balanceMan: yenToMan(balanceYen),
    stMan: stYen != null ? yenToMan(stYen) : null,
  };
}

function buildPlForProperty(
  prop: RePropertyMaster | null,
  propertyId: string,
  label: string,
  entity: "personal" | "corporate" | null,
  year: number,
  acc: Acc,
  loans: RePlLoanLite[],
  taxRate: number
): RePlColumn {
  const loanNums = loanInterestAndPrincipal(loans);
  let depB: number | null = null;
  let depE: number | null = null;
  if (prop?.book) {
    depB =
      prop.book.annualDepBuildingJpy != null
        ? yenToMan(prop.book.annualDepBuildingJpy)
        : straightLineDepMan(
            prop.book.buildingJpy,
            prop.book.buildingYears
          );
    depE =
      prop.book.annualDepEquipmentJpy != null
        ? yenToMan(prop.book.annualDepEquipmentJpy)
        : straightLineDepMan(
            prop.book.equipmentJpy,
            prop.book.equipmentYears
          );
  }

  const col = emptyPlColumn(propertyId, label, entity);
  col.rentIncome = sourced(
    acc.rent > 0 ? yenToMan(acc.rent) : null,
    acc.rent > 0 ? "zaim" : null
  );
  col.expenseManagement = sourced(
    acc.management > 0 ? yenToMan(acc.management) : null,
    acc.management > 0 ? "zaim" : null
  );
  col.expenseTaxPublic = sourced(
    acc.taxPublic > 0 ? yenToMan(acc.taxPublic) : null,
    acc.taxPublic > 0 ? "zaim" : null
  );
  col.expenseRepair = sourced(
    acc.repair > 0 ? yenToMan(acc.repair) : null,
    acc.repair > 0 ? "zaim" : null
  );
  col.expenseOther = sourced(
    acc.other > 0 ? yenToMan(acc.other) : null,
    acc.other > 0 ? "zaim" : null
  );
  col.depreciationBuilding = sourced(
    depB,
    depB == null
      ? null
      : prop?.book?.annualDepBuildingJpy != null
        ? "tax_return"
        : "master"
  );
  col.depreciationEquipment = sourced(
    depE,
    depE == null
      ? null
      : prop?.book?.annualDepEquipmentJpy != null
        ? "tax_return"
        : "master"
  );
  col.interest = sourced(
    loanNums.interestMan,
    loanNums.interestMan == null ? null : "loan_tracker",
    "残高×金利（概算）"
  );
  col.principalRepay = sourced(
    loanNums.principalMan,
    loanNums.principalMan == null ? null : "loan_tracker",
    "年返済−利息概算"
  );
  return finalizePlColumn(col, taxRate);
}

function buildBsForProperty(
  prop: RePropertyMaster | null,
  propertyId: string,
  label: string,
  entity: "personal" | "corporate" | null,
  year: number,
  loans: RePlLoanLite[],
  cashMan: number | null,
  ov?: RePlEntityOverride | null
): ReBsColumn {
  const loanNums = loanInterestAndPrincipal(loans);
  const elapsed = prop ? yearsElapsed(prop.acquired, year) : 0;
  const building = prop?.book
    ? netBookMan(
        prop.book.buildingJpy,
        prop.book.buildingYears,
        elapsed
      )
    : null;
  const equipment = prop?.book
    ? netBookMan(
        prop.book.equipmentJpy,
        prop.book.equipmentYears,
        elapsed
      )
    : null;
  const land = prop?.book?.landJpy != null ? yenToMan(prop.book.landJpy) : null;

  const cash =
    cashMan != null
      ? sourced(cashMan, "mq_bs")
      : sourced(ov?.cashMan ?? null, ov?.cashMan != null ? "override" : null);
  const receivables = sourced(ov?.receivablesMan ?? 0, "override");
  const ca = currentAssets(cash.man, receivables.man);
  const investments = sourced(ov?.investmentsMan ?? 0, "override");
  const fa = fixedAssetsSum(building, equipment, land, investments.man);
  const ta = totalAssets(ca.man, fa.man);

  const st = sourced(
    loanNums.stMan,
    loanNums.stMan == null ? null : "loan_tracker"
  );
  const payables = sourced(ov?.payablesMan ?? 0, "override");
  const cl = currentLiab(st.man, payables.man);
  const bal = loanNums.balanceMan;
  const ltMan =
    bal != null && st.man != null
      ? Math.max(0, bal - st.man)
      : bal;
  const lt = sourced(ltMan, ltMan == null ? null : "loan_tracker");
  const deposits = sourced(ov?.depositsMan ?? 0, "override");
  const fl = fixedLiab(lt.man, deposits.man);
  const tl = totalLiab(cl.man, fl.man);

  const eq = balanceEquity({
    totalAssets: ta.man,
    totalLiab: tl.man,
    capital: ov?.capitalMan ?? null,
    retained: ov?.retainedMan ?? null,
  });

  return {
    propertyId,
    label,
    entity,
    cash,
    receivables,
    currentAssets: ca,
    building: sourced(
      building,
      building == null
        ? null
        : prop?.book?.allocation === "tax_return"
          ? "tax_return"
          : "master",
      prop?.book?.allocation === "estimated"
        ? "按分概算"
        : prop?.book?.allocation === "tax_return"
          ? "申告・決算"
          : undefined
    ),
    equipment: sourced(
      equipment,
      equipment == null
        ? null
        : prop?.book?.allocation === "tax_return"
          ? "tax_return"
          : "master"
    ),
    land: sourced(
      land,
      land == null
        ? null
        : prop?.book?.allocation === "tax_return"
          ? "tax_return"
          : "master"
    ),
    investments,
    fixedAssets: fa,
    totalAssets: ta,
    stLoan: st,
    payables,
    currentLiab: cl,
    ltLoan: lt,
    deposits,
    fixedLiab: fl,
    totalLiab: tl,
    capital: eq.capital,
    retained: eq.retained,
    equity: eq.equity,
    totalLiabEquity: eq.totalLiabEquity,
    balanced: eq.balanced,
  };
}

function sumBsColumns(cols: ReBsColumn[], label = "合計"): ReBsColumn {
  const pick = (fn: (c: ReBsColumn) => number | null) => {
    const mans = cols.map(fn);
    if (mans.every((m) => m == null)) return sourced(null, null);
    return sourced(
      mans.reduce<number>((s, m) => s + (m ?? 0), 0),
      "derived"
    );
  };
  const ta = pick((c) => c.totalAssets.man);
  const tl = pick((c) => c.totalLiab.man);
  const eq = balanceEquity({
    totalAssets: ta.man,
    totalLiab: tl.man,
    capital: pick((c) => c.capital.man).man,
    retained: pick((c) => c.retained.man).man,
  });
  return {
    propertyId: "_total",
    label,
    entity: null,
    cash: pick((c) => c.cash.man),
    receivables: pick((c) => c.receivables.man),
    currentAssets: pick((c) => c.currentAssets.man),
    building: pick((c) => c.building.man),
    equipment: pick((c) => c.equipment.man),
    land: pick((c) => c.land.man),
    investments: pick((c) => c.investments.man),
    fixedAssets: pick((c) => c.fixedAssets.man),
    totalAssets: ta,
    stLoan: pick((c) => c.stLoan.man),
    payables: pick((c) => c.payables.man),
    currentLiab: pick((c) => c.currentLiab.man),
    ltLoan: pick((c) => c.ltLoan.man),
    deposits: pick((c) => c.deposits.man),
    fixedLiab: pick((c) => c.fixedLiab.man),
    totalLiab: tl,
    capital: eq.capital,
    retained: eq.retained,
    equity: eq.equity,
    totalLiabEquity: eq.totalLiabEquity,
    balanced: eq.balanced,
  };
}

/** 既定オーバーライド（YAML 写し） */
export const DEFAULT_RE_PL_OVERRIDES: RePlOverrides = {
  taxRate: DEFAULT_TAX_RATE,
  entity: {
    corporate: {
      cashMan: null,
      receivablesMan: 0,
      payablesMan: 0,
      depositsMan: 0,
      investmentsMan: 0,
      capitalMan: 10,
      retainedMan: null,
    },
    personal: {
      cashMan: null,
      receivablesMan: 0,
      payablesMan: 0,
      depositsMan: 0,
      investmentsMan: 0,
      capitalMan: null,
      retainedMan: null,
    },
  },
};

export function composeReBusinessPl(args: {
  year: number;
  entity: RePlEntity;
  txns: FinanceTxnLite[];
  loans: RePlLoanLite[];
  mqBsCash?: RePlMqBsCash;
  overrides?: RePlOverrides;
}): ReBusinessPlModel {
  const {
    year,
    entity,
    txns,
    loans,
    mqBsCash = { personal: null, corporate: null },
    overrides = DEFAULT_RE_PL_OVERRIDES,
  } = args;
  const taxRate = overrides.taxRate ?? DEFAULT_TAX_RATE;
  const notes: string[] = [
    "ゼミExcel準拠の事業BS・PL。MQ要素法・家計BSとは別ものさしです。",
    "土地・建物按分と利息・元金は概算を含みます。確定申告・決算の代替ではありません。",
  ];

  const props = RE_PROPERTY_MASTER.filter((p) => {
    if (entity === "combined") return true;
    return p.entity === entity;
  });

  const accByProp = new Map<string, Acc>();
  for (const p of props) accByProp.set(p.id, emptyAcc());
  accByProp.set(UNALLOCATED, emptyAcc());

  for (const t of txns) {
    const hit = matchBusinessAllowlist(t);
    if (!hit) continue;
    const te = resolveTxnEntity(t);
    if (entity !== "combined" && te && te !== entity) continue;
    // 物件フィルタ: 名義が合う物件のみ
    let pid = matchPropertyId(t, props);
    if (pid) {
      const prop = props.find((p) => p.id === pid);
      if (prop && entity !== "combined" && prop.entity !== entity) {
        pid = null;
      }
    }
    const key = pid || UNALLOCATED;
    if (!accByProp.has(key)) accByProp.set(key, emptyAcc());
    const acc = accByProp.get(key)!;
    const inc = Number(t.income_jpy) || 0;
    const exp = Number(t.expense_jpy) || 0;
    if (hit.side === "income" && inc > 0) {
      acc.rent += inc;
      continue;
    }
    if (hit.side === "expense" && exp > 0) {
      if (hit.expenseMode === "expense_flat") {
        acc.other += exp;
        continue;
      }
      const h = classifyExpenseTxnHeuristic(t);
      if (h.isLoan) continue; // 元本は loan tracker
      const b = expenseBucketToPl(h.bucket);
      acc[b] += exp;
    }
  }

  const plCols: RePlColumn[] = [];
  const bsCols: ReBsColumn[] = [];

  for (const prop of props) {
    const acc = accByProp.get(prop.id) || emptyAcc();
    const propLoans = loansForProperty(prop.id, loans);
    plCols.push(
      buildPlForProperty(
        prop,
        prop.id,
        prop.name,
        prop.entity,
        year,
        acc,
        propLoans,
        taxRate
      )
    );

    // 現預金は名義単位で1回だけ載せる（先頭物件に寄せる）
    const sameEntityProps = props.filter((p) => p.entity === prop.entity);
    const isFirstOfEntity = sameEntityProps[0]?.id === prop.id;
    const cashForProp = isFirstOfEntity
      ? prop.entity === "corporate"
        ? mqBsCash.corporate
        : mqBsCash.personal
      : null;
    const entOv = overrides.entity?.[prop.entity];
    bsCols.push(
      buildBsForProperty(
        prop,
        prop.id,
        prop.name,
        prop.entity,
        year,
        propLoans,
        cashForProp,
        isFirstOfEntity
          ? entOv
          : { ...(entOv || {}), cashMan: null, capitalMan: null }
      )
    );
  }

  const unAcc = accByProp.get(UNALLOCATED) || emptyAcc();
  const hasUn =
    unAcc.rent > 0 ||
    unAcc.management > 0 ||
    unAcc.taxPublic > 0 ||
    unAcc.repair > 0 ||
    unAcc.other > 0;
  if (hasUn) {
    notes.push(
      "物件に紐づかない事業取引は「未配分」列に集約しています（口座・摘要で紐づけ強化可）。"
    );
    plCols.push(
      buildPlForProperty(
        null,
        UNALLOCATED,
        "未配分",
        entity === "combined" ? null : entity,
        year,
        unAcc,
        [],
        taxRate
      )
    );
  }

  const totalPl = sumPlColumns(plCols, "合計", taxRate);
  const totalBs = sumBsColumns(bsCols);
  const ratios = computeRatios(totalBs, totalPl.cashFlow.man);

  if (props.some((p) => p.book?.allocation === "estimated")) {
    notes.push("固定資産の土地・建物按分は概算です。税務上の取得価額に差し替えてください。");
  }
  if (props.some((p) => p.book?.allocation === "tax_return")) {
    notes.push(
      "固定資産は確定申告（収支内訳）または第1期BS提出用サマリーの数値です。法人Ⅰの償却明細は画像PDFのため未OCR。"
    );
  }

  return {
    year,
    entity,
    taxRate,
    columns: plCols,
    totalPl,
    bsColumns: bsCols,
    totalBs,
    ratios,
    notes,
  };
}
