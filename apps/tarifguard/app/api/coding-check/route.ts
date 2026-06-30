import { NextRequest, NextResponse } from "next/server";
import { z } from "zod";

import { getTariff, ServingError, type CodingFlag, type CodingPosition } from "@/lib/api";
import { problem, problemFromZod } from "@/lib/problem";

/**
 * Server-side proxy for the coding-check screen.
 *
 * Serving exposes no combinability endpoint, so this is a STRUCTURAL check only: each
 * position is looked up via GET /api/v1/tariffs/{system}/{code} and reported with
 * frozen-record facts — found / requires-review / outside-validity — plus the certified
 * value relayed verbatim. No combinability verdict and no billing value are computed here.
 */
/**
 * Runtime schema for the coding-check request body. Each position is one upstream lookup, so
 * the fan-out is bounded to 50, and every element must carry a string system and code.
 */
const CodingCheckBody = z.object({
  positions: z
    .array(z.object({ system: z.string(), code: z.string() }))
    .min(1, "no positions supplied")
    .max(50, "too many positions (max 50)"),
});

export async function POST(req: NextRequest) {
  const instance = req.nextUrl.pathname;
  let raw: unknown;
  try {
    raw = await req.json();
  } catch {
    return problem({ status: 400, detail: "invalid JSON body", instance });
  }
  // Validate the untrusted body against the runtime schema rather than hand-rolled typeof
  // checks; a failure returns the shared RFC 7807 problem+json 400.
  const parsed = CodingCheckBody.safeParse(raw);
  if (!parsed.success) {
    return problemFromZod(parsed.error, instance);
  }
  const positions: CodingPosition[] = parsed.data.positions;

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
