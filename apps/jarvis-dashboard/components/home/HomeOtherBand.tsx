import BulkSkipNonPartnerButton from "@/components/BulkSkipNonPartnerButton";
import OtherMailDigestGenres from "@/components/home/OtherMailDigestGenres";
import { LEVEL_LABEL, laneLabel, mailPriorityToLevel } from "@/lib/homeLevels";
import { parseIntentDigest } from "@/lib/intentDigest";
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
      .limit(60),
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

  const needConfirm = otherMails.filter((m) => (m.kind || "mail") === "mail");
  const skimOnly = otherMails.filter((m) => m.kind === "skim");

  const digest =
    parseOtherMailDigest(metaMap.other_mail_digest) ||
    fallbackOtherMailDigest(otherMails);
  const actionItems = digest.action_items || [];
  const genres = digest.genres || [];
  const intent = parseIntentDigest(metaMap.intent_digest);
  const intentThemes = intent?.themes || [];
  const intentNotes = intent?.digest_notes || [];
  const intentPromoted = (intent?.promoted || []).filter(
    (p) => p.triage_id && p.action !== "candidate",
  );

  return (
    <div className="home-band home-band-other">
      <div className="home-band-head">
        <h2 className="home-band-title">その他メール</h2>
        <p className="home-band-sub">
          要確認 {needConfirm.length} · 要約 {skimOnly.length}
          {digest.generated_at
            ? ` · 要約 ${fmtSync(digest.generated_at)}`
            : ""}
        </p>
      </div>

      <p className="other-mail-hint">
        要確認は個別に開く。ざっと見る分はジャンル要約の「確認したよ」で既読にできます。
      </p>

      {intent && (intentThemes.length > 0 || intentNotes.length > 0) ? (
        <div className="intent-digest" role="status">
          <p className="intent-digest-title">いまの関心</p>
          {intentNotes.length > 0 ? (
            <p className="intent-digest-notes">{intentNotes[0]}</p>
          ) : null}
          {intentThemes.length > 0 ? (
            <ul className="intent-theme-list">
              {intentThemes.slice(0, 4).map((t, i) => (
                <li key={t.id || i}>
                  <span className="intent-theme-label">
                    {t.label || t.id || "テーマ"}
                  </span>
                  {t.why ? (
                    <span className="intent-theme-why"> — {t.why}</span>
                  ) : null}
                </li>
              ))}
            </ul>
          ) : null}
          {intentPromoted.length > 0 ? (
            <p className="intent-promoted">
              昇格:{" "}
              {intentPromoted.slice(0, 3).map((p, i) => (
                <span key={p.triage_id || i}>
                  {i > 0 ? " · " : null}
                  <a href={`/mail/${encodeURIComponent(p.triage_id!)}`}>
                    {p.subject || p.triage_id}
                  </a>
                </span>
              ))}
            </p>
          ) : null}
          {intent.generated_at ? (
            <p className="intent-digest-meta meta">
              Journal連動 {fmtSync(intent.generated_at)}
              {intent.via ? ` · ${intent.via}` : ""}
            </p>
          ) : null}
        </div>
      ) : null}

      <div className="other-mail-digest">
        <p className="other-mail-overview">
          {digest.overview || "（要約未生成。一覧をご確認ください）"}
        </p>
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
        ) : needConfirm.length > 0 ? (
          <p className="other-mail-no-action">特に緊急候補なし（要確認は下の一覧）</p>
        ) : null}
      </div>

      {genres.length > 0 ? (
        <OtherMailDigestGenres genres={genres} path="/" />
      ) : null}

      <div className="other-mail-toolbar">
        <BulkSkipNonPartnerButton
          path="/"
          pendingCount={otherMails.length}
          actionCandidateCount={needConfirm.length}
        />
        <a href="/general" className="home-more">
          レーンへ →
        </a>
      </div>

      <section className="home-section">
        <div className="home-section-head">
          <h3>要確認一覧</h3>
          <span className="meta">クリックで詳細</span>
        </div>
        {needConfirm.length === 0 ? (
          <p className="empty">要確認の未読はありません（要約は上のジャンルから）</p>
        ) : (
          <ul className="mail-skim">
            {needConfirm.map((it) => {
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
