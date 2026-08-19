import Link from "next/link";
import type { MqTaxCompare, MqTaxCompareDual } from "@/lib/mqTaxCompare";
import { fmtMqManSigned } from "@/lib/mqUnits";

function cellMan(n: number | null | undefined): string {
  if (n == null || !Number.isFinite(n)) return "—";
  return fmtMqManSigned(n);
}

function CompareTable({ compare }: { compare: MqTaxCompare }) {
  return (
    <>
      {!compare.hasMetrics ? (
        <div className="card notice" style={{ marginTop: 10 }}>
          <strong>申告KPI未登録</strong>
          <p className="meta" style={{ marginTop: 6 }}>
            {compare.yearLabel}の結果を /tax に登録すると、MQ実績との差が出ます。
          </p>
        </div>
      ) : null}

      <div className="table-scroll" style={{ marginTop: 12 }}>
        <table>
          <thead>
            <tr>
              <th>項目</th>
              <th className="num">MQ実績</th>
              <th className="num">申告</th>
              <th className="num">差（MQ−申告）</th>
              <th>差の典型</th>
            </tr>
          </thead>
          <tbody>
            {compare.rows.map((r) => (
              <tr
                key={r.id}
                style={r.emphasize ? { fontWeight: 600 } : undefined}
              >
                <td>{r.label}</td>
                <td className="num">{cellMan(r.mqMan)}</td>
                <td className="num">{cellMan(r.filedMan)}</td>
                <td className="num">{cellMan(r.diffMan)}</td>
                <td className="meta">{r.hint ?? "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {compare.categoryRows?.length ? (
        <div style={{ marginTop: 16 }}>
          <h3 style={{ fontSize: "0.9rem", marginBottom: 4 }}>
            科目別差（上位）
          </h3>
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>科目</th>
                  <th className="num">MQ</th>
                  <th className="num">申告</th>
                  <th className="num">差</th>
                </tr>
              </thead>
              <tbody>
                {compare.categoryRows.map((r) => (
                  <tr key={r.id}>
                    <td>{r.label}</td>
                    <td className="num">{cellMan(r.mqMan)}</td>
                    <td className="num">{cellMan(r.filedMan)}</td>
                    <td className="num">{cellMan(r.diffMan)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      ) : null}

      {compare.insights.length > 0 ? (
        <ul className="meta" style={{ marginTop: 10 }}>
          {compare.insights.map((t) => (
            <li key={t}>{t}</li>
          ))}
        </ul>
      ) : null}

      {compare.filedOn ? (
        <p className="meta" style={{ marginTop: 8 }}>
          申告日: {String(compare.filedOn).slice(0, 10)}
          {compare.filingStatus ? ` · ${compare.filingStatus}` : ""}
        </p>
      ) : null}
    </>
  );
}

type Props = {
  compare: MqTaxCompare | null;
  dual?: MqTaxCompareDual | null;
  grain: "month" | "year";
  line: string;
  entity: string;
  periodLabel: string;
};

export default function MqTaxComparePanel({
  compare,
  dual,
  grain,
  line,
  entity,
  periodLabel,
}: Props) {
  if (grain !== "year") {
    return (
      <div className="card" style={{ marginTop: 12 }}>
        <header>
          <span className="lvl">確定申告</span>
          <strong>比較物差し</strong>
        </header>
        <p className="meta" style={{ marginTop: 8 }}>
          確定申告との突合は年次表示です。上のスライサーで「年次」を選んでください。
        </p>
      </div>
    );
  }

  if (line === "all") {
    return (
      <div className="card" style={{ marginTop: 12 }}>
        <header>
          <span className="lvl">確定申告</span>
          <strong>比較物差し</strong>
        </header>
        <p className="meta" style={{ marginTop: 8 }}>
          事業線「全体」は申告比較の対象外です。不動産またはAIを選んでください。
        </p>
      </div>
    );
  }

  if (entity === "combined" && dual) {
    return (
      <div className="card" style={{ marginTop: 12 }}>
        <header>
          <span className="lvl">確定申告</span>
          <strong>比較物差し · 合算（個人+法人） · {periodLabel}</strong>
        </header>
        <p className="meta" style={{ marginTop: 6 }}>
          {dual.disclaimer}{" "}
          <Link href="/tax">/tax で申告KPI登録 →</Link>
        </p>

        {dual.combinedReference ? (
          <p className="meta" style={{ marginTop: 10 }}>
            MQ合算参考: PQ {cellMan(dual.combinedReference.pqMan)} · G{" "}
            {cellMan(dual.combinedReference.gMan)}（申告合算はしません）
          </p>
        ) : null}

        {dual.personal ? (
          <div style={{ marginTop: 16 }}>
            <h3 style={{ fontSize: "0.95rem", marginBottom: 4 }}>
              個人 · {dual.personal.yearLabel}
            </h3>
            <CompareTable compare={dual.personal} />
          </div>
        ) : (
          <p className="meta" style={{ marginTop: 12 }}>
            個人の比較を出せません（MQ実績または申告KPIを確認）。
          </p>
        )}

        {dual.corporate ? (
          <div style={{ marginTop: 20 }}>
            <h3 style={{ fontSize: "0.95rem", marginBottom: 4 }}>
              法人 · {dual.corporate.yearLabel}
            </h3>
            <CompareTable compare={dual.corporate} />
          </div>
        ) : (
          <p className="meta" style={{ marginTop: 12 }}>
            法人の比較を出せません（MQ実績または申告KPIを確認）。
          </p>
        )}
      </div>
    );
  }

  if (entity === "combined") {
    return (
      <div className="card" style={{ marginTop: 12 }}>
        <header>
          <span className="lvl">確定申告</span>
          <strong>比較物差し</strong>
        </header>
        <p className="meta" style={{ marginTop: 8 }}>
          合算表示ですが、この条件では個人・法人の比較データがありません。
        </p>
      </div>
    );
  }

  if (!compare) {
    return (
      <div className="card" style={{ marginTop: 12 }}>
        <header>
          <span className="lvl">確定申告</span>
          <strong>比較物差し</strong>
        </header>
        <p className="meta" style={{ marginTop: 8 }}>
          この条件では申告比較を出せません。
        </p>
      </div>
    );
  }

  return (
    <div className="card" style={{ marginTop: 12 }}>
      <header>
        <span className="lvl">確定申告</span>
        <strong>
          比較物差し · {compare.yearLabel} · {periodLabel}
        </strong>
      </header>
      <p className="meta" style={{ marginTop: 6 }}>
        {compare.disclaimer}{" "}
        <Link href="/tax">/tax で申告KPI登録 →</Link>
      </p>
      <CompareTable compare={compare} />
    </div>
  );
}
