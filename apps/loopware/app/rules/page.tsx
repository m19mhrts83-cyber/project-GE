import RulesClient from "@/components/RulesClient";

export const metadata = { title: "ルール候補｜ループウェア" };
export const dynamic = "force-dynamic";

export default function RulesPage() {
  return (
    <main>
      <RulesClient />
    </main>
  );
}
