# Security: npm advisory triage (TarifGuard console)

`npm audit` reports seven advisories in this app's dependency tree (five moderate, one
high, one critical). This note records why none is exploitable in the submitted runtime,
and what was upgraded. The same rationale is summarised in the architecture documentation
(arc42 chapter 8, "Dependency advisories and the runtime boundary").

## The runtime boundary

The production artefact is a Next.js `output: "standalone"` image (`Dockerfile`). Its
runtime stage copies only the traced standalone server, `.next/static` and `public`. The
advisories reach that image in two different ways, and neither is reachable on the
request-serving path.

The Vitest test stack (`vite`, `vitest`, `esbuild`, `@vitest/mocker`, `vite-node`) are
`devDependencies`. They are installed only in the build stage and are never traced into the
standalone bundle, so they are absent from the running container (confirmed: no `vite`,
`vitest` or `esbuild` directory under `.next/standalone`).

PostCSS is different. The copy our own CSS pipeline uses is build-time only and was patched
(see below), but `next` also bundles its own `postcss@8.4.31`, and because `next` is a
runtime dependency that copy does travel into `.next/standalone`. That is also why
`npm audit` lists `next` itself among the flagged packages. It is still not exploitable at
serve time, because the advisory requires running PostCSS's CSS stringifier over untrusted
CSS, and `next start` never invokes PostCSS on request input. PostCSS runs only at build
time, over the project's own trusted sources.

## The advisories

| Package | Severity | Advisory | Class | Why it is not reachable |
|---|---|---|---|---|
| `vitest` | critical | Vitest UI server can read and execute arbitrary files | test | Requires the `vitest --ui` server to be listening. CI runs headless `vitest run`, and the runner is a `devDependency` not shipped. |
| `vite` | high | `server.fs.deny` bypass on Windows alternate paths | test | Vite dev server only, Windows-only path handling. The console is built with `next build`, not the Vite dev server, and the prod image has no Vite. |
| `vite` | moderate | Path traversal in optimized-deps `.map` handling | test | Vite dev server only. Not present at runtime. |
| `vite` | moderate | `launch-editor` NTLMv2 hash disclosure via UNC path (Windows) | test | Vite dev server only, Windows-only. Not present at runtime. |
| `esbuild` | moderate | Dev server lets any site read responses | test | Pulled transitively by `vite`/`vitest`. Dev server only, not present at runtime. |
| `@vitest/mocker`, `vite-node` | moderate | Depend on vulnerable `vite` | test | Part of the Vitest stack, `devDependencies`, not shipped. |
| `postcss` (bundled in `next`, so `npm audit` also flags `next`) | moderate | XSS via unescaped `</style>` in CSS stringify output | build | Reachable only by running PostCSS's stringifier over untrusted CSS. PostCSS runs only at build time over our own trusted sources, never at serve time. The app's own copy is patched (see below), and the residual copy ships inside `next` but is not on the serve path. |

## What was upgraded

`postcss` was the one direct, non-breaking fix: it was raised from `8.4.39` to `^8.5.10`
and resolves to `8.5.15`, which dedupes the whole build pipeline (`autoprefixer`,
`tailwindcss`, `postcss-*`, `vite`) onto the patched line. The only `postcss` copy still
below `8.5.10` is the one bundled inside `next@15.5.19`, which cannot be moved without
`next` shipping an update.

## Why `npm audit fix --force` is not applied

`npm audit fix --force` proposes downgrading `next` from `15.5` to `9.3.3` and forcing
`vite`/`vitest` to new majors. That would replace the shipped App Router runtime with a
six-major-version-old release to remove advisories that are already unreachable, so it is
rejected. `npm audit fix` without `--force` is a no-op here, because every remaining fix is
semver-major.

## Re-verify

```bash
cd apps/tarifguard
npm audit          # 7 advisories, all dev/build-time per the table above
npm run build      # clean standalone build, no workspace-root warning
```
