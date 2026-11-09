# ProgImage

[![CI](https://github.com/arifchoudhury/drive-progimage/actions/workflows/ci.yml/badge.svg)](https://github.com/arifchoudhury/drive-progimage/actions/workflows/ci.yml)

An API-only image storage service: upload an image, get an id back, fetch the image with that id.
Python 3.14, FastAPI, Postgres, uv.

## Quick start

```bash
make setup
make hooks    # once: pre-commit hook (ruff + file hygiene)
make db-up    # Postgres via docker compose (host port 5433)
make migrate
make api      # http://localhost:8001/docs
make test
make lint
```

Or run the whole stack in Docker:

```bash
cp .env.example .env   # set the auth credentials
make up                # build, start Postgres, migrate, wait until ready (API on :8080)
make logs
make down
```

### Try it with Bruno

The [Bruno](https://www.usebruno.com) collection in `bruno/` is the easiest way to use the API:

1. Open the `bruno/` folder as a collection.
2. Pick the `local` environment (or `docker`) and set the `password` secret to match your `.env`.
3. Run *Upload image* (sends `sample_data/red-square.png`), then *Get image* or *List images*.
4. To see a rejection, point the upload at `sample_data/not-an-image.txt` (422).

The interactive docs at `/docs` also work.

## API

```
POST /images        multipart/form-data, field "file"  → 201 {"id": "..."}
GET  /images/{id}   → the image bytes, with the right Content-Type
GET  /images        → 200 {"items": [{id, original_filename, content_type, size_bytes, created_at}, ...]}, newest first
GET  /healthz       → liveness, no auth
GET  /readyz        → readiness, no auth
```

| status | when |
|---|---|
| `200` | image bytes, the image list, or a passing probe |
| `201` | upload stored; body is `{"id": "<uuid7>"}` |
| `401` | missing or wrong credentials (all `/images` endpoints) |
| `404` | no image with that id, or its bytes are gone |
| `413` | body or image over `PROGIMAGE_MAX_UPLOAD_BYTES` (default 10 MiB) |
| `415` | a real image, but not JPEG, PNG, GIF or WebP |
| `422` | no file, not an image, corrupt, or over `PROGIMAGE_MAX_IMAGE_PIXELS` (default 40 MP) |
| `503` | `/readyz` only: the database or storage check failed |

Guarantees:

- An id is returned only after both the bytes and the metadata row are written.
- A rejected upload stores nothing.
- Images never change once stored (no update or delete endpoint).
- A row whose bytes are missing is a 404, not a 500.
- The client's filename and Content-Type never affect the storage key or the type served back.

Not yet: no `429` (no rate limiting), and errors are FastAPI's plain `{"detail": "..."}`, not a stable contract.
`GET /images` is unpaginated; the `items` wrapper lets a cursor be added later without a breaking change.

### Auth

All `/images` endpoints use HTTP Basic auth. Set `PROGIMAGE_AUTH_USERNAME` and `PROGIMAGE_AUTH_PASSWORD`
(see `.env.example`; the app won't start without them).

**This is a temporary solution:** one shared credential, so no per-caller identity. A real rollout would use OIDC/OAuth2
for users and OAuth2 client credentials, API keys or mTLS for services. Basic auth should only run over HTTPS.

### Health checks

- `/healthz` does no I/O. The Dockerfile `HEALTHCHECK` uses it, so a slow database never restarts the container.
- `/readyz` runs `SELECT 1` and a storage check (`ImageStorage.check()`), and returns 503 naming the failing
  dependency. Compose and orchestrators use it as the readiness probe. The Postgres connect timeout is 5 seconds.

Both are unauthenticated and reveal nothing beyond "ok" or "error".

## Decisions & trade-offs

Each entry is the choice, why, and what it costs.

- **Sync endpoints, not async.** Pillow, boto3 and sync SQLAlchemy all block, so `async def` would need an executor
  around every call. FastAPI runs `def` endpoints in a threadpool. *Cost:* concurrency is bounded by workers ×
  threadpool × DB pool.
- **Metadata in Postgres, bytes behind an `ImageStorage` port.** Cheap queries, and switching storage needs no schema
  change. *Cost:* two systems and no shared transaction (see the orphaned-blob gap below).
- **uuid7 ids and generated storage keys (`<id>.<ext>`).** Time-ordered ids suit indexes and a future keyset cursor. The
  client's filename is never used, so keys can't collide or traverse paths. *Cost:* an id reveals roughly when the
  image was created.
- **Original bytes stored untouched, no re-encoding.** Byte-identical round trip, no quality loss, no CPU in the
  request path. *Cost:* embedded metadata (e.g. EXIF GPS) is stored and served as-is.
- **Format is sniffed, not trusted.** See [Upload validation](#upload-validation).
- **Local disk by default, S3 as a skeleton.** Runs with no cloud account. The S3 adapter passes the contract tests
  against a fake client but has never run against real S3.
- **GET buffers the whole image.** `ImageStorage.load()` returns `bytes`: simple, and bounded by the upload cap.
  *Cost:* memory per request grows with image size.
- **Known gap: orphaned blob if the DB insert fails.** The blob is saved before the row is inserted. A stronger design
  inserts a `pending` row, writes the blob, marks it `ready`, and sweeps stale `pending` rows. Not built.
- **Out of scope on purpose:** delete and update, transformations, deduplication, per-user ownership, rate limiting.

### Upload validation

`ImageValidator` (`app/images/domain/validation.py`) is the upload policy. It checks, cheapest first and header-only
until the last step: non-empty, size, format allowlist, pixel count, then `Image.verify()`. Pillow detects the format
from the bytes; the client's Content-Type and filename are ignored.

The size limit is enforced twice, on purpose:

- **At the edge**, `MaxBodySizeMiddleware` returns 413 before the multipart body is parsed, from `Content-Length` or
  the streamed byte count. It runs before auth, so anonymous clients can't make the server buffer large bodies. A
  production proxy would usually enforce the same limit first.
- **In the domain**, `ImageValidator` checks again, so the rule holds for non-HTTP callers.

*Trade-off:* `verify()` is thorough for PNG and GIF but weak for JPEG, so a truncated JPEG can be stored. Catching it
means fully decoding every upload (up to ~4 bytes × max pixels of memory per request), which we chose not to pay for.
Pillow's global `MAX_IMAGE_PIXELS` is left alone; its `DecompressionBombError` maps to 422.

### Storage backends

`ImageService` depends only on the `ImageStorage` protocol. `PROGIMAGE_STORAGE_BACKEND` picks the adapter in
`get_storage` (`app/images/api/dependencies.py`).

- `local` (default): files under `PROGIMAGE_STORAGE_DIR` (default `./local_storage`).
- `s3`: skeleton. Install with `uv sync --extra s3` and set `PROGIMAGE_S3_BUCKET` plus the `PROGIMAGE_AWS_*` /
  `PROGIMAGE_S3_*` values (see `.env.example`).

A new backend means implementing the protocol and adding one `case` to `get_storage`.

## Data model

Postgres holds the metadata; the bytes live in `ImageStorage`. A GET is `id → images row → storage_key → bytes`.

| column | notes |
|---|---|
| `id` | uuid7, generated by the app |
| `original_filename` | sanitised client filename, informational only |
| `storage_key` | `<id>.<ext>`, generated |
| `content_type`, `size_bytes`, `created_at` | recorded at upload, so GET never re-decodes the image |

Columns we'd add later (sha256, dimensions, deleted_at, owner_id) are listed in
`app/images/infrastructure/database/models.py`.

Schema changes go through Alembic:

| command | what it does |
|---|---|
| `make migration m="describe change"` | autogenerate a revision (review it) |
| `make migrate` / `make migrate-down` | upgrade to head / roll back one |
| `make migrate-current` / `make migrate-history` | where the DB is / list revisions |
| `make migrate-check` | fail if models and migrations drifted |
| `make migrate-heads` | fail unless there is exactly one head |
| `make migrate-roundtrip` | upgrade, downgrade to base, upgrade (destructive) |
| `make db-reset` | wipe the local Postgres volume and re-migrate (destructive) |

For a new table, add the model and import it in `alembic/env.py`, then run `make migration`.

## Structure

Feature-first, layered inside each feature. Dependencies point inwards: `domain/` and `service.py` never import
`infrastructure/` or `api/`. Only `api/dependencies.py` (the composition root) knows the concrete adapters.

```
app/
  main.py                    app factory (`uvicorn --factory app.main:create_app`)
  health/router.py           /healthz + /readyz
  core/                      config, db engine/session, Basic auth (temporary)
  images/
    service.py               ImageService: validate, assign id + key, store bytes and metadata
    domain/                  entities, values, exceptions, validation.py, ports.py (storage + repository protocols)
    infrastructure/
      storage/               local.py, s3.py
      database/              ImageRow + SqlAlchemyImageRepository
    api/                     router, body_limit.py, schemas, dependencies.py (wiring via FastAPI Depends)
alembic/                     migrations (env.py reads PROGIMAGE_DATABASE_URL)
Dockerfile, docker-compose.yml
tests/
  unit/                      ImageService against in-memory fakes (no I/O)
  integration/               API via TestClient + real local storage + real Postgres
  e2e/                       real uvicorn subprocess + real HTTP
```

`make test` runs everything; `make test-unit`, `make test-integration` and `make test-e2e` run one tier. Contract
tests run every storage and repository adapter through the same behaviour. Tests use a separate `progimage_test`
database, created and migrated automatically (`make db-up` first).

### Docker stack

`make up` runs three services: `db` (Postgres 18, host port 5433), `migrate` (a one-shot `alembic upgrade head`; the
API starts only after it exits 0) and `api` (uvicorn as a non-root user, host port `API_PORT`, default 8080, blobs on
the `images` volume, `WEB_CONCURRENCY` workers, default 2). The image is multi-stage: uv installs the locked
dependencies, including the `s3` extra, and a slim runtime stage copies the venv and code. The migrate job needs the
auth variables too, because `alembic/env.py` loads the full `Settings`.

### CI

`.github/workflows/ci.yml` runs on every pull request and push to `main`, as four parallel jobs:

| Job | Checks |
| --- | --- |
| `lint` | pre-commit hooks, `uv.lock` up to date, ruff, strict mypy |
| `migrations` | one head, fresh upgrade, `alembic check`, downgrade to base and back |
| `test` | all three tiers against a Postgres 18 service |
| `docker` | `make up`, then a smoke test: probes, upload and fetch |

Locally: `make lint migrate-heads migrate-check test`. `make migrate-roundtrip` drops every table, so point
`PROGIMAGE_DATABASE_URL` at a throwaway database first.

## What I'd do next

In rough priority order. None of this is built.

1. **Response headers and conditional GET:** `nosniff`, a restrictive CSP and `Cache-Control: immutable` on served
   bytes, plus a `sha256` column as an `ETag` so repeat requests get a 304.
2. **Orphan cleanup and atomic local writes:** delete the blob when the insert fails; write to a temp file then
   rename, so a crash can't leave a partial image.
3. **Error contract:** RFC 9457 `application/problem+json` with stable types, declared per route in OpenAPI.
4. **Streaming GET**, or a presigned-URL redirect for S3.
5. **Rate limiting** (429 with `Retry-After`) behind a port: in memory locally, Redis in production.
6. **Observability:** structured logs, request ids, metrics.
7. **S3 adapter against MinIO** in the contract tests and CI.

Stretch: pagination, deduplication, soft delete, thumbnails via a worker queue, per-caller identity, a load test, a
deployment sketch (ECS or Cloud Run, S3, RDS, CDN).

## How I worked

I chose the scope, architecture and trade-offs: feature-first hexagonal layout, metadata in Postgres with blobs in a
pluggable store, uuid7 ids and generated keys, the validation policy, and three test tiers with per-adapter contract
suites.

I used Claude Code as a pair programmer for implementation, test scaffolding and review against the brief, which is
why commits carry a `Co-Authored-By` trailer. I reviewed every change and can walk through any part of it.

I started committing late, so the first commits were split afterwards in dependency order (each lint-clean with its
tests passing). Everything after that is committed as it was built.
