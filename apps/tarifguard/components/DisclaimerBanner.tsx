/**
 * Standing reminder of the two boundaries TarifGuard operates under. Shown on every
 * screen that touches values or the explain seam. The sky accent is a signal, not a text
 * colour (visual law) — the message itself is body slate.
 */
export function DisclaimerBanner() {
  return (
    <p className="rounded-md border border-line border-l-2 border-l-sky bg-card px-3 py-2 text-xs leading-relaxed text-body">
      TarifGuard displays unaltered frozen records from the deterministic TarifHub serving
      API. It never computes or mutates a billing value. Any explanation runs on
      de-identified coding context only (server-side, <code className="font-mono">lib/deident.ts</code>);
      patient identifiers never leave Swiss infrastructure.
    </p>
  );
}
