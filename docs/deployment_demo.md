# Demo deployment

Model bundles remain outside Git and are mounted read-only. The normal demo journey is
assessment-first and therefore fails closed when the Riskline Public Profile Model is
missing. A rules fallback remains available for explicit development diagnostics, but
runtime and UI never report it as active ML.

## Local Docker demo

```powershell
.\scripts\start-demo.ps1
```

`start-demo.ps1` performs deterministic preparation, starts the stack, waits for
readiness and prints the exact model/offer status. It never removes volumes or modifies
source data.

Compose mounts `${MODEL_ARTIFACTS_PATH:-./artifacts/models}` read-only at
`/app/artifacts/models`. Expected optional files are:

- `production_model_bundle.joblib` — Full Credit Risk Model for internal scoring;
- `public_profile_model_bundle.joblib` — public Riskline profile;
- `offer_ranker.joblib` — optional future outcome ranker; rules remain default.

To validate the artifacts and build the public artifact only when it is missing:

```powershell
python -m src.cli prepare-local-ml
```

The command uses `configs/public_profile_model.yaml`. It may train only from the real,
ignored source configured there. If neither a trusted artifact nor that source exists,
it exits with `PUBLIC ML INACTIVE` and an actionable path; it never fabricates rows or
labels. `production_model_bundle.joblib` is validated but not retrained automatically.

After preparation, the equivalent manual startup is:

```powershell
docker compose -f docker-compose.yml -f docker-compose.demo.yml up -d --build
docker compose -f docker-compose.yml -f docker-compose.demo.yml ps
docker compose -f docker-compose.yml -f docker-compose.demo.yml exec -T api python -m src.cli verify-demo
```

`demo-setup` applies Alembic migrations and idempotently seeds only synthetic
`example.invalid` offers. Run the same operation outside Docker when needed:

```powershell
python -m src.cli setup-demo
python -m src.cli setup-demo --with-synthetic-events
python -m src.cli verify-demo
```

The optional events contain event names and a synthetic marker only; no financial
values or raw profiles are generated.

Local and demo modes use the `POSTGRES_*` variables as one credential source for
PostgreSQL, migrations and the API. Copying `.env.example` to `.env` therefore produces
a consistent Compose configuration. Always use `--build` after pulling migrations so
the one-shot `migrate` image contains the complete Alembic chain.

### Existing local volume recovery

Changing `POSTGRES_PASSWORD` does not change credentials already stored in a PostgreSQL
volume. Normal schema upgrades do not require deleting the volume. Restore the original
password in `.env`, start the database and update the role password deliberately if the
data must be preserved.

Only for a disposable development database, verify the exact volume first and then
recreate it manually:

```powershell
docker compose down
docker volume inspect credit-risk-scoring_postgres_data
docker volume rm credit-risk-scoring_postgres_data
docker compose -f docker-compose.yml -f docker-compose.demo.yml up -d --build
```

`docker volume rm` permanently removes the local database and is never executed by
setup scripts.

## Public-safe product profile

Copy `.env.example` to an ignored local file or inject variables through the
deployment platform. Generate a strong `API_KEY`; do not use the template fallback.
The example intentionally fails application startup while `API_KEY=change-me`.

```powershell
$env:API_KEY = "<strong-random-secret>"
$env:POSTGRES_PASSWORD = "<strong-random-db-secret>"
$env:DATABASE_URL = "postgresql+psycopg2://credit_user:<password>@db:5432/credit_risk"
docker compose -f docker-compose.yml -f docker-compose.public.example.yml up -d --build
```

Public mode disables OpenAPI, metrics, operator pages/BFF routes and demo
postbacks. `PUBLIC_SAFE_DEMO_ADAPTER_ENABLED=true` is explicit in the example only
to serve synthetic `example.invalid` click redirects; real partner callbacks stay off.

## Verification and smoke

```powershell
python -m src.cli verify-demo
python scripts/smoke_public_demo.py --base-url http://localhost:8000 --frontend-url http://localhost:3000 --mode public
```

For demo mode HMAC coverage:

```powershell
python scripts/smoke_public_demo.py --base-url http://localhost:8000 --frontend-url http://localhost:3000 --mode demo --postback-secret "<demo-secret>"
```

Run the browser E2E after the services are healthy:

```powershell
cd frontend
npx playwright install chromium
npm run test:e2e
```

The suite must pass in desktop and mobile projects. A local model-enabled run also
asserts that the public result is genuinely personalized; artifact-free CI keeps
the same browser path but accepts the explicitly labelled rules fallback because
model artifacts are intentionally absent from Git.

The script checks the assessment entry route, uses a band-only profile, tests matching/click tracking, and confirms
that operator pages, operator BFF, docs, OpenAPI, metrics and runtime diagnostics
are hidden in public mode. It never prints a supplied postback secret.

## Health semantics

- `/health` proves the API process is alive.
- `/ready` proves database access; it reports ML bundle and offer-catalog readiness
  separately. Missing optional ML is a degraded warning, not false success for ML scoring.
- `/v1/runtime/status` additionally checks migrations, catalog, partner config and
  public safety. It is API-key protected and returns 404 in public mode.
- the frontend container probes `/`; the optional `ml-worker` profile requires a model bundle.

To enable the worker, mount a trusted bundle at the configured path and run
`docker compose --profile ml-worker up`. The bundle remains outside Git and outside
the Docker build context.

## Known limitations

- the in-memory rate limiter is not multi-instance production-grade;
- the public example is a topology template, not managed TLS/WAF infrastructure;
- readiness does not claim that the optional production model is available;
- synthetic offers and `example.invalid` links are not bank products;
- the known transitive `image-size` advisory through Vinext must not be force-fixed
  with a breaking Vinext downgrade; re-evaluate when an upstream compatible fix exists.
