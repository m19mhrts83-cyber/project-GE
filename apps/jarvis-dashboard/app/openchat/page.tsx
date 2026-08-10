import Link from "next/link";
import Shell from "@/components/Shell";
import CopyPathButton from "@/components/CopyPathButton";
import FolderLinks from "@/components/FolderLinks";
import { LEVEL_LABEL, type HomeLevel } from "@/lib/homeLevels";
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

  const { data: watchRows } = await supabase
    .from("watch_status")
    .select("id,title,level,summary,detail,status,updated_at,payload")
    .in("id", ["openchat_threads", "square_probe"]);

  const { data: meta } = await supabase.from("sync_meta").select("key,value");
  const metaMap = Object.fromEntries((meta || []).map((m) => [m.key, m.value]));
  const digest = parseOpenchatDigest(metaMap.openchat_digest);

  const rows = (activities || []) as ActivityRow[];
  const groups = bundleByGroup(rows, digest);
  const health = (watchRows || []).find((w) => w.id === "openchat_threads");
  const square = (watchRows || []).find((w) => w.id === "square_probe");
  const healthLevel = (health?.level || "info") as string;
  const levelClass =
    healthLevel === "ok"
      ? "level-info"
      : `level-${(healthLevel as HomeLevel) || "info"}`;
  const healthPayload =
    health?.payload && typeof health.payload === "object"
      ? (health.payload as Record<string, unknown>)
      : {};

  return (
    <Shell active="/openchat">
      <h1>神大家オプチャ</h1>
      <FolderLinks links={getFolderLinks(pageFolderKey("openchat"))} />
      <p className="sub">
        情報収集枠。返信提案なし。詳細はグループから。Web
        からローカル OneDrive は直接開けません（パスコピー／Cursor
        プロンプト、またはこの詳細ページで確認）。
      </p>

      <section className={`openchat-health ${levelClass}`} aria-label="スレッド健全性">
        <div className="openchat-health-head">
          <h2>スレッド健全性</h2>
          <Link href="/situation" className="home-more">
            状況ウォッチへ →
          </Link>
        </div>
        {health ? (
          <>
            <p className="openchat-health-status">
              <span className="lvl">
                {healthLevel === "ok"
                  ? "健全"
                  : LEVEL_LABEL[healthLevel as HomeLevel] || healthLevel}
              </span>{" "}
              <strong>{health.title}</strong>
            </p>
            <p className="sum">{health.summary}</p>
            {health.detail ? (
              <p className="meta">{String(health.detail).slice(0, 200)}</p>
            ) : null}
            {healthPayload.threads_today != null ||
            healthPayload.heartbeat_at != null ? (
              <p className="meta">
                {healthPayload.threads_today != null
                  ? `今日【スレッド】 ${String(healthPayload.threads_today)}件`
                  : null}
                {healthPayload.threads_today != null &&
                healthPayload.heartbeat_at != null
                  ? " · "
                  : null}
                {healthPayload.heartbeat_at != null
                  ? `heartbeat ${String(healthPayload.heartbeat_at)}`
                  : null}
              </p>
            ) : null}
          </>
        ) : (
          <p className="empty">健全性データなし（situation_watch push 待ち）</p>
        )}
        {square ? (
          <p className="meta" style={{ marginTop: 8 }}>
            Square: {square.level} — {square.summary}
          </p>
        ) : null}
      </section>

      {digest?.overview ? (
        <p className="openchat-digest-overview">{digest.overview}</p>
      ) : null}

      <h2>グループ別</h2>
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
