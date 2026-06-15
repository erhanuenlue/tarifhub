// KassenFlow landing — purpose + scope / "coming in development" screen.
// This is a stub: it ships the planned scope, not working screens. KassenFlow will be a
// thin, read-only client over the deterministic tarifhub serving API (L1) and TarifIQ
// rules (L2); it computes no billing value of its own.

const PLANNED_SCREENS = [
  {
    title: "Kostengutsprache requests",
    body: "Assemble cost-approval / prior-authorization requests to insurers, grounded in frozen tariff positions and TarifIQ combinability checks. Draft text is de-identified before any LLM assist.",
  },
  {
    title: "MiGeL & medication approvals",
    body: "Track medical-device (MiGeL) and medication approval cases, their required evidence, and payer decisions across a case timeline.",
  },
  {
    title: "Multi-payer correspondence inbox",
    body: "One inbox for insurer queries and structured responses across multiple payers, with the source tariff/contract context attached.",
  },
];

export default function HomePage() {
  return (
    <div className="space-y-6">
      <section>
        <h1 className="text-2xl font-semibold text-slate-900">
          KassenFlow — payer correspondence &amp; Kostengutsprache
        </h1>
        <p className="mt-2 max-w-2xl text-sm text-slate-600">
          KassenFlow automates the back-and-forth with health insurers: cost-approval
          (Kostengutsprache) requests, MiGeL and medication approvals, and multi-payer
          query handling. It is a Layer-3 app on the tarifhub platform — read-only over the
          deterministic serving API (L1) and the TarifIQ rule engine (L2), so it never
          computes or mutates a billing value itself.
        </p>
      </section>

      <section className="rounded-lg border border-amber-200 bg-amber-50 p-4 text-sm text-amber-900">
        <p className="font-semibold">Scope — coming in development</p>
        <p className="mt-1">
          This is a skeleton stub. The screens below describe the planned scope; none are
          wired yet. Patient identifiers never leave Swiss infrastructure: any LLM-assisted
          drafting sends only de-identified context, built exclusively by{" "}
          <code className="rounded bg-amber-100 px-1">lib/deident.ts</code>.
        </p>
      </section>

      <section className="grid gap-4 sm:grid-cols-3">
        {PLANNED_SCREENS.map((screen) => (
          <div
            key={screen.title}
            className="rounded-lg border border-slate-200 bg-white p-4"
          >
            <div className="mb-1 text-xs font-medium uppercase tracking-wide text-brand">
              Planned
            </div>
            <h2 className="font-semibold text-slate-900">{screen.title}</h2>
            <p className="mt-1 text-sm text-slate-600">{screen.body}</p>
          </div>
        ))}
      </section>
    </div>
  );
}
