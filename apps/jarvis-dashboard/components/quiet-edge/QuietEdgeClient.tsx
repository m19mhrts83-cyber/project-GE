"use client";

import { useRouter } from "next/navigation";
import { useMemo, useRef, useState, useTransition } from "react";
import {
  deleteSnoreDaily,
  generateQuietEdgeIngestReview,
  parseSnoreScreenshots,
  upsertSnoreDaily,
  type SnoreDailyInput,
  type SnoreEvent,
} from "@/app/actions/quietEdge";
import { compressImageFiles } from "@/lib/compressImageFile";

export type SnoreRow = {
  recorded_at: string;
  score: number;
  count: number | null;
  event: string;
  sleep_time: string | null;
  memo: string | null;
  source: string | null;
};

const EVENTS: SnoreEvent[] = ["通常日", "治療当日", "治療直後"];

function emptyForm(): SnoreDailyInput {
  const d = new Date();
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return {
    recorded_at: `${y}-${m}-${day}`,
    score: 0,
    count: null,
    event: "通常日",
    sleep_time: "",
    memo: "",
    source: "manual",
    payload: {},
  };
}

export type QuietEdgeClientSection = "upload" | "form" | "log";

export default function QuietEdgeClient({
  rows,
  sections = ["upload", "form", "log"],
}: {
  rows: SnoreRow[];
  sections?: QuietEdgeClientSection[];
}) {
  const router = useRouter();
  const fileRef = useRef<HTMLInputElement>(null);
  const [pending, start] = useTransition();
  const [err, setErr] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const [form, setForm] = useState<SnoreDailyInput>(emptyForm);
  const [ocrHint, setOcrHint] = useState<string | null>(null);
  const [picked, setPicked] = useState<File[]>([]);
  const [ocrReady, setOcrReady] = useState(false);
  const [ingestReview, setIngestReview] = useState<string | null>(null);
  const [reviewPending, setReviewPending] = useState(false);

  const showUpload = sections.includes("upload");
  const showForm = sections.includes("form");
  const showLog = sections.includes("log");

  const sorted = useMemo(
    () =>
      [...rows].sort((a, b) => a.recorded_at.localeCompare(b.recorded_at)).reverse(),
    [rows],
  );

  function setField<K extends keyof SnoreDailyInput>(
    key: K,
    value: SnoreDailyInput[K],
  ) {
    setForm((f) => ({ ...f, [key]: value }));
  }

  function clearPicked() {
    setPicked([]);
    setOcrReady(false);
    if (fileRef.current) fileRef.current.value = "";
  }

  function runOcr() {
    if (!picked.length) {
      setErr("先にスクショを選んでください（1〜2枚）");
      return;
    }
    setErr(null);
    setMsg(null);
    setOcrHint(null);
    start(async () => {
      try {
        setMsg("画像を圧縮して読み取り中…");
        const compressed = await compressImageFiles(picked.slice(0, 2));
        const fd = new FormData();
        compressed.forEach((f) => fd.append("images", f));
        const r = await parseSnoreScreenshots(fd);
        if (!r.ok) {
          setErr(r.error);
          setOcrReady(false);
          setMsg(null);
          return;
        }
        setForm({
          ...r.merged,
          event: (r.merged.event as SnoreEvent) || "通常日",
        });
        const kinds = r.parts.map((p) => p.screen).join(" + ");
        setOcrHint(`読取: ${kinds} → ${r.merged.recorded_at}`);
        setOcrReady(true);
        setMsg(
          "読み取りました。下の内容を確認し、「取り込む」でアプリに保存してください。",
        );
      } catch (e) {
        const raw = e instanceof Error ? e.message : String(e);
        setOcrReady(false);
        setMsg(null);
        if (/Body exceeded|413|body size|too large/i.test(raw)) {
          setErr(
            "画像が大きすぎて送れませんでした。スクショを1枚ずつ読み取るか、もう一度お試しください。",
          );
        } else {
          setErr(`読み取りエラー: ${raw.slice(0, 160)}`);
        }
      }
    });
  }

  function saveRecord(source?: string) {
    setErr(null);
    setMsg(null);
    setIngestReview(null);
    const savedAt = form.recorded_at;
    start(async () => {
      const r = await upsertSnoreDaily({
        ...form,
        source: source || form.source || "manual",
      });
      if (!r.ok) {
        setErr(r.error);
        return;
      }
      setMsg(`${savedAt} を取り込みました。レビューを作成中…`);
      setOcrReady(false);
      clearPicked();
      setReviewPending(true);
      const review = await generateQuietEdgeIngestReview(savedAt);
      setReviewPending(false);
      if (review.ok) {
        setIngestReview(review.text);
        setMsg(`${savedAt} を取り込みました`);
      } else {
        setMsg(`${savedAt} を取り込みました（レビュー: ${review.error}）`);
      }
      router.refresh();
    });
  }

  return (
    <div className="qe-client">
      {showUpload ? (
        <section className="card qe-upload-card">
          <header>
            <span className="lvl">取込</span>
            <strong>AutoSnore スクショ（1日2枚）</strong>
          </header>
          <p className="meta">
            ① スクショを選ぶ → ②「読み取る」→ ③ 内容確認 → ④「取り込む」
          </p>
          <input
            ref={fileRef}
            type="file"
            accept="image/*"
            multiple
            disabled={pending}
            className="qe-file"
            onChange={(e) => {
              const files = e.target.files;
              if (!files?.length) {
                setPicked([]);
                return;
              }
              setPicked(Array.from(files).slice(0, 2));
              setOcrReady(false);
              setErr(null);
              setMsg(null);
              setOcrHint(null);
            }}
          />
          {picked.length ? (
            <ul className="qe-picked-list">
              {picked.map((f) => (
                <li key={`${f.name}-${f.size}`}>{f.name}</li>
              ))}
            </ul>
          ) : (
            <p className="meta">まだファイルが選ばれていません</p>
          )}
          <div className="qe-form-actions">
            <button
              type="button"
              className="btn"
              disabled={pending || picked.length === 0}
              onClick={runOcr}
            >
              {pending && !ocrReady ? "読み取り中…" : "読み取る"}
            </button>
            <button
              type="button"
              className="btn"
              disabled={pending || !Number.isFinite(form.score) || form.score <= 0}
              onClick={() => saveRecord(ocrReady ? "autosnore_ocr" : form.source)}
            >
              {pending && ocrReady ? "取込中…" : "取り込む"}
            </button>
            <button
              type="button"
              className="btn btn-ghost"
              disabled={pending}
              onClick={() => {
                clearPicked();
                setForm(emptyForm());
                setOcrHint(null);
                setMsg(null);
                setErr(null);
              }}
            >
              クリア
            </button>
          </div>
          {ocrHint ? <p className="meta qe-ocr-hint">{ocrHint}</p> : null}
          {err ? <p className="meta qe-err">{err}</p> : null}
          {msg ? <p className="meta qe-ok">{msg}</p> : null}
          {reviewPending ? (
            <p className="meta">依存データ（前回比・Health・Journal・治療）を見てレビュー作成中…</p>
          ) : null}
          {ingestReview ? (
            <div className="qe-ingest-review">
              <p className="meta">
                <strong>取込レビュー</strong>（診断ではなく励ましの観察メモ）
              </p>
              <pre className="qe-review-text">{ingestReview}</pre>
            </div>
          ) : null}
        </section>
      ) : null}

      {showForm ? (
        <section className="card qe-form-card">
          <header>
            <span className="lvl">確認</span>
            <strong>読み取り結果・手入力</strong>
          </header>
          <p className="meta">
            OCR後はここに値が入ります。直してから上の「取り込む」、または下の保存でも反映できます。
          </p>
          <div className="qe-form-grid">
            <label>
              測定日
              <input
                type="date"
                value={form.recorded_at}
                onChange={(e) => setField("recorded_at", e.target.value)}
                required
              />
            </label>
            <label>
              治療ステータス
              <select
                value={String(form.event || "通常日")}
                onChange={(e) => setField("event", e.target.value as SnoreEvent)}
              >
                {EVENTS.map((ev) => (
                  <option key={ev} value={ev}>
                    {ev}
                  </option>
                ))}
              </select>
            </label>
            <label>
              いびきスコア
              <input
                type="number"
                step="0.1"
                min={0}
                max={100}
                value={form.score}
                onChange={(e) => setField("score", Number(e.target.value))}
                required
              />
            </label>
            <label>
              いびき回数
              <input
                type="number"
                min={0}
                value={form.count ?? ""}
                onChange={(e) =>
                  setField(
                    "count",
                    e.target.value === "" ? null : Number(e.target.value),
                  )
                }
                placeholder="任意"
              />
            </label>
            <label className="qe-span2">
              睡眠時間帯
              <input
                type="text"
                value={form.sleep_time || ""}
                onChange={(e) => setField("sleep_time", e.target.value)}
                placeholder="例: 22:45 - 06:02"
              />
            </label>
            <label className="qe-span2">
              メモ
              <input
                type="text"
                value={form.memo || ""}
                onChange={(e) => setField("memo", e.target.value)}
                placeholder="任意"
              />
            </label>
          </div>
          <div className="qe-form-actions">
            <button
              type="button"
              className="btn"
              disabled={pending || !Number.isFinite(form.score)}
              onClick={() => saveRecord()}
            >
              {pending ? "保存中…" : "取り込む"}
            </button>
            <button
              type="button"
              className="btn btn-ghost"
              disabled={pending}
              onClick={() => {
                setForm(emptyForm());
                setOcrHint(null);
                setOcrReady(false);
                setMsg(null);
                setErr(null);
              }}
            >
              リセット
            </button>
          </div>
        </section>
      ) : null}

      {showLog ? (
        <section className="card qe-log-card">
          <header>
            <span className="lvl">ログ</span>
            <strong>記録されたいびきデータ</strong>
          </header>
          <div className="qe-table-wrap">
            <table className="qe-table">
              <thead>
                <tr>
                  <th>日付</th>
                  <th>ステータス</th>
                  <th>いびきスコア</th>
                  <th>いびき回数</th>
                  <th>睡眠</th>
                  <th>メモ</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {sorted.map((r) => (
                  <tr key={r.recorded_at}>
                    <td>
                      <button
                        type="button"
                        className="qe-linkish"
                        onClick={() => {
                          setForm({
                            recorded_at: r.recorded_at,
                            score: r.score,
                            count: r.count,
                            event: r.event,
                            sleep_time: r.sleep_time || "",
                            memo: r.memo || "",
                            source: r.source || "manual",
                          });
                          setOcrReady(false);
                        }}
                      >
                        {r.recorded_at}
                      </button>
                    </td>
                    <td>{r.event}</td>
                    <td>{r.score.toFixed(1)}</td>
                    <td>
                      {r.count != null ? r.count.toLocaleString("ja-JP") : "—"}
                    </td>
                    <td>{r.sleep_time || "—"}</td>
                    <td className="qe-memo">{r.memo || "—"}</td>
                    <td>
                      <button
                        type="button"
                        className="btn btn-ghost qe-del"
                        disabled={pending}
                        onClick={() => {
                          if (!confirm(`${r.recorded_at} を削除しますか？`)) return;
                          setErr(null);
                          start(async () => {
                            const res = await deleteSnoreDaily(r.recorded_at);
                            if (!res.ok) {
                              setErr(res.error);
                              return;
                            }
                            setMsg(`${r.recorded_at} を削除しました`);
                            router.refresh();
                          });
                        }}
                      >
                        削除
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {err ? <p className="meta qe-err">{err}</p> : null}
          {msg ? <p className="meta qe-ok">{msg}</p> : null}
        </section>
      ) : null}
    </div>
  );
}
