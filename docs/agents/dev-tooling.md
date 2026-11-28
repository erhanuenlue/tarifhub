# Development tooling for agents

Read by the lead and any worker that uses these tools. It records what is installed, at which
version, where its state lives and the rules that keep it inside the repository's workflow.
Machine facts are Erhan's macOS host as set up on 2026-11-22 (milestone
[#60](https://github.com/erhanuenlue/tarifhub/issues/60)). AGENTS.md and CLAUDE.md bind every
tool below unchanged: merge conditions, the freeze line, the independent Codex review, spending
decisions and the .env rule are not altered by any of them.

## Superpowers and `/ship-it`

- Superpowers is a user-level Claude Code plugin. Its `systematic-debugging` (a failing test or
  unexpected behaviour) and `verification-before-completion` (before calling work done) fit this
  repository's way of working; they never override AGENTS.md or CLAUDE.md. Matt Pocock's skills in
  `.claude/skills/` (locked in `skills-lock.json`) stay the repository's TDD, design, domain and
  grilling skills; for test-first work use `tdd`.
- `/ship-it` is `.claude/skills/ship-it/SKILL.md`, the repository's one release procedure (renamed
  from `ship` to `tarifhub-ship` on 2026-11-24, since a user-global gstack skill is named `/ship`,
  and to `ship-it` on 2026-11-27). Before acting on release authority the loaded skill is checked
  against that file under the current Git root (`/ship-it source-only` reports the loaded path);
  when the loader cannot establish the source, the file is read directly and the direct-file
  fallback is named. No global, bundled or plugin shipping procedure stands in for it. The tooling
  below changes none of its steps: there is one release procedure, with the same checks,
  protection tests and merge conditions.

## OpenRig (trial, pinned 0.7.21)

- **Install:** `@openrig/cli` 0.7.21 (`255fa708`), exact version, in its own npm project
  `~/.openrig-tarifhub/npm`, not installed globally. The lockfile integrity matches the registry,
  and `npm audit signatures` verified the registry signatures of all 119 packages (26 with
  attestations). Requires Node.js 22 and tmux.
- **Isolation:** `~/.openrig-tarifhub/bin/rig-th` starts `rig` from an empty environment with an
  allowlist, so no token, key or SSH agent of the calling shell reaches the daemon, its tmux server
  or a seat, and with `HOME`, `OPENRIG_HOME`, `CODEX_HOME` and `CLAUDE_CONFIG_DIR` under
  `~/.openrig-tarifhub/`, so OpenRig's hooks, trust entries and skills go to the isolated homes,
  never to `~/.claude`, `~/.claude.json`, `~/.codex` or `~/.agents`. One process is the
  exception: macOS finds the login keychain only under the normal home, so the Claude worker's
  `launch_wrapper` gives that process alone the normal macOS home, together with the dedicated
  `CLAUDE_CONFIG_DIR` (its settings, state and login stay apart from the real ones) and
  `DISABLE_AUTOUPDATER=1`. The daemon, the seat shells and the Codex seat keep the isolated
  home. The daemon runs on an isolated tmux server, is started with `--no-kernel` (the kernel's
  operator would get full access), and `rig setup` is used only with `--dry-run` (it would write
  `~/.tmux.conf`). OpenRig's guidance forbids copying credentials, so the isolated homes have
  their own logins (`~/.openrig-tarifhub/bin/login-isolated.sh`, run once by Erhan). The
  dedicated Claude config also receives the plugins synced to the claude.ai account, whose MCP
  servers start in the worker seat.
- **Team:** `~/.openrig-tarifhub/specs/rigs/launch/tarifhub-handoff/rig.yaml`, working only in the
  disposable clone `~/.openrig-tarifhub/clone/tarifhub` (no remote). A Claude Code worker
  (`claude-opus-5-5`, effort `max`) whose `claude_permissions` allow only what the bounded task
  needs (reading the trial tree, editing the one target file, `git add` of that file,
  `git commit`, read-only git commands and `rig queue`), and a Codex reviewer (`gpt-6.2-sol`,
  effort `max`) with read-only file access through a Codex permission profile (`:root` read,
  approval `never`). Network stays on for the reviewer because Codex's plain `read-only`
  sandbox also blocks the loopback connection `rig queue` needs to reach the daemon (measured: a
  connection to the daemon's port refused under `read-only` and accepted under the profile; a
  write in the clone refused under both). Both agent profiles are copies of OpenRig's
  `implementer` and `qa` without the shared remote MCP servers (exa, context7), and the clone
  keeps its own npx MCP servers off. OpenRig documents that its tests prove the launch flags, not
  Codex's enforcement, so a reviewer's permissions count only after a write attempt has been
  refused in the seat itself.
