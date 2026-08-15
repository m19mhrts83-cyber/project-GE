import type { MqComputed } from "@/lib/mqEquations";
import { formatRatio } from "@/lib/mqEquations";
import { fmtYen } from "@/lib/format";

function yenOrDash(n: number | null | undefined): string {
  if (n == null || !Number.isFinite(n)) return "—";
  return fmtYen(Math.round(n));
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
  return (
    <div className="card mq-strack">
      <header>
        <span className="lvl">MQ会計表</span>
        <strong>{title}</strong>
      </header>
      <div className="mq-strack-grid" style={{ marginTop: 12 }}>
        <div className="mq-box mq-box-pq">
          <div className="mq-box-label">PQ 売上</div>
          <div className="mq-box-val">{yenOrDash(c.pq)}</div>
          <div className="meta">
            P {yenOrDash(c.p)} × Q {c.q ?? "—"}
            {qUnitLabel ? `（${qUnitLabel}）` : ""}
          </div>
        </div>
        <div className="mq-box mq-box-vq">
          <div className="mq-box-label">VQ 変動費</div>
          <div className="mq-box-val">{yenOrDash(c.vq)}</div>
          <div className="meta">V {yenOrDash(c.v)}</div>
        </div>
        <div className="mq-box mq-box-mq">
          <div className="mq-box-label">MQ 粗利総額</div>
          <div className="mq-box-val">{yenOrDash(c.mq)}</div>
          <div className="meta">
            M {yenOrDash(c.m)} · m/p {formatRatio(c.mOverP)}
          </div>
        </div>
        <div className="mq-box mq-box-f">
          <div className="mq-box-label">F 固定費</div>
          <div className="mq-box-val">{yenOrDash(c.f)}</div>
          <div className="meta">元本返済は含めない</div>
        </div>
        <div className="mq-box mq-box-g">
          <div className="mq-box-label">G 利益</div>
          <div className="mq-box-val">{yenOrDash(c.g)}</div>
          <div className="meta">G/PQ {formatRatio(c.gOverPq)}</div>
        </div>
      </div>
      {!c.equationOk ? (
        <p className="meta" style={{ color: "var(--high)", marginTop: 8 }}>
          企業方程式 PQ＝VQ＋F＋G が一致していません
        </p>
      ) : (
        <p className="meta" style={{ marginTop: 8 }}>
          検算 OK · PQ = VQ + F + G
        </p>
      )}
      <div className="mq-cash-bridge" style={{ marginTop: 12 }}>
        <div className="meta" style={{ fontWeight: 600, marginBottom: 4 }}>
          現金橋（第5表要約）
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
    </div>
  );
}
