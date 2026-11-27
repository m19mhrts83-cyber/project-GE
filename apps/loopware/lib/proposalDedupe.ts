/**
 * 312「提案を仕分ける」の候補を、同じ案件が何度も出ないように整える（純粋関数。テストあり）。
 *
 * 重複が出ていた理由（2026-11-27 調べ）:
 *   1. 判断が「その日だけ」のお題（prop-<日付>-miss-<番号>）だったので、拾い漏れスキャンが同じ候補を置き続けると
 *      翌日もまた同じ案件が出た（11/14 の3件を 11/20〜11/27 に4回「見送る」していた）。
 *   2. 候補の id が並び順の番号（miss-1, miss-2…）で、中身が入れ替わると別の案件に判断がずれた。
 *   3. Journal を3日分読むので、同じ行が日付違いで並ぶことがあった。
 * ここでは
 *   - 中身（ソース＋正規化した本文。やり取りはフォルダも）から決まる固定の id にする
 *   - 同じ中身の候補は1枚にまとめる（日付・フォルダは「・」で並べる）
 *   - 前に「採る／見送る」を決めた候補は出さない（保留は次の日も出し、前回保留と添える）
 */

export type RawCandidate = {
  source?: string;
  folder?: string;
  snippet?: string;
  hypothesis?: string;
  ref?: string;
};

export type MissCandidate = {
  id: string;
  source: string;
  folder: string;
  snippet: string;
  hypothesis: string;
  ref?: string;
  /** まとめた件数（2以上なら同じ中身が複数あった） */
  merged: number;
  /** 前回の判断（保留だけが残る） */
  lastChoice?: "hold";
};

/** 比べるための本文。全角半角・空白・先頭の記号・末尾の句読点や絵文字の違いを無視する */
export function normSnippet(s: string): string {
  return String(s || "")
    .normalize("NFKC")
    .replace(/^[\s・•\-*#>]+/u, "")
    .replace(/[\s　]+/g, "")
    .replace(/[。．.!！🙇]+$/u, "")
    .toLowerCase();
}

/** 同じ案件かどうかの鍵。Journal は日付（folder）が違っても同じ行なら同じ案件 */
export function candidateKey(c: RawCandidate): string {
  const src = String(c.source || "");
  const scope = src === "yoritoori" ? String(c.folder || "") : "";
  return `${src}|${scope}|${normSnippet(String(c.snippet || ""))}`;
}

/** 鍵から短い固定 id（FNV-1a 32bit） */
export function stableId(key: string): string {
  let h = 0x811c9dc5;
  for (let i = 0; i < key.length; i++) {
    h ^= key.charCodeAt(i);
    h = Math.imul(h, 0x01000193) >>> 0;
  }
  return `miss-${h.toString(36)}`;
}

/** サーバの判断ログ（task_loop_topics.topic_text）と同じ書き方。ProposeClient の保存と揃える */
export function proposalTopicText(source: string, snippet: string): string {
  return `[提案:${source}] ${snippet}\n→ ${snippet.slice(0, 40)}`;
}

/** 同じ中身をまとめる。順番は最初に出た位置のまま */
export function mergeCandidates(list: RawCandidate[]): (MissCandidate & { variants: string[] })[] {
  const byKey = new Map<string, MissCandidate & { variants: string[] }>();
  for (const c of list) {
    const snippet = String(c.snippet || "").trim();
    if (!snippet) continue;
    const key = candidateKey(c);
    const hit = byKey.get(key);
    if (hit) {
      hit.merged += 1;
      const f = String(c.folder || "");
      if (f && !hit.folder.split("・").includes(f)) hit.folder = `${hit.folder}・${f}`;
      if (!hit.variants.includes(snippet)) hit.variants.push(snippet);
      continue;
    }
    byKey.set(key, {
      id: stableId(key),
      source: String(c.source || ""),
      folder: String(c.folder || ""),
      snippet,
      hypothesis: String(c.hypothesis || ""),
      ref: c.ref,
      merged: 1,
      variants: [snippet],
    });
  }
  return [...byKey.values()];
}

export type PastChoice = "take" | "skip" | "hold" | string;

/**
 * 前の判断で外す。past は topic_text → 最新の choice。
 * 採る・見送るを決めたものは出さない。保留は出す（前回保留と印）。
 */
export function dropDecided(
  merged: (MissCandidate & { variants: string[] })[],
  past: Map<string, PastChoice>,
): { candidates: MissCandidate[]; excluded: number } {
  const candidates: MissCandidate[] = [];
  let excluded = 0;
  for (const m of merged) {
    const choices = m.variants.map((v) => past.get(proposalTopicText(m.source, v))).filter(Boolean) as PastChoice[];
    if (choices.some((c) => c !== "hold")) {
      excluded += 1;
      continue;
    }
    const { variants: _v, ...rest } = m;
    void _v;
    candidates.push(choices.length ? { ...rest, lastChoice: "hold" } : rest);
  }
  return { candidates, excluded };
}

/** 問い合わせに使う topic_text の一覧 */
export function topicTextsOf(merged: { source: string; variants: string[] }[]): string[] {
  return merged.flatMap((m) => m.variants.map((v) => proposalTopicText(m.source, v)));
}
