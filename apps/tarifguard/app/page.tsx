import Link from "next/link";

import { DisclaimerBanner } from "@/components/DisclaimerBanner";

const SCREENS = [
  {
    href: "/search",
    title: "Tariff search",
    body: "Semantic search over frozen TARMED / TARDOC records via the serving API.",
  },
  {
    href: "/coding-check",
    title: "Coding check",
    body: "Paste coded encounter positions and see the backend's combinability and validation flags.",
  },
  {
    href: "/explain",
    title: "Explain",
    body: "Plain-language explanation and TARMED↔TARDOC cross-walk over de-identified input.",
  },
];

export default function HomePage() {
  return (
    <div className="space-y-6">
      <section>
        <h1 className="text-2xl font-semibold text-slate-900">TarifGuard</h1>
        <p className="mt-2 max-w-2xl text-sm text-slate-600">
          The practice-facing module of the TarifHub platform. TarifGuard is a thin,
          read-only client over the deterministic serving API — three focused screens,
          no billing logic of its own.
        </p>
      </section>

      <DisclaimerBanner />

      <section className="grid gap-4 sm:grid-cols-3">
        {SCREENS.map((screen) => (
          <Link
            key={screen.href}
            href={screen.href}
            className="rounded-lg border border-slate-200 bg-white p-4 transition hover:border-brand hover:shadow-sm"
          >
            <h2 className="font-semibold text-brand-dark">{screen.title}</h2>
            <p className="mt-1 text-sm text-slate-600">{screen.body}</p>
          </Link>
        ))}
      </section>
    </div>
  );
}
