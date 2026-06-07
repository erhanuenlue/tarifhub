// MeldePilot landing — purpose + scope / "coming in development" screen.
// This is a stub: it ships the planned scope, not working screens. MeldePilot will be a
// thin, read-only client over the deterministic TarifHub serving API (L1) and TarifIQ
// (L2); it computes no billing value and submits no report without human sign-off.

const PLANNED_SCREENS = [
  {
    title: "BFS / MARS submissions",
    body: "Assemble structural and statistical datasets for the Federal Statistical Office (BFS) and submit via the MARS data-collection portal, with validation against the required spec.",
  },
  {
    title: "ANQ quality measures",
    body: "Prepare national quality-measurement datasets (ANQ) and track their measurement periods and submission deadlines.",
  },
  {
    title: "interRAI / BESA → cantonal",
    body: "Route long-term-care assessment data (interRAI / BESA) to the responsible cantonal authorities, mapping fields to each canton's required format.",
  },
];

export default function HomePage() {
  return (
    <div className="space-y-6">
      <section>
        <h1 className="text-2xl font-semibold text-slate-900">
          MeldePilot — mandatory reporting &amp; quality data
        </h1>
        <p className="mt-2 max-w-2xl text-sm text-slate-600">
          MeldePilot automates Switzerland&apos;s mandatory reporting and quality-data
          obligations: BFS/MARS structural and statistical returns, ANQ quality measures,
          and interRAI/BESA long-term-care data to the cantons. It is a Layer-3 app on the
          TarifHub platform — read-only over the deterministic serving API (L1) and the
          TarifIQ rule engine (L2), so it never computes or mutates a billing value, and
          submits nothing without human sign-off.
        </p>
      </section>

      <section className="rounded-lg border border-amber-200 bg-amber-50 p-4 text-sm text-amber-900">
        <p className="font-semibold">Scope — coming in development</p>
        <p className="mt-1">
          This is a skeleton stub. The screens below describe the planned scope; none are
          wired yet. Patient identifiers never leave Swiss infrastructure: any LLM-assisted
          mapping or narrative uses only de-identified context, built exclusively by{" "}
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
