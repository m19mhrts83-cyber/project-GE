"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useSpeech } from "./useSpeech";
import type { DeskCard } from "@/lib/deskCore";

/**
 * 判断デスクの返信欄（2026-11-17）。Jarvis の画面へ飛ばずに、ここで
 *   過去に送った返信を見る → 声（または文字）で指示 → 下書き → 誤字脱字・指示で直す → 送信
 * まで済ませる。下書き作成・送信の中身は Jarvis 側（Slack の返信モーダルと同じ処理）。
 * AI は Mac の定額枠だけ（従量課金なし）。送信は「送信する」→「この宛先で送る」の二段。
 */

type Past = { id: string; subject: string; at: string; to: string; body: string };
type Log = { folder?: string; notice: string; tail: string } | null;

const ACCOUNTS = [
  { k: "estate", label: "estate（既定）" },
  { k: "admin", label: "admin（会社）" },
  { k: "m19m", label: "m19m（個人）" },
] as const;

function uid(): string {
  try {
    return crypto.randomUUID();
  } catch {
    return `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`;
  }
}

function addrOf(raw: string): string {
  const m = String(raw || "").match(/<([^>]+)>/);
  const a = (m ? m[1] : raw).trim().toLowerCase();
  return /^[^\s@<>]+@[^\s@<>]+\.[^\s@<>]+$/.test(a) ? a : "";
}

function normAccount(raw: string): string {
  const a = String(raw || "").trim().toLowerCase();
  if (a === "livingsupport") return "admin";
  return ACCOUNTS.some((x) => x.k === a) ? a : "estate";
}

function ymd(iso: string): string {
  const t = Date.parse(iso || "");
  if (!Number.isFinite(t)) return "";
  const d = new Date(t + 9 * 3600_000);
  return `${d.getUTCFullYear()}/${d.getUTCMonth() + 1}/${d.getUTCDate()}`;
}

type Res = { ok?: boolean; pending?: boolean; text?: string; changes?: string[]; message?: string };

async function call(body: unknown): Promise<Res> {
  try {
    const r = await fetch("/api/desk/reply", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(body),
    });
    return (await r.json()) as Res;
  } catch (e) {
    return { ok: false, message: e instanceof Error ? e.message : "つながりませんでした" };
  }
}

