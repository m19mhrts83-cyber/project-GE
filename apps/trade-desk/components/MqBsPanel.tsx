"use client";

import { useRouter } from "next/navigation";
import { useMemo, useState } from "react";
import { fmtYen } from "@/lib/format";
import {
  BS_FIELD_LABELS,
  isBsBalanced,
  isBsComplete,
  missingBsFields,
  normalizeBs,
  resolveCurrentProfit,
  sumAssets,
  sumLiabEquity,
  type MqBsFields,
} from "@/lib/mqBs";

function yenOrNeed(n: number | null | undefined): string {
  if (n == null || !Number.isFinite(n)) return "要確認";
  return fmtYen(Math.round(n));
}

type Props = {
  title: string;
  fields: MqBsFields | null;
  mqG?: number | null;
  asOfLabel: string;
  combineNote?: string | null;
  /** 賃貸は棚卸を必須にしない */
  requireInventory?: boolean;
  defaultLine: "realestate" | "ai";
  defaultEntity: "personal" | "corporate";
  defaultAsOf: string;
  initial?: Partial<MqBsFields> & { note?: string | null };
};

export default function MqBsPanel({
  title,
  fields,
  mqG,
  asOfLabel,
  combineNote,
  requireInventory = false,
  defaultLine,
  defaultEntity,
  defaultAsOf,
  initial,
}: Props) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [open, setOpen] = useState(false);

  const base = fields ?? normalizeBs(initial || {});
  const profit = resolveCurrentProfit(base, mqG);
  const display: MqBsFields = {
    ...base,
    current_profit: profit.value,
  };
  const complete = isBsComplete(base, { requireInventory });
  const balanced = isBsBalanced(
    { ...base, current_profit: base.current_profit ?? profit.value },
    { requireInventory }
  );
  const missing = missingBsFields(base, { requireInventory });

  const assets = sumAssets(display);
  const liabEq = sumLiabEquity({
    ...display,
    current_profit: profit.value,
  });

  const preview = useMemo(() => display, [display]);

  async function onSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setBusy(true);
    setMsg(null);
    const fd = new FormData(e.currentTarget);
    const num = (k: string) => {
      const v = fd.get(k);
      if (v == null || String(v).trim() === "") return null;
      return v;
    };
    const body = {
      business_line: String(fd.get("business_line")),
      entity: String(fd.get("entity")),
      as_of_date: String(fd.get("as_of_date")),
      cash: num("cash"),
      receivables: num("receivables"),
      inventory: num("inventory"),
      fixed_assets: num("fixed_assets"),
      liabilities_st: num("liabilities_st"),
      liabilities_lt: num("liabilities_lt"),
      capital: num("capital"),
      retained_earnings: num("retained_earnings"),
      current_profit: num("current_profit"),
      note: fd.get("note") || null,
      source: "manual",
    };
    try {
      const res = await fetch("/api/mq/bs", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      const json = await res.json().catch(() => ({}));
      if (!res.ok) {
        setMsg(String(json.error || `HTTP ${res.status}`));
        return;
      }
      setMsg("B/Sを保存しました");
      setOpen(false);
      router.refresh();
    } catch (err) {
      setMsg(err instanceof Error ? err.message : "保存に失敗");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="card mq-bs">
      <header>
        <span className="lvl">軽量B/S</span>
        <strong>{title}</strong>
      </header>
      <p className="meta" style={{ marginTop: 6 }}>
        基準日 {asOfLabel}
        {!complete ? " · 未入力あり（捏造しません）" : balanced ? " · 貸借一致" : " · 貸借不一致"}
      </p>
      {combineNote ? (
        <p className="meta" style={{ color: "var(--high)", marginTop: 4 }}>
          {combineNote}
        </p>
      ) : null}

      <div
        style={{
          display: "grid",
          gridTemplateColumns: "1fr 1fr",
          gap: 12,
          marginTop: 10,
        }}
      >
        <table>
          <thead>
            <tr>
              <th>資産</th>
              <th className="num">金額</th>
            </tr>
          </thead>
          <tbody>
            {(
              [
                "cash",
                "receivables",
                "inventory",
                "fixed_assets",
              ] as const
            ).map((k) => (
              <tr key={k}>
                <td>
                  {BS_FIELD_LABELS[k]}
                  {k === "inventory" && !requireInventory ? (
                    <span className="meta">（賃貸は任意）</span>
                  ) : null}
                </td>
                <td className="num">{yenOrNeed(preview[k])}</td>
              </tr>
            ))}
            <tr>
              <td>
                <strong>資産合計</strong>
              </td>
              <td className="num">
                <strong>
                  {complete || assets !== 0 ? yenOrNeed(assets) : "要確認"}
                </strong>
              </td>
            </tr>
          </tbody>
        </table>
        <table>
          <thead>
            <tr>
              <th>負債・資本</th>
              <th className="num">金額</th>
            </tr>
          </thead>
          <tbody>
            {(
              [
                "liabilities_st",
                "liabilities_lt",
                "capital",
                "retained_earnings",
                "current_profit",
              ] as const
            ).map((k) => (
              <tr key={k}>
                <td>
                  {BS_FIELD_LABELS[k]}
                  {k === "current_profit" && profit.fromMq ? (
                    <span className="meta">（MQのG・参考）</span>
                  ) : null}
                </td>
                <td className="num">
                  {k === "current_profit"
                    ? yenOrNeed(profit.value)
                    : yenOrNeed(preview[k])}
                </td>
              </tr>
            ))}
            <tr>
              <td>
                <strong>負債・資本合計</strong>
              </td>
              <td className="num">
                <strong>{yenOrNeed(liabEq)}</strong>
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      {missing.length > 0 ? (
        <p className="meta" style={{ marginTop: 8 }}>
          要確認: {missing.map((k) => BS_FIELD_LABELS[k]).join("、")}
        </p>
      ) : null}

      <div style={{ marginTop: 10 }}>
        <button type="button" className="btn" onClick={() => setOpen((v) => !v)}>
          {open ? "入力を閉じる" : "穴埋め入力"}
        </button>
      </div>

      {open ? (
        <form onSubmit={onSubmit} style={{ marginTop: 12 }}>
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "repeat(auto-fill, minmax(140px, 1fr))",
              gap: 8,
            }}
          >
            <label>
              事業線
              <select name="business_line" defaultValue={defaultLine}>
                <option value="realestate">不動産</option>
                <option value="ai">AI</option>
              </select>
            </label>
            <label>
              主体
              <select name="entity" defaultValue={defaultEntity}>
                <option value="personal">個人</option>
                <option value="corporate">法人</option>
              </select>
            </label>
            <label>
              基準日
              <input name="as_of_date" type="date" defaultValue={defaultAsOf} required />
            </label>
            {(
              Object.keys(BS_FIELD_LABELS) as (keyof MqBsFields)[]
            ).map((k) => (
              <label key={k}>
                {BS_FIELD_LABELS[k]}
                <input
                  name={k}
                  type="number"
                  step="1"
                  defaultValue={
                    initial?.[k] != null
                      ? String(initial[k])
                      : base[k] != null
                        ? String(base[k])
                        : ""
                  }
                  placeholder="空=要確認"
                />
              </label>
            ))}
            <label style={{ gridColumn: "1 / -1" }}>
              メモ
              <input name="note" defaultValue={initial?.note || ""} />
            </label>
          </div>
          <p className="meta" style={{ marginTop: 6 }}>
            空欄は NULL のまま保存します（0 を入れたいときだけ 0 を入力）。
          </p>
          <button type="submit" className="btn primary" disabled={busy} style={{ marginTop: 8 }}>
            {busy ? "保存中…" : "B/Sを保存"}
          </button>
          {msg ? (
            <p className="meta" style={{ marginTop: 6 }}>
              {msg}
            </p>
          ) : null}
        </form>
      ) : msg ? (
        <p className="meta" style={{ marginTop: 6 }}>
          {msg}
        </p>
      ) : null}
    </div>
  );
}
