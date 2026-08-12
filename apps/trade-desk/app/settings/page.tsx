import Shell from "@/components/Shell";
import SecretsForm from "@/components/SecretsForm";
import EnqueueJobButton from "@/components/EnqueueJobButton";
import { createClient } from "@/lib/supabase/server";

export const dynamic = "force-dynamic";

export default async function SettingsPage() {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();

  const { data: meta } = await supabase
    .from("sync_meta")
    .select("key, value, updated_at")
    .in("key", ["kurashift_secrets_status", "kurashift_secrets_updated_at"]);

  let status: Record<string, boolean> = {};
  let updatedAt: string | null = null;
  for (const row of meta ?? []) {
    if (row.key === "kurashift_secrets_updated_at") {
      updatedAt = row.value;
    }
    if (row.key === "kurashift_secrets_status") {
      try {
        status = JSON.parse(row.value) as Record<string, boolean>;
      } catch {
        status = {};
      }
    }
  }

  const setCount = Object.values(status).filter(Boolean).length;

  return (
    <Shell active="/settings" email={user?.email ?? null}>
      <h1>設定（ログイン・手登録）</h1>
      <p className="sub">
        入力した値は Mac 上の{" "}
        <code>.env.jarvis_private</code>{" "}
        にだけ残します。空欄は触りません。チャットや Git には貼らないでください。
      </p>

      <div className="card">
        <header>
          <span className="lvl">状況</span>
          <strong>
            登録済キー {setCount}
            {Object.keys(status).length
              ? ` / ${Object.keys(status).length}`
              : ""}
          </strong>
        </header>
        <p className="meta">
          最終反映: {updatedAt ?? "まだ worker 未実行"}（「状況を更新」で Mac
          側の有無だけ再スキャン）
        </p>
        <EnqueueJobButton
          jobType="secrets_status"
          title="secrets status"
          label="状況を更新"
        />
      </div>

      <SecretsForm status={status} />
    </Shell>
  );
}
