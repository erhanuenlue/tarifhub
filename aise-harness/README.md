# aise-harness — how this repository builds itself

> This folder is a **guided tour, not a separate codebase.** tarifhub was built with an
> agentic software‑engineering loop, and every part of that loop is checked into this
> repository as first‑class evidence (FFHS CAS AI‑Assisted Software Engineering, criterion 15).
> The files live in their working locations — the automation depends on those exact paths —
> so the links below are simply the front door.

## The operating model in one paragraph

A human writes an **outcome prompt** (the goal, the constraints, and how to verify it), not a
script. An orchestrator model plans the work and stops at exactly **one human gate — plan
approval**. It then implements test‑first, runs the suite, has an **independent second model**
review the diff, and self‑merges only when a hard **green contract** holds (CI green, findings
dispositioned, the deterministic freeze line untouched, working tree clean). Every session
writes a journal entry. A **closed loop** runs the remaining prompts back‑to‑back and **halts
to the owner** the moment any contract check fails. The freeze line — *no AI ever computes a
billing value at serve time* — is enforced by a git hook, not by good intentions.

## The pieces (paths relative to the repo root)

| Concern | Where | What it is |
|---|---|---|
| Prompt library | [`../prompts/`](../prompts/) | Outcome prompts, one per build block, mapped to CAS criteria. |
| Closed‑loop runner | [`../tools/loop.sh`](../tools/loop.sh) | Runs prompts headless; enforces the inter‑prompt contract (ratchet, clean tree, secret scan, CI green) and halts on any miss. |
| Agent roster | [`../.claude/agents/`](../.claude/agents/) | implementer, verifier, security‑reviewer, determinism‑auditor, grade‑auditor, codex‑reviewer, e2e‑tester. |
| Governance hooks | [`../.claude/hooks/`](../.claude/hooks/) | `guard_frozen` (freeze‑line gate), `approval_gate`, `format`, `brain_sync`, journal + session tracking. |
| Skills | [`../.claude/skills/`](../.claude/skills/) | `/ship` (the multi‑model pipeline), `/cas-audit`, `/cas-status`, `/new-source`. |
| Live dashboard | [`../tools/shipboard/`](../tools/shipboard/) | The "shipboard" cockpit that watches a run in real time (`python3 tools/shipboard/shipboard.py` → :8787). |
| Deterministic grade floor | [`../tools/cas_check.py`](../tools/cas_check.py) | ~60 anchor checks the loop and CI both ratchet against. |
| Model lifecycle | [`../tools/switch_model.sh`](../tools/switch_model.sh) | Single source of truth for the orchestrator model (ADR‑018). |
| Journal & knowledge | [`../vault/`](../vault/) · [`../knowledge/`](../knowledge/) | The contemporaneous AI‑workflow journal and decision/research notes. Excerpts feed the graded chapter `docs/method/`. |
| AI accept / correct / reject log | [`../LEARNINGS.md`](../LEARNINGS.md) | Where AI suggestions were taken, fixed, or rejected — with refs. |
| Owner playbook | [`../NEXT_STEPS.md`](../NEXT_STEPS.md) | The live "what's next" state of the build. |
| Future‑work design | [`../docs/cockpit/`](../docs/cockpit/) | Post‑submission redesign of the dashboard (design only; excluded from the graded site and PDF, ADR‑022). |

## Reproduce it

```bash
# One prompt, dry run (no model spend) — replaces the model with `true`
LOOP_CMD='true' bash tools/loop.sh 06

# The grading floor the loop and CI both enforce
python3 tools/cas_check.py

# Fresh-machine setup
#   ../docs/CLAUDE_CODE_SETUP.md
```

> **For graders:** the product itself (services, serving API, console, arc42 docs) stands on its
> own and is reviewed in the thesis PDF. This harness is *how* it was produced — the
> criterion‑15 evidence that the AI‑assisted method was real, governed, and reproducible.
