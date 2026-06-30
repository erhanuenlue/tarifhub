import { NextRequest } from "next/server";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { POST as codingCheckPOST } from "@/app/api/coding-check/route";
import { POST as explainPOST } from "@/app/api/explain/route";
import { POST as reviewPOST } from "@/app/api/review/route";

/**
 * Every BFF route that accepts a body now validates it with a zod schema and returns the
 * shared RFC 7807 problem+json 400 on failure. These tests prove, per converted route, that
 * a shape-malformed body is rejected with the consistent envelope and that a valid body
 * still passes through (upstream fetch stubbed, mirroring review-route.test.ts).
 */

const fetchMock = vi.fn();

function post(path: string, body: unknown): NextRequest {
  return new NextRequest(`http://localhost${path}`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: typeof body === "string" ? body : JSON.stringify(body),
  });
}

function okJson(body: unknown, status = 200) {
  return { ok: status >= 200 && status < 300, status, json: async () => body };
}

/** Assert the response is the shared RFC 7807 problem+json 400 and return its body. */
async function expectProblem400(res: Response): Promise<Record<string, unknown>> {
  expect(res.status).toBe(400);
  expect(res.headers.get("content-type")).toContain("application/problem+json");
  const body = await res.json();
  expect(body).toMatchObject({
    type: expect.any(String),
    title: expect.any(String),
    status: 400,
    detail: expect.any(String),
    instance: expect.any(String),
  });
  return body;
}

beforeEach(() => {
  vi.stubGlobal("fetch", fetchMock);
  fetchMock.mockReset();
  process.env.SERVING_BASE_URL = "https://serving.internal";
  delete process.env.INGEST_BASE_URL;
});

afterEach(() => {
  vi.unstubAllGlobals();
  delete process.env.SERVING_BASE_URL;
});

describe("coding-check BFF route validation", () => {
  it("rejects a non-array positions field with 400 problem+json", async () => {
    const res = await codingCheckPOST(post("/api/coding-check", { positions: "nope" }));
    const body = await expectProblem400(res);
    expect(body.instance).toBe("/api/coding-check");
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("rejects an empty positions list with 400 (no positions supplied)", async () => {
    const res = await codingCheckPOST(post("/api/coding-check", { positions: [] }));
    const body = await expectProblem400(res);
    expect(String(body.detail)).toContain("no positions supplied");
  });

  it("rejects a position whose system is not a string with 400", async () => {
    const res = await codingCheckPOST(
      post("/api/coding-check", { positions: [{ system: 123, code: "0010.00" }] })
    );
    await expectProblem400(res);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("accepts a well-formed positions list and returns the structural flags", async () => {
    fetchMock.mockResolvedValue(
      okJson({ valid_from: null, valid_to: null, requires_review: false })
    );
    const res = await codingCheckPOST(
      post("/api/coding-check", { positions: [{ system: "EAL", code: "0010.00" }] })
    );
    const body = await res.json();
    expect(res.status).toBe(200);
    expect(body.source).toBe("structural");
    expect(body.flags).toHaveLength(1);
    expect(body.flags[0].found).toBe(true);
  });
});

describe("explain BFF route validation", () => {
  it("rejects a body with no tariff code with 400 problem+json", async () => {
    const res = await explainPOST(post("/api/explain", {}));
    const body = await expectProblem400(res);
    expect(body.instance).toBe("/api/explain");
    // Quote one rejection: the missing-code body is the shared envelope end to end.
    expect(String(body.detail)).toContain("missing tariff code");
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("rejects a blank (whitespace-only) tariff code with 400", async () => {
    const res = await explainPOST(post("/api/explain", { code: "   " }));
    await expectProblem400(res);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("accepts a valid code and returns the explanation plus de-identification audit", async () => {
    fetchMock.mockResolvedValue(
      okJson({ code: "0010.00", records: [], explanation: "[deterministic] grounded explanation" })
    );
    const res = await explainPOST(post("/api/explain", { code: "0010.00" }));
    const body = await res.json();
    expect(res.status).toBe(200);
    expect(body.explanation).toContain("deterministic");
    expect(body.deident).toBeDefined();
  });
});

describe("review BFF route validation", () => {
  it("rejects a decision missing tariff_system / tariff_code with 400 problem+json", async () => {
    const res = await reviewPOST(post("/api/review", { action: "approve" }));
    const body = await expectProblem400(res);
    expect(body.instance).toBe("/api/review");
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("rejects an unknown action with 400", async () => {
    const res = await reviewPOST(
      post("/api/review", {
        tariff_system: "EAL",
        tariff_code: "0010.00",
        record_hash: null,
        action: "delete",
      })
    );
    await expectProblem400(res);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("accepts a valid approve decision and freezes offline (no fetch)", async () => {
    const res = await reviewPOST(
      post("/api/review", {
        tariff_system: "EAL",
        tariff_code: "0010.00",
        record_hash: null,
        action: "approve",
      })
    );
    const body = await res.json();
    expect(res.status).toBe(200);
    expect(body.frozen).toBe(true);
    expect(body.action).toBe("approve");
    expect(fetchMock).not.toHaveBeenCalled();
  });
});

describe("validation hardening (post-review)", () => {
  it("caps the error detail for a large malformed positions array (no amplification)", async () => {
    const positions = Array.from({ length: 60 }, () => ({}));
    const res = await codingCheckPOST(post("/api/coding-check", { positions }));
    const body = await expectProblem400(res);
    // The detail is bounded with a "(+N more)" suffix rather than one issue per bad element:
    // at most 10 field paths are listed however many elements are malformed.
    expect(String(body.detail)).toContain("(+");
    const pathCount = (String(body.detail).match(/positions\./g) || []).length;
    expect(pathCount).toBeLessThanOrEqual(10);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("rejects too many well-formed positions with a single clean message", async () => {
    const positions = Array.from({ length: 51 }, () => ({ system: "EAL", code: "0010.00" }));
    const res = await codingCheckPOST(post("/api/coding-check", { positions }));
    const body = await expectProblem400(res);
    expect(String(body.detail)).toContain("too many positions (max 50)");
    expect(String(body.detail)).not.toContain("(+");
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("accepts a review decision that omits record_hash (lenient, matches the backend)", async () => {
    const res = await reviewPOST(
      post("/api/review", { tariff_system: "EAL", tariff_code: "0010.00", action: "approve" })
    );
    const body = await res.json();
    expect(res.status).toBe(200);
    expect(body.frozen).toBe(true);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("names the missing field in the review 400 detail", async () => {
    const res = await reviewPOST(post("/api/review", { action: "approve" }));
    const body = await expectProblem400(res);
    expect(String(body.detail)).toContain("tariff_system");
  });
});
