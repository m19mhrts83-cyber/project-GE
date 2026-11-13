import UiuxClient from "@/components/UiuxClient";

export const metadata = { title: "画面の好み｜ループウェア" };
export const dynamic = "force-dynamic";

export default function UiuxPage() {
  return (
    <main>
      <UiuxClient />
    </main>
  );
}
