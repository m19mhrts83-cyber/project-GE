import { NextResponse } from "next/server";
import { readFile } from "fs/promises";
import path from "path";
import { serviceClient } from "@/lib/supabase";
import { loadMisses } from "@/lib/misses";

export const runtime = "nodejs";

/**
 * 見落とし候補。
 * ?surface=triage → メールの仕分けが出さなかったもの（Supabase）
 * それ以外 → 312 の Mac 上の miss_scan state を読む（Cloud では空＝シード）
 */
export async function GET(req: Request) {
  if (new URL(req.url).searchParams.get("surface") === "triage") {
    const sb = serviceClient();
    if (!sb) return NextResponse.json({ ok: true, persisted: false, candidates: [] });
    try {
      return NextResponse.json({ ok: true, persisted: true, candidates: await loadMisses(sb) }, { headers: { "cache-control": "private, no-store" } });
    } catch (e) {
      return NextResponse.json({ ok: false, error: e instanceof Error ? e.message : String(e) }, { status: 500 });
    }
  }
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
