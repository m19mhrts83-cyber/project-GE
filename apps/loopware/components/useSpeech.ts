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
};

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
      wantRef.current = false;
      try {
        recRef.current?.stop();
      } catch {
        /* ignore */
      }
    };
  }, []);

  const start = useCallback(() => {
    const w = window as unknown as Record<string, new () => Rec>;
    const Ctor = w.SpeechRecognition || w.webkitSpeechRecognition;
    if (!Ctor) {
      setSupported(false);
      return;
    }
    setError("");
    const rec = new Ctor();
    rec.lang = "ja-JP";
    rec.continuous = true;
    rec.interimResults = true;
    rec.onresult = (e) => {
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
      setInterim(live);
    };
    rec.onerror = (e) => {
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
      setError("音声認識を開始できませんでした");
    }
  }, []);

  const stop = useCallback(() => {
    wantRef.current = false;
    try {
      recRef.current?.stop();
    } catch {
      /* ignore */
    }
    setListening(false);
    setInterim("");
  }, []);

  return { supported, listening, interim, error, start, stop };
}
