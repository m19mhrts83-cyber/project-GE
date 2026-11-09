"use client";

import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "next/navigation";
import Icon from "./Icon";
import VoiceDock, { CommentList } from "./VoiceDock";
import { useVoiceLog } from "./useVoiceLog";
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
  const voice = useVoiceLog("312");
  // 本物のお題（312 collect が Slack から拾ったもの）。見本の前に並べる
  const [live, setLive] = useState<SeedTopic[]>([]);
  const allTopics = useMemo(() => [...live, ...SEED_TOPICS_312], [live]);
  const [sel, setSel] = useState<number | null>(1);
  const [rate, setRate] = useState<Record<number, "good" | "bad" | null>>({});

  useEffect(() => {
    setResults(loadStore().decisions.filter((d) => d.agentId === "312"));
    fetch("/api/topics")
      .then((r) => (r.ok ? r.json() : null))
      .then((j: { topics?: SeedTopic[] } | null) => {
        const list = j?.topics || [];
        setLive(list);
        // URL でお題を指定していなければ、本物の1件目から始める
        if (list.length && !topicFromUrl) setTopicId(list[0].id);
      })
      .catch(() => setLive([]));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (topicFromUrl) setTopicId(topicFromUrl);
  }, [topicFromUrl]);

  useEffect(() => {
    // ★推しの案があれば最初から選んでおく（見本は案1）
    setSel(allTopics.find((t) => t.id === topicId)?.starred ?? 1);
    setRate({});
    setEditIndex(null);
    setMsg("");
  }, [topicId, allTopics]);

  const topic: SeedTopic | null = useMemo(() => {
    const found = allTopics.find((t) => t.id === topicId);
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
    return allTopics[0];
  }, [topicId, customText, allTopics]);

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
    const chosenLabel = topic.proposals.find((p) => p.index === chosenIndex)?.label || "";
    const toTodoist = topic.dbId && /既存タスクへ追記|別タスクを作る/.test(chosenLabel) && choice !== "hold" && choice !== "none_of_above";
    setMsg(
      choice === "none_of_above"
        ? "「どれも違う」を記録した"
        : choice === "hold"
          ? "保留として記録した"
          : `案${chosenIndex}で記録した${toTodoist ? "（30分以内に Todoist へ反映）" : ""}`,
    );
    setEditIndex(null);
    const label =
      choice === "none_of_above"
        ? "どれも違う"
        : choice === "hold"
          ? "保留（まだ判断できない）"
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
    {
      const n = topic.proposals.reduce((a, p) => a + voice.forTarget(`${topic.id}#${p.index}`).length, 0);
      lines.push({ k: "voice", v: n ? `音声・文字コメント ${n}件（案ごとにログへ）` : "音声コメントなし" });
    }
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
          seedId: topic.dbId ? undefined : topic.id,
          topicDbId: topic.dbId,
          proposals: topic.proposals,
          decision: rec,
        }),
      });
      const j = (await res.json().catch(() => null)) as { persisted?: boolean } | null;
      setSaved((cur) => (cur ? { ...cur, status: j?.persisted ? "server" : "local" } : cur));
    } catch {
      setSaved((cur) => (cur ? { ...cur, status: "local" } : cur));
    }
  }

  if (!topic) return null;

  const doneRec = results.find((r) => r.topicId === topic.id);
  const doneIdx = topicIndexOf(allTopics, topic.id);
  const decidedProposal = doneRec?.chosenIndex
    ? topic.proposals.find((p) => p.index === doneRec.chosenIndex)
    : undefined;

  const nextPending = allTopics.find(
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
        {allTopics.map((t) => {
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
              {doneIdx + 1} / {allTopics.length}
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
          <>
            <p>{topic.topicText}</p>
            {topic.sourceRef ? (
              <a className="meta" href={topic.sourceRef} target="_blank" rel="noreferrer">
                元の発言を Slack で開く
              </a>
            ) : (
              <small className="meta">見本のお題</small>
            )}
          </>
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
                ) : doneRec.choice === "hold" ? (
                  "保留"
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
            {doneRec.choice === "none_of_above" || doneRec.choice === "hold" ? null : (
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
          <div
            key={p.index}
            data-tid={`${topic.id}#${p.index}`}
            data-tlabel={`${shortTitle(topic.title)} 案${p.index} ${p.label}`}
            className={`card opt targetable ${on ? "sel is-target" : ""}`}
            onClick={() => setSel(p.index)}
          >
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
            <CommentList comments={voice.forTarget(`${topic.id}#${p.index}`)} onDelete={voice.remove} onMove={voice.reassign} />
            <div className="rate" onClick={(e) => e.stopPropagation()}>
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
                  : r.choice === "hold"
                    ? "保留"
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
          <VoiceDock
            onComment={voice.add}
          />
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
            <button
              type="button"
              className="secondary ghost"
              onClick={() => decide("hold")}
            >
              保留
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
