"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

type Field = {
  key: string;
  label: string;
  type?: "text" | "password";
  placeholder?: string;
};

type Group = { title: string; hint?: string; fields: Field[] };

const GROUPS: Group[] = [
  {
    title: "ソニー生命",
    hint: "お客さまWEBのログインID／パスワード（真治=1 / 千景=2）。保存後にこちらで実ログイン検証します。",
    fields: [
      { key: "SONYLIFE_LOGIN_URL", label: "ログインURL" },
      { key: "SONYLIFE_USERNAME_1", label: "真治 利用者ID" },
      { key: "SONYLIFE_PASSWORD_1", label: "真治 パスワード", type: "password" },
      { key: "SONYLIFE_USERNAME_2", label: "千景 利用者ID" },
      { key: "SONYLIFE_PASSWORD_2", label: "千景 パスワード", type: "password" },
    ],
  },
  {
    title: "Bloomo",
    hint: "公式は bloomo.co.jp。ログインは https://sec.bloomo.co.jp （※2025年以降パスワードレス＝メール認証コードの可能性あり）。",
    fields: [
      { key: "BLOOMO_EMAIL", label: "メール" },
      { key: "BLOOMO_PASSWORD", label: "パスワード（従来方式の場合）", type: "password" },
      {
        key: "BLOOMO_LOGIN_URL",
        label: "ログインURL",
        placeholder: "https://sec.bloomo.co.jp",
      },
    ],
  },
  {
    title: "プルデンシャル生命（Web）",
    hint: "Myページで解約返戻・貸付を取得（真治=1 / 千景=2）。確認番号は Gmail 連携が既定。手登録は予備。",
    fields: [
      {
        key: "PRUDENTIAL_LOGIN_URL",
        label: "ログインURL",
        placeholder: "https://mypage-poj.jpsso.prudential.com/s/login",
      },
      { key: "PRUDENTIAL_USERNAME_1", label: "真治 ログインID" },
      { key: "PRUDENTIAL_PASSWORD_1", label: "真治 パスワード", type: "password" },
      { key: "PRUDENTIAL_USERNAME_2", label: "千景 ログインID" },
      { key: "PRUDENTIAL_PASSWORD_2", label: "千景 パスワード", type: "password" },
      { key: "PRUDENTIAL_VALUE_JPY", label: "（予備）真治 評価額手登録" },
      { key: "PRUDENTIAL_LOAN_JPY", label: "（予備）真治 貸付手登録" },
      { key: "PRUDENTIAL_CHIKAGE_VALUE_JPY", label: "（予備）千景 評価額手登録" },
      { key: "PRUDENTIAL_CHIKAGE_LOAN_JPY", label: "（予備）千景 貸付手登録" },
    ],
  },
];

export default function SecretsForm({
  status,
}: {
  status: Record<string, boolean>;
}) {
  const router = useRouter();
  const [values, setValues] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    const updates: Record<string, string> = {};
    for (const [k, v] of Object.entries(values)) {
      if (v.trim()) updates[k] = v.trim();
    }
    if (Object.keys(updates).length === 0) {
      setMsg("入力が空です（埋めた欄だけ保存します）");
      return;
    }
    setBusy(true);
    setMsg(null);
    try {
      const res = await fetch("/api/secrets", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ updates }),
      });
      const data = await res.json();
      if (!res.ok) {
        setMsg(data.error || "失敗");
      } else {
        setMsg(
          "キューに入れました。Mac worker（最大約15分）が .env.jarvis_private に反映します。値は画面に残りません。"
        );
        setValues({});
        router.refresh();
      }
    } catch (err) {
      setMsg(err instanceof Error ? err.message : "エラー");
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={onSubmit}>
      {GROUPS.map((g) => (
        <div className="card" key={g.title} style={{ marginBottom: 12 }}>
          <header>
            <span className="lvl">設定</span>
            <strong>{g.title}</strong>
          </header>
          {g.hint ? <p className="meta">{g.hint}</p> : null}
          <div style={{ display: "grid", gap: 10 }}>
            {g.fields.map((f) => (
              <label key={f.key} style={{ display: "grid", gap: 4 }}>
                <span>
                  {f.label}{" "}
                  <span className="meta">
                    {status[f.key] ? "✅ 登録済" : "— 未設定"}
                  </span>
                </span>
                <input
                  className="btn"
                  style={{ textAlign: "left", padding: "8px 10px" }}
                  type={f.type || "text"}
                  autoComplete="off"
                  placeholder={
                    status[f.key]
                      ? "（変更するときだけ入力）"
                      : f.placeholder || ""
                  }
                  value={values[f.key] || ""}
                  onChange={(ev) =>
                    setValues((prev) => ({ ...prev, [f.key]: ev.target.value }))
                  }
                />
              </label>
            ))}
          </div>
        </div>
      ))}
      <button type="submit" className="btn primary" disabled={busy}>
        {busy ? "送信中…" : "入力した項目を保存キューへ"}
      </button>
      {msg ? <p className="meta">{msg}</p> : null}
    </form>
  );
}
