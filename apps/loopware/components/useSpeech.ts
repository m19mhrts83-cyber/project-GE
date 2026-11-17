"use client";

import { useCallback, useEffect, useRef, useState } from "react";

type Rec = {
  lang: string;
  continuous: boolean;
  interimResults: boolean;
  onresult: ((e: any) => void) | null; // eslint-disable-line @typescript-eslint/no-explicit-any
  onerror: ((e: any) => void) | null; // eslint-disable-line @typescript-eslint/no-explicit-any
  onend: (() => void) | null;
  start: () => void;
  stop: () => void;
  abort?: () => void;
};

/** 止めた後、言い終わりの確定文だけを受け取る猶予 */
export const STOP_GRACE_MS = 700;

/**
 * 認識を確実に止める（2026-11-17）。
 * iPhone の Safari／Slack から開いた画面では continuous の stop() が効かず、
 * 「止める」を押しても字幕が増え続けることがあった。
 * stop() で言い終わりを確定させ、少し待って abort()。その後はハンドラを外して何も受け取らない。
 */
export function hardStop(rec: Rec | null | undefined, graceMs = 0) {
  if (!rec) return;
  rec.onend = null;
  rec.onerror = null;
  try {
    rec.stop();
  } catch {
    /* ignore */
  }
  const kill = () => {
    rec.onresult = null;
    try {
      rec.abort?.();
    } catch {
      /* ignore */
    }
  };
  if (graceMs > 0) window.setTimeout(kill, graceMs);
  else kill();
}

/** ブラウザの音声認識（Web Speech API）。話している間の字幕（interim）と、区切りごとの確定文を返す。 */
export function useSpeech(onFinal: (text: string) => void) {
  const [supported, setSupported] = useState(true);
  const [listening, setListening] = useState(false);
  const [interim, setInterim] = useState("");
  const [error, setError] = useState("");
  const recRef = useRef<Rec | null>(null);
  const wantRef = useRef(false);
  const finalRef = useRef(onFinal);
  finalRef.current = onFinal;

  useEffect(() => {
    const w = window as unknown as Record<string, unknown>;
    if (!w.SpeechRecognition && !w.webkitSpeechRecognition) setSupported(false);
    return () => {
      // 画面を離れたら必ず止める（マイクを掴んだままにしない）
      wantRef.current = false;
      hardStop(recRef.current);
      recRef.current = null;
    };
  }, []);

  const start = useCallback(() => {
    const w = window as unknown as Record<string, new () => Rec>;
    const Ctor = w.SpeechRecognition || w.webkitSpeechRecognition;
    if (!Ctor) {
      setSupported(false);
      return;
    }
    // 前の認識が残っていたら止めてから（二重に動くと片方しか止まらない）
    hardStop(recRef.current);
    setError("");
    const rec = new Ctor();
    rec.lang = "ja-JP";
    rec.continuous = true;
    rec.interimResults = true;
    rec.onresult = (e) => {
      // 止めた後は確定文だけ（言い終わり）を受け取り、字幕は出さない
      const stopped = recRef.current !== rec || !wantRef.current;
      let live = "";
      for (let i = e.resultIndex; i < e.results.length; i++) {
        const r = e.results[i];
        const txt = (r[0]?.transcript || "").trim();
        if (r.isFinal) {
          if (txt) finalRef.current(txt);
        } else {
          live += txt;
        }
      }
      if (!stopped) setInterim(live);
    };
    rec.onerror = (e) => {
      if (recRef.current !== rec) return;
      const code = String(e?.error || "");
      if (code === "no-speech" || code === "aborted") return;
      if (code === "not-allowed" || code === "service-not-allowed") {
        setError("マイクの許可が必要です（ブラウザの設定で許可してください）");
      } else {
        setError(`音声認識でエラー：${code}`);
      }
      wantRef.current = false;
      setListening(false);
    };
    rec.onend = () => {
      if (recRef.current !== rec) return;
      setInterim("");
      // 無音で自動終了することがあるので、止めていなければ続ける
      if (wantRef.current) {
        try {
          rec.start();
          return;
        } catch {
          /* fallthrough */
        }
      }
      setListening(false);
    };
    recRef.current = rec;
    wantRef.current = true;
    try {
      rec.start();
      setListening(true);
    } catch {
      wantRef.current = false;
      setError("音声認識を開始できませんでした");
    }
  }, []);

  const stop = useCallback(() => {
    wantRef.current = false;
    const rec = recRef.current;
    recRef.current = null;
    hardStop(rec, STOP_GRACE_MS);
    setListening(false);
    setInterim("");
  }, []);

  return { supported, listening, interim, error, start, stop };
}
