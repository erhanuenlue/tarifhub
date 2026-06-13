# CAS scorecard reconciliation, dual-blind estimate (2026-06-13)

Internal evidence for the owner. This is an estimate, a proxy for the human grader, not the grader. No number here feeds `cas_check`, the ratchet, the green-contract or the submission.

## Method

Two graders scored the built documentation independently and blind to each other, against the official anchor rubric `docs/cas/bewertungskriterien-anker.md` (18 criteria, 100 points, conjunctive Stufenregel). Both ran the same calibration: hostile examiner, lowest defensible score, no charity for intent that is not on the page, every score citing the German anchor line and an evidence path.

- Pass A: grade-auditor, Opus 4.8, ultracode. Output: `score-opus.json` / `score-opus.md`.
- Pass B: gpt-5.5 via `codex exec -s read-only` (xhigh reasoning), independent model family, blind to Pass A. Output: `score-gpt5.json` / `score-gpt5.md`.

Backdrop: the deterministic structural floor `python3 tools/cas_check.py` reports 63 of 63 mechanically-verifiable anchor elements present (0 not due). The floor measures presence; this scorecard measures the quality and consistency the floor cannot judge.

## Per-criterion comparison

Delta is Opus minus gpt-5.5. Status: agree (delta 0), minor (delta within one point), diverge (delta greater than one point, or one grader awards full and the other flags a gap).

| # | Kriterium | max | Opus | gpt-5.5 | Δ | status |
|---|-----------|----:|-----:|--------:|---:|--------|
| 1 | Use-Cases und Anforderungen | 5 | 5 | 5 | 0 | agree |
| 2 | Qualitaetsanforderungen (NfA) nach SMART | 5 | 5 | 5 | 0 | agree |
| 3 | Vision | 5 | 5 | 5 | 0 | agree |
| 4 | Architektur (bildlich und textuell) | 7 | 7 | 4 | +3 | diverge |
| 5 | Perspektiven (Struktur, Verhalten, Interaktion) | 7 | 7 | 4 | +3 | diverge |
| 6 | Datenmodell | 3 | 3 | 3 | 0 | agree |
| 7 | Code-Struktur und Lesbarkeit | 7 | 7 | 7 | 0 | agree |
| 8 | Framework-Konzepte | 10 | 7 | 10 | -3 | diverge |
| 9 | Erkenntnisse aus der Programmierung | 3 | 3 | 3 | 0 | agree |
| 10 | Git-Repository verfuegbar | 2 | 0 | 2 | -2 | diverge |
| 11 | Abnahmekriterien | 5 | 5 | 5 | 0 | agree |
| 12 | Teststrategie | 5 | 5 | 5 | 0 | agree |
| 13 | Unit-Tests | 3 | 3 | 3 | 0 | agree |
| 14 | Test-Ergebnisse dokumentiert | 3 | 3 | 3 | 0 | agree |
| 15 | KI-Werkzeuge | 12 | 7 | 7 | 0 | agree |
| 16 | KI-Services | 6 | 6 | 6 | 0 | agree |
| 17 | Container und Sub-Systeme | 5 | 5 | 5 | 0 | agree |
| 18 | Fazit | 7 | 7 | 4 | +3 | diverge |
| | **Total** | **100** | **90** | **86** | | |

Implied Swiss grade band (grade = 1 + 5 * points/100): Opus **5.5**, gpt-5.5 **5.3**. Both sit in the gut-bis-sehr-gut range and well above the 4.0 pass line; the top band (5.7 to 6.0) needs roughly 94 points.

Area subtotals expose where the two families disagree:

| Bereich | max | Opus | gpt-5.5 |
|---|----:|----:|--------:|
| Spezifikation (1 to 3) | 15 | 15 | 15 |
| Entwurf (4 to 6) | 17 | 17 | 11 |
| Programmierung (7 to 10) | 22 | 17 | 22 |
| Validierung (11 to 14) | 16 | 16 | 16 |
| KI und Architektur (15 to 18) | 30 | 25 | 22 |

The four-point total spread comes entirely from the five divergent criteria, and the two graders push in opposite directions: Opus is harsher on Programmierung (it zeroes C10 and docks C8), gpt-5.5 is harsher on Entwurf (it docks C4 and C5). They agree on 13 of 18 criteria, including all of Spezifikation and all of Validierung, and including the single largest structural gap (C15).

## Ranked point-lift list

Ordered by points recoverable per unit of effort. Divergences rank high because they mark criteria a real grader could read either way, so a small wording or evidence change moves the score.

