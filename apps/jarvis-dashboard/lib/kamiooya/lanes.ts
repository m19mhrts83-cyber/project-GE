/** レーン既定で神大家ナレッジを参照するか（副作用なし） */

export function defaultUseKamiooyaKnowledge(
  lane: string | null | undefined,
): boolean {
  const l = (lane || "").toLowerCase();
  return (
    l === "kamiooya" ||
    l === "kanji" ||
    l === "kodate" ||
    l === "properties" ||
    l.includes("kamiooya") ||
    l.includes("kanji") ||
    l.includes("kodate")
  );
}
