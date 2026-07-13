import { NextResponse } from "next/server";

type RouteHandlerFn = (
  req: Request,
  ctx: { params: Promise<Record<string, string>> }
) => Promise<NextResponse>;

export function withErrorHandler(handler: RouteHandlerFn): RouteHandlerFn {
  return async (req, ctx) => {
    try {
      return await handler(req, ctx);
    } catch (err: any) {
      const status = typeof err?.status === "number" ? err.status : 500;
      const message = err?.message || "Internal Server Error";
      return NextResponse.json({ errorMessage: message }, { status });
    }
  };
}
