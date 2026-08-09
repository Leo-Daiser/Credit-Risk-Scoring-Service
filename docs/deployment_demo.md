# Demo deployment

The deployment profiles do not need raw Home Credit CSV files or a production
model bundle. Privacy-light profile and offer matching continue to work; raw ML
`/score` remains unavailable until a trusted bundle is mounted.

## Local Docker demo

```powershell
docker compose -f docker-compose.yml -f docker-compose.demo.yml up -d --build
docker compose -f docker-compose.yml -f docker-compose.demo.yml ps
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

The script uses a band-only profile, tests matching/click tracking, and confirms
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
