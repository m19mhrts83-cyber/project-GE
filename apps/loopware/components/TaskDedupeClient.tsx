"use client";

import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "next/navigation";
import Icon from "./Icon";
import SaveSheet, { type SaveLine, type SaveStatus } from "./SaveSheet";
import {
  REASON_TAGS_312,
  SEED_TOPICS_312,
  type SeedTopic,
} from "@/lib/seed312";
import {
  formatDecisionMd,
  loadStore,
  removeDecision,
  upsertDecision,
  type DecisionRecord,
} from "@/lib/storage";

export default function TaskDedupeClient({
  initialTopicId = "",
}: {
  initialTopicId?: string;
}) {
  const sp = useSearchParams();
  const topicFromUrl = sp.get("topic") || initialTopicId;
  const [topicId, setTopicId] = useState(
    topicFromUrl || SEED_TOPICS_312[0].id,
  );
  const [customText, setCustomText] = useState("");
  const [editIndex, setEditIndex] = useState<number | null>(null);
  const [editBody, setEditBody] = useState("");
  const [tags, setTags] = useState<string[]>([]);
  const [note, setNote] = useState("");
  const [results, setResults] = useState<DecisionRecord[]>([]);
  const [msg, setMsg] = useState("");
  const [saved, setSaved] = useState<{
    rec: DecisionRecord;
    label: string;
    lines: SaveLine[];
    total: number;
    status: SaveStatus;
  } | null>(null);
  const [sel, setSel] = useState<number | null>(1);
  const [rate, setRate] = useState<Record<number, "good" | "bad" | null>>({});

  useEffect(() => {
    setResults(loadStore().decisions.filter((d) => d.agentId === "312"));
  }, []);

  useEffect(() => {
    if (topicFromUrl) setTopicId(topicFromUrl);
  }, [topicFromUrl]);

  useEffect(() => {
    setSel(1);
    setRate({});
    setEditIndex(null);
    setMsg("");
  }, [topicId]);

  const topic: SeedTopic | null = useMemo(() => {
    const found = SEED_TOPICS_312.find((t) => t.id === topicId);
    if (found) return found;
    if (topicId === "custom") {
      return {
        id: "custom",
        title: "手入力お題",
        topicText: customText,
        proposals: [
          { index: 1, label: "既存へ追記", body: "（案生成待ち・シード以外）" },
          { index: 2, label: "別タスク作成", body: "（案生成待ち・シード以外）" },
          { index: 3, label: "登録しない", body: "（案生成待ち・シード以外）" },
        ],
      };
    }
    return SEED_TOPICS_312[0];
  }, [topicId, customText]);

  function toggleTag(t: string) {
    setTags((prev) =>
      prev.includes(t) ? prev.filter((x) => x !== t) : [...prev, t],
    );
  }

  async function decide(
    choice: DecisionRecord["choice"],
    chosenIndex?: number,
    finalText?: string,
    beforeText?: string,
  ) {
    if (!topic) return;
    const rec: DecisionRecord = {
      topicId: topic.id,
      agentId: "312",
      choice,
      chosenIndex,
      finalText,
      beforeText,
      afterText: finalText,
      reasonTags: tags,
      freeNote:
        [note, ...Object.entries(rate).map(([i, v]) => (v ? `案${i}=${v}` : ""))]
          .filter(Boolean)
          .join(" / ") || undefined,
      decidedAt: new Date().toISOString(),
      decidedVia: "app",
    };
    upsertDecision(rec);
    setResults(loadStore().decisions.filter((d) => d.agentId === "312"));
    setMsg(choice === "none_of_above" ? "「どれも違う」を記録した" : `案${chosenIndex}で記録した`);
    setEditIndex(null);
    const label =
      choice === "none_of_above"
        ? "どれも違う"
        : `案${chosenIndex} ${topic.proposals.find((p) => p.index === chosenIndex)?.label ?? ""}${choice === "edit_use" ? "（直して使う）" : ""}`;
    const rates = Object.entries(rate)
      .filter(([, v]) => v)
      .map(([i, v]) => `案${i}=${v === "good" ? "良い" : "悪い"}`)
      .join(" / ");
    const lines: SaveLine[] = [
      { k: "decision", v: label },
      { k: "reason", v: tags.join("・") || "選ぶだけで保存（理由は任意）" },
      { k: "rating", v: rates || "評価なし" },
      { k: "note", v: note || "一言なし" },
    ];
    if (choice === "edit_use") lines.push({ k: "diff", v: "直す前と直した後を保存" });
    setSaved({
      rec,
      label,
      lines,
      total: loadStore().decisions.length,
      status: "pending",
    });
    try {
      const res = await fetch("/api/decide", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          agentId: "312",
          topicText: topic.topicText,
          seedId: topic.id,
          proposals: topic.proposals,
          decision: rec,
        }),
      });
      const j = (await res.json().catch(() => null)) as { persisted?: boolean } | null;
      setSaved((cur) => (cur ? { ...cur, status: j?.persisted === false ? "local" : "server" } : cur));
    } catch {
      setSaved((cur) => (cur ? { ...cur, status: "local" } : cur));
    }
  }

  if (!topic) return null;

  const doneRec = results.find((r) => r.topicId === topic.id);
  const doneIdx = topicIndexOf(SEED_TOPICS_312, topic.id);
  const decidedProposal = doneRec?.chosenIndex
    ? topic.proposals.find((p) => p.index === doneRec.chosenIndex)
    : undefined;

  const nextPending = SEED_TOPICS_312.find(
    (t) => t.id !== topic.id && !results.some((r) => r.topicId === t.id),
  );

  function reopen() {
    removeDecision(topic!.id, "312");
    setResults(loadStore().decisions.filter((d) => d.agentId === "312"));
    setMsg("");
    setSel(1);
    setRate({});
    setTags([]);
    setNote("");
  }
  const selProposal = topic.proposals.find((p) => p.index === sel);

  return (
    <div>
      {saved ? (
        <SaveSheet
          rec={saved.rec}
          decisionLabel={saved.label}
          lines={saved.lines}
          total={saved.total}
          status={saved.status}
          closeLabel={nextPending ? "次のお題へ" : "閉じる"}
          onClose={() => {
            setSaved(null);
            if (nextPending) setTopicId(nextPending.id);
          }}
          onUndo={() => {
            setSaved(null);
            reopen();
          }}
        />
      ) : null}
      <div className="tabs">
        {SEED_TOPICS_312.map((t) => {
          const done = results.some((r) => r.topicId === t.id);
          return (
            <button
              key={t.id}
              type="button"
              className={`tab ${topicId === t.id ? "active" : ""}`}
              onClick={() => setTopicId(t.id)}
            >
              {done ? <Icon name="check" size={14} stroke={3} /> : null}
              {shortTitle(t.title)}
            </button>
          );
        })}
        <button
          type="button"
          className={`tab ${topicId === "custom" ? "active" : ""}`}
          onClick={() => setTopicId("custom")}
        >
          手入力
        </button>
      </div>

      <div className="glass card topic">
        <div className="eyebrow" style={{ margin: 0 }}>
          お題
          {doneIdx >= 0 ? (
            <small className="mono">
              {doneIdx + 1} / {SEED_TOPICS_312.length}
            </small>
          ) : null}
        </div>
        {topicId === "custom" ? (
          <textarea
            rows={5}
            placeholder="発言と既存タスクをお題として貼る"
            value={customText}
            onChange={(e) => setCustomText(e.target.value)}
          />
        ) : (
          <p>{topic.topicText}</p>
        )}
      </div>

      {doneRec ? (
        <>
          <div className="eyebrow">
            決めた案<small>この1枚だけ残しています</small>
          </div>
          <div className="card opt sel done" style={{ minHeight: 0 }}>
            <div className="done-head">
              <span className="radio">
                <Icon name="check" size={12} stroke={3.5} />
              </span>
              <span style={{ flexGrow: 1 }}>
                {doneRec.choice === "none_of_above" ? (
                  "どれも違う"
                ) : (
                  <>
                    <span className="n">{doneRec.chosenIndex}</span>
                    {decidedProposal?.label}
                    {doneRec.choice === "edit_use" ? "（直して使う）" : ""}
                  </>
                )}
              </span>
              <span className="done-badge">決定済み</span>
            </div>
            {doneRec.choice === "none_of_above" ? null : (
              <dl className="rows" style={{ margin: 0 }}>
                {parseRows(doneRec.finalText || "").map((r, i) => (
                  <div key={i}>
                    <dt>{r.k}</dt>
                    <dd>{r.v}</dd>
                  </div>
                ))}
              </dl>
            )}
            {doneRec.reasonTags.length || doneRec.freeNote ? (
              <div className="meta">
                {[...doneRec.reasonTags, doneRec.freeNote].filter(Boolean).join(" ／ ")}
              </div>
            ) : null}
            <button type="button" className="secondary" onClick={reopen}>
              <Icon name="back" size={16} /> やっぱり見直す
            </button>
          </div>
        </>
      ) : (
        <>
      <div className="eyebrow">
        3案から選ぶ<small>良い／悪いの評価は任意</small>
      </div>
      {topic.proposals.map((p) => {
        const on = sel === p.index;
        const warn = /二重管理/.test(p.body);
        const rows = parseRows(p.body);
        return (
          <div key={p.index} className={`card opt ${on ? "sel" : ""}`}>
            <button
              type="button"
              className="opt-head"
              aria-pressed={on}
              aria-label={`案${p.index}を選ぶ`}
              onClick={() => setSel(p.index)}
            >
              <span className="radio">
                {on ? <Icon name="check" size={12} stroke={3.5} /> : null}
              </span>
              <span>
                <span className="n">{p.index}</span>
                {p.label}
              </span>
            </button>
            {editIndex === p.index ? (
              <textarea
                rows={8}
                value={editBody}
                onChange={(e) => setEditBody(e.target.value)}
              />
            ) : (
              <dl className="rows" style={{ margin: 0 }}>
                {rows.map((r, i) => (
                  <div key={i}>
                    <dt>{r.k}</dt>
                    <dd>{r.v}</dd>
                  </div>
                ))}
              </dl>
            )}
            {warn ? (
              <div className="warn">
                <Icon name="warn" size={14} stroke={2.2} />
                二重管理になります
              </div>
            ) : null}
            <div className="rate">
              <button
                type="button"
                className={`good ${rate[p.index] === "good" ? "on" : ""}`}
                aria-label={`案${p.index}は良い`}
                aria-pressed={rate[p.index] === "good"}
                onClick={() =>
                  setRate({ ...rate, [p.index]: rate[p.index] === "good" ? null : "good" })
                }
              >
                <Icon name="thumb" size={16} />
              </button>
              <button
                type="button"
                className={`bad ${rate[p.index] === "bad" ? "on" : ""}`}
                aria-label={`案${p.index}は悪い`}
                aria-pressed={rate[p.index] === "bad"}
                onClick={() =>
                  setRate({ ...rate, [p.index]: rate[p.index] === "bad" ? null : "bad" })
                }
              >
                <Icon name="thumb" size={16} flip />
              </button>
            </div>
          </div>
        );
      })}

      <div className="eyebrow">
        決め手<small>押すだけ・任意</small>
      </div>
      <div className="tags">
        {REASON_TAGS_312.map((t) => (
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
        placeholder="一言（なくても保存できる）"
      />

        </>
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
                <strong>{labelOf(r.topicId)}</strong> ·{" "}
                {r.choice === "none_of_above"
                  ? "どれも違う"
                  : r.chosenIndex != null
                    ? `案${r.chosenIndex}`
                    : r.choice}
              </span>
            </div>
            <div className="meta">
              {(r.reasonTags || []).join(" / ") || "理由タグなし"}
            </div>
            <div className="btn-row">
              <button
                type="button"
                onClick={() => {
                  void navigator.clipboard.writeText(formatDecisionMd(r));
                  setMsg("MDをコピーした");
                }}
              >
                記録をコピー
              </button>
            </div>
          </li>
        ))}
      </ul>

      {doneRec ? null : (
      <div className="bar">
        <div className="bar-in">
          {msg || doneRec ? (
            <div className="ok-line" role="status">
              <Icon name="check" size={16} stroke={2.6} />
              {msg || "記録済み"}
            </div>
          ) : null}
          <div className="two">
            <button
              type="button"
              className="secondary ghost"
              onClick={() => decide("none_of_above")}
            >
              どれも違う
            </button>
            {editIndex != null ? (
              <button
                type="button"
                className="secondary"
                onClick={() => setEditIndex(null)}
              >
                直すのをやめる
              </button>
            ) : (
              <button
                type="button"
                className="secondary"
                disabled={!selProposal}
                onClick={() => {
                  if (!selProposal) return;
                  setEditIndex(selProposal.index);
                  setEditBody(selProposal.body);
                }}
              >
                直して使う
              </button>
            )}
          </div>
          {editIndex != null ? (
            <button
              type="button"
              className="cta big"
              onClick={() => {
                const p = topic.proposals.find((x) => x.index === editIndex);
                if (p) void decide("edit_use", p.index, editBody, p.body);
              }}
            >
              <Icon name="check" size={20} stroke={2.6} />
              直した案{editIndex}で決める
            </button>
          ) : (
            <button
              type="button"
              className="cta big"
              disabled={!selProposal}
              onClick={() =>
                selProposal && void decide("use", selProposal.index, selProposal.body)
              }
            >
              <Icon name="check" size={20} stroke={2.6} />
              {selProposal ? `案${selProposal.index}を使う` : "案を選んでください"}
            </button>
          )}
        </div>
      </div>
      )}
    </div>
  );
}

function topicIndexOf(list: SeedTopic[], id: string) {
  return list.findIndex((t) => t.id === id);
}

function labelOf(id: string) {
  const t = SEED_TOPICS_312.find((x) => x.id === id);
  return t ? shortTitle(t.title) : id;
}

/** 「例1 青葉社見積（Slack+メール）」→「青葉社見積」 */
function shortTitle(title: string) {
  return title.replace(/^例\d+\s*/, "").replace(/[（(].*$/, "").trim();
}

/** 「キー：値」行を表の行にする。キーが無い行は直前の値に続ける */
function parseRows(body: string) {
  const rows: { k: string; v: string }[] = [];
  for (const line of body.split("\n")) {
    const m = line.match(/^([^：]{1,8})：(.*)$/);
    if (m) rows.push({ k: m[1], v: m[2] });
    else if (rows.length) rows[rows.length - 1].v += `\n${line}`;
    else rows.push({ k: "", v: line });
  }
  return rows;
}
