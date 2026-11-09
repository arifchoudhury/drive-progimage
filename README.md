# ProgImage

[![CI](https://github.com/arifchoudhury/drive-progimage/actions/workflows/ci.yml/badge.svg)](https://github.com/arifchoudhury/drive-progimage/actions/workflows/ci.yml)

An API-only image storage service: upload an image, get an id back, fetch the image with that id.
Python 3.14, FastAPI, Postgres, Redis, uv.

```
POST /images        multipart field "file"  → 201 {"id": "..."}
GET  /images/{id}   → the image bytes, with the right Content-Type
GET  /images        → {"items": [...metadata...]}, newest first
GET  /healthz       liveness     GET /readyz   readiness (both unauthenticated)
```

## Run it

```bash
cp .env.example .env   # set the auth credentials
make up                # Docker: Postgres, Redis, migrations, API on :8080
```

Or locally: `make setup db-up migrate api` (API on :8001, docs at `/docs`). Then `make test` and `make lint`.

**Try it with [Bruno](https://www.usebruno.com):** open the `bruno/` folder as a collection, pick the `local` (or
`docker`) environment, set the `password` secret to match your `.env`, then run *Upload image* and *Get image*.
Point the upload at `sample_data/not-an-image.txt` to see a rejection.

## How it maps to the brief

**Packaging and environments.** A multi-stage, non-root Docker image and a compose stack (Postgres, a one-shot
migration job, the API). Config comes from environment variables, and the app refuses to start without credentials.
`/healthz` and `/readyz` serve as container and orchestrator probes. CI builds the image and smoke-tests it.

**Concurrency and load.** Endpoints are sync `def`, run by FastAPI's threadpool, because Pillow, boto3 and SQLAlchemy
all block. Scale with `WEB_CONCURRENCY` workers and the DB pool. A request body is capped before it is parsed, which
bounds memory per request. GET currently buffers the whole image (fine under the 10 MiB cap; streaming is next).

**Storage abstraction.** The service depends on two ports, `ImageStorage` and `ImageRepository`, each with two
adapters (local disk and S3; in-memory and Postgres). Metadata lives in Postgres and bytes behind the storage port, so
switching storage needs no schema change. Dependencies point inwards and only `api/dependencies.py` knows the
concrete adapters. The S3 adapter has only been run against a fake client.

**Errors and guarantees.**

| status | when |
|---|---|
| `201` | stored; the id is returned only after both bytes and metadata are written |
| `401` | missing or wrong credentials |
| `404` | no such image, or its bytes are gone |
| `429` | rate limit spent for this window; `Retry-After` says when to retry |
| `413` / `415` / `422` | too large / real image but not JPEG, PNG, GIF or WebP / not a valid image or too many pixels |
| `503` | `/readyz` only: database or storage unavailable |

A rejected upload stores nothing, and images never change once stored. Errors are FastAPI's `{"detail": ...}` for now.

**Security, validation, resource protection.** Pillow decides the format from the bytes, against an allowlist; the
client's Content-Type and filename are ignored. Checks run cheapest first: size, format, pixel count (decompression
bombs), then `verify()`. The size limit is enforced at the edge (before auth and parsing) and again in the domain.
Storage keys are generated (`<uuid7>.<ext>`) and local paths can't escape the storage root. Basic auth uses a
constant-time compare.

**Rate limiting** is at two layers. Coarse per-IP flood protection belongs at the gateway or ingress, which is
deployment config and not built here. The app enforces per-client quotas over a 60-second window: 30 writes and 600
reads per minute by default, set by `PROGIMAGE_RATE_LIMIT_*`. A limit applies before auth, so failed logins count
too. It sits behind a `RateLimiter` port with an in-memory adapter (one process) and a Redis adapter (shared by every
worker, which the two-worker compose stack needs). If Redis is down, requests are allowed and the error is logged.
Health probes are never limited. Responses carry `RateLimit-*` headers. Behind a load balancer, set uvicorn's
`FORWARDED_ALLOW_IPS` to the proxy's addresses, or every request appears to come from the proxy and all clients
share one quota.

*Trade-off:* `verify()` is weak for JPEG, so a truncated JPEG can be stored; fully decoding
every upload costs too much memory.

**Testing.** Three tiers: unit tests against in-memory fakes, integration tests on real Postgres and local storage,
and end-to-end tests against a live uvicorn process. Contract suites run every storage and repository adapter through
the same behaviour. Failure paths are covered (401, 404, 413, 415, 422, a missing blob, nothing stored after a
rejection), not just the happy path.

## Trade-offs and known gaps

- **Basic auth is a stopgap:** one shared credential, no per-caller identity. A real rollout would use OAuth2/OIDC or
  API keys.
- **`GET /images` is unpaginated;** the `items` wrapper lets a cursor be added without a breaking change.
- **Rate limits are keyed by client IP,** since the shared credential has no caller identity. Clients behind one
  NAT share a quota. With real auth they would be keyed per caller. Fixed windows allow a burst of up to 2x at a
  window edge.
- **uuid7 ids** are time-ordered and index-friendly, but reveal roughly when an image was created.

## What I'd do next

1. `nosniff`, CSP and `Cache-Control` on served bytes, plus a `sha256` ETag for 304s.
2. Orphan cleanup and atomic local writes (temp file, then rename).
3. RFC 9457 error responses with stable types, documented in OpenAPI.
4. Streaming GET, observability (logs, request ids, metrics).
5. Run the S3 adapter against MinIO in CI.

## Project layout

```
app/
  main.py, health/       app factory and probes
  core/                  config, db, auth, rate_limit/ (port, memory + Redis adapters)
  images/
    service.py           ImageService
    domain/              entities, validation, ports (storage + repository)
    infrastructure/      storage/ (local, s3), database/ (SQLAlchemy)
    api/                 router, body-limit middleware, wiring
alembic/                 migrations (`make migration m="..."`, `make migrate-check`)
tests/                   unit/, integration/, e2e/
```

## How I worked

I chose the scope, architecture and trade-offs. I used Claude Code as a pair programmer for implementation, test
scaffolding and review against the brief, so commits carry a `Co-Authored-By` trailer. I reviewed every change and can walk through any part of it.
