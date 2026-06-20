import { NextRequest, NextResponse } from "next/server";

import { getTariff, ServingError, type CodingFlag, type CodingPosition } from "@/lib/api";
import { problem } from "@/lib/problem";

/**
 * Server-side proxy for the coding-check screen.
 *
 * Serving exposes no combinability endpoint, so this is a STRUCTURAL check only: each
 * position is looked up via GET /api/v1/tariffs/{system}/{code} and reported with
 * frozen-record facts — found / requires-review / outside-validity — plus the certified
 * value relayed verbatim. No combinability verdict and no billing value are computed here.
 */
export async function POST(req: NextRequest) {
  const instance = req.nextUrl.pathname;
  let positions: CodingPosition[];
  try {
    const body = await req.json();
    positions = Array.isArray(body?.positions) ? body.positions : [];
  } catch {
    return problem({ status: 400, detail: "invalid JSON body", instance });
  }
  if (positions.length === 0) {
    return problem({ status: 400, detail: "no positions supplied", instance });
  }
  // Bound the fan-out (each position is one upstream lookup) and validate element shape.
  if (positions.length > 50) {
    return problem({ status: 400, detail: "too many positions (max 50)", instance });
  }
  const wellFormed = positions.every(
    (p) => p && typeof p.system === "string" && typeof p.code === "string"
  );
  if (!wellFormed) {
    return problem({
      status: 400,
      detail: "each position needs a string system and code",
      instance,
    });
  }

  const today = new Date().toISOString().slice(0, 10);
  const flags: CodingFlag[] = [];
  try {
    for (const position of positions) {
      flags.push(await checkPosition(position, today));
    }
  } catch (err) {
    const status = err instanceof ServingError ? 502 : 500;
    return problem({ status, detail: String((err as Error).message), instance });
  }
  return NextResponse.json({ source: "structural", flags });
}

async function checkPosition(position: CodingPosition, today: string): Promise<CodingFlag> {
  try {
    const record = await getTariff(position.system, position.code);
    const outside =
      (record.valid_from !== null && record.valid_from > today) ||
      (record.valid_to !== null && record.valid_to < today);
    const messages: string[] = [];
    if (record.requires_review) messages.push("flagged for human review");
    if (outside) {
      messages.push(
        `outside validity window (${record.valid_from ?? "—"} → ${record.valid_to ?? "open"})`
      );
    }
    return {
      position,
      found: true,
      requires_review: record.requires_review,
      outside_validity: outside,
      record,
      messages,
    };
  } catch (err) {
    if (err instanceof ServingError && err.status === 404) {
      return {
        position,
        found: false,
        requires_review: false,
        outside_validity: false,
        messages: ["no frozen record for this system/code"],
      };
    }
    throw err;
  }
}
