# Pre-registration: paired within-task measurement of the rules-and-instructions bundle

**Fixed in writing on 2026-08-02, before the first measurement run.** This document
pre-registers the design, case selection, measures, and analysis rules for a paired
experiment on frozen repository states. It exists so that the commit date of this file
provides an externally verifiable timestamp that the plan predates all measurements.

## Scope

The observational measurement window of this repository is commit `6edd368` (2026-06-07)
through `312e0ef` (2026-07-15). The paired runs below are a separate, retrospective
experiment executed on frozen pre-merge states from that window; they do not alter it.

## Design

Paired within-task runs: each selected pull request is re-executed twice by the same
agent tooling on the same pre-merge commit (obtained via the API tarball, no clone),
once **with** and once **without** the rules-and-instructions bundle (`CLAUDE.md`,
`AGENTS.md`, `.claude/rules/`). All other components stay fixed. Condition order
alternates between pairs; every run starts in a fresh context; no run is repeated.

## Case selection (deterministic, no hand-picking)

- Population: the 49 merged pull requests, restricted to the three occupied task classes
  of the pre-registered classification (scaffolding 11, integration 8, domain logic 4).
- Selection metric: sum of changed lines in production files per pull request, taken from
  its file list; test and configuration files excluded.
- Per class: the largest case and the lower median (class sizes 8 and 4 are even); ties
  resolved toward the older pull request. Six pull requests, twelve runs in total.
- Largest-plus-median instead of random draw: four to eleven cases per class do not
  support random sampling. The sample is explicitly not representative.

## Measures

- **Primary:** wall-clock time per run, from first instruction to the end of the last
  tool call, rounded to seconds, taken from the agent tooling's session record; the
  paired difference per pull request is the unit of analysis.
- **Secondary:** output tokens per run; correctness proxy: whether the follow-up
  commit's test suite passes on the run's result.

## Analysis and failure rules

- Median of the six paired differences plus range. No mean, no significance test —
  six pairs carry neither.
- If a run aborts, the pair is void and reported as a dropout; it is not replaced.

## Known limitations (stated up front)

One run per condition captures no model variance; the same operator revisits the same
task twice, so memory and learning effects remain uncontrolled; the varied component is
a bundle, so the measured effect is a bundle effect, not the effect of a single rule.
