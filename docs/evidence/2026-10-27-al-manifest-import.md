# BAG AL manifest import: SQLite, PostgreSQL and container verification

Verification record for the dated, hash-checked import of the BAG Analysenliste editions of
1 January and 1 July 2026 ([ADR-021](../adr/021-al-manifest-import.md)). Captured on
2026-10-27 on an Apple Silicon Mac with Docker Desktop (Docker Engine 29.9.2, arm64 Linux
containers, about 8 GB for the Docker VM). PostgreSQL is `pgvector/pgvector:pg16` in the
isolated compose project `tarifhub-verify` (`deploy/docker-compose.verify.yml`): its own
container names, image tags and loopback ports, storage on tmpfs, no volume, nothing read
from a `.env` file.

## Tested revision

The uncommitted working tree on top of `bb151ff` (branch `feat/slim-ai-workflow`). Nothing
was committed or pushed, so **GitHub CI has not run on this state**. The files under test, by
git blob ID (a commit of exactly these files carries the same IDs; compare with
`git ls-tree <commit> <path>`):

| Blob | File |
|---|---|
| `f1bc7fc82694` | `services/ingestion/src/tarifhub_ingest/ingestion/manifest.py` |
| `cc45ac7d997c` | `services/ingestion/src/tarifhub_ingest/cli.py` |
| `cb1ced1e84d1` | `services/ingestion/src/tarifhub_ingest/ingestion/pipeline.py` |
| `8c8e2890a129` | `services/ingestion/src/tarifhub_ingest/ingestion/source_loader.py` |
| `4bd73d82f199` | `services/ingestion/src/tarifhub_ingest/ingestion/fill_reuse.py` |
| `0944c676d936` | `services/ingestion/src/tarifhub_ingest/adapters/bag_eal.py` |
| `1cfb8365d315` | `services/ingestion/src/tarifhub_ingest/storage/tariff_repository.py` |
| `7c50ca5b23b3` | `services/ingestion/tests/test_manifest_import.py` |
| `2fa2b136a8a1` | `services/ingestion/tests/fixtures/eal/Analysenliste per 1. Januar 2026_fixture.xlsx` |
| `7a04a67b60d5` | `services/ingestion/tests/fixtures/eal/Analysenliste per 1. Juli 2026_fixture.xlsx` |
| `508eb3197cb4` | `services/ingestion/tests/fixtures/eal/make_edition_fixtures.py` |
| `d49421cd0b49` | `services/serving/tests/test_manifest_editions.py` |
| `ce2bfb20a85f` | `data/manifests/bag-al.json` |
| `b61fbbfb12c1` | `deploy/docker-compose.e5.yml` |
| `f42e3f94030c` | `deploy/docker-compose.verify.yml` |
| `e18221b38315` | `.github/workflows/ci.yml` |

## Results obtained earlier the same day (before the final changes)

These ran before the NFC-tolerant lookup, the unusable-path refusals, the CI step and the
narrowed e5 mounts. They are kept as history; every check that the final changes touch was
re-run below.

- The first PostgreSQL run of the existing suite: 358 tests, 1 failure. It was test setup:
  the review path's 16-dim stub embedder does not fit `vector(1024)`. It was fixed with the
  convention `tests/test_review_api.py` already uses.
- A direct `import_manifest` call that failed mid-import left the January rows and their
  audit events committed, on SQLite and PostgreSQL alike. The import then took ownership of
  its transaction (ADR-021).
- The container run on that state matched the one below, except that a byte-exact Linux
  copy of the real files was refused (exit 2, "file not found" for the two July PDFs that
  macOS stored with NFD names). That finding led to the NFC-tolerant lookup.
- Reviews of that state: the determinism audit was clean. Codex (gpt-6.1-sol, read-only)
  found one P2, a failed rollback could leave the batch pending; it was fixed test-first,
  and a re-check found nothing. The verifier failed requirement 4 for the then
  undocumented NFD limitation, which the lookup now removes.

## Red phase of the final changes

Each new test failed first, for the expected reason:

- On a Linux file system (container, Python 3.12.13), with no lookup yet, the NFD-named
  workbook and PDF were "file not found" through their NFC paths. Two names that differ only
  in normalisation did not raise.
- A symlink loop or a listable but unsearchable folder, under either the manifest or a listed
  document, crashed instead of being refused. On Python 3.12.13 all four cases raised
  `RuntimeError` or `PermissionError`; on Python 3.13.12 the two folder cases raised
  `PermissionError`.

