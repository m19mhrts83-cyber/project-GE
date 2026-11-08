import ZaimClient from "@/components/ZaimClient";

export const metadata = { title: "Zaim の見直し｜ループウェア" };
export const dynamic = "force-dynamic";

export default function ZaimPage() {
  return (
    <main>
      <ZaimClient />
    </main>
  );
}
