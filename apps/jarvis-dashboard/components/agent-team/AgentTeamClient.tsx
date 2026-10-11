"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import {
  flowforgeOpenLabel,
  flowforgeOpenUrl,
  mixupKindLabel,
  reportLabel,
  sortAgents,
  statusClass,
  type AgentTeamAgent,
  type AgentTeamDept,
  type GrokPayload,
} from "@/lib/agentTeam";

const STATUS_FILTERS = ["すべて", "運用確認", "設計中", "運用", "候補", "停止"] as const;
type Tab = "ai" | "grok" | "map";

type Props = {
  departments: AgentTeamDept[];
  agents: AgentTeamAgent[];
  counts: Record<string, number>;
  updated: string;
  flowforgeNote: string;
  builderUrl: string;
  builderTitle: string;
  grok: GrokPayload;
};

export default function AgentTeamClient({
  departments,
  agents,
  counts,
  updated,
  flowforgeNote,
  builderUrl,
  builderTitle,
  grok,
}: Props) {
  const [tab, setTab] = useState<Tab>("ai");
  const [statusFilter, setStatusFilter] = useState<string>("すべて");
  const [deptFilter, setDeptFilter] = useState<string>("すべて");
  const [grokDeptFilter, setGrokDeptFilter] = useState<string>("すべて");

  const filtered = useMemo(() => {
    let list = agents;
    if (statusFilter !== "すべて") {
      list = list.filter((a) => a.status === statusFilter);
    }
    if (deptFilter !== "すべて") {
      list = list.filter((a) => a.department_id === deptFilter);
    }
    return sortAgents(list);
  }, [agents, statusFilter, deptFilter]);

  const byDept = useMemo(() => {
    const map = new Map<string, AgentTeamAgent[]>();
    for (const d of departments) map.set(d.id, []);
    for (const a of sortAgents(agents)) {
      const arr = map.get(a.department_id) || [];
      arr.push(a);
      map.set(a.department_id, arr);
    }
    return map;
  }, [agents, departments]);

  const grokBotsFiltered = useMemo(() => {
    if (grokDeptFilter === "すべて") return grok.bots;
    return grok.bots.filter((b) => b.department_id === grokDeptFilter);
  }, [grok.bots, grokDeptFilter]);

  const grokByDept = useMemo(() => {
    const map = new Map<string, typeof grok.bots>();
    for (const d of grok.departments) map.set(d.id, []);
    for (const b of grok.bots) {
      const arr = map.get(b.department_id) || [];
      arr.push(b);
      map.set(b.department_id, arr);
    }
    return map;
  }, [grok.bots, grok.departments]);

  return (
    <>
      <p className="sub">
        AIエージェントチーム（FlowForge）と Grok Bot の俯瞰です。作り込みは{" "}
        <strong>Cursor インブラウザの FlowForge</strong>、Grok の作業は Bot
        チャンネルで行います。
      </p>
      <p className="meta" style={{ marginBottom: 12 }}>
        最終同期: {updated}
        {" · "}
        <a href={builderUrl} target="_blank" rel="noopener noreferrer">
          {builderTitle || "ビルダー"} ↗
        </a>
        {grok.updated ? ` · Grok正本: ${grok.updated}` : null}
      </p>

      <div className="at-tabs" role="tablist" aria-label="俯瞰ビュー">
        {(
          [
            ["ai", "AIエージェントチーム", agents.length],
            ["grok", "Grok Bot", grok.bots.length],
            ["map", "対応表", grok.mappings.length],
          ] as const
        ).map(([id, label, n]) => (
          <button
            key={id}
            type="button"
            role="tab"
            aria-selected={tab === id}
            className={`at-tab ${tab === id ? "is-on" : ""}`}
            onClick={() => setTab(id)}
          >
            {label}
            <span className="at-tab-n">{n}</span>
          </button>
        ))}
      </div>

      {tab === "ai" ? (
        <>
          <div className="at-counts" aria-label="状態別件数">
            {(
              [
                ["運用確認", counts["運用確認"] ?? 0],
                ["設計中", counts["設計中"] ?? 0],
                ["運用", counts["運用"] ?? 0],
                ["候補", counts["候補"] ?? 0],
                ["停止", counts["停止"] ?? 0],
              ] as const
            ).map(([label, n]) => (
              <button
                key={label}
                type="button"
                className={`at-count ${statusFilter === label ? "is-on" : ""}`}
                onClick={() =>
                  setStatusFilter(statusFilter === label ? "すべて" : label)
                }
              >
                <span className={statusClass(label)}>{label}</span>
                <strong>{n}</strong>
              </button>
            ))}
          </div>

          <p className="at-hint">{flowforgeNote}</p>

          <section className="home-section">
            <div className="home-section-head">
              <h2 style={{ fontSize: "1.08rem", margin: 0 }}>組織図（8室）</h2>
            </div>
            <div className="at-org">
              {departments.map((d) => {
                const list = byDept.get(d.id) || [];
                return (
                  <div key={d.id} className="at-org-col">
                    <h3>
                      <span className="at-org-id">{d.id}</span>
                      {d.name}
                      <span className="at-org-n">{list.length}</span>
                    </h3>
                    <ul>
                      {list.map((a) => (
                        <li key={a.id}>
                          <Link href={`/agent-team/${a.id}`}>
                            <span
                              className={statusClass(a.status)}
                              title={a.status}
                            >
                              {a.status_icon}
                            </span>
                            <span className="at-org-name">
                              {a.id} {a.name}
                            </span>
                          </Link>
                        </li>
                      ))}
                    </ul>
                  </div>
                );
              })}
            </div>
          </section>

          <section className="home-section">
            <div className="home-section-head">
              <h2 style={{ fontSize: "1.08rem", margin: 0 }}>一覧</h2>
              <span className="meta">{filtered.length}件</span>
            </div>
            <div className="at-filters">
              <label>
                状態{" "}
                <select
                  value={statusFilter}
                  onChange={(e) => setStatusFilter(e.target.value)}
                >
                  {STATUS_FILTERS.map((s) => (
                    <option key={s} value={s}>
                      {s}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                部門{" "}
                <select
                  value={deptFilter}
                  onChange={(e) => setDeptFilter(e.target.value)}
                >
                  <option value="すべて">すべて</option>
                  {departments.map((d) => (
                    <option key={d.id} value={d.id}>
                      {d.id} {d.name}
                    </option>
                  ))}
                </select>
              </label>
            </div>
            <div className="at-table-wrap">
              <table className="at-table">
                <thead>
                  <tr>
                    <th>ID</th>
                    <th>名前</th>
                    <th>部門</th>
                    <th>状態</th>
                    <th>合図</th>
                    <th>報告</th>
                    <th>ツール</th>
                    <th>Grok</th>
                    <th>フロー</th>
                  </tr>
                </thead>
                <tbody>
                  {filtered.map((a) => (
                    <tr key={a.id}>
                      <td>
                        <Link href={`/agent-team/${a.id}`}>{a.id}</Link>
                      </td>
                      <td>
                        <Link href={`/agent-team/${a.id}`}>
                          {a.name}
                          {a.builder_tag ? (
                            <span className="at-tag">{a.builder_tag}</span>
                          ) : null}
                        </Link>
                      </td>
                      <td className="meta">
                        {a.department_id} {a.department_name}
                      </td>
                      <td>
                        <span className={statusClass(a.status)}>
                          {a.status_icon} {a.status}
                        </span>
                      </td>
                      <td className="meta">{a.schedule || a.trigger || "—"}</td>
                      <td className="meta">{reportLabel(a.report)}</td>
                      <td className="meta">{a.tool_assigned || "—"}</td>
                      <td className="meta">
                        {a.builder_tag || a.grok_counterpart || "—"}
                      </td>
                  <td>
                    {flowforgeOpenUrl(a) ? (
                      <a
                        href={flowforgeOpenUrl(a)}
                        target="_blank"
                        rel="noopener noreferrer"
                        title={
                          a.flowforge_share_url
                            ? "閲覧専用（外部ブラウザOK）"
                            : "編集は m19m。同期失敗なら詳細の案内を見て"
                        }
                      >
                        {flowforgeOpenLabel(a)} ↗
                      </a>
                    ) : (
                      "—"
                    )}
                  </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        </>
      ) : null}

      {tab === "grok" ? (
        <>
          <p className="at-hint">{grok.note}</p>

          {grok.pillars.length ? (
            <section className="home-section">
              <div className="home-section-head">
                <h2 style={{ fontSize: "1.08rem", margin: 0 }}>AI三柱</h2>
              </div>
              <div className="at-pillars">
                {grok.pillars.map((p) => (
                  <div key={p.id} className="at-pillar">
                    <strong>{p.name}</strong>
                    <span className="meta">{p.role}</span>
                    {p.note ? <span className="meta">{p.note}</span> : null}
                  </div>
                ))}
              </div>
            </section>
          ) : null}

          <section className="home-section">
            <div className="home-section-head">
              <h2 style={{ fontSize: "1.08rem", margin: 0 }}>
                Grok 組織図（{grok.departments.length}部署）
              </h2>
            </div>
            <div className="at-org">
              {grok.departments.map((d) => {
                const list = grokByDept.get(d.id) || [];
                return (
                  <div key={d.id} className="at-org-col">
                    <h3>
                      {d.name}
                      <span className="at-org-n">{list.length}</span>
                    </h3>
                    <p className="at-org-meta meta">
                      {d.exec_level || d.channel || ""}
                    </p>
                    <ul>
                      {list.map((b) => (
                        <li key={b.id}>
                          <span className="at-org-name">
                            {b.code && b.code !== "—" ? `${b.code} ` : ""}
                            {b.name}
                          </span>
                          <span className="meta at-org-work">{b.work}</span>
                        </li>
                      ))}
                    </ul>
                  </div>
                );
              })}
            </div>
          </section>

          <section className="home-section">
            <div className="home-section-head">
              <h2 style={{ fontSize: "1.08rem", margin: 0 }}>社員一覧</h2>
              <span className="meta">{grokBotsFiltered.length}件</span>
            </div>
            <div className="at-filters">
              <label>
                部署{" "}
                <select
                  value={grokDeptFilter}
                  onChange={(e) => setGrokDeptFilter(e.target.value)}
                >
                  <option value="すべて">すべて</option>
                  {grok.departments.map((d) => (
                    <option key={d.id} value={d.id}>
                      {d.name}（{d.bot_count}）
                    </option>
                  ))}
                </select>
              </label>
            </div>
            <div className="at-table-wrap">
              <table className="at-table">
                <thead>
                  <tr>
                    <th>コード</th>
                    <th>名前</th>
                    <th>部署</th>
                    <th>種別</th>
                    <th>実施内容</th>
                    <th>スケジュール</th>
                    <th>Drive</th>
                  </tr>
                </thead>
                <tbody>
                  {grokBotsFiltered.map((b) => (
                    <tr key={b.id}>
                      <td className="meta">{b.code || "—"}</td>
                      <td>
                        <strong>{b.name}</strong>
                      </td>
                      <td className="meta">{b.department_name}</td>
                      <td className="meta">{b.kind || "—"}</td>
                      <td>{b.work || "—"}</td>
                      <td className="meta">{b.schedule || "—"}</td>
                      <td className="meta">{b.drive_target || "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        </>
      ) : null}

      {tab === "map" ? (
        <>
          <p className="at-hint">
            同じ仕事系統の対応です。〔Grok:◯◯〕は置き換えではなく
            <strong> 並べて比較する相手</strong>。ミックスレーンは比較する側。
            {grok.mixup_doc ? ` 詳細: ${grok.mixup_doc}` : null}
          </p>
          <section className="home-section">
            <div className="home-section-head">
              <h2 style={{ fontSize: "1.08rem", margin: 0 }}>
                AIエージェントチーム ↔ Grok Bot
              </h2>
              <span className="meta">{grok.mappings.length}行</span>
            </div>
            <div className="at-table-wrap">
              <table className="at-table">
                <thead>
                  <tr>
                    <th>AI社員</th>
                    <th>印</th>
                    <th>種別</th>
                    <th>対応 Grok</th>
                    <th>役割分担</th>
                  </tr>
                </thead>
                <tbody>
                  {grok.mappings.map((m) => (
                    <tr key={m.agent_id}>
                      <td>
                        <Link href={`/agent-team/${m.agent_id}`}>
                          {m.agent_id} {m.agent_name}
                        </Link>
                      </td>
                      <td>
                        {m.builder_tag ? (
                          <span className="at-tag">{m.builder_tag}</span>
                        ) : (
                          "—"
                        )}
                      </td>
                      <td className="meta">{mixupKindLabel(m.mixup_kind)}</td>
                      <td>
                        {m.mixup_kind === "lane" ? (
                          <span className="meta">全Grok／比較レーン</span>
                        ) : m.grok_labels.length ? (
                          m.grok_labels.join(" · ")
                        ) : (
                          "—"
                        )}
                      </td>
                      <td className="meta">{m.role_split || "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        </>
      ) : null}
    </>
  );
}
