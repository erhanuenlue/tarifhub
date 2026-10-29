# CLAUDE.md: tarifhub development workflow

@AGENTS.md

Project facts, safety boundaries, commands and the definition of done live in AGENTS.md (imported above). This file is the short Claude Code workflow. When Erhan corrects you, add one short rule here (or in auto memory), don't grow paragraphs.

## How to work

- Take small tasks one at a time: confirm the scope, make the change, run the relevant checks from the AGENTS.md definition of done, review your own diff (`git status --porcelain`, `git diff`), then explain the result: what changed, which checks ran with their output, what was skipped and why.
- Do the simplest thing that works: no new harness, no speculative abstractions, no broad formatting. Use plan mode when a multi-file change has no settled approach yet.
- Do checks and reviews inline. Delegate to a subagent (any Agent-tool call, the agents in `.claude/agents/` included) only when Erhan has explicitly authorized delegation for the current task; within that task's scope the authorization holds without asking again. When you delegate, block on the result in-turn (background agents surface only idle pings) and have the agent write its findings to a named file. Never work around a permission denial: report what it blocked.
- You do the git work (Erhan doesn't run git by hand), but commit, push, open PRs and merge only when he explicitly asks in this session.
- Pause only for destructive or irreversible actions, real scope changes, or input only Erhan has. When he is thinking out loud, give an assessment, not a patch.

## Model and effort

- One pin: `"model"` in `.claude/settings.json` (`claude-opus-5-5`). Change it only with `bash tools/switch_model.sh opus|fable`, which writes that key; never switch mid-task.
- Every agent in `.claude/agents/` declares `model: inherit` and `effort: max`: subagents run on the main model at max effort (a `CLAUDE_CODE_EFFORT_LEVEL` environment variable would override the effort).
- Settings files cannot store `max` effort; for the main session use `/effort max` or `claude --effort max`.
- `"ultracode": false` keeps automatic dynamic workflows off. Start a multi-agent workflow only when Erhan asks for one.

## Agents, Codex, skills

- Reviewers: `verifier` (fresh-context diff vs. spec), `determinism-auditor` (services/ value-path changes), `security-reviewer` (secrets, input parsing, de-identification seam, internet-facing code). Workers: `implementer` (one scoped TDD task), `e2e-tester` (runtime evidence, only when a change needs it).
- Codex is the independent second model family: use the read-only commands in `.claude/agents/codex-reviewer.md`, one run at a time. Running them yourself is not delegation and needs no authorization; going through that agent is delegation. Either way every restriction in that file holds, and a denied run is a skipped review. Its model comes from `~/.codex/config.toml`; cite the model a run reports, never one from a description.
- Matt Pocock skills (`.claude/skills/`, locked in `skills-lock.json`): use `tdd`, `codebase-design`, `domain-modeling` and `grilling` only when the task calls for them; `grill-with-docs`, `to-tickets` and `setup-matt-pocock-skills` are user-invoked.
- `tdd` points its review stage (where refactoring belongs) to a `code-review` skill that this repo does not install: it is in neither `.claude/skills/` nor `skills-lock.json`, and a same-named skill from outside the repo, such as Claude Code's bundled one, is not it. The local fallback is the repo review procedure, inline: AGENTS.md definition of done step 5 with the applicable checklists in `.claude/agents/`. Report it as the local fallback; never claim that Matt's `code-review` ran.
- `/ship` means this repo's `.claude/skills/ship/SKILL.md`. A user-global gstack skill has the same name: if the Skill tool resolves that one, read the repo file and follow it.

## Agent skills

### Issue tracker

GitHub Issues in `erhanuenlue/tarifhub` via `gh`. No triage labels are configured (the `triage` skill is not installed), so `/to-tickets` must not apply `ready-for-agent`. See `docs/agents/issue-tracker.md`.

### Domain docs

Single-context. Vocabulary: `docs/arc42/12-glossary.md`, read wherever a skill says `GLOSSARY.md` (no root `GLOSSARY.md` yet; before creating one, propose how to keep one authoritative definition per term). ADRs: `docs/adr/`, numbered `NNN-slug.md`, not the skills' `0001-` default. See `docs/agents/domain.md`.

## History, not workflow

- Kept as earlier-CAS evidence, not part of the workflow: `tools/loop.sh`, `tools/curate.sh`, `tools/shipboard/`, `tools/hooks/` (legacy git hooks), the `.claude/hooks/` scripts no longer wired in settings, the `grade-auditor` agent with `/cas-audit` and `/cas-status`, and the `vault/` journals. Don't run, install or rewire them unless Erhan asks.
- Auto memory is yours: corrections, gotchas, confirmed approaches; delete what proves wrong. `vault/` is not your memory.
