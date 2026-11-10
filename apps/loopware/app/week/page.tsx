import Link from "next/link";
import Icon from "@/components/Icon";
import WeekPickClient from "@/components/WeekPickClient";

export const dynamic = "force-dynamic";

export default function WeekPage() {
  return (
    <main className="wk-main">
      <div className="top">
        <Link className="back" href="/" aria-label="ハブへ戻る">
          <Icon name="back" size={22} />
        </Link>
        <div className="grow">
          <div className="eyebrow acc">週次 ／ 日曜の夜</div>
          <h1>今週の9件</h1>
        </div>
      </div>
      <WeekPickClient />
    </main>
  );
}
