"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import {
  flowforgeOpenLabel,
  flowforgeOpenUrl,
  mappingSideLabel,
  mixupKindLabel,
  reportLabel,
  sortAgents,
  statusClass,
  type AgentTeamAgent,
  type AgentTeamDept,
  type AgentTeamGenre,
  type GrokPayload,
} from "@/lib/agentTeam";

const STATUS_FILTERS = ["すべて", "運用確認", "設計中", "運用", "候補", "停止"] as const;
type Tab = "genre" | "ai" | "grok" | "map";

/** AI社員の状態シグナル（色・印）— docs/AIエージェントチーム/22_運用状態の識別 */
const STATUS_LEGEND = [
  { status: "運用確認", icon: "🟡", meaning: "定時が動いている仕上げ中" },
  { status: "設計中", icon: "🔵", meaning: "FlowForge／実装着手〜" },
  { status: "運用", icon: "🟢", meaning: "意図OK済みの定常運用" },
  { status: "候補", icon: "⚪", meaning: "指示書スタブのみ（未着手）" },
  { status: "停止", icon: "⛔", meaning: "止めている" },
] as const;

type Props = {
  departments: AgentTeamDept[];
  agents: AgentTeamAgent[];
  genres: AgentTeamGenre[];
  genreNote?: string;
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
  genres,
  genreNote,
  counts,
  updated,
  flowforgeNote,
  builderUrl,
  builderTitle,
  grok,
}: Props) {
  const [tab, setTab] = useState<Tab>("genre");
  const [genreFilter, setGenreFilter] = useState<string>("すべて");
  const [statusFilter, setStatusFilter] = useState<string>("すべて");
  const [deptFilter, setDeptFilter] = useState<string>("すべて");
  const [grokDeptFilter, setGrokDeptFilter] = useState<string>("すべて");
  const [mapFilter, setMapFilter] = useState<string>("すべて");

  const agentsById = useMemo(() => {
    const m = new Map<string, AgentTeamAgent>();
    for (const a of agents) m.set(a.id, a);
    return m;
  }, [agents]);

  const botsById = useMemo(() => {
    const m = new Map<string, (typeof grok.bots)[0]>();
    for (const b of grok.bots) m.set(b.id, b);
    return m;
  }, [grok.bots]);

  const filtered = useMemo(() => {
    let list = agents;
    if (statusFilter !== "すべて") {
      list = list.filter((a) => a.status === statusFilter);
    }
    if (deptFilter !== "すべて") {
      list = list.filter((a) => a.department_id === deptFilter);
    }
    if (genreFilter !== "すべて" && tab === "ai") {
      list = list.filter((a) => a.genre_id === genreFilter);
    }
    return sortAgents(list);
  }, [agents, statusFilter, deptFilter, genreFilter, tab]);

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
    let list = grok.bots;
    if (grokDeptFilter !== "すべて") {
      list = list.filter((b) => b.department_id === grokDeptFilter);
    }
    if (genreFilter !== "すべて" && tab === "grok") {
      list = list.filter((b) => b.genre_id === genreFilter);
    }
    return list;
  }, [grok.bots, grokDeptFilter, genreFilter, tab]);

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

  const mapCounts = grok.mapping_counts || {
    paired: 0,
    ai_only: 0,
    grok_only: 0,
    all: grok.mappings.length,
  };

  const mappingsFiltered = useMemo(() => {
    if (mapFilter === "すべて") return grok.mappings;
    if (mapFilter === "対応あり") {
      return grok.mappings.filter((m) => m.side === "paired");
    }
    if (mapFilter === "AIのみ") {
      return grok.mappings.filter((m) => m.side === "ai_only");
    }
    if (mapFilter === "Grokのみ") {
      return grok.mappings.filter((m) => m.side === "grok_only");
    }
    return grok.mappings;
  }, [grok.mappings, mapFilter]);

  const genresShown = useMemo(() => {
    if (genreFilter === "すべて") return genres;
    return genres.filter((g) => g.id === genreFilter);
  }, [genres, genreFilter]);

  return (
    <>
      <p className="sub">
        上位ジャンルで Grok Bot 組織と AIエージェントチームを横並びで俯瞰します。作り込みは{" "}
        <strong>Cursor インブラウザの FlowForge</strong>、Grok の作業は Bot
        チャンネルで行います。
      </p>
      <p className="meta" style={{ marginBottom: 12 }}>
        最終同期: {updated}
        {" · "}
        <a href={builderUrl} target="_blank" rel="noopener noreferrer">
          ビルダー参考: {builderTitle || "物件と連絡の見守り隊"} ↗
        </a>
        {" · "}
        <span title="組織図の正は agents_registry → 本画面。ビルダー共有は編成の参考（localStorage依存）">
          組織図正＝registry
        </span>
        {grok.updated ? ` · Grok正本: ${grok.updated}` : null}
      </p>

      <div className="at-tabs" role="tablist" aria-label="俯瞰ビュー">
        {(
          [
            ["genre", "ジャンル", genres.length],
            ["ai", "AIエージェントチーム", agents.length],
            ["grok", "Grok Bot", grok.bots.length],
            ["map", "対応表", grok.mapping_counts?.all ?? grok.mappings.length],
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

      <p className="at-legend" aria-label="AI社員ステータスの凡例">
        <span className="at-legend-title">状態シグナル</span>
        {STATUS_LEGEND.map((row) => (
          <span key={row.status} className="at-legend-item" title={row.meaning}>
            <span className={statusClass(row.status)} aria-hidden>
              {row.icon}
            </span>
            <span className={statusClass(row.status)}>{row.status}</span>
            <span className="at-legend-mean">{row.meaning}</span>
          </span>
        ))}
      </p>

      {tab === "genre" ? (
        <>
          {genreNote ? <p className="at-hint">{genreNote}</p> : null}
          <div className="at-filters" style={{ marginBottom: 14 }}>
            <label>
              ジャンル{" "}
              <select
                value={genreFilter}
                onChange={(e) => setGenreFilter(e.target.value)}
              >
                <option value="すべて">すべて</option>
                {genres.map((g) => (
                  <option key={g.id} value={g.id}>
                    {g.name}（AI {g.counts.ai} / Grok {g.counts.grok}）
                  </option>
                ))}
              </select>
            </label>
          </div>

          <div className="at-genres">
            {genresShown.map((g) => {
              const aiList = sortAgents(
                g.ai_agent_ids
                  .map((id) => agentsById.get(id))
                  .filter(Boolean) as AgentTeamAgent[],
              );
              const grokList = g.grok_bot_ids
                .map((id) => botsById.get(id))
                .filter(Boolean) as typeof grok.bots;
              const aiRooms = departments.filter((d) =>
                g.ai_department_ids.includes(d.id),
              );
              const grokDepts = grok.departments.filter((d) =>
                g.grok_department_ids.includes(d.id),
              );
              return (
                <section key={g.id} className="at-genre-card" id={`genre-${g.id}`}>
                  <header className="at-genre-head">
                    <div>
                      <h2>{g.name}</h2>
                      <p className="meta">{g.summary}</p>
                    </div>
                    <div className="at-genre-stats" aria-label="件数">
                      <span>
                        AI <strong>{g.counts.ai}</strong>
                      </span>
                      <span>
                        Grok <strong>{g.counts.grok}</strong>
                      </span>
                      <span>
                        対応 <strong>{g.counts.paired}</strong>
                      </span>
                      <span className="meta">
                        AIのみ {g.counts.ai_only} · Grokのみ {g.counts.grok_only}
                      </span>
                    </div>
                  </header>

                  <div className="at-genre-leaders">
                    <div>
                      <span className="at-genre-leader-label">Grok リーダー</span>
                      <strong>{g.leaders.grok || "—"}</strong>
                    </div>
                    <div>
                      <span className="at-genre-leader-label">AI 側</span>
                      <strong>{g.leaders.ai || "—"}</strong>
                    </div>
                  </div>

                  {g.nav_hints?.length ? (
                    <p className="at-genre-nav meta">
                      ナビ目安: {g.nav_hints.join(" · ")}
                    </p>
                  ) : null}

                  <div className="at-genre-cols">
                    <div className="at-genre-col">
                      <h3>
                        AIエージェントチーム
                        <span className="at-org-n">{aiList.length}</span>
                      </h3>
                      {aiRooms.length ? (
                        <p className="meta at-genre-sub">
                          室:{" "}
                          {aiRooms
                            .map((d) => `${d.id} ${d.name}`)
                            .join(" · ")}
                        </p>
                      ) : null}
                      <ul>
                        {aiList.map((a) => (
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
                        {!aiList.length ? (
                          <li className="meta">AI社員なし</li>
                        ) : null}
                      </ul>
                    </div>
                    <div className="at-genre-col">
                      <h3>
                        Grok Bot
                        <span className="at-org-n">{grokList.length}</span>
                      </h3>
                      {grokDepts.length ? (
                        <p className="meta at-genre-sub">
                          部: {grokDepts.map((d) => d.name).join(" · ")}
                        </p>
                      ) : null}
                      <ul>
                        {grokList.map((b) => (
                          <li key={b.id}>
                            <span className="at-org-name">
                              {b.code && b.code !== "—" ? `${b.code} ` : ""}
                              {b.name}
                            </span>
                            <span className="meta at-org-work">{b.work}</span>
                          </li>
                        ))}
                        {!grokList.length ? (
                          <li className="meta">Grok Bot なし</li>
                        ) : null}
                      </ul>
                    </div>
                  </div>
                </section>
              );
            })}
          </div>
        </>
      ) : null}

      {tab === "ai" ? (
        <>
          <div className="at-counts" aria-label="状態別件数">
            {(
              [
                ["運用確認", "🟡", counts["運用確認"] ?? 0],
                ["設計中", "🔵", counts["設計中"] ?? 0],
                ["運用", "🟢", counts["運用"] ?? 0],
                ["候補", "⚪", counts["候補"] ?? 0],
                ["停止", "⛔", counts["停止"] ?? 0],
              ] as const
            ).map(([label, icon, n]) => (
              <button
                key={label}
                type="button"
                className={`at-count ${statusFilter === label ? "is-on" : ""}`}
                title={
                  STATUS_LEGEND.find((r) => r.status === label)?.meaning || label
                }
                onClick={() =>
                  setStatusFilter(statusFilter === label ? "すべて" : label)
                }
              >
                <span className={statusClass(label)} aria-hidden>
                  {icon}
                </span>
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
                    {d.genre_name ? (
                      <p className="meta at-org-meta">{d.genre_name}</p>
                    ) : null}
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
                ジャンル{" "}
                <select
                  value={genreFilter}
                  onChange={(e) => setGenreFilter(e.target.value)}
                >
                  <option value="すべて">すべて</option>
                  {genres.map((g) => (
                    <option key={g.id} value={g.id}>
                      {g.name}
                    </option>
                  ))}
                </select>
              </label>
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
                    <th>ジャンル</th>
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
                      <td className="meta">{a.genre_name || "—"}</td>
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
                      {[d.genre_name, d.exec_level || d.channel]
                        .filter(Boolean)
                        .join(" · ")}
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
                ジャンル{" "}
                <select
                  value={genreFilter}
                  onChange={(e) => setGenreFilter(e.target.value)}
                >
                  <option value="すべて">すべて</option>
                  {genres.map((g) => (
                    <option key={g.id} value={g.id}>
                      {g.name}
                    </option>
                  ))}
                </select>
              </label>
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
                    <th>ジャンル</th>
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
                      <td className="meta">{b.genre_name || "—"}</td>
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
            {grok.note ||
              "対応表は全件（対応あり／AIのみ／Grokのみ）。〔Grok:◯◯〕は置き換えではなく並べて比較する相手。"}
            {grok.mixup_doc ? ` 詳細: ${grok.mixup_doc}` : null}
          </p>
          <div className="at-counts" aria-label="対応表フィルタ">
            {(
              [
                ["すべて", mapCounts.all],
                ["対応あり", mapCounts.paired],
                ["AIのみ", mapCounts.ai_only],
                ["Grokのみ", mapCounts.grok_only],
              ] as const
            ).map(([label, n]) => (
              <button
                key={label}
                type="button"
                className={`at-count ${mapFilter === label ? "is-on" : ""}`}
                onClick={() => setMapFilter(label)}
              >
                <span>{label}</span>
                <strong>{n}</strong>
              </button>
            ))}
          </div>
          <section className="home-section">
            <div className="home-section-head">
              <h2 style={{ fontSize: "1.08rem", margin: 0 }}>
                AIエージェントチーム ↔ Grok Bot
              </h2>
              <span className="meta">{mappingsFiltered.length}行</span>
            </div>
            <div className="at-table-wrap">
              <table className="at-table">
                <thead>
                  <tr>
                    <th>側</th>
                    <th>AI社員</th>
                    <th>印</th>
                    <th>種別</th>
                    <th>対応 Grok</th>
                    <th>役割／実施</th>
                  </tr>
                </thead>
                <tbody>
                  {mappingsFiltered.map((m, i) => {
                    const rowKey =
                      m.side === "grok_only"
                        ? `g-${m.grok_ids[0] || i}`
                        : `a-${m.agent_id || i}`;
                    return (
                      <tr
                        key={rowKey}
                        className={
                          m.side === "grok_only"
                            ? "at-map-grok-only"
                            : m.side === "ai_only"
                              ? "at-map-ai-only"
                              : undefined
                        }
                      >
                        <td>
                          <span
                            className={`at-map-side at-map-side-${m.side || "paired"}`}
                          >
                            {mappingSideLabel(m.side || "paired")}
                          </span>
                        </td>
                        <td>
                          {m.side === "grok_only" ? (
                            <span className="at-map-missing">AI社員対応なし</span>
                          ) : (
                            <Link href={`/agent-team/${m.agent_id}`}>
                              {m.agent_id} {m.agent_name}
                            </Link>
                          )}
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
                          {m.side === "ai_only" ? (
                            <span className="at-map-missing">Grok対応なし</span>
                          ) : m.mixup_kind === "lane" ? (
                            <span className="meta">全Grok／比較レーン</span>
                          ) : m.grok_labels.length ? (
                            <>
                              {m.grok_labels.join(" · ")}
                              {m.grok_department ? (
                                <span className="meta">
                                  {" "}
                                  （{m.grok_department}）
                                </span>
                              ) : null}
                            </>
                          ) : (
                            "—"
                          )}
                        </td>
                        <td className="meta">{m.role_split || "—"}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </section>
        </>
      ) : null}
    </>
  );
}
