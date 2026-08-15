"use client";

import { useRouter } from "next/navigation";
import { useState, useTransition } from "react";
import {
  ackOtherMailDigestSkim,
  askOtherMailDigestGenre,
} from "@/app/actions/triage";
import type { OtherMailGenre } from "@/lib/otherMailDigest";
import { useToast } from "@/components/Toast";

type Props = {
  genres: OtherMailGenre[];
  path?: string;
};

export default function OtherMailDigestGenres({
  genres,
  path = "/",
}: Props) {
  const router = useRouter();
  const toast = useToast();
  const [pending, start] = useTransition();
  const [askOpen, setAskOpen] = useState<string | null>(null);
  const [askText, setAskText] = useState("");
  const [answer, setAnswer] = useState<Record<string, string>>({});

  if (!genres.length) return null;

  function ackGenre(g: OtherMailGenre) {
    const skimHint =
      g.item_ids.length > 0
        ? `${g.label}（${g.item_ids.length} 件）を確認済みにします。要確認（個別対応）は残ります。`
        : "対象がありません";
    if (!window.confirm(skimHint)) return;
    start(async () => {
      const r = await ackOtherMailDigestSkim(path, g.item_ids, g.id);
      if (!r.ok) {
        toast.push(r.error, "err");
        return;
      }
      toast.push(r.message || "確認しました");
      router.refresh();
    });
  }

  function askGenre(g: OtherMailGenre) {
    const q = askText.trim() || g.ask_hint || `${g.label}で気になる点は？`;
    start(async () => {
      const r = await askOtherMailDigestGenre({
        genreLabel: g.label,
        bullets: g.bullets || [],
        question: q,
        engine: "cursor",
      });
      if (!r.ok) {
        toast.push(r.error, "err");
        return;
      }
      setAnswer((prev) => ({ ...prev, [g.id]: r.answer || "" }));
      if (r.message) toast.push(r.message);
    });
  }

  return (
    <div className="other-mail-genres">
      {genres.map((g) => (
        <article key={g.id} className="other-mail-genre">
          <header className="other-mail-genre-head">
            <h3>{g.label}</h3>
            <span className="meta">{g.item_ids.length} 件</span>
          </header>
          {(g.bullets || []).length > 0 ? (
            <ul className="other-mail-genre-bullets">
              {g.bullets.slice(0, 5).map((b, i) => (
                <li key={i}>{b}</li>
              ))}
            </ul>
          ) : null}
          <div className="other-mail-genre-actions">
            <button
              type="button"
              className="btn"
              disabled={pending || !g.item_ids.length}
              onClick={() => ackGenre(g)}
            >
              確認したよ
            </button>
            <button
              type="button"
              className="btn"
              disabled={pending}
              onClick={() => {
                setAskOpen(askOpen === g.id ? null : g.id);
                setAskText(g.ask_hint || "");
              }}
            >
              聞く
            </button>
          </div>
          {askOpen === g.id ? (
            <div className="other-mail-genre-ask">
              <textarea
                rows={3}
                value={askText}
                onChange={(e) => setAskText(e.target.value)}
                placeholder="このジャンルについて聞きたいこと"
                disabled={pending}
              />
              <button
                type="button"
                className="btn"
                disabled={pending}
                onClick={() => askGenre(g)}
              >
                {pending ? "送信中…" : "送って聞く"}
              </button>
              {answer[g.id] ? (
                <p className="other-mail-genre-answer">{answer[g.id]}</p>
              ) : null}
            </div>
          ) : null}
        </article>
      ))}
    </div>
  );
}
