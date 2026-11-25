/**
 * 土地値率の欄を「率」として読んでよいか。
 * 先頭（「参考」「約」「概ね」を除く）が数字の時だけ率として使う。
 * 「算定不可」「未取得（…404…）」等の文章中の数字は率にしない
 * （Python 側 scripts/jarvis_property_gate_lib.py `_ratio_scenarios` と同じ方針）。
 */
export function usableLandRatioText(raw: string): string | null {
  const s = String(raw ?? "").trim();
  return /^(?:参考|約|概ね)?\s*\d/.test(s) ? s : null;
}
