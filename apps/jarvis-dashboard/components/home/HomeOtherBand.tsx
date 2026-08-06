import BulkSkipNonPartnerButton from "@/components/BulkSkipNonPartnerButton";
import { LEVEL_LABEL, laneLabel, mailPriorityToLevel } from "@/lib/homeLevels";
import {
  fallbackOtherMailDigest,
  parseOtherMailDigest,
} from "@/lib/otherMailDigest";
import { createClient } from "@/lib/supabase/server";
import { fmtSync } from "./homeHelpers";

export default async function HomeOtherBand() {
  const supabase = await createClient();
  const [{ data: mailRows }, { data: meta }] = await Promise.all([
    supabase
      .from("triage_items")
      .select(
        "id,lane,kind,status,partner,folder,subject,received_at,summary,priority,from_email",
      )
      .eq("status", "pending")
      .neq("lane", "partner")
      .neq("kind", "activity")
      .order("received_at", { ascending: false })
      .limit(40),
    supabase.from("sync_meta").select("key,value"),
  ]);
  const metaMap = Object.fromEntries((meta || []).map((m) => [m.key, m.value]));

  const otherMails = (mailRows || []).slice().sort((a, b) => {
    const order = { attention: 0, warn: 1, info: 2 } as const;
    return (
      order[mailPriorityToLevel(a.priority)] -
      order[mailPriorityToLevel(b.priority)]
    );
  });

  const digest =
    parseOtherMailDigest(metaMap.other_mail_digest) ||
    fallbackOtherMailDigest(otherMails);
  const actionItems = digest.action_items || [];

  return (
    <div className="home-band home-band-other">
      <div className="home-band-head">
        <h2 className="home-band-title">その他メール</h2>
        <p className="home-band-sub">
          未読 {otherMails.length}
          {digest.generated_at
            ? ` · 要約 ${fmtSync(digest.generated_at)}`
            : ""}
        </p>
      </div>

      <p className="other-mail-hint">
        ざざっと見て、残したい／対応したいものだけ開く。終わったら一括スキップ。
      </p>

      <div className="other-mail-digest">
        <p className="other-mail-overview">
          {digest.overview || "（要約未生成。一覧をご確認ください）"}
        </p>
        {(digest.lines || []).length > 0 ? (
          <ul className="other-mail-lines">
            {(digest.lines || []).slice(0, 5).map((line, i) => (
              <li key={i}>{line}</li>
            ))}
          </ul>
        ) : null}
        {actionItems.length > 0 ? (
          <div className="other-mail-actions" role="status">
            <p className="other-mail-actions-title">対応した方がよさそう</p>
            <ul>
              {actionItems.slice(0, 5).map((a, i) => (
                <li key={a.id || i}>
                  {a.id ? (
                    <a href={`/mail/${encodeURIComponent(a.id)}`}>
                      {a.subject || "（件名なし）"}
                    </a>
                  ) : (
                    <span>{a.subject || "（件名なし）"}</span>
                  )}
                  {a.from ? (
                    <span className="meta"> · {a.from}</span>
                  ) : null}
                  {a.reason ? (
                    <span className="other-mail-reason"> — {a.reason}</span>
                  ) : null}
                </li>
              ))}
            </ul>
          </div>
        ) : otherMails.length > 0 ? (
          <p className="other-mail-no-action">特に緊急候補なし</p>
        ) : null}
      </div>

      <div className="other-mail-toolbar">
        <BulkSkipNonPartnerButton
          path="/"
          pendingCount={otherMails.length}
          actionCandidateCount={actionItems.length}
        />
        <a href="/general" className="home-more">
          レーンへ →
        </a>
      </div>

      <section className="home-section">
        <div className="home-section-head">
          <h3>一覧</h3>
          <span className="meta">クリックで詳細</span>
        </div>
        {otherMails.length === 0 ? (
          <p className="empty">パートナー以外の未読はありません</p>
        ) : (
          <ul className="mail-skim">
            {otherMails.map((it) => {
              const level = mailPriorityToLevel(it.priority);
              const who = it.partner || it.from_email || "—";
              const oneLine = (it.summary || "").replace(/\s+/g, " ").trim();
              return (
                <li key={it.id}>
                  <a
                    href={`/mail/${encodeURIComponent(it.id)}`}
                    className={`mail-row level-${level}`}
                  >
                    <span className="lvl">{LEVEL_LABEL[level]}</span>
                    <span className="mail-row-main">
                      <span className="mail-row-top">
                        <strong>{who}</strong>
                        <span className="meta">
                          {laneLabel(it.lane)}
                          {it.received_at ? ` · ${it.received_at}` : ""}
                        </span>
                      </span>
                      <span className="mail-subject">
                        {it.subject || "（件名なし）"}
                      </span>
                      {oneLine ? (
                        <span className="mail-preview">{oneLine}</span>
                      ) : null}
                    </span>
                    <span className="mail-chevron" aria-hidden>
                      ›
                    </span>
                  </a>
                </li>
              );
            })}
          </ul>
        )}
        <p className="home-lane-links">
          レーン別: <a href="/general">それ以外</a>
          {" · "}
          <a href="/openchat">オプチャ</a>
        </p>
      </section>
    </div>
  );
}
