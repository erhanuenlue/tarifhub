import Link from "next/link";

import { AiContent, CertifiedValue, HashChip, VersionChip } from "@/components/brand";
import { DisclaimerBanner } from "@/components/DisclaimerBanner";

const SURFACES = [
  {
    href: "/search",
    title: "Search → detail",
    body: "Semantic and code search over frozen records; open one to see the certified value, provenance and version history.",
  },
  {
    href: "/review",
    title: "Review",
    body: "The human-in-the-loop: flagged records show the raw extract beside the AI proposal; approve or correct, then the record is frozen.",
  },
  {
    href: "/explain",
    title: "Explain",
    body: "A plain-language, record-grounded explanation on a clearly labelled AI surface. Input is a tariff code only.",
  },
  {
    href: "/coding-check",
    title: "Coding check",
    body: "Paste coded positions and see structural validity and review flags, read straight from frozen records.",
  },
];

export default function HomePage() {
  return (
    <div className="space-y-8">
      <section>
        <h1 className="text-2xl font-semibold text-navy">TarifGuard Console</h1>
        <p className="mt-2 max-w-2xl text-sm leading-relaxed text-body">
          The trust surface of the TarifHub platform: a thin, read-only client over the
          deterministic serving API. Every billing value shown is an unaltered frozen
          record. The console computes nothing of its own.
        </p>
      </section>

      <DisclaimerBanner />

      {/* Visual-law legend — the one rule a reader must hold in their head. */}
      <section className="rounded-lg border border-line bg-card p-5">
        <h2 className="text-xs font-semibold uppercase tracking-wide text-muted">
          How to read this console
        </h2>
        <div className="mt-3 grid gap-4 sm:grid-cols-2">
          <div className="space-y-1">
            <p className="text-sm font-medium text-navy">Frozen = certified</p>
            <p className="text-xs text-body">
              Deterministic billing values are navy mono with version and hash chips:
            </p>
            <p className="flex items-center gap-2 pt-1">
              <CertifiedValue value="10.10" unit="TP" />
              <VersionChip version={2} />
              <HashChip hash="a1b2c3d4e5f6a1b2c3d4" />
            </p>
          </div>
          <div className="space-y-1">
            <p className="text-sm font-medium text-navy">AI = labelled, never a value</p>
            <AiContent>
              <p className="text-sm">
                AI output always lives on this slate surface, behind its own label. It never
                looks like, or stands in for, a frozen value.
              </p>
            </AiContent>
          </div>
        </div>
      </section>

      <section className="grid gap-4 sm:grid-cols-2">
        {SURFACES.map((s) => (
          <Link
            key={s.href}
            href={s.href}
            className="rounded-lg border border-line bg-card p-4 transition hover:border-sky hover:shadow-sm"
          >
            <h2 className="font-semibold text-navy">{s.title}</h2>
            <p className="mt-1 text-sm leading-relaxed text-body">{s.body}</p>
          </Link>
        ))}
      </section>
    </div>
  );
}
