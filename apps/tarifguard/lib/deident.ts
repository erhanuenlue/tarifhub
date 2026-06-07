/**
 * ============================================================================
 *  DE-IDENTIFICATION BOUNDARY  —  the ONLY code in TarifGuard allowed to build
 *  an LLM-bound payload.  (AGENTS.md rule 7.)
 * ============================================================================
 *
 * Patient identifiers never leave Swiss infrastructure. Only de-identified coding
 * context (tariff/diagnosis codes, encounter structure) may be sent to an LLM, and
 * the request is routed via AWS Bedrock EU or Google Vertex AI EU by the backend.
 *
 * Nothing in this app may construct a prompt, an `explain` request, or any other
 * LLM-bound object except through {@link buildExplainPayload} below. The /explain
 * route handler calls this module first and forwards ONLY its output. If you find
 * yourself building an LLM payload anywhere else, stop — it belongs here.
 *
 * This is a deterministic, regex-based scrubber: it removes direct identifiers and
 * keeps the coding structure an explanation needs. It is intentionally conservative
 * (over-redact rather than leak) and does not, and must not, call any model itself.
 *
 * Tariff/diagnosis codes (e.g. 00.0010, AA.00.0010, M54.5) are single-separator or
 * letter-prefixed and are deliberately preserved; dates (two separators) and bare
 * 8+ digit IDs are redacted.
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
  // field separator (comma/semicolon/newline) — bounded so it cannot swallow a whole
  // single-line encounter (and the tariff/diagnosis codes within it).
  {
    name: "labelled-name",
    pattern: /\b(?:name|patient(?:in)?|versicherte[r]?|geb(?:urtsdatum)?)\s*[:=]\s*[^,;\n]+/gi,
    placeholder: "[NAME]",
  },
  // Full dates / dates of birth (two separators, three groups)
  { name: "date", pattern: /\b\d{1,2}[.\/-]\d{1,2}[.\/-]\d{2,4}\b/g, placeholder: "[DATE]" },
  // Insurance / patient card / case numbers: 8+ consecutive digits (codes have separators)
  { name: "longnumber", pattern: /\b\d{8,}\b/g, placeholder: "[ID]" },
];

export interface DeidentResult {
  /** The scrubbed text, safe to include in an LLM-bound payload. */
  text: string;
  /** Which identifier classes were found and redacted (for the audit trail / UI). */
  redactions: { rule: string; count: number }[];
}

/**
 * Strip direct identifiers from free text while preserving coding structure.
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
 * THE ONLY sanctioned constructor of an LLM-bound payload in TarifGuard.
 *
 * @param code      a tariff/diagnosis code (non-identifying by nature) — passed through
 * @param question  the user's natural-language question — de-identified
 * @param context   optional free-text encounter context — de-identified
 */
export function buildExplainPayload(args: {
  code?: string;
  question?: string;
  context?: string;
}): {
  payload: { code?: string; question?: string; context?: string };
  redactions: { rule: string; count: number }[];
} {
  const q = args.question ? deidentify(args.question) : undefined;
  const ctx = args.context ? deidentify(args.context) : undefined;

  const redactions = [...(q?.redactions ?? []), ...(ctx?.redactions ?? [])];
  return {
    payload: {
      code: args.code?.trim() || undefined,
      question: q?.text,
      context: ctx?.text,
    },
    redactions,
  };
}
