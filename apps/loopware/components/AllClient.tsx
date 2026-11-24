"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import {
  GENRE_LABEL,
  LATER,
  LEVEL_LABEL,
  adoptSuggestions,
  applyFilter,
  countBy,
  type AllItem,
  type Filter,
  type Genre,
  type Level,
} from "@/lib/allCore";
import { buildCleanupDecisions, type Choices } from "@/lib/cleanupBulk";

type Chosen = Record<string, string>;

/** 同時に送る数（メールは Jarvis 側の更新を通るので控えめに） */
async function pool<T>(list: T[], n: number, fn: (x: T) => Promise<void>) {
  let i = 0;
  await Promise.all(
    Array.from({ length: Math.min(n, list.length) }, async () => {
      while (i < list.length) await fn(list[i++]);
    }),
  );
}

export default function AllClient() {
  const [items, setItems] = useState<AllItem[] | null>(null);
  const [errors, setErrors] = useState<string[]>([]);
  const [err, setErr] = useState("");
  const [filter, setFilter] = useState<Filter>({ genre: "all", level: 0 });
  const [chosen, setChosen] = useState<Chosen>({});
  const [open, setOpen] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [report, setReport] = useState<string[]>([]);

  function load() {
    fetch("/api/all", { cache: "no-store" })
      .then((r) => r.json())
      .then((j) => {
        if (!j.ok) throw new Error(j.error || "読み込めませんでした");
        setItems(j.items);
        setErrors(j.errors || []);
      })
      .catch((e) => setErr(e instanceof Error ? e.message : String(e)));
  }
  useEffect(load, []);

  const all = items || [];
  const counts = useMemo(() => countBy(all), [all]);
  const shown = useMemo(() => applyFilter(all, filter), [all, filter]);
  const nChosen = Object.keys(chosen).length;
  const nSuggest = shown.filter((i) => i.suggest && !chosen[i.key]).length;

  function choose(it: AllItem, act: string) {
    setChosen((p) => {
      const n = { ...p };
      if (n[it.key] === act) delete n[it.key];
      else n[it.key] = act;
      return n;
    });
  }

  async function submit() {
    if (!items) return;
    setSaving(true);
    setReport([]);
    const done = new Set<string>();
    const lines: string[] = [];
    const picked = items.filter((i) => chosen[i.key]);
    try {
      // 片付け: まとめて1回
      const cl = picked.filter((i) => i.genre === "cleanup" && i.cleanup);
      if (cl.length) {
        const ch: Choices = {};
        for (const i of cl) {
          const a = chosen[i.key];
          ch[i.id] = a === LATER ? { act: "keep" } : { act: a as "close" | "drop" };
        }
        const rows = buildCleanupDecisions(cl.map((i) => i.cleanup!), ch, Date.now().toString(36), new Date().toISOString());
        try {
          const r = await fetch("/api/cleanup", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ decisions: rows }) });
          const j = await r.json();
          const failed = new Set<string>((j.failed || []).map((s: string) => s.split(":").slice(1).join(":")));
          for (const i of cl) if (!failed.has(i.id) && (j.ok || j.saved)) done.add(i.key);
          lines.push(`片付け ${j.saved ?? 0}件を記録（30分以内にTodoistへ反映）${failed.size ? `／失敗${failed.size}件` : ""}`);
        } catch {
          lines.push("片付け: 保存できませんでした");
        }
      }
      // メール: 1件ずつ（Jarvisの状態を変える）
      const ml = picked.filter((i) => i.genre === "mail");
      if (ml.length) {
        let ok = 0;
        const run = Date.now().toString(36);
        await pool(ml, 3, async (i) => {
          const choice = chosen[i.key] === LATER ? "hesitate" : chosen[i.key];
          try {
            const r = await fetch("/api/desk/decide", {
              method: "POST",
              headers: { "content-type": "application/json" },
              body: JSON.stringify({ itemId: i.id, choice, idemKey: `loopware:all:${i.id}:${choice}:${run}`, subject: i.title, partner: i.mail?.partner, lane: i.mail?.lane, note: "まとめて判断" }),
            });
            const j = await r.json();
            if (j.ok) {
              ok += 1;
              done.add(i.key);
            }
          } catch {
            /* 失敗は残す */
          }
        });
        lines.push(`メール ${ok}/${ml.length}件${ok < ml.length ? "（残りは失敗。もう一度押せます）" : ""}`);
      }
      // お題: 1件ずつ
      const tl = picked.filter((i) => i.genre === "topic" && i.topic);
      if (tl.length) {
        let ok = 0;
        await pool(tl, 3, async (i) => {
          const a = chosen[i.key];
          const idx = a.startsWith("pick:") ? Number(a.slice(5)) : undefined;
          try {
            const r = await fetch("/api/decide", {
              method: "POST",
              headers: { "content-type": "application/json" },
              body: JSON.stringify({
                agentId: "312",
                topicText: i.topic!.text,
                topicDbId: i.id,
                proposals: i.topic!.proposals,
                decision: { choice: a === LATER ? "hold" : "use", chosenIndex: idx, reasonTags: [], freeNote: "まとめて判断", decidedVia: "app" },
              }),
            });
            const j = await r.json();
            if (j.ok && j.persisted) {
              ok += 1;
              done.add(i.key);
            }
          } catch {
            /* 失敗は残す */
          }
        });
        lines.push(`お題 ${ok}/${tl.length}件`);
      }
    } finally {
      // 記録できたものは一覧から外し、できなかったものは選んだまま残す
      setItems((cur) => (cur || []).filter((i) => !done.has(i.key)));
      setChosen((p) => Object.fromEntries(Object.entries(p).filter(([k]) => !done.has(k))));
      setReport(lines);
      setSaving(false);
    }
  }

  if (err) return <p className="meta">{err}</p>;
  if (!items) return <p className="meta">読み込み中…</p>;

  const genres: (Genre | "all")[] = ["all", "mail", "cleanup", "topic"];
  const levels: (Level | 0)[] = [0, 3, 2, 1];

  return (
    <div className="all-wrap">
      <div className="glass all-head">
        <div className="all-total">
          <b>{counts.total}</b>
          <span>件が判断待ち</span>
        </div>
        <div className="meta">
          高 {counts.level[3]}／中 {counts.level[2]}／低 {counts.level[1]}　（メール {counts.genre.mail}・片付け {counts.genre.cleanup}・お題 {counts.genre.topic}）
        </div>
        <div className="all-chips" role="group" aria-label="重要度">
          {levels.map((l) => (
            <button key={l} className={`chip ${filter.level === l ? "on" : ""} ${l ? `lv${l}` : ""}`} onClick={() => setFilter({ ...filter, level: l })}>
              {l === 0 ? "すべて" : `重要度 ${LEVEL_LABEL[l]}`}
              {l ? ` ${counts.level[l]}` : ""}
            </button>
          ))}
        </div>
        <div className="all-chips" role="group" aria-label="ジャンル">
          {genres.map((g) => (
            <button key={g} className={`chip ${filter.genre === g ? "on" : ""}`} onClick={() => setFilter({ ...filter, genre: g })}>
              {g === "all" ? "ぜんぶ" : GENRE_LABEL[g]}
              {g === "all" ? "" : ` ${counts.genre[g]}`}
            </button>
          ))}
        </div>
        <div className="all-quick">
          <button className="secondary" onClick={() => setFilter({ genre: "all", level: 3 })}>
            時間がない：重要度「高」だけ
          </button>
          <button className="secondary" disabled={!nSuggest} onClick={() => setChosen((p) => adoptSuggestions(shown, p))}>
            表示中の提案どおり {nSuggest}件を選ぶ
          </button>
        </div>
      </div>

      {errors.length > 0 && (
        <div className="wk-banner">
          <span>読み込めなかったジャンルがあります（空ではありません）：{errors.join(" ／ ")}</span>
        </div>
      )}
      {report.length > 0 && (
        <div className="wk-banner ok">
          <span>{report.join("　")}</span>
        </div>
      )}

      {!shown.length && (
        <div className="glass wk-empty">
          <b>{counts.total ? "この条件に当てはまるものはありません" : "いま判断待ちはありません"}</b>
          <span className="meta">{counts.total ? "絞り込みを「すべて」に戻すと残りが見えます。" : "新しい判断が出ると、ここに並びます。"}</span>
        </div>
      )}

      {shown.map((it) => {
        const v = chosen[it.key];
        const expanded = open === it.key;
        return (
          <div key={it.key} className={`glass all-row lv${it.level} ${v ? "picked" : ""}`}>
            <button className="all-main-btn" onClick={() => setOpen(expanded ? null : it.key)} aria-expanded={expanded}>
              <span className={`all-lv lv${it.level}`}>{LEVEL_LABEL[it.level]}</span>
              <span className="all-tt">
                <b>{it.title}</b>
                <span className="meta">
                  {GENRE_LABEL[it.genre]}｜{it.sub}
                </span>
              </span>
            </button>
            {expanded && (
              <div className="all-detail">
                {it.summary && <div className="meta">{it.summary}</div>}
                <div className="meta">重要度の理由: {it.why}</div>
                {it.link && (
                  <Link className="wk-link" href={it.link} target={it.link.startsWith("http") ? "_blank" : undefined}>
                    {it.genre === "mail" ? "開いて返信する／全文を見る" : it.genre === "topic" ? "案の中身を見る" : "元のメールを開く"}
                  </Link>
                )}
              </div>
            )}
            <div className="all-acts">
              {it.options.map((o) => (
                <button key={o.act} className={`${v === o.act ? "primary" : ""} ${it.suggest === o.act ? "sug" : ""}`} onClick={() => choose(it, o.act)}>
                  {o.label}
                  {it.suggest === o.act ? " ★" : ""}
                </button>
              ))}
            </div>
          </div>
        );
      })}

      <div className="all-bar">
        <div className="all-bar-in">
          <span>
            <b>{nChosen}</b>件を選択中
            {nChosen > 0 && (
              <button className="wk-link" onClick={() => setChosen({})}>
                全部外す
              </button>
            )}
          </span>
          <button className="primary" disabled={saving || !nChosen} onClick={submit}>
            {saving ? "保存中…" : `まとめて確定（${nChosen}）`}
          </button>
        </div>
      </div>
      <div className="meta" style={{ margin: "8px 0 0" }}>★ はAIのおすすめ。確定するまで何も変わりません。</div>
    </div>
  );
}
