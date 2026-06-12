# NEXT_STEPS · owner playbook (Erhan)

> The single file that answers "what do I do next?", no chat needed. Work whenever you
> want; nothing here is scheduled except the school's submission deadline.
> State of truth: Shipboard (key **8** = CAS floor) and `python3 tools/cas_check.py`.

---

## Where the project stands

- ✅ Foundation, two real sources (EAL XLSX + ePL FHIR R5), parity, search tuning,
  scale/fill-reuse hash-integrity, services + MCP: **PRs #1–#15 merged, CI green**.
- ✅ Spec/design docs anchored to the official Bewertungskriterien; structural floor
  **51/51**, ratchet armed in CI.
- ⛔ Remaining build: console → validation evidence → final document. Three prompts.

## The remaining prompts · run in this order, one per session

| # | Prompt file | What it produces | Unlocks |
|---|---|---|---|
| 1 | `prompts/05_tarifguard_console.md` | TarifGuard console (master-detail + review form + explain panel) + screenshots | criteria 1/4 console parts |
| 2 | `prompts/06_validation_evidence.md` | Interpreted test results, NfA measured column (incl. p95), container run evidence, decision matrix | criteria 14, 17 captures |
| 3 | `prompts/07_documentation_fazit.md` | AI-tools chapter (phase-structured), veto-Fazit, German summary; **submission PDF from the official FFHS LaTeX template** (`docs/latex_template/`), with journal excerpts + Fazit as chapters inside it; Pages site beside it; no em-dashes anywhere | criteria 15, 18 + submission package |

### Manual mode (a session at a time)

```
Terminal B:  cd ~/Documents/Tarif/tarifhub && python3 tools/shipboard/shipboard.py
Terminal A:  cd ~/Documents/Tarif/tarifhub && claude
             /effort ultracode
             → paste the prompt file's content
             → answer the one plan question (gate 01)
             → walk away; it auto-merges on green
```

One prompt = one session. Exit after the ship report; fresh session for the next prompt.

### Loop mode (optional, hands-off)

```
cd ~/Documents/Tarif/tarifhub && bash tools/loop.sh
```

Runs the remaining prompts back-to-back, headless. Between prompts it verifies the
completion contract (PR merged · CI fully green · zero ratchet regressions · CAS floor
non-decreasing) and **halts to you** with the reason if anything misses. You can stop it
anytime; the board shows everything live either way.

## After each prompt (2 minutes, yours alone)

1. Read `vault/daily/<today>.md` and curate the journal draft into your own words.
   **This is graded material in your voice. Never skip, never generate.**
2. Drop one honest line into `vault/fazit-notes.md` (veto moments, surprises,
   what you corrected). The CAS floor wants 5+ notes; this is today's only Block-1 miss.
3. Glance at the board: CAS tab green? GitHub tab CI green? Done.

## After prompt 06 and again after 07

- Type `/cas-audit` in any session → grade-auditor writes the dated estimate;
  it appears on the CAS tab automatically. Fix what it ranks as points-at-risk.

## Your errands (only you can do these)

- [ ] **Moodle:** upload the Problemstellung one-pager (condense Feasibility §2–3).
- [ ] **Moodle:** fill the Modulevaluation (closes 22 Jun).
- [ ] **Before prompt 07, GitHub go-live trio** (also documented in `docs.yml`):
      repo Settings → make **public** → Environments → `github-pages` → allow `main`
      → Actions → Variables → `DEPLOY_PAGES=true`.
- [ ] **Write your Eigenständigkeitserklärung** into the reserved page when prompt 07
      hands it to you.
- [ ] **Submission (deadline: Mon 6 Jul 2026, 00:00, Gruppe K):** upload the final PDF
      (FFHS-template build, clickable repo URL inside) on the "Deployment & Abgabe"
      assignment. Prompt 07's pre-flight checklist verifies everything first, including
      a zero-em-dash sweep.

## Hard human floor (never delegated, by design)

- **Protected billing-integrity code** (hashing, versioning, audit trail; internally called
  the "freeze line"): a guard hook blocks every agent edit there. When a change is truly
  needed, the session stops and asks you to approve the exact lines, like the one-line
  audit fix you authorized on 11 Jun. You approve or refuse; nothing happens without you.
- Journal + Fazit voice: drafted for you, written by you. Both appear as chapters inside
  the architecture documentation and the submission PDF.
- Eigenständigkeitserklärung: prompt 07 reserves the page; **you write the text yourself**
  and sign (name, place, date).
- Moodle uploads and GitHub account settings.

## If something looks wrong

- Board badge red / phase fail → click the phase, read the evidence.
- CAS tab shows a 🔻 → a once-passing anchor element regressed; CI is already red on it;
  paste the gap row's text into a session and say "fix this, then /ship".
- Session feels stuck → ask Fable (Cowork) "is it still running?"; the worktree
  heartbeat is the ground truth for background agents.

## Done means

PDF uploaded and rendering on Moodle · repo public and frozen on the submitted commit ·
`/cas-status` floor all green · journal curated through the final day. Then stop.
