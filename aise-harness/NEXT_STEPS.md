# NEXT_STEPS · owner playbook (Erhan)

> The single file that answers "what do I do next?", no chat needed. Work whenever you
> want; nothing here is scheduled except the school's submission deadline.
> State of truth: Shipboard (key **8** = CAS tab) and `python3 tools/cas_check.py`.

---

## WHERE WE ARE (14 Jun) · the core build is DONE

Prompts 06 and 07 are both merged. `cas_check` is **62/62** (all 18 criteria structurally
present, ratchet green): crit 13/14 evidence, crit 17 deployment, the crit-15 AI-tools
chapter, the crit-18 Fazit, and the crit-10 repo URL are all in. The **83-page FFHS PDF
builds** (`python3 tools/build_pdf.py` -> `build/pdf/tarifhub-cas.pdf`), em-dash sweep is
clean, `mkdocs --strict` passes, CI is green. What remains is the docs-polish loop (Step 6:
08/09/10/11) and your own veto items (Erklaerung, freeze, Moodle upload).

The loop halted twice on benign vault-journal churn (the curate/brain_sync hooks rewrite
`vault/00-index.md` and `vault/daily/*` at session end, landing uncommitted after the
session's commits). Fixed durably: the whole hook-managed `vault/` tree is now excluded
from the loop's clean-tree contract. If you see that halt again, it is never lost work,
just clear it:

```
cd ~/Documents/Tarif/tarifhub
git add tools/loop.sh vault/
git commit -m "fix(loop): exclude hook-managed vault/ tree from clean-tree contract; commit session-end journal"
```

Prompt 07 is already merged at 62/62, so there is nothing to re-run for it. Go straight to
Step 6 below to build the framework chapter, diagrams, deck, and the independent score.

---

## Where the project stands (13 Jun)

- Foundation, two real sources (EAL XLSX + ePL FHIR R5), parity, search tuning,
  scale/fill-reuse hash-integrity, services + MCP: **PRs #1-#15 merged, CI green**.
- CAS floor **51/52**, 0 regressions. Blocks measure progress, not dates:
  Block 0 done 40/40 · Block 1 active 9/10 · Block 2 at 2/4 · Block 3 at 0/8.
- Journal + fazit-note drafting is fully delegated to Codex gpt-5.5 (`tools/curate.sh`,
  owner decision 13 Jun); the loop runs it at start, after every prompt, and after the
  audit. The 5+ notes Block-1 miss fills itself. The only text you write yourself is
  the Eigenständigkeitserklärung (step 5).
- Quality before cost is law (ADR-018): the orchestrator is Opus 4.8 (Fable 5 ran the
  early blocks; access ended 22 Jun) and **everything runs at `/effort ultracode`**, no
  down-shift; every seat is Opus 4.8, Sonnet/Haiku banned. Codex gpt-5.5 (your Pro login,
  verified 13 Jun) reviews EVERY PR, reviews the final document in prompt 07, curates the
  journal, and writes a second opinion on each grade estimate. Effort map below.
- Remaining build: console, validation evidence, final document. One manual session,
  then the loop.

## Model and effort map (who runs what, at which effort)

| Step | Who | Model | Effort |
|---|---|---|---|
| 01 Plan | orchestrator | Opus 4.8 | ultracode |
| 02 Implement | implementer | Opus 4.8 | ultracode |
| 03 Local gates | orchestrator | Opus 4.8 | ultracode |
| 04 Review: verifier | verifier | Opus 4.8 (inherit) | ultracode |
| 04 Review: determinism / security | determinism-auditor, security-reviewer | Opus 4.8 | ultracode |
| 04 Review: independent | codex-reviewer | gpt-5.5 (Codex CLI) | Codex's own |
| 05 Fix cycle | orchestrator | Opus 4.8 | ultracode |
| 06 PR + CI | orchestrator | Opus 4.8 | ultracode |
| 07 Runtime verify | e2e-tester | Opus 4.8 | ultracode |
| 08 Report | orchestrator | Opus 4.8 | ultracode |
| 09 Merge gate | orchestrator | Opus 4.8 | ultracode |
| post: grade audit | grade-auditor | Opus 4.8 | ultracode |
| post: curate + 2nd opinion | gpt-5.5 (Codex CLI) | gpt-5.5 | Codex's own |

Orchestrator effort is set by `/effort ultracode` (manual sessions) and by the loop's
standing order (headless). Worker effort is pinned per agent in `.claude/agents/*.md`
(`effort: ultracode`). Codex runs gpt-5.5 at its own configured effort on your Pro login.

## TOMORROW, exactly

### Step 0 · one-time, 2 minutes (if not already done)

```
cd ~/Documents/Tarif/tarifhub
git status        # if it lists modified tools/prompts/agents files, commit them:
git add -A && git commit -m "chore: board v9, loop runner, quality-before-cost seats, codex doc review" && git push
```

### Step 1 · prompt 05 manually (the dress rehearsal)

```
Terminal B:  cd ~/Documents/Tarif/tarifhub && python3 tools/shipboard/shipboard.py
Terminal A:  cd ~/Documents/Tarif/tarifhub && claude
             /effort ultracode
             → paste the full content of prompts/05_tarifguard_console.md
```

Gate-01 is pre-approved inside the prompt: the session logs its plan and proceeds on
its own, auto-merges on green. You do not need to answer anything. It stops only for:
freeze-line contact, scope beyond the prompt, a contract breach, or a destructive op.

While it runs: watch the board (Overview cards, Pipeline rail). When the ship report
appears: `/exit`. Nothing else; the loop curates 05's journal when it starts.

### Step 2 · glance (optional, 10 seconds)

Board: CAS tab green? GitHub tab CI green? Done. Journal and fazit notes curate,
commit and push themselves (gpt-5.5 via `tools/curate.sh`, automated everywhere);
the pipeline is documented in the AI-tools chapter.

### Step 3 · go-live trio (BEFORE starting the loop; the loop reaches prompt 07)

In GitHub, in this order (also documented in `docs.yml`):

1. repo Settings → Visibility → make **public**
2. Settings → Environments → `github-pages` → allow branch `main`
3. Settings → Actions → Variables → new repo variable `DEPLOY_PAGES = true`

### Step 4 · the loop carries the rest

```
cd ~/Documents/Tarif/tarifhub && bash tools/loop.sh 06 07
```

What it does, all automatic: curates 05's journal (catch-up) → runs prompt 06 →
contract check → curate → runs prompt 07 (includes the Codex gpt-5.5 document review
and the FFHS-LaTeX PDF build) → contract check → curate → **runs /cas-audit** (grade
estimate → CAS tab) → **codex second opinion on the estimate** (disagreements and
missed gaps → `vault/cas-audit/`) → final curate. Between prompts the completion contract
(zero ratchet regressions · CAS floor non-decreasing · working tree clean · latest CI
on main green) must hold, else it **halts to you with the printed reason**; fix what
it names (or ask the orchestrator why) and rerun the printed command, it resumes from the halted
prompt. Log: `.shipboard/loop.log` (tail -f friendly). The board shows everything
live either way.

### Step 5 · after the loop finishes (one manual thing in total)

The audit estimate is already on the CAS tab (the loop ran it). If it flags
points-at-risk you care about: paste the gap row into a session and say "fix this,
then /ship". Optional.

1. **Write your Eigenständigkeitserklärung** (the only text that is yours to write):
   prompt 07's ship report names the file with the reserved page. Write your text
   (name, place, date), rebuild the PDF with the one command the report gives you,
   check the page renders.
2. Before you upload: read the PDF once and edit whatever you want changed.
   Everything is yours to override; nothing ships to Moodle except by your hand.

### Step 6 · docs polish + independent scoring loop (after the 06/07 loop finishes)

Four prompts add the AI-SE framework chapter, the Eraser diagrams, the presentation deck, and a final
independent score. They live in `prompts/08_ai_se_framework.md`, `prompts/09_diagrams.md`,
`prompts/10_slide_deck.md`, and `prompts/11_cas_score.md`. They are in the bundle; apply and run them
in one paste once the current loop has finished and the tree is clean:

```
cd ~/Documents/Tarif/tarifhub
B=~/Documents/Claude/Projects/Tarif/tarifhub-fable5/06_Dev/tarifhub
# prompts 08-11 are already committed; this adds prompt 12 + the three reviewed bridge components
cp $B/prompts/12_approval_bridge.md prompts/
mkdir -p .claude/hooks
cp $B/approval_bridge/approval_gate.sh   .claude/hooks/approval_gate.sh
cp $B/approval_bridge/notify_telegram.sh .claude/hooks/notify_telegram.sh
cp $B/approval_bridge/approval_telegram.py tools/approval_telegram.py
chmod +x .claude/hooks/approval_gate.sh .claude/hooks/notify_telegram.sh
cp $B/NEXT_STEPS.md ./NEXT_STEPS.md
git add prompts/12_approval_bridge.md .claude/hooks/approval_gate.sh .claude/hooks/notify_telegram.sh tools/approval_telegram.py NEXT_STEPS.md
git commit -m "chore(approval-bridge): gate hook + telegram daemon + notifier + prompt 12 (no-op until APPROVALS_ON=1)" && git push
caffeinate -is nohup bash tools/loop.sh 08 09 10 12 11 >> .shipboard/loop.log 2>&1 &
tail -f .shipboard/loop.log
```

The bridge components ship as a hard no-op (the gate allows everything unless `APPROVALS_ON=1`,
the notifier is silent unless the Telegram env vars are set), so committing and running them changes
nothing about how this loop behaves. Prompt 12 wires them into the board and documents them; turning
approvals live is the separate owner toggle in Step 8.

08 folds the AI-SE framework write-up into the architecture docs (and has the AI-tools chapter name
the full tool set: Claude Code, Codex gpt-5.5, Eraser MCP) and leaves diagram placeholders; this is
also what fills most of the open crit-15 (KI-Werkzeuge) gaps: the KI chapter, the phase structure,
the prompt/diff/commit evidence, and the Eigenständigkeit explanation. 09 renders the diagrams with
Eraser (MCP, logged in) to committed SVG/PNG and embeds them (crit-4 architecture in picture and
text), then rebuilds the PDF. 10 builds the minimalist Reveal.js deck (`docs/presentation/index.html`)
for your 5-minute school talk, reusing 09's diagrams, with speaker notes and a per-slide time budget.
11 is the new one: an independent dual-blind CAS score (see Step 7).

12 wires the approval bridge into the dashboard, fixes the Loop-tab Recent-log overflow, and
documents the bridge inside the framework chapter (crit 15 tool set, crit 18 human floor). Order
matters: 10 reuses 09's diagrams, 12 documents into the post-08 chapter, and 11 scores the finished
docs last, so keep `08 09 10 12 11`. Eraser only, no Mermaid; if the Eraser MCP is ever unreachable,
09 stops and names the diagram rather than substituting, rerun when it is back. Open the deck after
the loop with `open docs/presentation/index.html`; press **S** for the speaker-notes view while you
rehearse.

### Step 7 · independent scoring and gap-closing (the last build before submission)

Prompt 11 produces, in `vault/cas-audit/`, two independent scorecards against the official anchor
rubric (`docs/cas/bewertungskriterien-anker.md`): one from Opus 4.8, one from gpt-5.5 via Codex, each
scoring all 18 criteria blind to the other as a hostile grader, lowest defensible score, every score
tied to an anchor quote and an evidence path. The reconciliation file `vault/cas-audit/scorecard.md`
diffs them: per-criterion `Opus | gpt-5.5 | Δ`, both totals out of 100, and a ranked **point-lift
list** of what to fix for the most points.

This is advisory by design and never gates the loop: `cas_check.py` stays the only deterministic
floor, and no number from prompt 11 ever feeds the ratchet, the green-contract, or the submitted PDF.
The scorecard is your internal map, not something the grader sees.

How to use it to close gaps:

1. Read `vault/cas-audit/scorecard.md`. Trust the **divergences** most: where the two graders
   disagree by more than a point is exactly where a real grader could read it either way, so a small
   wording or evidence change moves the score.
2. For each criterion you choose to chase, paste its row plus the named fix into a session and say
   "fix this, then /ship". These are normal build sessions (Gate-01 pre-approved), so they merge on
   green like any other.
3. Re-run prompt 11 (`bash tools/loop.sh 11`) to confirm the lift and refresh the scorecard. Stop
   when the cheap points are banked; do not chase the asymptote or teach-to-the-test the wording.

The CAS tab's audit-estimate column remains the at-a-glance read; the scorecard is the detailed,
two-grader version behind it.

### Step 8 · turn the approval bridge on (optional, after the loop, your secrets)

Prompt 12 has already shipped the bridge as a no-op. To make it live you do two manual things, none
of which I can do for you (they involve your own Telegram bot token and chat id, which never enter
the repo):

1. **Create the Telegram bot.** In Telegram, message `@BotFather`, send `/newbot`, follow the prompts,
   and copy the bot token. Then message `@userinfobot` (or `@RawDataBot`) to get your numeric chat id.
   Put both in a local `.env` beside the repo (it is gitignored):

   ```
   TG_BOT_TOKEN=123456:ABC...your-token
   TG_CHAT_ID=987654321
   ```

2. **Start the bridge and run the loop in approval mode.** In one terminal start the daemon, in
   another launch the loop with approvals on and the default permission mode (not bypass):

   ```
   # terminal C, the Telegram bridge
   set -a; source .env; set +a
   nohup python3 tools/approval_telegram.py >> .shipboard/tg.log 2>&1 &

   # terminal A, a loop run that asks before sensitive actions
   set -a; source .env; set +a
   APPROVALS_ON=1 caffeinate -is bash tools/loop.sh <prompts>
   ```

When the loop hits a merge-to-main, a destructive git command, or a go-public action it now pauses,
posts an Approve/Deny card to the dashboard Approvals panel AND your Telegram, and continues on the
first tap from either side. No tap within nine minutes denies and halts, exactly like today. Leave
`APPROVALS_ON` unset (the default) and the loop behaves exactly as it does now. The phase-1
notifications (a Telegram ping on halt or finish) work as soon as the `.env` is present, even with
approvals off.

## Your remaining errands (only you can do these)

- [x] Codex ready (verified 13 Jun: gpt-5.5, xhigh, headless OK)
- [ ] **Moodle:** upload the Problemstellung one-pager (condense Feasibility §2-3).
- [ ] **Moodle:** fill the Modulevaluation (closes 22 Jun).
- [ ] Go-live trio (step 3 above) before the loop.
- [ ] Eigenständigkeitserklärung (step 5 above).
- [ ] **Submission (deadline: Mon 6 Jul 2026, 00:00, Gruppe K):** upload the final PDF
      (FFHS-template build, clickable repo URL inside) on the "Projektarbeit:
      Deployment & Abgabe" assignment. Prompt 07's pre-flight verifies everything
      first, including the zero-em-dash sweep and the Codex review dispositions.

## Hard human floor (never delegated, by design)

- **Protected billing-integrity code** (hashing, versioning, audit trail; internally
  called the "freeze line"): a guard hook blocks every agent edit there. When a change
  is truly needed, the session stops and asks you to approve the exact lines, like the
  one-line audit fix you authorized on 11 Jun. Nothing happens there without you.
- Final acceptance: the go-live decision, the Moodle submission and the
  Eigenständigkeitserklärung. You can edit any text before submitting; nothing ships
  except by your hand.
- Eigenständigkeitserklärung: page reserved by prompt 07, text authored by you.
- Moodle uploads and GitHub account settings.

## If something looks wrong

- Board badge red / phase fail → click the phase, read the evidence.
- CAS tab shows a regression marker → a once-passing anchor element regressed; CI is
  already red on it; paste the gap row's text into a session and say "fix this, then
  /ship".
- Loop halted → read the printed reason (also in `.shipboard/loop.log`), fix, rerun
  the printed command.
- Session feels stuck → ask Claude (Cowork) "is it still running?"; the worktree
  heartbeat is the ground truth for background agents.

## Done means

PDF uploaded and rendering on Moodle · repo public and frozen on the submitted commit ·
`/cas-status` floor all green · journal curated through the final day. Then stop.
