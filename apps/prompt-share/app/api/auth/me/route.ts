import { NextResponse } from "next/server";
import { getSessionUser } from "@/lib/authz";

export const runtime = "nodejs";

export async function GET(req: Request) {
  const user = getSessionUser(req);
  if (!user || user.role !== "admin" || user.status !== "approved") {
    return NextResponse.json({ user: null });
  }
  return NextResponse.json({ user });
}
