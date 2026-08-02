/** digest カード要約を読みやすいブロックに分割 */

export type DigestBullet = {
  title: string;
  detail: string | null;
};

export type ParsedDigestSummary = {
  question: string | null;
  bullets: DigestBullet[];
  leftover: string | null;
};

function stripOuterParens(s: string): string {
  const t = s.trim();
  if (t.startsWith("（") && t.endsWith("）")) return t.slice(1, -1).trim();
  if (t.startsWith("(") && t.endsWith(")")) return t.slice(1, -1).trim();
  return t;
}

export function parseDigestSummary(
  summary: string | null | undefined,
  payload?: Record<string, unknown> | null,
): ParsedDigestSummary {
  const fromPayload = payload?.bullets;
  if (Array.isArray(fromPayload) && fromPayload.length) {
    const bullets: DigestBullet[] = fromPayload
      .map((b) => {
        if (typeof b === "string") {
          return splitBulletLine(b.startsWith("- ") ? b.slice(2) : b);
        }
        if (b && typeof b === "object") {
          const o = b as { title?: unknown; detail?: unknown };
          return {
            title: String(o.title || "").trim() || "（無題）",
            detail: o.detail != null ? String(o.detail).trim() || null : null,
          };
        }
        return null;
      })
      .filter((x): x is DigestBullet => Boolean(x?.title));
    const q =
      typeof payload?.question === "string" ? payload.question.trim() : null;
    return { question: q, bullets, leftover: null };
  }

  const raw = (summary || "").replace(/\r\n/g, "\n").trim();
  if (!raw) return { question: null, bullets: [], leftover: null };

  // 改行が潰れている場合: 「- 」で分割を試みる
  let lines = raw.split("\n").map((l) => l.trim()).filter(Boolean);
  if (lines.length === 1 && (raw.match(/ - /g) || []).length >= 1) {
    const parts = raw.split(/\s+-\s+/);
    lines = [parts[0], ...parts.slice(1).map((p) => `- ${p.trim()}`)];
  }

  const questionParts: string[] = [];
  const bulletLines: string[] = [];
  for (const line of lines) {
    if (line.startsWith("- ") || line.startsWith("* ")) {
      bulletLines.push(line.replace(/^[-*]\s+/, ""));
    } else if (bulletLines.length === 0) {
      questionParts.push(line);
    } else {
      // 箇条書きの続き行
      const last = bulletLines[bulletLines.length - 1];
      bulletLines[bulletLines.length - 1] = `${last} ${line}`;
    }
  }

  return {
    question: questionParts.join(" ").trim() || null,
    bullets: bulletLines.map(splitBulletLine),
    leftover: null,
  };
}

function splitBulletLine(line: string): DigestBullet {
  const s = line.trim();
  const m = s.match(/^(.+?)[（(](.+)[）)]\s*$/);
  if (m) {
    return {
      title: m[1].trim(),
      detail: stripOuterParens(`（${m[2]}）`),
    };
  }
  return { title: s, detail: null };
}

/** `**bold**` を簡易表示用に分割 */
export function splitInlineBold(
  text: string,
): { text: string; bold?: boolean }[] {
  const parts: { text: string; bold?: boolean }[] = [];
  const re = /\*\*(.+?)\*\*/g;
  let last = 0;
  let m: RegExpExecArray | null;
  while ((m = re.exec(text))) {
    if (m.index > last) parts.push({ text: text.slice(last, m.index) });
    parts.push({ text: m[1], bold: true });
    last = m.index + m[0].length;
  }
  if (last < text.length) parts.push({ text: text.slice(last) });
  return parts.length ? parts : [{ text }];
}
