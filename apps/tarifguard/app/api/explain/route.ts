import { NextRequest, NextResponse } from "next/server";
import { z } from "zod";

import { getExplain, ServingError } from "@/lib/api";
import { buildExplainPayload } from "@/lib/deident";
import { problem, problemFromZod } from "@/lib/problem";

/**
 * Runtime schema for the explain request body. A tariff code is required (trimmed,
 * non-empty); the optional free-text context is de-identified for the audit and never
 * forwarded.
 */
const ExplainBody = z.object({
  // A missing key and a blank string both read as "missing tariff code", matching the
  // original guard (which rejected any falsy trimmed code with that one message).
  code: z.string({ error: "missing tariff code" }).trim().min(1, "missing tariff code"),
  context: z.string().optional(),
});

/**
 * Server-side proxy for the explain panel.
 *
 * The backend explain seam takes a TARIFF CODE ONLY: the code is forwarded to the
 * deterministic GET /api/v1/explain endpoint, which grounds its explanation in frozen
 * records and never invents a value. A code carries no patient data.
 *
 * The de-identification boundary (ADR-012, lib/deident.ts) is demonstrated here: any
 * optional free-text clinical context is scrubbed by lib/deident.ts and returned ONLY as
 * an audit (what was redacted). It is NEVER forwarded to the explanation endpoint — the
 * explanation is grounded in the code's frozen records, not in free text.
 */
export async function POST(req: NextRequest) {
  const instance = req.nextUrl.pathname;
  let raw: unknown;
  try {
    raw = await req.json();
  } catch {
    return problem({ status: 400, detail: "invalid JSON body", instance });
  }
  const parsed = ExplainBody.safeParse(raw);
  if (!parsed.success) {
    return problemFromZod(parsed.error, instance);
  }
  const code = parsed.data.code;

  // The de-identification checkpoint: the optional context is scrubbed for the audit and
  // never leaves the server. Only the bare code reaches the backend explain seam.
  const { payload, redactions } = buildExplainPayload({ context: parsed.data.context });
  const deident = { scrubbed: payload.context ?? null, redactions };

  try {
    const result = await getExplain(code);
    return NextResponse.json({ ...result, deident });
  } catch (err) {
    if (err instanceof ServingError && err.status === 404) {
      return problem({
        status: 404,
        detail: `no frozen record for code ${code}`,
        instance,
        extra: { deident },
      });
    }
    const status = err instanceof ServingError ? 502 : 500;
    return problem({ status, detail: String((err as Error).message), instance, extra: { deident } });
  }
}
