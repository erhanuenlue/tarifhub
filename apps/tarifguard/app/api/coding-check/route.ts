import { NextRequest, NextResponse } from "next/server";

import {
  checkCoding,
  getTariff,
  ServingError,
  type CodingFlag,
  type CodingPosition,
} from "@/lib/api";

/**
 * Server-side proxy for the coding-check screen.
 *
 * Combinability/validation is a DETERMINISTIC, backend-owned concern: this handler
 * prefers the serving `POST /api/v1/coding-check` endpoint and relays its flags
 * verbatim. If that endpoint is not present in the running serving build, it falls
 * back to a structural lookup of each position via GET /api/v1/tariffs/{system}/{code}
 * — reporting only frozen-record facts (found / requires-review / outside validity).
 * Neither path computes a billing value or a combinability verdict in the app.
 */
export async function POST(req: NextRequest) {
  let positions: CodingPosition[];
  try {
    const body = await req.json();
    positions = Array.isArray(body?.positions) ? body.positions : [];
  } catch {
    return NextResponse.json({ error: "invalid JSON body" }, { status: 400 });
  }
  if (positions.length === 0) {
    return NextResponse.json({ error: "no positions supplied" }, { status: 400 });
  }

  try {
    const flags = await checkCoding(positions);
    return NextResponse.json({ source: "serving", flags });
  } catch (err) {
    // 404/405 => combinability endpoint not in this build: degrade to per-position lookup.
    if (err instanceof ServingError && (err.status === 404 || err.status === 405)) {
      const flags = await structuralFallback(positions);
      return NextResponse.json({ source: "structural-fallback", flags });
    }
    const status = err instanceof ServingError ? 502 : 500;
    return NextResponse.json({ error: String((err as Error).message) }, { status });
  }
}

/** Frozen-record structural checks only — no combinability logic lives here. */
async function structuralFallback(positions: CodingPosition[]): Promise<CodingFlag[]> {
  const today = new Date().toISOString().slice(0, 10);
  const results: CodingFlag[] = [];
  for (const position of positions) {
    try {
      const record = await getTariff(position.system, position.code);
      const outsideValidity =
        (record.validFrom !== null && record.validFrom > today) ||
        (record.validTo !== null && record.validTo < today);
      results.push({
        position,
        found: true,
        requiresReview: record.requiresReview,
        outsideValidity,
        messages: [],
        record,
      });
    } catch (err) {
      if (err instanceof ServingError && err.status === 404) {
        results.push({
          position,
          found: false,
          requiresReview: false,
          outsideValidity: false,
          messages: ["no frozen record for this system/code"],
        });
      } else {
        throw err;
      }
    }
  }
  return results;
}
