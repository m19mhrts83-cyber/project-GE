"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";
import Icon from "./Icon";
import LogJar, { type Bead } from "./LogJar";
import VoicePanel from "./VoicePanel";
import { MAIL_REASON_TAGS, STAY_REASON_TAGS, type WeekTally } from "@/lib/decisionContract";
import { SENDER_POLICIES, type SenderPolicy } from "@/lib/senderPolicyCore";
import { agoLabel, stateLine, type DeskCard, type DeskChoice } from "@/lib/deskCore";

/**
 * 判断デスク（/desk?surface=triage）。メールを1件ずつ大きく出して判断する。
 * - 1 返信する（Jarvis の返信画面へ）／2 見送る／3 ToDo／4 迷う／0 回答不要
 * - 理由はすべて任意。押さなくても 5 秒で次へ
 * - 迷った・見ていないは NG に混ぜない（粒の色が違う）
 * - 表示から判断までの時間を測って一緒に残す
 */

type Phase =
  | { k: "card" }
  | { k: "reason"; key: string; choice: DeskChoice; itemId: string }
  | { k: "opened" };

const QUEUE_KEY = "loopware_desk_queue_v1";
const AUTO_MS = 5000;

const MAIL_TAGS = (["no_reply", "self_or_grok", "handled", "notnow", "not_important", "other"] as const).map((k) => ({
  k,
  label: MAIL_REASON_TAGS[k],
}));
const STAY_TAGS = (Object.keys(STAY_REASON_TAGS) as (keyof typeof STAY_REASON_TAGS)[]).map((k) => ({
  k,
  label: STAY_REASON_TAGS[k],
}));

const CHOICE_BEAD: Record<DeskChoice, Bead> = { skip: "ng", todo: "take", done: "take", hesitate: "hesitate" };
const CHOICE_LABEL: Record<DeskChoice, string> = {
  skip: "見送りました",
  todo: "ToDo に入れました",
  done: "回答不要にしました",
  hesitate: "迷うにしました（NGにはしません）",
};

function uid(): string {
  try {
    return crypto.randomUUID();
  } catch {
    return `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`;
  }
}

type Queued = { url: string; body: unknown };

function readQueue(): Queued[] {
  try {
    return JSON.parse(localStorage.getItem(QUEUE_KEY) || "[]") as Queued[];
  } catch {
    return [];
  }
}
function writeQueue(q: Queued[]) {
  try {
    localStorage.setItem(QUEUE_KEY, JSON.stringify(q.slice(-50)));
  } catch {
    /* 端末に置けなくても続ける */
  }
}

async function post(url: string, body: unknown): Promise<{ ok: boolean; status: number; json: Record<string, unknown> }> {
  const r = await fetch(url, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(body) });
  let json: Record<string, unknown> = {};
  try {
    json = await r.json();
  } catch {
    /* 空 */
  }
  return { ok: r.ok && json.ok !== false, status: r.status, json };
}

