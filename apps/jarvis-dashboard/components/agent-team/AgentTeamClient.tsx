"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import {
  reportLabel,
  sortAgents,
  statusClass,
  type AgentTeamAgent,
  type AgentTeamDept,
} from "@/lib/agentTeam";

const STATUS_FILTERS = ["すべて", "運用確認", "設計中", "運用", "候補", "停止"] as const;

type Props = {
  departments: AgentTeamDept[];
  agents: AgentTeamAgent[];
  counts: Record<string, number>;
  updated: string;
  flowforgeNote: string;
  builderUrl: string;
  builderTitle: string;
};

export default function AgentTeamClient({
  departments,
  agents,
  counts,
  updated,
  flowforgeNote,
  builderUrl,
  builderTitle,
}: Props) {
  const [statusFilter, setStatusFilter] = useState<string>("すべて");
  const [deptFilter, setDeptFilter] = useState<string>("すべて");

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

  return (
    <>
      <p className="sub">
        作成状況の俯瞰です。作業フローの作り込み・拡大・要素詳細は{" "}
        <strong>Cursor インブラウザの FlowForge</strong>（AIオートメーション）で行います。
      </p>
      <p className="meta" style={{ marginBottom: 16 }}>
        最終同期: {updated}
        {" · "}
        <a href={builderUrl} target="_blank" rel="noopener noreferrer">
          {builderTitle || "ビルダー"} ↗
        </a>
      </p>

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
                        <span className={statusClass(a.status)} title={a.status}>
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
                  <td>
                    {a.flowforge_url ? (
                      <a
                        href={a.flowforge_url}
                        target="_blank"
                        rel="noopener noreferrer"
                        title="Cursorインブラウザ推奨"
                      >
                        開く ↗
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
  );
}
