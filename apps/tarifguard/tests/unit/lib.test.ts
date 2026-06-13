import { primaryValue, shortHash } from "@/lib/api";
import { makeRecord } from "./_fixtures";

describe("lib/api pure helpers", () => {
  it("shortHash truncates a SHA-256 with an ellipsis and reports unhashed for null", () => {
    expect(shortHash("a".repeat(64), 12)).toBe(`${"a".repeat(12)}…`);
    expect(shortHash("abc", 12)).toBe("abc");
    expect(shortHash(null)).toBe("unhashed");
  });

  it("primaryValue selects tax_points (TP), else price_chf (CHF), else nothing — never computes", () => {
    expect(primaryValue(makeRecord({ tax_points: "9.57", price_chf: null }))).toEqual({
      value: "9.57",
      unit: "TP",
    });
    expect(primaryValue(makeRecord({ tax_points: null, price_chf: "4.85" }))).toEqual({
      value: "4.85",
      unit: "CHF",
    });
    expect(primaryValue(makeRecord({ tax_points: null, price_chf: null }))).toEqual({
      value: null,
      unit: null,
    });
  });
});
