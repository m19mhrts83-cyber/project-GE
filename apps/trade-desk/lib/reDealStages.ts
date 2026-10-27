/**
 * ③-B 購入検討 — 2次調査（S5/S3）以降の段階管理。
 *
 * DB の status（info / viewing / offer / loan / purchased）はそのまま使い、
 * 細かい段階・チェックリスト・日付は summary_json に持つ（migration 不要）。
 *   - summary_json.viewing     … 内見（候補 → 依頼 → 日程確定 → 内見済 → 判断）
 *   - summary_json.acquisition … 買付〜引渡し（8段階）
 *
 * 安全境界: ここは記録と「次にやること」の表示だけ。仲介・銀行への送信はしない。
 */
import { deskGate } from "./reViewingGate";

export type ViewingStep = "candidate" | "requested" | "scheduled" | "done";
export type ViewingVerdict = "go" | "hold" | "pass";

export type ViewingState = {
  step?: ViewingStep;
  /** 内見日 YYYY-MM-DD */
  date?: string | null;
  /** 内見時刻（任意） HH:MM */
  time?: string | null;
  /** 仲介・担当者メモ */
  contact?: string | null;
  memo?: string | null;
  verdict?: ViewingVerdict | null;
  checklist?: Record<string, boolean>;
  /** S3 ヒアリング項目の回答（index → 回答） */
  hearing_answers?: Record<string, string>;
  /** 保守の想定家賃（万円/月）。S3 の値を手で上書きするとき */
  desk_rent_man?: number | null;
  /** 修繕概算（万円）。内見後に入れて指値ラインから引く */
  repair_man?: number | null;
  updated_at?: string;
};

export const VIEWING_STEP_LABEL: Record<ViewingStep, string> = {
  candidate: "内見候補",
  requested: "内見依頼中",
  scheduled: "内見日確定",
  done: "内見済",
};

export const VIEWING_VERDICT_LABEL: Record<ViewingVerdict, string> = {
  go: "買付へ進む",
  hold: "保留",
  pass: "見送り",
};

export type ChecklistItem = { key: string; label: string; hint?: string };

export const VIEWING_CHECKLIST: ChecklistItem[] = [
  { key: "contact_agent", label: "仲介へ内見希望を連絡した", hint: "送信は自分で。KURASHIFT からは送らない" },
  { key: "date_fixed", label: "内見日時が確定した" },
  { key: "hearing_ready", label: "S3 ヒアリング項目を確認した", hint: "下の回答欄に当日メモ" },
  { key: "loan_precheck", label: "融資の当たり（S7）を付けた", hint: "愛知なら名銀ソフト打診の準備だけ" },
  { key: "tools", label: "持ち物（メジャー・ライト・水平器・カメラ）" },
  { key: "building", label: "建物: 雨漏り・傾き・シロアリ・設備年式を見た" },
  { key: "surroundings", label: "周辺: 騒音・日当たり・駐車場・嫌悪施設を見た" },
  { key: "repair_estimate", label: "修繕の概算（S4 業者）を取った／依頼した" },
  { key: "memo_saved", label: "内見メモを記録した" },
];

export type AcqStage =
  | "offer_prep"
  | "offer_submitted"
  | "offer_accepted"
  | "loan_applied"
  | "loan_approved"
  | "contract"
  | "settlement"
  | "handover";

export type AcqStageDef = {
  key: AcqStage;
  label: string;
  /** この段階にいるときの DB status */
  status: "offer" | "loan" | "purchased";
  /** 担当（Grok 社員・部長内蔵・本人） */
  owner: string;
  /** 主な日付フィールドのラベル */
  dateLabel: string;
  checklist: ChecklistItem[];
};

