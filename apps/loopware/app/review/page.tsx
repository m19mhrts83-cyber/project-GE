import Link from "next/link";
import ReviewClient from "@/components/ReviewClient";
import Icon from "@/components/Icon";

export default function ReviewPage() {
  return (
    <main>
      <div className="top">
        <Link className="back" href="/" aria-label="ハブへ戻る">
          <Icon name="back" size={22} />
        </Link>
        <div className="grow">
          <div className="eyebrow acc">REVIEW ／ 週1</div>
          <h1>判断ログを確認して基準を更新</h1>
        </div>
      </div>
      <ReviewClient />
    </main>
  );
}
