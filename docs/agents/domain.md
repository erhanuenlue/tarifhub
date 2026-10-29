# Domain Docs

How the engineering skills should consume this repo's domain documentation when exploring the codebase. This repo is single-context.

## Before exploring, read these

- **`docs/arc42/12-glossary.md`**: the glossary chapter of the published docs site, and the current vocabulary reference. Read it wherever a skill says to read `GLOSSARY.md`.
- **`docs/adr/`**: read ADRs that touch the area you're about to work in. The register, one row per ADR with its status, is `docs/arc42/09-architecture-decisions.md`.

There is no root `GLOSSARY.md` and no `GLOSSARY-MAP.md` yet: don't flag their absence and don't suggest creating them upfront.

## File structure

```
/
└── docs/
    ├── adr/
    │   ├── 001-python-first-core.md
    │   ├── …
    │   ├── 020-codex-seat-model-lifecycle.md
    │   ├── template.md                  ← house ADR template
    │   └── legacy/                      ← pre-2026-06-11 register
    └── arc42/
        ├── 09-architecture-decisions.md ← ADR register
        └── 12-glossary.md               ← current vocabulary reference
```

`docs/adr/legacy/` (colliding pre-2026-06-11 numbers) and `docs/cockpit/adr/` (historical design package) are not part of the register: don't cite or continue their numbers.

## Use the glossary's vocabulary

When your output names a domain concept (in an issue title, a refactor proposal, a hypothesis, a test name), use the term as defined in `docs/arc42/12-glossary.md`. Don't drift to synonyms for a term it defines.

If the concept you need isn't in the glossary yet, that's a signal: either you're inventing language the project doesn't use (reconsider) or there's a real gap (note it for `/domain-modeling`).

## One glossary

Keep one authoritative definition per term. Don't create a root `GLOSSARY.md` or any second glossary, including where `/domain-modeling` would create `GLOSSARY.md` lazily when a first term is resolved. If a root glossary becomes necessary, first propose to Erhan how to keep one authoritative definition per term.

## ADRs

- **Numbering**: three digits, `NNN-slug.md`, overriding the four-digit `0001-slug.md` default in `/domain-modeling`'s ADR format. The next number is the highest top-level `docs/adr/NNN-*.md` plus one. Cite it as `ADR-NNN`.
- **Format**: the house template, `docs/adr/template.md`.
- **Register**: a new ADR also gets a row in `docs/arc42/09-architecture-decisions.md` and an entry under "9 · Architecture Decisions" in the `nav` of `docs/mkdocs.yml`.

## Flag ADR conflicts

If your output contradicts an existing ADR, surface it explicitly rather than silently overriding:

> _Contradicts ADR-005 (single AI seam), but worth reopening because…_