- **Demonstrated (2026-11-22):** one handoff through OpenRig's queue, with no message relayed by
  hand. The lead's Claude Code session queued the bounded task (a two-phrase wording fix in arc42
  §13) with a return route; the worker claimed it, committed the change in the clone (one file,
  one line) and handed the exact commit SHA to the reviewer; the reviewer checked that commit
  read-only against `evidence_agent.py` and handed its finding (no findings) back to the return
  route, where the lead read it from the queue. Checked in the seats themselves: the worker
  process ran with the normal home and the dedicated config dir, its own Claude login reported
  logged in, and none of the calling shell's GitHub or messaging tokens or SSH agent reached it;
  the reviewer's Codex session recorded `gpt-6.2-sol`, effort `max`, approval `never` and
  read-only file access, and its `touch` in the clone failed with "Operation not permitted". The
  lead typed two things into seats: the default answer (browser tools off) to Claude's one-time
  "Claude in Chrome" notice at the worker's first start, and the write check. A first launch
  without the permission allowlist stopped at a read prompt during the worker's orientation, so
  the team was relaunched with it. The demo commit stays in the clone. Hashes before and after
  the demo show Erhan's real Codex configuration and hooks, Claude settings, plugins and skills,
  `~/.agents/skills`, `~/.tmux.conf` and the Herdr Desktop files compared (`keys.json`,
  `settings.json`, the `layouts` and `mods` folders) unchanged; the demo opened plain tabs, not
  the Rig view, which adds OpenRig's own files there (below). The real
  `~/.claude.json`, which the running lead session rewrites, names no trial path.
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

## LiteParse with OCRia-nano-1 (diagnostic only, opt-in)

- **Tool:** `tools/commentary_rag/liteparse_ocr.py`, a standalone diagnostic like the layout probe:
  the pilot never imports it, its offline tests replace liteparse at the import seam, and liteparse
  is in no lockfile, service environment or image. It runs in an ephemeral environment with an
  exact pin, `uv run --no-project --with liteparse==2.21.4 python tools/commentary_rag/liteparse_ocr.py`
  (the official Python package of `run-llama/liteparse`, Apache-2.0, checked on 2026-11-28).
- **Output:** the report goes to stdout only, as ASCII-only JSON bytes (every other character as a
  JSON escape) written past Python's text layer, so they read as UTF-8 whatever encoding stdout is
  set to (the locale or `PYTHONIOENCODING`); the tool has no output option. Write each report into
  a new folder under the git-ignored `tools/commentary_rag/local/` (or outside the repository), so
  that a repeat cannot overwrite an earlier one, and chain the folder steps with the parse, so that
  a failed `mkdir` or `mktemp` stops before the redirect:
  `mkdir -p tools/commentary_rag/local && out=$(mktemp -d tools/commentary_rag/local/liteparse-XXXXXX) && ... > "$out/2021-07-01-p3-4.json"`;
  a refused run leaves that file empty and exits 1. The JSON holds every text item and layout
  block (every field of liteparse's block: table header and rows with each cell's text,
  box and items, code and grid lines), each with its bounding box and 1-based source page; the
  backend liteparse reports; the liteparse version; and, for OCRia-nano-1, the model directory, the
  files with their pinned SHA-256 and the environment check, never which runtime the loader chose.
  In liteparse 2.21.4 `get_config()` fails (AttributeError on `keep_clipped_text`), so the tool
  reads the same values from the native configuration object; there `table_model` is only an
  explicit override (with ocria-nano, liteparse uses the package's TableNet and still reports
  none), so the report calls it `table_model_override`. The tool also sets `max_pages`: without it,
  liteparse 2.21.4 returned 1,000 pages of a generated 1,005-page PDF parsed without `--pages`
  (OCR off, 2026-11-28; observed, not a test), which the tool refuses as incomplete.
- **Temporary files:** besides the report on stdout, `parse` writes one temporary file with either
  backend: liteparse's native stderr (file descriptor 2) goes into a file from Python's
  `tempfile.TemporaryFile` in the system temporary directory while the parser runs (on macOS and
  Linux it keeps no name in the directory, on Windows it does until it is closed) and is then
  passed on to stderr; it is gone when the parse ends. Python may first write and remove a small
  probe file there to check that the directory is writable. So a parse needs a writable temporary
  directory. `pull` downloads with `HF_HOME` naming an empty temporary directory and lets liteparse
  install the model files into the model directory. Temporary files of liteparse's own native code
  are not checked here.
- **Backend:** always named, `--ocr-backend ocria-nano` or `--ocr-backend none`; there is no default
  and no Tesseract choice, and a parser that resolves another backend is refused before it parses.
  `--ocr-backend none` needs no model, model directory or environment check. With OCR off the tool
  still names a backend, because liteparse otherwise makes an installed ocria-nano package the
  resolved backend and its layout model changes the blocks of born-digital pages (seen in the
  2026-11-28 evaluation, not a test).
