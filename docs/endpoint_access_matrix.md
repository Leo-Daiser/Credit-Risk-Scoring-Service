# Endpoint access matrix

This document is the central deployment-boundary reference. Application-level checks do not
replace reverse-proxy, firewall, TLS, WAF, or secret-management controls.

## Deployment modes

| Mode | Public UI | Operator UI | Demo adapters | Intended use |
|---|---:|---:|---:|---|
| `local` | enabled | configurable, enabled by default | allowed | local development |
| `demo` | enabled | configurable, enabled by default | allowed | controlled portfolio demo |
| `public` | enabled | always blocked | disabled unless explicit safe `example.invalid` mode | public MVP |

Public mode must use `DEMO_MODE=false`, `OPERATOR_UI_ENABLED=false`,
`PUBLIC_AUTH_STRICT=true`, an explicit `DATABASE_URL`, and a non-placeholder `API_KEY`.
`PUBLIC_SAFE_DEMO_ADAPTER_ENABLED=true` may only enable the bundled synthetic redirect adapter;
it cannot be combined with partner callbacks. Invalid combinations fail startup.

## Frontend routes

| Route | Class | Public-mode behavior |
|---|---|---|
| `/` | public | landing page |
| `/score` | public | browser-only payment and debt-load calculator |
| `/offers` | public | privacy-light profile and offer matching |
| `/credit-calculator`, `/debt-load-calculator`, `/loan-by-income` | public | static educational pages |
| `/refinance-check`, `/credit-history-guide` | public | static educational pages |
| `/operator`, `/operator/score` | local/demo-only | returns not found |
| `/operator/offers` | local/demo-only | protected catalog management; returns not found |
| `/commercial` | local/demo-only | returns not found |
| `/batches` | local/demo-only | returns not found |
| `/history` | local/demo-only | returns not found |
| `/model` | local/demo-only | returns not found |
| `/api/backend/**` | allowlisted BFF | public paths only; operator and unknown paths return not found |

The BFF strips browser-provided `X-API-Key`, `Authorization`, and `Cookie` headers. It adds the
server-side operator key only for allowlisted operator requests in local/demo mode. Partner
postbacks and arbitrary backend paths are never proxied by the browser BFF.

## Backend endpoints

| Method and path | Class | Enforcement |
|---|---|---|
| `POST /v1/profile/score` | public | rate limit; privacy-light bands only |
| `POST /v1/offers/match` | public | rate limit; public response schema |
| `POST /v1/offers/{offer_id}/click` | public | rate limit and tracked redirect |
| `POST /v1/analytics/public-event` | public | allowlisted page event; exact values rejected |
| `POST /v1/partner/postback` | partner-only | HMAC signature and stricter failure limit |
| `POST /score` | operator-only | operator API key |
| `GET /model_info` | operator-only | operator API key |
| `GET /feature_schema` | operator-only | operator API key |
| `GET /v1/dashboard` | BFF/operator-only | operator API key |
| `/v1/scoring/history` | BFF/operator-only | operator API key |
| `/v1/batch/**` | BFF/operator-only | operator API key |
| `GET /v1/analytics/commercial-summary` | operator-only | operator API key |
| `GET /v1/analytics/segment-opportunities` | operator-only | operator API key |
| `GET /v1/analytics/event-debug` | operator-only | operator API key |
| `GET /v1/offers/quality-report` | operator-only | operator API key |
| `GET/POST /v1/operator/offers` | BFF/operator-only | operator API key; list/create catalog items |
| `GET/PATCH /v1/operator/offers/{offer_id}` | BFF/operator-only | operator API key; detail/update |
| `POST /v1/operator/offers/{offer_id}/deactivate` | BFF/operator-only | operator API key; non-destructive deactivation |
| `POST /v1/operator/offers/{offer_id}/validate` | BFF/operator-only | operator API key; no-write validation preview |
| `GET /v1/offers` | local/demo-only | operator API key; not found in public mode |
| `GET /v1/runtime/status` | local/demo-only | operator API key; not found in public mode |
| `GET /health`, `GET /ready` | platform-only | expose only to load balancer/orchestrator network |
| `GET /metrics` | platform-only | not found in public mode; restrict at network boundary elsewhere |
| `/docs`, `/redoc`, `/openapi.json` | local/demo-only | disabled in public mode |

The current project has no end-user/operator login. Therefore operator pages are intentionally
unavailable in public mode even when the backend has an operator API key. A future authenticated
operator gateway can replace this local/demo-only UI boundary without changing public APIs.

## Public deployment checklist

1. Generate API and partner secrets in deployment secret storage; never commit them.
2. Set `APP_ENV=public`, `DEMO_MODE=false`, `OPERATOR_UI_ENABLED=false`, and
   `PUBLIC_AUTH_STRICT=true`.
3. Expose the frontend publicly; keep backend operator endpoints on a private network where
   possible.
4. Route partner callbacks directly to the backend and require HMAC validation.
5. Restrict `/health`, `/ready`, and monitoring access at the reverse proxy/orchestrator.
6. Add WAF or shared rate limiting before running multiple API instances.
