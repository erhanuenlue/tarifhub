# NEXT_STEPS · owner playbook (Erhan)

> The single file that answers "what do I do next?", no chat needed. Work whenever you
> want; nothing here is scheduled except the school's submission deadline.
> State of truth: Shipboard (key **8** = CAS tab) and `python3 tools/cas_check.py`.

---

## DO THIS FIRST (14 Jun) · recover the halted 06/07 loop

The 06/07 loop halted, but the cause is benign: prompt 06 finished all its work and
committed it (PR #18, CI green), then the `brain_sync` hook regenerated
`vault/00-index.md` at session end (only a timestamp bump and derived counts). That
regen landed after the session's commits, so it sat uncommitted and the loop's
clean-tree contract counted it as dirt and stopped before merging. No work was lost.

Fixed durably: `vault/00-index.md` is now excluded from the loop's clean-tree contract
(it is auto-generated, "do not edit by hand," like `.shipboard/` and the ratchet
baseline that were already excluded). To recover, paste this once:

```
cd ~/Documents/Tarif/tarifhub
git add vault/00-index.md tools/loop.sh NEXT_STEPS.md
git commit -m "fix(loop): exclude auto-generated vault/00-index.md from clean-tree contract; commit session-end index"
caffeinate -is nohup bash tools/loop.sh 06 07 >> .shipboard/loop.log 2>&1 &
tail -f .shipboard/loop.log
```

The rerun re-enters prompt 06, which now only has to push the branch, wait for green CI,
and merge PR #18 (phase 09), then it runs prompt 07. Watch the board's Loop tab. When it
finishes cleanly, continue with Step 6 below (prompts 08/09/10).

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

### Step 6 · docs polish loop (after the 06/07 loop finishes)

Three more prompts add the AI-SE framework chapter, the Eraser diagrams, and the presentation deck.
They live in `prompts/08_ai_se_framework.md`, `prompts/09_diagrams.md`, and
`prompts/10_slide_deck.md`. They are in the bundle; apply and run them in one paste once the current
loop has finished and the tree is clean:

```
cd ~/Documents/Tarif/tarifhub
cp ~/Documents/Claude/Projects/Tarif/tarifhub-fable5/06_Dev/tarifhub/prompts/08_ai_se_framework.md prompts/
cp ~/Documents/Claude/Projects/Tarif/tarifhub-fable5/06_Dev/tarifhub/prompts/09_diagrams.md prompts/
cp ~/Documents/Claude/Projects/Tarif/tarifhub-fable5/06_Dev/tarifhub/prompts/10_slide_deck.md prompts/
git add prompts/08_ai_se_framework.md prompts/09_diagrams.md prompts/10_slide_deck.md && git commit -m "docs: prompts 08 (AI-SE framework) + 09 (Eraser diagrams) + 10 (Reveal.js deck)" && git push
caffeinate -is nohup bash tools/loop.sh 08 09 10 >> .shipboard/loop.log 2>&1 &
```

08 folds the AI-SE framework write-up into the architecture docs (and has the AI-tools chapter name
the full tool set: Claude Code, Codex gpt-5.5, Eraser MCP) and leaves diagram placeholders; 09
renders the diagrams with Eraser (MCP, logged in) to committed SVG/PNG and embeds them, then rebuilds
the PDF; 10 builds the minimalist Reveal.js deck (`docs/presentation/index.html`) for your 5-minute
school talk, reusing 09's diagrams, with speaker notes and a per-slide time budget. Eraser only, no
Mermaid. If the Eraser MCP is ever unreachable, 09 stops and names the diagram rather than
substituting; rerun when it is back. Run order matters: 10 depends on 09's diagrams, so keep
`08 09 10`. Open the deck after the loop with `open docs/presentation/index.html`; press **S** in the
browser for the speaker-notes view while you rehearse.

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
