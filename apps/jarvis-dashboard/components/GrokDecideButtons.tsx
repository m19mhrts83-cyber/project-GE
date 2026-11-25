"use client";

import { useRouter } from "next/navigation";
import { useState, useTransition } from "react";
import { decideGrokCandidate } from "@/app/actions/grokCandidates";

export default function GrokDecideButtons({ name }: { name: string }) {
  const router = useRouter();
  const [pending, start] = useTransition();
  const [msg, setMsg] = useState<string | null>(null);

  const go = (decision: "adopt" | "skip") =>
    start(async () => {
      const r = await decideGrokCandidate(name, decision);
      setMsg(r.message);
      if (r.ok) router.refresh();
    });

  return (
    <span style={{ display: "inline-flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
      <button type="button" className="btn primary" disabled={pending} onClick={() => go("adopt")}>
        {pending ? "処理中…" : "採用"}
      </button>
      <button type="button" className="btn" disabled={pending} onClick={() => go("skip")}>
        見送り
      </button>
      {msg ? <span className="meta">{msg}</span> : null}
    </span>
  );
}