export default function DeskClient() {
  const sp = useSearchParams();
  const item = sp.get("item");
  const fromKurashift = sp.get("from") === "kurashift";

  const [cards, setCards] = useState<DeskCard[] | null>(null);
  const [idx, setIdx] = useState(0);
  const [tallyWeek, setTallyWeek] = useState<WeekTally | null>(null);
  const [beads, setBeads] = useState<Bead[]>([]);
  const [phase, setPhase] = useState<Phase>({ k: "card" });
  const [toast, setToast] = useState("");
  const [error, setError] = useState("");
  const [dash, setDash] = useState("https://jarvis-dashboard-amber.vercel.app");
  const [busy, setBusy] = useState(false);
  const [left, setLeft] = useState(AUTO_MS);
  const [selLine, setSelLine] = useState<number | null>(null);
  const [pending, setPending] = useState(0);

  const shownAt = useRef<string>(new Date().toISOString());
  const firstTouch = useRef<string | null>(null);
  const card = cards ? cards[idx] : undefined;

  useEffect(() => {
    if (fromKurashift) document.documentElement.dataset.app = "kurashift";
  }, [fromKurashift]);

  // 端末に溜まった判断（電波が切れていた分）を送る。同じ鍵なので二重にはならない
  const flush = useCallback(async () => {
    const q = readQueue();
    if (!q.length) return setPending(0);
    const rest: Queued[] = [];
    for (const x of q) {
      try {
        const r = await post(x.url, x.body);
        if (!r.ok && r.status >= 500) rest.push(x);
      } catch {
        rest.push(x);
      }
    }
    writeQueue(rest);
    setPending(rest.length);
  }, []);

  useEffect(() => {
    void flush();
    (async () => {
      try {
        const r = await fetch(`/api/desk?surface=triage${item ? `&item=${encodeURIComponent(item)}` : ""}`, { cache: "no-store" });
        const j = await r.json();
        if (!j.ok) throw new Error(j.error || "読めませんでした");
        setCards(j.cards || []);
        setTallyWeek(j.tally || null);
        if (j.dashboard) setDash(j.dashboard);
      } catch (e) {
        setError(e instanceof Error ? e.message : String(e));
        setCards([]);
      }
    })();
  }, [item, flush]);

  // カードが替わったら時計を戻す
  useEffect(() => {
    shownAt.current = new Date().toISOString();
    firstTouch.current = null;
    setSelLine(null);
  }, [idx, cards]);

  const touch = useCallback(() => {
    if (!firstTouch.current) firstTouch.current = new Date().toISOString();
  }, []);

  const next = useCallback(() => {
    setPhase({ k: "card" });
    setIdx((i) => i + 1);
  }, []);

  const flash = (s: string) => {
    setToast(s);
    window.setTimeout(() => setToast(""), 2400);
  };

  const decide = useCallback(
    async (choice: DeskChoice) => {
      if (!card || busy) return;
      touch();
      const key = `lw-desk-${uid()}`;
      const body = {
        itemId: card.id,
        choice,
        idemKey: key,
        subject: card.subject,
        partner: card.who,
        lane: card.lane,
        appliedRules: card.appliedRules,
        timing: { shown_at: shownAt.current, first_touch_at: firstTouch.current, decided_at: new Date().toISOString() },
      };
      setBusy(true);
      // 粒は先に落とす（押した手応え）。失敗したら端末に溜めて後で送る
      setBeads((b) => [...b, CHOICE_BEAD[choice]]);
      try {
        const r = await post("/api/desk/decide", body);
        if (!r.ok && r.status !== 409) throw new Error(String(r.json.error || r.status));
        if (!r.ok) {
          flash(String(r.json.error || "Jarvis 側で処理できませんでした"));
        } else {
          const n = (tallyWeek?.total || 0) + beads.length + 1;
          flash(`✓ ${CHOICE_LABEL[choice]}・判断ログに記録（今週 ${n} 件）`);
        }
      } catch {
        writeQueue([...readQueue(), { url: "/api/desk/decide", body }]);
        setPending(readQueue().length);
        flash("電波が弱いので端末に預かりました。次に開いたとき送ります");
      } finally {
        setBusy(false);
      }
      if (choice === "skip" || choice === "hesitate" || choice === "done") {
        setLeft(AUTO_MS);
        setPhase({ k: "reason", key, choice, itemId: card.id });
      } else {
        next();
      }
    },
    [card, busy, touch, next, tallyWeek, beads.length],
  );

  const tag = useCallback(
    async (key: string, choice: DeskChoice, tagKey: string) => {
      const body =
        choice === "hesitate"
          ? { idemKey: key, itemId: card?.id, stayReason: tagKey }
          : { idemKey: key, reasonTags: [tagKey] };
      next();
      try {
        const r = await post("/api/desk/tag", body);
        if (!r.ok && r.status >= 500) throw new Error();
      } catch {
        writeQueue([...readQueue(), { url: "/api/desk/tag", body }]);
        setPending(readQueue().length);
      }
    },
    [next, card],
  );

  // 「この送り手は次回から」（任意）。選ぶと次回から Slack にもデスクにも反映される
  const senderPolicy = useCallback(
    async (itemId: string, key: string, policy: SenderPolicy) => {
      next();
      try {
        const r = await post("/api/desk/sender-policy", { itemId, policy, idemKey: key });
        if (r.ok) flash(`✓ この送り手は次回から「${SENDER_POLICIES[policy]}」`);
        else flash(String(r.json.error || "送り手の設定を保存できませんでした"));
      } catch {
        flash("送り手の設定を保存できませんでした（判断は記録済みです）");
      }
    },
    [next],
  );

  // 理由は任意。5 秒で次へ
  useEffect(() => {
    if (phase.k !== "reason") return;
    const t0 = Date.now();
    const iv = window.setInterval(() => {
      const rest = AUTO_MS - (Date.now() - t0);
      setLeft(Math.max(0, rest));
      if (rest <= 0) {
        window.clearInterval(iv);
        next();
      }
    }, 100);
    return () => window.clearInterval(iv);
  }, [phase, next]);

  const openReply = useCallback(() => {
    if (!card) return;
    touch();
    window.open(`${dash}/mail/${encodeURIComponent(card.id)}`, "_blank", "noopener");
    setPhase({ k: "opened" });
  }, [card, dash, touch]);

  // キーボード: 1〜4・0。理由の画面では 1〜6 でタグ、Enter で飛ばす
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement) return;
      if (phase.k === "reason") {
        const tags = phase.choice === "hesitate" ? STAY_TAGS : MAIL_TAGS;
        const n = Number(e.key);
        if (phase.choice !== "done" && n >= 1 && n <= tags.length) void tag(phase.key, phase.choice, tags[n - 1].k);
        if (phase.choice !== "hesitate" && n >= 7 && n <= 9) {
          void senderPolicy(phase.itemId, phase.key, (["hide", "auto_done", "always"] as const)[n - 7]);
        }
        if (e.key === "Enter" || e.key === "Escape") next();
        return;
      }
      if (phase.k === "opened") {
        if (e.key === "Enter") next();
        return;
      }
      if (e.key === "1") openReply();
      if (e.key === "2") void decide("skip");
      if (e.key === "3") void decide("todo");
      if (e.key === "4") void decide("hesitate");
      if (e.key === "0") void decide("done");
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [phase, decide, tag, next, openReply]);

  const remaining = cards ? Math.max(0, cards.length - idx) : 0;
  const ago = useMemo(() => agoLabel(card?.receivedAt || null), [card]);

  return (
    <div className="desk" onPointerDown={touch}>
      <header className="desk-top">
        <div>
          <div className="eyebrow acc">判断デスク・メール</div>
          <strong className="desk-count">
            <b>{cards ? remaining : "…"}</b> 件
          </strong>
        </div>
        <LogJar week={tallyWeek} session={beads} />
      </header>

      {pending ? <p className="meta">端末に預かっている判断 {pending} 件（つながったら送ります）</p> : null}
      {error ? <p className="meta" style={{ color: "var(--alert)" }}>{error}</p> : null}

      {cards && !card ? (
        <div className="glass desk-empty">
          <div className="eyebrow acc" style={{ color: "var(--positive)" }}>ALL CLEAR</div>
          <p className="desk-empty-title">今出せる判断は終わりです</p>
          <p className="meta">今日 {beads.length} 件を判断しました。迷ったものは「残り」で次の一手を出します。</p>
          <a className="cta" href="/desk?surface=triage&view=left">残りを見る <Icon name="arrow" size={18} /></a>
        </div>
      ) : null}

      {card ? (
        <article className="glass desk-card" key={card.id}>
          <div className="desk-meta">
            <span>{card.who || card.fromEmail}</span>
            {ago ? <span className="mono">{ago}</span> : null}
            {card.postedToSlack ? <span className="pill">Slack</span> : null}
            {card.hesitatedAt ? <span className="pill hes">迷った</span> : null}
          </div>
          <h2 className="desk-subject">{card.subject}</h2>
          <p className="desk-state">{stateLine(card)}</p>
          {card.history.map((h) => (
            <p key={h} className="desk-history">{h}</p>
          ))}
          {card.summary ? <p className="desk-summary">{card.summary}</p> : null}
          {card.appliedRules.length ? (
            <p className="meta">効いているルール: {card.appliedRules.map((r) => <code key={r}>{r} </code>)}</p>
          ) : null}

          {card.thread.length ? (
            <details className="desk-thread" open={card.thread.some((m) => m.mine)}>
              <summary>
                {card.thread.some((m) => m.mine) ? "あなたが送った前のメール" : "前のやりとり"}（{card.thread.length}通）
              </summary>
              {card.thread.map((m, i) => (
                <div key={i} className={m.mine ? "thread-msg mine" : "thread-msg"}>
                  <div className="thread-who">
                    {m.mine ? "あなた" : "相手"} <span className="mono">{m.at}</span>
                  </div>
                  {m.body.split("\n").map((l, j) => (
                    <p key={j}>{l || " "}</p>
                  ))}
                </div>
              ))}
            </details>
          ) : null}

          {card.bodyLines.length ? (
            <details className="desk-body">
              <summary>本文の先頭</summary>
              {card.bodyLines.map((l, i) => (
                <p key={i}>{l || " "}</p>
              ))}
            </details>
          ) : null}

          {card.draftLines.length ? (
            <div className="desk-draft" aria-label="下書き">
              <div className="eyebrow">下書き</div>
              <ol>
                {card.draftLines.map((l, i) => (
                  <li
                    key={i}
                    className={selLine === i ? "on" : ""}
                    onClick={() => setSelLine(i === selLine ? null : i)}
                  >
                    {l || " "}
                  </li>
                ))}
              </ol>
            </div>
          ) : (
            <p className="meta">下書きはまだありません</p>
          )}

          {phase.k === "card" ? (
            <div className="desk-actions">
              <button className="primary" onClick={openReply} disabled={busy}>
                <kbd>1</kbd>返信する
              </button>
              <button onClick={() => void decide("skip")} disabled={busy}>
                <kbd>2</kbd>見送る
              </button>
              <button onClick={() => void decide("todo")} disabled={busy}>
                <kbd>3</kbd>ToDo
              </button>
              <button className="hes" onClick={() => void decide("hesitate")} disabled={busy}>
                <kbd>4</kbd>迷う
              </button>
              <button className="ghost" onClick={() => void decide("done")} disabled={busy}>
                <kbd>0</kbd>回答不要
              </button>
            </div>
          ) : null}

          {phase.k === "opened" ? (
            <div className="desk-reason">
              <p>Jarvis の返信画面を開きました。送ったら記録は自動で残ります。</p>
              <div className="btn-row">
                <button className="primary" onClick={next}>次へ</button>
                <button onClick={() => setPhase({ k: "card" })}>このカードに戻る</button>
              </div>
            </div>
          ) : null}
        </article>
      ) : null}

      {card && phase.k === "card" ? (
        <VoicePanel
          target={{ id: card.id, subject: card.subject, line: selLine }}
          onSaved={() => setBeads((b) => [...b, "note"])}
        />
      ) : null}

      {phase.k === "reason" ? (
        <div className="glass desk-reason desk-sheet">
          {phase.choice !== "done" ? (
            <>
              <p>
                {phase.choice === "hesitate" ? "残っている理由は？（任意）" : "見送った理由は？（任意）"}
                <span className="meta"> {Math.ceil(left / 1000)} 秒で次へ</span>
              </p>
              <div className="tags">
                {(phase.choice === "hesitate" ? STAY_TAGS : MAIL_TAGS).map((t, i) => (
                  <button key={t.k} className="tag" onClick={() => void tag(phase.key, phase.choice, t.k)}>
                    <kbd>{i + 1}</kbd>
                    {t.label}
                  </button>
                ))}
              </div>
            </>
          ) : (
            <p>
              回答不要にしました
              <span className="meta"> {Math.ceil(left / 1000)} 秒で次へ</span>
            </p>
          )}
          {phase.choice !== "hesitate" ? (
            <div className="desk-sender">
              <p className="meta">この送り手は次回から（任意）</p>
              <div className="tags">
                {(Object.keys(SENDER_POLICIES) as SenderPolicy[]).map((p, i) => (
                  <button key={p} className="tag" onClick={() => void senderPolicy(phase.itemId, phase.key, p)}>
                    <kbd>{7 + i}</kbd>
                    {SENDER_POLICIES[p]}
                  </button>
                ))}
              </div>
            </div>
          ) : null}
          <div className="desk-timer" style={{ width: `${(left / AUTO_MS) * 100}%` }} />
          <button className="ghost" onClick={next}>理由なしで次へ</button>
        </div>
      ) : null}

      {toast ? <div className="desk-toast" role="status">{toast}</div> : null}
    </div>
  );
}
