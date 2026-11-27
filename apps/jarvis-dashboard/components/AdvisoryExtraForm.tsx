"use client";

import { useRouter } from "next/navigation";
import { useState, useTransition } from "react";
import { saveAdvisoryExtra } from "@/app/actions/advisoryFee";

export default function AdvisoryExtraForm({ months }: { months: { ym: string; label: string; current: number | null }[] }) {
  const router = useRouter();
  const [ym, setYm] = useState(months[months.length - 1]?.ym || "");
  const [yen, setYen] = useState("");
  const [msg, setMsg] = useState<string | null>(null);
  const [pending, start] = useTransition();
  return (
    <section className="card" style={{ padding: 12 }}>
      <p className="billing-summary-kicker">追加費用を入れる（改修対応など・月ごと）</p>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "center" }}>
        <select
          value={ym}
          onChange={(e) => {
            setYm(e.target.value);
            setYen("");
            setMsg(null);
          }}
          style={{ fontSize: 16, padding: 8 }}
          aria-label="月"
        >
          {months.map((m) => (
            <option key={m.ym} value={m.ym}>
              {m.label}
            </option>
          ))}
        </select>
        <input
          inputMode="numeric"
          value={yen}
          onChange={(e) => setYen(e.target.value)}
          placeholder={months.find((m) => m.ym === ym)?.current != null ? "いまの値あり・空で消す" : "円"}
          style={{ fontSize: 16, padding: 8, width: 140 }}
          aria-label="追加費用（円）"
        />
        <button
          type="button"
          className="btn"
          disabled={pending}
          onClick={() => {
            setMsg(null);
            start(async () => {
              const r = await saveAdvisoryExtra(ym, yen);
              if (!r.ok) {
                setMsg(r.error || "保存に失敗しました");
                return;
              }
              setMsg("保存しました");
              router.refresh();
            });
          }}
        >
          {pending ? "保存中…" : "保存"}
        </button>
      </div>
      {msg ? <p className="meta" style={{ margin: "6px 0 0" }}>{msg}</p> : null}
      <p className="meta" style={{ margin: "6px 0 0" }}>外には何も送りません。ボットは scripts/jarvis_advisory_fee.py --extra でも入れられます。</p>
    </section>
  );
}
