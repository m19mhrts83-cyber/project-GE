import Link from "next/link";
import FocusCard from "@/components/FocusCard";
import Icon from "@/components/Icon";

export default function HubPage() {
  return (
    <main>
      <div className="brand">
        <div className="logo">
          <Icon name="bolt" size={20} />
        </div>
        <div>
          <div className="eyebrow acc">LOOPWARE</div>
          <strong>社員ループウェア</strong>
        </div>
      </div>

      <FocusCard />

      <div className="eyebrow">メール</div>
      <Link className="glass nav-card" href="/desk?surface=triage">
        <span className="ico">
          <Icon name="check" size={22} />
        </span>
        <span className="txt">
          <strong>判断デスク</strong>
          <span className="meta">1件ずつ。返信／見送る／ToDo／迷う</span>
        </span>
        <Icon name="next" size={18} />
      </Link>
      <Link className="glass nav-card" href="/desk?surface=triage&view=left">
        <span className="ico">
          <Icon name="clock" size={22} />
        </span>
        <span className="txt">
          <strong>残り・次の一手</strong>
          <span className="meta">迷った・見ていないものに次の一手。良い／違う</span>
        </span>
        <Icon name="next" size={18} />
      </Link>
      <Link className="glass nav-card" href="/misses?surface=triage">
        <span className="ico">
          <Icon name="warn" size={22} />
        </span>
        <span className="txt">
          <strong>見落とし</strong>
          <span className="meta">仕分けが出さなかったもの。要対応だった？</span>
        </span>
        <Icon name="next" size={18} />
      </Link>

      <Link className="glass nav-card" href="/rules">
        <span className="ico">
          <Icon name="thumb" size={22} />
        </span>
        <span className="txt">
          <strong>今週の学び</strong>
          <span className="meta">判断から見つけたルール候補。採用／今回だけ／違う</span>
        </span>
        <Icon name="next" size={18} />
      </Link>

      <div className="eyebrow">IN ／ OUT</div>
      <Link className="glass nav-card" href="/312">
        <span className="ico">
          <Icon name="inbox" size={22} />
        </span>
        <span className="txt">
          <strong>312 入口</strong>
          <span className="meta">何を拾うか。追記／別作成／登録しない</span>
        </span>
        <Icon name="next" size={18} />
      </Link>
      <Link className="glass nav-card" href="/313">
        <span className="ico">
          <Icon name="done" size={22} />
        </span>
        <span className="txt">
          <strong>313 出口</strong>
          <span className="meta">片付ける。済んだ／いつ・優先／やめる</span>
        </span>
        <Icon name="next" size={18} />
      </Link>

      <div className="eyebrow">LOOP</div>
      <div className="glass loop">
        <div><span className="mono">01</span>AIが案</div>
        <div><span className="mono">02</span>人が選ぶ</div>
        <div><span className="mono">03</span>ログ</div>
        <div><span className="mono">04</span>次の案へ</div>
      </div>
      <p className="meta" style={{ marginTop: 10 }}>
        判断は Slack でもここでも同じログに残る。iPhone は Chrome で開く。
      </p>
    </main>
  );
}
