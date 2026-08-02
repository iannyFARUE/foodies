# Foodies API — Design Spec

Date: 2026-08-01
Status: Approved by user

## Purpose

A learning project to practice FastAPI + MongoDB (PyMongo async) fundamentals by
mirroring the architecture of the `sample-app-python-mflix` reference project,
applied to a new domain the learner designs themselves: recipes and reviews.
Backend-focused — no frontend in v1. Swagger UI (`/docs`) is the primary test
surface.

## Reference project

`sample-app-python-mflix` (sibling repo, `c:\Code\python\sample-app-python-mflix`)
— FastAPI + PyMongo async driver, MongoDB Atlas (Search + Vector Search), Next.js
frontend (not mirrored in this project).

## Data Model

### `recipes` collection (mirrors `movies`)

| Field | Type | Notes |
|---|---|---|
| `_id` | ObjectId | |
| `title` | str | required |
| `description` | str | short summary — Atlas Search + Vector Search target |
| `instructions` | str | full steps — Atlas Search target |
| `cuisine` | str | e.g. "Italian" — categorical, filters/aggregation |
| `difficulty` | str | "easy" / "medium" / "hard" |
| `prepTimeMinutes` | int | numeric filter |
| `cookTimeMinutes` | int | numeric filter |
| `servings` | int | |
| `ingredients` | list[str] | unwind target (mirrors `directors`) |
| `tags` | list[str] | e.g. "vegan", "gluten-free" |
| `createdAt` | datetime | |
| `description_embedding_voyage_3_large` | list[float] | populated for Vector Search, same model/dimension as mflix (voyage-3-large, 2048 dims) |

### `reviews` collection (mirrors `comments`)

| Field | Type | Notes |
|---|---|---|
| `_id` | ObjectId | |
| `recipe_id` | ObjectId | ref to `recipes._id`, standard index |
| `reviewerName` | str | |
| `rating` | int | 1–5 |
| `comment` | str | |
| `date` | datetime | |

## API Surface

All endpoints under `/api/recipes`, wrapped in the same `SuccessResponse[T]` /
`create_error_response` envelope pattern as mflix.

- `GET /search` — Atlas Search (compound query) over `description`, `instructions`, `tags`
- `GET /vector-search` — Vector Search over `description_embedding_voyage_3_large` (Voyage AI)
- `GET /cuisines` — `distinct()` on `cuisine`
- `GET /{id}` — fetch by ObjectId
- `GET /` — filter (cuisine, difficulty, max prep time, min rating) + sort + paginate
- `POST /` — create one
- `POST /batch` — create many
- `PATCH /{id}` — update one
- `PATCH /` — batch update by filter
- `DELETE /{id}` — delete one
- `DELETE /` — batch delete by filter
- `DELETE /{id}/find-and-delete` — atomic find-and-delete
- `GET /aggregations/byCuisine` — `$lookup` reviews + `$group` avg rating & count per cuisine (mirrors `reportingByYear`)
- `GET /aggregations/topIngredients` — `$unwind` ingredients + `$group` most-used (mirrors `reportingByDirectors`)
- `GET /aggregations/recentReviews` — `$lookup` recipes↔reviews, most recent N reviews per recipe (mirrors `reportingByComments`)
- `POST /{id}/reviews` — **new pattern vs. mflix**: nested-resource write endpoint, since reviews need a way to be created (mflix's `comments` is aggregation-read-only)

## Backend Architecture

Mirrors `server/src/` layout in the reference repo:

```
server/
├── main.py                      # FastAPI app, lifespan (index creation), CORS, exception handlers
├── src/
│   ├── database/mongo_client.py # AsyncMongoClient singleton, get_collection()
│   ├── models/models.py         # Pydantic: Recipe, Review, Create/Update requests, SuccessResponse[T], Pagination
│   ├── routers/recipes.py       # all endpoints above
│   ├── middleware/request_logging.py
│   └── utils/
│       ├── successResponse.py / errorResponse.py
│       ├── exceptions.py        # Voyage AI auth/API error equivalents
│       ├── logger.py
│       └── response_docs.py
├── scripts/seed_data.py         # NEW vs. mflix: generates ~75-100 synthetic recipes + reviews (no MongoDB-provided sample dataset for this domain)
├── tests/
│   ├── conftest.py
│   ├── test_recipe_routes.py
│   ├── test_recipe_schemas.py
│   └── integration/
├── .env.example                 # MONGODB_URI, VOYAGE_API_KEY, PORT, CORS_ORIGINS
├── requirements.in / requirements.txt
└── pytest.ini
```

Startup (`lifespan`) creates three indexes on boot, same as mflix:
1. Atlas Search index (`recipeSearchIndex`) over `description`, `instructions`, `tags`
2. Vector Search index (`vector_index`) over `description_embedding_voyage_3_large`
3. Standard index on `reviews.recipe_id`

## Testing

Pytest, same split as mflix:
- `test_recipe_schemas.py` — Pydantic validation (required fields, aliasing, defaults)
- `test_recipe_routes.py` — endpoint behavior against a test DB/fixtures
- `integration/` — tests that hit real Atlas Search/Vector Search, skipped without Atlas creds

## Out of scope (v1)

No frontend, no auth/user accounts, no image uploads. Candidate stretch goals once
fundamentals are solid.

## Project location

`c:\Code\python\foodies` — sibling folder to `sample-app-python-mflix`, own git
repo (`origin` already configured).
