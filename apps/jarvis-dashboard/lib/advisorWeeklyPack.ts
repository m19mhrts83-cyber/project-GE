import {
  fetchKinshuMeetingSummaries,
  type MeetingNoteDetail,
} from "@/lib/genspark/meeting";

export type PackResult = {
  start: string;
  end: string;
  markdown: string;
  sb_count: number;
  sb_error?: string;
};

type Routing = {
  teams?: Record<string, { keywords?: string[] }>;
  unclassified_team?: string;
};

/** 直近完了金締（土〜金）。JST。 */
export function kinshuRange(now = new Date()): { start: string; end: string } {
  const ymd = new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Tokyo",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(now);
  const localNoon = new Date(`${ymd}T12:00:00+09:00`);
  const short = new Intl.DateTimeFormat("en-US", {
    timeZone: "Asia/Tokyo",
    weekday: "short",
  }).format(localNoon);
  const map: Record<string, number> = {
    Sun: 0,
    Mon: 1,
    Tue: 2,
    Wed: 3,
    Thu: 4,
    Fri: 5,
    Sat: 6,
  };
  const jstWd = map[short] ?? 0;
  const daysSinceFri = (jstWd - 5 + 7) % 7;
  const endDate = new Date(localNoon);
  endDate.setUTCDate(endDate.getUTCDate() - daysSinceFri);
  const startDate = new Date(endDate);
  startDate.setUTCDate(startDate.getUTCDate() - 6);
  const iso = (x: Date) =>
    new Intl.DateTimeFormat("en-CA", {
      timeZone: "Asia/Tokyo",
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
    }).format(x);
  return { start: iso(startDate), end: iso(endDate) };
}

function defaultRouting(): Routing {
  return {
    unclassified_team: "hawk",
    teams: {
      family: {
        keywords: [
          "家族会議",
          "千景",
          "珠己",
          "円香",
          "紗和",
          "まどか",
          "塾",
          "日能研",
          "空手",
          "遊愛会",
          "高校",
        ],
      },
      somu: {
        keywords: ["総務", "企画", "作戦", "今井", "大原", "蜂谷", "中島", "太田", "組織運営"],
      },
      partner_dx: {
        keywords: ["Shift", "シフト", "ワールドインテック", "WI", "WT", "代理店", "板垣"],
      },
      app_dev: {
        keywords: ["アプリ", "ダッシュボード", "KURASHIFT", "Vercel", "Todoist", "実装", "PR"],
      },
    },
  };
}

function labelTeams(title: string, summary: string, routing: Routing): string[] {
  const blob = `${title}\n${summary}`.toLowerCase();
  const hit: string[] = [];
  for (const [team, spec] of Object.entries(routing.teams || {})) {
    for (const kw of spec.keywords || []) {
      if (blob.includes(String(kw).toLowerCase())) {
        hit.push(team);
        break;
      }
    }
  }
  if (!hit.length) hit.push(routing.unclassified_team || "hawk");
  return hit;
}

function renderPack(
  start: string,
  end: string,
  notes: MeetingNoteDetail[],
  sbError?: string,
): string {
  const routing = defaultRouting();
  const lines: string[] = [
    `# 週次材料パック · 金締 ${start}〜${end}`,
    `生成: ${new Date().toISOString()} · Cloud advisor-weekly-pack`,
    "",
    "## A. SecondBrain（要約のみ・全文なし）",
  ];
  if (sbError) {
    lines.push(`- SB: 取得不可（${sbError}）`);
  } else {
    lines.push(`- 件数: ${notes.length}`);
    for (const n of notes) {
      const labels = labelTeams(n.title || "", n.summary || "", routing).join(",");
      lines.push(
        `- ${(n.created_at || "").slice(0, 10)} | ${n.duration_human || "—"} | **${n.title || "(無題)"}** \`[${labels}]\``,
      );
      lines.push(`  - id: \`${n.id}\``);
      lines.push(
        `  - summary: ${(n.summary || "（なし）").replace(/\n/g, " ").slice(0, 400)}`,
      );
    }
  }
  lines.push(
    "",
    "## B. パートナーやり取り（差分）",
    "- （Cloud本線では未取得。Mac `jarvis_advisor_weekly_pack.py` または後続で追記）",
    "",
    "## C. アプリ更新",
    "- （Cloud本線では未取得。Macスクリプト側で追記）",
    "",
    "## D. Journalギャップ候補（必須・断定しない）",
    "- Cloud取得分のSBタイトルを Journal と照合するのは統括／アドバイザー判断。機械候補は Mac パック参照可。",
    "",
    "## E. チーム別フォーカス（SB抜粋）",
  );
  const byTeam: Record<string, MeetingNoteDetail[]> = {
    family: [],
    somu: [],
    partner_dx: [],
    app_dev: [],
  };
  for (const n of notes) {
    for (const lab of labelTeams(n.title || "", n.summary || "", routing)) {
      if (byTeam[lab]) byTeam[lab].push(n);
    }
  }
  for (const team of ["family", "somu", "partner_dx", "app_dev"] as const) {
    lines.push(`### ${team}`);
    const items = byTeam[team];
    if (!items.length) lines.push("- （該当SBなし）");
    else {
      for (const n of items.slice(0, 8)) {
        lines.push(`- ${(n.created_at || "").slice(0, 10)} ${n.title}`);
      }
    }
  }
  lines.push(
    "",
    "---",
    "使い方: ★Journalは理解の正本。全部の出来事が載っている前提にしない。",
    "返答に「Journalに無い重要」節を必ず1つ（該当なしならギャップなしと明記）。",
    "",
  );
  return lines.join("\n");
}

export async function buildAdvisorWeeklyPack(opts?: {
  end?: string;
}): Promise<PackResult> {
  let start: string;
  let end: string;
  if (opts?.end) {
    end = opts.end;
    const e = new Date(`${end}T12:00:00+09:00`);
    const s = new Date(e.getTime() - 6 * 24 * 60 * 60 * 1000);
    start = new Intl.DateTimeFormat("en-CA", {
      timeZone: "Asia/Tokyo",
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
    }).format(s);
  } else {
    ({ start, end } = kinshuRange());
  }
  const { notes, error } = await fetchKinshuMeetingSummaries(start, end);
  const markdown = renderPack(start, end, notes, error);
  return {
    start,
    end,
    markdown,
    sb_count: notes.length,
    sb_error: error,
  };
}
