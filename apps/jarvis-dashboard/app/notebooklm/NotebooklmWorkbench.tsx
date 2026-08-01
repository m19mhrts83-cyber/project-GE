"use client";

import { useEffect, useState } from "react";

const HELPER_URL = "http://127.0.0.1:8766/notebooklm-workbench";
const NOTEBOOKLM_URL = "https://notebooklm.google.com/";
const DRIVE_FALLBACK =
  process.env.NEXT_PUBLIC_NOTEBOOKLM_DRIVE_FOLDER_URL ||
  "https://drive.google.com/drive/search?q=200_NoteBookLM";
const ZEROICHI_HINT = "00_共通(デザイントーン）";

const SUBFOLDERS: { name: string; note: string }[] = [
  { name: "00_共通(デザイントーン）", note: "ゼロイチ／いけとも共通スタイル" },
  { name: "01_セサミ使用方法説明", note: "" },
  { name: "02_Grandole周辺MAP試作", note: "" },
  { name: "03_周辺MAP作成手順説明", note: "" },
  {
    name: "04_神・大家さん俱楽部Q&Aチャットボットアプリ",
    note: "",
  },
  {
    name: "05_Jarvisダッシュボード_設計と引き継ぎ",
    note: "設計メモ・NotebookLM説明用",
  },
  { name: "99_PlusAI検証_20260727", note: "検証用" },
  { name: "★アウトプット", note: "生成スライド等" },
];

type HelperState = "idle" | "trying" | "ok" | "fallback";

export default function NotebooklmWorkbench() {
  const [helper, setHelper] = useState<HelperState>("idle");

  useEffect(() => {
    let cancelled = false;
    const run = async () => {
      setHelper("trying");
      const ctrl = new AbortController();
      const t = setTimeout(() => ctrl.abort(), 1500);
      try {
        const res = await fetch(HELPER_URL, {
          method: "GET",
          signal: ctrl.signal,
          mode: "cors",
        });
        clearTimeout(t);
        if (cancelled) return;
        setHelper(res.ok ? "ok" : "fallback");
      } catch {
        clearTimeout(t);
        if (!cancelled) setHelper("fallback");
      }
    };
    void run();
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <>
      <h1>NotebookLM 作業セット</h1>
      <p className="sub">
        ソース正本は admin Drive の <strong>200_NoteBookLM</strong>。Mac では
        Finder の MD を NotebookLM のソースへドラッグ＆ドロップします。
      </p>

      <p className="meta" style={{ marginBottom: 16 }}>
        {helper === "trying" && "Mac ヘルパーに接続中…"}
        {helper === "ok" &&
          "✅ Finder（200_NoteBookLM）と NotebookLM を開きました"}
        {helper === "fallback" &&
          "ヘルパー未起動（iPhone／別PC可）。下のリンクから続行してください"}
        {helper === "idle" && null}
      </p>

      <div style={{ display: "flex", flexWrap: "wrap", gap: 10, marginBottom: 24 }}>
        <a
          className="btn"
          href={NOTEBOOKLM_URL}
          target="_blank"
          rel="noopener noreferrer"
        >
          NotebookLM を開く
        </a>
        <a
          className="btn"
          href={DRIVE_FALLBACK}
          target="_blank"
          rel="noopener noreferrer"
        >
          Drive（200_NoteBookLM）
        </a>
        <button
          type="button"
          className="btn"
          onClick={() => {
            setHelper("trying");
            void fetch(HELPER_URL, { mode: "cors" })
              .then((r) => setHelper(r.ok ? "ok" : "fallback"))
              .catch(() => setHelper("fallback"));
          }}
        >
          Mac: Finder＋NLM を再オープン
        </button>
      </div>

      <h2>手順</h2>
      <ol style={{ lineHeight: 1.7, marginBottom: 24, paddingLeft: 22 }}>
        <li>Finder でノート用フォルダ（下表）を開く</li>
        <li>Chrome の NotebookLM でノートを開く（または新規作成）</li>
        <li>MD／PDF をソースパネルへ D&amp;D</li>
        <li>
          スタイルは必要なら <code>{ZEROICHI_HINT}</code> を同じノートに追加
        </li>
      </ol>

      <h2>200_NoteBookLM サブフォルダ</h2>
      <ul style={{ listStyle: "none", padding: 0, margin: 0 }}>
        {SUBFOLDERS.map((f) => (
          <li
            key={f.name}
            className="card"
            style={{ marginBottom: 8, padding: "10px 14px" }}
          >
            <strong>{f.name}</strong>
            {f.note ? (
              <span className="meta" style={{ marginLeft: 8 }}>
                {f.note}
              </span>
            ) : null}
          </li>
        ))}
      </ul>

      <p className="meta" style={{ marginTop: 24 }}>
        アカウント: admin@livingsupport-matsu.co.jp ／ ヘルパー:{" "}
        <code>127.0.0.1:8766</code>
      </p>
    </>
  );
}
