import { readFileSync } from "fs";
import path from "path";
import Shell from "@/components/Shell";
import catalog from "@/data/kiso_transcripts.json";
import courseStatus from "@/data/kiso_course_status.json";

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

function loadGaps(): string {
  try {
    return readFileSync(
      path.join(process.cwd(), "data", "kiso_course_gaps.md"),
      "utf8"
    );
  } catch {
    return "";
  }
}

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
  const gapsMd = loadGaps();
  const cs = courseStatus as {
    total?: number;
    vtt_ready?: number;
    desc_only?: number;
    missing?: number;
    updated?: string;
    lessons?: Array<{
      slug: string;
      title?: string;
      status?: string;
      cue_count?: number;
      section?: string;
    }>;
  };
  const courseLessons = cs.lessons || [];

  return (
    <Shell active="/kiso-transcripts">
      <h1>基礎講座・文字起こし</h1>
      <p className="sub">
        チャットボットの正本は<strong>今村さん字幕</strong>。Jarvis の
        Vimeo自動字幕は突き合わせ用。方針・把握サマリーを白いカードに、進捗を一覧に出します。
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
          <p className="sum">Jarvis = compare_only（ボットへ無確認投入しない）</p>
        </div>
        <div className="card watch-card">
          <header>
            <span className={statusClass("ready")}>コース</span>
            <strong>
              {cs.vtt_ready ?? "—"} / {cs.total ?? "—"} VTT
            </strong>
          </header>
          <p className="sum">
            説明文のみ {cs.desc_only ?? "—"} · 未取得 {cs.missing ?? "—"} ·{" "}
            {cs.updated || catalog.updated || "—"}
          </p>
        </div>
        <div className="card watch-card">
          <header>
            <span className={statusClass(imamuraReady ? "ready" : "missing")}>
              今村
            </span>
            <strong>{imamuraReady} 本（inbox/正本）</strong>
          </header>
          <p className="sum">受領待ちなら 0。inbox へ置けばここに出る</p>
        </div>
      </div>

      <UnderstandingBlock text={understanding} />
      {gapsMd ? (
        <>
          <h2 style={{ fontSize: "1.08rem" }}>ギャップと対応策</h2>
          <UnderstandingBlock text={gapsMd} />
        </>
      ) : null}

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
            };
            const st = row.status || row.jarvis_status || "—";
            const ok = st === "vtt_ready" || st === "ready";
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
