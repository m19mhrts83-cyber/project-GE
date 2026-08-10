"use client";

import { useMemo, type ReactNode } from "react";
import { VARIABLE_COLORS, type PromptVariable } from "@/lib/prompts";

export function PromptPreview({
  template,
  values,
  variables,
  filled
}: {
  template: string;
  values: Record<string, string>;
  variables: PromptVariable[];
  filled?: boolean;
}) {
  const colorByKey = useMemo(() => {
    const map = new Map<string, string>();
    variables.forEach((v, i) => {
      map.set(v.key, VARIABLE_COLORS[i % VARIABLE_COLORS.length]);
    });
    return map;
  }, [variables]);

  const defaults = useMemo(() => {
    const m = new Map(variables.map((v) => [v.key, v.default_example || ""]));
    return m;
  }, [variables]);

  const nodes = useMemo(() => {
    const parts: ReactNode[] = [];
    const re = /\{([^{}]+)\}/g;
    let last = 0;
    let m: RegExpExecArray | null;
    let i = 0;
    const src = template || "";
    while ((m = re.exec(src))) {
      if (m.index > last) parts.push(src.slice(last, m.index));
      const key = m[1].trim();
      const val = values[key];
      const shown =
        filled
          ? (val != null && val !== "" ? val : defaults.get(key) || "")
          : (val != null && val !== "" ? val : `{${key}}`);
      const bg = colorByKey.get(key) || "#fef08a";
      parts.push(
        <span key={`${key}-${i++}`} className="var-chip" style={{ background: bg, color: "#111827" }}>
          {shown}
        </span>
      );
      last = m.index + m[0].length;
    }
    if (last < src.length) parts.push(src.slice(last));
    return parts;
  }, [template, values, colorByKey, defaults, filled]);

  return <div className="preview-box">{nodes}</div>;
}
