import { NextRequest, NextResponse } from "next/server";

import { searchTariffs, ServingError } from "@/lib/api";

/**
 * Server-side proxy for semantic tariff search.
 *
 * The browser calls this same-origin handler so SERVING_BASE_URL never reaches the
 * client. It relays the deterministic serving result verbatim — no re-ranking, no
 * value computation.
 */
export async function GET(req: NextRequest) {
  const q = req.nextUrl.searchParams.get("q")?.trim();
  const system = req.nextUrl.searchParams.get("system")?.trim() || undefined;
  if (!q) {
    return NextResponse.json({ error: "missing query parameter 'q'" }, { status: 400 });
  }
  try {
    const hits = await searchTariffs(q, { system, limit: 10 });
    return NextResponse.json(hits);
  } catch (err) {
    const status = err instanceof ServingError ? 502 : 500;
    return NextResponse.json({ error: String((err as Error).message) }, { status });
  }
}
