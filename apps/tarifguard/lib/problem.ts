import { NextResponse } from "next/server";

/**
 * Consistent RFC 7807 error envelope for the BFF, matching the Python services.
 *
 * Every API route in this app returns failures as `application/problem+json` with the same
 * members the serving / ingestion / intelligence services emit: `type`, `title`, `status`,
 * `detail`, `instance`. There are two shapes of failure:
 *
 *   - The BFF's OWN errors (a malformed request body, a billing-field guard, an unreachable
 *     upstream): build a problem document here with {@link problem}.
 *   - An upstream Python-service failure on a proxy route: surface the upstream body and
 *     status verbatim with {@link upstreamProblem} — the upstream already speaks problem+json,
 *     so the console sees ONE envelope end to end, never a re-wrapped or masked error.
 *
 * The console never invents a billing value, and an error envelope never carries one.
 */

export const PROBLEM_CONTENT_TYPE = "application/problem+json";
const PROBLEM_BASE = "https://tarifhub.example/problems";

const TITLES: Record<number, string> = {
  400: "Bad request",
  404: "Not found",
  409: "Conflict",
  422: "Request validation failed",
  500: "Internal server error",
  502: "Upstream service unavailable",
};

const TYPES: Record<number, string> = {
  400: `${PROBLEM_BASE}/bad-request`,
  404: `${PROBLEM_BASE}/not-found`,
  409: `${PROBLEM_BASE}/conflict`,
  422: `${PROBLEM_BASE}/validation-error`,
  500: `${PROBLEM_BASE}/internal-error`,
  502: `${PROBLEM_BASE}/upstream-unavailable`,
};

export interface ProblemInit {
  status: number;
  detail: string;
  instance: string;
  title?: string;
  type?: string;
  /** RFC 7807 extension members merged into the body (e.g. a de-identification audit). */
  extra?: Record<string, unknown>;
}

/** Build an RFC 7807 problem+json response for one of the BFF's own failures. */
export function problem({ status, detail, instance, title, type, extra }: ProblemInit): NextResponse {
  const body: Record<string, unknown> = {
    type: type ?? TYPES[status] ?? "about:blank",
    title: title ?? TITLES[status] ?? "Error",
    status,
    detail,
    instance,
    ...(extra ?? {}),
  };
  return new NextResponse(JSON.stringify(body), {
    status,
    headers: { "content-type": PROBLEM_CONTENT_TYPE },
  });
}

/**
 * Surface an upstream Python-service failure on a proxy route. The upstream already returns
 * an RFC 7807 body, so its body and status are relayed verbatim under the problem+json
 * content type. When the upstream body is missing or unparseable, a problem document is
 * synthesised from the status and `fallbackDetail` so the caller still gets the envelope.
 */
export function upstreamProblem(opts: {
  status: number;
  body: unknown;
  instance: string;
  fallbackDetail: string;
  extra?: Record<string, unknown>;
}): NextResponse {
  const { status, body, instance, fallbackDetail, extra } = opts;
  if (body && typeof body === "object") {
    const merged = extra ? { ...(body as Record<string, unknown>), ...extra } : body;
    return new NextResponse(JSON.stringify(merged), {
      status,
      headers: { "content-type": PROBLEM_CONTENT_TYPE },
    });
  }
  return problem({ status, detail: fallbackDetail, instance, extra });
}
