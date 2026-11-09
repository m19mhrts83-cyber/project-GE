/**
 * 下書きレビューの純粋な部品（import なし。tests/draftCore.test.mjs で確かめる）。
 *
 * - diffText: 前後の版の差分（行で揃えてから、変わった行の中を1文字ずつ）
 * - buildRevisePrompt / parseRevise: ダメ出しを AI に渡して直した文面を受け取る
 * - nextLabel: v1 → v2
 */

export type DiffOp = "eq" | "ins" | "del";
export type DiffSeg = { op: DiffOp; text: string };

export type DraftComment = {
  quote: string; // 選んだ箇所（空なら全体へのひとこと）
  start: number | null;
  end: number | null;
  text: string; // ダメ出し（声を文字にしたもの、または入力）
  via: "voice" | "typed";
};

export type DraftVersion = {
  label: string;
  text: string;
  at: string;
  by: "agent" | "ai" | "owner";
  comments?: DraftComment[];
  note?: string;
  changes?: { before: string; after: string; why: string }[];
  reverted?: boolean;
};

const CHAR_CELLS_MAX = 1_000_000;

/** 最長共通部分列で揃える（配列どうし）。戻りは [op, aIndex, bIndex] の列 */
function lcsOps<T>(a: T[], b: T[]): { op: DiffOp; i: number; j: number }[] {
  const n = a.length;
  const m = b.length;
  // 前後の一致を先に削ると表が小さくなる
  let pre = 0;
  while (pre < n && pre < m && a[pre] === b[pre]) pre++;
  let suf = 0;
  while (suf < n - pre && suf < m - pre && a[n - 1 - suf] === b[m - 1 - suf]) suf++;
  const A = a.slice(pre, n - suf);
  const B = b.slice(pre, m - suf);
  const out: { op: DiffOp; i: number; j: number }[] = [];
  for (let k = 0; k < pre; k++) out.push({ op: "eq", i: k, j: k });
  const N = A.length;
  const M = B.length;
  if (N * M > CHAR_CELLS_MAX) {
    for (let i = 0; i < N; i++) out.push({ op: "del", i: pre + i, j: -1 });
    for (let j = 0; j < M; j++) out.push({ op: "ins", i: -1, j: pre + j });
  } else {
    const dp: number[][] = [];
    for (let i = 0; i <= N; i++) dp.push(new Array<number>(M + 1).fill(0));
    for (let i = N - 1; i >= 0; i--) {
      for (let j = M - 1; j >= 0; j--) {
        dp[i][j] = A[i] === B[j] ? dp[i + 1][j + 1] + 1 : Math.max(dp[i + 1][j], dp[i][j + 1]);
      }
    }
    let i = 0;
    let j = 0;
    while (i < N && j < M) {
      if (A[i] === B[j]) {
        out.push({ op: "eq", i: pre + i, j: pre + j });
        i++;
        j++;
      } else if (dp[i + 1][j] >= dp[i][j + 1]) {
        out.push({ op: "del", i: pre + i, j: -1 });
        i++;
      } else {
        out.push({ op: "ins", i: -1, j: pre + j });
        j++;
      }
    }
    while (i < N) out.push({ op: "del", i: pre + i++, j: -1 });
    while (j < M) out.push({ op: "ins", i: -1, j: pre + j++ });
  }
  for (let k = 0; k < suf; k++) out.push({ op: "eq", i: n - suf + k, j: m - suf + k });
  return out;
}

function push(segs: DiffSeg[], op: DiffOp, text: string) {
  if (!text) return;
  const last = segs[segs.length - 1];
  if (last && last.op === op) last.text += text;
  else segs.push({ op, text });
}

function charDiff(a: string, b: string, segs: DiffSeg[]) {
  const A = Array.from(a);
  const B = Array.from(b);
  for (const o of lcsOps(A, B)) {
    if (o.op === "eq") push(segs, "eq", A[o.i]);
    else if (o.op === "del") push(segs, "del", A[o.i]);
    else push(segs, "ins", B[o.j]);
  }
}

/** 前後の差分。行で揃え、消えた行と増えた行が隣り合うところは1文字ずつ比べる */
export function diffText(before: string, after: string): DiffSeg[] {
  const a = before.split(/(?<=\n)/);
  const b = after.split(/(?<=\n)/);
  const ops = lcsOps(a, b);
  const segs: DiffSeg[] = [];
  let k = 0;
  while (k < ops.length) {
    if (ops[k].op === "eq") {
      push(segs, "eq", a[ops[k].i]);
      k++;
      continue;
    }
    let dels = "";
    let inss = "";
    while (k < ops.length && ops[k].op !== "eq") {
      if (ops[k].op === "del") dels += a[ops[k].i];
      else inss += b[ops[k].j];
      k++;
    }
    if (dels && inss) charDiff(dels, inss, segs);
    else if (dels) push(segs, "del", dels);
    else push(segs, "ins", inss);
  }
  return segs;
}

