import { createClient } from "@/lib/supabase/server";
import { fmtSync } from "./homeHelpers";

export default async function HomeMetaDetails() {
  const supabase = await createClient();
  const { data: meta } = await supabase.from("sync_meta").select("key,value");
  const metaMap = Object.fromEntries((meta || []).map((m) => [m.key, m.value]));
  const cloudAt =
    metaMap.gha_triage_pushed_at ||
    metaMap.gha_watch_pushed_at ||
    metaMap.gha_heartbeat_at;
  const macMorningAt = metaMap.mac_morning_refreshed_at;

  return (
    <>
      <details className="home-meta">
        <summary>同期情報（詳細）</summary>
        <div className="stats" style={{ marginTop: 10 }}>
          <div className="stat">cloud {fmtSync(cloudAt)}</div>
          <div className="stat">mac_morning {fmtSync(macMorningAt)}</div>
          <div className="stat">
            triage {metaMap.triage_pushed_at ?? "未push"}
          </div>
          <div className="stat">
            watch {metaMap.watch_pushed_at ?? "未push"}
          </div>
          <div className="stat">経路 {metaMap.triage_source ?? "—"}</div>
          <div className="stat">
            Mac push {metaMap.mac_triage_pushed_at ?? "—"}
          </div>
          <div className="stat">
            GHA triage {metaMap.gha_triage_pushed_at ?? "—"}
          </div>
        </div>
      </details>

      <details className="home-meta home-data-locations">
        <summary>お知らせ · データ所在・復旧メモ</summary>
        <div className="home-data-locations-body">
          <p>
            画面に出ているのは Supabase への<strong>投影</strong>です。アプリ本体（JS／CSS／TS）と設定の正本は
            Git。DB が消えても YAML／CSV／スキーマから作り直せます。
          </p>
          <dl className="home-data-locations-list">
            <div>
              <dt>アプリ本体（最新の JS／CSS／TS）</dt>
              <dd>
                GitHub{" "}
                <a
                  href="https://github.com/m19mhrts83-cyber/project-GE"
                  target="_blank"
                  rel="noopener noreferrer"
                >
                  m19mhrts83-cyber/project-GE
                </a>
                {" · フォルダ "}
                <code>apps/jarvis-dashboard/</code>
                <br />
                画面・スタイル: <code>app/</code>（例:{" "}
                <code>app/globals.css</code>）· <code>components/</code> ·{" "}
                <code>lib/</code>
                <br />
                Mac クローン: <code>~/git-repos/apps/jarvis-dashboard/</code>
              </dd>
            </div>
            <div>
              <dt>表示用 DB（投影）</dt>
              <dd>
                Supabase プロジェクト <code>jarvis-dashboard</code>（ref{" "}
                <code>idkdqneutpvkhxhpjtgc</code>）
                <br />
                スキーマ正本:{" "}
                <code>apps/jarvis-dashboard/supabase/schema.sql</code>
                <br />
                Dashboard:{" "}
                <a
                  href="https://supabase.com/dashboard/project/idkdqneutpvkhxhpjtgc"
                  target="_blank"
                  rel="noopener noreferrer"
                >
                  supabase.com/…/idkdqneutpvkhxhpjtgc
                </a>
              </dd>
            </div>
            <div>
              <dt>本番ホスティング</dt>
              <dd>
                Vercel（Root Directory = <code>apps/jarvis-dashboard</code>）
                <br />
                URL:{" "}
                <a
                  href="https://jarvis-dashboard-amber.vercel.app/"
                  target="_blank"
                  rel="noopener noreferrer"
                >
                  jarvis-dashboard-amber.vercel.app
                </a>
              </dd>
            </div>
            <div>
              <dt>設定・収集の正本（Git／Mac）</dt>
              <dd>
                YAML: <code>config/</code>（状況ウォッチ・課金・Zaim 等）
                <br />
                収集スクリプト: <code>scripts/</code> → Mac／GHA が Supabase へ
                push
                <br />
                秘密: <code>~/git-repos/.env.jarvis_private</code>
                （Git 外）
              </dd>
            </div>
            <div>
              <dt>業務ファイル原本（ダッシュボード外）</dt>
              <dd>
                OneDrive（パートナーやり取り等）· admin Drive{" "}
                <code>200_NoteBookLM/</code> · Notion（タスク原本）
                <br />
                Web はこれらを丸ごとマウントせず、必要なときだけ Server
                が読んで注入／Mac が投影する
              </dd>
            </div>
            <div>
              <dt>障害時の取り方（短い順）</dt>
              <dd>
                1. GitHub（または <code>~/git-repos</code>
                ）から <code>apps/jarvis-dashboard</code> を取得
                <br />
                2. <code>npm install</code> → env を埋めて{" "}
                <code>npm run dev</code>／別ホストへデプロイ
                <br />
                3. DB は Schema SQL 適用後、Mac の{" "}
                <code>jarvis_dashboard_push.py</code> 等で再投影。必要なら
                Supabase から事前に CSV／SQL エクスポートも可
              </dd>
            </div>
            <div>
              <dt>設計メモ</dt>
              <dd>
                リポジトリ内{" "}
                <code>docs/Jarvis_Dashboard_設計メモ_20260801.md</code>
                （置き場の表あり）
              </dd>
            </div>
          </dl>
        </div>
      </details>
    </>
  );
}
