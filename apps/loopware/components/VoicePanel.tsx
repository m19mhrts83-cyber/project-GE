"use client";

import { useCallback, useEffect, useRef, useState } from "react";

/**
 * 声のひとこと。話した言葉がその場で文字で流れ、映している物・選んでいる行が変わったら
 * 「▶ 件名／n行目」の区切りが入る。「ここ／これ」は印を付けて、後で何を指したか確かめる。
 * 文字起こしは端末（ブラウザ）の音声認識だけを使う（費用ゼロ）。使えない端末では文字で入れる。
 * 記録: surface=triage, action=comment, payload.voice.segments（対象・行・秒・文字）、timing.voice_sec
 */

export type VoiceTarget = { id: string; subject: string; line: number | null };

type Seg = { cardId: string; target: string; line: number | null; t_start: number; t_end?: number; text: string };

type Rec = {
  lang: string;
  continuous: boolean;
  interimResults: boolean;
  start: () => void;
  stop: () => void;
  onresult: ((e: { resultIndex: number; results: ArrayLike<{ isFinal: boolean; 0: { transcript: string } }> }) => void) | null;
  onend: (() => void) | null;
  onerror: ((e: { error?: string }) => void) | null;
};

const VAGUE = /(ここ|これ|それ|あれ|この辺)/;
const VAGUE_ONE = /^(ここ|これ|それ|あれ|この辺)$/;

function label(t: { target: string; line: number | null }): string {
  return `▶ ${t.target}${t.line !== null ? `／${t.line + 1}行目` : ""}`;
}

function uid(): string {
  try {
    return crypto.randomUUID();
  } catch {
    return `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`;
  }
}

function Marked({ text }: { text: string }) {
  const parts = text.split(VAGUE);
  return (
    <>
      {parts.map((p, i) => (VAGUE_ONE.test(p) ? <mark key={i} title="何を指しているか後で確認">{p}</mark> : <span key={i}>{p}</span>))}
    </>
  );
}

