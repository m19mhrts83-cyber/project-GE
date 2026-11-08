import Shell from "@/components/Shell";
import PurchaseCompareClient from "@/components/PurchaseCompareClient";

export default function PurchaseComparePage() {
  return (
    <Shell active="/purchase-compare">
      <h1>購入比較</h1>
      <p className="sub">
        候補を写真付きで並べて1つ選ぶか見送り、理由と購入後の感想を残すループウェア。最初のお題はシャワーヘッド（再装着済み・ヘッド単体交換可）。写真は公式URLまたは端末アップロード。保存はこの端末の
        localStorage。チャットAIへは「結果をMDでコピー」。
      </p>
      <p className="meta" style={{ marginBottom: 16 }}>
        設計: <code>docs/購入比較_ループウェア設計_20261107.md</code>
      </p>
      <PurchaseCompareClient />
    </Shell>
  );
}