- **OCRia-nano-1, before a parser exists:** another platform than macOS arm64 is refused, before a
  missing model is mentioned; so is any variable named `DYLD_*` or `LD_*`, or `ORT_DYLIB_PATH`,
  present at all, even empty, since the dynamic loader or liteparse could then load an ONNX Runtime
  the pins do not cover. The tool then resolves one absolute model directory,
  `LITEPARSE_MODEL_DIR` (refused when empty or relative) or else `$HOME/.cache/liteparse/models`
  (refused without an absolute `HOME`), and writes it back to `LITEPARSE_MODEL_DIR`, so that
  liteparse lists that folder and parses with it set; a package liteparse lists elsewhere is
  refused. The package must be ocria-nano 1.0.0 with exactly the sixteen pinned files, each matching
  its bytes and SHA-256: a missing or incomplete package, another version, or a changed, missing or
  additional file (a stray `.DS_Store` counts) is refused.
- **Asset pins:** the sixteen files of ocria-nano 1.0.0 as installed on macOS arm64, checked on
  2026-11-28: the model files equal liteparse's release pins and Hugging Face's files at revision
  v1.0.0, the ONNX Runtime 1.31.1 library liteparse's NuGet pin, `LICENSE` Hugging Face's file
  (liteparse fetches it without a check) and `manifest.json` the one liteparse's pull writes.
- **Model download:** `pull` is the only command that downloads (OCRia-nano-1, `ocria-nano` 1.0.0,
  Hugging Face `llamaindex/OCRia-nano-1`). Before liteparse downloads it refuses the platform,
  variable and model-directory cases above; it then runs liteparse's pull with the one absolute
  model directory set, without `HF_TOKEN` and with `HF_HOME` naming an empty directory, and checks
  the sixteen pins after the download. While downloading, liteparse checks the model files and the
  ONNX Runtime against pins built into its release. The offline tests replace liteparse's pull with
  a stand-in that only records the call, so the transfer, what it sends and liteparse's own checks
  are not tested.
- **OCR failures:** liteparse 2.21.4 reports a page whose OCR failed only on native stderr
  (`[ocr] failed for page N: ...`, then `[ocr] k/n page(s) failed OCR; continuing with partial
  results`) and returns the page anyway, without OCR text; it raises only when every OCR task failed
  and one of them was on a text-poor page (read in its 2.21.4 source and seen from the installed
  library). The tool captures file descriptor 2 during the parse and refuses the run on any `[ocr]`
  line, so nothing reaches stdout; a page without OCR text in a printed report had no OCR failure.
- **Input:** the PDF an edition (`--edition`, an effective date) or a source ID (`--source-id`, a
  `sources` entry's `source_id`, for a date two commentaries share, such as 2023-01-01) names must
  be the only one it names, must lie inside `--root` once links are resolved, must not be a link
  itself and must match its manifest's SHA-256. A manifest that cannot be read (one nested too
  deeply for the JSON parser included), has neither a `sources` nor an `editions` list (a section
  that is not a list counts), or names a commentary path no file system can take (an embedded NUL)
  is refused by name. The checks see the manifest as the JSON parser decodes it, in which a
  repeated key keeps only its last value. `sources` and `editions`, whichever it holds, are each
  checked by their own structure, so a valid `sources` section cannot hide an `editions` section
  that fails its checks: `sources` is a list of objects with a string path without NUL, a string
  SHA-256 and a list of effective dates;
  `editions` is a list of objects, each with a `documents` list, in which every document is an
  object with a `kind`, every commentary document has a string path without NUL and a string
  SHA-256, and every edition holding a commentary document has an `effective_date`. Paths of other
  document kinds and the values of the dates are not checked. With both sections valid, the PDF
  comes from `sources`.
- **Network:** `parse` never downloads a model. `uv run --with` fetches liteparse itself when uv's
  cache lacks it, and `uv --offline` stops only uv's own fetches, not the parser process (liteparse
  turns ONNX Runtime's telemetry off only when `ORT_DISABLE_TELEMETRY` is unset; an inherited value,
  `0` included, is kept). A parse without network is therefore the one run, with a warm cache,
  under the network-denying sandbox, as on 2026-11-28 (observed, not a test):
  `sandbox-exec -p "(version 1)(allow default)(deny network*)" uv run --offline --no-project --with liteparse==2.21.4 ...`.
- **Licence:** the weights are not under LiteParse's licence but under the OCRia-nano-1 Model License
  (a modified OpenRAIL-M; pulling accepts it). Its Attachment A restricts use above revenue or
  funding thresholds and in competing document-parsing services, except for Research Purposes,
  which include evaluating and benchmarking the model. Treat the weights and their output as
  evaluation material: they stay out of the corpus and out of any product path until Erhan decides
  otherwise.
- **Local material:** model files, renders, parser output and scores stay in scratch or git-ignored
  folders (`tools/commentary_rag/local/`); none of it is committed.
