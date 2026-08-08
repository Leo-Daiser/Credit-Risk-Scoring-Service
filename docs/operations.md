# Operational readiness and local SLO targets

This document describes portfolio-service operating expectations. Targets below
are design objectives for a controlled deployment, not measured guarantees for
arbitrary hardware or a banking SLA.

Public deployment must follow the route and configuration boundary in
[`endpoint_access_matrix.md`](endpoint_access_matrix.md). In particular, do not expose the
operator UI or catch-all backend access in `APP_ENV=public`.

## Service objectives

| Signal | Local portfolio objective | Measurement |
|---|---:|---|
| Availability | 99.5% per month | successful `/ready` probes |
| Scoring errors | 0% in load smoke | HTTP status from `/score` |
| Scoring latency | p95 <= 1,500 ms at concurrency 2 | `scripts/load_smoke.py` |
| Audit durability | 100% when `DATABASE_REQUIRED=true` | `logging_status=persisted` |
| Model identity | one contract per version | validated bundle manifest |

The latency target includes feature alignment, calibrated inference, local reason
codes and synchronous PostgreSQL audit logging. It is intentionally modest for a
single-container portfolio deployment. Capacity must be re-measured after changing
hardware, worker count, model bundle or reason-code implementation.
Exact CatBoost SHAP computation is limited to one thread per request to avoid
nested CPU oversubscription when several API requests are handled concurrently.

## Load smoke

Start the production-like stack with a locally generated bundle:

```powershell
docker compose up -d --build
.\.venv\Scripts\python.exe scripts\load_smoke.py --requests 50 --concurrency 2
```

If the deployment enables `API_KEY`, expose it only in the current process
environment before running the command:

```powershell
$env:API_KEY = "<deployment-api-key>"
.\.venv\Scripts\python.exe scripts\load_smoke.py
Remove-Item Env:API_KEY
```

The script checks `/ready`, validates its payload against `/feature_schema`, uses
unique idempotency and correlation IDs, performs warmup requests, and fails when
the configured p95 or error-rate objective is exceeded. Its JSON report is written
to `artifacts/reports/load_smoke_report.json`, which is gitignored.

Latest local run on 2026-08-07 (Windows host, Docker Desktop, one API container,
bundle `catboost_calibrated-6dba880cb73a`) measured 50 requests after warmup:

- 50 successful responses, 0 errors, 50 persisted audit records;
- p50 `1,032.71 ms`, p95 `1,256.70 ms`, p99 `1,520.78 ms`;
- throughput `1.91 requests/second` at concurrency 2.

These numbers are local-run-specific. A diagnostic run at concurrency 4 did not
increase throughput and raised p95 to approximately `2.74 seconds`, indicating CPU
saturation in the single-container configuration. Higher capacity should be
validated with replica-level scaling and per-replica metric collection.

## Request correlation and logs

The API accepts a safe `X-Correlation-ID` (`A-Z`, `a-z`, digits, `.`, `_`, `:`,
`-`; maximum 128 characters) and returns it in the response. Missing or unsafe
values are replaced with a UUID. Application request events use one JSON object per
event and include only allowlisted operational fields. Uvicorn's duplicate access
log is disabled; lifecycle logs may retain Uvicorn's native format. Feature payloads
and API keys are not logged.

Use text logs only for local debugging:

```text
LOG_FORMAT=text
```

## Triage runbook

1. Check process liveness at `/health`.
2. Check `/ready`; failure means the validated model bundle or PostgreSQL is
   unavailable.
3. Inspect `/metrics` for HTTP status and latency changes.
4. Search container logs by `correlation_id`; do not copy feature payloads into
   incident notes.
5. For a model-load failure, verify the mounted path and regenerate the trusted
   bundle with `python -m src.cli prepare-production-model`. Never download and
   deserialize an untrusted joblib artifact.
6. For a database failure, restore PostgreSQL before serving when
   `DATABASE_REQUIRED=true`; scoring responses intentionally fail closed.
7. Treat a critical offline drift report as an investigation signal, not as an
   automatic outage or retraining trigger.

## Batch worker

The API only accepts uploads and creates durable jobs. The worker is a separate
process:

```powershell
python -m src.worker.main
```

Inspect it independently from the API:

```powershell
docker compose ps worker
docker compose logs --tail 100 worker
```

Jobs progress through `queued -> running -> completed|failed`. A worker restart
requeues `running` jobs older than 30 minutes. Successful inputs are deleted when
`BATCH_RETAIN_INPUTS=false`; failed inputs are retained for controlled diagnosis.
Do not attach uploaded feature rows to tickets or logs. Result files contain only
the configured ID, probability, decision, risk band, model version and missing
feature count.

## Known deployment limits

- One API container, one batch worker, one frontend/BFF and one PostgreSQL instance
  are used in Compose.
- Local artifact storage is single-host. Multi-host scaling requires S3-compatible
  object storage before API and worker replicas can move independently.
- The cabinet is a single-tenant local/demo operator surface and is disabled in
  `APP_ENV=public`. Re-enabling it in a future deployment requires an identity-aware
  reverse proxy or platform SSO; the BFF-held API key is service authentication,
  not end-user authentication or RBAC.
- Repository-level in-memory commercial rate limiting protects one local/demo API
  process. It is not shared between replicas; TLS termination, secrets manager,
  WAF/reverse-proxy or Redis-backed limits and autoscaling remain target-platform
  responsibilities.
- Load-smoke results are host-specific and must not be presented as universal model
  properties.
