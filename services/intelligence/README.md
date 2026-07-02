# tarifiq

**TarifIQ** is the tarifhub intelligence service (Layer 2). It layers deterministic
*reasoning* (combinability/cumulation rules, the **TARMED↔TARDOC cross-walk**, and rule
validation) on top of the frozen tariff facts served by TarifCore (Layer 1). Runs fully
offline (bundled frozen tables, no network, no live LLM) so the suite is reproducible
anywhere.

## The freeze line, one layer up

Rule **evaluation is deterministic**: every endpoint is a pure function of the request
and the frozen rule/cross-walk tables (each content-hashed and versioned, the same
discipline L1 applies to tariff records). AI may only **suggest** a candidate rule or
cross-walk entry *before* it is frozen: a single, clearly marked, replaceable seam
(`crosswalk/tarmed_tardoc.py::ai_rule_suggest`) that a human reviews and validates
(`POST /v1/validate`) before freezing. Nothing here computes or mutates a billing value,
and no endpoint calls a model. An AST boundary test enforces that the value path imports
no LLM client.

## API

| Method | Path | Purpose |
|---|---|---|
| GET | `/health` | Liveness/readiness. |
| POST | `/v1/combinability-check` | Evaluate submitted positions against the frozen rule set (exclusivity, requirement, cumulation caps). |
| GET | `/v1/crosswalk/{tarmed_code}` | Look up a TARMED code in the frozen TARMED→TARDOC table (404 if unknown). |
| POST | `/v1/validate` | Deterministically validate a candidate rule (structural + referential) before freeze. |

## Layout

```
src/tarifiq/
├─ main.py                    FastAPI app (4 endpoints); no LLM import
├─ config.py                  12-factor settings (offline-first; SERVING_BASE_URL when live)
├─ models/rule_model.py       Pydantic contracts (rules carry NO billing value)
├─ rules/combinability.py     deterministic combinability/cumulation over the frozen rule set
├─ crosswalk/tarmed_tardoc.py deterministic cross-walk lookup + replaceable ai_rule_suggest() seam
├─ validators/rule_validator.py  pre-freeze structural + referential validation
└─ store/frozen_client.py     reads frozen tariff facts from serving (httpx) + offline stub
```

## Develop

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"     # add the dev extra for ruff
pytest -q                   # fully offline
ruff check .

# Run the API
tarifiq                     # uvicorn tarifiq.main:app on :8070
curl -X POST localhost:8070/v1/combinability-check \
  -H 'content-type: application/json' \
  -d '{"system":"TARDOC","positions":[{"code":"AA.00.0010"},{"code":"AA.00.0030"}]}'
curl localhost:8070/v1/crosswalk/00.0010
```

## Configuration (env)

| Var | Default | Meaning |
|---|---|---|
| `TARIFIQ_OFFLINE` | `1` (true) | Use the bundled offline frozen store. Set `0` to read live frozen records. |
| `SERVING_BASE_URL` | `http://localhost:8000` | L1 TarifCore serving API (also `TARIFIQ_SERVING_BASE_URL`). |
| `TARIFIQ_HTTP_TIMEOUT` | `10` | httpx timeout (seconds) for the serving client. |
| `ANTHROPIC_API_KEY` | _unset_ | Reserved switch for a future live rule-*suggestion* model (pre-freeze, human-reviewed). Never enables a live call in this skeleton. |

The optional `ai` extra (anthropic) is commented out and never required for tests; the
rule-suggestion seam returns a deterministic placeholder until it is deliberately wired.
