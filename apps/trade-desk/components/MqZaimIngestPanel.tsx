"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { fmtMqMan, yenToMan } from "@/lib/mqUnits";

type Unmapped = {
  category: string;
  subcategory: string;
  entity: string;
  count: number;
  amount: number;
};

export default function MqZaimIngestPanel({
  defaultYear,
}: {
  defaultYear: string;
}) {
  const router = useRouter();
  const [year, setYear] = useState(defaultYear);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [unmapped, setUnmapped] = useState<Unmapped[]>([]);
  const [loanWarn, setLoanWarn] = useState(false);

  async function run(force: boolean) {
    setBusy(true);
    setMsg(null);
    try {
      const res = await fetch("/api/mq/ingest", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ year: Number(year), force }),
      });
      const json = await res.json().catch(() => ({}));
      if (!res.ok) {
        setMsg(String(json.error || `HTTP ${res.status}`));
        return;
      }
      setUnmapped(json.unmapped || []);
      setLoanWarn(Boolean(json.loanMixedWarn));
      setMsg(
        `取込完了: ${json.upserted}ヶ月分更新` +
          (json.skippedManual
            ? ` / 手入力保護でスキップ ${json.skippedManual}`
            : "") +
          (json.unmappedTotal ? ` / 未分類 ${json.unmappedTotal}種` : "")
      );
      router.refresh();
    } catch (e) {
      setMsg(e instanceof Error ? e.message : "失敗");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div>
      <div className="tax-form-row">
        <label>
          取込年
          <input
            type="number"
            min={2000}
            max={2100}
            value={year}
            onChange={(ev) => setYear(ev.target.value)}
          />
        </label>
        <button
          type="button"
          className="btn primary"
          disabled={busy}
          onClick={() => run(false)}
        >
          {busy ? "取込中…" : "Zaimから月次実績を取込"}
        </button>
        <button
          type="button"
          className="btn"
          disabled={busy}
          onClick={() => {
            if (
              typeof window !== "undefined" &&
              !window.confirm(
                "手入力の月も上書きします。よろしいですか？"
              )
            ) {
              return;
            }
            void run(true);
          }}
        >
          手入力も上書きして取込
        </button>
      </div>
      <p className="meta" style={{ marginTop: 8 }}>
        承認済みマップのみ使用。家賃→PQ、管理費→VQ、固都税→F年額、ローン返済→出金のみ（Gに入れない）。Q（稼働戸月）は取込後に手入力。
      </p>
      {msg ? <p className="meta">{msg}</p> : null}
      {loanWarn ? (
        <p className="meta" style={{ color: "var(--med)" }}>
          ローン行は元利が分かれていないため、全額を現金出金扱い（Fに未計上）にしています。利息を分けたい場合は手入力でFを補正してください。
        </p>
      ) : null}
      {unmapped.length > 0 ? (
        <div style={{ marginTop: 12 }}>
          <div className="meta" style={{ fontWeight: 600, color: "var(--high)" }}>
            未分類（事業系）— 暫定MQから除外されています
          </div>
          <table style={{ marginTop: 6 }}>
            <thead>
              <tr>
                <th>主体</th>
                <th>カテゴリ</th>
                <th>サブ</th>
                <th className="num">件数</th>
                <th className="num">金額</th>
              </tr>
            </thead>
            <tbody>
              {unmapped.map((u) => (
                <tr key={`${u.entity}-${u.category}-${u.subcategory}`}>
                  <td>{u.entity}</td>
                  <td>{u.category}</td>
                  <td>{u.subcategory || "—"}</td>
                  <td className="num">{u.count}</td>
                  <td className="num">{fmtMqMan(yenToMan(u.amount))}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
    </div>
  );
}
