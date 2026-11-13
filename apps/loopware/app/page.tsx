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

      <Link className="glass nav-card" href="/drafts">
        <span className="ico">
          <Icon name="mic" size={22} />
        </span>
        <span className="txt">
          <strong>下書きを直す</strong>
          <span className="meta">箇所を選んで声でダメ出し → AI が直す → 差分で確認</span>
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

      <Link className="glass nav-card" href="/zaim">
        <span className="ico">
          <Icon name="check" size={22} />
        </span>
        <span className="txt">
          <strong>Zaim の見直し</strong>
          <span className="meta">学習で直した費目。正しい／違う</span>
        </span>
        <Icon name="next" size={18} />
      </Link>

      <div className="eyebrow">IN ／ OUT</div>
      <Link className="glass nav-card" href="/week">
        <span className="ico">
          <Icon name="calendar" size={22} />
        </span>
        <span className="txt">
          <strong>今週の9件</strong>
          <span className="meta">日曜の夜に。残った理由→おすすめを直して月・水・金に置く</span>
        </span>
        <Icon name="next" size={18} />
      </Link>
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

      <div className="eyebrow">資料</div>
      <Link className="glass nav-card" href="/slides">
        <span className="ico">
          <Icon name="list" size={22} />
        </span>
        <span className="txt">
          <strong>資料づくり</strong>
          <span className="meta">構成案を選ぶ／直しから次回の基準を決める</span>
        </span>
        <Icon name="next" size={18} />
      </Link>

      <div className="eyebrow">画面</div>
      <Link className="glass nav-card" href="/uiux">
        <span className="ico">
          <Icon name="list" size={22} />
        </span>
        <span className="txt">
          <strong>画面の好み</strong>
          <span className="meta">画面の案を 良い／違う で選ぶ／好み帳を育てる</span>
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
