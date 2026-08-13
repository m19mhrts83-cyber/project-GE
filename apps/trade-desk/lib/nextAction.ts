/** ホーム「いまやること」— 優先順位は改善プラン QA 固定 */

export type WeeklySourceBrief = {
  status?: string;
  reason?: string;
};

export type PortfolioWeeklySummary = {
  iso_week?: string;
  ok?: number;
  error?: number;
  skipped?: number;
  last_full_ok?: boolean | null;
  last_full_at?: string | null;
  finished_at?: string | null;
  sources?: Record<string, WeeklySourceBrief>;
};

export type NextAction = {
  label: string;
  href: string;
  level: "warn" | "info" | "ok";
};

const SOURCE_LABEL: Record<string, string> = {
  sony_life: "ソニー生命（真治・一時払）",
  sony_life_sovani: "ソニー生命（真治・SOVANI）",
  sony_life_chikage: "ソニー生命（千景）",
  bloomo: "Bloomo評価取得",
  bloomo_zaim: "Bloomo→Zaim財務反映",
  sbi_index: "SBIインデックス",
  liquidity_weekly: "銀行・流動性",
  axa_life: "アクサ生命",
};

export function parseWeeklySummary(raw: string | null | undefined): PortfolioWeeklySummary | null {
  if (!raw) return null;
  try {
    return JSON.parse(raw) as PortfolioWeeklySummary;
  } catch {
    return null;
  }
}

export function failedSources(
  summary: PortfolioWeeklySummary | null
): { id: string; label: string; reason: string }[] {
  if (!summary?.sources) return [];
  const out: { id: string; label: string; reason: string }[] = [];
  for (const [id, rec] of Object.entries(summary.sources)) {
    if ((rec?.status || "") === "error") {
      out.push({
        id,
        label: SOURCE_LABEL[id] || id,
        reason: rec.reason || "",
      });
    }
  }
  return out;
}

type ThemeLite = { id: string; status: string; title: string };
type JobLite = { id: string; status: string; created_at: string; job_type: string };

export type DealFunnelBrief = {
  info: number;
  viewing: number;
};

export type CardDebitWatchBrief = {
  updated_at?: string;
  smbc_balance_jpy?: number | null;
  olive_infinite?: {
    amount_jpy?: number | null;
    due_date?: string | null;
    amount_pending?: boolean;
    smbc_shortfall?: number | null;
    notice_date?: string | null;
  };
  top_alert?: {
    card_id?: string;
    label?: string;
    level?: string;
    reason?: string;
    amount_jpy?: number | null;
    due_date?: string | null;
    smbc_shortfall?: number | null;
    href?: string;
  } | null;
  money_ops_href?: string;
};

export function parseCardDebitWatch(
  raw: string | null | undefined
): CardDebitWatchBrief | null {
  if (!raw) return null;
  try {
    return JSON.parse(raw) as CardDebitWatchBrief;
  } catch {
    return null;
  }
}

export function computeNextAction(input: {
  summary: PortfolioWeeklySummary | null;
  themes: ThemeLite[];
  stalledQueued: number;
  annualWindow: boolean;
  annualDone: boolean;
  personalTaxAlert: boolean;
  corporateTaxAlert: boolean;
  /** Phase C: 千三つに情報だけ溜まっている */
  dealFunnel?: DealFunnelBrief | null;
  /** Phase C: 買い進め canonical が無い */
  buyPlanMissing?: boolean;
  /** カード引落（Infinite 本線） */
  cardDebit?: CardDebitWatchBrief | null;
}): NextAction {
  const debit = input.cardDebit?.top_alert;
  if (debit && (debit.level === "warn" || debit.level === "attention")) {
    const label = debit.label || "カード引落";
    const reason = debit.reason || "要確認";
    return {
      level: debit.level === "warn" ? "warn" : "info",
      label: `${label}: ${reason} → 寄せ計画`,
      href: debit.href || input.cardDebit?.money_ops_href || "/money-ops",
    };
  }

  const fails = failedSources(input.summary);
  if (fails.length > 0) {
    const f = fails[0];
    // Bloomo 評価は取れて Zaim 差分だけ失敗、が典型。資産画面に行っても操作がない
    if (f.id === "bloomo_zaim") {
      const accountMiss = /口座/.test(f.reason);
      return {
        level: "warn",
        label: accountMiss
          ? "Bloomo評価は取得済み。Zaim財務への差分登録だけ失敗（口座名ゆれ）。週次が自動再試行します"
          : "Bloomo評価は取得済み。Zaim財務への差分登録に失敗。Jarvisに「Bloomo財務を直して」",
        href: "/jobs",
      };
    }
    return {
      level: "warn",
      label: `週次の${f.label}が失敗しています（再実行または確認）`,
      href: "/portfolio",
    };
  }
  if (input.stalledQueued > 0) {
    return {
      level: "warn",
      label: `ジョブが ${input.stalledQueued} 件、30分超キュー滞留（Mac worker を確認）`,
      href: "/jobs",
    };
  }
  const consulting = input.themes.find((t) => t.status === "consulting");
  if (consulting) {
    return {
      level: "info",
      label: `相談内容を確認して承認: ${consulting.title}`,
      href: `/themes/${consulting.id}`,
    };
  }
  const approved = input.themes.find((t) => t.status === "approved");
  if (approved) {
    return {
      level: "info",
      label: `完走アシストをキュー: ${approved.title}`,
      href: `/themes/${approved.id}`,
    };
  }
  if (input.buyPlanMissing) {
    return {
      level: "warn",
      label: "買い進めプランが未取込です（Excel再取込）",
      href: "/realestate/buy-plan",
    };
  }
  if (input.annualWindow && !input.annualDone) {
    return {
      level: "info",
      label: "ライフプラン年次更新を開く",
      href: "/lifeplan/budget?mode=annual",
    };
  }
  if (input.corporateTaxAlert) {
    return {
      level: "warn",
      label: "法人確定申告のメールをそろそろ取り込む",
      href: "/tax",
    };
  }
  if (input.personalTaxAlert) {
    return {
      level: "info",
      label: "個人の確定申告をそろそろ回す",
      href: "/tax",
    };
  }
  const funnel = input.dealFunnel;
  if (funnel && funnel.info >= 8 && funnel.viewing === 0) {
    return {
      level: "info",
      label: `千三つ: 情報 ${funnel.info} 件が未内見（1件でも進める）`,
      href: "/realestate/deals",
    };
  }
  if (funnel && funnel.info >= 12) {
    return {
      level: "info",
      label: `千三つ: 情報 ${funnel.info} 件 — 内見候補を絞る`,
      href: "/realestate/deals",
    };
  }
  return {
    level: "ok",
    label: "特になし（週次は自動。気になったら手動更新）",
    href: "/",
  };
}

export function countStalledQueued(jobs: JobLite[], olderThanMs = 30 * 60 * 1000): number {
  const now = Date.now();
  return jobs.filter((j) => {
    if (j.status !== "queued") return false;
    const t = Date.parse(j.created_at);
    return Number.isFinite(t) && now - t > olderThanMs;
  }).length;
}
