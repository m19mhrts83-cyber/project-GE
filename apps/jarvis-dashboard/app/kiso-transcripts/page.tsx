import { readFileSync } from "fs";
import path from "path";
import Shell from "@/components/Shell";
import catalog from "@/data/kiso_transcripts.json";
import courseStatus from "@/data/kiso_course_status.json";
import courseGaps from "@/data/kiso_course_gaps.json";

function loadUnderstanding(): string {
  try {
    return readFileSync(
      path.join(process.cwd(), "data", "kiso_understanding.md"),
      "utf8"
    );
  } catch {
    return "# Jarvis 把握サマリー\n\n（data/kiso_understanding.md 未配置）\n";
  }
}

type GapLesson = {
  slug: string;
  title?: string;
  url?: string;
  ask_priority?: string;
  ask_band?: string;
  ask_rank?: number;
  gap_reason?: string;
  ask_note?: string;
};

type Lesson = {
  slug: string;
  title?: string;
  jarvis_status?: string;
  imamura_status?: string;
  jarvis_file?: string | null;
  imamura_file?: string | null;
  bytes?: number;
  mtime?: string;
  extra?: boolean;
};

function statusClass(s?: string) {
  if (s === "ready" || s === "canonical" || s === "ingested") return "lvl ok";
  if (s === "inbox") return "lvl";
  return "lvl warn";
}

function UnderstandingBlock({ text }: { text: string }) {
  return (
    <div
      style={{
        padding: "1.25rem 1.5rem",
        background: "#fff",
        border: "1px solid #e5e7eb",
        borderRadius: 12,
        marginBottom: 28,
        lineHeight: 1.65,
        color: "#1f2937",
      }}
    >
      <pre
        style={{
          margin: 0,
          whiteSpace: "pre-wrap",
          fontFamily: "inherit",
          fontSize: "0.92rem",
        }}
      >
        {text}
      </pre>
    </div>
  );
}

