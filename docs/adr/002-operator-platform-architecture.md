# ADR 002: Operator platform and durable batch workflow

- Status: accepted
- Date: 2026-08-07

## Context

The repository already had a production-like model bundle, online FastAPI
inference, PostgreSQL audit logging and offline CLI batch scoring. It did not have
an operator workflow. Running a CLI against configured local paths is useful for
development, but it is not a service boundary for users who need to submit a
registry, observe progress and retrieve a result.

The platform must remain suitable for a portfolio deployment on one machine. A
large collection of network services, Kafka, Kubernetes or a separate feature
store would increase operational surface without solving a demonstrated load or
ownership problem.

## Decision

Use three runtime processes and one relational source of truth:

1. `frontend`: React/Vinext operator cabinet and server-side BFF;
2. `api`: synchronous contracts, online scoring, audit queries and batch job creation;
3. `worker`: asynchronous batch scoring from a durable PostgreSQL queue;
4. PostgreSQL stores audit records and job metadata; a mounted artifact directory
   stores trusted model artifacts, temporary uploads and prediction-only results.

The API and worker are separate processes built from the same Python image. They
share the `ScoringService` and `ModelBundle` library instead of calling a fourth
inference service over the network. This preserves one implementation of schema
alignment, thresholding and probability calculation while allowing online and
batch workloads to scale independently.

## Request flows

### Online scoring

```text
browser calculator (no network request)

browser short form / expert JSON -> frontend BFF -> POST /score -> ModelBundle
                                                            -> PostgreSQL audit transaction
```

The BFF injects `X-API-Key` server-side. The browser never receives the deployment
secret. A successful response contains the persisted logging status when database
logging is required. The personal calculator sends only feature names present in
the current model schema and is explicitly labelled as a preliminary estimate; the
expert flow remains available for a complete prepared feature payload.

### Batch scoring

```text
browser -> frontend BFF -> POST /v1/batch/jobs
                         -> streamed file in artifact storage
                         -> queued row in PostgreSQL

worker -> SELECT ... FOR UPDATE SKIP LOCKED
       -> validate table against ModelBundle input contract
       -> prediction-only CSV
       -> completed/failed job row
```

The API does not perform batch inference inside an HTTP request. Job claiming uses
row locking so multiple workers cannot process the same queued job. A stale
`running` job is returned to the queue after a worker restart. The uploaded source
is deleted after successful processing by default; failed inputs are retained for
controlled diagnosis.

## Data ownership

| Data | Owner | Persistence |
|---|---|---|
| Online request and prediction | API | PostgreSQL, atomic transaction |
| Batch job status and summary | API/worker | PostgreSQL |
| Uploaded registry | worker workflow | artifact storage, temporary |
| Batch result | worker workflow | artifact storage, prediction-only |
| Model bundle | deployment pipeline | read-only trusted artifact |
| UI preferences | frontend | ephemeral; no product state in browser storage |

PostgreSQL stores paths and searchable metadata, not large file bytes. A future
deployment may replace the local artifact directory with S3-compatible object
storage behind the same workflow without changing the public job contract.

## Failure behaviour

- Model or database unavailable: `/ready` fails and Compose does not start dependent
  processes as healthy.
- Upload exceeds limits or has an unsupported extension: API rejects it before
  creating a job.
- Feature contract mismatch: worker marks the job `failed` with a bounded error.
- Worker termination during a job: stale `running` jobs are requeued on startup.
- Result artifact missing: download returns `410` instead of a false success.
- Duplicate online request ID: API returns `409` and does not write a second audit row.

## Security and privacy boundaries

- API key stays in BFF and backend process environments.
- The cabinet is a single-tenant operator surface and is disabled in public mode.
  A future public operator deployment must place it behind platform SSO or an
  identity-aware proxy; the backend API key is not treated as end-user authentication.
- Upload paths are generated from UUIDs; the original filename is metadata only.
- Download paths must resolve under the configured prediction directory.
- Feature payloads and API keys are excluded from application logs.
- Raw datasets, uploads, prediction files and model artifacts are gitignored.
- The interface states that a model-ready Home Credit feature table is required;
  it does not claim to understand arbitrary customer exports.

## Alternatives rejected

### Run batch scoring synchronously in FastAPI

Rejected because long CPU-bound work would tie job lifetime to an HTTP connection,
compete with online latency and lose progress on process restarts.

### Redis/Celery for the first portfolio deployment

Rejected for now. PostgreSQL already provides durability and row-level locking,
and the expected queue volume does not justify another stateful dependency. Redis
becomes appropriate if measured queue contention, scheduling or retry policies
outgrow the relational queue.

### A separate network inference microservice

Rejected until online and batch consumers require independent release ownership or
language stacks. It would add network failure modes and duplicate bundle lifecycle
coordination without improving current correctness.

### Store uploads in PostgreSQL

Rejected because large binary payloads complicate backup, vacuum and query
performance. PostgreSQL stores only metadata and workflow state.

## Consequences

The platform is a small multiservice system with clear operational boundaries and
one-command local startup. It demonstrates BFF secret handling, async work,
idempotent audit logging, migrations and failure states without pretending to need
enterprise infrastructure. The main limitation is that local artifact storage is
single-host; horizontal deployment requires an object-storage adapter before
running API and workers on different hosts.