export default function ReplyComposer({
  card,
  dash,
  onSent,
  onBack,
}: {
  card: DeskCard;
  dash: string;
  onSent: (message: string) => void;
  onBack: () => void;
}) {
  const [past, setPast] = useState<Past[] | null>(null);
  const [log, setLog] = useState<Log>(null);
  const [instr, setInstr] = useState("");
  const [viaVoice, setViaVoice] = useState(false);
  const [draft, setDraft] = useState(card.draftText);
  const [to, setTo] = useState(addrOf(card.fromEmail));
  const [account, setAccount] = useState(normAccount(card.account));
  const [busy, setBusy] = useState<"" | "compose" | "proofread" | "revise" | "send">("");
  const [note, setNote] = useState("");
  const [changes, setChanges] = useState<string[]>([]);
  const [confirm, setConfirm] = useState(false);
  const openedAt = useRef(Date.now());
  const assist = useRef({ proofread: 0, revise: 0 });

  const speech = useSpeech((text) => {
    setViaVoice(true);
    setInstr((s) => (s ? `${s}${/[。、！？\s]$/.test(s) ? "" : "。"}${text}` : text));
  });

  useEffect(() => {
    let alive = true;
    fetch(`/api/desk/reply?item=${encodeURIComponent(card.id)}`, { cache: "no-store" })
      .then((r) => r.json())
      .then((j) => {
        if (!alive) return;
        setPast(Array.isArray(j?.past) ? j.past : []);
        setLog(j?.log && typeof j.log.tail === "string" ? j.log : null);
      })
      .catch(() => alive && setPast([]));
    return () => {
      alive = false;
    };
  }, [card.id]);

  /** 下書き系。Mac の定額 AI が作成中なら、少し待って同じ依頼をもう一度（同じ依頼は使い回される） */
  const run = useCallback(
    async (op: "compose" | "proofread" | "revise") => {
      if (busy) return;
      if (speech.listening) speech.stop();
      if (op === "revise" && !instr.trim()) {
        setNote("直し方をひとこと話すか書いてください（例: もう少し短く、日程は来週で）");
        return;
      }
      setBusy(op);
      setChanges([]);
      setNote(op === "compose" ? "下書きを作っています（Mac の定額AI・1分ほど）…" : op === "proofread" ? "誤字脱字を見ています…" : "指示どおり直しています…");
      const key = `lw-reply-${op}-${uid()}`;
      const body = {
        itemId: card.id,
        op,
        draft,
        instruction: op === "proofread" ? "" : instr,
        subject: card.subject,
        input: viaVoice ? "voice" : "text",
        idemKey: key,
      };
      let r: Res = {};
      for (let i = 0; i < 4; i++) {
        r = await call(body);
        if (!r.pending) break;
        setNote(`Mac の定額AIで作成中です…（${i + 1}回目の確認）`);
        await new Promise((ok) => setTimeout(ok, 5000));
      }
      setBusy("");
      if (r.ok && r.text) {
        setDraft(r.text);
        setChanges(r.changes || []);
        if (op !== "compose") assist.current[op] += 1;
        if (op !== "proofread") {
          setInstr("");
          setViaVoice(false);
        }
        setNote(
          op === "compose"
            ? `✍️ ${r.message || "下書きを作りました"}。読んで直してから送信してください`
            : op === "proofread"
              ? r.changes?.length
                ? "✅ 誤字脱字を直しました（下に直した所）"
                : "✅ 誤字脱字は見つかりませんでした"
              : "✅ 指示どおり直しました",
        );
      } else {
        setNote(`❌ ${r.message || "作れませんでした"}（本文はそのままです）`);
      }
    },
    [busy, speech, instr, card.id, card.subject, draft, viaVoice],
  );

  const send = useCallback(async () => {
    if (busy) return;
    if (speech.listening) speech.stop();
    setBusy("send");
    setNote("送信しています…");
    const r = await call({
      itemId: card.id,
      op: "send",
      draft,
      to,
      account,
      openedAt: openedAt.current,
      assist: assist.current,
    });
    setBusy("");
    setConfirm(false);
    if (r.ok) onSent(r.message || "送信しました");
    else setNote(`❌ ${r.message || "送れませんでした"}（本文はそのままです）`);
  }, [busy, speech, card.id, draft, to, account, onSent]);

  const hasDraft = Boolean(draft.trim());

  return (
    <section className="reply" aria-label="返信">
      <div className="reply-head">
        <span className="eyebrow acc">返信</span>
        <a className="meta" href={`${dash}/mail/${encodeURIComponent(card.id)}`} target="_blank" rel="noopener noreferrer">
          添付・HTML は Jarvis で
        </a>
      </div>

      <details className="reply-past" open={Boolean(past && past.length)}>
        <summary>
          この相手に送った過去の返信{past ? `（${past.length}通）` : "（読み込み中）"}
        </summary>
        {past && !past.length ? <p className="meta">このアプリから送った記録はまだありません。下の「前のやりとり」も見てください。</p> : null}
        {(past || []).map((p, i) => (
          <details key={p.id} className="reply-past-one" open={i === 0}>
            <summary>
              <span className="mono">{ymd(p.at)}</span> {p.subject}
            </summary>
            <pre className="reply-pre">{p.body}</pre>
          </details>
        ))}
      </details>

      {log ? (
        <details className="reply-past">
          <summary>やり取りログ（md）の末尾</summary>
          <p className="meta">{log.notice}。下書きを作るときはこれも読ませます。</p>
          <pre className="reply-pre">{log.tail}</pre>
        </details>
      ) : null}

      <div className="reply-instr">
        <div className="reply-row">
          <label htmlFor="reply-instr" className="eyebrow">
            どう返すか（声でも文字でも）
          </label>
          {speech.supported ? (
            <button
              type="button"
              className={`mic${speech.listening ? " on" : ""}`}
              onClick={() => (speech.listening ? speech.stop() : speech.start())}
              aria-pressed={speech.listening}
            >
              <span className="wave" aria-hidden="true">
                <i />
                <i />
                <i />
              </span>
              {speech.listening ? "止める" : "話す"}
            </button>
          ) : null}
        </div>
        <textarea
          id="reply-instr"
          rows={3}
          value={instr + (speech.listening && speech.interim ? speech.interim : "")}
          onChange={(e) => {
            setInstr(e.target.value);
          }}
          readOnly={speech.listening}
          placeholder="例: 了解です、来週火曜の午後で調整したいと返して。前回お願いした見積もりのお礼も一言"
        />
        {speech.error ? <p className="meta" style={{ color: "var(--alert)" }}>{speech.error}</p> : null}
        <div className="btn-row">
          <button className="primary" onClick={() => void run("compose")} disabled={Boolean(busy)}>
            {busy === "compose" ? "作成中…" : hasDraft ? "この指示で作り直す" : "この指示で下書きを作る"}
          </button>
          {hasDraft ? (
            <button onClick={() => void run("revise")} disabled={Boolean(busy) || !instr.trim()}>
              {busy === "revise" ? "直し中…" : "この指示で今の下書きを直す"}
            </button>
          ) : null}
        </div>
      </div>

      <div className="reply-draft">
        <div className="reply-row">
          <label htmlFor="reply-draft" className="eyebrow">
            下書き（そのまま直せます）
          </label>
          <button className="ghost" onClick={() => void run("proofread")} disabled={Boolean(busy) || !hasDraft}>
            {busy === "proofread" ? "点検中…" : "誤字脱字チェック"}
          </button>
        </div>
        <textarea id="reply-draft" rows={12} value={draft} onChange={(e) => setDraft(e.target.value)} placeholder="下書きはまだありません。上で指示して作るか、ここに直接書いてください" />
        {changes.length ? (
          <ul className="reply-changes">
            {changes.map((c, i) => (
              <li key={i}>{c}</li>
            ))}
          </ul>
        ) : null}
      </div>

      <details className="reply-to">
        <summary>
          宛先 {to || "（Jarvis が推定）"}・送信元 {account}
        </summary>
        <label>
          宛先
          <input type="email" value={to} onChange={(e) => setTo(e.target.value.trim())} placeholder="空なら本文から推定します" />
        </label>
        <label>
          送信元
          <select value={account} onChange={(e) => setAccount(e.target.value)}>
            {ACCOUNTS.map((a) => (
              <option key={a.k} value={a.k}>
                {a.label}
              </option>
            ))}
          </select>
        </label>
      </details>

      {note ? <p className="meta reply-note" role="status">{note}</p> : null}

      {confirm ? (
        <div className="reply-confirm">
          <p>
            <b>{to || "（推定した宛先）"}</b> へ {account} から送ります。よろしいですか？
          </p>
          <div className="btn-row">
            <button className="primary" onClick={() => void send()} disabled={Boolean(busy)}>
              {busy === "send" ? "送信中…" : "この宛先で送る"}
            </button>
            <button onClick={() => setConfirm(false)} disabled={busy === "send"}>
              やめる
            </button>
          </div>
        </div>
      ) : (
        <div className="btn-row">
          <button className="primary" onClick={() => setConfirm(true)} disabled={Boolean(busy) || !hasDraft}>
            送信する
          </button>
          <button onClick={onBack} disabled={busy === "send"}>
            判断に戻る
          </button>
        </div>
      )}
    </section>
  );
}
