# ProgImage

[![CI](https://github.com/arifchoudhury/drive-progimage/actions/workflows/ci.yml/badge.svg)](https://github.com/arifchoudhury/drive-progimage/actions/workflows/ci.yml)

An API-only image storage service: upload an image, get back an id, then retrieve the image with that id.

```
POST /images        multipart/form-data, field "file"  → 201 {"id": "..."}
GET  /images/{id}   → the image bytes, with the correct Content-Type
GET  /images        → 200 {"items": [{id, original_filename, content_type, size_bytes, created_at}, ...]}, newest first
GET  /healthz       → 200 liveness (no auth)
GET  /readyz        → 200, or 503 naming the failing dependency (no auth)
```

### API guarantees

| status | when |
|---|---|
| `200` | image bytes, the image list, or a passing probe |
| `201` | upload stored; body is `{"id": "<uuid7>"}` |
| `401` | missing or wrong credentials (every `/images` endpoint) |
| `404` | no image with that id (or its bytes are gone) |
| `413` | request body or image over `PROGIMAGE_MAX_UPLOAD_BYTES` (default 10 MiB) |
| `415` | a real image, but not JPEG, PNG, GIF or WebP |
| `422` | no file, not an image, corrupt/truncated, or over `PROGIMAGE_MAX_IMAGE_PIXELS` (default 40 MP) |
| `503` | `GET /readyz` only: the database or storage check failed |

There is no `429` yet: nothing rate-limits clients (see [What I'd do next](#what-id-do-next)).

- An id is returned only after both the blob and its metadata row are written.
- A rejected upload stores nothing.
- An image never changes once stored; there is no update or delete endpoint.
- A row whose blob is missing is a 404, not a 500.
- The client's filename and Content-Type never influence the storage key or the Content-Type served back.

Errors are FastAPI's `{"detail": "..."}`. That shape is not a stable contract yet (see "What I'd do next").

`GET /images` returns every image in one response. Pagination is not implemented yet (see the `TODO(pagination)` notes in the code); the `items` wrapper leaves room to add it without a breaking change.

Python 3.14, FastAPI and uv.

## Running

```bash
make setup
make hooks   # once: git pre-commit hook (ruff + file hygiene)
make db-up    # Postgres via docker compose (host port 5433)
make migrate  # alembic upgrade head
make api      # http://localhost:8001/docs
make test
make lint
```

```bash
curl -u admin:change-me -F file=@sample_data/red-square.png localhost:8001/images
curl -u admin:change-me localhost:8001/images/<id> -o out.jpg
```

### With Docker

```bash
cp .env.example .env   # set the auth credentials
make up                # builds the image, starts Postgres, runs migrations, waits until the API is ready
curl localhost:8080/readyz
curl -u admin:change-me -F file=@sample_data/red-square.png localhost:8080/images
make logs              # follow the API logs
make down
```

`make up` is `docker compose up -d --build --wait api`. The stack is three services:

- `db`: Postgres 18, published on host port 5433 for local (non-Docker) runs and the test suite.
- `migrate`: a one-shot `alembic upgrade head`, run from the same image. The API starts only after it exits 0.
- `api`: uvicorn as a non-root user on container port 8000, published on `API_PORT` (default 8080). Blobs go to the
  `images` volume. `WEB_CONCURRENCY` (default 2) sets the number of workers.

The image is multi-stage: uv installs the locked runtime dependencies (including the `s3` extra, so one image runs
either backend) into a venv, and a slim runtime stage copies just that venv and the code. Config comes from `.env`
plus compose overrides for the in-network database URL and the storage path.

Note: the migrate job needs the auth variables too, because `alembic/env.py` loads the full `Settings`.

### Health checks

- `GET /healthz` (liveness) does no I/O: if it answers, the process is alive. The Dockerfile `HEALTHCHECK` uses it,
  so a slow database never gets the container restarted.
- `GET /readyz` (readiness) runs `SELECT 1` and `ImageStorage.check()` (a probe-file write for local storage,
  `HeadBucket` for S3). It returns 503 with `{"checks": {"database": "error", ...}}` when either fails, with the
  details only in the logs. Compose's `api` healthcheck and an orchestrator's readiness probe use this one. A
  5-second Postgres connect timeout keeps it from hanging when the database is unreachable.

Both are unauthenticated so probes don't need credentials, and they reveal nothing beyond "ok" or "error".

Sample files live in `sample_data/` (regenerate with `make sample-data`; `not-an-image.txt` should be rejected with 422).

A [Bruno](https://www.usebruno.com) collection lives in `bruno/` (open the folder as a collection, pick the `local` environment (or `docker` for `make up`),
set the image path in *Upload image*, then run *Upload image* → *Get image*).

## Auth

All `/images` endpoints use HTTP Basic auth. Set `PROGIMAGE_AUTH_USERNAME` and `PROGIMAGE_AUTH_PASSWORD` (see `.env.example`; the app won't start without them).

```bash
curl -u admin:change-me -F file=@photo.jpg localhost:8001/images
```

**This is a temporary solution** (one shared credential pair). A real rollout would depend on who the caller is: end users via OIDC/OAuth2 login with JWT sessions, machine-to-machine via OAuth2 client credentials, API keys or mTLS, with per-caller identity and scopes. Basic auth should only be used over HTTPS. In Bruno, set the `password` secret in the `local` environment.

## Upload validation

`ImageValidator` (`app/images/domain/validation.py`) is the upload policy, injected into `ImageService` like
storage and the repository. It checks, cheapest first and header-only until the last step: non-empty, size,
format allowlist, pixel count, then `Image.verify()`. Pillow detects the format from the bytes; the client's
Content-Type and filename are ignored.

The size limit is enforced twice, on purpose:

- **At the edge**, `MaxBodySizeMiddleware` (`app/images/api/body_limit.py`) refuses an oversized request body with 413
  before FastAPI parses the multipart form. It checks `Content-Length` up front and counts bytes as they arrive,
  so chunked uploads are caught too. This is what protects memory and disk; by the time a handler sees the file,
  the whole body has already been read. It runs before auth, so anonymous clients can't make us buffer either.
  In production a proxy or ingress would usually enforce the same limit first.
- **In the domain**, `ImageValidator` checks `max_bytes` again, so the rule holds for any non-HTTP caller.

Trade-off: `verify()` checks PNG and GIF structure and checksums, but does little for JPEG, so a truncated JPEG
can be stored. Catching that means fully decoding every upload (up to ~4 bytes × max pixels of memory per
request), which we chose not to pay for. The pixel cap is our own check on the header; Pillow's process-global
`MAX_IMAGE_PIXELS` is left alone (and its `DecompressionBombError` is mapped to 422).

Images are stored on local disk under `PROGIMAGE_STORAGE_DIR` (default `./local_storage`).

## Decisions & trade-offs

Each entry is the choice, why, and what it costs.

- **Sync endpoints, not async.** Pillow, boto3 and the sync SQLAlchemy driver all block, so `async def` would need
  an executor around every call for no gain. FastAPI runs `def` endpoints in its threadpool. Cost: concurrency is
  bounded by workers × threadpool size × DB pool size, not by an event loop.
- **Metadata in Postgres, bytes behind an `ImageStorage` port.** Listing and querying are cheap, and switching
  between local disk and S3 needs no schema change (see [Data model](#data-model), [Storage backends](#storage-backends)).
  Cost: two systems with no shared transaction (see the orphaned-blob gap below).
- **uuid7 ids, generated by the app, and generated storage keys (`<id>.<ext>`).** Ids are time-ordered, so they
  suit indexes and a future keyset cursor, and they are not sequential integers. Keys can't collide or traverse
  paths because the client's filename is never used. Cost: an id reveals roughly when the image was created.
- **Original bytes are stored untouched; nothing is re-encoded.** The round trip is byte-identical, there is no quality
  loss, and no CPU work in the request path. Cost: whatever metadata the file carries (EXIF GPS, for example) is
  stored and served as-is, and a truncated JPEG can pass validation (see [Upload validation](#upload-validation)).
- **Format is sniffed, not trusted.** Pillow decides the format from the bytes, against a JPEG/PNG/GIF/WebP
  allowlist, with cheap header-only checks first. The size limit is enforced at the edge and again in the domain.
  Details and costs are in [Upload validation](#upload-validation).
- **Local disk by default, S3 as a skeleton.** The service runs with no cloud account. The S3 adapter passes the
  contract tests against a fake client but has never been run against a real S3-compatible service.
- **Basic auth as a stopgap.** One shared credential and no per-caller identity. See [Auth](#auth).
- **`GET /images` is unpaginated.** Fine at this scale. The `items` wrapper means a cursor can be added without a
  breaking change (`TODO(pagination)` in the code).
- **GET buffers the whole image in memory.** `ImageStorage.load()` returns `bytes`. That is simple and bounded by the
  upload cap, but memory per request grows with image size. Streaming is on the list below.
- **Known gap: an orphaned blob if the DB insert fails.** `ImageService.upload` saves the blob and then inserts the
  row, so a failed insert leaves a blob nothing points to. A stronger design would insert a `pending` row, write the
  blob, mark the row `ready`, and have a reconciler sweep old `pending` rows. Not built.
- **Out of scope on purpose:** delete and update endpoints, transformations, deduplication, per-user ownership,
  rate limiting.

### Storage backends

`ImageService` depends only on the `ImageStorage` protocol; the concrete backend is chosen by
`PROGIMAGE_STORAGE_BACKEND` in `get_storage` in `app/images/api/dependencies.py` and injected through FastAPI `Depends`.

- `local` (default): `LocalImageStorage`.
- `s3`: `S3ImageStorage` (skeleton, not exercised against real AWS). Install with `uv sync --extra s3` and set
  `PROGIMAGE_S3_BUCKET` plus the `PROGIMAGE_AWS_*` / `PROGIMAGE_S3_*` values (see `.env.example`).

Adding a backend means implementing the protocol and adding one `case` to `get_storage`.

## Data model

Postgres is the system of record for image metadata; the bytes stay in `ImageStorage`. A GET is
`id → images row → storage_key → bytes`.

| column | notes |
|---|---|
| `id` | uuid7, generated by the app |
| `original_filename` | sanitised client filename; informational only, never used to address the blob |
| `storage_key` | where the blob lives (`<id>.<ext>`), generated, so same-named uploads can't collide or traverse paths |
| `content_type`, `size_bytes`, `created_at` | recorded at upload; GET no longer re-decodes the image |

Schema changes go through Alembic (`alembic/`, config in `alembic.ini`):

| command | what it does |
|---|---|
| `make migration m="describe change"` | autogenerate a revision from model changes (review it!) |
| `make migrate` / `make migrate-down` | upgrade to head / roll back one revision |
| `make migrate-current` / `make migrate-history` | where the DB is / list revisions |
| `make migrate-check` | fail if models and migrations have drifted |
| `make migrate-heads` | fail unless the revision history has exactly one head |
| `make migrate-roundtrip` | upgrade, downgrade to base, upgrade again (destructive) |
| `make db-reset` | wipe the local Postgres volume and re-migrate (destructive) |

New tables: add the model, import it in `alembic/env.py`, then `make migration`.
Fields we'd add later (sha256, dimensions, deleted_at, owner_id, ...) are listed in `app/images/infrastructure/database/models.py`.
Tests use a separate `progimage_test` database on the same Postgres, created and migrated automatically (`make db-up` first).

## Structure

Feature-first, layered inside each feature. Dependencies point inwards: `domain/` and `service.py` never import
`infrastructure/` or `api/`; only `api/dependencies.py` (the composition root) knows the concrete adapters.

```
app/
  main.py                    app factory (`uvicorn --factory app.main:create_app`)
  health/router.py           /healthz + /readyz probes (its own module: readiness checks the images feature's storage)
  core/                      shared plumbing
    config.py                settings
    db.py                    engine / session factory, declarative base
    auth.py                  HTTP Basic auth (temporary)
  images/
    service.py               ImageService: validates the upload, assigns an id + key, stores bytes and metadata
    domain/
      entities.py            Image
      values.py              ImageContent, ImageInfo
      exceptions.py
      validation.py          ImageValidator: the upload policy (size, formats, pixels, integrity)
      ports.py               ImageStorage + ImageRepository protocols
    infrastructure/
      storage/               ImageStorage adapters: local.py, s3.py
      database/              ImageRow (the `images` table) + SqlAlchemyImageRepository
    api/
      router.py              HTTP endpoints
      body_limit.py          MaxBodySizeMiddleware: 413 before the body is parsed
      schemas.py             response models
      dependencies.py        wires ImageService -> ImageStorage + ImageRepository + ImageValidator via FastAPI Depends
alembic/                     Alembic env + versions/ (env.py takes the URL from PROGIMAGE_DATABASE_URL; imports every feature's ORM models)
Dockerfile                   multi-stage image: uv-built venv, slim non-root runtime
docker-compose.yml           Postgres, one-shot migrate job, api
tests/                       class-based tests; each folder's tests get its marker automatically
  unit/                      ImageService against in-memory fake storage + repository (no I/O)
  integration/               API via TestClient + real LocalImageStorage on a temp dir + real Postgres (swapped via dependency_overrides)
  e2e/                       real uvicorn subprocess + real HTTP (httpx2), no overrides
```

`make test` runs everything; `make test-unit`, `make test-integration`, `make test-e2e` run one tier (or `pytest -m <tier>`).

### CI

`.github/workflows/ci.yml` runs on every pull request and every push to `main`, as four parallel jobs:

| Job | Checks |
| --- | --- |
| `lint` | the pre-commit hooks on every file, `uv.lock` is up to date, ruff (lint + format), strict mypy |
| `migrations` | one Alembic head, a fresh database upgrades to head, models match migrations (`alembic check`), downgrade to base and back |
| `test` | all three tiers against a Postgres 18 service container |
| `docker` | `make up` builds the image and runs the migrate job, then a smoke test: health probes, upload and fetch an image |

The pre-commit hook (`make hooks`) runs the fast part of `lint` before each commit: ruff, `uv lock`, and whitespace,
YAML/TOML, merge-marker and private-key checks. Locally: `make lint migrate-heads migrate-check test`. `make migrate-roundtrip` drops every table, so point
`PROGIMAGE_DATABASE_URL` at a throwaway database before running it.

## What I'd do next

In rough priority order. None of this is built.

1. **Response headers and conditional GET.** `nosniff`, a restrictive CSP and `Cache-Control: immutable` on served
   bytes, plus a `sha256` column used as an `ETag` so repeat requests get a 304 without touching storage.
2. **Orphan cleanup and atomic local writes.** Delete the blob when the insert fails, and write local files to a temp
   file then rename, so a crash can't leave a partial image that GET serves.
3. **Error contract.** RFC 9457 `application/problem+json` with stable error types, declared per route in OpenAPI.
4. **Streaming GET**, or a redirect to a presigned URL for S3, so memory per request stops depending on image size.
5. **Rate limiting** (429 with `Retry-After`), behind a port: in memory locally, Redis in production, with the body
   cap also enforced at the gateway.
6. **Observability:** structured logs, request ids and metrics.
7. **Run the S3 adapter against MinIO** in the contract tests and in CI.

Stretch: pagination, `sha256` deduplication, delete with soft delete, thumbnails through a worker queue, per-caller
identity with an `owner_id`, a load test to size workers and pools, and a deployment sketch (ECS or Cloud Run, S3,
RDS, a CDN in front of GET).

## How I worked

I chose the scope, the architecture and the trade-offs: feature-first hexagonal layout with storage and repository
ports, metadata in Postgres with blobs in a pluggable store, uuid7 ids and generated storage keys, the upload validation
policy, and three test tiers with contract suites per adapter.

I used Claude (Claude Code) as a pair programmer for implementation, test scaffolding and reviewing the work against
the brief, which is why commits carry a `Co-Authored-By` trailer. I reviewed every change and can walk through any part
of the code and the reasoning behind it.

I started committing late, so the first commits were split afterwards in dependency order (each one lint-clean with its
tests passing). Everything after that is committed as it was built.
