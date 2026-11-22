# Development tooling for agents

Read by the lead and any worker that uses these tools. It records what is installed, at which
version, where its state lives and the rules that keep it inside the repository's workflow.
Machine facts are Erhan's macOS host as set up on 2026-11-22 (milestone
[#60](https://github.com/erhanuenlue/tarifhub/issues/60)). AGENTS.md and CLAUDE.md bind every
tool below unchanged: merge conditions, the freeze line, the independent Codex review, spending
decisions and the .env rule are not altered by any of them.

## Superpowers and `/ship`

- Superpowers is a user-level Claude Code plugin. Its `systematic-debugging` (a failing test or
  unexpected behaviour) and `verification-before-completion` (before calling work done) fit this
  repository's way of working; they never override AGENTS.md or CLAUDE.md. Matt Pocock's skills in
  `.claude/skills/` (locked in `skills-lock.json`) stay the repository's TDD, design, domain and
  grilling skills; for test-first work use `tdd`.
- `/ship` is `.claude/skills/ship/SKILL.md`, read directly (a user-global gstack skill has the
  same name). The tooling below changes none of its steps: there is one release procedure, with the
  same checks, protection tests and merge conditions.

## OpenRig (trial, pinned 0.7.21)

- **Install:** `@openrig/cli` 0.7.21 (`255fa708`), exact version, in its own npm project
  `~/.openrig-tarifhub/npm`, not installed globally. The lockfile integrity matches the registry,
  and `npm audit signatures` verified the registry signatures of all 119 packages (26 with
  attestations). Requires Node.js 22 and tmux.
- **Isolation:** `~/.openrig-tarifhub/bin/rig-th` runs `rig` with `HOME`, `OPENRIG_HOME`,
  `CODEX_HOME` and `CLAUDE_CONFIG_DIR` under `~/.openrig-tarifhub/`, so OpenRig's hooks, trust
  entries and skills go to the isolated homes, never to `~/.claude`, `~/.claude.json`,
  `~/.codex` or `~/.agents`. The daemon runs on an isolated tmux server, is started with
  `--no-kernel` (the kernel's operator would get full access), and `rig setup` is used only with
  `--dry-run` (it would write `~/.tmux.conf`). OpenRig's guidance forbids copying credentials,
  so the isolated homes need their own logins: `~/.openrig-tarifhub/bin/login-isolated.sh`.
- **Team:** `~/.openrig-tarifhub/specs/rigs/launch/tarifhub-handoff/rig.yaml`, a Claude Code
  worker (`claude-opus-5-5`) and a Codex reviewer (`gpt-6.2-sol`, effort `max` in the isolated
  Codex config, `codex_permissions`: sandbox `read-only`, approval `never`), working only in the
  disposable clone `~/.openrig-tarifhub/clone/tarifhub` (no remote). OpenRig documents that its
  tests prove the launch flags, not Codex's enforcement, so a reviewer's permissions count only
  after a write attempt has been refused in the seat itself.
- **Herdr Desktop:** two routes work from the existing Herdr Desktop window (herdr-app, whose
  terminals run in herdr-core `default`): OpenRig's `herdr-app` provider opens a Rig view in the
  window the command runs in (`rig-th terminal open <rig> --provider herdr-app --app-home
  ~/.config/herdr-app`; it switches that window to its `rig` layout, and "Your tabs" switches
  back), and a plain tmux attachment in a Desktop tab (`env -u TMUX tmux -S <socket> attach -t
  <session>`, the command `rig-th ps --nodes --json --fields tmuxAttachCommand` prints). OpenRig's
  `herdr` provider targets the Herdr TUI server, which Desktop does not use. The `herdr-app`
  route adds OpenRig's own files to `~/.config/herdr-app` (`mods/rig-*`, `layouts/rig.json`,
  `openrig/`).
- **Rules:** the trial runs only in the disposable clone. A reviewer seat does not replace the
  independent review of `.claude/agents/codex-reviewer.md`. Milestone decisions and acceptance
  evidence stay in GitHub Issues, not in OpenRig's queue.

## Phoenix (tracing demonstration)

- **Executable:** an installed Phoenix 20.26 (here the one installed with the CAS harness),
  started by `tools/commentary_rag/phoenix_serve.sh` with `PHOENIX_PYTHON` naming its Python:
  an empty environment, TarifHub's own git-ignored storage in `tools/commentary_rag/local/phoenix`,
  loopback only on port 6016, gRPC receiver, telemetry, agent assistant and server-side bash off.
- **Demo:** `tools/commentary_rag/trace_demo.py` (command in the pilot README). The spans carry
  decisions, counts, elapsed times and hash prefixes, never question, passage, query or answer text
  and never a cost. The ledgers stay the spending record; a trace is not evidence of spending.

## pdfplumber (diagnostic only)

`tools/commentary_rag/layout_probe.py` runs in an ephemeral environment
(`uv run --no-project --with pdfplumber==0.11.11 ...`); pdfplumber is in no lockfile. Crops go to
the git-ignored `tools/commentary_rag/local/`. The frozen corpus (`pdftotext`) and its results
stay as they are; findings are in `docs/evidence/2026-11-22-pdfplumber-layout-probe.md`.

## pytest-socket (pilot suite)

In the ingestion `dev` extra; only `tools/commentary_rag/conftest.py` enables it, around every
pilot test (Unix sockets allowed). Never add `--disable-socket` to a shared configuration: the
ingestion PostgreSQL legs need network.

## diagram-design (CAS project diagrams)

- **Convention:** every new or revised CAS project diagram is drawn with the official
  `cathrynlavery/diagram-design` Claude plugin. Keep the editable HTML source beside the exported
  SVG in `docs/diagrams/` (`<name>.html`, `<name>.svg`, the SVG exported with the plugin's own
  procedure and system fonts, so nothing loads from the network), verify every label against arc42
  and the code, and check legibility at A4 (render kept in the git-ignored `local/` folder) before
  use. Previously delivered reports and their figures stay as they are.
- **Pin:** commit `d7b0176` (version 2.6.170), installed at user scope from the local checkout
  `~/.local/share/claude-plugins-pinned/diagram-design` (`claude plugin marketplace add <path>`,
  then `claude plugin install diagram-design@diagram-design`). A session started before the
  install, or a subagent that cannot load it, reads `skills/diagram-design/SKILL.md` from that
  checkout and says so. The skin is the plugin's default until Erhan chooses another (the project
  brand would need his decision).
- **First use:** the agent loop of arc42 §6, Scenario 5 (`docs/diagrams/agent-search-answer-loop`).
