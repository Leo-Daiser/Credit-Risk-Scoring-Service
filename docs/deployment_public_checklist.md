# Public deployment checklist

Complete every item before exposing the frontend:

- [ ] Set `APP_ENV=public`, `DEMO_MODE=false`, `OPERATOR_UI_ENABLED=false`, `PUBLIC_AUTH_STRICT=true`.
- [ ] Generate a strong random `API_KEY`; confirm placeholder values fail startup.
- [ ] Store database/API/partner secrets in a platform secret store, never `.env` in Git or an image layer.
- [ ] Disable partner callbacks or configure a separate strong `PARTNER_POSTBACK_SECRET`.
- [ ] Keep real partner mode disabled until legal, signature and redirect review is complete.
- [ ] Expose the frontend through TLS; keep backend and PostgreSQL on a private network or loopback.
- [ ] Configure reverse-proxy/WAF request-size and rate limits; do not rely on the in-memory limiter across replicas.
- [ ] Keep `/commercial`, `/operator`, operator BFF, `/docs`, `/openapi.json`, `/metrics` and runtime diagnostics inaccessible.
- [ ] Mount trusted full/public model bundles read-only from a controlled artifact source; do not bake or commit them.
- [ ] Confirm `/ready` and operator system status show the public model as available; otherwise communicate the explicit rules fallback.
- [ ] Confirm the image contains no raw/processed data, reports, uploads, predictions, `.env`, host `node_modules`, `dist` or `.next`.
- [ ] Run all three Compose config checks, backend/frontend tests and Docker builds.
- [ ] Run `python -m src.cli setup-demo`, `verify-demo` and the public smoke script.
- [ ] Review advertising labels, legal disclaimer, referral wording and public privacy notice.
- [ ] Configure retention, backups, monitoring and incident contacts for the target platform.
- [ ] Confirm synthetic demo offers are clearly marked and never presented as current bank terms.

The public example binds the backend to `127.0.0.1` for local verification. A real
reverse proxy should use the private container network and expose only the public
frontend flow.