1. **C15 KI-Werkzeuge, up to 5 points. Flagged by both graders (agreement).**
   Both stop at 7/12 for the same reason: the per-phase evidence (Generierung, Review, Refactoring, Recherche) is at the vollständig standard with prompts, diffs and commit refs, but the conjunctive top anchor also requires the Erklaerung der Eigenstaendigkeit "vollstaendig", and it is an explicit unsigned placeholder.
   Fix: the owner writes and signs the final Erklaerung der Eigenstaendigkeit. File: `docs/method/ai-tools.md` (Erklaerung section). Highest single lift, low mechanical effort, but an owner-only human-gate item (final acceptance veto), so it cannot be delegated. This is the one move that crosses Opus from 5.5 into the 5.7+ band.

2. **C4 Architektur, up to 3 points. Flagged by gpt-5.5 (divergence).**
   gpt-5.5 docks to 4/7 on a concrete Bild-Text inconsistency: arc42/05 text references `parsers/fhir_parser.py`, which is not present in the actual `services/` layout. Opus saw the C4 views as consistent and awarded full.
   Fix: reconcile the building-block text with the real service layout (remove or correct the phantom parser reference, confirm the parser inventory). Files: `docs/arc42/05-building-block-view.md`, verify against `services/ingestion/parsers/`. Trivial doc reconciliation; decisive for a hostile reader.

3. **C10 Git-Repository, 2 points. Flagged by Opus (divergence).**
   Opus zeroes it: the Fazit (Veto 3, PR #17) states the repository stays private until go-live, so the only non-zero anchor "Repository zugaenglich" fails at grading time and there is no partial tier. gpt-5.5 read the linked URL plus the present local checkout as sufficient and awarded full.
   Fix: flip the repository to public before submission (the planned go-live step) and confirm the report states it is public. File: GitHub visibility setting plus a one-line check in `docs/criterion-map.md` and the report. Cheap and decisive; binary on a single owner action.

4. **C5 Perspektiven, up to 3 points. Flagged by gpt-5.5 (divergence).**
   gpt-5.5 docks to 4/7: the interaction perspective is carried by a use-case diagram, not by an interface-contract or OpenAPI view with its own diagram and explanatory text, so it judges the three-perspective set not fully complete. Opus counted the OpenAPI response_model contracts as satisfying interaction.
   Fix: add or surface an explicit interface-contract view (an OpenAPI or schnittstellen diagram with text) as the interaction perspective. Files: `docs/arc42/05-building-block-view.md` or `docs/arc42/06-runtime-view.md`. Moderate effort.

5. **C8 Framework-Konzepte, up to 3 points. Flagged by Opus (divergence).**
   Opus docks to 7/10 on two self-admitted inconsistencies: observability is decided (ADR-011) but not instrumented, and the TarifGuard component and Playwright tests are not wired into CI (`npm run test --if-present` is a no-op). gpt-5.5 awarded full on the idiomatic FastAPI DI, Pydantic validation, env config and error handling.
   Fix: instrument minimal OpenTelemetry or Sentry and wire the console tests into a real CI job. Files: service instrumentation, `.github/workflows/ci.yml`, `apps/tarifguard/package.json`. Real engineering work, so lowest lift-per-effort in this list.

6. **C18 Fazit, up to 3 points. Flagged by gpt-5.5 (divergence).**
   gpt-5.5 docks to 4/7: it reads Veto 3 (go-live, Moodle submission, Eigenstaendigkeitserklaerung) as only provable as non-delegated intent before submission, so the belegtiefe is uneven. Opus saw all three vetoes evidenced with incident plus PR/SHA and awarded full.
   Fix: largely resolves at go-live together with C10 and C15; until then it is partly inherent to pre-submission timing. Low actionability now. File: `docs/method/fazit.md`.

## Confidence read

Banked, both graders agree at full: all of Spezifikation (C1, C2, C3), Datenmodell (C6), Code-Struktur (C7), Erkenntnisse (C9), all of Validierung (C11, C12, C13, C14), KI-Services (C16), Container und Sub-Systeme (C17). These 12 criteria are high-confidence strong and need no further work.

Banked as a known gap, both agree: C15. The 5 points are blocked by one owner-only item (the signed Eigenstaendigkeitserklaerung), not by missing substance.

Manual-inspection list, the two graders diverge and a real grader could go either way: C4, C5, C8, C10, C18. Three of these (C10, C18, and the signature half of C15) hinge on go-live timing and the owner's final acts, which is consistent with the house vetoes. The other two (C4 the phantom parser reference, C5 the interaction perspective) are pure documentation fixes the owner should inspect directly, because a hostile grader can read them down by 3 points each.

Net: the banked floor across both graders is 86 points (gpt-5.5's total, since on every criterion where they disagree at least one grader awards the higher value), the optimistic ceiling at go-live with the signature, public repo and the two doc fixes is roughly 95 to 97. The realistic submitted band is 5.3 to 5.5 today, moving toward 5.7+ once C15 and C10 close at go-live.

---

This scorecard is one Opus pass and one gpt-5.5 pass estimating a human grader against the written anchors. It is advisory only and was produced without touching `tools/cas_check.py`, `tools/cas_baseline.json`, the green-contract, product code or the submission PDF.
