import { NextResponse } from "next/server";
import { readFile } from "fs/promises";
import path from "path";

export const runtime = "nodejs";

/** Mac 上の miss_scan state を読む（Cloud では空＝シード）。 */
export async function GET() {
  const home = process.env.HOME || "";
  const candidates = [
    path.join(home, "git-repos/.jarvis_state/todoist_312_miss_scan.json"),
    path.join(process.cwd(), "../../.jarvis_state/todoist_312_miss_scan.json"),
  ];
  for (const p of candidates) {
    try {
      const raw = await readFile(p, "utf8");
      const j = JSON.parse(raw) as {
        candidates?: {
          source: string;
          folder?: string;
          ref?: string;
          snippet?: string;
          hypothesis?: string;
        }[];
      };
      const list = (j.candidates || []).map((c, i) => ({
        id: `miss-${i + 1}`,
        source: c.source,
        folder: c.folder || "",
        snippet: c.snippet || "",
        hypothesis: c.hypothesis || "",
        ref: c.ref,
      }));
      return NextResponse.json({ ok: true, candidates: list });
    } catch {
      /* try next */
    }
  }
  return NextResponse.json({ ok: true, candidates: [] });
}