export const ACQ_STAGES: AcqStageDef[] = [
  {
    key: "offer_prep",
    label: "買付準備",
    status: "offer",
    owner: "S6 買付交渉",
    dateLabel: "買付予定日",
    checklist: [
      { key: "price_basis", label: "指値の根拠を整理（S3想定家賃・修繕概算・利回り）" },
      { key: "old_quake", label: "旧耐震なら保険増→約100万円減額論点を入れた" },
      { key: "ops_consult", label: "神大家運営相談の回答を確認した" },
      { key: "funds", label: "頭金・諸費用の出所を確認（次物件キープ枠）" },
      { key: "s6_request", label: "@買付交渉 に材料を渡した" },
    ],
  },
  {
    key: "offer_submitted",
    label: "買付提出",
    status: "offer",
    owner: "本人（仲介へ）",
    dateLabel: "買付提出日",
    checklist: [
      { key: "offer_doc", label: "買付証明書を作成（価格・融資特約・有効期限）" },
      { key: "offer_sent", label: "仲介へ提出した（本人送信）" },
      { key: "offer_saved", label: "提出した買付証明を保存した" },
    ],
  },
  {
    key: "offer_accepted",
    label: "買付通過",
    status: "offer",
    owner: "本人",
    dateLabel: "売渡承諾日",
    checklist: [
      { key: "accepted", label: "売主の承諾（売渡承諾書等）を受け取った" },
      { key: "docs_request", label: "融資用資料（謄本・公図・レントロール等）を依頼した" },
      { key: "s7_request", label: "@融資相談 に打診材料を渡した" },
    ],
  },
  {
    key: "loan_applied",
    label: "融資申込",
    status: "loan",
    owner: "S7 融資相談",
    dateLabel: "融資申込日",
    checklist: [
      { key: "lender_pick", label: "打診先を決めた（/realestate/lenders）" },
      { key: "finance_pack", label: "融資提出パックを作成（/realestate/finance-pack）" },
      { key: "applied", label: "銀行へ申込んだ（承認後に本人送信）" },
      { key: "loan_deadline", label: "融資特約の期限をメモした" },
    ],
  },
  {
    key: "loan_approved",
    label: "融資承認",
    status: "loan",
    owner: "S7 融資相談",
    dateLabel: "融資承認日",
    checklist: [
      { key: "terms", label: "金利・期間・融資額・返済比率を確認した" },
      { key: "cf_check", label: "承認条件で CF 再試算（月CF・返済比率50%目安）" },
      { key: "lp_check", label: "ライフプラン影響を確認（/lifeplan?mode=re_purchase）" },
    ],
  },
  {
    key: "contract",
    label: "売買契約",
    status: "loan",
    owner: "部長（契約リーガル）",
    dateLabel: "契約日",
    checklist: [
      { key: "draft_review", label: "契約書・重要事項説明の案を事前に読んだ" },
      { key: "legal_check", label: "部長の契約リーガルで不利条項を洗い出した" },
      { key: "loan_clause", label: "融資特約・契約不適合責任・引渡し条件を確認" },
      { key: "deposit", label: "手付金を支払った（本人）" },
      { key: "signed", label: "契約締結・書類を保存した" },
    ],
  },
  {
    key: "settlement",
    label: "決済",
    status: "loan",
    owner: "本人＋司法書士",
    dateLabel: "決済日",
    checklist: [
      { key: "fire_insurance", label: "火災保険を手配（部長内蔵の比較）" },
      { key: "money_ready", label: "残代金・諸費用を決済口座へ準備（振替は承認後）" },
      { key: "settlement_statement", label: "精算書（固都税・家賃日割）を確認" },
      { key: "settled", label: "決済・所有権移転を完了した" },
    ],
  },
  {
    key: "handover",
    label: "引渡し・運営開始",
    status: "purchased",
    owner: "S8 ライフライン／S9 管理会社",
    dateLabel: "引渡日",
    checklist: [
      { key: "keys", label: "鍵・書類一式を受け取った" },
      { key: "lifeline", label: "ライフラインの名義変更（S8）" },
      { key: "mgmt", label: "管理会社を決めた（S9）・賃借人へ通知" },
      { key: "property_master", label: "保有物件マスタ（③-C）に登録" },
      { key: "loan_tracker", label: "借入残高トラッカーに登録" },
      { key: "plan", label: "③-A 年間計画に組み込んだ" },
    ],
  },
];

export type AcquisitionState = {
  stage?: AcqStage;
  /** 段階ごとの日付 */
  dates?: Partial<Record<AcqStage, string>>;
  /** `${stage}.${itemKey}` → done */
  checklist?: Record<string, boolean>;
  offer_price_man?: number | null;
  loan_amount_man?: number | null;
  lender?: string | null;
  memo?: string | null;
  updated_at?: string;
};

export function acqStageDef(stage: AcqStage | string | undefined | null) {
  return ACQ_STAGES.find((s) => s.key === stage) || null;
}

export function acqStageIndex(stage: AcqStage | string | undefined | null) {
  return ACQ_STAGES.findIndex((s) => s.key === stage);
}

type SjDeal = {
  status?: string | null;
  price_man?: number | string | null;
  summary_json?: Record<string, unknown> | null;
};

function sjOf(d: SjDeal): Record<string, unknown> {
  return d.summary_json && typeof d.summary_json === "object"
    ? (d.summary_json as Record<string, unknown>)
    : {};
}

