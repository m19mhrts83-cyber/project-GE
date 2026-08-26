import Shell from "@/components/Shell";
import EnqueueJobButton from "@/components/EnqueueJobButton";
import RealEstateLaneNav from "@/components/RealEstateLaneNav";
import { createClient } from "@/lib/supabase/server";
import {
  ALIVE_STATUS_LABEL,
  VENDOR_STATUS_LABEL,
  vendorAliveEffective,
  vendorAliveOk,
  vendorNeedsFollowUp,
} from "@/lib/rePipelineUi";
import Link from "next/link";

export const dynamic = "force-dynamic";

const FILTERS: { id: string; label: string }[] = [
  { id: "alive", label: "すぐ連絡可" },
  { id: "followup", label: "要フォロー" },
  { id: "all", label: "すべて" },
  { id: "pending", label: "候補" },
  { id: "contacted", label: "連絡済" },
  { id: "excluded", label: "除外" },
];

function chipStyle(status: string): Record<string, string | number> {
  const base: Record<string, string | number> = {
    display: "inline-block",
    padding: "2px 8px",
    borderRadius: 4,
    fontSize: 12,
    border: "1px solid var(--border, #ccc)",
  };
  if (status === "replied" || status === "ok")
    return { ...base, background: "#ecfdf5" };
  if (status === "contacted") return { ...base, background: "#eff6ff" };
  if (status === "fail" || status === "stale")
    return { ...base, background: "#fff7ed" };
  return base;
}

