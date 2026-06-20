import { NextRequest, NextResponse } from "next/server";

import { searchTariffs, ServingError } from "@/lib/api";
import { problem } from "@/lib/problem";

/**
 * Server-side proxy for semantic tariff search.
 *
 * The browser calls this same-origin handler so SERVING_BASE_URL never reaches the
 * client. It relays the deterministic serving result verbatim — no re-ranking, no value
 * computation.
 */
export async function GET(req: NextRequest) {
  const instance = req.nextUrl.pathname;
  const q = req.nextUrl.searchParams.get("q")?.trim();
  if (!q) {
    return problem({ status: 400, detail: "missing query parameter 'q'", instance });
  }
  try {
    const hits = await searchTariffs(q, { limit: 10 });
    return NextResponse.json(hits);
  } catch (err) {
    const status = err instanceof ServingError ? 502 : 500;
    return problem({ status, detail: String((err as Error).message), instance });
  }
}