export function getViewing(d: SjDeal): ViewingState {
  const v = sjOf(d).viewing;
  return v && typeof v === "object" ? (v as ViewingState) : {};
}

export function getAcquisition(d: SjDeal): AcquisitionState {
  const a = sjOf(d).acquisition;
  const st = (a && typeof a === "object" ? (a as AcquisitionState) : {}) || {};
  if (!st.stage) {
    // 旧データ: status だけ offer/loan/purchased になっている案件
    const s = String(d.status || "");
    if (s === "offer") return { ...st, stage: "offer_prep" };
    if (s === "loan") return { ...st, stage: "loan_applied" };
    if (s === "purchased") return { ...st, stage: "handover" };
  }
  return st;
}

function s3Verdict(d: SjDeal): string {
  const s3 = sjOf(d).s3_investigation;
  if (s3 && typeof s3 === "object") {
    return String((s3 as Record<string, unknown>).verdict || "").toLowerCase();
  }
  return "";
}

/** 今日（JST）YYYY-MM-DD */
export function todayJst(now: Date = new Date()): string {
  const j = new Date(now.getTime() + 9 * 3600 * 1000);
  return j.toISOString().slice(0, 10);
}

export function daysUntil(date: string, today: string = todayJst()): number {
  const a = Date.parse(`${today}T00:00:00Z`);
  const b = Date.parse(`${date}T00:00:00Z`);
  if (Number.isNaN(a) || Number.isNaN(b)) return NaN;
  return Math.round((b - a) / 86400000);
}

/**
 * 内見ボードに載せるか。
 * - 内見の段階を付けた案件（依頼中・日程確定・内見済で未判断）
 * - status=viewing
 * - S3 判定が go / hold で、まだ内見の判断をしていない案件（＝内見に行くか決める候補）
 */
export function isViewingBoardDeal(d: SjDeal): boolean {
  const st = String(d.status || "");
  if (st !== "info" && st !== "viewing") return false;
  const v = getViewing(d);
  if (v.verdict === "pass" || v.verdict === "go") return false;
  if (v.step) return true;
  if (st === "viewing") return true;
  const verdict = s3Verdict(d);
  return verdict === "go" || verdict === "hold";
}

/**
 * 並び: 日程確定（日付順）→ 内見済・未判断 → 依頼中
 * → 候補（机上GO → S3 go → 指値ライン超え・未計算 → hold）
 */
export function viewingBoardRank(d: SjDeal): [number, string] {
  const v = getViewing(d);
  if (v.step === "scheduled") return [0, v.date || "9999-99-99"];
  if (v.step === "done") return [1, v.date || ""];
  if (v.step === "requested") return [2, v.updated_at || ""];
  if (deskGate(d).verdict === "go") return [3, ""];
  const verdict = s3Verdict(d);
  return [verdict === "go" ? 4 : 5, ""];
}

export function filterViewingBoardDeals<T extends SjDeal>(deals: T[]): T[] {
  return deals.filter(isViewingBoardDeal).sort((a, b) => {
    const [ra, ka] = viewingBoardRank(a);
    const [rb, kb] = viewingBoardRank(b);
    if (ra !== rb) return ra - rb;
    return ka.localeCompare(kb);
  });
}

export type NextStep = { label: string; urgent: boolean };

/** 内見フェーズの「次にやること」 */
export function viewingNextStep(d: SjDeal, today: string = todayJst()): NextStep {
  const v = getViewing(d);
  const step = v.step || "candidate";
  if (step === "candidate") {
    const g = deskGate(d);
    if (g.verdict === "go") {
      return { label: `${g.label} → 仲介へ内見依頼`, urgent: true };
    }
    if (g.verdict === "over") {
      return { label: `${g.label} → 指値が通りそうなら内見依頼、無理なら見送り`, urgent: false };
    }
    return { label: "保守の想定家賃を入れて指値ラインを出す → 内見に行くか決める", urgent: false };
  }
  if (step === "requested") {
    return { label: "仲介から日程の返事待ち → 決まったら内見日を入力", urgent: false };
  }
  if (step === "scheduled") {
    if (!v.date) return { label: "内見日を入力", urgent: true };
    const n = daysUntil(v.date, today);
    if (n < 0) return { label: "内見済にして結果（買付へ／保留／見送り）を記録", urgent: true };
    if (n === 0) return { label: "今日内見。ヒアリング項目と持ち物を確認", urgent: true };
    return { label: `内見まであと${n}日。ヒアリング項目を確認`, urgent: n <= 2 };
  }
  return { label: "内見結果を記録して買付へ進むか決める", urgent: true };
}

