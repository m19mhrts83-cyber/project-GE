/** 千三つ — match_score の見せ方 */

export type ScoreBand = "high" | "mid" | "low" | "none";

export function scoreBand(score: number | null | undefined): ScoreBand {
  if (typeof score !== "number" || Number.isNaN(score)) return "none";
  if (score >= 7) return "high";
  if (score >= 4) return "mid";
  return "low";
}

export function scoreBandLabel(band: ScoreBand): string {
  switch (band) {
    case "high":
      return "高";
    case "mid":
      return "中";
    case "low":
      return "低";
    default:
      return "—";
  }
}

export function formatMatchScore(score: number | null | undefined): string {
  if (typeof score !== "number" || Number.isNaN(score)) return "—";
  return Number.isInteger(score) ? String(score) : score.toFixed(1);
}

/** hits の先頭を短く（エリア・戸建・価格帯など） */
export function scoreHitsPreview(
  hits: unknown,
  max = 4
): string {
  if (!Array.isArray(hits)) return "";
  const parts = hits
    .filter((h): h is string => typeof h === "string" && h.trim().length > 0)
    .map((h) => h.trim())
    .filter((h) => !h.endsWith("-") && h !== "grok")
    .slice(0, max);
  return parts.join("·");
}

export function scoreCellStyle(band: ScoreBand): Record<string, string | number> {
  const base: Record<string, string | number> = {
    fontVariantNumeric: "tabular-nums",
    fontWeight: 600,
    whiteSpace: "nowrap",
  };
  if (band === "high") return { ...base, color: "#047857" };
  if (band === "mid") return { ...base, color: "#b45309" };
  if (band === "low") return { ...base, color: "#6b7280" };
  return base;
}
