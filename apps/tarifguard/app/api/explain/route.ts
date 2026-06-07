import { NextRequest, NextResponse } from "next/server";

import { explain, ServingError } from "@/lib/api";
import { buildExplainPayload } from "@/lib/deident";

/**
 * Server-side proxy for the /explain screen.
 *
 * This is the de-identification choke point. Raw user input is scrubbed by
 * lib/deident.ts BEFORE anything is forwarded; only the de-identified payload reaches
 * the serving explanation endpoint (whose LLM seam is routed via AWS Bedrock EU /
 * Google Vertex AI EU). The returned explanation is grounded in frozen records and
 * never invents a value.
 */
export async function POST(req: NextRequest) {
  let input: { code?: string; question?: string; context?: string };
  try {
    input = await req.json();
  } catch {
    return NextResponse.json({ error: "invalid JSON body" }, { status: 400 });
  }

  // The ONLY place an LLM-bound payload is built (AGENTS.md rule 7).
  const { payload, redactions } = buildExplainPayload(input);

  try {
    const result = await explain(payload);
    // Echo what was redacted so the UI can prove de-identification happened.
    return NextResponse.json({ ...result, redactions, sentPayload: payload });
  } catch (err) {
    if (err instanceof ServingError && (err.status === 404 || err.status === 405)) {
      return NextResponse.json(
        {
          error:
            "the deterministic explanation endpoint (/api/v1/explain) is not available " +
            "in this serving build yet",
          redactions,
          sentPayload: payload,
        },
        { status: 501 }
      );
    }
    const status = err instanceof ServingError ? 502 : 500;
    return NextResponse.json({ error: String((err as Error).message) }, { status });
  }
}