/** 買付以降の「次にやること」（その段階で未完の最初のチェック項目） */
export function acquisitionNextStep(d: SjDeal): NextStep & { stageLabel: string } {
  const a = getAcquisition(d);
  const def = acqStageDef(a.stage) || ACQ_STAGES[0];
  const cl = a.checklist || {};
  const open = def.checklist.find((it) => !cl[`${def.key}.${it.key}`]);
  if (open) return { stageLabel: def.label, label: open.label, urgent: false };
  const idx = acqStageIndex(def.key);
  const next = ACQ_STAGES[idx + 1];
  if (next) {
    return { stageLabel: def.label, label: `${next.label}へ進める`, urgent: true };
  }
  return { stageLabel: def.label, label: "完了（運営フェーズへ）", urgent: false };
}

export function checklistProgress(
  items: ChecklistItem[],
  done: Record<string, boolean> | undefined,
  prefix = ""
): { done: number; total: number } {
  const d = done || {};
  return {
    done: items.filter((it) => d[`${prefix}${it.key}`]).length,
    total: items.length,
  };
}

/** Grok 社員への依頼文（クリップボード用。送信はしない） */
export function grokRequestText(
  stage: AcqStage | "viewing",
  deal: { title: string; area?: string | null; price_man?: number | null },
  extra?: { memo?: string | null; quake?: string | null }
): string {
  const head = `${deal.title}${deal.area ? ` / ${deal.area}` : ""}${
    deal.price_man != null ? ` / ${deal.price_man}万円` : ""
  }`;
  const memo = extra?.memo ? `\n内見メモ: ${extra.memo}` : "";
  const quake = extra?.quake ? `\n耐震区分: ${extra.quake}` : "";
  switch (stage) {
    case "viewing":
      return `@融資相談 【S7 · 内見前の当たり】${head}\n所在の県と概算から打診先候補と必要書類だけ整理してください（送信しない）。`;
    case "offer_accepted":
    case "loan_applied":
    case "loan_approved":
      return `@融資相談 【S7 · ${acqStageDef(stage)?.label}】${head}${memo}\n/realestate/lenders を見て打診先・提出物・質問リストを整理してください（銀行送信はしない）。`;
    case "contract":
      return `部長、契約リーガルお願いします。【契約前チェック】${head}\n契約書・重説の不利条項と確認質問リストを（断定禁止）。`;
    case "settlement":
      return `部長、火災保険の比較をお願いします。【決済前】${head}`;
    case "handover":
      return `@物件ライフライン 【S8 · 引渡し】${head}\n電気・水道・ガス・ネットの名義変更手順を整理してください。`;
    default:
      return `@買付交渉 【S6 · 買付】${head}${quake}${memo}\n指値の根拠と交渉論点、推奨 go|hold|pass をください。`;
  }
}

export type ProgressBody =
  | { kind: "viewing"; patch: Partial<ViewingState> }
  | { kind: "acquisition"; patch: Partial<AcquisitionState> }
  | { kind: "start_acquisition" };

const VIEWING_STEPS: ViewingStep[] = ["candidate", "requested", "scheduled", "done"];
const VERDICTS: ViewingVerdict[] = ["go", "hold", "pass"];

function mergeBoolMap(
  base: Record<string, boolean> | undefined,
  patch: Record<string, boolean> | undefined
): Record<string, boolean> | undefined {
  if (!patch) return base;
  const out = { ...(base || {}) };
  for (const [k, v] of Object.entries(patch)) out[k] = Boolean(v);
  return out;
}

/**
 * 内見／買付以降の更新を summary_json と status に反映する（純関数）。
 * 不正な値は error を返す。送信系の副作用は持たない。
 */