export default function VoicePanel({ target, onSaved }: { target: VoiceTarget | null; onSaved?: () => void }) {
  const [supported, setSupported] = useState<boolean | null>(null);
  const [on, setOn] = useState(false);
  const [segs, setSegs] = useState<Seg[]>([]);
  const [interim, setInterim] = useState("");
  const [typed, setTyped] = useState("");
  const [msg, setMsg] = useState("");
  const rec = useRef<Rec | null>(null);
  const t0 = useRef(0);
  const segsRef = useRef<Seg[]>([]);
  segsRef.current = segs;

  useEffect(() => {
    const w = window as unknown as { SpeechRecognition?: new () => Rec; webkitSpeechRecognition?: new () => Rec };
    setSupported(Boolean(w.SpeechRecognition || w.webkitSpeechRecognition));
  }, []);

  const sec = () => Math.round((Date.now() - t0.current) / 100) / 10;

  // 映している物・行が変わったら区切る
  useEffect(() => {
    if (!on || !target) return;
    setSegs((s) => {
      const last = s[s.length - 1];
      if (last && last.cardId === target.id && last.line === target.line) return s;
      const closed = last && last.t_end === undefined ? [...s.slice(0, -1), { ...last, t_end: sec() }] : s;
      return [...closed, { cardId: target.id, target: target.subject, line: target.line, t_start: sec(), text: "" }];
    });
  }, [on, target?.id, target?.line]); // eslint-disable-line react-hooks/exhaustive-deps

  const start = useCallback(() => {
    const w = window as unknown as { SpeechRecognition?: new () => Rec; webkitSpeechRecognition?: new () => Rec };
    const C = w.SpeechRecognition || w.webkitSpeechRecognition;
    if (!C || !target) return;
    const r = new C();
    r.lang = "ja-JP";
    r.continuous = true;
    r.interimResults = true;
    r.onresult = (e) => {
      let inter = "";
      for (let i = e.resultIndex; i < e.results.length; i++) {
        const res = e.results[i];
        const text = res[0].transcript;
        if (res.isFinal) {
          setSegs((s) => {
            if (!s.length) return s;
            const last = s[s.length - 1];
            return [...s.slice(0, -1), { ...last, text: (last.text + text).slice(0, 1000) }];
          });
        } else {
          inter += text;
        }
      }
      setInterim(inter);
    };
    r.onerror = (e) => setMsg(e.error === "not-allowed" ? "マイクの使用が許可されていません" : "音声認識が止まりました");
    r.onend = () => {
      setOn(false);
      setInterim("");
    };
    t0.current = Date.now();
    setSegs([{ cardId: target.id, target: target.subject, line: target.line, t_start: 0, text: "" }]);
    setMsg("");
    rec.current = r;
    r.start();
    setOn(true);
  }, [target]);

  const stop = useCallback(() => {
    rec.current?.stop();
    setOn(false);
    setSegs((s) => (s.length && s[s.length - 1].t_end === undefined ? [...s.slice(0, -1), { ...s[s.length - 1], t_end: sec() }] : s));
  }, []);

  const save = useCallback(
    async (list: Seg[], voiceSec: number | null) => {
      const filled = list.filter((s) => s.text.trim());
      if (!filled.length) return;
      // 案件ごとに1行（どの件への声かで数えるため）
      const byCard = new Map<string, Seg[]>();
      for (const s of filled) byCard.set(s.cardId, [...(byCard.get(s.cardId) || []), s]);
      const decisions = Array.from(byCard.entries()).map(([cardId, ss]) => ({
        surface: "triage",
        action: "comment",
        source: "loopware",
        targetType: "triage_item",
        targetId: cardId,
        subject: ss[0].target,
        note: ss.map((s) => s.text).join(" ").slice(0, 2000),
        idemKey: `lw-voice-${uid()}`,
        voice: { segments: ss.map((s) => ({ target: s.target, line: s.line, t_start: s.t_start, t_end: s.t_end, text: s.text })) },
        timing: voiceSec !== null ? { voice_sec: voiceSec } : undefined,
        payload: { input: voiceSec !== null ? "voice" : "text" },
      }));
      try {
        const r = await fetch("/api/log", {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({ decisions }),
        });
        const j = await r.json();
        if (!j.ok) throw new Error();
        setSegs([]);
        setTyped("");
        setMsg(`✓ ひとことを記録しました（${decisions.length} 件分）`);
        onSaved?.();
      } catch {
        setMsg("記録できませんでした。もう一度押してください");
      }
    },
    [onSaved],
  );

  const voiceSec = segs.length ? (segs[segs.length - 1].t_end ?? sec()) : 0;

  return (
    <section className="glass voice" aria-label="声のひとこと">
      <div className="voice-head">
        <span className="eyebrow">ひとこと</span>
        {supported ? (
          <button className={`mic${on ? " on" : ""}`} onClick={on ? stop : start} disabled={!target} aria-pressed={on}>
            <span className="wave" aria-hidden="true">
              <i />
              <i />
              <i />
            </span>
            {on ? "止める" : "話す"}
          </button>
        ) : null}
      </div>
      {supported === false ? <p className="meta">この端末では音声認識が使えません。キーボードの音声入力でも区切りは付きます。</p> : null}

      {segs.length ? (
        <div className="voice-log" aria-live="polite">
          {segs.map((s, i) => (
            <div key={i} className="voice-seg">
              <div className="voice-mark">
                {label(s)} <span className="mono">{s.t_start.toFixed(1)}s</span>
              </div>
              <p>
                <Marked text={s.text} />
                {i === segs.length - 1 && interim ? <span className="interim">{interim}</span> : null}
              </p>
            </div>
          ))}
        </div>
      ) : null}

      {!on && segs.some((s) => s.text.trim()) ? (
        <div className="btn-row">
          <button className="primary" onClick={() => void save(segs, voiceSec)}>記録する</button>
          <button onClick={() => setSegs([])}>消す</button>
        </div>
      ) : null}

      {!on ? (
        <form
          className="voice-type"
          onSubmit={(e) => {
            e.preventDefault();
            if (!typed.trim() || !target) return;
            void save([{ cardId: target.id, target: target.subject, line: target.line, t_start: 0, text: typed.trim() }], null);
          }}
        >
          <input
            type="text"
            value={typed}
            placeholder={target ? `${label({ target: target.subject, line: target.line })} への一言` : "一言"}
            onChange={(e) => setTyped(e.target.value)}
          />
          <button type="submit" disabled={!typed.trim()}>残す</button>
        </form>
      ) : null}
      {msg ? <p className="meta">{msg}</p> : null}
    </section>
  );
}