## Re-run after the final changes

### Test suites on the host (macOS)

| Suite | Python | Legs | Tests | Failures | Skipped |
|---|---|---|---|---|---|
| ingestion | 3.13.12 | SQLite + PostgreSQL | 376 | 0 | 2 |
| ingestion | 3.13.12 | SQLite only | 284 | 0 | 4 |
| ingestion | 3.12.13 | SQLite + PostgreSQL | 376 | 0 | 2 |
| ingestion | 3.12.13 | SQLite only | 284 | 0 | 4 |
| serving | 3.13.12 | SQLite + PostgreSQL | 151 | 0 | 2 |
| serving | 3.13.12 | SQLite only | 127 | 0 | 2 |
| serving | 3.12.13 | SQLite + PostgreSQL | 151 | 0 | 2 |
| serving | 3.12.13 | SQLite only | 127 | 0 | 2 |

With PostgreSQL, ingestion collected 92 engine-parameterised PostgreSQL cases and ran 91,
plus the three PostgreSQL-only audit tests; serving collected and ran 24. The ingestion
skips are the ambiguity test, in both engine legs, because APFS cannot hold two names that
differ only in normalisation, plus, offline, the three PostgreSQL-only audit tests. The
serving skips are the two pgvector-only tests on SQLite. `ruff check` is clean in both
services.

### Linux file system (container)

Both commands are listed under Reproduction, and each result below came from running exactly
that command (the credential placeholders filled in).

- The whole manifest test file on the container's own overlayfs, pytest as an unprivileged
  user: **76 passed, 0 skipped**. The ambiguity test runs there.
- The new CI step's exact script, extracted from `ci.yml` and run against the isolated
  PostgreSQL: **70** PostgreSQL manifest tests and **5** PostgreSQL served-edition tests ran,
  0 skipped. The guard itself was checked by running the same script on the macOS host:
  with `TARIFHUB_PG_TEST_URL` unset it fails (pytest exit 5, nothing selected), and with the
  ambiguity test's PostgreSQL case skipped there, the junit check fails it.

### Container path (rebuilt images, final code)

The images were built with the existing Dockerfiles and the e5 build argument. The
`manifest.py`, `cli.py` and `pipeline.py` installed in the ingestion image match the working
tree byte for byte. The real e5 model (`intfloat/multilingual-e5-large`, 1024 dimensions)
loaded offline (`HF_HUB_OFFLINE=1`). No LLM client is installed and `ANTHROPIC_API_KEY` is
unset in the containers.

| Step (CLI in the ingestion container, against PostgreSQL) | Result |
|---|---|
| Write failure forced on a July row (database trigger) | exit 1; 2283 tariff and 2283 audit rows were inserted, then rolled back to 0 |
| Import of both editions | exit 0; January 1279 and July 1280 positions frozen, 0 flagged, 0 parse failures; all 2559 rows carry 1024-dim vectors |
| Serving: diff of version 1 and 2 | 4700: tax points 21.6 to 16.6; 1368: 59.4 to 64.4; `valid_from` 2026-01-01 to 2026-07-01 |
| Serving: `as_of` 2026-03-15 and 2026-08-15 | 4700: 21.6 and 16.6; 1368: 59.4 and 64.4; 1779: 404, then 73.3 |
| Repeat import | exit 0, both editions `already_present`; row counts and the record fingerprint unchanged |
| The same import on a byte-exact Linux copy of the real files | exit 0, both editions `already_present`: the NFD-named PDFs are found through their NFC manifest paths |
| Semantic search "Auftragstaxe" (serving, e5 query side) | 4700 ranks first |

Mounts and permissions: the manifest and the AL source folders are mounted read-only
(writes fail with "Read-only file system"); the container user, uid 10001, reads mode 644
files and verifies all 8 SHA-256 values. Of the Hugging Face cache, the e5 overlay now mounts
only `~/.cache/huggingface/hub`, read-only, for `ingestion`, `serving` and `ingestion-batch`.
In the `ingestion` (uid 10001) and `serving` (uid 1001) containers only `hub` is visible, no
login token, and the e5 embedder loads offline at 1024 dimensions.

### Review of the final changes

A focused review ran once the edits were complete: the verifier passed all six decisions;
the security review found two Low issues (the unusable-path crashes above, and the verify
overlay's unused `ingestion` service published on all interfaces); Codex (gpt-6.1-sol,
read-only) raised one P3 on how this record counts PostgreSQL cases. All of them were fixed
before the re-runs above.

