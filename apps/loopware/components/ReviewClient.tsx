"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Icon from "./Icon";
import { jstDay, loadDaily, loadStore, loadVoice } from "@/lib/storage";

type Item = {
  at: string;
  agent: string;
  title: string;
  choice: string;
  reasons: string[];
  note: string;
  before: string;
  after: string;
  scope: string;
};
type VoiceItem = { at: string; target: string; text: string };
type Criterion = { id: string; text: string; range: string; basis: string; at: string };

const CHOICE: Record<string, string> = {
  take: "採る", skip: "見送る", hold: "保留", use: "案を使う", edit_use: "直して使う",
  none_of_above: "どれも違う", close: "済んだ", reschedule: "いつ・優先", drop: "やめる",
};
const lab = (c: string) => CHOICE[c] ?? c;

const STAGES = [
  { id: "now", name: "その場｜今回の修正に使う", ask: "以下の結果（本人の修正とコメント）に沿って、今回のタスク文を整えてください。この段階では、本人の恒常的な好みと決めつけないでください。" },
  { id: "ref", name: "〜10件｜参照例として渡す", ask: "以下の結果から、似た依頼の採用例と修正前後を選び、次のタスク案を依頼する文章に添える参照例を作ってください。" },
  { id: "rule", name: "〜30件｜共通点を基準案にする", ask: "以下の結果から、選んだものと選ばなかったものの共通点（見送り理由と原文）を整理し、基準案を出してください。本人の理由とAIの推測を分け、「今回だけ」の判断は基準案に入れないでください。本人が承認するまで基準にはしません。" },
  { id: "check", name: "〜100件｜点検と並べ替え", ask: "以下の結果から、案を作った後の点検項目（担当者・完了表現・作業の重複）と、候補の並べ方を提案してください。ツール内の自動変更はしません。" },
  { id: "result", name: "結果が出たら｜成果で基準を見直す", ask: "以下の結果と、下に追記する「Todoistへ登録した後の着手・完了・削除・取りこぼし」を照らし、現在の基準の維持・変更・取り消しを提案してください。" },
] as const;

function monday(d: Date) {
  const x = new Date(d);
  const day = (x.getDay() + 6) % 7;
  x.setDate(x.getDate() - day);
  x.setHours(0, 0, 0, 0);
  return x;
}
const fmt = (d: Date) => `${d.getMonth() + 1}/${d.getDate()}`;
const weekKey = (d: Date) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;

