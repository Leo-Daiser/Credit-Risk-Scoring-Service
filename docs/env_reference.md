# Environment reference

Configuration is loaded from environment variables by `src.core.config.Settings`.
`.env.example` is local-only guidance; a public deployment must inject secrets through
the platform secret store and must not bake them into an image.

## Deployment and network

| Variable | Type / default | local | demo | public | Secret | Safe example / unsafe example |
|---|---|---|---|---|---|---|
| `APP_ENV` | enum / `local` | required | required | required | no | `public` / `production-ish` |
| `DEMO_MODE` | bool / `true` | optional | `true` | `false` | no | `false` / `true` in public |
| `OPERATOR_UI_ENABLED` | bool / `true` | optional | optional | `false` | no | `false` / `true` in public |
| `PUBLIC_AUTH_STRICT` | bool / `false` | optional | optional | `true` | no | `true` / `false` in public |
| `PUBLIC_SAFE_DEMO_ADAPTER_ENABLED` | bool / `false` | optional | optional | optional | no | `false`; set `true` only for the bundled `example.invalid` catalog |
| `APP_HOST`, `APP_PORT` | string,int / `0.0.0.0`,`8000` | optional | optional | optional | no | internal listener / directly exposed backend |
| `APP_NAME` | string | optional | optional | optional | no | `Riskline` |
| `BACKEND_URL` | URL / Compose `http://api:8000` | optional | required by frontend | required by frontend | no | private service URL / public operator backend |
| `FRONTEND_PORT` | int / `3000` | optional | optional | optional | no | `3000` |

## Database and authentication

| Variable | Type / default | local | demo | public | Secret | Safe example / unsafe example |
|---|---|---|---|---|---|---|
| `DATABASE_URL` | SQLAlchemy URL / composed PostgreSQL fields | optional | optional | required | yes | secret-managed DSN / committed password |
| `POSTGRES_USER`, `POSTGRES_DB`, `POSTGRES_HOST`, `POSTGRES_PORT` | strings,int | optional | Compose defaults | platform-specific | partly | dedicated DB role / superuser role |
| `POSTGRES_PASSWORD` | string / local `credit_pass` | optional | replace for shared demo | required | yes | random secret / `change-me-public-db` |
| `API_KEY` | string / none | needed for operator API | needed when operator UI is on | required and non-placeholder | yes | random 32+ bytes / `change-me`, `demo`, `secret` |
| `DATABASE_REQUIRED` | bool / `true` | optional | `true` | `true` | no | `true` |
| `INFERENCE_LOGGING_ENABLED` | bool / `true` | optional | optional | policy decision | no | `true` with retention controls |

Local/demo Compose uses `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`,
`POSTGRES_HOST` and `POSTGRES_PORT` as the single source of truth. The application
constructs its effective SQLAlchemy URL from those values. Do not add a second local
`DATABASE_URL`; public mode intentionally requires an explicit secret-managed DSN.

## Model, batch and worker

| Variable | Type / default | Requirement | Secret | Notes |
|---|---|---|---|---|
| `MODEL_BUNDLE_PATH` | path / `artifacts/models/production_model_bundle.joblib` | optional unless ML scoring is enabled | no | Mount the bundle at runtime; never commit it. |
| `MODEL_BUNDLE_REQUIRED` | bool / `false` | set `true` only for ML-scoring/worker deployments | no | Privacy-light matching remains ready without the bundle. |
| `TOP_REASON_CODES` | int / `5` | optional | no | Operator model explanation limit. |
| `MAX_BATCH_SIZE` | int / `1000` | optional | no | Synchronous batch limit. |
| `BATCH_STORAGE_DIR`, `BATCH_OUTPUT_DIR` | paths under `artifacts/` | optional | no | Use ephemeral or protected runtime volumes. |
| `BATCH_MAX_UPLOAD_BYTES`, `BATCH_MAX_ROWS` | int / `50000000`,`100000` | optional | no | Abuse/resource bounds. |
| `BATCH_WORKER_POLL_SECONDS` | float / `2` | optional | no | Worker poll interval. |
| `BATCH_RETAIN_INPUTS` | bool / `false` | keep `false` by default | no | Inputs may contain sensitive operator data. |

