import type { ReactNode } from "react";

type Block =
  | { t: "h"; level: 1 | 2 | 3; text: string }
  | { t: "ul"; items: string[] }
  | { t: "ol"; items: string[] }
  | { t: "pre"; text: string }
  | { t: "p"; text: string }
  | { t: "bq"; text: string }
  | { t: "hr" };

function inlineParts(text: string, keyPrefix: string): ReactNode[] {
  const nodes: ReactNode[] = [];
  const re = /(\*\*[^*]+\*\*|`[^`]+`|\*[^*]+\*)/g;
  let last = 0;
  let i = 0;
  let m: RegExpExecArray | null;
  while ((m = re.exec(text))) {
    if (m.index > last) {
      nodes.push(text.slice(last, m.index));
    }
    const tok = m[0];
    if (tok.startsWith("**")) {
      nodes.push(<strong key={`${keyPrefix}-b${i++}`}>{tok.slice(2, -2)}</strong>);
    } else if (tok.startsWith("`")) {
      nodes.push(<code key={`${keyPrefix}-c${i++}`}>{tok.slice(1, -1)}</code>);
    } else {
      nodes.push(<em key={`${keyPrefix}-i${i++}`}>{tok.slice(1, -1)}</em>);
    }
    last = m.index + tok.length;
  }
  if (last < text.length) nodes.push(text.slice(last));
  return nodes;
}

function parseBlocks(source: string): Block[] {
  const lines = source.replace(/\r\n/g, "\n").split("\n");
  const blocks: Block[] = [];
  let i = 0;
  while (i < lines.length) {
    const line = lines[i];
    const trimmed = line.trim();

    if (trimmed.startsWith("```")) {
      const buf: string[] = [];
      i += 1;
      while (i < lines.length && !lines[i].trim().startsWith("```")) {
        buf.push(lines[i]);
        i += 1;
      }
      if (i < lines.length) i += 1;
      blocks.push({ t: "pre", text: buf.join("\n") });
      continue;
    }

    if (trimmed === "---" || trimmed === "***") {
      blocks.push({ t: "hr" });
      i += 1;
      continue;
    }

    const hm = /^(#{1,3})\s+(.+)$/.exec(trimmed);
    if (hm) {
      const level = Math.min(3, hm[1].length) as 1 | 2 | 3;
      blocks.push({ t: "h", level, text: hm[2].trim() });
      i += 1;
      continue;
    }

    if (/^[-*]\s+/.test(trimmed)) {
      const items: string[] = [];
      while (i < lines.length && /^[-*]\s+/.test(lines[i].trim())) {
        items.push(lines[i].trim().replace(/^[-*]\s+/, ""));
        i += 1;
      }
      blocks.push({ t: "ul", items });
      continue;
    }

    if (/^\d+\.\s+/.test(trimmed)) {
      const items: string[] = [];
      while (i < lines.length && /^\d+\.\s+/.test(lines[i].trim())) {
        items.push(lines[i].trim().replace(/^\d+\.\s+/, ""));
        i += 1;
      }
      blocks.push({ t: "ol", items });
      continue;
    }

    if (trimmed.startsWith(">")) {
      const buf: string[] = [];
      while (i < lines.length && lines[i].trim().startsWith(">")) {
        buf.push(lines[i].trim().replace(/^>\s?/, ""));
        i += 1;
      }
      blocks.push({ t: "bq", text: buf.join("\n") });
      continue;
    }

    if (!trimmed) {
      i += 1;
      continue;
    }

    const buf: string[] = [line];
    i += 1;
    while (i < lines.length) {
      const n = lines[i];
      const nt = n.trim();
      if (
        !nt ||
        nt.startsWith("```") ||
        nt === "---" ||
        /^(#{1,3})\s+/.test(nt) ||
        /^[-*]\s+/.test(nt) ||
        /^\d+\.\s+/.test(nt) ||
        nt.startsWith(">")
      ) {
        break;
      }
      buf.push(n);
      i += 1;
    }
    blocks.push({ t: "p", text: buf.join("\n").trim() });
  }
  return blocks;
}

export default function MarkdownLite({ source }: { source: string }) {
  const blocks = parseBlocks(source || "");
  if (!blocks.length) return null;
  return (
    <div className="watch-md">
      {blocks.map((b, idx) => {
        const k = `md-${idx}`;
        if (b.t === "h") {
          const Tag = (`h${b.level}` as "h1" | "h2" | "h3");
          return <Tag key={k}>{inlineParts(b.text, k)}</Tag>;
        }
        if (b.t === "ul") {
          return (
            <ul key={k}>
              {b.items.map((it, j) => (
                <li key={`${k}-${j}`}>{inlineParts(it, `${k}-${j}`)}</li>
              ))}
            </ul>
          );
        }
        if (b.t === "ol") {
          return (
            <ol key={k}>
              {b.items.map((it, j) => (
                <li key={`${k}-${j}`}>{inlineParts(it, `${k}-${j}`)}</li>
              ))}
            </ol>
          );
        }
        if (b.t === "pre") {
          return (
            <pre key={k}>
              <code>{b.text}</code>
            </pre>
          );
        }
        if (b.t === "bq") {
          return <blockquote key={k}>{inlineParts(b.text, k)}</blockquote>;
        }
        if (b.t === "hr") {
          return <hr key={k} />;
        }
        return <p key={k}>{inlineParts(b.text, k)}</p>;
      })}
    </div>
  );
}
