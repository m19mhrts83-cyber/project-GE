"use client";

import { useRouter } from "next/navigation";
import { useMemo, useState } from "react";
import { fmtYen } from "@/lib/format";
import {
  FREE_RAILS,
  FUNDING_LADDER,
  POLICY_LOAN_UI_NOTE,
  SCENARIO_EXAMPLES,
  SMBC_SETTLEMENT_ACCOUNT_LABEL,
  TRANSFER_PHASES,
  buildCardSettlementAssistSteps,
  computeGapView,
  defaultCardSettlementRationale,
} from "@/lib/cardSettlementBuffer";

export default function CardSettlementBufferForm({
  smbcBalanceYen,
  smbcAccountLabel,
  liquidityTotalYen,
  initialDueDate,
  initialNeedYen,
}: {
  smbcBalanceYen?: number | null;
  smbcAccountLabel?: string;
  liquidityTotalYen?: number | null;
  initialDueDate?: string | null;
  initialNeedYen?: number | null;
}) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [dueDate, setDueDate] = useState(initialDueDate?.trim() || "");
  const [needYen, setNeedYen] = useState(
    initialNeedYen != null && Number.isFinite(initialNeedYen)
      ? String(Math.round(initialNeedYen))
      : "1000000"
  );
  const [smbcYen, setSmbcYen] = useState(
    smbcBalanceYen != null ? String(Math.round(smbcBalanceYen)) : ""
  );
  const [reserveYen, setReserveYen] = useState("0");

  const accountLabel = smbcAccountLabel || SMBC_SETTLEMENT_ACCOUNT_LABEL;

  const gapView = useMemo(() => {
    const need = Number(needYen);
    const smbc = Number(smbcYen);
    const reserve = Number(reserveYen) || 0;
    if (![need, smbc].every((n) => Number.isFinite(n))) return null;
    return computeGapView({
      needYen: need,
      smbcYen: smbc,
      reserveYen: reserve,
      liquidityTotalYen,
    });
  }, [needYen, smbcYen, reserveYen, liquidityTotalYen]);

  async function onSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (!dueDate.trim()) {
      setMsg("引落日を入れてください（Vpassの請求日）");
      return;
    }
    setBusy(true);
    setMsg(null);
    const need = Number(needYen);
    const smbc = Number(smbcYen);
    const gv =
      Number.isFinite(need) && Number.isFinite(smbc)
        ? computeGapView({
            needYen: need,
            smbcYen: smbc,
            reserveYen: Number(reserveYen) || 0,
            liquidityTotalYen,
          })
        : null;
    try {
      const res = await fetch("/api/money-ops", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          title: `Olive Infinite 引落バッファ（${dueDate}）`,
          kind: "card_settlement_buffer",
          from_account: "各行余剰（無料レール）",
          to_account: accountLabel,
          amount_jpy: Number.isFinite(need) ? need : null,
          due_date: dueDate,
          rationale: defaultCardSettlementRationale({
            needYen: Number.isFinite(need) ? need : null,
            dueDate,
            gapView: gv,
          }),
          assist_payload: {
            playbook: "card_settlement_buffer",
            due_date: dueDate,
            need_jpy: Number.isFinite(need) ? need : null,
            smbc_jpy: Number.isFinite(smbc) ? smbc : null,
            smbc_account: accountLabel,
            reserve_jpy: Number(reserveYen) || 0,
            gap_jpy: gv?.smbcShortfall ?? null,
            liquidity_total_jpy: liquidityTotalYen ?? null,
            household_coverable: gv?.householdCoverable ?? null,
            funding_ladder: FUNDING_LADDER.map((s) => s.id),
            free_rails: FREE_RAILS.map((r) => r.id),
            transfer_phases: TRANSFER_PHASES.map((p) => p.id),
            scenario_examples: SCENARIO_EXAMPLES.map((s) => s.id),
            steps: buildCardSettlementAssistSteps({
              dueDate,
              needYen: Number.isFinite(need) ? need : null,
              smbcYen: Number.isFinite(smbc) ? smbc : null,
              gapView: gv,
            }),
          },
          status: "consulting",
        }),
      });
      const data = await res.json();
      if (!res.ok) {
        setMsg(data.error || "失敗");
      } else {
        setMsg(
          data.reused
            ? "同じ引落日の検討案が既にあったので、それを開きました（二重作成しません）"
            : "検討素案を consulting で作成しました。下の一覧で確認・承認へ。"
        );
        router.refresh();
      }
    } catch (err) {
      setMsg(err instanceof Error ? err.message : "エラー");
    } finally {
      setBusy(false);
    }
  }

  const shortfall = gapView?.smbcShortfall;
  const coverHint =
    gapView == null
      ? null
      : shortfall != null && shortfall <= 0
        ? "引落口座だけで足りそうです"
        : gapView.householdCoverable === true
          ? "他の銀行・現金を寄せれば足りそう（まず無料レール。調達ラダーは原則不要）"
          : gapView.householdCoverable === false
            ? "他行寄せでも足りない可能性 → 利金、または返済計画付き貸付／Bloomo"
            : "他行合計は下の参考額を見て判断";

  return (
    <form className="card notice" onSubmit={onSubmit} style={{ marginBottom: 16 }}>
      <header>
        <span className="lvl">プレイブック</span>
        <strong>カード引落バッファ</strong>
      </header>
      <p className="meta" style={{ marginTop: 8 }}>
        Olive などの大型引落に向け、<strong>引落口座へ無料で寄せる</strong>計画です。
        自動振込はしません。承認は「この寄せ方でよい」の合意だけです。
        金額・引落日は財務メール（Gmail）または Vpass で確定して入力してください。
      </p>
      <p className="meta" style={{ marginTop: 6 }}>
        {POLICY_LOAN_UI_NOTE}
      </p>

      <div
        className="meta"
        style={{
          marginTop: 10,
          padding: 10,
          borderRadius: 8,
          background: "var(--card-soft, #f6f6f4)",
        }}
      >
        <div>
          引落口座（正本）: <strong>{accountLabel}</strong>
          {smbcBalanceYen != null ? ` · 直近 ${fmtYen(Math.round(smbcBalanceYen))}` : ""}
        </div>
        {liquidityTotalYen != null ? (
          <div style={{ marginTop: 4 }}>
            銀行＋現金の合計（参考）: <strong>{fmtYen(Math.round(liquidityTotalYen))}</strong>
            {gapView?.otherBanksYen != null
              ? ` · うち他口座 ${fmtYen(Math.round(gapView.otherBanksYen))}`
              : ""}
          </div>
        ) : null}
      </div>

      <div style={{ marginTop: 12 }}>
        <strong style={{ fontSize: 14 }}>この画面の読み方</strong>
        <p className="meta" style={{ marginTop: 6 }}>
          <strong>本流</strong>は①〜④です。無料レールは送金手段、例A〜Dは入金額が変わった場合の
          結果比較です。どちらも本流とは別の記号です。
        </p>
      </div>

      <div style={{ marginTop: 12 }}>
        <strong style={{ fontSize: 14 }}>本流① 必要額と残す額を確定する</strong>
        <p className="meta" style={{ marginTop: 6 }}>
          引落日・必要額・引落口座残高を確認し、各口座では次回の固定引落と安全バッファを先に確保します。
        </p>
      </div>

      <div style={{ marginTop: 12 }}>
        <strong style={{ fontSize: 14 }}>本流② 段階的に寄せる</strong>
        <ol className="meta" style={{ marginTop: 6, paddingLeft: 18 }}>
          {TRANSFER_PHASES.map((p) => (
            <li key={p.id} style={{ marginBottom: 6 }}>
              <strong>{p.title}</strong>（{p.timing}）— {p.action}
              <br />
              確認: {p.gate}
            </li>
          ))}
        </ol>
      </div>

      <div style={{ marginTop: 12 }}>
        <strong style={{ fontSize: 14 }}>送金手段：無料レール3本</strong>
        <p className="meta" style={{ marginTop: 4 }}>
          以下は本流②で使う「運び方」です。A・B・Cの代替案ではありません。
        </p>
        <ol className="meta" style={{ marginTop: 6, paddingLeft: 18 }}>
          {FREE_RAILS.map((r) => (
            <li key={r.id}>
              <strong>{r.title}</strong> — {r.use}
            </li>
          ))}
        </ol>
      </div>

      <div style={{ marginTop: 12 }}>
        <strong style={{ fontSize: 14 }}>本流③ 例A〜Dで充足度を確認する</strong>
        <p className="meta" style={{ marginTop: 4 }}>
          A〜Dは手順の選択肢ではなく、給与や家賃入金をどこまで反映したかを比較する例です。
        </p>
        <ol className="meta" style={{ marginTop: 6, paddingLeft: 18 }}>
          {SCENARIO_EXAMPLES.map((s) => (
            <li key={s.id} style={{ marginBottom: 4 }}>
              <strong>
                例{s.id}：{s.title}（{s.role}）
              </strong>{" "}
              — {s.example}
            </li>
          ))}
        </ol>
      </div>

      <div style={{ marginTop: 12 }}>
        <strong style={{ fontSize: 14 }}>本流④ それでも足りないときだけ調達する</strong>
        <ol className="meta" style={{ marginTop: 6, paddingLeft: 18 }}>
          {FUNDING_LADDER.filter((s) => s.order >= 1).map((s) => (
            <li key={s.id}>
              <strong>
                {s.order}. {s.title}
              </strong>{" "}
              [{s.verdict}] — {s.note}
            </li>
          ))}
        </ol>
      </div>

      <div
        style={{
          display: "grid",
          gap: 8,
          marginTop: 14,
          gridTemplateColumns: "repeat(auto-fit, minmax(160px, 1fr))",
        }}
      >
        <label className="meta">
          引落日（必須）
          <input
            value={dueDate}
            onChange={(e) => setDueDate(e.target.value)}
            type="date"
            required
            style={{ display: "block", width: "100%", marginTop: 4 }}
          />
        </label>
        <label className="meta">
          必要額（円）
          <input
            value={needYen}
            onChange={(e) => setNeedYen(e.target.value)}
            type="number"
            min={0}
            required
            style={{ display: "block", width: "100%", marginTop: 4 }}
          />
        </label>
        <label className="meta">
          {accountLabel}の残高（円）
          <input
            value={smbcYen}
            onChange={(e) => setSmbcYen(e.target.value)}
            type="number"
            min={0}
            required
            style={{ display: "block", width: "100%", marginTop: 4 }}
          />
        </label>
        <label className="meta">
          同口座に残す固定＋バッファ（円）
          <input
            value={reserveYen}
            onChange={(e) => setReserveYen(e.target.value)}
            type="number"
            min={0}
            style={{ display: "block", width: "100%", marginTop: 4 }}
          />
        </label>
      </div>

      <div style={{ marginTop: 12 }}>
        <strong>
          SMBC不足（寄せの目標）:{" "}
          {shortfall == null
            ? "—"
            : shortfall <= 0
              ? "0円（足りている）"
              : `${Math.round(shortfall).toLocaleString("ja-JP")}円`}
        </strong>
        {coverHint ? (
          <p className="meta" style={{ marginTop: 4 }}>
            {coverHint}
          </p>
        ) : null}
        <p className="meta" style={{ marginTop: 4 }}>
          「不足」＝引落口座に足りない額です。家計全体の現金不足ではありません。
        </p>
      </div>

      <p style={{ marginTop: 12 }}>
        <button type="submit" className="btn primary" disabled={busy}>
          {busy ? "作成中…" : "この内容で検討案を作る"}
        </button>
      </p>
      {msg ? <p className="meta">{msg}</p> : null}
    </form>
  );
}
