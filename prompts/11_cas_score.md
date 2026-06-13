# 11 · Independent dual-blind CAS scoring (Opus + gpt-5.5)

> **Gate-01: pre-approved by the owner (14 Jun).** Produce and log the plan (emit + plan report), then proceed without waiting. STOP only for: scope beyond this prompt, any freeze-line contact, a green-contract or ratchet breach, or a destructive operation.

Run at `/effort ultracode`. This prompt does NOT build or change the product. It produces an
independent, structured estimate of how the project will score against the official rubric, so the
owner can see where the points actually are before the deadline. It is advisory: it must not touch
`tools/cas_check.py`, `tools/cas_baseline.json`, the green-contract, any product code, or the
submission PDF/docs. The deterministic fitness function stays the only thing the loop gates on.

## What you score against

The official anchor rubric: `docs/cas/bewertungskriterien-anker.md` (local, git-ignored, 18
criteria, point-weighted, 100 points total). Score the built artefacts as a cold grader would: read
only what is on the page in the final docs (`docs/`, the built PDF, the diagrams from prompt 09, the
deck from prompt 10), plus the repository surface a grader sees (README, repo URL, CI status). Do not
credit intent that is not written down.

## Two blind, independent passes (this is the point of the exercise)

Run two graders that never see each other's scores. Independence is the whole value: one is the same
model family that wrote the docs, the other is not.

**Pass A, Opus.** Dispatch the grade-auditor (Opus 4.8, ultracode). For each of the 18 criteria,
award points out of that criterion's maximum, citing the exact anchor line being scored and the
evidence path(s) (`file#section`). Grade as a hostile examiner: the lowest score the anchor text
defensibly permits, no benefit of the doubt. Note gaps per criterion. Write
`vault/cas-audit/score-opus.json` and a readable `vault/cas-audit/score-opus.md`. This pass must not
see any gpt-5.5 output.

**Pass B, gpt-5.5.** Run an independent pass through the Codex CLI (`codex exec`, the owner's Pro
login, the same bridge the codex-reviewer uses). Give it the anchor rubric and the built docs and ask
for the identical structured scorecard: points per criterion out of max, the anchor line quoted, the
evidence path, a one-line justification, gaps. Same hostile, lowest-defensible calibration. The
rubric is German and the docs are English plus a German abstract: score in the German criterion's
terms, mapping the English evidence onto it. Do NOT pass it Pass A's scores. Write
`vault/cas-audit/score-gpt5.json` and `vault/cas-audit/score-gpt5.md`.

## Reconciliation (the deliverable)

Diff the two scorecards into `vault/cas-audit/scorecard.md`:

- A table, one row per criterion: `Kriterium | max | Opus | gpt-5.5 | Δ | status`, where status is
  one of agree (Δ = 0), minor (Δ within one point), or **diverge** (Δ greater than one point, or one
  grader awards full and the other flags a gap). Plus both column totals out of 100 and the implied
  Swiss grade band for each.
- A ranked **point-lift list**: the criteria with missing points, ordered by points recoverable per
  unit of effort. Each entry names the concrete fix, the file to change, and which grader(s) flagged
  it. Divergences rank high because they mark the criteria a real grader could read either way, which
  is exactly where a small wording or evidence change moves the score.
- A short **confidence read**: where both graders agree the project is strong, treat as banked; where
  they diverge, that is the manual-inspection list for the owner.

## Calibration rules (bake these into both passes)

Quote-or-it-did-not-happen: every score cites the anchor line and an evidence path, never a vibe.
Lowest defensible score, hostile examiner, no charity for unwritten intent. gpt-5.5 scores blind to
Opus. Score in the rubric's German terms. The estimate is a proxy for the human grader, not the
grader: report it as an estimate and never let a number from this prompt feed `cas_check`, the
ratchet, the green-contract, or the submission.

## Steps

1. Confirm the docs loop (08, 09, 10) has merged and `tools/cas_check.py` reports its current floor;
   record the structural floor (NN/62) as the backdrop for the quality scoring.
2. Run Pass A (Opus), then Pass B (gpt-5.5 via codex exec), blind to each other.
3. Reconcile into `vault/cas-audit/scorecard.md` per the spec above.
4. Style law: no em-dashes anywhere in the outputs; grep zero.
5. The vault autocommit hook commits `vault/cas-audit/` at session end (`[skip ci]`); do not open a
   PR and do not add the scorecard to the submission PDF or the published docs. This is internal
   evidence for the owner only.

## Done means

`vault/cas-audit/{score-opus,score-gpt5,scorecard}.md` exist; the scorecard shows both totals out of
100, per-criterion Δ, and a ranked point-lift list; outputs are em-dash-free. In the report, give the
two totals, the three biggest point lifts, and the criteria where the two graders most disagree.
Curate the journal entry. No product code, `cas_check`, baseline, green-contract, or submission file
was touched.
