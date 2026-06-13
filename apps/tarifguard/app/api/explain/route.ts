import { NextRequest, NextResponse } from "next/server";

import { getExplain, ServingError } from "@/lib/api";
import { buildExplainPayload } from "@/lib/deident";

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
  let input: { code?: string; context?: string };
  try {
    input = await req.json();
  } catch {
    return NextResponse.json({ error: "invalid JSON body" }, { status: 400 });
  }

  const code = input.code?.trim();
  if (!code) {
    return NextResponse.json({ error: "missing tariff code" }, { status: 400 });
  }

  // The de-identification checkpoint: the optional context is scrubbed for the audit and
  // never leaves the server. Only the bare code reaches the backend explain seam.
  const { payload, redactions } = buildExplainPayload({ context: input.context });
  const deident = { scrubbed: payload.context ?? null, redactions };

  try {
    const result = await getExplain(code);
    return NextResponse.json({ ...result, deident });
  } catch (err) {
    if (err instanceof ServingError && err.status === 404) {
      return NextResponse.json(
        { error: `no frozen record for code ${code}`, deident },
        { status: 404 }
      );
    }
    const status = err instanceof ServingError ? 502 : 500;
    return NextResponse.json({ error: String((err as Error).message), deident }, { status });
  }
}
