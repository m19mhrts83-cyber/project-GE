import Shell from "@/components/Shell";
import EnqueueJobButton from "@/components/EnqueueJobButton";
import RealEstateLaneNav from "@/components/RealEstateLaneNav";
import { createClient } from "@/lib/supabase/server";
import { fmtYen } from "@/lib/format";
import {
  buyPlanActionView,
  isBuyAction,
  isSaleAction,
} from "@/lib/buyPlanAction";

export const dynamic = "force-dynamic";

type EventRow = {
  row_no: number;
  action: string | null;
  entity: string | null;
  location: string | null;
  structure: string | null;
  property_name: string | null;
  price_man: number | string | null;
  yield_pct: number | string | null;
  bank: string | null;
  loan_man: number | string | null;
  down_man: number | string | null;
  event_date: string | null;
  memo: string | null;
  sale_strategy: string | null;
};

function n(v: number | string | null | undefined): number | null {
  if (v == null || v === "") return null;
  const x = typeof v === "number" ? v : Number(v);
  return Number.isFinite(x) ? x : null;
}

function yearOf(d: string | null): string {
  if (!d) return "未定";
  return d.slice(0, 4);
}

export default async function BuyPlanPage() {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();

  const { data: buyPlan } = await supabase
    .from("kurashift_buy_plan_versions")
    .select("id, version_key, label, as_of, metadata, source_filename")
    .eq("is_canonical", true)
    .maybeSingle();

  const vid = buyPlan?.id;

  const [{ data: events }, { data: criteria }, { data: constraints }] =
    await Promise.all([
      vid
        ? supabase
            .from("kurashift_buy_plan_events")
            .select(
              "row_no, action, entity, location, structure, property_name, price_man, yield_pct, bank, loan_man, down_man, event_date, memo, sale_strategy"
            )
            .eq("version_id", vid)
            .order("event_date", { ascending: true, nullsFirst: false })
            .order("row_no", { ascending: true })
            .limit(200)
        : Promise.resolve({ data: [] as EventRow[] }),
      vid
        ? supabase
            .from("kurashift_buy_plan_criteria")
            .select("kind, raw_text, sort_order")
            .eq("version_id", vid)
            .order("sort_order", { ascending: true })
            .limit(60)
        : Promise.resolve({ data: [] }),
      vid
        ? supabase
            .from("kurashift_buy_plan_constraints")
            .select(
              "lender, collateral_type, limit_note, rate_term, prop_cond, geo_cond, attr_note"
            )
            .eq("version_id", vid)
            .order("row_no", { ascending: true })
            .limit(40)
        : Promise.resolve({ data: [] }),
    ]);

  const rows = (events || []) as EventRow[];
  const byYear = new Map<string, EventRow[]>();
  for (const e of rows) {
    const y = yearOf(e.event_date);
    if (!byYear.has(y)) byYear.set(y, []);
    byYear.get(y)!.push(e);
  }
  const years = [...byYear.keys()].sort((a, b) => {
    if (a === "未定") return 1;
    if (b === "未定") return -1;
    return a.localeCompare(b);
  });

  const buyCount = rows.filter((e) => isBuyAction(e.action)).length;
  const saleCount = rows.filter((e) => isSaleAction(e.action)).length;
  const loanSum = rows.reduce((s, e) => s + (n(e.loan_man) || 0), 0);
  const priceSum = rows.reduce((s, e) => s + (n(e.price_man) || 0), 0);

  const areas = (criteria || []).filter((c) => c.kind === "area");
  const rules = (criteria || []).filter((c) => c.kind === "purchase_rule");
  const otherCrit = (criteria || []).filter(
    (c) => c.kind !== "area" && c.kind !== "purchase_rule"
  );

  // Notion「物件買い進め条件」(2025-11) の要約（正本は Excel criteria。ここはフォーカス補助）
  const focusHints = [
    "戸建中心・築古OK",
    "想定利回り 20%以上",
    "購入価格 300万以下",
    "土地値 60%以上",
    "ハザード原則除外（高利回りは例外可）",
    "エリア: 愛知（岡崎・碧南・知多・安城・豊田・瀬戸・春日井・犬山・一宮）／岐阜（各務原・岐阜・大垣）／三重（桑名・四日市・津・鈴鹿・海沿除外）／大阪・門真",
  ];

  return (
    <Shell active="/realestate" email={user?.email ?? null}>
      <RealEstateLaneNav active="b-plan" />
      <p className="page-kicker">③-B · 長期プラン</p>
      <h1>買い進めプラン</h1>
      <p className="sub">
        トップダウン（目標CFから逆算）。正本は買い進め Excel → DB 投影。ライフプランと同じく「年表」で見る。
        {" · "}
        <a href="/lifeplan?mode=re_purchase">LP 物件購入モード →</a>
        {" · "}
        <a href="/realestate/deals">千三つ（実行）→</a>
      </p>

      <div className="card notice">
        <header>
          <span className="lvl">Canonical</span>
          <strong>
            {buyPlan
              ? `${buyPlan.label || buyPlan.version_key}`
              : "未取込"}
          </strong>
        </header>
        <p className="meta" style={{ marginTop: 8 }}>
          {buyPlan
            ? `as_of ${buyPlan.as_of} · ${buyPlan.source_filename || ""} · events ${rows.length}`
            : "OneDrive の ★プランニングシートを ingest してください"}
        </p>
        <p style={{ marginTop: 10, display: "flex", flexWrap: "wrap", gap: 8 }}>
          <EnqueueJobButton
            jobType="buy_plan_ingest"
            title="買い進めExcel再取込"
            label="Excel再取込"
            payload={{}}
          />
          <EnqueueJobButton
            jobType="buy_plan_export"
            title="STEP3互換Excelをexport"
            label="STEP3 export"
            payload={{}}
          />
        </p>
      </div>

      <div className="card">
        <header>
          <span className="lvl">KPI</span>
          <strong>プラン要約（STEP3 部品化の俯瞰）</strong>
        </header>
        <table style={{ marginTop: 8 }}>
          <tbody>
            <tr>
              <td>イベント行</td>
              <td>
                <strong>{rows.length}</strong>
              </td>
            </tr>
            <tr>
              <td>購入系 / 売却系（action キーワード）</td>
              <td>
                <strong>
                  {buyCount} / {saleCount}
                </strong>
              </td>
            </tr>
            <tr>
              <td>価格合計（万円・行の合算）</td>
              <td>
                <strong>{priceSum ? `${Math.round(priceSum)} 万` : "—"}</strong>
              </td>
            </tr>
            <tr>
              <td>借入合計（万円・行の合算）</td>
              <td>
                <strong>{loanSum ? `${Math.round(loanSum)} 万` : "—"}</strong>
              </td>
            </tr>
            <tr>
              <td>目標接続</td>
              <td>
                CF 月50万 ·{" "}
                <a href="/realestate">運用レーンでギャップ確認 →</a>
              </td>
            </tr>
          </tbody>
        </table>
        <p className="meta" style={{ marginTop: 8 }}>
          神大家 STEP3: トップダウン・戸建売却で資金回復・フリー／運転は原資部品。カードローンは禁じ手。
        </p>
      </div>

      <div className="card">
        <header>
          <span className="lvl">Focus</span>
          <strong>今狙う物件（条件フォーカス）</strong>
        </header>
        <p className="meta" style={{ marginTop: 8 }}>
          Notion「物件買い進め条件」＋ Excel criteria。ここに合わない提案は断る（勝ち続けるプランニング）。
        </p>
        <ul className="meta" style={{ paddingLeft: 18, marginTop: 8 }}>
          {focusHints.map((h) => (
            <li key={h}>{h}</li>
          ))}
        </ul>
        {areas.length > 0 || rules.length > 0 ? (
          <div className="card-grid" style={{ marginTop: 12 }}>
            <div>
              <strong className="meta">エリア（Excel）</strong>
              <ul className="meta" style={{ paddingLeft: 18 }}>
                {areas.slice(0, 12).map((c, i) => (
                  <li key={i}>{c.raw_text}</li>
                ))}
              </ul>
            </div>
            <div>
              <strong className="meta">購入ルール（Excel）</strong>
              <ul className="meta" style={{ paddingLeft: 18 }}>
                {rules.slice(0, 12).map((c, i) => (
                  <li key={i}>{c.raw_text}</li>
                ))}
                {otherCrit.slice(0, 6).map((c, i) => (
                  <li key={`o-${i}`}>{c.raw_text}</li>
                ))}
              </ul>
            </div>
          </div>
        ) : null}
        <p style={{ marginTop: 12 }}>
          <a className="btn" href="/realestate/deals">
            この条件で千三つ（候補・内見）へ →
          </a>
        </p>
      </div>

      {(constraints || []).length > 0 ? (
        <div className="card">
          <header>
            <span className="lvl">銀行枠</span>
            <strong>プランニング制約</strong>
          </header>
          <table style={{ marginTop: 8 }}>
            <thead>
              <tr>
                <th>金融機関</th>
                <th>担保</th>
                <th>枠・条件</th>
                <th>金利・期間</th>
                <th>物件・地理</th>
              </tr>
            </thead>
            <tbody>
              {(constraints || []).map((c, i) => (
                <tr key={i}>
                  <td>{c.lender || "—"}</td>
                  <td className="meta">{c.collateral_type || "—"}</td>
                  <td className="meta">
                    {c.limit_note || c.attr_note || "—"}
                  </td>
                  <td className="meta">{c.rate_term || "—"}</td>
                  <td className="meta">
                    {[c.prop_cond, c.geo_cond].filter(Boolean).join(" / ") ||
                      "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}

      <div className="card">
        <header>
          <span className="lvl">Timeline</span>
          <strong>長期年表（購入・売却・調達）</strong>
        </header>
        <p className="meta" style={{ marginTop: 8 }}>
          STEP3 シートのイベント行。日付が無い行は「未定」。ライフプランの年次感で読む。
        </p>
        {years.length === 0 ? (
          <p className="meta" style={{ marginTop: 8 }}>
            イベントがありません。Excel 再取込を実行してください。
          </p>
        ) : (
          years.map((y) => (
            <div key={y} style={{ marginTop: 16 }}>
              <h2 style={{ fontSize: 16, margin: "0 0 8px" }}>{y}年</h2>
              <table>
                <thead>
                  <tr>
                    <th>日付</th>
                    <th>種別</th>
                    <th>名義</th>
                    <th>物件・場所</th>
                    <th className="num">価格万</th>
                    <th className="num">利回</th>
                    <th>銀行</th>
                    <th className="num">借入万</th>
                  </tr>
                </thead>
                <tbody>
                  {(byYear.get(y) || []).map((e) => {
                    const act = buyPlanActionView(e.action);
                    return (
                    <tr key={`${y}-${e.row_no}`}>
                      <td className="meta">
                        {e.event_date ? e.event_date.slice(0, 10) : "—"}
                      </td>
                      <td>
                        <span
                          title={e.action || ""}
                          style={{
                            display: "inline-block",
                            padding: "2px 8px",
                            borderRadius: 4,
                            fontSize: 12,
                            background: act.bg,
                            color: act.fg,
                            fontWeight: 600,
                          }}
                        >
                          {act.label}
                        </span>
                      </td>
                      <td className="meta">{e.entity || "—"}</td>
                      <td>
                        {e.property_name || e.location || "—"}
                        {e.structure ? (
                          <span className="meta"> · {e.structure}</span>
                        ) : null}
                      </td>
                      <td className="num meta">
                        {n(e.price_man) != null ? n(e.price_man) : "—"}
                      </td>
                      <td className="num meta">
                        {n(e.yield_pct) != null
                          ? `${n(e.yield_pct)}%`
                          : "—"}
                      </td>
                      <td className="meta">{e.bank || "—"}</td>
                      <td className="num meta">
                        {n(e.loan_man) != null ? n(e.loan_man) : "—"}
                      </td>
                    </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          ))
        )}
      </div>
    </Shell>
  );
}
