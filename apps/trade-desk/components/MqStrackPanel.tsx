/* eslint-disable react/no-unescaped-entities */
"use client";

import { useMemo, useState } from "react";
import type { MqComputed } from "@/lib/mqEquations";
import { formatRatio } from "@/lib/mqEquations";
import { fmtMqMan } from "@/lib/mqUnits";

type AccountMapSummary = {
  category_match: string;
  subcategory_match: string;
  entity_match: string;
  combine_treatment: string;
  note?: string | null;
};

function yenOrDash(n: number | null | undefined): string {
  if (n == null || !Number.isFinite(n)) return "—";
  return fmtMqMan(n);
}

export default function MqStrackPanel({
  title,
  computed,
  cashBegin,
  cashIn,
  cashOut,
  cashEnd,
  depreciation,
  emptyHint,
  qUnitLabel,
  fMonthlyPart,
  fAnnualAllocated,
  fBreakdownKind,
  includeDebtServiceInF,
  vqAccountMap,
  cashBridgeNote,
}: {
  title: string;
  computed: MqComputed | null;
  cashBegin?: number | null;
  cashIn?: number | null;
  cashOut?: number | null;
  cashEnd?: number | null;
  depreciation?: number | null;
  emptyHint?: string;
  /** 例: 稼働戸月 / 案件数 */
  qUnitLabel?: string;
  /** F 固定費の内訳: 月次F（=F/月） */
  fMonthlyPart?: number | null;
  /** F 固定費の内訳: 年額側（=年額÷12 or 年額そのもの） */
  fAnnualAllocated?: number | null;
  /** UI の見せ方: 粒度（month=年額÷12 / year=年額） */
  fBreakdownKind?: "month" | "year";
  /** 不動産ラインだけ: ローン出金（cash_out）をFへ寄せて「実態版」で表示 */
  includeDebtServiceInF?: boolean;
  /** VQ（変動費）に割り当てられているZaimカテゴリのマップ（クリック内訳用） */
  vqAccountMap?: AccountMapSummary[];
  /** 現金橋の出典（資金繰り連動など） */
  cashBridgeNote?: string;
}) {
  if (!computed) {
    return (
      <div className="card mq-strack">
        <header>
          <span className="lvl">MQ会計表</span>
          <strong>{title}</strong>
        </header>
        <p className="meta" style={{ marginTop: 8 }}>
          {emptyHint || "データがありません"}
        </p>
      </div>
    );
  }

  const c = computed;

  const [detail, setDetail] = useState<
    "pq" | "vq" | "mq" | "f" | "g" | "eq" | null
  >(null);

  const debtServiceMan = includeDebtServiceInF && cashOut != null ? cashOut : null;
  const fShown = debtServiceMan == null ? c.f : c.f + debtServiceMan;
  const gShown = debtServiceMan == null ? c.g : c.g - debtServiceMan;
  const gOverPqShown = c.pq !== 0 ? gShown / c.pq : null;

  const equationDiff = useMemo(() => {
    const v = c.pq - (c.vq + fShown + gShown);
    return Number.isFinite(v) ? v : null;
  }, [c.pq, c.vq, fShown, gShown]);

  const equationOkShown =
    equationDiff != null ? Math.abs(equationDiff) <= 0.5 : false;

  const fBreakdownText = useMemo(() => {
    if (fBreakdownKind === "year") {
      if (fMonthlyPart == null && fAnnualAllocated == null) return null;
      return `内訳（年次）: 月額合計 ${fmtMqMan(fMonthlyPart)} + 年額 ${fmtMqMan(
        fAnnualAllocated
      )}`;
    }
    if (fMonthlyPart == null && fAnnualAllocated == null) return null;
    return `内訳（月次）: 月額 ${fmtMqMan(fMonthlyPart)} + 年額÷12 ${fmtMqMan(
      fAnnualAllocated
    )}`;
  }, [fAnnualAllocated, fBreakdownKind, fMonthlyPart]);

  return (
    <div className="card mq-strack">
      <header>
        <span className="lvl">MQ会計表</span>
        <strong>{title}</strong>
      </header>
      <div className="mq-strack-grid" style={{ marginTop: 12 }}>
        <div
          className="mq-box mq-box-pq clickable"
          role="button"
          tabIndex={0}
          aria-label="PQ（クリックで内訳/検算）"
          onClick={() => setDetail("pq")}
          onKeyDown={(e) => {
            if (e.key === "Enter" || e.key === " ") setDetail("pq");
          }}
        >
          <div className="mq-box-label">PQ 売上</div>
          <div className="mq-box-val">{yenOrDash(c.pq)}</div>
          <div className="meta">
            P {yenOrDash(c.p)} × Q {c.q ?? "—"}
            {qUnitLabel ? `（${qUnitLabel}）` : ""}
          </div>
        </div>
        <div
          className="mq-box mq-box-vq clickable"
          role="button"
          tabIndex={0}
          aria-label="VQ（クリックで内訳/検算）"
          onClick={() => setDetail("vq")}
          onKeyDown={(e) => {
            if (e.key === "Enter" || e.key === " ") setDetail("vq");
          }}
        >
          <div className="mq-box-label">VQ 変動費</div>
          <div className="mq-box-val">{yenOrDash(c.vq)}</div>
          <div className="meta">V {yenOrDash(c.v)}</div>
        </div>
        <div
          className="mq-box mq-box-mq clickable"
          role="button"
          tabIndex={0}
          aria-label="MQ（クリックで内訳/検算）"
          onClick={() => setDetail("mq")}
          onKeyDown={(e) => {
            if (e.key === "Enter" || e.key === " ") setDetail("mq");
          }}
        >
          <div className="mq-box-label">MQ 粗利総額</div>
          <div className="mq-box-val">{yenOrDash(c.mq)}</div>
          <div className="meta">
            M {yenOrDash(c.m)} · m/p {formatRatio(c.mOverP)}
          </div>
        </div>
        <div
          className="mq-box mq-box-f clickable"
          role="button"
          tabIndex={0}
          aria-label="F（クリックで内訳/検算）"
          onClick={() => setDetail("f")}
          onKeyDown={(e) => {
            if (e.key === "Enter" || e.key === " ") setDetail("f");
          }}
        >
          <div className="mq-box-label">F 固定費</div>
          <div className="mq-box-val">{yenOrDash(fShown)}</div>
          <div className="meta">
            {debtServiceMan == null
              ? "元本返済は含めない（MQ定義）"
              : "元本相当（ローン出金）を含む（実態版）"}
          </div>
        </div>
        <div
          className="mq-box mq-box-g clickable"
          role="button"
          tabIndex={0}
          aria-label="G（クリックで内訳/検算）"
          onClick={() => setDetail("g")}
          onKeyDown={(e) => {
            if (e.key === "Enter" || e.key === " ") setDetail("g");
          }}
        >
          <div className="mq-box-label">G 利益</div>
          <div className="mq-box-val">{yenOrDash(gShown)}</div>
          <div className="meta">G/PQ {formatRatio(gOverPqShown)}</div>
        </div>
      </div>
      {!equationOkShown ? (
        <p className="meta" style={{ color: "var(--high)", marginTop: 8 }}>
          企業方程式 PQ＝VQ＋F＋G が一致していません
          {equationDiff != null && Math.abs(equationDiff) > 0
            ? `（差分 ${equationDiff.toFixed(0)}万）`
            : ""}
          {" · "}
          <a
            href="#"
            onClick={(e) => {
              e.preventDefault();
              setDetail("eq");
            }}
            style={{ fontWeight: 700 }}
          >
            検算を開く
          </a>
        </p>
      ) : (
        <p className="meta" style={{ marginTop: 8 }}>
          検算 OK · PQ = VQ + F + G
          {equationDiff != null && Math.abs(equationDiff) > 0
            ? `（差分 ${equationDiff.toFixed(0)}万）`
            : ""}
        </p>
      )}

      {detail ? (
        <div className="mq-detail" style={{ marginTop: 12 }}>
          <div className="mq-detail-title">
            {detail === "pq"
              ? "PQ（売上）内訳"
              : detail === "vq"
                ? "VQ（変動費）内訳"
                : detail === "mq"
                  ? "MQ（粗利総額）内訳"
                  : detail === "f"
                    ? "F（固定費）内訳"
                    : detail === "g"
                      ? "G（利益）内訳"
                      : "検算（PQ=VQ+F+G）"}
          </div>

          {detail === "f" ? (
            <div className="mq-detail-grid">
              <div className="k">F（表示）</div>
              <div className="v">{fmtMqMan(fShown)}</div>

              <div className="k">従来MQの固定費</div>
              <div className="v">{fmtMqMan(c.f)}</div>

              <div className="k">月次側</div>
              <div className="v">{fMonthlyPart == null ? "要確認" : fmtMqMan(fMonthlyPart)}</div>

              <div className="k">{fBreakdownKind === "year" ? "年額側" : "年額換算（÷12）"}</div>
              <div className="v">
                {fAnnualAllocated == null ? "要確認" : fmtMqMan(fAnnualAllocated)}
              </div>

              <div className="k">＋元本相当（ローン出金）</div>
              <div className="v">
                {debtServiceMan == null ? "要確認" : fmtMqMan(debtServiceMan)}
              </div>
            </div>
          ) : (
            <div className="mq-detail-grid">
              <div className="k">値</div>
              <div className="v">
                {detail === "pq"
                  ? fmtMqMan(c.pq)
                  : detail === "vq"
                    ? fmtMqMan(c.vq)
                    : detail === "mq"
                      ? fmtMqMan(c.mq)
                      : detail === "g"
                        ? fmtMqMan(c.g)
                        : fmtMqMan(c.pq)}
              </div>
              {detail === "eq" ? (
                <>
                  <div className="k">PQ</div>
                  <div className="v">{fmtMqMan(c.pq)}</div>
                  <div className="k">VQ + F + G</div>
                  <div className="v">{fmtMqMan(c.vq + fShown + gShown)}</div>
                </>
              ) : null}
            </div>
          )}

          {detail === "vq" ? (
            <div style={{ marginTop: 10 }}>
              <div className="meta" style={{ fontWeight: 700, marginBottom: 6 }}>
                VQに入る科目（Zaim→MQ割当）
              </div>
              <div className="meta" style={{ fontSize: 12, marginBottom: 8 }}>
                ※金額ではなく「Zaim科目→MQ要素」の割当マップです
              </div>
              {vqAccountMap && vqAccountMap.length > 0 ? (
                <div style={{ display: "grid", gap: 6 }}>
                  {vqAccountMap.map((m, idx) => {
                    const ent =
                      m.entity_match === "personal"
                        ? "個人"
                        : m.entity_match === "corporate"
                          ? "法人"
                          : "両方";
                    const cat = m.category_match || "—";
                    const sub = m.subcategory_match || "";
                    return (
                      <div key={`${idx}-${cat}-${sub}`} className="meta" style={{ fontSize: 13 }}>
                        - {cat}
                        {sub ? ` / ${sub}` : ""}（${ent}・${m.combine_treatment}）
                        {m.note ? `：${m.note}` : ""}
                      </div>
                    );
                  })}
                </div>
              ) : (
                <div className="meta">マップ未取得（要確認）</div>
              )}
            </div>
          ) : null}

          <div className="mq-detail-note">
            {detail === "f"
              ? debtServiceMan == null
                ? "元本返済は含めません（MQ定義）"
                : "ローン出金（元本相当近似）をFへ寄せた実態版です（従来MQと考え方が異なります）"
              : "企業方程式: PQ = VQ + F + G"}
            {detail === "f" && fBreakdownText ? ` · ${fBreakdownText}` : ""}
            {equationDiff != null ? ` · 差分 ${equationDiff.toFixed(0)}万` : ""}
          </div>

          <div style={{ marginTop: 10, display: "flex", gap: 10, flexWrap: "wrap" }}>
            <button type="button" className="btn" onClick={() => setDetail(null)}>
              閉じる
            </button>
            <button
              type="button"
              className="btn"
              onClick={() => setDetail("eq")}
              title="企業方程式の検算（PQ=VQ+F+G）"
            >
              検算を表示
            </button>
          </div>
        </div>
      ) : null}
      <div className="mq-cash-bridge" style={{ marginTop: 12 }}>
        <div className="meta" style={{ fontWeight: 600, marginBottom: 4 }}>
          現金橋（第5表要約）
          {cashBridgeNote ? ` · ${cashBridgeNote}` : ""}
        </div>
        <table>
          <tbody>
            <tr>
              <td>前期繰越現金</td>
              <td className="num">
                {cashBegin == null ? "要入力" : yenOrDash(cashBegin)}
              </td>
            </tr>
            <tr>
              <td>入金合計</td>
              <td className="num">
                {cashIn == null ? "要入力" : yenOrDash(cashIn)}
              </td>
            </tr>
            <tr>
              <td>出金合計</td>
              <td className="num">
                {cashOut == null ? "要入力" : yenOrDash(cashOut)}
              </td>
            </tr>
            <tr>
              <td>期末現金（家計含む・参考）</td>
              <td className="num">
                {cashEnd == null ? "要入力" : yenOrDash(cashEnd)}
              </td>
            </tr>
            <tr>
              <td>減価（F内・非現金）</td>
              <td className="num">
                {depreciation == null ? "—" : yenOrDash(depreciation)}
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <div className="mq-detail" style={{ marginTop: 12 }}>
        <div className="mq-detail-title">単価評価（Qで割る）</div>
        <div className="mq-detail-grid">
          <div className="k">Q</div>
          <div className="v">
            {c.q == null ? "要確認" : `${c.q.toLocaleString("ja-JP")}${qUnitLabel ? ` ${qUnitLabel}` : ""}`}
          </div>
          <div className="k">P = PQ ÷ Q</div>
          <div className="v">{c.p == null ? "要確認" : fmtMqMan(c.p)}</div>
          <div className="k">V = VQ ÷ Q</div>
          <div className="v">{c.v == null ? "要確認" : fmtMqMan(c.v)}</div>
          <div className="k">M = MQ ÷ Q = P - V</div>
          <div className="v">{c.m == null ? "要確認" : fmtMqMan(c.m)}</div>
          <div className="k">m/p</div>
          <div className="v">{formatRatio(c.mOverP)}</div>
        </div>
        <div className="mq-detail-note">
          単価は Q が入っているときだけ評価できます。総額の PQ / VQ / MQ と合わせて、
          「1戸月あたり・1案件あたりでいくら残るか」を見るための帯です。
        </div>
      </div>
    </div>
  );
}
