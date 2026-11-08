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
          <div className="eyebrow acc">NODY</div>
          <strong>Nody</strong>
        </div>
      </div>

      <FocusCard />

      <div className="eyebrow">IN ／ OUT</div>
      <Link className="glass nav-card" href="/312">
        <span className="ico">
          <Icon name="inbox" size={22} />
        </span>
        <span className="txt">
          <strong>312 入口</strong>
          <span className="meta">いろんなソースから提案を仕分ける。採る／見送る／保留</span>
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

      <Link className="glass nav-card" href="/review">
        <span className="ico">
          <Icon name="clock" size={22} />
        </span>
        <span className="txt">
          <strong>週1のレビュー</strong>
          <span className="meta">判断ログを確認して、基準を更新する</span>
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
