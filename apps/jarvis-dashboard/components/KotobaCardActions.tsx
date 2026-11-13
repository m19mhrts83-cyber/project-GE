"use client";

import { useRouter } from "next/navigation";
import { useState, useTransition } from "react";
import { addShelfNote, judgeKotoba } from "@/app/actions/kotoba";
import { useToast } from "@/components/Toast";
import { STATUS_LABEL, type KotobaVerdict } from "@/lib/kotoba";

const TOAST: Record<KotobaVerdict, string> = {
  keep: "棚に残しました",
  drop: "いらないにしました（「すべて」で見返せます）",
  hesitate: "迷うにしました（NGには数えません）",
  comment: "ひとことを残しました",
};

function newKey(id: string): string {
  const r =
    typeof crypto !== "undefined" && "randomUUID" in crypto
      ? crypto.randomUUID()
      : `${Date.now()}-${Math.random().toString(36).slice(2)}`;
  return `kotoba:${id}:${r}`;
}

export function KotobaCardActions({ cardId, status }: { cardId: string; status: string }) {
  const router = useRouter();
  const toast = useToast();
  const [pending, start] = useTransition();
  const [note, setNote] = useState("");
  const [open, setOpen] = useState(false);

  function send(v: KotobaVerdict) {
    start(async () => {
      const r = await judgeKotoba(cardId, v, newKey(cardId), note);
      if (!r.ok) {
        toast.push(r.error, "err");
        return;
      }
      toast.push(note.trim() && v !== "comment" ? `${TOAST[v]}（ひとことも残しました）` : TOAST[v]);
      setNote("");
      setOpen(false);
      router.refresh();
    });
  }

  const btn = (v: KotobaVerdict, label: string, on: string) => (
    <button
      className={status === on ? "btn primary" : "btn ghost"}
      aria-pressed={status === on}
      disabled={pending}
      onClick={() => send(v)}
    >
      {label}
    </button>
  );

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 6, marginTop: 8 }}>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 6, alignItems: "center" }}>
        {btn("keep", "残す", "kept")}
        {btn("drop", "いらない", "dropped")}
        {btn("hesitate", "迷う", "hesitated")}
        <button className="btn ghost" disabled={pending} onClick={() => setOpen((o) => !o)}>
          ひとこと
        </button>
        <span className="sub" style={{ marginLeft: 4 }}>
          今: {STATUS_LABEL[status] || status}
        </span>
      </div>
      {open ? (
        <>
          <textarea
            value={note}
            onChange={(e) => setNote(e.target.value)}
            rows={2}
            maxLength={2000}
            placeholder="このことばで思ったこと（任意）。例: 次の物件検討の前に読む"
            style={{ width: "100%", padding: 8, borderRadius: 8, font: "inherit" }}
          />
          <div>
            <button className="btn" disabled={pending || !note.trim()} onClick={() => send("comment")}>
              ひとことだけ残す
            </button>
          </div>
        </>
      ) : null}
    </div>
  );
}

export function KotobaShelfNote({ shelf }: { shelf: string }) {
  const router = useRouter();
  const toast = useToast();
  const [pending, start] = useTransition();
  const [body, setBody] = useState("");

  function save() {
    start(async () => {
      const r = await addShelfNote(shelf, body);
      if (!r.ok) {
        toast.push(r.error, "err");
        return;
      }
      toast.push("この棚のまとめを残しました");
      setBody("");
      router.refresh();
    });
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 6, marginTop: 8 }}>
      <textarea
        value={body}
        onChange={(e) => setBody(e.target.value)}
        rows={2}
        maxLength={4000}
        placeholder="この棚を見て思ったこと・自分の言葉でのまとめ"
        style={{ width: "100%", padding: 8, borderRadius: 8, font: "inherit" }}
      />
      <div>
        <button className="btn" disabled={pending || !body.trim()} onClick={save}>
          まとめを残す
        </button>
      </div>
    </div>
  );
}
