import Link from "next/link";
import { notFound } from "next/navigation";
import Shell from "@/components/Shell";
import {
  flowforgeOpenLabel,
  flowforgeOpenUrl,
  getAgentById,
  getAgentTeam,
  getMappingsForAgent,
  mixupKindHint,
  mixupKindLabel,
  permissionLevelClass,
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
  const viewUrl = agent.flowforge_share_url || "";
  const editUrl = agent.flowforge_edit_url || agent.flowforge_url || "";
  const primaryUrl = flowforgeOpenUrl(agent);

  return (
    <Shell active="/agent-team">
      <p className="meta" style={{ marginBottom: 8 }}>
        <Link href="/agent-team">← AIエージェントチーム</Link>
        {agent.genre_name ? (
          <>
            {" · "}
            <Link href={`/agent-team#genre-${agent.genre_id}`}>
              {agent.genre_name}
            </Link>
          </>
        ) : null}
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
              <dt>ジャンル</dt>
              <dd>{agent.genre_name || "—"}</dd>
            </div>
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
            <>
              {mixupKindHint(mapping.mixup_kind) ? (
                <p className="sum" style={{ marginBottom: 12 }}>
                  {mixupKindHint(mapping.mixup_kind)}
                </p>
              ) : null}
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
            </>
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
            <strong>実行権限</strong>
          </header>
          {agent.permissions ? (
            <>
              <p className="sum">{agent.permissions.can_do || "（未記入）"}</p>
              <dl className="at-dl">
                <div>
                  <dt>サイト／ログイン</dt>
                  <dd>
                    {agent.permissions.has_site_logins ? (
                      <span className="at-perm-site">
                        {agent.permissions.site_logins_summary}
                      </span>
                    ) : (
                      "なし"
                    )}
                  </dd>
                </div>
                <div>
                  <dt>envキー（名前のみ）</dt>
                  <dd>
                    {(agent.permissions.env_keys || []).length
                      ? agent.permissions.env_keys.join(" · ")
                      : "—"}
                  </dd>
                </div>
                <div>
                  <dt>人が確かめる</dt>
                  <dd>{agent.permissions.human_gate || "—"}</dd>
                </div>
              </dl>
              {agent.permissions.methods?.length ? (
                <ul className="at-perm-methods" style={{ marginTop: 12 }}>
                  {agent.permissions.methods.map((m) => (
                    <li key={m.name}>
                      <span className={permissionLevelClass(m.level)}>
                        {m.level || "—"}
                      </span>{" "}
                      {m.name}
                      {m.detail ? (
                        <span className="meta"> — {m.detail}</span>
                      ) : null}
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="meta" style={{ marginTop: 8 }}>
                  CLAUDE.md「## 3. 実行権限」が未記入です。
                </p>
              )}
              {agent.permissions.has_site_logins ? (
                <ul className="at-perm-site-list">
                  {agent.permissions.site_logins.map((s) => (
                    <li key={s.service}>
                      <strong>{s.service}</strong>
                      {s.access ? ` · ${s.access}` : ""}
                      {s.note ? (
                        <span className="meta"> — {s.note}</span>
                      ) : null}
                    </li>
                  ))}
                </ul>
              ) : null}
              <p className="meta" style={{ marginTop: 10 }}>
                <Link href="/agent-team">権限タブで一覧</Link>
              </p>
            </>
          ) : (
            <p className="meta">
              権限データがありません。sync 後に agentTeam.json を更新してください。
            </p>
          )}
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

          <div className="at-ff-warn" role="note">
            <strong>Safari／Chrome で編集URLを開くと「同期失敗」「新しいフロー」になりやすいです。</strong>
            <span>
              原因はログインアカウント違い（正は{" "}
              {team.flowforge_login_email || "m19m.hrts83@gmail.com"}
              ）。ダッシュの admin とは別です。
            </span>
          </div>

          {primaryUrl ? (
            <p style={{ marginTop: 14, display: "flex", flexWrap: "wrap", gap: 10 }}>
              {viewUrl ? (
                <a
                  className="at-ff-cta"
                  href={viewUrl}
                  target="_blank"
                  rel="noopener noreferrer"
                >
                  閲覧で開く（推奨） ↗
                </a>
              ) : null}
              {editUrl ? (
                <a
                  className="at-ff-cta at-ff-cta-secondary"
                  href={editUrl}
                  target="_blank"
                  rel="noopener noreferrer"
                  title="m19m を選んでください"
                >
                  {viewUrl ? "編集（m19m選択） ↗" : `${flowforgeOpenLabel(agent)} ↗`}
                </a>
              ) : null}
            </p>
          ) : (
            <p className="meta">FlowForge URL 未設定</p>
          )}

          <p className="at-hint" style={{ marginTop: 12 }}>
            {team.flowforge_open_note}
          </p>
          <ol className="at-ff-steps">
            <li>
              <strong>見るだけ</strong> → 「閲覧で開く」。ログイン不要でノード構成が見えます（編集不可）。
            </li>
            <li>
              <strong>直す・作り込む</strong> → Cursor の Simple Browser（インブラウザ）で FlowForge を開き、
              {team.flowforge_login_hint || "m19m"} でログイン。チャットで「〇〇のフローを開いて」でも可。
            </li>
            <li>
              外部ブラウザで編集するなら「編集（m19m選択）」→ Google で{" "}
              <code>{team.flowforge_login_email || "m19m.hrts83@gmail.com"}</code>{" "}
              を選ぶ。admin のままだと空フローになります。
            </li>
          </ol>
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
