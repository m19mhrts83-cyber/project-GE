import { Suspense } from "react";
import LoginClient from "./LoginClient";

export const metadata = { title: "ループウェア｜入る" };

export default function LoginPage() {
  return (
    <main>
      <Suspense>
        <LoginClient />
      </Suspense>
    </main>
  );
}
