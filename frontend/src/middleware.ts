import { NextRequest, NextResponse } from "next/server";

/**
 * Runtime reverse-proxy for /api and /health so the desktop shell can pick free ports.
 * Enabled when API_INTERNAL_URL or DESKTOP_RUNTIME_PROXY is set; otherwise fall through
 * to next.config.js rewrites (dev / docker).
 */
export function middleware(request: NextRequest) {
  const enabled =
    process.env.DESKTOP_RUNTIME_PROXY === "1" || Boolean(process.env.API_INTERNAL_URL);
  if (!enabled) {
    return NextResponse.next();
  }

  const backend = (
    process.env.API_INTERNAL_URL ||
    process.env.NEXT_PUBLIC_API_URL ||
    "http://127.0.0.1:8000"
  ).replace(/\/$/, "");

  const { pathname, search } = request.nextUrl;
  return NextResponse.rewrite(new URL(`${backend}${pathname}${search}`));
}

export const config = {
  matcher: ["/api/:path*", "/health", "/health/:path*"],
};