export default async function RepairVendorsPage({
  searchParams,
}: {
  searchParams?: Promise<{ filter?: string; trade?: string }>;
}) {
  const sp = (await searchParams) || {};
  const filter = (sp.filter || "alive").trim();
  const trade = (sp.trade || "").trim();

  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();

  const { data: vendors, error } = await supabase
    .from("kurashift_re_repair_vendors")
    .select("*")
    .order("updated_at", { ascending: false })
    .limit(500);

  let rows = [...(vendors || [])];
  if (trade) {
    rows = rows.filter((v) => (v.trade || "") === trade);
  }
  if (filter === "pending") {
    rows = rows.filter((v) =>
      ["pending", "discovered"].includes(v.status || "")
    );
  } else if (filter === "contacted") {
    rows = rows.filter((v) => v.status === "contacted");
  } else if (filter === "excluded") {
    rows = rows.filter((v) => ["skip", "invalid"].includes(v.status || ""));
  } else if (filter === "alive") {
    rows = rows.filter((v) => vendorAliveOk(v));
  } else if (filter === "followup") {
    rows = rows.filter((v) => vendorNeedsFollowUp(v));
  }

  // alive_ok を先頭
  rows.sort((a, b) => {
    const ao = vendorAliveOk(a) ? 0 : 1;
    const bo = vendorAliveOk(b) ? 0 : 1;
    if (ao !== bo) return ao - bo;
    return String(a.name || "").localeCompare(String(b.name || ""), "ja");
  });

  const counts: Record<string, number> = {};
  let aliveOk = 0;
  const trades = new Set<string>();
  for (const v of vendors || []) {
    const st = v.status || "pending";
    counts[st] = (counts[st] || 0) + 1;
    if (vendorAliveOk(v)) aliveOk += 1;
    if (v.trade) trades.add(String(v.trade));
  }

  let latestSync: string | null = null;
  for (const v of vendors || []) {
    const s = v.synced_at as string | undefined;
    if (s && (!latestSync || s > latestSync)) latestSync = s;
  }

  return (
    <Shell active="/realestate" email={user?.email ?? null}>
      <RealEstateLaneNav active="b-repair" />
      <p className="page-kicker">③-B開 · 修繕業者</p>
      <h1>修繕業者（S4）</h1>
      <p className="sub">
        正本は Mac の <code>kurashift_repair_vendor_list.yaml</code>。修繕依頼は{" "}
        <strong>生存OK（90日以内）</strong> を先頭に表示します。
      </p>

      <div className="card">
        <header>
          <span className="lvl">Summary</span>
          <strong>件数</strong>
        </header>
        <p className="meta" style={{ marginTop: 8 }}>
          候補 {counts.pending || 0}+{counts.discovered || 0} · 連絡済{" "}
          {counts.contacted || 0} · 生存OK {aliveOk}
        </p>
        <p className="meta">
          最終同期{" "}
          {latestSync
            ? latestSync.slice(0, 16).replace("T", " ")
            : "—（未同期）"}
        </p>
        <p style={{ marginTop: 10 }}>
          <EnqueueJobButton
            jobType="re_repair_vendor_sync"
            title="修繕業者リストを Supabase へ投影"
            label="リストを同期"
            payload={{}}
          />
        </p>
      </div>

      <div
        style={{
          display: "flex",
          flexWrap: "wrap",
          gap: 8,
          marginBottom: 12,
        }}
      >
        {FILTERS.map((f) => {
          const on = filter === f.id;
          const href = trade
            ? `/realestate/repair-vendors?filter=${f.id}&trade=${encodeURIComponent(trade)}`
            : `/realestate/repair-vendors?filter=${f.id}`;
          return (
            <Link
              key={f.id}
              href={href}
              className={on ? "btn" : undefined}
              style={
                on
                  ? undefined
                  : {
                      padding: "4px 10px",
                      border: "1px solid var(--border, #ccc)",
                      borderRadius: 6,
                      textDecoration: "none",
                      fontSize: 13,
                    }
              }
            >
              {f.label}
            </Link>
          );
        })}
      </div>

      {trades.size > 0 ? (
        <div
          style={{
            display: "flex",
            flexWrap: "wrap",
            gap: 6,
            marginBottom: 16,
          }}
        >
          <Link
            href={`/realestate/repair-vendors?filter=${filter}`}
            className={!trade ? "btn" : undefined}
            style={
              !trade
                ? undefined
                : {
                    padding: "2px 8px",
                    border: "1px solid var(--border, #ccc)",
                    borderRadius: 4,
                    textDecoration: "none",
                    fontSize: 12,
                  }
            }
          >
            全職種
          </Link>
          {[...trades].sort().map((t) => (
            <Link
              key={t}
              href={`/realestate/repair-vendors?filter=${filter}&trade=${encodeURIComponent(t)}`}
              className={trade === t ? "btn" : undefined}
              style={
                trade === t
                  ? undefined
                  : {
                      padding: "2px 8px",
                      border: "1px solid var(--border, #ccc)",
                      borderRadius: 4,
                      textDecoration: "none",
                      fontSize: 12,
                    }
              }
            >
              {t}
            </Link>
          ))}
        </div>
      ) : null}

      <div className="card">
        <header>
          <span className="lvl">Repair</span>
          <strong>一覧（{rows.length} 件）</strong>
        </header>
        {error ? (
          <p className="meta" style={{ color: "var(--danger, #b45309)" }}>
            {error.message} — migration 未適用の可能性があります
          </p>
        ) : rows.length === 0 ? (
          <p className="meta" style={{ marginTop: 8 }}>
            {filter === "alive"
              ? "生存OK の業者がいません。電話キュー／Web チェック後に同期してください"
              : "YAML 未取込 or 未同期"}
          </p>
        ) : (
          <div style={{ overflowX: "auto" }}>
            <table>
              <thead>
                <tr>
                  <th>生存</th>
                  <th>状態</th>
                  <th>業者名</th>
                  <th>職種</th>
                  <th>エリア</th>
                  <th>電話</th>
                  <th>備考</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((v) => {
                  const alive = vendorAliveEffective(v);
                  return (
                    <tr key={v.id}>
                      <td>
                        <span style={chipStyle(alive)}>
                          {ALIVE_STATUS_LABEL[alive] || alive}
                        </span>
                      </td>
                      <td>
                        <span style={chipStyle(v.status || "pending")}>
                          {VENDOR_STATUS_LABEL[v.status || "pending"] ||
                            v.status}
                        </span>
                      </td>
                      <td>{v.name}</td>
                      <td className="meta">{v.trade || "—"}</td>
                      <td className="meta">{v.area || "—"}</td>
                      <td className="meta">{v.phone || "—"}</td>
                      <td className="meta">
                        {(v.notes || v.alive_note || "—").slice(0, 48)}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </Shell>
  );
}