export function applyProgress(
  current: { status: string; summary_json: Record<string, unknown> },
  body: ProgressBody,
  now: string
):
  | { ok: true; status: string; summary_json: Record<string, unknown>; summary: string }
  | { ok: false; error: string } {
  const sj = { ...current.summary_json };
  let status = current.status || "info";
  if (status === "archived") return { ok: false, error: "アーカイブ済の案件は更新できません" };

  if (body.kind === "viewing") {
    const p = body.patch || {};
    if (p.step != null && !VIEWING_STEPS.includes(p.step)) {
      return { ok: false, error: "step が不正です" };
    }
    if (p.verdict != null && !VERDICTS.includes(p.verdict)) {
      return { ok: false, error: "verdict が不正です" };
    }
    if (p.date && !/^\d{4}-\d{2}-\d{2}$/.test(p.date)) {
      return { ok: false, error: "date は YYYY-MM-DD" };
    }
    const prev = getViewing(current);
    const next: ViewingState = { ...prev };
    if (p.step !== undefined) next.step = p.step;
    if (p.date !== undefined) next.date = p.date || null;
    if (p.time !== undefined) next.time = p.time || null;
    if (p.contact !== undefined) next.contact = p.contact;
    if (p.memo !== undefined) next.memo = p.memo;
    if (p.verdict !== undefined) next.verdict = p.verdict;
    for (const f of ["desk_rent_man", "repair_man"] as const) {
      if (p[f] !== undefined) {
        const n = p[f] == null || (p[f] as unknown) === "" ? null : Number(p[f]);
        if (n != null && (!Number.isFinite(n) || n < 0)) {
          return { ok: false, error: `${f} が数値ではありません` };
        }
        next[f] = n;
      }
    }
    next.checklist = mergeBoolMap(prev.checklist, p.checklist);
    if (p.hearing_answers) {
      next.hearing_answers = { ...(prev.hearing_answers || {}), ...p.hearing_answers };
    }
    // 日付が入れば日程確定に寄せる
    if (p.date && (!next.step || next.step === "candidate" || next.step === "requested")) {
      next.step = "scheduled";
    }
    next.updated_at = now;
    sj.viewing = next;

    let summary = "内見メモを更新";
    if (p.verdict === "pass") {
      if (status === "info" || status === "viewing") status = "passed";
      summary = "内見の結果: 見送り";
    } else if (p.verdict) {
      if (status === "info" || status === "passed") status = "viewing";
      summary = `内見の結果: ${VIEWING_VERDICT_LABEL[p.verdict]}`;
    } else if (next.step && next.step !== "candidate") {
      if (status === "info" || status === "passed") status = "viewing";
      if (p.step) summary = `内見: ${VIEWING_STEP_LABEL[next.step]}`;
      else if (p.date) summary = `内見日: ${p.date}`;
    }
    if (status === "viewing" || status === "info") {
      delete sj.pursue_exclude;
      delete sj.pursue_exclude_at;
    }
    return { ok: true, status, summary_json: sj, summary };
  }

  if (body.kind === "start_acquisition") {
    const prevV = getViewing(current);
    sj.viewing = { ...prevV, verdict: prevV.verdict || "go", updated_at: now };
    const prevA = getAcquisition({ status: "", summary_json: sj });
    sj.acquisition = {
      ...prevA,
      stage: prevA.stage || "offer_prep",
      updated_at: now,
    } satisfies AcquisitionState;
    status = acqStageDef((sj.acquisition as AcquisitionState).stage)!.status;
    delete sj.pursue_exclude;
    delete sj.pursue_exclude_at;
    return { ok: true, status, summary_json: sj, summary: "買付準備を開始" };
  }

  if (body.kind === "acquisition") {
    const p = body.patch || {};
    if (p.stage != null && !acqStageDef(p.stage)) {
      return { ok: false, error: "stage が不正です" };
    }
    const prev = getAcquisition(current);
    const next: AcquisitionState = { ...prev };
    if (p.stage !== undefined) next.stage = p.stage;
    if (p.dates) {
      for (const [k, v] of Object.entries(p.dates)) {
        if (!acqStageDef(k)) return { ok: false, error: `dates.${k} が不正です` };
        if (v && !/^\d{4}-\d{2}-\d{2}$/.test(v)) {
          return { ok: false, error: "日付は YYYY-MM-DD" };
        }
      }
      next.dates = { ...(prev.dates || {}), ...p.dates };
    }
    next.checklist = mergeBoolMap(prev.checklist, p.checklist);
    for (const f of ["offer_price_man", "loan_amount_man"] as const) {
      if (p[f] !== undefined) {
        const n = p[f] == null || (p[f] as unknown) === "" ? null : Number(p[f]);
        if (n != null && !Number.isFinite(n)) return { ok: false, error: `${f} が数値ではありません` };
        next[f] = n;
      }
    }
    if (p.lender !== undefined) next.lender = p.lender;
    if (p.memo !== undefined) next.memo = p.memo;
    if (!next.stage) next.stage = "offer_prep";
    next.updated_at = now;
    sj.acquisition = next;
    const def = acqStageDef(next.stage)!;
    let summary = "買付以降のメモを更新";
    if (p.stage) {
      status = def.status;
      summary = `段階: ${def.label}`;
    }
    return { ok: true, status, summary_json: sj, summary };
  }

  return { ok: false, error: "kind が不正です" };
}
