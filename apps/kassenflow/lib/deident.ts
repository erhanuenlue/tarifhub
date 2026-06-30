/**
 * ============================================================================
 *  DE-IDENTIFICATION SCRUBBER: KassenFlow's de-identification seam for the planned
 *  LLM-assisted drafting (tarifhub determinism / data-sovereignty rule).
 * ============================================================================
 *
 * KassenFlow drafts payer correspondence (Kostengutsprache requests, MiGeL/medication
 * approvals, multi-payer replies). Patient identifiers never leave Swiss infrastructure:
 * only de-identified case context (tariff/diagnosis codes, request structure) may be sent
 * to an LLM, and the request is routed via an EU-resident managed model (AWS Bedrock EU /
 * Google Vertex AI EU) by the backend.
 *
 * KassenFlow is a scope stub: no screen is wired yet, so nothing imports this module today.
 * When the drafting screens are built, every LLM-bound payload is intended to be assembled
 * here through {@link buildCorrespondencePayload}, keeping de-identification a single seam.
 *
 * This is a deterministic, regex-based scrubber: it removes direct identifiers and keeps
 * the coding/case structure a draft needs. It is intentionally conservative (over-redact
 * rather than leak) and does not, and must not, call any model itself. Authoritative
 * tariff values come from the serving API (L1) and combinability from TarifIQ (L2); this
 * app computes no billing value.
 *
 * Tariff/diagnosis codes (e.g. 00.0010, AA.00.0010, M54.5) are single-separator or
 * letter-prefixed and are deliberately preserved; dates (two separators) and bare 8+ digit
 * IDs are redacted.
 */

/** A direct-identifier class we redact, with the token we replace it with. */
interface Rule {
  name: string;
  pattern: RegExp;
  placeholder: string;
}

// Order matters: more specific patterns run first so they win over generic ones.
const RULES: Rule[] = [
  // Swiss AHV/AVS social-security number, e.g. 756.1234.5678.97
  { name: "ahv", pattern: /\b756[.\s]?\d{4}[.\s]?\d{4}[.\s]?\d{2}\b/g, placeholder: "[AHV]" },
  // E-mail addresses
  { name: "email", pattern: /\b[\w.+-]+@[\w-]+\.[\w.-]+\b/g, placeholder: "[EMAIL]" },
  // Swiss phone numbers (+41 / 0xx) — leading marker then nine more digits
  { name: "phone", pattern: /(?:\+41|\b0)(?:[\s./-]?\d){9}\b/g, placeholder: "[PHONE]" },
  // "Name:" / "Patient:" / "Versicherte(r):" / "geb:" labelled value up to the next
  // field separator (comma/semicolon/newline).
  {
    name: "labelled-name",
    pattern: /\b(?:name|patient(?:in)?|versicherte[r]?|geb(?:urtsdatum)?)\s*[:=]\s*[^,;\n]+/gi,
    placeholder: "[NAME]",
  },
  // Full dates / dates of birth (two separators, three groups)
  { name: "date", pattern: /\b\d{1,2}[.\/-]\d{1,2}[.\/-]\d{2,4}\b/g, placeholder: "[DATE]" },
  // Insurance / case / policy numbers: 8+ consecutive digits (codes have separators)
  { name: "longnumber", pattern: /\b\d{8,}\b/g, placeholder: "[ID]" },
];

export interface DeidentResult {
  /** The scrubbed text, safe to include in an LLM-bound payload. */
  text: string;
  /** Which identifier classes were found and redacted (for the audit trail / UI). */
  redactions: { rule: string; count: number }[];
}

/**
 * Strip direct identifiers from free text while preserving coding/case structure.
 * Pure and deterministic — the same input always yields the same output.
 */
export function deidentify(input: string): DeidentResult {
  const redactions: { rule: string; count: number }[] = [];
  let text = input ?? "";

  for (const rule of RULES) {
    let count = 0;
    text = text.replace(rule.pattern, () => {
      count += 1;
      return rule.placeholder;
    });
    if (count > 0) redactions.push({ rule: rule.name, count });
  }

  return { text: text.trim(), redactions };
}

/**
 * The intended constructor of any LLM-bound payload for KassenFlow's planned drafting.
 *
 * @param payerId    an insurer/payer reference (non-identifying for the patient)
 * @param codes      tariff/diagnosis codes (non-identifying by nature) — passed through
 * @param request    the free-text correspondence draft / request — de-identified
 */
export function buildCorrespondencePayload(args: {
  payerId?: string;
  codes?: string[];
  request?: string;
}): {
  payload: { payerId?: string; codes?: string[]; request?: string };
  redactions: { rule: string; count: number }[];
} {
  const req = args.request ? deidentify(args.request) : undefined;
  return {
    payload: {
      payerId: args.payerId?.trim() || undefined,
      codes: args.codes?.map((c) => c.trim()).filter(Boolean),
      request: req?.text,
    },
    redactions: req?.redactions ?? [],
  };
}
