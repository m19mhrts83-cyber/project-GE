import Link from "next/link";
import type { HouseholdTaxBand } from "@/lib/householdBsTaxBand";
import { fmtMqManSigned } from "@/lib/mqUnits";

function cell(n: number | null | undefined): string {
  if (n == null || !Number.isFinite(n)) return "—";
  return fmtMqManSigned(n);
}

export default function HouseholdBsTaxBandPanel({
  band,
}: {
  band: HouseholdTaxBand;
}) {
  return (
    <div className="card" style={{ marginTop: 12 }}>
      <header>
        <span className="lvl">確定申告</span>
        <strong>比較帯 · {band.year}年</strong>
      </header>
      <p className="meta" style={{ marginTop: 6 }}>
        {band.disclaimer}{" "}
        <Link href="/tax">/tax で申告KPI →</Link>
        {" · "}
        <Link href="/mq">/mq 詳細比較 →</Link>
      </p>
      <table style={{ marginTop: 10 }}>
        <thead>
          <tr>
            <th>主体</th>
            <th className="num">MQ（万円）</th>
            <th className="num">申告</th>
            <th className="num">差</th>
            <th>メモ</th>
          </tr>
        </thead>
        <tbody>
          {band.rows.map((r) => (
            <tr key={r.id}>
              <td>{r.label}</td>
              <td className="num">{cell(r.mqMan)}</td>
              <td className="num">{cell(r.filedMan)}</td>
              <td className="num">{cell(r.diffMan)}</td>
              <td className="meta">{r.hint ?? "—"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
