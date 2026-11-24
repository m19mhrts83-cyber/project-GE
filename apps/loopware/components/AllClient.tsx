"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import {
  GENRES,
  GENRE_LABEL,
  LATER,
  LEVEL_LABEL,
  SORT_LABEL,
  WEIGHT_MARK,
  adoptSuggestions,
  applyFilter,
  cleanupChoice,
  countBy,
  isCleanup,
  sortItems,
  type AllItem,
  type Filter,
  type Genre,
  type Level,
  type SortMode,
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

const LINK_LABEL: Record<Genre, string> = {
  mail: "開いて返信する／全文を見る",
  g318: "根拠・元のメールを開く",
  g313: "根拠（PR・Issue 等）を開く",
  star: "元のメールを開く",
  topic: "案の中身を見る",
  week: "今週の9件を開く",
  zaim: "Zaim の見直しを開く",
  rule: "今週の学びを開く",
};

export default function AllClient() {
  const [items, setItems] = useState<AllItem[] | null>(null);
  const [errors, setErrors] = useState<string[]>([]);
  const [err, setErr] = useState("");
  const [filter, setFilter] = useState<Filter>({ genre: "all", level: 0, weight: "all", suggestOnly: false });
  const [sort, setSort] = useState<SortMode>("level");
  const [chosen, setChosen] = useState<Chosen>({});
  const [checked, setChecked] = useState<Set<string>>(new Set());
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
  const shown = useMemo(() => sortItems(applyFilter(all, filter), sort), [all, filter, sort]);
  const nChosen = Object.keys(chosen).length;
  const nSuggest = shown.filter((i) => i.suggest && !chosen[i.key]).length;
  const nChecked = shown.filter((i) => checked.has(i.key) && i.suggest).length;

  function toggleCheck(key: string) {
    setChecked((p) => {
      const n = new Set(p);
      if (n.has(key)) n.delete(key);
      else n.add(key);
      return n;
    });
  }
  function adoptChecked() {
    setChosen((p) => {
      // チェックした分は、選び直していても提案どおりに戻す（本人がチェックで指したので）
      const out = { ...p };
      for (const i of shown) if (checked.has(i.key) && i.suggest) out[i.key] = i.suggest;
      return out;
    });
    setChecked(new Set());
  }

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
      const cl = picked.filter((i) => isCleanup(i) && i.cleanup && cleanupChoice(i, chosen[i.key]));
      if (cl.length) {
        const ch: Choices = {};
        for (const i of cl) ch[i.id] = cleanupChoice(i, chosen[i.key])!;
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
      // Zaim: 1件ずつ順に（同じ見張りの行を読み書きするので並べない）
      const zl = picked.filter((i) => i.genre === "zaim");
      if (zl.length) {
        let ok = 0;
        const run = Date.now().toString(36);
        await pool(zl, 1, async (i) => {
          try {
            const r = await fetch("/api/zaim", {
              method: "POST",
              headers: { "content-type": "application/json" },
              body: JSON.stringify({ id: i.id, verdict: chosen[i.key], note: "", idemKey: `lw-zaim-all-${i.id}-${run}` }),
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
        lines.push(`Zaim ${ok}/${zl.length}件`);
      }
      // ルール候補: 1件ずつ（採用＝承認。本人が押したものだけ）
      const rl = picked.filter((i) => i.genre === "rule" && i.rule);
      if (rl.length) {
        let ok = 0;
        const run = Date.now().toString(36);
        await pool(rl, 1, async (i) => {
          try {
            const r = await fetch("/api/rules/decide", {
              method: "POST",
              headers: { "content-type": "application/json" },
              body: JSON.stringify({ verdict: chosen[i.key], candidate: i.rule, idemKey: `lw-rule-all-${i.id}-${run}` }),
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
        lines.push(`ルール ${ok}/${rl.length}件`);
      }
    } finally {
      // 記録できたものは一覧から外し、できなかったものは選んだまま残す
      setItems((cur) => (cur || []).filter((i) => !done.has(i.key)));
      setChosen((p) => Object.fromEntries(Object.entries(p).filter(([k]) => !done.has(k))));
      setChecked((p) => new Set([...p].filter((k) => !done.has(k))));
      setReport(lines);
      setSaving(false);
    }
  }

  if (err) return <p className="meta">{err}</p>;
  if (!items) return <p className="meta">読み込み中…</p>;

  const genres: (Genre | "all")[] = ["all", ...GENRES.filter((g) => counts.genre[g] > 0)];
  const levels: (Level | 0)[] = [0, 3, 2, 1];
  const sorts: SortMode[] = ["level", "overdue", "quick"];

  return (
    <div className="all-wrap">
      <div className="glass all-head">
        <div className="all-total">
          <b>{counts.total}</b>
          <span>件が判断待ち</span>
        </div>
        <div className="meta">
          高 {counts.level[3]}／中 {counts.level[2]}／低 {counts.level[1]}　提案あり {counts.suggest}
          {counts.overdue ? `　期日超過 ${counts.overdue}` : ""}
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
              <span className="all-badge">{g === "all" ? counts.total : counts.genre[g]}</span>
            </button>
          ))}
        </div>
        <div className="all-chips" role="group" aria-label="判断の重さ・提案">
          <button className={`chip ${filter.weight === "quick" ? "on" : ""}`} onClick={() => setFilter({ ...filter, weight: filter.weight === "quick" ? "all" : "quick" })}>
            すぐ決まる {counts.weight.quick}
          </button>
          <button className={`chip ${filter.weight === "deep" ? "on" : ""}`} onClick={() => setFilter({ ...filter, weight: filter.weight === "deep" ? "all" : "deep" })}>
            じっくり {counts.weight.deep}
          </button>
          <button className={`chip ${filter.suggestOnly ? "on" : ""}`} onClick={() => setFilter({ ...filter, suggestOnly: !filter.suggestOnly })}>
            提案ありだけ {counts.suggest}
          </button>
        </div>
        <div className="all-chips" role="group" aria-label="並べ替え">
          {sorts.map((m) => (
            <button key={m} className={`chip ${sort === m ? "on" : ""}`} onClick={() => setSort(m)}>
              {SORT_LABEL[m]}
            </button>
          ))}
        </div>
        <div className="all-quick">
          <button className="secondary" onClick={() => setFilter({ genre: "all", level: 3, weight: "all", suggestOnly: false })}>
            時間がない：重要度「高」だけ
          </button>
          <button className="secondary" disabled={!nSuggest} onClick={() => setChosen((p) => adoptSuggestions(shown, p))}>
            表示中の提案どおり {nSuggest}件を選ぶ
          </button>
          <button className="secondary" disabled={!nChecked} onClick={adoptChecked}>
            チェックした {nChecked}件を提案どおりに
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
            <div className="all-row-top">
              {it.suggest ? (
                <input
                  type="checkbox"
                  className="all-check"
                  aria-label="提案どおりの対象にする"
                  checked={checked.has(it.key)}
                  onChange={() => toggleCheck(it.key)}
                />
              ) : (
                <span className="all-check-sp" />
              )}
              <button className="all-main-btn" onClick={() => setOpen(expanded ? null : it.key)} aria-expanded={expanded}>
                <span className={`all-lv lv${it.level}`}>{LEVEL_LABEL[it.level]}</span>
                <span className="all-tt">
                  <b>{it.title}</b>
                  <span className="meta">
                    <span className={`all-gtag g-${it.genre}`}>{GENRE_LABEL[it.genre]}</span>
                    {it.weight && WEIGHT_MARK[it.weight] && <span className={`all-wtag w-${it.weight}`}>{WEIGHT_MARK[it.weight]}</span>}
                    {(it.overdue ?? 0) > 0 && <span className="all-otag">{it.overdue}日超過</span>}
                    {it.sub}
                  </span>
                  {it.suggest && <span className="meta all-sugline">提案: {it.options.find((o) => o.act === it.suggest)?.label}（{it.why}）</span>}
                </span>
              </button>
            </div>
            {expanded && (
              <div className="all-detail">
                {it.summary && <div className="meta">{it.summary}</div>}
                <div className="meta">理由: {it.why}</div>
                {it.weightWhy && <div className="meta">重さ: {it.weightWhy}</div>}
                {it.link && (
                  <Link className="wk-link" href={it.link} target={it.link.startsWith("http") ? "_blank" : undefined}>
                    {LINK_LABEL[it.genre]}
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
              {!it.options.length && it.link && (
                <Link className="all-open" href={it.link}>
                  開いて決める
                </Link>
              )}
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
