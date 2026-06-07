/**
 * Standing reminder of the two boundaries TarifGuard operates under. Shown on every
 * screen that touches values or the LLM seam.
 */
export function DisclaimerBanner() {
  return (
    <p className="rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-800">
      TarifGuard displays unaltered frozen records from the deterministic TarifHub
      serving API. It never computes or mutates a billing value. Any natural-language
      explanation runs on de-identified coding context only, routed via an EU-resident
      model — patient identifiers never leave Swiss infrastructure.
    </p>
  );
}
