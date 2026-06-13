---
name: cas-status
description: Where do we stand against the CAS rubric and the 6 July deadline? Run weekly and before any scope decision.
disable-model-invocation: true
allowed-tools: Bash, Read, Grep, Glob
---

Produce an honest CAS status check — evidence-based, no optimism.

1. **Days remaining** to Sun 5 Jul (submission day; deadline Mon 6 Jul 00:00): `date`.
2. **Floor check** (CAS Dossier §7 — never-cut items), each verified against the repo, not memory:
   - live `ai_map` (is the Claude call real or still the deterministic fallback? read the code)
   - journal: `ls vault/daily/` — count entries, flag gaps > 2 days
   - determinism test green: run it
   - two sources harmonised end-to-end (which fixtures/tests prove it?)
   - arc42 site builds: `mkdocs build -f docs/mkdocs.yml --strict`
   - console: `apps/tarifguard` lints/builds + component/smoke tests pass + **screenshot set present in `docs/img/console/`**
   - captured distribution evidence: compose-up screenshot + CI image-build matrix green (code-only review — runtime proofs don't count, captures do)
   - "Modern application concepts" page exists in arc42 §8 and opens with the criterion-8 wording verbatim
3. **Anchor audit — run `python3 tools/cas_check.py` (single source of truth) and include its table.** It measures the structural floor of all 18 criteria with evidence paths and flags ratchet regressions. Then add the judgment items the checker cannot see: roter Faden across chapter openings? prose specific rather than generic? diagrams consistent with text? (Full judgment tier: `/cas-audit`.)
4. **Evidence artifacts:** acceptance criteria written? test-results table populated? decision matrix drafted? Fazit notes accumulating in `vault/fazit-notes.md`?
5. **Block plan position**: which block should today be in, what's late, what's at risk.
6. Output: a table (floor item → status → evidence), the anchor-audit misses, then the **three highest-leverage actions for the coming week**, then the cut-list recommendation if anything is slipping.

No false greens: a thing is done when the repo proves it.