## Reproduction

From the repository root, in bash or zsh. `<user>` and `<password>` are the `db` service's
`POSTGRES_USER` and `POSTGRES_PASSWORD` in `deploy/docker-compose.yml`. The first import embeds
2559 passages on CPU, about 0.2 s each, which took 9 to 10 minutes here.

```bash
V=(-p tarifhub-verify --env-file /dev/null -f deploy/docker-compose.yml
   -f deploy/docker-compose.e5.yml -f deploy/docker-compose.verify.yml)
docker compose "${V[@]}" up -d --wait db
docker compose "${V[@]}" build ingestion-batch serving
docker compose "${V[@]}" run --rm -T ingestion-batch \
  python -m tarifhub_ingest.cli --manifest /repo/data/manifests/bag-al.json
docker compose "${V[@]}" up -d --wait serving
curl -s 'http://127.0.0.1:18001/api/v1/tariffs/EAL/4700/diff?from=1&to=2'
curl -s 'http://127.0.0.1:18001/api/v1/tariffs/EAL/4700?as_of=2026-03-15'
curl -s 'http://127.0.0.1:18001/api/v1/tariffs/EAL/4700?as_of=2026-08-15'
# The PostgreSQL test legs (after the demo: one existing test writes into this database)
(cd services/ingestion && env -u ANTHROPIC_API_KEY \
  TARIFHUB_PG_TEST_URL="postgresql://<user>:<password>@localhost:55432/tarifhub" \
  uv run --no-sync pytest -q)
docker compose "${V[@]}" --profile app --profile batch down
```

The manifest tests on a Linux file system:

```bash
docker run --rm -v "$PWD/services/ingestion:/src:ro" \
  python:3.12-slim@sha256:a39549e211a16149edf74e5fdc9ef03a6767e46cd987c5048b6659b6c9904c94 sh -c '
  set -e
  mkdir -p /work/services/ingestion && tar -C /src --exclude=./.venv -cf - . | tar -C /work/services/ingestion -xf -
  pip install -q --disable-pip-version-check --root-user-action=ignore uv
  useradd -m tester && chown -R tester /work && cd /work/services/ingestion
  setpriv --reuid=tester --regid=tester --init-groups env HOME=/home/tester \
    sh -c "uv sync -q --frozen --extra dev && uv run --no-sync pytest -rs -p no:cacheprovider tests/test_manifest_import.py"'
```

The new CI step on Linux, against the isolated PostgreSQL (the `db` service must be up):

```bash
docker run --rm --network tarifhub-verify_default -v "$PWD:/src:ro" \
  -e TARIFHUB_PG_TEST_URL="postgresql://<user>:<password>@db:5432/tarifhub" \
  python:3.12-slim@sha256:a39549e211a16149edf74e5fdc9ef03a6767e46cd987c5048b6659b6c9904c94 sh -c '
  set -e
  mkdir -p /work && tar -C /src --exclude=.venv -cf - .github services/ingestion services/serving db/schema.sql | tar -C /work -xf -
  pip install -q --disable-pip-version-check --root-user-action=ignore uv
  cd /work && uv run -q --no-project --with pyyaml python - > /tmp/step.sh <<PY
import yaml
steps = yaml.safe_load(open(".github/workflows/ci.yml"))["jobs"]["python-parity"]["steps"]
print(next(s["run"] for s in steps if s.get("name", "").startswith("Manifest import")))
PY
  useradd -m tester && chown -R tester /work
  setpriv --reuid=tester --regid=tester --init-groups env HOME=/home/tester UV_FROZEN=1 RUNNER_TEMP=/tmp \
    sh -c "for s in services/ingestion services/serving; do (cd \$s && uv sync -q --frozen --extra dev); done; bash -e /tmp/step.sh"'
```

## Remaining limitations

- GitHub CI has not run this state. The new `python-parity` step was exercised only as
  described above, on Linux in a container.
- The ambiguity test cannot run on macOS and skips there with that reason; it runs on Linux.
- Container timings come from Docker Desktop on arm64 with e5 on CPU.
- Under PostgreSQL READ COMMITTED, a non-colliding row from another writer can still land
  between the import's final re-check and its commit (ADR-021).
- `tests/test_audit_pg_roundtrip.py` writes into the database that `TARIFHUB_PG_TEST_URL`
  names; point that variable only at a throwaway server.
- Stored codes stay as the workbook gives them (`4700`); lookups by `4700.00`, an
  edition-wide change list and RAG are not part of this increment.