export default function ReviewClient() {
  const [start, setStart] = useState<Date>(() => monday(new Date()));
  const end = useMemo(() => {
    const e = new Date(start);
    e.setDate(e.getDate() + 7);
    return e;
  }, [start]);

  const [items, setItems] = useState<Item[]>([]);
  const [voice, setVoice] = useState<VoiceItem[]>([]);
  const [configured, setConfigured] = useState(false);
  const [lastReview, setLastReview] = useState<string | null>(null);
  const [dailyDone, setDailyDone] = useState<string[]>([]);
  const [criteria, setCriteria] = useState<Criterion[]>([]);
  const [critServer, setCritServer] = useState(false);
  const [stage, setStage] = useState<(typeof STAGES)[number]["id"]>("rule");
  const [form, setForm] = useState({ text: "", range: "", basis: "" });
  const [msg, setMsg] = useState("");
  const [result, setResult] = useState("");

  const load = useCallback(async () => {
    // 端末のログ
    const f = start.getTime();
    const t = end.getTime();
    const local: Item[] = loadStore()
      .decisions.filter((d) => {
        const at = new Date(d.decidedAt).getTime();
        return at >= f && at < t && !d.topicId.startsWith("prop-batch-");
      })
      .map((d) => ({
        at: d.decidedAt,
        agent: d.agentId,
        title: (d.finalText || d.topicId).split("\n")[0].slice(0, 80),
        choice: d.choice,
        reasons: d.reasonTags || [],
        note: d.freeNote || "",
        before: d.beforeText || "",
        after: d.afterText || "",
        scope: d.scope || "once",
      }));
    const lv: VoiceItem[] = loadVoice()
      .filter((c) => new Date(c.at).getTime() >= f && new Date(c.at).getTime() < t)
      .map((c) => ({ at: c.at, target: c.targetLabel, text: c.text }));
    try {
      const j = await (await fetch(`/api/review?from=${start.toISOString()}&to=${end.toISOString()}`)).json();
      setConfigured(!!j.configured);
      setLastReview(j.lastReview ?? null);
      const wk = Array.from({ length: 7 }, (_, k) => jstDay(new Date(start.getTime() + k * 86400000)));
      const localDays = Object.keys(loadDaily()).filter((d) => wk.includes(d));
      setDailyDone(Array.from(new Set([...(j.dailyDone || []), ...localDays])));
      if (j.configured) {
        // サーバのログを正とし、サーバに無い端末のログだけ足す
        const server: Item[] = j.items || [];
        const key = (x: Item) => `${x.agent}|${x.title}|${x.choice}`;
        const seen = new Set(server.map(key));
        setItems([...server, ...local.filter((x) => !seen.has(key(x)))]);
        setVoice([...(j.voice || []), ...lv.filter((x) => !(j.voice || []).some((y: VoiceItem) => y.text === x.text))]);
      } else {
        setItems(local);
        setVoice(lv);
      }
    } catch {
      setConfigured(false);
      setItems(local);
      setVoice(lv);
      const wk = Array.from({ length: 7 }, (_, k) => jstDay(new Date(start.getTime() + k * 86400000)));
      setDailyDone(Object.keys(loadDaily()).filter((d) => wk.includes(d)));
    }
  }, [start, end]);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    fetch("/api/criteria")
      .then((r) => r.json())
      .then((j) => {
        setCritServer(!!j.configured);
        if (j.configured) setCriteria(j.criteria || []);
        else {
          try {
            setCriteria(JSON.parse(localStorage.getItem("loopware_criteria_v1") || "[]"));
          } catch {
            /* ignore */
          }
        }
      })
      .catch(() => undefined);
  }, []);

  const saveLocalCrit = (list: Criterion[]) => {
    try {
      localStorage.setItem("loopware_criteria_v1", JSON.stringify(list));
    } catch {
      /* ignore */
    }
  };

  async function postCrit(op: string, c: Partial<Criterion>) {
    try {
      const r = await fetch("/api/criteria", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ op, id: c.id, text: c.text, range: c.range, basis: c.basis }),
      });
      const j = await r.json();
      return j.persisted === true;
    } catch {
      return false;
    }
  }

  async function approve() {
    if (!form.text.trim()) return;
    const c: Criterion = {
      id: `cr-${Date.now()}`,
      text: form.text.trim(),
      range: form.range.trim(),
      basis: form.basis.trim(),
      at: new Date().toISOString(),
    };
    const next = [c, ...criteria];
    setCriteria(next);
    saveLocalCrit(next);
    setForm({ text: "", range: "", basis: "" });
    const ok = await postCrit("approve", c);
    setMsg(ok ? "基準として承認し、Supabase に記録した" : "基準として承認した（端末のみ。サーバ未接続）");
  }

  async function revoke(c: Criterion) {
    const next = criteria.filter((x) => x.id !== c.id);
    setCriteria(next);
    saveLocalCrit(next);
    const ok = await postCrit("revoke", c);
    setMsg(ok ? "基準を取り消した（履歴は残る）" : "基準を取り消した（端末のみ）");
  }

  async function markReviewed() {
    const week = weekKey(start);
    try {
      const r = await fetch("/api/criteria", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ op: "review", week, text: `${items.length}件を確認` }),
      });
      const j = await r.json();
      if (j.persisted) setLastReview(new Date().toISOString());
      setMsg(j.persisted ? `${fmt(start)}〜の週をレビュー済みにした` : "レビュー済み（端末のみ。サーバ未接続）");
    } catch {
      setMsg("レビュー済み（端末のみ）");
    }
  }

  // ---- 集計 ----
  const n = (pred: (i: Item) => boolean) => items.filter(pred).length;
  const take = n((i) => i.choice === "take" || i.choice === "use" || i.choice === "close");
  const skip = n((i) => i.choice === "skip" || i.choice === "none_of_above" || i.choice === "drop");
  const hold = n((i) => i.choice === "hold");
  const edits = items.filter((i) => i.before && i.after && i.before !== i.after);
  const rules = items.filter((i) => i.scope === "rule");
  const tally = (pred: (i: Item) => boolean) => {
    const m: Record<string, number> = {};
    items.filter(pred).forEach((i) => i.reasons.forEach((r) => (m[r] = (m[r] ?? 0) + 1)));
    return Object.entries(m).sort((a, b) => b[1] - a[1]);
  };
  const skipWhy = tally((i) => i.choice === "skip" || i.choice === "none_of_above" || i.choice === "drop");
  const holdWhy = tally((i) => i.choice === "hold");
  const noWhy = items.filter((i) => ["skip", "hold", "none_of_above", "drop"].includes(i.choice) && !i.reasons.length).length;

  function bundle() {
    const st = STAGES.find((s) => s.id === stage)!;
    const lines: string[] = [];
    lines.push(`# 判断ログ（${fmt(start)}〜${fmt(new Date(end.getTime() - 86400000))}）`, "", `お願い：${st.ask}`, "");
    lines.push("## 注意", "- 顧客名・社名・連絡先は、渡す前に伏せてください。", "- これは「生の判断」です。AIの解釈は本人の理由として扱わず、承認された基準だけを基準とみなしてください。", "");
    lines.push("## 承認済みの基準", ...(criteria.length ? criteria.map((c) => `- ${c.text}${c.range ? `（範囲：${c.range}）` : ""}${c.basis ? `（根拠：${c.basis}）` : ""}`) : ["- なし"]), "");
    lines.push(`## 判断（${items.length}件）`);
    items.forEach((i, k) => {
      lines.push(`${k + 1}. [${i.agent}] ${i.title} → ${lab(i.choice)}${i.scope === "rule" ? "（次も同じに）" : "（今回だけ）"}`);
      if (i.reasons.length) lines.push(`   - 理由：${i.reasons.join("・")}`);
      else if (["skip", "hold", "none_of_above"].includes(i.choice)) lines.push("   - 理由：未選択");
      if (i.note) lines.push(`   - コメント：${i.note}`);
      if (i.before && i.after) lines.push(`   - 修正前：${i.before.replace(/\n/g, " / ")}`, `   - 修正後：${i.after.replace(/\n/g, " / ")}`);
    });
    if (voice.length) {
      lines.push("", "## 音声・文字コメント（見ていたカードごと）");
      voice.forEach((v) => lines.push(`- ${v.target}：${v.text}`));
    }
    if (stage === "result") lines.push("", "## Todoist 登録後の結果（本人が追記）", "- 着手・完了・削除・取りこぼし：", result || "（ここに書く）");
    return lines.join("\n");
  }

  const days = lastReview ? Math.floor((Date.now() - new Date(lastReview).getTime()) / 86400000) : null;

  return (
    <div>
      <div className="weeknav">
        <button type="button" aria-label="前の週" onClick={() => { const d = new Date(start); d.setDate(d.getDate() - 7); setStart(d); }}>
          <Icon name="back" size={18} />
        </button>
        <div>
          <strong className="mono">{fmt(start)}〜{fmt(new Date(end.getTime() - 86400000))}</strong>
          <div className="meta">
            {days === null ? "まだレビューしていません" : days === 0 ? "最後のレビュー：今日" : `最後のレビュー：${days}日前`}
            {days !== null && days >= 7 ? "（週1の確認の時期）" : ""}
          </div>
        </div>
        <button type="button" aria-label="次の週" disabled={end.getTime() > Date.now() + 7 * 86400000} onClick={() => { const d = new Date(start); d.setDate(d.getDate() + 7); setStart(d); }}>
          <Icon name="next" size={18} />
        </button>
      </div>
      <p className="meta" style={{ margin: "0 0 10px" }}>
        {configured ? "Supabase の判断ログと、この端末のログを合わせて見ています。" : "いまは、この端末のログだけを見ています（サーバ未接続）。"}
      </p>

      <div className="eyebrow">今週の判断<small>{items.length}件</small></div>
      <div className="tally">
        <div className="tally-i take"><b className="mono">{take}</b><span>採る・済み</span></div>
        <div className="tally-i skip"><b className="mono">{skip}</b><span>見送り</span></div>
        <div className="tally-i hold"><b className="mono">{hold}</b><span>保留</span></div>
      </div>
      <p className="meta" style={{ margin: "8px 0 0" }}>毎日の仕分け：<b className="mono">{dailyDone.length}</b>／7日 完了。直し {edits.length}件・音声コメント {voice.length}件・「次も同じに」{rules.length}件。件数は精度ではなく、確認する材料の量です。</p>

      <div className="eyebrow">見送り・保留の理由<small>分けて見る</small></div>
      <div className="card" style={{ display: "flex", flexDirection: "column", gap: 10 }}>
        <ReasonBars title="見送り" rows={skipWhy} />
        <ReasonBars title="保留" rows={holdWhy} />
        {noWhy ? <div className="meta">理由が未選択の見送り・保留：{noWhy}件（理由不明として扱い、同意とは見なしません）</div> : null}
        {!skipWhy.length && !holdWhy.length && !noWhy ? <div className="meta">この週の見送り・保留はありません</div> : null}
      </div>

      {edits.length ? (
        <>
          <div className="eyebrow">直しの前後<small>同じ直しが繰り返されていないか</small></div>
          <ul className="list glass">
            {edits.map((e, k) => (
              <li key={k}>
                <div className="row"><span className="src-badge">{e.agent}</span><strong>{e.title}</strong></div>
                <div className="diff"><span className="mono">前</span>{e.before.replace(/\n/g, " / ")}</div>
                <div className="diff after"><span className="mono">後</span>{e.after.replace(/\n/g, " / ")}</div>
                {e.reasons.length ? <div className="meta">理由：{e.reasons.join("・")}</div> : null}
              </li>
            ))}
          </ul>
        </>
      ) : null}

      <div className="eyebrow">「次も同じに」が付いた判断<small>基準の候補</small></div>
      {rules.length ? (
        <ul className="list glass">
          {rules.map((r, k) => (
            <li key={k}>
              <div className="row"><span className="vchip hold">{lab(r.choice)}</span><span style={{ flexGrow: 1 }}>{r.title}</span></div>
              {r.reasons.length || r.note ? <div className="meta">{[...r.reasons, r.note].filter(Boolean).join(" ／ ")}</div> : null}
              <div className="btn-row">
                <button type="button" onClick={() => setForm({ text: `${r.title}は、${r.reasons[0] || lab(r.choice)}として扱う`, range: "", basis: `${fmt(start)}週の判断1件` })}>
                  この判断から基準を書く
                </button>
              </div>
            </li>
          ))}
        </ul>
      ) : (
        <div className="card meta">「次も同じに」を付けた判断はありません。付けなければ「今回だけ」のままです。</div>
      )}

      <div className="eyebrow">承認した基準<small>{criteria.length}件・{critServer ? "Supabase に履歴あり" : "端末のみ"}</small></div>
      <ul className="list glass">
        {!criteria.length ? <li className="meta">まだ基準はありません。判断の共通点を見て、本人が認めたものだけを書きます。</li> : null}
        {criteria.map((c) => (
          <li key={c.id}>
            <div style={{ fontWeight: 700 }}>{c.text}</div>
            {c.range ? <div className="meta">範囲：{c.range}</div> : null}
            {c.basis ? <div className="meta">根拠：{c.basis}</div> : null}
            <div className="btn-row"><button type="button" onClick={() => revoke(c)}>取り消す</button></div>
          </li>
        ))}
      </ul>

      <div className="card editbox" style={{ marginTop: 10 }}>
        <div className="eyebrow" style={{ margin: 0 }}>基準を追加（本人が承認）</div>
        <label>基準<input type="text" value={form.text} onChange={(e) => setForm({ ...form, text: e.target.value })} placeholder="例：他人が担当と明記された作業は候補に含めない" /></label>
        <label>範囲<input type="text" value={form.range} onChange={(e) => setForm({ ...form, range: e.target.value })} placeholder="例：Slack・メール・日誌に担当者の記載がある作業" /></label>
        <label>根拠（ログ）<input type="text" value={form.basis} onChange={(e) => setForm({ ...form, basis: e.target.value })} placeholder="例：今週、同じ理由で見送った3件" /></label>
        <button type="button" className="cta" disabled={!form.text.trim()} onClick={approve}>基準として承認する</button>
      </div>

      <div className="eyebrow">チャットのAIに渡す<small>分析はツールの外で</small></div>
      <div className="card" style={{ display: "flex", flexDirection: "column", gap: 10 }}>
        <div className="tags">
          {STAGES.map((s) => (
            <button key={s.id} type="button" className={`tag ${stage === s.id ? "on" : ""}`} aria-pressed={stage === s.id} onClick={() => setStage(s.id)}>
              {s.name}
            </button>
          ))}
        </div>
        {stage === "result" ? (
          <textarea rows={3} value={result} onChange={(e) => setResult(e.target.value)} placeholder="Todoist に登録した後の着手・完了・削除・取りこぼし" />
        ) : null}
        <button type="button" className="secondary" onClick={() => { void navigator.clipboard.writeText(bundle()); setMsg("AIに渡す文章をコピーした"); }}>
          AIに渡す文章をコピー
        </button>
        <div className="meta">判断の生ログ・承認済みの基準・お願いをまとめます。渡す前に、顧客名などを伏せてください。</div>
      </div>

      <div className="bar">
        <div className="bar-in">
          {msg ? <div className="ok-line" role="status"><Icon name="check" size={16} stroke={2.6} />{msg}</div> : null}
          <button type="button" className="cta big" onClick={markReviewed}>
            <Icon name="check" size={20} stroke={2.6} />
            この週のレビューを完了にする
          </button>
        </div>
      </div>
    </div>
  );
}

function ReasonBars({ title, rows }: { title: string; rows: [string, number][] }) {
  if (!rows.length) return null;
  const max = Math.max(...rows.map((r) => r[1]));
  return (
    <div>
      <div className="meta" style={{ marginBottom: 4 }}>{title}</div>
      {rows.map(([t, c]) => (
        <div key={t} className="bar-row">
          <span>{t}</span>
          <i><u style={{ width: `${(c / max) * 100}%` }} /></i>
          <b className="mono">{c}</b>
        </div>
      ))}
    </div>
  );
}
