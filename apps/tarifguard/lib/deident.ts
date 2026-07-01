/**
 * ============================================================================
 *  DE-IDENTIFICATION CHECKPOINT: the ONLY code in TarifGuard that scrubs
 *  optional free-text clinical context.  (AGENTS.md rule 7.)
 * ============================================================================
 *
 * This module scrubs optional free-text clinical context so it can be shown to
 * the reviewer as a de-identification audit. The scrubbed context is NEVER
 * forwarded anywhere. The explain seam sends the tariff code only to the
 * deterministic, record-grounded serving endpoint GET /api/v1/explain
 * (ADR-017), which is not an LLM call.
 *
 * AWS Bedrock EU / Google Vertex AI EU is a data-residency design boundary for a
 * future L3 patient-facing app (ADR-012), not the current explain feature.
 *
 * Nothing in this app may construct the de-identification audit object except
 * through {@link buildExplainPayload} below. The explain route handler calls this
 * module first and forwards ONLY the tariff code to serving. If you find yourself
 * scrubbing clinical context anywhere else, stop, it belongs here.
 *
 * This is a deterministic, regex-based scrubber: it removes direct identifiers and
 * keeps the coding structure the audit needs. It is intentionally conservative
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
  /** The scrubbed text, shown in the de-identification audit and never forwarded to a model. */
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
 * THE ONLY sanctioned builder of the console's de-identification audit in TarifGuard.
 * The scrubbed question/context populate the audit only and are never forwarded to a
 * model. Only `code` reaches the deterministic serving explain endpoint (ADR-017).
 *
 * @param code      a tariff/diagnosis code (non-identifying by nature), passed through to serving
 * @param question  the user's natural-language question, de-identified for the audit
 * @param context   optional free-text encounter context, de-identified for the audit
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