/** 変わった量（0〜1）。判断ログの edit_ratio とは別に、画面の「◯か所」表示用 */
export function diffStats(segs: DiffSeg[]): { places: number; added: number; removed: number } {
  let places = 0;
  let added = 0;
  let removed = 0;
  let inChange = false;
  for (const s of segs) {
    if (s.op === "eq") {
      inChange = false;
      continue;
    }
    if (!inChange) places++;
    inChange = true;
    if (s.op === "ins") added += Array.from(s.text).length;
    else removed += Array.from(s.text).length;
  }
  return { places, added, removed };
}

export function nextLabel(versions: { label: string }[]): string {
  let max = 0;
  for (const v of versions) {
    const m = /^v(\d+)$/.exec(v.label);
    if (m) max = Math.max(max, Number(m[1]));
  }
  return `v${max + 1}`;
}

/** 戻した版を飛ばした、いまの版 */
export function currentVersion<T extends { reverted?: boolean }>(versions: T[]): T | null {
  for (let i = versions.length - 1; i >= 0; i--) if (!versions[i].reverted) return versions[i];
  return null;
}

export function buildRevisePrompt(input: {
  text: string;
  comments: DraftComment[];
  recipient: string;
  channel: string;
  context?: string | null;
}): string {
  const lines = input.comments.map((c, i) => {
    const where = c.quote ? `「${c.quote.slice(0, 300)}」の箇所` : "全体";
    return `${i + 1}. ${where}: ${c.text.slice(0, 600)}`;
  });
  return [
    "あなたは松野さんの文面アシスタントです。松野さんのダメ出しに従って、下書きを直してください。",
    "",
    "守ること:",
    "- ダメ出しされた箇所と、それに伴って直す必要がある所だけを直す。ほかの文はそのまま残す（言い回しを勝手に変えない）",
    "- 声で話したダメ出しなので、言い間違いや「えーと」は意図をくんで読む",
    "- 事実・数字・名前は、ダメ出しで指示がない限り変えない。分からないことを作らない",
    "- 改行や記号（■、・）の形は元に合わせる",
    "",
    `宛先: ${input.recipient}（${input.channel}）`,
    input.context ? `\n前提・守るルール:\n${input.context.slice(0, 3000)}\n` : "",
    "ダメ出し:",
    ...lines,
    "",
    "下書き:",
    "<<<",
    input.text,
    ">>>",
    "",
    'JSON だけを返す。形: {"text":"直した全文","changes":[{"before":"直す前の短い抜き出し","after":"直した後","why":"どのダメ出しに対応したか"}],"rule_hint":"次の下書きにも効きそうな一般化したルール（なければ空）"}',
  ].join("\n");
}

export type ReviseResult = {
  text: string;
  changes: { before: string; after: string; why: string }[];
  ruleHint: string;
};

export function parseRevise(raw: string): ReviseResult | null {
  let s = raw.trim();
  const fence = /```(?:json)?\s*([\s\S]*?)```/.exec(s);
  if (fence) s = fence[1].trim();
  const first = s.indexOf("{");
  const last = s.lastIndexOf("}");
  if (first < 0 || last <= first) return null;
  let obj: unknown;
  try {
    obj = JSON.parse(s.slice(first, last + 1));
  } catch {
    return null;
  }
  if (!obj || typeof obj !== "object") return null;
  const o = obj as Record<string, unknown>;
  if (typeof o.text !== "string" || !o.text.trim()) return null;
  const changes = Array.isArray(o.changes)
    ? o.changes
        .filter((c): c is Record<string, unknown> => !!c && typeof c === "object")
        .map((c) => ({ before: String(c.before ?? ""), after: String(c.after ?? ""), why: String(c.why ?? "") }))
        .slice(0, 30)
    : [];
  return { text: o.text, changes, ruleHint: typeof o.rule_hint === "string" ? o.rule_hint.trim() : "" };
}

/** 判断ログの note（松野さんの言葉）。箇所つきで短く */
export function commentsNote(comments: DraftComment[]): string {
  return comments
    .map((c) => (c.quote ? `「${c.quote.slice(0, 60)}」→ ${c.text}` : c.text))
    .join(" / ")
    .slice(0, 2000);
}
