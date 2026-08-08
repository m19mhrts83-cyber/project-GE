"use client";

import { useRouter } from "next/navigation";
import { useMemo, useState, useTransition } from "react";
import {
  saveContextNote,
  type QuietEdgeResult,
} from "@/app/actions/quietEdge";
import {
  addDaysYmd,
  ymdJst,
  type ContextNoteRow,
  type QuietEdgeAsk,
} from "@/lib/quietEdgeContext";

const OPTIONAL_SCALES = [
  {
    key: "sleepiness",
    trigger: "scale_sleepiness",
    label: "朝の眠気",
    prompt: "朝の眠気（1=すっきり〜5=強い）",
  },
  {
    key: "subjective_snore",
    trigger: "scale_subjective_snore",
    label: "主観いびき",
    prompt: "主観的ないびきの強さ（1=ほぼなし〜5=強い）",
  },
] as const;

export default function QuietEdgeAskPanel({
  asks,
  notes,
}: {
  asks: QuietEdgeAsk[];
  notes: ContextNoteRow[];
}) {
  const router = useRouter();
  const [pending, start] = useTransition();
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const [err, setErr] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const [scaleDate, setScaleDate] = useState(() => addDaysYmd(ymdJst(), -1));
  const [scales, setScales] = useState<Record<string, number | "">>({
    sleepiness: "",
    subjective_snore: "",
  });

  const recentNotes = [...notes]
    .sort((a, b) => b.created_at.localeCompare(a.created_at))
    .slice(0, 8);

  const scaleAnswered = useMemo(() => {
    const s = new Set(
      notes
        .filter((n) => n.answer && n.trigger.startsWith("scale_"))
        .map((n) => `${n.recorded_at}|${n.trigger}`),
    );
    return s;
  }, [notes]);

  function keyOf(a: QuietEdgeAsk) {
    return `${a.recorded_at}|${a.trigger}`;
  }

  function submit(a: QuietEdgeAsk) {
    const k = keyOf(a);
    const answer = (drafts[k] || "").trim();
    if (!answer) {
      setErr("回答を入力してください");
      return;
    }
    setErr(null);
    setMsg(null);
    start(async () => {
      const r: QuietEdgeResult = await saveContextNote({
        recorded_at: a.recorded_at,
        trigger: a.trigger,
        prompt: a.prompt,
        answer,
      });
      if (!r.ok) {
        setErr(r.error);
        return;
      }
      setDrafts((d) => {
        const next = { ...d };
        delete next[k];
        return next;
      });
      setMsg(`${a.recorded_at} の補完を保存しました`);
      router.refresh();
    });
  }

  function submitScales() {
    const rows = OPTIONAL_SCALES.filter((s) => {
      const v = scales[s.key];
      return typeof v === "number" && v >= 1 && v <= 5;
    }).filter((s) => !scaleAnswered.has(`${scaleDate}|${s.trigger}`));

    if (!rows.length) {
      setErr("1〜5 の値を選ぶか、未保存の項目がありません");
      return;
    }
    setErr(null);
    setMsg(null);
    start(async () => {
      for (const s of rows) {
        const v = scales[s.key] as number;
        const r = await saveContextNote({
          recorded_at: scaleDate,
          trigger: s.trigger,
          prompt: s.prompt,
          answer: String(v),
        });
        if (!r.ok) {
          setErr(r.error);
          return;
        }
      }
      setScales({ sleepiness: "", subjective_snore: "" });
      setMsg(`${scaleDate} の任意スケールを保存しました`);
      router.refresh();
    });
  }

  return (
    <section className="card qe-ask-panel">
      <header>
        <span className="lvl">Ask</span>
        <strong>そこに対して何がありましたか？</strong>
      </header>
      <p className="meta">
        Journal 欠落・いびき急変・Health 欠測・治療日メモ空のときだけ聞きます。短いメモで十分。蓄積は観察レビューに使います。
      </p>

      {!asks.length ? (
        <p className="sum">いま未回答の問いはありません。</p>
      ) : (
        <ul className="qe-ask-list">
          {asks.map((a) => {
            const k = keyOf(a);
            return (
              <li key={k}>
                <p className="qe-ask-prompt">{a.prompt}</p>
                <p className="meta">理由: {a.reason}</p>
                <textarea
                  rows={3}
                  disabled={pending}
                  value={drafts[k] || ""}
                  placeholder="例: 飲み会あり／鼻詰まり／残業で遅い就寝…"
                  onChange={(e) =>
                    setDrafts((d) => ({ ...d, [k]: e.target.value }))
                  }
                />
                <div className="qe-form-actions">
                  <button
                    type="button"
                    className="btn"
                    disabled={pending}
                    onClick={() => submit(a)}
                  >
                    保存
                  </button>
                </div>
              </li>
            );
          })}
        </ul>
      )}

      <details className="qe-scale-optional">
        <summary>任意: 1〜5 スケール（本線ではない）</summary>
        <p className="meta">
          毎朝必須にはしません。気になった日だけ残せます。観察レビューの補完として使います。
        </p>
        <label className="qe-scale-date">
          <span className="meta">対象日</span>
          <input
            type="date"
            value={scaleDate}
            disabled={pending}
            onChange={(e) => setScaleDate(e.target.value)}
          />
        </label>
        <ul className="qe-scale-list">
          {OPTIONAL_SCALES.map((s) => {
            const done = scaleAnswered.has(`${scaleDate}|${s.trigger}`);
            return (
              <li key={s.key}>
                <span>
                  {s.label}
                  {done ? <span className="meta">（保存済）</span> : null}
                </span>
                <select
                  disabled={pending || done}
                  value={scales[s.key] === "" ? "" : String(scales[s.key])}
                  onChange={(e) => {
                    const raw = e.target.value;
                    setScales((cur) => ({
                      ...cur,
                      [s.key]: raw === "" ? "" : Number(raw),
                    }));
                  }}
                >
                  <option value="">—</option>
                  {[1, 2, 3, 4, 5].map((n) => (
                    <option key={n} value={n}>
                      {n}
                    </option>
                  ))}
                </select>
              </li>
            );
          })}
        </ul>
        <div className="qe-form-actions">
          <button
            type="button"
            className="btn"
            disabled={pending}
            onClick={submitScales}
          >
            スケールを保存
          </button>
        </div>
      </details>

      {err ? <p className="qe-err">{err}</p> : null}
      {msg ? <p className="qe-ok">{msg}</p> : null}

      {recentNotes.length ? (
        <div className="qe-notes-recent">
          <p className="meta">直近の補完メモ</p>
          <ul>
            {recentNotes.map((n) => (
              <li key={n.id}>
                <strong>{n.recorded_at}</strong>
                <span className="meta"> · {n.trigger}</span>
                <p className="sum">{n.answer}</p>
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </section>
  );
}
