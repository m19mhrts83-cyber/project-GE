import { DailyChart, HourChart, KindLegend, WeeklyChart } from "@/components/mail-insights/MiCharts";
import type { DayBar, Insight, Kpis, StyleStats, WeekVol } from "@/lib/mailInsights";

/** メールの振り返り（/mail）の見た目。数字は app/mail/page.tsx で集計して渡す */

export type Learned = { at: string; title: string; detail: string; pill: string; tone: "on" | "wait" };

export type MailInsightsProps = {
  rangeDays: number;
  chartDays: number;
  weeksN: number;
  error: string | null;
  deskCount: number;
  deskPartner: number;
  waitDays: number | null;
  deskHref: string;
  k: Kpis;
  days: DayBar[];
  hours: number[];
  peaks: number[];
  weeks: WeekVol[];
  style: StyleStats;
  learned: Learned[];
  notes: Insight[];
};

function pctText(n: number, d: number): string {
  return d ? `${Math.round((n / d) * 100)}` : "—";
}

export default function MailInsightsView({
  rangeDays,
  chartDays,
  weeksN,
  error,
  deskCount,
  deskPartner,
  waitDays,
  deskHref,
  k,
  days,
  hours,
  peaks,
  weeks,
  style,
  learned,
  notes,
}: MailInsightsProps) {
  return (
    <div className="mi">
      <header className="mi-head">
        <span className="mi-eyebrow">メール</span>
        <h1>メールの振り返り</h1>
        <p className="sub">
          処置は判断デスクで。ここでは直近{rangeDays}日の判断と、届いたメールの傾向を見ます。
          {error ? ` 一部読めませんでした（${error}）。` : ""}{" "}
          <a href="/mail/partners">パートナー別の見送り・Todoistを見る</a>
        </p>
      </header>

      <section className="mi-now" aria-label="今判断すべきもの">
        <div className="mi-now-main">
          <span className="mi-eyebrow mi-on-dark">今判断すべきもの</span>
          <div className="mi-now-row">
            <span className="mi-now-big">{deskCount}</span>
            <span>{deskCount ? "件が判断デスクで待っています" : "件。いま判断待ちはありません"}</span>
          </div>
          {deskCount ? (
            <div className="mi-chips">
              <span>
                パートナー <b>{deskPartner}</b>
              </span>
              <span>
                その他メール <b>{deskCount - deskPartner}</b>
              </span>
              {waitDays !== null ? (
                <span>
                  いちばん古いもの <b>{waitDays ? `${waitDays}日前` : "今日"}</b>
                </span>
              ) : null}
            </div>
          ) : null}
        </div>
        <a className="mi-go" href={deskHref} target="_blank" rel="noopener noreferrer">
          判断デスクを開く ↗
        </a>
      </section>

      <div className="mi-kpis">
        <div className="mi-kpi">
          <span className="mi-l">判断した件数（{rangeDays}日）</span>
          <span className="mi-v">
            {k.decided}
            <small>件</small>
          </span>
          <span className="mi-s">{k.bulk ? `うち一括 ${k.bulk}件` : "一括の判断なし"}</span>
        </div>
        <div className="mi-kpi">
          <span className="mi-l">送った返信</span>
          <span className="mi-v">
            {k.sent}
            <small>通</small>
          </span>
          <span className="mi-s">1日平均 {k.sentPerDay.toFixed(1)}通（目標は1日5通）</span>
        </div>
        <div className="mi-kpi">
          <span className="mi-l">下書きをそのまま送った率</span>
          <span className="mi-v">
            {pctText(k.sentUnedited, k.sentTotalForEdit)}
            <small>%</small>
          </span>
          <span className={`mi-s${k.sentTotalForEdit ? " mi-good" : ""}`}>
            {k.sentTotalForEdit ? `${k.sentTotalForEdit}通中 ${k.sentUnedited}通は直しなし` : "まだ記録がありません"}
          </span>
        </div>
        <div className="mi-kpi">
          <span className="mi-l">仕分けが合っていた率</span>
          <span className="mi-v">
            {pctText(k.missOk, k.missTotal)}
            <small>%</small>
          </span>
          <span className={`mi-s${k.missTotal ? " mi-good" : ""}`}>
            {k.missTotal ? `見落とし確認 ${k.missTotal}件中 ${k.missOk}件 OK` : "見落とし確認の記録なし"}
          </span>
        </div>
      </div>

      <section className="mi-sec">
        <h2>回答状況と傾向</h2>
        <div className="mi-grid2">
          <div className="mi-col">
            <p className="mi-cap">毎日の判断の内訳（直近{chartDays}日）</p>
            <div className="mi-chart">
              <DailyChart days={days} />
            </div>
            <KindLegend />
          </div>
          <div className="mi-col">
            <p className="mi-cap">判断している時間帯（一括の判断を除く）</p>
            <div className="mi-chart">
              <HourChart hours={hours} peaks={peaks} />
            </div>
            <p className="mi-cap">
              {peaks.length ? `${peaks.map((h) => `${h}時台`).join("・")}に山があります。` : "まだ記録がありません。"}
              {k.decideMsMedian ? ` 1件の判断にかかる時間は中央値 ${Math.round(k.decideMsMedian / 1000)}秒。` : ""}
            </p>
          </div>
        </div>
        <div className="mi-col">
          <p className="mi-cap">届いたメールの量（週ごと・直近{weeksN}週）</p>
          <div className="mi-chart">
            <WeeklyChart weeks={weeks} />
          </div>
          <div className="mi-legend">
            <span>
              <i style={{ background: "var(--accent)" }} />
              パートナー
            </span>
            <span>
              <i style={{ background: "var(--mi-skip)" }} />
              その他メール
            </span>
          </div>
        </div>
      </section>

      <section className="mi-sec">
        <h2>判断から学んだこと</h2>
        {learned.length ? (
          <ul className="mi-learn">
            {learned.map((l, i) => (
              <li key={i}>
                <span className="mi-d">{l.at}</span>
                <span className="mi-w">
                  {l.title}
                  <span>{l.detail}</span>
                </span>
                <span className={`mi-pill mi-pill-${l.tone}`}>{l.pill}</span>
              </li>
            ))}
          </ul>
        ) : (
          <p className="empty">まだ学びの記録がありません。</p>
        )}
        <p className="mi-cap">
          ルールの採否と取り消しは <a href="/review">週次レビュー</a> で。
        </p>
      </section>

      <section className="mi-sec">
        <h2>
          メールから見える私のスタイル <span className="mi-tag">送った{style.n}通から</span>
        </h2>
        {style.n ? (
          <div className="mi-style">
            <div className="mi-st">
              <span className="mi-k">文の長さ</span>
              <span className="mi-q">
                1通 平均 <b>{style.avgLen}</b> 字（{style.shortest}〜{style.longest}字）
              </span>
              <div className="mi-meter" aria-hidden="true">
                <i style={{ width: `${Math.min(100, Math.round(((style.avgLen || 0) / 600) * 100))}%` }} />
              </div>
              <div className="mi-meter-l">
                <span>短い</span>
                <span>600字</span>
              </div>
            </div>
            <div className="mi-st">
              <span className="mi-k">よく使う書き出し</span>
              {style.openings.length ? (
                style.openings.map((o) => (
                  <span key={o.text} className="mi-q">
                    「{o.text}」<small>{o.n}回</small>
                  </span>
                ))
              ) : (
                <span className="mi-q mi-mute">まだ型が見えません</span>
              )}
            </div>
            <div className="mi-st">
              <span className="mi-k">よく使う結び</span>
              {style.closings.length ? (
                style.closings.map((o) => (
                  <span key={o.text} className="mi-q">
                    「{o.text}」<small>{o.n}回</small>
                  </span>
                ))
              ) : (
                <span className="mi-q mi-mute">まだ型が見えません</span>
              )}
            </div>
            <div className="mi-st mi-st-off">
              <span className="mi-k">ていねいさ・直しで多い指摘</span>
              <span className="mi-q mi-mute">未計測。週1回 Mac の定額枠で言葉にする予定です（追加のAI料金なし）。</span>
            </div>
          </div>
        ) : (
          <p className="empty">直近{rangeDays}日に送った返信の本文がまだありません。</p>
        )}
      </section>

      <section className="mi-sec">
        <h2>全メールからの気づき</h2>
        {notes.length ? (
          <div className="mi-ins">
            {notes.map((n) => (
              <div key={n.title} className={`mi-in mi-in-${n.tone}`}>
                <span className="mi-h">{n.title}</span>
                <p>{n.body}</p>
                <span className="mi-a">{n.hint}</span>
              </div>
            ))}
          </div>
        ) : (
          <p className="empty">まだ気づきを出せるほど記録がありません。</p>
        )}
        <p className="mi-cap">気づきの文は決まった型（集計＋定型文）で作っています。AIは使っていません。</p>
      </section>

      <p className="mi-cap">
        前のメール一覧（<a href="/queue">処理キュー</a>・<a href="/partner">パートナー</a>・<a href="/general">その他メール</a>
        ）はメニューから外しましたが、ここから開けます。
      </p>
    </div>
  );
}
