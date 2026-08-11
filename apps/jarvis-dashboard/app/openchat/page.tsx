import Link from "next/link";
import Shell from "@/components/Shell";
import CopyPathButton from "@/components/CopyPathButton";
import FolderLinks from "@/components/FolderLinks";
import OpenchatHealthBody from "@/components/OpenchatHealthBody";
import { getFolderLinks, pageFolderKey } from "@/lib/folderLinks";
import {
  bundleByGroup,
  parseOpenchatDigest,
  yoritooriCursorPrompt,
  yoritooriRelPath,
  type ActivityRow,
} from "@/lib/openchatDigest";
import { createClient } from "@/lib/supabase/server";

export default async function OpenchatPage() {
  const supabase = await createClient();
  const { data: activities } = await supabase
    .from("triage_items")
    .select(
      "id,partner,folder,subject,summary,received_at,channel",
    )
    .eq("lane", "openchat")
    .eq("kind", "activity")
    .order("received_at", { ascending: false })
    .limit(120);

  const { data: meta } = await supabase.from("sync_meta").select("key,value");
  const metaMap = Object.fromEntries((meta || []).map((m) => [m.key, m.value]));
  const digest = parseOpenchatDigest(metaMap.openchat_digest);

  const rows = (activities || []) as ActivityRow[];
  const groups = bundleByGroup(rows, digest);

  return (
    <Shell active="/openchat">
      <h1>神大家オプチャ</h1>
      <FolderLinks links={getFolderLinks(pageFolderKey("openchat"))} />
      <p className="sub">
        情報収集枠。返信提案なし。上部が取得の健全性、下部がグループ別ダイジェスト。
        Web からローカル OneDrive は直接開けません（パスコピー／Cursor
        プロンプト、またはグループ詳細で確認）。
      </p>

      <OpenchatHealthBody />

      {digest?.overview ? (
        <p className="openchat-digest-overview">{digest.overview}</p>
      ) : null}

      <h2>グループ別ダイジェスト</h2>
      {!groups.length ? (
        <p className="empty">なし（push 待ち）</p>
      ) : (
        <div className="watch-grid">
          {groups.map((g) => {
            const path = yoritooriRelPath(g.name);
            const prompt = yoritooriCursorPrompt(g.name);
            const lines = g.digestLines?.length ? g.digestLines : g.lines;
            return (
              <article key={g.slug} className="card watch-card openchat-group-card">
                <header>
                  <span className="lvl">更新 {g.count}</span>
                  <strong>{g.name}</strong>
                  <span className="meta">{g.latestAt || "—"}</span>
                </header>
                {lines.length ? (
                  <ul className="openchat-group-lines">
                    {lines.map((ln, i) => (
                      <li key={i}>{ln}</li>
                    ))}
                  </ul>
                ) : (
                  <p className="sum">直近の要約なし</p>
                )}
                <p className="openchat-group-actions">
                  <Link href={`/openchat/${g.slug}`}>詳細 →</Link>
                  <span className="meta"> · </span>
                  <CopyPathButton path={path} label="やり取りパス" />
                  <span className="meta"> · </span>
                  <CopyPathButton path={prompt} label="Cursorプロンプト" />
                </p>
                <p className="meta openchat-path-hint">{path}</p>
              </article>
            );
          })}
        </div>
      )}
    </Shell>
  );
}
