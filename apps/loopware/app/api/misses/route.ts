import { NextResponse } from "next/server";
import { readFile } from "fs/promises";
import path from "path";
import { serviceClient } from "@/lib/supabase";
import { loadMisses } from "@/lib/misses";
import { loadProposalCandidates } from "@/lib/proposalCandidates";
import { mergeCandidates, type RawCandidate } from "@/lib/proposalDedupe";

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
  // 本番（Vercel）では Mac のファイルが読めないので、スキャンが sync_meta に置いた候補を読む。
  // 同じ中身はまとめ、前に採る／見送るを決めたものは出さない（lib/proposalDedupe.ts）
  const sbm = serviceClient();
  if (sbm) {
    try {
      const got = await loadProposalCandidates(sbm);
      if (got) {
        return NextResponse.json(
          { ok: true, at: got.at, candidates: got.candidates, excluded: got.excluded, mergedAway: got.mergedAway },
          { headers: { "cache-control": "private, no-store" } },
        );
      }
    } catch {
      /* 次（Mac 上のファイル）へ */
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
      const j = JSON.parse(raw) as { at?: string; candidates?: RawCandidate[] };
      if (sbm) {
        const got = await loadProposalCandidates(sbm, j);
        if (got) return NextResponse.json({ ok: true, at: got.at, candidates: got.candidates, excluded: got.excluded, mergedAway: got.mergedAway });
      }
      return NextResponse.json({ ok: true, candidates: mergeCandidates(j.candidates || []).map(({ variants: _v, ...c }) => c) });
    } catch {
      /* try next */
    }
  }
  return NextResponse.json({ ok: true, candidates: [] });
}
