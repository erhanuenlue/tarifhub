import type { TariffRecord } from "@/lib/api";

/**
 * Renders one frozen tariff record. Values (tax points, price) are shown exactly as
 * returned by serving — this component formats layout, never numbers.
 */
export function TariffCard({ record, rank }: { record: TariffRecord; rank?: number }) {
  return (
    <article className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
      <div className="flex items-baseline justify-between">
        <h3 className="font-mono text-sm font-semibold text-slate-900">
          {rank ? <span className="mr-2 text-slate-400">#{rank}</span> : null}
          {record.tariffSystem} {record.tariffCode}
        </h3>
        {record.requiresReview ? (
          <span className="rounded bg-amber-100 px-2 py-0.5 text-xs text-amber-800">
            requires review
          </span>
        ) : null}
      </div>

      <p className="mt-1 text-sm text-slate-700">
        {record.designationDe || record.designationFr || record.designationIt || "—"}
      </p>

      <dl className="mt-3 grid grid-cols-2 gap-x-4 gap-y-1 text-xs text-slate-600">
        <dt className="text-slate-400">Tax points</dt>
        <dd>{record.taxPoints ?? "—"}</dd>
        <dt className="text-slate-400">Price (CHF)</dt>
        <dd>{record.priceChf ?? "—"}</dd>
        <dt className="text-slate-400">Valid</dt>
        <dd>
          {record.validFrom ?? "—"} → {record.validTo ?? "open"}
        </dd>
        <dt className="text-slate-400">Source version</dt>
        <dd>{record.sourceVersion ?? "—"}</dd>
      </dl>

      <p className="mt-3 truncate font-mono text-[10px] text-slate-300" title={record.recordHash}>
        hash {record.recordHash}
      </p>
    </article>
  );
}
