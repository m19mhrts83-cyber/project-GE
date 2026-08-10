/**
 * 神大家ポイント配点基準（成果報告の観点注入・自己チェック用）
 * CSV 正本: 215_kamiooya/.../採点自動化/02_得点基準_seed.csv
 * Dashboard 写し: ./scoring_seed.csv （更新時は正本からコピー）
 */

import { readFileSync } from "fs";
import { join } from "path";
import type {
  ResultScoringHints,
  ScoringSuggestion,
} from "./types";

export type { ResultScoringHints, ScoringSuggestion };

export type ScoringRule = {
  ruleId: string;
  major: string;
  mid: string;
  level: number;
  viewpoint: string;
  criteria: string;
  points: number;
  keywords: string[];
  enabled: boolean;
};

const DISCLAIMER =
  "運営採点の保証ではない。投稿前の自己チェックです（本文に点数・ルールIDは書かない）。";

function splitCsvLine(line: string): string[] {
  const out: string[] = [];
  let cur = "";
  let inQuotes = false;
  for (let i = 0; i < line.length; i++) {
    const ch = line[i];
    if (ch === '"') {
      if (inQuotes && line[i + 1] === '"') {
        cur += '"';
        i++;
      } else {
        inQuotes = !inQuotes;
      }
      continue;
    }
    if (ch === "," && !inQuotes) {
      out.push(cur);
      cur = "";
      continue;
    }
    cur += ch;
  }
  out.push(cur);
  return out;
}

export function parseScoringCsv(text: string): ScoringRule[] {
  const lines = text
    .split(/\r?\n/)
    .map((l) => l.trim())
    .filter((l) => l && !l.startsWith("#"));
  if (lines.length < 2) return [];
  const header = splitCsvLine(lines[0]);
  const idx = (name: string) => header.indexOf(name);
  const iId = idx("ルールID");
  const iMajor = idx("大分類");
  const iMid = idx("中分類");
  const iLv = idx("レベル");
  const iView = idx("観点");
  const iCrit = idx("判定基準");
  const iPts = idx("点数");
  const iKw = idx("キーワード補助");
  const iEn = idx("有効");
  if ([iId, iMajor, iMid, iLv, iView, iCrit, iPts, iKw, iEn].some((n) => n < 0)) {
    return [];
  }

  const rules: ScoringRule[] = [];
  for (const line of lines.slice(1)) {
    const cols = splitCsvLine(line);
    const enabled = String(cols[iEn] || "")
      .trim()
      .toUpperCase();
    if (enabled !== "TRUE" && enabled !== "1" && enabled !== "YES") continue;
    const kwRaw = cols[iKw] || "";
    const keywords = kwRaw
      .split(/[,、]/)
      .map((k) => k.trim())
      .filter(Boolean);
    rules.push({
      ruleId: String(cols[iId] || "").trim(),
      major: String(cols[iMajor] || "").trim(),
      mid: String(cols[iMid] || "").trim(),
      level: Number(cols[iLv] || 0) || 0,
      viewpoint: String(cols[iView] || "").trim(),
      criteria: String(cols[iCrit] || "").trim(),
      points: Number(cols[iPts] || 0) || 0,
      keywords,
      enabled: true,
    });
  }
  return rules;
}

let cachedRules: ScoringRule[] | null = null;

/** 有効行のみ（サーバ側。CSV を lib/glucon/scoring_seed.csv から読む） */
export function loadScoringRules(): ScoringRule[] {
  if (cachedRules) return cachedRules;
  const path = join(process.cwd(), "lib/glucon/scoring_seed.csv");
  const text = readFileSync(path, "utf8");
  cachedRules = parseScoringCsv(text);
  return cachedRules;
}

/** Gemini 向けに中分類＋Lv＋判定基準＋点数を短く列挙 */
export function formatRubricForPrompt(rules: ScoringRule[]): string {
  const byMid = new Map<string, ScoringRule[]>();
  for (const r of rules) {
    const list = byMid.get(r.mid) || [];
    list.push(r);
    byMid.set(r.mid, list);
  }
  const blocks: string[] = [];
  for (const [mid, list] of byMid) {
    const lines = list
      .slice()
      .sort((a, b) => a.level - b.level)
      .map(
        (r) =>
          `  Lv${r.level}（目安${r.points}点・${r.viewpoint}）: ${r.criteria}`,
      );
    blocks.push(`- ${mid}\n${lines.join("\n")}`);
  }
  return blocks.join("\n");
}

/** キーワード補助で候補ルールを数件（UI用・断定しない） */
export function suggestRulesFromText(
  text: string,
  rules?: ScoringRule[],
  limit = 5,
): ScoringSuggestion[] {
  const src = rules || loadScoringRules();
  const t = (text || "").trim();
  if (!t || t.includes("該当する成果報告なし")) return [];

  const scored: ScoringSuggestion[] = [];
  for (const r of src) {
    const matched = r.keywords.filter((k) => k && t.includes(k));
    if (!matched.length) continue;
    scored.push({
      ruleId: r.ruleId,
      mid: r.mid,
      level: r.level,
      viewpoint: r.viewpoint,
      points: r.points,
      matchedKeywords: matched,
    });
  }
  scored.sort((a, b) => {
    if (b.matchedKeywords.length !== a.matchedKeywords.length) {
      return b.matchedKeywords.length - a.matchedKeywords.length;
    }
    if (b.level !== a.level) return b.level - a.level;
    return b.points - a.points;
  });
  // 同じ中分類は最高一致の1件に寄せる
  const seenMid = new Set<string>();
  const out: ScoringSuggestion[] = [];
  for (const s of scored) {
    if (seenMid.has(s.mid)) continue;
    seenMid.add(s.mid);
    out.push(s);
    if (out.length >= limit) break;
  }
  return out;
}

/** 不足しがちな観点（ヒューリスティック） */
export function findMissingAspects(text: string): string[] {
  const t = (text || "").trim();
  if (!t || t.includes("該当する成果報告なし")) return [];
  const gaps: string[] = [];
  const hasNumber =
    /\d/.test(t) ||
    /[０-９]/.test(t) ||
    /万円|円|％|%|利回り|金利|年|月|日/.test(t);
  if (!hasNumber) {
    gaps.push("数字（金額・利回り・融資条件・期間・削減額など）が見当たりません");
  }
  const hasProcess =
    /手順|やったこと|方法|交渉|見積|比較|ステージング|指値|募集|内見|再現/.test(
      t,
    ) || t.split(/\n/).filter((l) => l.trim().startsWith("・")).length >= 3;
  if (!hasProcess) {
    gaps.push("手順・再現できる粒度の記述が薄い可能性があります");
  }
  if (!/■|【/.test(t)) {
    gaps.push("カテゴリが分かる題名（■【…】）が無い可能性があります");
  }
  return gaps;
}

export function buildResultScoringHints(text: string): ResultScoringHints {
  const rules = loadScoringRules();
  return {
    suggestions: suggestRulesFromText(text, rules),
    gaps: findMissingAspects(text),
    disclaimer: DISCLAIMER,
  };
}