export default function KisoTranscriptsPage() {
  const lessons = (catalog.lessons || []) as Lesson[];
  const priority = lessons.filter((l) => !l.extra);
  const extra = lessons.filter((l) => l.extra);
  const jarvisReady = lessons.filter((l) => l.jarvis_status === "ready").length;
  const imamuraReady = lessons.filter(
    (l) => l.imamura_status && l.imamura_status !== "missing"
  ).length;
  const understanding = loadUnderstanding();
  const cs = courseStatus as {
    total?: number;
    vtt_ready?: number;
    desc_only?: number;
    missing?: number;
    video_lessons?: number;
    no_video?: number;
    video_no_caption?: number;
    updated?: string;
    lessons?: Array<{
      slug: string;
      title?: string;
      status?: string;
      cue_count?: number;
      section?: string;
      url?: string;
    }>;
  };
  const courseLessons = cs.lessons || [];
  const gaps = courseGaps as {
    count?: number;
    purpose?: string;
    handoff_hint?: string;
    updated?: string;
    bands?: Array<{ id: string; label: string; count: number }>;
    lessons?: GapLesson[];
    excluded?: Array<GapLesson & { excluded_reason?: string }>;
  };
  const gapLessons = (gaps.lessons || []) as GapLesson[];
  const excluded = gaps.excluded || [];
  const gapByBand = (id: string) =>
    gapLessons.filter((g) => g.ask_priority === id);

  return (
    <Shell active="/kiso-transcripts">
      <h1>基礎講座・文字起こし</h1>
      <p className="sub">
        チャットボットの正本は<strong>今村さん字幕</strong>。正本の受領まで、
        Vimeo自動字幕を「暫定」と明示して検索・参照に利用します（2026-10-27 松野了承）。
        字幕が取れなかった分は下の「今村さん依頼」一覧から渡せます。
        コース:{" "}
        <a
          href="https://westudy.co.jp/course/kami-ooyasan-club"
          target="_blank"
          rel="noopener noreferrer"
        >
          神大家1.基礎
        </a>
      </p>

      <div className="watch-grid" style={{ marginBottom: 20 }}>
        <div className="card watch-card">
          <header>
            <span className="lvl">方針</span>
            <strong>正本 = 今村</strong>
          </header>
          <p className="sum">Vimeo = provisional_search（暫定検索・運営正本を上書きしない）</p>
        </div>
        <div className="card watch-card">
          <header>
            <span className={statusClass("ready")}>コース</span>
            <strong>
              {cs.vtt_ready ?? "—"} / {cs.video_lessons ?? cs.total ?? "—"} 字幕取得
            </strong>
          </header>
          <p className="sum">
            動画あり・字幕なし {cs.video_no_caption ?? "—"} · 動画なし（対象外）{" "}
            {cs.no_video ?? "—"} · 全 {cs.total ?? "—"} レッスン ·{" "}
            {cs.updated || catalog.updated || "—"}
          </p>
        </div>
        <div className="card watch-card">
          <header>
            <span className="lvl warn">字幕依頼</span>
            <strong>{gaps.count ?? gapLessons.length} 本</strong>
          </header>
          <p className="sum">
            Vimeo自動字幕なし → 今村さんへSRT依頼（下の一覧）
          </p>
        </div>
        <div className="card watch-card">
          <header>
            <span className={statusClass(imamuraReady ? "ready" : "missing")}>
              今村受領
            </span>
            <strong>{imamuraReady} 本（inbox/正本）</strong>
          </header>
          <p className="sum">受領待ちなら 0。inbox へ置けばここに出る</p>
        </div>
      </div>

      <section className="home-section" id="imamura-ask">
        <div className="home-section-head">
          <h2 style={{ fontSize: "1.15rem", margin: 0 }}>
            今村さん依頼：字幕未取得（{gaps.count ?? gapLessons.length}本）
          </h2>
        </div>
        <div
          style={{
            padding: "1rem 1.25rem",
            background: "#fff7ed",
            border: "1px solid #fdba74",
            borderRadius: 12,
            marginBottom: 16,
            lineHeight: 1.6,
            color: "#9a3412",
            fontSize: "0.92rem",
          }}
        >
          <p style={{ margin: "0 0 0.5rem" }}>
            {gaps.handoff_hint ||
              "特に P1 を優先で SRT 等いただけると助かります。"}
          </p>
          <p style={{ margin: 0 }} className="meta">
            更新: {gaps.updated || "—"} · 置き場:{" "}
            <code>基礎講座_文字起こし/imamura/inbox/</code>
          </p>
        </div>
        {(["P1", "P2", "P3"] as const).map((bandId) => {
          const band = (gaps.bands || []).find((b) => b.id === bandId);
          const rows = gapByBand(bandId);
          if (!rows.length) return null;
          return (
            <div key={bandId} style={{ marginBottom: 20 }}>
              <h3 style={{ fontSize: "1rem", margin: "0 0 8px" }}>
                {bandId} {band?.label || ""}（{rows.length}）
              </h3>
              <ul className="mail-skim">
                {rows.map((g) => (
                  <li key={g.slug}>
                    <div className="mail-row" style={{ cursor: "default" }}>
                      <span className="mail-row-main">
                        <span className="mail-subject">
                          #{g.ask_rank} {g.title || g.slug}
                        </span>
                        <span className="mail-preview">
                          {g.gap_reason || ""}
                          {g.ask_note ? ` · ${g.ask_note}` : ""}
                          {" · "}
                          <span className="meta">({g.slug})</span>
                          {g.url ? (
                            <>
                              {" · "}
                              <a
                                href={g.url}
                                target="_blank"
                                rel="noopener noreferrer"
                              >
                                WeStudy
                              </a>
                            </>
                          ) : null}
                        </span>
                      </span>
                      <span className="lvl warn">{bandId}</span>
                    </div>
                  </li>
                ))}
              </ul>
            </div>
          );
        })}
        {excluded.length ? (
          <div style={{ marginBottom: 20 }}>
            <h3 style={{ fontSize: "1rem", margin: "0 0 8px" }}>
              対象外：動画なし（{excluded.length}）
            </h3>
            <ul className="mail-skim">
              {excluded.map((g) => (
                <li key={g.slug}>
                  <div className="mail-row" style={{ cursor: "default" }}>
                    <span className="mail-row-main">
                      <span className="mail-subject">{g.title || g.slug}</span>
                      <span className="mail-preview">
                        {g.excluded_reason || g.gap_reason || ""}
                        {" · "}
                        <span className="meta">({g.slug})</span>
                      </span>
                    </span>
                    <span className="lvl">対象外</span>
                  </div>
                </li>
              ))}
            </ul>
          </div>
        ) : null}
      </section>

      <UnderstandingBlock text={understanding} />

      <section className="home-section">
        <div className="home-section-head">
          <h2 style={{ fontSize: "1.08rem", margin: 0 }}>
            コース全レッスン（{courseLessons.length || priority.length}）
          </h2>
        </div>
        <ul className="mail-skim">
          {(courseLessons.length ? courseLessons : priority).map((it) => {
            const row = it as Lesson & {
              status?: string;
              cue_count?: number;
              section?: string;
              url?: string;
            };
            const st = row.status || row.jarvis_status || "—";
            const ok = st === "vtt_ready" || st === "ready";
            const url =
              row.url || `https://westudy.co.jp/lesson/${row.slug}`;
            return (
              <li key={row.slug}>
                <div className="mail-row" style={{ cursor: "default" }}>
                  <span className="mail-row-main">
                    <span className="mail-subject">
                      {row.title || row.slug}{" "}
                      <span className="meta">({row.slug})</span>
                    </span>
                    <span className="mail-preview">
                      {row.section ? `${row.section.slice(0, 40)} · ` : ""}
                      {st}
                      {typeof row.cue_count === "number"
                        ? ` · cues ${row.cue_count}`
                        : ""}
                      {row.jarvis_file ? ` · ${row.jarvis_file}` : ""}
                      {" · "}
                      <a href={url} target="_blank" rel="noopener noreferrer">
                        WeStudy
                      </a>
                    </span>
                  </span>
                  <span className={statusClass(ok ? "ready" : "missing")}>
                    {ok ? "VTT" : st === "desc_only" ? "説明" : "…"}
                  </span>
                </div>
              </li>
            );
          })}
        </ul>
      </section>

      {extra.length ? (
        <section className="home-section">
          <div className="home-section-head">
            <h2 style={{ fontSize: "1.08rem", margin: 0 }}>
              参考（基礎STEP外・既存コピー）
            </h2>
          </div>
          <ul className="mail-skim">
            {extra.map((it) => (
              <li key={it.slug}>
                <div className="mail-row" style={{ cursor: "default" }}>
                  <span className="mail-row-main">
                    <span className="mail-subject">{it.title || it.slug}</span>
                    <span className="mail-preview">{it.jarvis_file}</span>
                  </span>
                </div>
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      <p className="meta" style={{ marginTop: 24 }}>
        関連: <a href="/materials">資料ハブ</a>
        {" · "}
        <a href="/ai-raimo">AI推進・Raimo</a>
        {" · "}
        OneDrive{" "}
        <code>C1_cursor/1c_…/基礎講座_文字起こし/</code>
      </p>
    </Shell>
  );
}
