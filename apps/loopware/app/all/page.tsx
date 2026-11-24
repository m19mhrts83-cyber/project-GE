import Link from "next/link";
import Icon from "@/components/Icon";
import AllClient from "@/components/AllClient";

export const metadata = { title: "まとめて判断｜Nody" };
export const dynamic = "force-dynamic";

export default function AllPage() {
  return (
    <main className="wk-main all-main">
      <div className="top">
        <Link className="back" href="/" aria-label="ホームへ戻る">
          <Icon name="back" size={22} />
        </Link>
        <div className="grow">
          <div className="eyebrow acc">ぜんぶ</div>
          <h1>まとめて判断</h1>
        </div>
      </div>
      <AllClient />
    </main>
  );
}
