# 12 · Approval bridge (dashboard + Telegram) + board fix, wired and documented

> **Gate-01: pre-approved by the owner (14 Jun).** Produce and log the plan (emit + plan report), then proceed without waiting. STOP only for: scope beyond this prompt, any freeze-line contact, a green-contract or ratchet breach, or a destructive operation.

Read AGENTS.md, CLAUDE.md, and `APPROVAL_BRIDGE_DESIGN.md` (in the strategy bundle beside the repo).
Run at `/effort ultracode`. This session wires the approval bridge into the dashboard and Telegram,
fixes a board layout bug, and documents the bridge inside the framework documentation. It is tooling
and documentation only: no product code, no freeze-line files, and it does NOT change the loop's
permission mode (that is a deliberate owner toggle, see step 8). The approval gate ships as a hard
no-op unless `APPROVALS_ON=1`, so nothing here changes the unattended loop's behavior or can cause a
halt.

## 1. Drop in the three reviewed components (already written, in the bundle)

Copy these from the bundle into the repo and mark the shell hooks executable:
- `approval_bridge/approval_gate.sh`     -> `.claude/hooks/approval_gate.sh`
- `approval_bridge/notify_telegram.sh`   -> `.claude/hooks/notify_telegram.sh`
- `approval_bridge/approval_telegram.py` -> `tools/approval_telegram.py`

The manual apply step copies them in before you run; verify they are present and `bash -n` / `python3
-m py_compile` clean. Do not rewrite them; they are the reviewed reference.

## 2. Fix the Loop tab overflow (the visible bug)

In `tools/shipboard/shipboard.py`, the Loop tab "Recent log (.shipboard/loop.log)" box overflows
horizontally because the long ship-report lines do not wrap. Make `#looptail` and `#loopcp` (the two
`pre.jl` boxes in the Loop tab) wrap: add `white-space:pre-wrap;overflow-wrap:anywhere` to their
style (keep `max-height:340px;overflow:auto`). Confirm long lines now wrap inside the panel and the
box no longer runs past its container or the footer.

## 3. Dashboard approvals panel + POST routes (`shipboard.py`)

- Read `.shipboard/approvals/pending/*.json` (skip dotfiles and `.done`) and `decided/*.json` into a
  new "Approvals" panel on the Loop tab (or its own tab), plus a count badge in the header so a
  waiting request is impossible to miss. Each pending row shows risk + summary and an Approve and a
  Deny button; resolved rows show `decision` and `via`.
- Add `POST /approve` and `POST /deny` (mirror the existing `POST /reset` handler). Each reads
  `{"id": ...}` and writes `.shipboard/approvals/decided/<id>.json` with
  `{"decision":"allow|deny","via":"dashboard","by":"erhan","ts":...}`. Idempotent and first-writer
  wins: if the decided file already exists (Telegram got there first), do not overwrite, just return
  the existing decision. The panel re-reads the queue on the board's normal refresh tick, so a
  Telegram-side decision appears here automatically within one tick.

## 4. Register the hooks (`.claude/settings.json`)

- `PreToolUse` matcher `Bash` -> `.claude/hooks/approval_gate.sh`, with `"timeout": 600`.
- `Notification` (and `Stop`) -> `.claude/hooks/notify_telegram.sh`.
Both are safe to register now: the gate allows everything instantly unless `APPROVALS_ON=1`, and the
notifier is a no-op unless `TG_BOT_TOKEN`/`TG_CHAT_ID` are set. Add `TG_BOT_TOKEN=`, `TG_CHAT_ID=`,
and `APPROVALS_ON=0` placeholders to `.env.example` (never real secrets). Confirm `.shipboard/` (which
holds `approvals/`) stays gitignored.

## 5. Document it in the framework documentation (the integration you asked for)

Weave the approval bridge into the existing docs as a real, evidence-linked mechanism, pointing to the
files this session created. Do not invent capabilities beyond what is committed.
- In `docs/method/ai-tools.md` (criterion 15): add the approval bridge to the named tool set as the
  human-in-the-loop governance layer, one queue with two surfaces (the dashboard and a Telegram bot),
  decisions logged to `.shipboard/approvals/log.jsonl`. Point to `.claude/hooks/approval_gate.sh`,
  `tools/approval_telegram.py`, and the dashboard panel.
- In the AI-SE framework chapter (the observability and the human-floor sections): describe how the
  bridge upgrades the human floor from halt-and-rerun to pause-tap-resume, with the verified fail-safe
  (timeout denies, so the worst case is the existing safe halt), and that it is opt-in via
  `APPROVALS_ON`. This strengthens criterion 18 (the human floor and veto decisions are now logged
  and routed, not merely asserted). Keep the Eigenständigkeitserklärung untouched.
- No em-dashes; the chapters are PDF-bound. Rebuild the PDF (`python3 tools/build_pdf.py`) so the
  documentation stays consistent.

## 6. Test (prove it, do not assert it)

- Gate is a no-op when off: feed `approval_gate.sh` a sample Bash tool-input on stdin with
  `APPROVALS_ON` unset; it must return `permissionDecision: allow` immediately.
- Seed a fake `.shipboard/approvals/pending/<id>.json`; the board shows it; `POST /approve` writes
  `decided/<id>.json` with `via:"dashboard"`; the panel flips to resolved on the next tick.
- With `APPROVALS_ON=1`, run the gate against a `git push ... main` sample and a benign `ls` sample:
  the push enqueues and waits, the `ls` allows instantly. Write a decision file and confirm the gate
  returns it; confirm a no-decision run denies after the timeout path (use a shortened loop count in
  a copy for the test, not in the shipped file).
- `python3 -m py_compile tools/approval_telegram.py tools/shipboard/shipboard.py`; `bash -n` the two
  hooks; `mkdocs build -f docs/mkdocs.yml --strict` clean; em-dash grep zero on all rendered docs.

## 7. Constraints

Tooling and documentation only. No product code, no freeze-line files. Conventional commits, branch
`chore/approval-bridge`, then `/ship`; phase 09 auto-merges on the green-contract, else stops for the
owner. The CAS ratchet must not regress (crit 15/18 stay green or improve).

## 8. Do NOT switch the permission mode in this session

Leave `tools/loop.sh` launching with `bypassPermissions` so this run and future unattended runs stay
stable. Enabling live approvals is an owner toggle, documented in NEXT_STEPS: run the loop in the
default permission mode with `APPROVALS_ON=1` and the Telegram daemon started. Note that toggle in the
ai-tools chapter and NEXT_STEPS, but do not flip it here.

## Done means

The three components are in place and compile; the Loop tab box wraps and no longer overflows; the
board has an Approvals panel with working Approve/Deny POST routes (idempotent, first-writer-wins);
the hooks are registered and provably no-op when off; the bridge is documented in `ai-tools.md` and
the framework chapter pointing to the real files; the PDF rebuilds; tests pass; em-dash grep zero;
the ratchet did not regress; merged on the green-contract. Report the test results and the exact
owner steps to turn approvals on. Curate the journal entry.
