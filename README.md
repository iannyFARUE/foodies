# Foodies API

[![CI](https://github.com/iannyFARUE/foodies/actions/workflows/ci.yml/badge.svg)](https://github.com/iannyFARUE/foodies/actions/workflows/ci.yml)

A FastAPI + MongoDB backend for browsing recipes and reviews, built as a learning
project mirroring the architecture of MongoDB's `sample-app-python-mflix`:
CRUD, filtering/pagination, batch operations, aggregations ($group, $unwind,
$lookup), Atlas Search, and Vector Search.

## Prerequisites

- Python 3.10–3.13 (this project was built and tested against 3.12)
- A MongoDB Atlas cluster (Atlas Search and Vector Search require Atlas, not
  a local/Community deployment)
- (Optional) A Voyage AI API key, for vector search — https://www.voyageai.com/

## Setup

```bash
cd server
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
```

Edit `.env` and set `MONGODB_URI` (and optionally `VOYAGE_API_KEY`). Also set
`API_KEY` — a shared secret required on every write/delete request to
`/api/recipes` (sent as the `X-API-Key` header); generate one with
`python -c "import secrets; print(secrets.token_urlsafe(32))"`.

## Seed sample data

```bash
python -m scripts.seed_data
```

Generates 30 synthetic recipes with random reviews, and populates each
recipe's `averageRating`/`reviewCount` and (if `VOYAGE_API_KEY` is set) its
description embedding for vector search. Safe to re-run — it clears existing
`recipes`/`reviews` first.

## Run the server

```bash
uvicorn main:app --reload --port 3011
```

- API: http://localhost:3011/api/recipes
- Swagger UI: http://localhost:3011/docs
- ReDoc: http://localhost:3011/redoc

On first boot, the server creates an Atlas Search index (`recipeSearchIndex`),
a Vector Search index (`vector_index`), and a standard index on
`reviews.recipe_id`. This requires the `recipes`/`reviews` collections to
already exist — the server creates them automatically if empty.

## Run tests

```bash
pytest -m unit -v          # fast, mocked, no database required
pytest -m integration -v   # requires the Atlas cluster from .env (spins up a real server on port 8011)
pytest -v                  # everything
```

CI ([.github/workflows/ci.yml](.github/workflows/ci.yml)) runs the unit suite on every push/PR to `main`. Integration
tests need a live Atlas cluster and aren't run in CI.

## Project structure

```
server/
├── main.py                  # FastAPI app, startup index creation, CORS, exception handlers
├── src/
│   ├── database/              # MongoDB client
│   ├── models/                  # Pydantic request/response schemas
│   ├── routers/                   # /api/recipes endpoints
│   ├── middleware/                  # Request logging
│   └── utils/                         # Response envelopes, errors, logging, OpenAPI docs
├── scripts/seed_data.py     # Generates synthetic recipes + reviews
└── tests/                   # Unit, schema, and integration tests
```

## Design notes

- **Denormalized ratings:** each recipe stores `averageRating`/`reviewCount`,
  recomputed whenever a review is added. This lets `GET /api/recipes/` filter
  by `minRating` directly, without a `$lookup` on every list request.
- **Pagination metadata:** `GET /api/recipes/` and `/search` still take
  `skip`/`limit`, but responses now include a `pagination` object
  (`page`/`limit`/`total`/`pages`) computed from a `count_documents`/`$facet`
  total, so clients can tell whether more pages exist.
- **Embeddings live on the recipe itself** (`description_embedding_voyage_3_large`),
  unlike the reference project's separate `embedded_movies` collection — there's
  no reason to split it out since every recipe gets exactly one embedding.
- **Atlas Search index quotas:** free/shared Atlas tiers cap the total number
  of Search + Vector Search indexes per cluster. If you're also running the
  `sample-app-python-mflix` reference project against the same cluster, you
  may need a second cluster or to free up an index slot.
- **API key on writes:** all `POST`/`PATCH`/`DELETE` endpoints under
  `/api/recipes` require an `X-API-Key` header matching the server's `API_KEY`
  env var; `GET` endpoints (browsing, search, aggregations) stay public. This
  is a single shared secret, not per-user accounts — enough to stop anonymous
  writes without building out a user system.
- **Vector search rate limiting:** `/vector-search` calls the paid Voyage AI
  embeddings API per request, so it's capped at 10 requests/minute per client
  IP via an in-memory limiter. Single-process only (state isn't shared across
  workers), which matches this app's one-process deployment.

See `docs/superpowers/specs/2026-08-01-foodies-api-design.md` and
`docs/superpowers/plans/2026-08-01-foodies-api.md` for the full design spec
and implementation plan this project was built from.
