import Link from "next/link";

import {
  CertifiedValue,
  ConfidenceMeter,
  HashChip,
  Provenance,
  ReviewPill,
  SystemBadge,
  ValidityWindow,
  VersionChip,
} from "@/components/brand";
import { primaryValue, type TariffRecord } from "@/lib/api";

/** Read AI-harmonisation provenance out of the record's free-form metadata, safely. */
function aiProvenance(metadata: Record<string, unknown>): {
  assisted: boolean;
  fields: string[];
  model: string | null;
} {
  const assisted = metadata.ai_assisted === true;
  const fields = Array.isArray(metadata.ai_fields)
    ? (metadata.ai_fields.filter((f): f is string => typeof f === "string"))
    : [];
  const model = typeof metadata.ai_model === "string" ? metadata.ai_model : null;
  return { assisted, fields, model };
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <dt className="text-xs font-medium uppercase tracking-wide text-muted">{label}</dt>
      <dd className="mt-0.5 text-sm text-body">{children}</dd>
    </div>
  );
}

/**
 * The frozen-record detail. The certified value is the visual anchor (navy mono) with
 * version + truncated record_hash chips; everything else is provenance and context. AI
 * involvement (pre-freeze, non-billing fields only) is disclosed as a labelled note — it
 * is never blended with the certified value.
 */
export function DetailPanel({
  record,
  versions = [],
  crosswalkSystems = [],
}: {
  record: TariffRecord;
  versions?: TariffRecord[];
  crosswalkSystems?: string[];
}) {
  const { value, unit } = primaryValue(record);
  const ai = aiProvenance(record.metadata);

  return (
    <article className="space-y-6">
      <div>
        <Link href="/search" className="text-xs text-blue underline underline-offset-2 hover:text-navy">
          ← back to search
        </Link>
      </div>

      <header className="space-y-2">
        <div className="flex flex-wrap items-center gap-2">
          <SystemBadge system={record.tariff_system} />
          <span className="font-mono text-lg font-semibold text-navy">{record.tariff_code}</span>
          {record.requires_review ? <ReviewPill /> : null}
        </div>
        <h1 className="text-xl font-semibold text-navy">{record.designation.de}</h1>
      </header>

      {/* Certified value + provenance grid. */}
      <section className="grid gap-6 rounded-lg border border-line bg-card p-5 sm:grid-cols-3">
        <div className="sm:col-span-1">
          <p className="text-xs font-medium uppercase tracking-wide text-muted">Certified value</p>
          <p className="mt-1 text-2xl">
            <CertifiedValue value={value} unit={unit} ariaLabel="certified value" />
          </p>
          <p className="mt-3 flex flex-wrap items-center gap-2">
            <VersionChip version={record.version} />
            <HashChip hash={record.record_hash} />
          </p>
        </div>

        <dl className="grid grid-cols-2 gap-4 sm:col-span-2">
          <Field label="Validity">
            <ValidityWindow from={record.valid_from} to={record.valid_to} />
          </Field>
          <Field label="Category">{record.category ?? "—"}</Field>
          <Field label="Unit">{record.unit ?? "—"}</Field>
          <Field label="Provenance">
            <Provenance url={record.source_url} version={record.source_version} />
          </Field>
          <Field label="Confidence">
            <ConfidenceMeter value={record.harmonization_confidence} />
          </Field>
          <Field label="Frozen at">
            <span className="font-mono text-xs text-muted">{record.created_at}</span>
          </Field>
        </dl>
      </section>

      {/* Multilingual designation (DE canonical; FR/IT where present). */}
      {(record.designation.fr || record.designation.it) ? (
        <section className="rounded-lg border border-line bg-card p-4">
          <p className="text-xs font-medium uppercase tracking-wide text-muted">Designation</p>
          <dl className="mt-2 space-y-1 text-sm">
            <div className="flex gap-2">
              <dt className="w-8 font-mono text-muted">de</dt>
              <dd className="text-body">{record.designation.de}</dd>
            </div>
            {record.designation.fr ? (
              <div className="flex gap-2">
                <dt className="w-8 font-mono text-muted">fr</dt>
                <dd className="text-body">{record.designation.fr}</dd>
              </div>
            ) : null}
            {record.designation.it ? (
              <div className="flex gap-2">
                <dt className="w-8 font-mono text-muted">it</dt>
                <dd className="text-body">{record.designation.it}</dd>
              </div>
            ) : null}
          </dl>
        </section>
      ) : null}

      {/* Cross-walk hint: the same code defined in other tariff systems. */}
      {crosswalkSystems.length > 0 ? (
        <section className="rounded-lg border border-line border-l-2 border-l-cyan bg-card p-4">
          <p className="text-xs font-medium uppercase tracking-wide text-muted">Cross-walk</p>
          <p className="mt-1 text-sm text-body">
            Code <span className="font-mono text-navy">{record.tariff_code}</span> is also defined
            in {crosswalkSystems.map((s) => <SystemBadge key={s} system={s} />)}. See the{" "}
            <Link
              href={`/explain?code=${encodeURIComponent(record.tariff_code)}`}
              className="text-blue underline underline-offset-2 hover:text-navy"
            >
              explain panel
            </Link>{" "}
            for the grounded comparison.
          </p>
        </section>
      ) : null}

      {/* Version history (deterministic, from the explain endpoint). */}
      {versions.length > 1 ? (
        <section className="rounded-lg border border-line bg-card p-4">
          <p className="text-xs font-medium uppercase tracking-wide text-muted">
            Version history ({versions.length})
          </p>
          <ul className="mt-2 space-y-1.5">
            {versions.map((v) => {
              const pv = primaryValue(v);
              const current = v.version === record.version && v.tariff_system === record.tariff_system;
              return (
                <li
                  key={`${v.tariff_system}-${v.version}`}
                  className="flex items-center justify-between gap-2 text-sm"
                >
                  <span className="flex items-center gap-2">
                    <VersionChip version={v.version} />
                    <span className="text-body">{v.designation.de}</span>
                    {current ? <span className="text-xs text-muted">(this version)</span> : null}
                  </span>
                  <CertifiedValue value={pv.value} unit={pv.unit} />
                </li>
              );
            })}
          </ul>
        </section>
      ) : null}

      {/* AI-harmonisation provenance — disclosed, labelled, never styled as a value. */}
      {ai.assisted ? (
        <p className="rounded-md border border-line bg-bg px-3 py-2 text-xs text-muted">
          <span className="font-semibold uppercase tracking-wide text-muted">AI-assisted (pre-freeze)</span>{" "}
          non-billing fields were proposed by{" "}
          <span className="font-mono">{ai.model ?? "an AI model"}</span>
          {ai.fields.length > 0 ? <> · fields: <span className="font-mono">{ai.fields.join(", ")}</span></> : null}.
          The certified value above was never AI-computed.
        </p>
      ) : null}
    </article>
  );
}
