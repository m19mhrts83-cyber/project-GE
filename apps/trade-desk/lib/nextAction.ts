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
  sony_life: "ソニー生命（真治）",
  sony_life_chikage: "ソニー生命（千景）",
  bloomo: "Bloomo",
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

export function computeNextAction(input: {
  summary: PortfolioWeeklySummary | null;
  themes: ThemeLite[];
  stalledQueued: number;
  annualWindow: boolean;
  annualDone: boolean;
  personalTaxAlert: boolean;
  corporateTaxAlert: boolean;
}): NextAction {
  const fails = failedSources(input.summary);
  if (fails.length > 0) {
    const f = fails[0];
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
