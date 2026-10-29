import { readFileSync } from "fs";
import path from "path";
import Shell from "@/components/Shell";
import catalog from "@/data/kiso_transcripts.json";
import courseStatus from "@/data/kiso_course_status.json";
import courseGaps from "@/data/kiso_course_gaps.json";
import nottaReceived from "@/data/kiso_notta_received.json";
import nottaReview from "@/data/kiso_notta_a1_review.json";
import transcriptionStatus from "@/data/kamiooya_transcription_status.json";

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
  const receivedSlugs = new Set(nottaReceived.lessons.map((l) => l.slug));
  const resolvedGapSlugs = new Set(transcriptionStatus.resolved_gap_lessons);
  const gapLessons = ((gaps.lessons || []) as GapLesson[]).filter(
    (l) => !receivedSlugs.has(l.slug) && !resolvedGapSlugs.has(l.slug)
  );
  const excluded = gaps.excluded || [];
  const gapByBand = (id: string) =>
    gapLessons.filter((g) => g.ask_priority === id);

  return (
    <Shell active="/kiso-transcripts">
      <h1>基礎講座・文字起こし</h1>
      <p className="sub">
        Vimeo自動字幕と今村さん提供字幕を優先し、字幕がない動画はMac上のローカルWhisperで補完します。
        把握済みの字幕不足は解消し、現在は週次の差分取込と誤記候補の確認を続けています。
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
            <span className={statusClass("ready")}>初回登録</span>
            <strong>字幕不足を解消</strong>
          </header>
          <p className="sum">Vimeo・今村さん提供・ローカルWhisperを使い分け</p>
        </div>
        <div className="card watch-card">
          <header>
            <span className={statusClass("ready")}>Whisper追加</span>
            <strong>{transcriptionStatus.whisper_import.videos}動画</strong>
          </header>
          <p className="sum">
            {transcriptionStatus.whisper_import.chunks.toLocaleString("ja-JP")}チャンク登録
            （50動画・1,168 ＋ 16動画・385）
          </p>
          <p className="meta">PR #{transcriptionStatus.merged_prs.join(" / #")} マージ済み</p>
        </div>
        <div className="card watch-card">
          <header>
            <span className={statusClass("ready")}>週次自動</span>
            <strong>{transcriptionStatus.weekly_job.schedule}</strong>
          </header>
          <p className="sum">
            初回スケジュール実行は11月1日。結果確認待ち
          </p>
        </div>
        <div className="card watch-card">
          <header>
            <span className="lvl warn">誤記確認</span>
            <strong>{transcriptionStatus.typo_review.candidates}候補</strong>
          </header>
          <p className="sum">承認した語だけ補正表へ追加。自動一括反映はしません</p>
        </div>
      </div>

      <section className="home-section" id="imamura-ask">
        <div className="home-section-head">
          <h2 style={{ fontSize: "1.15rem", margin: 0 }}>
             字幕未取得の解消状況
          </h2>
        </div>
        <div
          style={{
            padding: "1rem 1.25rem",
            background: gapLessons.length ? "#fff7ed" : "#ecfdf5",
            border: `1px solid ${gapLessons.length ? "#fdba74" : "#6ee7b7"}`,
            borderRadius: 12,
            marginBottom: 16,
            lineHeight: 1.6,
            color: gapLessons.length ? "#9a3412" : "#065f46",
            fontSize: "0.92rem",
          }}
        >
          <p style={{ margin: "0 0 0.5rem" }}>
            {gapLessons.length
              ? `未取得が${gapLessons.length}レッスン残っています。`
              : "従来の依頼候補16レッスンはローカルWhisperで補完し、本番検索へ登録済みです。今村さんへの追加依頼は不要になりました。"}
          </p>
          <p style={{ margin: 0 }} className="meta">
            更新: 2026-10-29 · 最終適用 10月29日 13:03 · 失敗工程 0
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

      <section className="home-section">
        <h2 style={{ fontSize: "1.15rem" }}>対応済み：今村さん提供により本番反映</h2>
        <p>{nottaReceived.note}</p>
        <ul>{nottaReceived.lessons.map((lesson) => <li key={lesson.slug}>
          <a href={`https://westudy.co.jp/lesson/${lesson.slug}`} target="_blank" rel="noopener noreferrer">{lesson.title}</a>
          {" · "}{lesson.videos}動画 · <strong>対応済み（今村さん提供・本番検索反映済み）</strong>
        </li>)}</ul>
      </section>
      <section className="home-section" id="notta-received">
        <h2 style={{ fontSize: "1.15rem" }}>A1動画名による受領ファイル照合</h2>
        <p>{nottaReview.note}</p>
        <p className="meta">確認日 {nottaReview.updated} · 今回受領38ファイルはすべて対応済み。部分取得レッスン内の不足15動画も本番反映済みです。従来の字幕未取得16レッスンも10月29日にWhisperで補完したため、追加依頼は不要です。</p>
        <h3 style={{ fontSize: "1rem" }}>対応済み：既存字幕で参照可能</h3>
        <p>同一動画IDで既存字幕あり {nottaReview.existing_video}動画。加えて、以下の3動画は既存の別字幕に対応本文があります。</p>
        <ul>{nottaReview.covered_elsewhere.map((item) => <li key={item.file}>{item.title}（{item.file}） · {item.status}</li>)}</ul>
        <h3 style={{ fontSize: "1rem" }}>対応済み：追加{nottaReview.additional_imported.length}動画・本番検索反映済み</h3>
        <ul>{nottaReview.additional_imported.map((item) => <li key={item.file}>
          <a href={`https://westudy.co.jp/lesson/${item.slug}`} target="_blank" rel="noopener noreferrer">{item.title}</a>
          {" "}（{item.file}） · 対応済み（今村さん提供・本番検索反映済み）
        </li>)}</ul>
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
            const whisperResolved = resolvedGapSlugs.has(row.slug);
            const st = receivedSlugs.has(row.slug)
              ? "対応済み（今村さん提供・本番反映済み）"
              : whisperResolved
                ? "対応済み（ローカルWhisper・本番反映済み）"
                : row.status || row.jarvis_status || "—";
            const ok = st === "vtt_ready" || st === "ready" || receivedSlugs.has(row.slug) || whisperResolved;
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
                    {whisperResolved ? "Whisper" : ok ? "VTT" : st === "desc_only" ? "説明" : "…"}
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
