"use client";

import { useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import Icon from "./Icon";
import { REASON_TAGS_313 } from "@/lib/seed312";
import {
  formatDecisionMd,
  loadStore,
  upsertDecision,
  type DecisionRecord,
} from "@/lib/storage";

type Tab = "cleanup" | "misses";

export default function CleanupClient({
  initialTaskId = "",
  initialTab = "cleanup",
}: {
  initialTaskId?: string;
  initialTab?: Tab;
}) {
  const sp = useSearchParams();
  const taskId = sp.get("task") || initialTaskId;
  const [tab, setTab] = useState<Tab>(
    sp.get("tab") === "misses" ? "misses" : initialTab,
  );
  const [title, setTitle] = useState(taskId ? `Task ${taskId}` : "");
  const [due, setDue] = useState("");
  const [note, setNote] = useState("");
  const [tags, setTags] = useState<string[]>([]);
  const [results, setResults] = useState<DecisionRecord[]>([]);
  const [msg, setMsg] = useState("");
  const [act, setAct] = useState<"close" | "reschedule" | "drop">("close");

  useEffect(() => {
    setResults(loadStore().decisions.filter((d) => d.agentId === "313"));
  }, []);

  function toggleTag(t: string) {
    setTags((prev) =>
      prev.includes(t) ? prev.filter((x) => x !== t) : [...prev, t],
    );
  }

  async function decide(choice: DecisionRecord["choice"]) {
    const tid = taskId || `manual-${Date.now()}`;
    const rec: DecisionRecord = {
      topicId: tid,
      agentId: "313",
      choice,
      finalText: title || tid,
      reasonTags: tags,
      freeNote: [note, due ? `due=${due}` : ""].filter(Boolean).join(" / ") || undefined,
      decidedAt: new Date().toISOString(),
      decidedVia: "app",
    };
    upsertDecision(rec);
    setResults(loadStore().decisions.filter((d) => d.agentId === "313"));
    setMsg(`記録した：${ACTS.find((a) => a.id === choice)?.label ?? choice}`);
    try {
      await fetch("/api/decide", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          agentId: "313",
          topicText: title || tid,
          seedId: tid,
          decision: rec,
          todoistTaskId: taskId || null,
        }),
      });
    } catch {
      /* ok */
    }
  }

  const cur = ACTS.find((a) => a.id === act) ?? ACTS[0];

  return (
    <div>
      <div className="seg" style={{ marginBottom: 14 }}>
        <a
          href="?tab=cleanup"
          className={tab === "cleanup" ? "active" : ""}
          onClick={(e) => {
            e.preventDefault();
            setTab("cleanup");
          }}
        >
          片付ける
        </a>
        <a
          href="?tab=misses"
          className={tab === "misses" ? "active" : ""}
          onClick={(e) => {
            e.preventDefault();
            setTab("misses");
          }}
        >
          閉じ漏れ
        </a>
      </div>

      {tab === "cleanup" ? (
        <>
          <div className="card" style={{ display: "flex", flexDirection: "column", gap: 10 }}>
            <div className="eyebrow" style={{ margin: 0 }}>TASK</div>
            <input
              type="text"
              style={{ fontSize: 17, fontWeight: 700 }}
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="タスク名"
              aria-label="タスク名"
            />
            <div className="btn-row">
              {taskId ? (
                <span className="chip-task mono">id {taskId}</span>
              ) : (
                <span className="chip-task">手入力</span>
              )}
              {due ? <span className="chip-task">期日 {due}</span> : null}
            </div>
          </div>

          <div className="eyebrow">どうする？</div>
          {ACTS.map((a) => (
            <button
              key={a.id}
              type="button"
              className={`act ${a.id} ${act === a.id ? "on" : ""}`}
              aria-pressed={act === a.id}
              onClick={() => setAct(a.id)}
            >
              <span className="ico">
                <Icon name={a.icon} size={24} />
              </span>
              <span>
                <strong>{a.label}</strong>
                <span className="d">{a.desc}</span>
              </span>
            </button>
          ))}

          {act === "reschedule" ? (
            <>
              <div className="eyebrow">新しい期日</div>
              <div className="tags">
                {DUE_CHIPS.map((c) => {
                  const v = c.value();
                  return (
                    <button
                      key={c.label}
                      type="button"
                      className={`tag ${due === v ? "on" : ""}`}
                      aria-pressed={due === v}
                      onClick={() => setDue(v)}
                    >
                      {c.label}
                    </button>
                  );
                })}
              </div>
              <input
                type="text"
                style={{ marginTop: 10 }}
                value={due}
                onChange={(e) => setDue(e.target.value)}
                placeholder="2026-11-14（空＝期日を外す）"
                aria-label="新しい期日"
              />
            </>
          ) : null}

          <div className="eyebrow">
            理由<small>押すだけ・任意</small>
          </div>
          <div className="tags">
            {REASON_TAGS_313.map((t) => (
              <button
                key={t}
                type="button"
                aria-pressed={tags.includes(t)}
                className={`tag ${tags.includes(t) ? "on" : ""}`}
                onClick={() => toggleTag(t)}
              >
                {t}
              </button>
            ))}
          </div>
          <input
            type="text"
            style={{ marginTop: 10 }}
            value={note}
            onChange={(e) => setNote(e.target.value)}
            placeholder="一言・根拠"
          />
        </>
      ) : (
        <div className="card">
          <div className="eyebrow" style={{ margin: 0 }}>閉じ漏れ（段階2）</div>
          <p className="meta">
            台帳送信済・PRマージ・watch解消・番頭さんの指摘・「これ済んだ」をここに並べる。
            検知スクリプト: <code>scripts/jarvis_todoist_313_done_elsewhere.py</code>
          </p>
          <p className="meta">現状は枠のみ。検知結果は API／state から流し込む。</p>
        </div>
      )}

      <div className="eyebrow">記録</div>
      <ul className="list glass">
        {results.length === 0 ? (
          <li className="meta">まだ記録がありません</li>
        ) : null}
        {results.map((r) => (
          <li key={`${r.topicId}-${r.decidedAt}`}>
            <div className="row">
              <span className="done-mark">
                <Icon name="check" size={12} stroke={3} />
              </span>
              <span style={{ flexGrow: 1 }}>
                <strong>{r.finalText || r.topicId}</strong> ·{" "}
                {ACTS.find((a) => a.id === r.choice)?.label ?? r.choice}
              </span>
            </div>
            <div className="meta">{(r.reasonTags || []).join(" / ") || "理由タグなし"}</div>
            <div className="btn-row">
              <button
                type="button"
                onClick={() => {
                  void navigator.clipboard.writeText(formatDecisionMd(r));
                  setMsg("コピーした");
                }}
              >
                記録をコピー
              </button>
            </div>
          </li>
        ))}
      </ul>

      {tab === "cleanup" ? (
        <div className="bar">
          <div className="bar-in">
            {msg ? (
              <div className="ok-line" role="status">
                <Icon name="check" size={16} stroke={2.6} />
                {msg}
              </div>
            ) : null}
            <button
              type="button"
              className="cta big"
              style={{ background: cur.color }}
              onClick={() => decide(cur.id)}
            >
              {cur.label} で記録する
            </button>
          </div>
        </div>
      ) : null}
    </div>
  );
}

const ACTS = [
  { id: "close", label: "済んだ", desc: "Todoist を完了にして記録", icon: "check", color: "var(--positive)" },
  { id: "reschedule", label: "いつ・優先", desc: "期日を動かす。外すことも選べる", icon: "calendar", color: "var(--accent)" },
  { id: "drop", label: "やめる", desc: "完了にして、やめた理由をコメント", icon: "trash", color: "var(--alert)" },
] as const;

function ymd(plusDays: number) {
  const d = new Date();
  d.setDate(d.getDate() + plusDays);
  const p = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`;
}

const DUE_CHIPS = [
  { label: "今日", value: () => ymd(0) },
  { label: "明日", value: () => ymd(1) },
  { label: "来週", value: () => ymd(7) },
  { label: "期日なし", value: () => "" },
];
