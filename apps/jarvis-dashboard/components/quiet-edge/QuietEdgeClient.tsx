"use client";

import { useRouter } from "next/navigation";
import { useMemo, useState, useTransition } from "react";
import {
  deleteSnoreDaily,
  parseSnoreScreenshots,
  upsertSnoreDaily,
  type SnoreDailyInput,
  type SnoreEvent,
} from "@/app/actions/quietEdge";

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
  const [pending, start] = useTransition();
  const [err, setErr] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const [form, setForm] = useState<SnoreDailyInput>(emptyForm);
  const [ocrHint, setOcrHint] = useState<string | null>(null);

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

  return (
    <div className="qe-client">
      {showUpload ? (
      <section className="card qe-upload-card">
        <header>
          <span className="lvl">取込</span>
          <strong>AutoSnore スクショ（1日2枚）</strong>
        </header>
        <p className="meta">
          「いびきスコア」と「いびき回数」の画面を同時選択、または1枚ずつ。日付が同じなら1レコードにマージします。
        </p>
        <input
          type="file"
          accept="image/*"
          multiple
          disabled={pending}
          className="qe-file"
          onChange={(e) => {
            const files = e.target.files;
            if (!files?.length) return;
            setErr(null);
            setMsg(null);
            setOcrHint(null);
            const fd = new FormData();
            Array.from(files).slice(0, 2).forEach((f) => fd.append("images", f));
            start(async () => {
              const r = await parseSnoreScreenshots(fd);
              if (!r.ok) {
                setErr(r.error);
                return;
              }
              setForm({
                ...r.merged,
                event: (r.merged.event as SnoreEvent) || "通常日",
              });
              const kinds = r.parts.map((p) => p.screen).join(" + ");
              setOcrHint(`読取: ${kinds} → ${r.merged.recorded_at}`);
              setMsg("フォームに反映しました。内容を確認して保存してください。");
            });
            e.target.value = "";
          }}
        />
        {ocrHint ? <p className="meta qe-ocr-hint">{ocrHint}</p> : null}
      </section>
      ) : null}

      {showForm ? (
      <section className="card qe-form-card">
        <header>
          <span className="lvl">記録</span>
          <strong>日次いびきデータ</strong>
        </header>
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
            disabled={pending}
            onClick={() => {
              setErr(null);
              setMsg(null);
              start(async () => {
                const r = await upsertSnoreDaily({
                  ...form,
                  source: form.source || "manual",
                });
                if (!r.ok) {
                  setErr(r.error);
                  return;
                }
                setMsg(`${form.recorded_at} を保存しました`);
                router.refresh();
              });
            }}
          >
            {pending ? "保存中…" : "ダッシュボードに反映"}
          </button>
          <button
            type="button"
            className="btn btn-ghost"
            disabled={pending}
            onClick={() => {
              setForm(emptyForm());
              setOcrHint(null);
              setMsg(null);
              setErr(null);
            }}
          >
            リセット
          </button>
        </div>
        {err ? <p className="meta qe-err">{err}</p> : null}
        {msg ? <p className="meta qe-ok">{msg}</p> : null}
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
                      onClick={() =>
                        setForm({
                          recorded_at: r.recorded_at,
                          score: r.score,
                          count: r.count,
                          event: r.event,
                          sleep_time: r.sleep_time || "",
                          memo: r.memo || "",
                          source: r.source || "manual",
                        })
                      }
                    >
                      {r.recorded_at}
                    </button>
                  </td>
                  <td>{r.event}</td>
                  <td>{r.score.toFixed(1)}</td>
                  <td>{r.count != null ? r.count.toLocaleString("ja-JP") : "—"}</td>
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
        {!showForm && err ? <p className="meta qe-err">{err}</p> : null}
        {!showForm && msg ? <p className="meta qe-ok">{msg}</p> : null}
      </section>
      ) : null}
    </div>
  );
}
