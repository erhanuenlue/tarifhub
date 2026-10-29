# ADR-022: Install the Python images from their lockfiles and build every image before merge

*Status: Accepted · Date: 2026-10-29 · Decider: Erhan (+ AI-assisted analysis)*

## Context
CI tests and scans the committed `uv.lock` files and never re-resolves them (the owner decision of 2026-06-11 noted in `ci.yml`), but the four Python Dockerfiles ran `pip install .`, which re-resolved the open `pyproject.toml` ranges on every build. Built in October 2026, the images differed from their locks in 17 to 37 package versions, and the MCP image no longer started (`mcp` 2.3.0 instead of the locked 1.30.0). The `images` job ran on `main` only ([ADR-010](010-github-actions-devsecops.md)), so a broken image build showed up only after merge.

## Decision
We install each Python image's runtime dependencies from its committed `uv.lock` with `uv sync --locked --no-editable` (uv 0.13.6, pinned by image digest), so a lock that no longer matches its `pyproject.toml` fails the build instead of being re-resolved, and we build every image on pull requests as well as on `main`:

- **MCP exception:** the MCP lock's dev extra names the sibling `../serving` and `../ingestion` projects, which the MCP build context does not contain, so `--locked` cannot check that lock there. The MCP image installs with `--frozen`: exactly the lock, without the freshness check.
- **CI lock check:** the `images` job first runs `uv lock --check` in every service, MCP included, then builds all seven images and pushes none.
- **`WITH_E5=1`:** installs a dedicated `e5` extra (sentence-transformers only) from the same lock, never the `ai` extra with the LLM client.
- **Build contexts:** a `.dockerignore` per context (for serving, which builds from the repository root, a Dockerfile-specific allowlist) keeps host virtualenvs, bytecode and `node_modules` out of the images.

## Alternatives weighed
- **pip with an exported requirements file**: a second generated version list per service to keep in step with every lock, and pip cannot tell when it is stale.
- **Exact pins in `pyproject.toml`**: duplicates the lock by hand and leaves the transitive dependencies open.
- **`--frozen` in every image**: a stale lock would build without complaint wherever the CI check does not run; only MCP needs it.
- **Image builds on `main` only, as before**: a change that breaks an image build fails only after merge.

## Consequences
- (+) Each Python image installs the versions that the offline suites ran against and Trivy scanned.
- (+) A change that breaks an image build, a stale lock included, fails on its pull request.
- (-) CI builds the default images only and starts none of them. The `WITH_E5=1` images (about 8.6 GB each) and the container smoke checks were verified locally on macOS arm64 for PR #50 on 2026-10-29, not in CI. Revisit when an e5 image is deployed.
- (-) A local MCP build trusts its lock; only the CI check catches a stale one.
- (-) Every pull request now also runs the seven builds, about three minutes in CI.

*Lineage: new, no legacy counterpart; amends [ADR-010](010-github-actions-devsecops.md), whose image builds ran on `main` only.*
