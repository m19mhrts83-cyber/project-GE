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
  { id: "followup", label: "要フォロー" },
  { id: "alive", label: "生存OK" },
  { id: "all", label: "すべて" },
  { id: "pending", label: "未送信" },
  { id: "contacted", label: "送信済" },
  { id: "replied", label: "返信あり" },
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
  if (status === "replied") return { ...base, background: "#ecfdf5" };
  if (status === "contacted") return { ...base, background: "#eff6ff" };
  if (status === "ok") return { ...base, background: "#ecfdf5" };
  if (status === "fail" || status === "stale")
    return { ...base, background: "#fff7ed" };
  return base;
}

export default async function MgmtVendorsPage({
  searchParams,
}: {
  searchParams?: Promise<{ filter?: string }>;
}) {
  const sp = (await searchParams) || {};
  const filter = (sp.filter || "followup").trim();

  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();

  const { data: vendors, error } = await supabase
    .from("kurashift_re_mgmt_vendors")
    .select("*")
    .order("contacted_at", { ascending: false, nullsFirst: false })
    .order("updated_at", { ascending: false })
    .limit(500);

  let rows = vendors || [];
  if (filter === "pending") {
    rows = rows.filter((v) =>
      ["pending", "discovered"].includes(v.status || "")
    );
  } else if (filter === "contacted") {
    rows = rows.filter((v) => v.status === "contacted");
  } else if (filter === "replied") {
    rows = rows.filter((v) => v.status === "replied");
  } else if (filter === "excluded") {
    rows = rows.filter((v) => ["skip", "invalid"].includes(v.status || ""));
  } else if (filter === "alive") {
    rows = rows.filter((v) => vendorAliveOk(v));
  } else if (filter === "followup") {
    rows = rows.filter((v) => vendorNeedsFollowUp(v));
  }

  const counts: Record<string, number> = {};
  let aliveOk = 0;
  for (const v of vendors || []) {
    const st = v.status || "pending";
    counts[st] = (counts[st] || 0) + 1;
    if (vendorAliveOk(v)) aliveOk += 1;
  }

  let latestSync: string | null = null;
  for (const v of vendors || []) {
    const s = v.synced_at as string | undefined;
    if (s && (!latestSync || s > latestSync)) latestSync = s;
  }

  return (
    <Shell active="/realestate" email={user?.email ?? null}>
      <RealEstateLaneNav active="b-mgmt" />
      <p className="page-kicker">③-B開 · 管理会社</p>
      <h1>管理会社開拓（S9）</h1>
      <p className="sub">
        正本は Mac の <code>kurashift_mgmt_vendor_list.yaml</code>（Excel{" "}
        <code>★管理会社一覧.xlsx</code> からの投影）。空室一括送信の Excel
        は別経路のまま。
      </p>

      <div className="card">
        <header>
          <span className="lvl">Summary</span>
          <strong>件数</strong>
        </header>
        <p className="meta" style={{ marginTop: 8 }}>
          未送信 {counts.pending || 0} · 送信済 {counts.contacted || 0} · 返信{" "}
          {counts.replied || 0} · スキップ {counts.skip || 0} · 生存OK {aliveOk}
        </p>
        <p className="meta">
          最終同期{" "}
          {latestSync
            ? latestSync.slice(0, 16).replace("T", " ")
            : "—（未同期）"}
        </p>
        <p style={{ marginTop: 10 }}>
          <EnqueueJobButton
            jobType="re_mgmt_vendor_sync"
            title="管理会社リストを Supabase へ投影"
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
          marginBottom: 16,
        }}
      >
        {FILTERS.map((f) => {
          const on = filter === f.id;
          return (
            <Link
              key={f.id}
              href={`/realestate/mgmt-vendors?filter=${f.id}`}
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

      <div className="card">
        <header>
          <span className="lvl">Mgmt</span>
          <strong>一覧（{rows.length} 件）</strong>
        </header>
        {error ? (
          <p className="meta" style={{ color: "var(--danger, #b45309)" }}>
            {error.message} — migration 未適用の可能性があります
          </p>
        ) : rows.length === 0 ? (
          <p className="meta" style={{ marginTop: 8 }}>
            YAML 未取込 or 未同期 → Mac で{" "}
            <code>--import-xlsx</code> 後「リストを同期」
          </p>
        ) : (
          <div style={{ overflowX: "auto" }}>
            <table>
              <thead>
                <tr>
                  <th>状態</th>
                  <th>生存</th>
                  <th>会社名</th>
                  <th>エリア</th>
                  <th>URL</th>
                  <th>送信日</th>
                  <th>備考</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((v) => {
                  const alive = vendorAliveEffective(v);
                  return (
                    <tr key={v.id}>
                      <td>
                        <span style={chipStyle(v.status || "pending")}>
                          {VENDOR_STATUS_LABEL[v.status || "pending"] ||
                            v.status}
                        </span>
                      </td>
                      <td>
                        <span style={chipStyle(alive)}>
                          {ALIVE_STATUS_LABEL[alive] || alive}
                        </span>
                      </td>
                      <td>{v.name}</td>
                      <td className="meta">
                        {[v.prefecture, v.city, v.station]
                          .filter(Boolean)
                          .join(" ") ||
                          v.area ||
                          "—"}
                      </td>
                      <td className="meta">
                        {v.url ? (
                          <a href={v.url} target="_blank" rel="noreferrer">
                            ↗
                          </a>
                        ) : (
                          "—"
                        )}
                      </td>
                      <td className="meta">{v.contacted_at || "—"}</td>
                      <td className="meta">
                        {(v.notes || v.last_result || "—").slice(0, 48)}
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
