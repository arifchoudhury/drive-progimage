# ProgImage

[![CI](https://github.com/arifchoudhury/drive-progimage/actions/workflows/ci.yml/badge.svg)](https://github.com/arifchoudhury/drive-progimage/actions/workflows/ci.yml)

Image storage API. Upload an image, get an id, fetch it by id.
Python 3.14, FastAPI, Postgres, Redis, uv.

```
POST /images        upload (multipart field "file") → 201 {"id": "..."}
GET  /images/{id}   the image
GET  /images        all images' metadata, newest first
GET  /healthz       liveness
GET  /readyz        readiness
```

## Run it

1. `cp .env.example .env` and set a password.
2. Run **one** of:
   - `make local`: API on your machine with reload, Postgres and Redis in Docker.
   - `make docker`: everything in Docker.

   Both start with an empty database. API on http://localhost:8000, docs at `/docs`. `make down` to stop.
3. Open `bruno/` in [Bruno](https://www.usebruno.com), pick the **dev** environment, set the password, then run:
   1. **Upload image** (`sample_data/red-square.png`; try `not-an-image.txt` for a 422)
   2. **List images**
   3. **Get image**

Tests: `make services`, then `make test`. Lint: `make lint`.

## How it maps to the brief

**Packaging**
- Multi-stage, non-root Docker image. Compose runs Postgres, Redis, migrations and the API.
- Config from env vars. Won't start without credentials.
- Health checks: `/healthz`, `/readyz`.
- CI builds and smoke-tests the image.

**Load**
- Sync endpoints on a threadpool (Pillow and SQLAlchemy block).
- Scale with `WEB_CONCURRENCY` and the DB pool.
- Oversized bodies rejected before parsing.

**Storage**
- Storage behind an interface: local disk or S3 (S3 only tested against a fake).
- Metadata in Postgres, bytes in storage. Swapping storage needs no schema change.

**Responses**
- `201` stored · `401` bad login · `404` not found · `413` too large
- `415` unsupported format · `422` not an image · `429` rate limited · `503` not ready
- Rejected uploads store nothing. Images never change.

**Security**
- Format detected from the bytes, not the filename or Content-Type. JPEG, PNG, GIF, WebP only.
- Pixel limit against decompression bombs.
- Generated storage names, no path traversal.
- Constant-time password check.
- Download headers stop browsers treating images as anything else.

**Rate limiting**
- 30 uploads / 600 reads per minute per client, configurable.
- Counted in Redis, shared across workers. Fails open if Redis is down.
- Per-IP flood protection belongs at the load balancer.

**Testing**
- Unit (in-memory fakes), integration (real Postgres, Redis, disk), end-to-end (live server).
- Every storage and database adapter runs the same contract tests.

## Trade-offs and next steps

- Basic auth with one shared login. A real setup would use OAuth or API keys.
- No paging on `GET /images` yet.
- Rate limits are per IP, so clients behind one NAT share a limit.
- Truncated JPEGs can get through; fully decoding every upload costs too much memory.
- Next: caching, depending on the consumer. Through a CDN, let the CDN cache images (they're `private` today).
  Called directly, add `ETag`s so clients get a 304.

## Layout

```
app/
  core/          config, db, auth, rate limiting
  health/        probes
  images/
    domain/      entities, validation, interfaces
    infrastructure/  storage (local, s3), database
    api/         routes
alembic/         migrations
tests/           unit/, integration/, e2e/
```

## How I worked

I chose the scope, design and trade-offs. Claude Code helped with implementation, tests and review, so commits carry
a `Co-Authored-By` trailer. I reviewed every change.
