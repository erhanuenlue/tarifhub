import { NextRequest, NextResponse } from "next/server";

import { listTariffs, ServingError } from "@/lib/api";

/**
 * Server-side proxy for browsing the latest frozen record per (system, code), optionally
 * filtered by system. Relays serving verbatim; the console never alters a value.
 */
export async function GET(req: NextRequest) {
  const system = req.nextUrl.searchParams.get("system")?.trim() || undefined;
  const limitParam = Number(req.nextUrl.searchParams.get("limit"));
  const limit = Number.isFinite(limitParam) && limitParam > 0 ? Math.min(limitParam, 50) : 25;
  try {
    const records = await listTariffs({ system, limit });
    return NextResponse.json(records);
  } catch (err) {
    const status = err instanceof ServingError ? 502 : 500;
    return NextResponse.json({ error: String((err as Error).message) }, { status });
  }
}
