import Link from "next/link";
import { notFound } from "next/navigation";
import Shell from "@/components/Shell";
import {
  getAgentById,
  getAgentTeam,
  getMappingsForAgent,
  mixupKindLabel,
  reportLabel,
  statusClass,
} from "@/lib/agentTeam";

export function generateStaticParams() {
  return getAgentTeam().agents.map((a) => ({ id: a.id }));
}

export default async function AgentTeamDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const agent = getAgentById(id);
  if (!agent) notFound();
  const team = getAgentTeam();
  const mapping = getMappingsForAgent(id);

  return (
    <Shell active="/agent-team">
      <p className="meta" style={{ marginBottom: 8 }}>
        <Link href="/agent-team">← AIエージェントチーム</Link>
        {" · "}
        {agent.department_id} {agent.department_name}
      </p>
      <h1>
        <span className={statusClass(agent.status)}>
          {agent.status_icon} {agent.status}
        </span>{" "}
        {agent.id} {agent.name}
      </h1>
      {agent.builder_tag ? (
        <p className="meta">{agent.builder_tag}</p>
      ) : null}

      <div className="at-detail-grid">
        <section className="card at-detail-card">
          <header>
            <strong>概要</strong>
          </header>
          <p className="sum">{agent.summary || agent.note || "（要約なし）"}</p>
          <dl className="at-dl">
            <div>
              <dt>合図</dt>
              <dd>{agent.trigger || "—"}</dd>
            </div>
            <div>
              <dt>スケジュール</dt>
              <dd>{agent.schedule || "—"}</dd>
            </div>
            <div>
              <dt>報告</dt>
              <dd>{reportLabel(agent.report)}</dd>
            </div>
            <div>
              <dt>ツール</dt>
              <dd>
                {agent.tool_assigned || "—"}
                {agent.tool_fit ? `（${agent.tool_fit}）` : ""}
              </dd>
            </div>
            {agent.tool_notes ? (
              <div>
                <dt>ツールメモ</dt>
                <dd>{agent.tool_notes}</dd>
              </div>
            ) : null}
            {agent.note && agent.note !== agent.summary ? (
              <div>
                <dt>メモ</dt>
                <dd>{agent.note}</dd>
              </div>
            ) : null}
          </dl>
        </section>

        <section className="card at-detail-card">
          <header>
            <strong>Grok Bot 対応</strong>
          </header>
          {mapping ? (
            <dl className="at-dl">
              <div>
                <dt>種別</dt>
                <dd>{mixupKindLabel(mapping.mixup_kind)}</dd>
              </div>
              <div>
                <dt>印</dt>
                <dd>{mapping.builder_tag || "—"}</dd>
              </div>
              <div>
                <dt>対応 Grok</dt>
                <dd>
                  {mapping.mixup_kind === "lane"
                    ? "全Grok／比較レーン"
                    : mapping.grok_labels.join(" · ") || "—"}
                </dd>
              </div>
              <div>
                <dt>役割分担</dt>
                <dd>{mapping.role_split || "—"}</dd>
              </div>
            </dl>
          ) : (
            <p className="meta">
              Grok 同型なし（Jarvis／Slack／Mac 本線）。対応表タブにも載りません。
            </p>
          )}
          <p className="meta" style={{ marginTop: 10 }}>
            <Link href="/agent-team">対応表タブで一覧</Link>
          </p>
        </section>

        <section className="card at-detail-card">
          <header>
            <strong>作業フロー（AIオートメーション）</strong>
          </header>
          {agent.flow_summary ? (
            <p className="sum">{agent.flow_summary}</p>
          ) : (
            <p className="meta">flow.md の結論行は未整備です。</p>
          )}
          {agent.flowforge_url ? (
            <p style={{ marginTop: 14 }}>
              <a
                className="at-ff-cta"
                href={agent.flowforge_url}
                target="_blank"
                rel="noopener noreferrer"
              >
                AIオートメーションを開く ↗
              </a>
            </p>
          ) : (
            <p className="meta">FlowForge URL 未設定</p>
          )}
          <p className="at-hint" style={{ marginTop: 12 }}>
            {team.flowforge_open_note}
          </p>
          <p className="meta" style={{ marginTop: 8 }}>
            作り込み・ズーム・ノード詳細は Cursor インブラウザで開いて作業してください。
            このダッシュ画面への埋め込みは FlowForge 側の制限（X-Frame DENY）のためできません。
          </p>
        </section>
      </div>

      <p className="meta" style={{ marginTop: 24 }}>
        フォルダ: <code>{agent.path}</code>
        {" · "}
        <Link href="/agent-team">一覧へ戻る</Link>
      </p>
    </Shell>
  );
}