## Offers, partners and experiments

| Variable | Type / default | local/demo | public | Secret | Safe example / unsafe example |
|---|---|---|---|---|---|
| `OFFER_CONFIG_PATH` | path / `configs/offers.yaml` | required for demo seed | required for safe demo seed | no | committed synthetic catalog |
| `PARTNER_CONFIG_PATH` | path / `configs/partners.yaml` | required | required | no | registry containing env-key names only |
| `EXPERIMENT_CONFIG_PATH` | path / `configs/experiments.yaml` | required | required | no | rules-first config |
| `PARTNER_POSTBACKS_ENABLED` | bool / `true` | optional | explicit | no | `false` when callbacks are unused |
| `PARTNER_POSTBACK_SECRET` | string / none | needed for HMAC demo callbacks | required when callbacks enabled | yes | random secret / committed token |
| `REAL_PARTNER_ENABLED` | bool / `false` | keep `false` | keep `false` until integration review | no | `false` |
| `REAL_PARTNER_SECRET` | string / none | required only when real partner enabled | secret store only | yes | injected secret / YAML value |
| affiliate template env keys | URL templates / none | local ignored config | secret store only | yes | `ALFA_CREDIT_AFFILIATE_TEMPLATE` env / URL with token in Git |
| `OFFER_REFERENCE_ANNUAL_RATE` | float / `0.24` | optional | optional | no | calculation prior, not a quoted bank rate |
| `OFFER_RANKER_MODE` | enum / `rules` | `rules` | `rules` until label gates pass | no | `rules` / `commission_only` |
| `OFFER_RANKER_MIN_SAMPLES` | int / `200` | optional | optional | no | minimum supervised sample count |
| `OFFER_RANKING_DATASET_PATH` | path | optional offline | do not mount publicly | no | ignored generated artifact |
| `OFFER_RANKING_DATASET_REPORT_PATH`, `OFFER_RANKER_MODEL_PATH`, `OFFER_RANKER_METRICS_PATH`, `OFFER_RANKER_REPORT_PATH` | paths under `artifacts/` | optional offline | runtime mount only if needed | no | ignored generated artifacts |
| `PERSIST_EXACT_COMMERCIAL_VALUES` | bool / `false` | keep `false` | `false` | no | band-only persistence |
| `ANALYTICS_DEFAULT_DAYS` | `7|30|90` / `30` | optional | optional | no | operator aggregation window |

## Limits and logging

| Variable | Type / default | Notes |
|---|---|---|
| `RATE_LIMIT_ENABLED` | bool / `true` | In-memory limiter; use proxy/WAF limits for multiple instances. |
| `RATE_LIMIT_WINDOW_SECONDS` | int / `60` | Shared local window. |
| `RATE_LIMIT_PROFILE_SCORE` | int / `60` | Privacy-light profile limit. |
| `RATE_LIMIT_OFFER_MATCH` | int / `30` | Match limit. |
| `RATE_LIMIT_OFFER_CLICK` | int / `60` | Click limit. |
| `RATE_LIMIT_PUBLIC_EVENT` | int / `120` | Privacy-safe event limit. |
| `RATE_LIMIT_PARTNER_POSTBACK` | int / `30` | Callback request limit. |
| `RATE_LIMIT_INVALID_POSTBACK` | int / `8` | Stricter invalid-HMAC limit. |
| `LOG_LEVEL` | string / `INFO` | Do not enable payload logging. |
| `LOG_FORMAT` | `json|text` / `json` | JSON is recommended for containers. |

Public validation rejects demo mode, operator UI, non-strict auth, missing
`DATABASE_URL`, missing/placeholder `API_KEY`, and a callback-enabled deployment
without `PARTNER_POSTBACK_SECRET`. The safe public demo adapter flag only enables
the bundled `example.invalid` redirect adapter and cannot be combined with partner callbacks.
