/**
 * ============================================================================
 *  DE-IDENTIFICATION BOUNDARY  —  the ONLY code in MeldePilot allowed to build
 *  an LLM-bound payload.  (tarifhub determinism / data-sovereignty rule.)
 * ============================================================================
 *
 * MeldePilot prepares mandatory reports and quality datasets (BFS/MARS, ANQ,
 * interRAI/BESA → cantonal). Mandatory reporting is governed and patient identifiers
 * never leave Swiss infrastructure: only de-identified context (codes, indicators,
 * structure) may be sent to an LLM — e.g. to help map fields or draft a narrative — and
 * the request is routed via an EU-resident managed model (AWS Bedrock EU / Vertex AI EU)
 * by the backend. The authoritative report payload itself is assembled deterministically.
 *
 * Nothing in this app may construct a prompt or any other LLM-bound object except through
 * {@link buildReportPayload} below. If you find yourself building an LLM payload anywhere
 * else, stop — it belongs here.
 *
 * This is a deterministic, regex-based scrubber: it removes direct identifiers and keeps
 * the reporting structure. It is intentionally conservative (over-redact rather than leak)
 * and does not, and must not, call any model itself.
 *
 * Codes/indicators (e.g. 00.0010, AA.00.0010, M54.5) are single-separator or
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
  // Case / record / policy numbers: 8+ consecutive digits (codes have separators)
  { name: "longnumber", pattern: /\b\d{8,}\b/g, placeholder: "[ID]" },
];

export interface DeidentResult {
  /** The scrubbed text, safe to include in an LLM-bound payload. */
  text: string;
  /** Which identifier classes were found and redacted (for the audit trail / UI). */
  redactions: { rule: string; count: number }[];
}

/**
 * Strip direct identifiers from free text while preserving reporting structure.
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
 * THE ONLY sanctioned constructor of an LLM-bound payload in MeldePilot.
 *
 * @param registry   the target register/report (e.g. "BFS-MARS", "ANQ", "interRAI") — non-identifying
 * @param indicators structured indicator/field codes (non-identifying) — passed through
 * @param narrative  optional free-text narrative to map/summarize — de-identified
 */
export function buildReportPayload(args: {
  registry?: string;
  indicators?: string[];
  narrative?: string;
}): {
  payload: { registry?: string; indicators?: string[]; narrative?: string };
  redactions: { rule: string; count: number }[];
} {
  const narrative = args.narrative ? deidentify(args.narrative) : undefined;
  return {
    payload: {
      registry: args.registry?.trim() || undefined,
      indicators: args.indicators?.map((i) => i.trim()).filter(Boolean),
      narrative: narrative?.text,
    },
    redactions: narrative?.redactions ?? [],
  };
}
