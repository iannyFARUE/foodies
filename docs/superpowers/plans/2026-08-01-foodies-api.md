# Foodies API Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a FastAPI + MongoDB backend for a recipes/reviews domain ("Foodies") that mirrors the architecture of the reference project `sample-app-python-mflix`, to practice FastAPI + PyMongo async fundamentals (CRUD, filtering/pagination, batch ops, aggregations, Atlas Search, Vector Search).

**Architecture:** `main.py` boots a FastAPI app with CORS + request-logging middleware and a `recipes` router mounted at `/api/recipes`. All MongoDB access goes through a single `AsyncMongoClient` in `src/database/mongo_client.py`. Every response is wrapped in a `SuccessResponse[T]` / standardized error envelope. Two collections: `recipes` (main resource) and `reviews` (child resource, joined via `$lookup` for reporting and denormalized onto the parent for read-path filtering).

**Tech Stack:** FastAPI, PyMongo `AsyncMongoClient`, Pydantic v2, Voyage AI (`voyage-3-large`, 2048-dim embeddings), pytest + pytest-asyncio, httpx (integration tests).

## Global Constraints

- Python 3.10–3.13 (matches the reference project's floor/ceiling).
- MongoDB database name: `foodies`. Collections: `recipes`, `reviews`. No manual DB creation needed — MongoDB creates both on first insert.
- Default server port: `3011` (deliberately different from the reference project's `3001` so both can run at the same time on one machine).
- Response envelope is fixed and must not drift between endpoints: success responses are `SuccessResponse[T]` (`success`, `message`, `data`, `timestamp`, optional `pagination`); error responses are the dict returned by `create_error_response(message, code, details=None)` (`success: false`, `message`, `error: {message, code, details}`, `timestamp`).
- Voyage AI embedding model: `voyage-3-large`, `outputDimension=2048`. Reuses the same `VOYAGE_API_KEY` the user already has for the reference project.
- Every ObjectId returned to a client must be converted to `str` before it crosses the API boundary.
- Only define Pydantic models that a route actually uses — the reference project defines several unused filter/batch models; don't carry that dead code into this project.
- Every task that adds business logic (not pure scaffolding/config) follows TDD: write the failing test, confirm it fails, implement, confirm it passes, commit.

---

### Task 1: Project Scaffolding & Dependencies

**Files:**
- Create: `server/requirements.in`
- Create: `server/requirements.txt`
- Create: `server/.env.example`
- Create: `server/.gitignore`
- Create: `server/pytest.ini`
- Create: `server/tests/__init__.py`
- Create: `server/src/middleware/__init__.py`

**Interfaces:**
- Consumes: nothing (first task).
- Produces: an installable Python environment and a pytest config that later tasks' tests run under (`-m unit` / `-m integration` markers registered).

No TDD cycle here — there's no logic yet to test, only project setup. This task is verified by successfully installing dependencies and confirming pytest can start.

- [ ] **Step 1: Create the folder structure**

```bash
mkdir -p server/src/database server/src/models server/src/routers server/src/middleware server/src/utils server/tests/integration server/scripts
```

- [ ] **Step 2: Write `server/requirements.in`**

```
fastapi~=0.136.3
uvicorn~=0.38.0
pydantic~=2.12.5
python-dotenv>=1.2.2
pymongo~=4.17.0
dnspython~=2.8.0
voyageai~=0.3.7
httpx~=0.28.1
pytest~=9.0.3
pytest-asyncio~=1.3.0
```

- [ ] **Step 3: Create a virtual environment and install**

```bash
cd server
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.in
pip freeze > requirements.txt
```

- [ ] **Step 4: Write `server/.env.example`**

```
# MongoDB Connection
MONGODB_URI="mongodb+srv://<username>:<password>@<cluster>.mongodb.net/foodies?retryWrites=true&w=majority"

# OPTIONAL: Voyage AI Configuration (required for Vector Search)
# VOYAGE_API_KEY=your_voyage_api_key

# Server Configuration
PORT=3011

# CORS Configuration
CORS_ORIGINS=http://localhost:3000

# Logging Configuration
LOG_LEVEL=INFO
```

- [ ] **Step 5: Create your real `.env`**

```bash
cp .env.example .env
```

Edit `.env` and set `MONGODB_URI` to your Atlas connection string (pointing at any database name — the app will use/create the `foodies` database regardless of what's in the URI path). Add `VOYAGE_API_KEY` if you want vector search to work later.

- [ ] **Step 6: Write `server/.gitignore`**

```
.venv/
__pycache__/
*.pyc
.env
.pytest_cache/
*.egg-info/
```

- [ ] **Step 7: Write `server/pytest.ini`**

```ini
[pytest]
python_files = test_*.py *_test.py
python_classes = Test*
python_functions = test_*

testpaths = tests

addopts =
    -v
    --strict-markers
    --tb=short
    --asyncio-mode=auto
    --color=yes

markers =
    unit: Unit tests with mocked dependencies
    integration: Integration tests requiring database

asyncio_mode = auto
asyncio_default_fixture_loop_scope = function
```

- [ ] **Step 8: Create empty package marker files**

```bash
touch server/tests/__init__.py
touch server/src/middleware/__init__.py
```

- [ ] **Step 9: Verify pytest boots cleanly**

Run: `cd server && pytest --collect-only -q`
Expected: `no tests ran` (exit code 5) — this confirms `pytest.ini` parses and markers are registered without error, not that any test exists yet.

- [ ] **Step 10: Commit**

```bash
git add server/requirements.in server/requirements.txt server/.env.example server/.gitignore server/pytest.ini server/tests/__init__.py server/src/middleware/__init__.py
git commit -m "Scaffold server project structure and dependencies"
```

---

### Task 2: MongoDB Client Module

**Files:**
- Create: `server/src/database/mongo_client.py`
- Test: `server/tests/test_mongo_client.py`

**Interfaces:**
- Consumes: `.env` (`MONGODB_URI`, `VOYAGE_API_KEY`) from Task 1.
- Produces: `get_collection(name: str) -> AsyncCollection` and `voyage_ai_available() -> Optional[str]`, used by every router task from Task 6 onward. Also exposes `db` (the `AsyncDatabase` handle) and `client` (the `AsyncMongoClient`), used by `main.py` in Task 16.

- [ ] **Step 1: Write the failing tests**

```python
# server/tests/test_mongo_client.py
"""Unit tests for the MongoDB client module's pure-logic helpers."""

import os
import pytest
from unittest.mock import patch


@pytest.mark.unit
def test_get_collection_returns_named_collection():
    from src.database.mongo_client import get_collection, db
    collection = get_collection("recipes")
    assert collection.name == "recipes"
    assert collection is db["recipes"]


@pytest.mark.unit
def test_voyage_ai_available_returns_none_when_unset():
    with patch.dict(os.environ, {}, clear=True):
        from src.database.mongo_client import voyage_ai_available
        assert voyage_ai_available() is None


@pytest.mark.unit
def test_voyage_ai_available_returns_none_for_placeholder_key():
    with patch.dict(os.environ, {"VOYAGE_API_KEY": "your_voyage_api_key"}):
        from src.database.mongo_client import voyage_ai_available
        assert voyage_ai_available() is None


@pytest.mark.unit
def test_voyage_ai_available_returns_key_when_configured():
    with patch.dict(os.environ, {"VOYAGE_API_KEY": "abc123"}):
        from src.database.mongo_client import voyage_ai_available
        assert voyage_ai_available() == "abc123"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd server && pytest tests/test_mongo_client.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'src.database.mongo_client'`

- [ ] **Step 3: Write the implementation**

```python
# server/src/database/mongo_client.py
from pymongo import AsyncMongoClient
from dotenv import load_dotenv
import os
import voyageai

load_dotenv()

DATABASE_NAME = "foodies"

client = AsyncMongoClient(os.getenv("MONGODB_URI"),
    appname="foodies-api")

db = client[DATABASE_NAME]

voyage_api_key = os.getenv("VOYAGE_API_KEY")
if voyage_api_key:
    voyageai.api_key = voyage_api_key


def get_collection(name: str):
    return db[name]


def voyage_ai_available():
    """Check if Voyage API Key is available and valid."""
    api_key = os.getenv("VOYAGE_API_KEY")
    if api_key is None or api_key == "your_voyage_api_key":
        return None
    return api_key is not None and api_key.strip() != ""
```

Note: `AsyncMongoClient` is lazy — constructing it and reading `client[DATABASE_NAME]` does not open a network connection, so this test suite runs without hitting Atlas. `MONGODB_URI` still needs to be a syntactically valid string (from your `.env`), or construction itself will fail.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd server && pytest tests/test_mongo_client.py -v`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add server/src/database/mongo_client.py server/tests/test_mongo_client.py
git commit -m "Add MongoDB client module with collection accessor"
```

---

### Task 3: Pydantic Models & Schema Tests

**Files:**
- Create: `server/src/models/models.py`
- Test: `server/tests/test_recipe_schemas.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: `Recipe`, `CreateRecipeRequest`, `UpdateRecipeRequest`, `Pagination`, `SuccessResponse[T]`, `T`, `Review`, `CreateReviewRequest`, `VectorSearchResult`, `SearchRecipesResponse` — imported by every utils/router task from Task 4 onward.

`Recipe` carries two server-managed, denormalized fields — `averageRating` and `reviewCount` — recomputed from the `reviews` collection whenever a review is created (Task 12). This lets `GET /api/recipes/` filter by minimum rating directly on the `recipes` collection instead of running a `$lookup` on every list request.

- [ ] **Step 1: Write the failing tests**

```python
# server/tests/test_recipe_schemas.py
"""
Unit tests for recipe and review Pydantic models.

These verify request validation only — no database or HTTP dependencies.
"""

import pytest
from pydantic import ValidationError
from src.models.models import CreateRecipeRequest, UpdateRecipeRequest, CreateReviewRequest


@pytest.mark.unit
class TestRecipeCreateValidation:
    """Tests for CreateRecipeRequest model validation."""

    def test_create_recipe_with_valid_data(self):
        recipe_data = {
            "title": "Test Recipe",
            "cuisine": "Italian",
            "difficulty": "easy",
            "ingredients": ["flour", "eggs"],
            "prepTimeMinutes": 15
        }
        recipe = CreateRecipeRequest(**recipe_data)
        assert recipe.title == "Test Recipe"
        assert recipe.cuisine == "Italian"
        assert recipe.prepTimeMinutes == 15

    def test_create_recipe_missing_required_field(self):
        recipe_data = {"cuisine": "Italian", "description": "A recipe without a title"}
        with pytest.raises(ValidationError) as exc_info:
            CreateRecipeRequest(**recipe_data)
        errors = exc_info.value.errors()
        assert any(error["loc"] == ("title",) for error in errors)

    def test_create_recipe_invalid_prep_time_type(self):
        recipe_data = {"title": "Test Recipe", "prepTimeMinutes": "not-a-number"}
        with pytest.raises(ValidationError) as exc_info:
            CreateRecipeRequest(**recipe_data)
        errors = exc_info.value.errors()
        assert any(error["loc"] == ("prepTimeMinutes",) for error in errors)

    def test_create_recipe_with_only_required_fields(self):
        recipe = CreateRecipeRequest(**{"title": "Minimal Recipe"})
        assert recipe.title == "Minimal Recipe"
        assert recipe.cuisine is None
        assert recipe.ingredients is None


@pytest.mark.unit
class TestRecipeUpdateValidation:
    """Tests for UpdateRecipeRequest model validation."""

    def test_update_recipe_with_valid_data(self):
        recipe_update = UpdateRecipeRequest(**{"title": "Updated Title", "difficulty": "hard"})
        assert recipe_update.title == "Updated Title"
        assert recipe_update.difficulty == "hard"

    def test_update_recipe_with_partial_data(self):
        recipe_update = UpdateRecipeRequest(**{"title": "Only Title Updated"})
        assert recipe_update.title == "Only Title Updated"
        assert recipe_update.cuisine is None

    def test_update_recipe_empty_data(self):
        recipe_update = UpdateRecipeRequest(**{})
        assert recipe_update.title is None
        assert recipe_update.difficulty is None


@pytest.mark.unit
class TestRecipeDataStructure:
    """Tests for recipe data structure and types."""

    def test_recipe_with_all_fields(self):
        recipe_data = {
            "title": "Complete Recipe",
            "description": "Short summary",
            "instructions": "Step 1. Step 2.",
            "cuisine": "Mexican",
            "difficulty": "medium",
            "prepTimeMinutes": 20,
            "cookTimeMinutes": 30,
            "servings": 4,
            "ingredients": ["tortilla", "beans", "cheese"],
            "tags": ["vegetarian", "quick"]
        }
        recipe = CreateRecipeRequest(**recipe_data)
        assert recipe.title == "Complete Recipe"
        assert len(recipe.ingredients) == 3
        assert len(recipe.tags) == 2

    def test_recipe_ingredients_as_list(self):
        recipe = CreateRecipeRequest(**{"title": "Ingredient Test", "ingredients": ["salt", "pepper"]})
        assert isinstance(recipe.ingredients, list)
        assert "salt" in recipe.ingredients

    def test_recipe_with_numeric_fields(self):
        recipe_data = {"title": "Numeric Test", "prepTimeMinutes": 10, "cookTimeMinutes": 25, "servings": 2}
        recipe = CreateRecipeRequest(**recipe_data)
        assert isinstance(recipe.prepTimeMinutes, int)
        assert isinstance(recipe.servings, int)


@pytest.mark.unit
class TestReviewCreateValidation:
    """Tests for CreateReviewRequest model validation."""

    def test_create_review_with_valid_data(self):
        review = CreateReviewRequest(**{"reviewerName": "Alex", "rating": 5, "comment": "Delicious!"})
        assert review.reviewerName == "Alex"
        assert review.rating == 5

    def test_create_review_missing_reviewer_name(self):
        with pytest.raises(ValidationError) as exc_info:
            CreateReviewRequest(**{"rating": 4})
        errors = exc_info.value.errors()
        assert any(error["loc"] == ("reviewerName",) for error in errors)

    def test_create_review_rating_above_maximum(self):
        with pytest.raises(ValidationError) as exc_info:
            CreateReviewRequest(**{"reviewerName": "Alex", "rating": 6})
        errors = exc_info.value.errors()
        assert any(error["loc"] == ("rating",) for error in errors)

    def test_create_review_rating_below_minimum(self):
        with pytest.raises(ValidationError) as exc_info:
            CreateReviewRequest(**{"reviewerName": "Alex", "rating": 0})
        errors = exc_info.value.errors()
        assert any(error["loc"] == ("rating",) for error in errors)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd server && pytest tests/test_recipe_schemas.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'src.models.models'`

- [ ] **Step 3: Write the implementation**

```python
# server/src/models/models.py
from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional, TypeVar, Generic

T = TypeVar("T")


class Recipe(BaseModel):
    id: Optional[str] = Field(alias="_id")
    title: str
    description: Optional[str] = None
    instructions: Optional[str] = None
    cuisine: Optional[str] = None
    difficulty: Optional[str] = None
    prepTimeMinutes: Optional[int] = None
    cookTimeMinutes: Optional[int] = None
    servings: Optional[int] = None
    ingredients: Optional[list[str]] = None
    tags: Optional[list[str]] = None
    averageRating: Optional[float] = None
    reviewCount: Optional[int] = None
    createdAt: Optional[datetime] = None

    model_config = {
        "populate_by_name": True
    }


class CreateRecipeRequest(BaseModel):
    title: str
    description: Optional[str] = None
    instructions: Optional[str] = None
    cuisine: Optional[str] = None
    difficulty: Optional[str] = None
    prepTimeMinutes: Optional[int] = None
    cookTimeMinutes: Optional[int] = None
    servings: Optional[int] = None
    ingredients: Optional[list[str]] = None
    tags: Optional[list[str]] = None


class UpdateRecipeRequest(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    instructions: Optional[str] = None
    cuisine: Optional[str] = None
    difficulty: Optional[str] = None
    prepTimeMinutes: Optional[int] = None
    cookTimeMinutes: Optional[int] = None
    servings: Optional[int] = None
    ingredients: Optional[list[str]] = None
    tags: Optional[list[str]] = None


class Pagination(BaseModel):
    page: int
    limit: int
    total: int
    pages: int


class SuccessResponse(BaseModel, Generic[T]):
    success: bool = True
    message: Optional[str]
    data: T
    timestamp: str
    pagination: Optional[Pagination] = None


class Review(BaseModel):
    id: Optional[str] = Field(alias="_id")
    recipe_id: str
    reviewerName: str
    rating: int
    comment: Optional[str] = None
    date: Optional[datetime] = None

    model_config = {
        "populate_by_name": True
    }


class CreateReviewRequest(BaseModel):
    reviewerName: str
    rating: int = Field(..., ge=1, le=5)
    comment: Optional[str] = None


class VectorSearchResult(BaseModel):
    id: Optional[str] = Field(alias="_id")
    title: str
    description: Optional[str] = None
    cuisine: Optional[str] = None
    score: float

    model_config = {
        "populate_by_name": True
    }


class SearchRecipesResponse(BaseModel):
    recipes: list[Recipe]
    totalCount: int
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd server && pytest tests/test_recipe_schemas.py -v`
Expected: 13 passed

- [ ] **Step 5: Commit**

```bash
git add server/src/models/models.py server/tests/test_recipe_schemas.py
git commit -m "Add recipe and review Pydantic models"
```

---

### Task 4: Response Envelope, Logging & Error Utilities

**Files:**
- Create: `server/src/utils/logger.py`
- Create: `server/src/utils/exceptions.py`
- Create: `server/src/utils/errorResponse.py`
- Create: `server/src/utils/successResponse.py`
- Create: `server/src/utils/response_docs.py`
- Create: `server/src/middleware/request_logging.py`
- Test: `server/tests/test_response_utils.py`

**Interfaces:**
- Consumes: `SuccessResponse`, `T` from `src.models.models` (Task 3).
- Produces: `create_success_response(data, message=None) -> SuccessResponse[T]`, `create_error_response(message, code=None, details=None) -> dict`, `server_error_response(message, code, *, log_context, status_code=500) -> JSONResponse`, `VoyageAuthError`, `VoyageAPIError`, `logger`, `RequestLoggingMiddleware`, and the response-doc dicts (`OBJECTID_VALIDATION_RESPONSES`, `SEARCH_ENDPOINT_RESPONSES`, `VECTOR_SEARCH_RESPONSES`, `DATABASE_OPERATION_RESPONSES`, `CRUD_OPERATION_RESPONSES`, `CRUD_WITH_OBJECTID_RESPONSES`) — all consumed by every router task from Task 6 onward.

`logger.py`, `request_logging.py`, and `response_docs.py` are infrastructure/configuration with no branching business logic, so they're not put through TDD — they're verified by the app-boot smoke test in Task 5 instead. `errorResponse.py` and `successResponse.py` are pure functions and do get tests.

- [ ] **Step 1: Write the failing tests**

```python
# server/tests/test_response_utils.py
"""Unit tests for the success/error response envelope helpers."""

import pytest
from src.utils.successResponse import create_success_response
from src.utils.errorResponse import create_error_response


@pytest.mark.unit
class TestCreateSuccessResponse:
    def test_wraps_data_with_default_message(self):
        response = create_success_response({"title": "Pasta"})
        assert response.success is True
        assert response.data == {"title": "Pasta"}
        assert response.message == "Operation completed successfully."
        assert response.timestamp.endswith("Z")

    def test_wraps_data_with_custom_message(self):
        response = create_success_response(["a", "b"], "Found 2 items")
        assert response.message == "Found 2 items"
        assert response.data == ["a", "b"]


@pytest.mark.unit
class TestCreateErrorResponse:
    def test_includes_code_and_message(self):
        body = create_error_response("Not found", code="RECIPE_NOT_FOUND")
        assert body["success"] is False
        assert body["message"] == "Not found"
        assert body["error"]["code"] == "RECIPE_NOT_FOUND"
        assert body["error"]["details"] is None

    def test_includes_details_when_provided(self):
        body = create_error_response("Bad input", code="VALIDATION_ERROR", details="field 'title' required")
        assert body["error"]["details"] == "field 'title' required"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd server && pytest tests/test_response_utils.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write `server/src/utils/logger.py`**

```python
"""
Logging configuration for the FastAPI application.
"""

import logging
import os
import sys
from datetime import datetime
from typing import Optional


class Colors:
    RESET = "\033[0m"
    BOLD = "\033[1m"
    FAINT = "\033[2m"
    DEBUG = "\033[36m"
    INFO = "\033[32m"
    WARNING = "\033[33m"
    ERROR = "\033[31m"
    CRITICAL = "\033[35m"
    TIMESTAMP = "\033[90m"
    LOGGER_NAME = "\033[36m"


class ColoredFormatter(logging.Formatter):
    LEVEL_COLORS = {
        logging.DEBUG: Colors.DEBUG,
        logging.INFO: Colors.INFO,
        logging.WARNING: Colors.WARNING,
        logging.ERROR: Colors.ERROR,
        logging.CRITICAL: Colors.CRITICAL,
    }

    def format(self, record: logging.LogRecord) -> str:
        level_color = self.LEVEL_COLORS.get(record.levelno, Colors.RESET)
        timestamp = datetime.fromtimestamp(record.created).strftime("%H:%M:%S")
        level_name = f"{record.levelname:>5}"
        logger_name = record.name[-40:] if len(record.name) > 40 else record.name

        formatted = (
            f"{Colors.FAINT}{timestamp}{Colors.RESET} "
            f"{level_color}{level_name}{Colors.RESET} "
            f"{Colors.FAINT}---{Colors.RESET} "
            f"{Colors.FAINT}[{Colors.RESET}"
            f"{Colors.LOGGER_NAME}{logger_name:>40}{Colors.RESET}"
            f"{Colors.FAINT}]{Colors.RESET} "
            f"{Colors.FAINT}:{Colors.RESET} "
            f"{record.getMessage()}"
        )
        if record.exc_info:
            formatted += "\n" + self.formatException(record.exc_info)
        return formatted


class PlainFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        timestamp = datetime.fromtimestamp(record.created).strftime("%Y-%m-%d %H:%M:%S")
        level_name = f"{record.levelname:>5}"
        logger_name = record.name[-40:] if len(record.name) > 40 else record.name
        formatted = f"{timestamp} {level_name} --- [{logger_name:>40}] : {record.getMessage()}"
        if record.exc_info:
            formatted += "\n" + self.formatException(record.exc_info)
        return formatted


def setup_logger(name: str = "foodies", level: Optional[str] = None, log_file: Optional[str] = None) -> logging.Logger:
    log_level_str = level or os.getenv("LOG_LEVEL", "INFO").upper()
    log_level = getattr(logging, log_level_str, logging.INFO)

    logger = logging.getLogger(name)
    logger.setLevel(log_level)
    logger.handlers.clear()

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(log_level)
    console_handler.setFormatter(ColoredFormatter())
    logger.addHandler(console_handler)

    file_path = log_file or os.getenv("LOG_FILE")
    if file_path:
        file_handler = logging.FileHandler(file_path)
        file_handler.setLevel(log_level)
        file_handler.setFormatter(PlainFormatter())
        logger.addHandler(file_handler)

    logger.propagate = False
    return logger


logger = setup_logger()
```

- [ ] **Step 4: Write `server/src/utils/exceptions.py`**

```python
"""Custom exception classes for Voyage AI interactions."""


class VoyageAuthError(Exception):
    def __init__(self, message: str = "Invalid Voyage AI API key"):
        self.message = message
        super().__init__(self.message)


class VoyageAPIError(Exception):
    def __init__(self, message: str, status_code: int = 500):
        self.message = message
        self.status_code = status_code
        super().__init__(self.message)
```

- [ ] **Step 5: Write `server/src/utils/errorResponse.py`**

```python
"""Utility functions for creating standardized error responses."""

from datetime import datetime, timezone
from typing import Optional, Any

from fastapi.responses import JSONResponse

from src.utils.logger import logger


def create_error_response(
    message: str,
    code: Optional[str] = None,
    details: Optional[Any] = None
) -> dict:
    return {
        "success": False,
        "message": message,
        "error": {
            "message": message,
            "code": code,
            "details": details
        },
        "timestamp": datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
    }


def server_error_response(
    message: str,
    code: str,
    *,
    log_context: str,
    status_code: int = 500,
) -> JSONResponse:
    """Log the current exception and return a generic error payload (no stack traces). Call only from an except block."""
    logger.exception("%s failed", log_context)
    return JSONResponse(
        status_code=status_code,
        content=create_error_response(message=message, code=code),
    )
```

- [ ] **Step 6: Write `server/src/utils/successResponse.py`**

```python
from datetime import datetime, timezone
from typing import Optional
from src.models.models import SuccessResponse, T


def create_success_response(data: T, message: Optional[str] = None) -> SuccessResponse[T]:
    return SuccessResponse(
        message=message or "Operation completed successfully.",
        data=data,
        timestamp=datetime.now(timezone.utc).isoformat() + "Z",
    )
```

- [ ] **Step 7: Write `server/src/middleware/request_logging.py`**

```python
"""Request logging middleware for FastAPI."""

import time
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from src.utils.logger import logger


SKIP_PATHS = {"/docs", "/redoc", "/openapi.json", "/favicon.ico", "/health"}


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if request.url.path in SKIP_PATHS:
            return await call_next(request)

        start_time = time.perf_counter()
        logger.debug(
            f"Incoming request: {request.method} {request.url.path} from {request.client.host if request.client else 'unknown'}"
        )

        response = await call_next(request)
        response_time_ms = (time.perf_counter() - start_time) * 1000

        self._log_request(
            method=request.method,
            path=request.url.path,
            status_code=response.status_code,
            response_time_ms=response_time_ms
        )
        return response

    def _log_request(self, method: str, path: str, status_code: int, response_time_ms: float) -> None:
        message = f"{method} {path} {status_code} - {response_time_ms:.0f}ms"
        if status_code >= 500:
            logger.error(message)
        elif status_code >= 400:
            logger.warning(message)
        else:
            logger.info(message)
```

- [ ] **Step 8: Write `server/src/utils/response_docs.py`**

```python
"""OpenAPI response documentation helpers, shared across recipe endpoints."""

ERROR_RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "success": {"type": "boolean"},
        "message": {"type": "string"},
        "error": {
            "type": "object",
            "properties": {
                "message": {"type": "string"},
                "code": {"type": "string"},
                "details": {"type": "string"}
            }
        },
        "timestamp": {"type": "string"}
    }
}

ERROR_400_INVALID_OBJECTID = {
    "description": "Bad Request - Invalid ObjectId format",
    "content": {"application/json": {"schema": {
        **ERROR_RESPONSE_SCHEMA,
        "example": {
            "success": False,
            "message": "The provided ID 'invalid_id' is not a valid ObjectId",
            "error": {"message": "The provided ID 'invalid_id' is not a valid ObjectId", "code": "INVALID_OBJECT_ID", "details": None},
            "timestamp": "2024-01-01T12:00:00.000Z"
        }
    }}}
}

ERROR_400_VALIDATION = {
    "description": "Bad Request - Request validation failed",
    "content": {"application/json": {"schema": {
        **ERROR_RESPONSE_SCHEMA,
        "example": {
            "success": False,
            "message": "No valid fields provided for update.",
            "error": {"message": "No valid fields provided for update.", "code": "NO_UPDATE_DATA", "details": None},
            "timestamp": "2024-01-01T12:00:00.000Z"
        }
    }}}
}

ERROR_400_SEARCH_ERRORS = {
    "description": "Bad Request - Invalid search operator or missing search parameters",
    "content": {"application/json": {
        "schema": ERROR_RESPONSE_SCHEMA,
        "examples": {
            "invalid_operator": {
                "summary": "Invalid search operator",
                "value": {
                    "success": False,
                    "message": "Invalid search operator 'invalid'.",
                    "error": {"message": "Invalid search operator 'invalid'.", "code": "INVALID_SEARCH_OPERATOR", "details": None},
                    "timestamp": "2024-01-01T12:00:00.000Z"
                }
            },
            "missing_params": {
                "summary": "Missing search parameters",
                "value": {
                    "success": False,
                    "message": "At least one search parameter must be provided.",
                    "error": {"message": "At least one search parameter must be provided.", "code": "MISSING_SEARCH_PARAMS", "details": None},
                    "timestamp": "2024-01-01T12:00:00.000Z"
                }
            }
        }
    }}
}

ERROR_401_VOYAGE_AUTH = {
    "description": "Unauthorized - Invalid Voyage AI API key",
    "content": {"application/json": {"schema": {
        **ERROR_RESPONSE_SCHEMA,
        "example": {
            "success": False,
            "message": "Invalid Voyage AI API key",
            "error": {"message": "Invalid Voyage AI API key", "code": "VOYAGE_AUTH_ERROR", "details": "Please verify your VOYAGE_API_KEY is correct in the .env file"},
            "timestamp": "2024-01-01T12:00:00.000Z"
        }
    }}}
}

ERROR_404_RECIPE_NOT_FOUND = {
    "description": "Not Found - Recipe not found",
    "content": {"application/json": {"schema": {
        **ERROR_RESPONSE_SCHEMA,
        "example": {
            "success": False,
            "message": "No recipe found with ID: 507f1f77bcf86cd799439011",
            "error": {"message": "No recipe found with ID: 507f1f77bcf86cd799439011", "code": "RECIPE_NOT_FOUND", "details": None},
            "timestamp": "2024-01-01T12:00:00.000Z"
        }
    }}}
}

FASTAPI_422_VALIDATION_ERROR = {
    "description": "Unprocessable Entity - Validation error",
    "content": {"application/json": {"schema": {
        "type": "object",
        "properties": {"detail": {"type": "array", "items": {"type": "object", "properties": {
            "loc": {"type": "array"}, "msg": {"type": "string"}, "type": {"type": "string"}
        }}}},
        "example": {"detail": [{"loc": ["body", "title"], "msg": "field required", "type": "value_error.missing"}]}
    }}}
}

ERROR_500_DATABASE = {
    "description": "Internal Server Error - Database operation failed",
    "content": {"application/json": {"schema": {
        **ERROR_RESPONSE_SCHEMA,
        "example": {
            "success": False,
            "message": "Database error occurred.",
            "error": {"message": "Database error occurred.", "code": "DATABASE_ERROR", "details": None},
            "timestamp": "2024-01-01T12:00:00.000Z"
        }
    }}}
}

ERROR_500_SEARCH = {
    "description": "Internal Server Error - Search operation failed",
    "content": {"application/json": {"schema": {
        **ERROR_RESPONSE_SCHEMA,
        "example": {
            "success": False,
            "message": "An error occurred while performing the search.",
            "error": {"message": "An error occurred while performing the search.", "code": "SEARCH_ERROR", "details": None},
            "timestamp": "2024-01-01T12:00:00.000Z"
        }
    }}}
}

ERROR_500_VECTOR_SEARCH = {
    "description": "Internal Server Error - Vector search operation failed",
    "content": {"application/json": {"schema": {
        **ERROR_RESPONSE_SCHEMA,
        "example": {
            "success": False,
            "message": "Error performing vector search.",
            "error": {"message": "Error performing vector search.", "code": "VECTOR_SEARCH_ERROR", "details": None},
            "timestamp": "2024-01-01T12:00:00.000Z"
        }
    }}}
}

ERROR_503_VOYAGE = {
    "description": "Service Unavailable - Vector search service unavailable",
    "content": {"application/json": {
        "schema": ERROR_RESPONSE_SCHEMA,
        "examples": {
            "api_key_not_configured": {
                "summary": "Voyage API key not configured",
                "value": {
                    "success": False,
                    "message": "Vector search unavailable: VOYAGE_API_KEY not configured.",
                    "error": {"message": "Vector search unavailable: VOYAGE_API_KEY not configured.", "code": "SERVICE_UNAVAILABLE", "details": None},
                    "timestamp": "2024-01-01T12:00:00.000Z"
                }
            }
        }
    }}
}

OBJECTID_VALIDATION_RESPONSES = {400: ERROR_400_INVALID_OBJECTID, 404: ERROR_404_RECIPE_NOT_FOUND, 500: ERROR_500_DATABASE}
SEARCH_ENDPOINT_RESPONSES = {400: ERROR_400_SEARCH_ERRORS, 500: ERROR_500_SEARCH}
VECTOR_SEARCH_RESPONSES = {401: ERROR_401_VOYAGE_AUTH, 500: ERROR_500_VECTOR_SEARCH, 503: ERROR_503_VOYAGE}
DATABASE_OPERATION_RESPONSES = {500: ERROR_500_DATABASE}
CRUD_OPERATION_RESPONSES = {400: ERROR_400_VALIDATION, 422: FASTAPI_422_VALIDATION_ERROR, 500: ERROR_500_DATABASE}
CRUD_WITH_OBJECTID_RESPONSES = {**OBJECTID_VALIDATION_RESPONSES, 422: FASTAPI_422_VALIDATION_ERROR}
```

- [ ] **Step 9: Run tests to verify they pass**

Run: `cd server && pytest tests/test_response_utils.py -v`
Expected: 4 passed

- [ ] **Step 10: Commit**

```bash
git add server/src/utils server/src/middleware/request_logging.py server/tests/test_response_utils.py
git commit -m "Add response envelope, logging, and exception utilities"
```

---

### Task 5: FastAPI App Skeleton

**Files:**
- Create: `server/main.py`
- Create: `server/src/routers/recipes.py`
- Test: `server/tests/test_app.py`

**Interfaces:**
- Consumes: `RequestLoggingMiddleware` (Task 4).
- Produces: `app` (the FastAPI instance in `main.py`) and `router` (an empty `APIRouter` in `src/routers/recipes.py`) — every endpoint task from Task 6 onward appends to `recipes.py` and relies on this `app`/`router` wiring already being in place.

- [ ] **Step 1: Write the failing test**

```python
# server/tests/test_app.py
"""Smoke tests verifying the FastAPI app boots and is wired up correctly."""

import pytest


@pytest.mark.unit
def test_openapi_schema_generates():
    """The app should generate its OpenAPI schema without opening a database connection."""
    from main import app
    schema = app.openapi()
    assert "openapi" in schema
    assert "paths" in schema
```

This calls `app.openapi()` directly (a plain Python method, no ASGI request, no lifespan) so it never touches MongoDB — safe to run with no server running and no live index setup.

- [ ] **Step 2: Run test to verify it fails**

Run: `cd server && pytest tests/test_app.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'main'`

- [ ] **Step 3: Write the router stub**

```python
# server/src/routers/recipes.py
from fastapi import APIRouter

router = APIRouter()
```

- [ ] **Step 4: Write `server/main.py`**

```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from src.routers import recipes
from src.middleware.request_logging import RequestLoggingMiddleware

import os
from dotenv import load_dotenv

load_dotenv()

app = FastAPI()

cors_origins = os.getenv("CORS_ORIGINS", "http://localhost:3000,http://localhost:3011").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in cors_origins],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_middleware(RequestLoggingMiddleware)

app.include_router(recipes.router, prefix="/api/recipes", tags=["recipes"])
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd server && pytest tests/test_app.py -v`
Expected: 1 passed

- [ ] **Step 6: Manually confirm the server actually boots**

```bash
uvicorn main:app --reload --port 3011
```

Visit `http://localhost:3011/docs` — you should see an empty Swagger UI (no endpoints yet, since `recipes.router` has none). Stop the server (Ctrl+C) once confirmed.

- [ ] **Step 7: Commit**

```bash
git add server/main.py server/src/routers/recipes.py server/tests/test_app.py
git commit -m "Add FastAPI app skeleton with CORS and logging middleware"
```

---

### Task 6: GET /api/recipes/{id}

**Files:**
- Modify: `server/src/routers/recipes.py`
- Create: `server/tests/test_recipe_routes.py`

**Interfaces:**
- Consumes: `get_collection` (Task 2), `Recipe`/`SuccessResponse` (Task 3), `create_success_response`/`create_error_response`/`server_error_response` (Task 4), `OBJECTID_VALIDATION_RESPONSES` (Task 4).
- Produces: `get_recipe_by_id(id: str)` route handler. `TEST_RECIPE_ID` / `INVALID_RECIPE_ID` constants in the test file, reused by every subsequent test task.

- [ ] **Step 1: Write the failing tests**

```python
# server/tests/test_recipe_routes.py
"""
Unit Tests for Recipe Routes

These tests verify route handler logic using mocked MongoDB operations
(unittest.mock.AsyncMock), with no real database connection required.
"""

import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from bson import ObjectId
from fastapi.responses import JSONResponse

TEST_RECIPE_ID = "507f1f77bcf86cd799439011"
INVALID_RECIPE_ID = "invalid-id"


@pytest.mark.unit
@pytest.mark.asyncio
class TestGetRecipeById:
    """Tests for GET /api/recipes/{id} endpoint."""

    @patch('src.routers.recipes.get_collection')
    async def test_get_recipe_by_id_success(self, mock_get_collection):
        mock_collection = AsyncMock()
        mock_recipe = {"_id": ObjectId(TEST_RECIPE_ID), "title": "Test Recipe", "cuisine": "Italian"}
        mock_collection.find_one.return_value = mock_recipe
        mock_get_collection.return_value = mock_collection

        from src.routers.recipes import get_recipe_by_id
        result = await get_recipe_by_id(TEST_RECIPE_ID)

        assert result.success is True
        assert result.data["title"] == "Test Recipe"
        assert result.data["_id"] == TEST_RECIPE_ID
        mock_collection.find_one.assert_called_once_with({"_id": ObjectId(TEST_RECIPE_ID)})

    @patch('src.routers.recipes.get_collection')
    async def test_get_recipe_by_id_not_found(self, mock_get_collection):
        mock_collection = AsyncMock()
        mock_collection.find_one.return_value = None
        mock_get_collection.return_value = mock_collection

        from src.routers.recipes import get_recipe_by_id
        response = await get_recipe_by_id(TEST_RECIPE_ID)

        assert isinstance(response, JSONResponse)
        assert response.status_code == 404
        body = json.loads(response.body.decode())
        assert body["success"] is False
        assert body["error"]["code"] == "RECIPE_NOT_FOUND"

    async def test_get_recipe_by_id_invalid_id(self):
        from src.routers.recipes import get_recipe_by_id
        response = await get_recipe_by_id(INVALID_RECIPE_ID)

        assert isinstance(response, JSONResponse)
        assert response.status_code == 400
        body = json.loads(response.body.decode())
        assert body["error"]["code"] == "INVALID_OBJECT_ID"

    @patch('src.routers.recipes.get_collection')
    async def test_get_recipe_by_id_database_error(self, mock_get_collection):
        mock_collection = AsyncMock()
        mock_collection.find_one.side_effect = Exception("Database connection failed")
        mock_get_collection.return_value = mock_collection

        from src.routers.recipes import get_recipe_by_id
        response = await get_recipe_by_id(TEST_RECIPE_ID)

        assert isinstance(response, JSONResponse)
        assert response.status_code == 500
        body = json.loads(response.body.decode())
        assert body["error"]["code"] == "DATABASE_ERROR"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd server && pytest tests/test_recipe_routes.py -v`
Expected: FAIL with `ImportError: cannot import name 'get_recipe_by_id'`

- [ ] **Step 3: Implement the endpoint**

Replace the contents of `server/src/routers/recipes.py` with:

```python
from fastapi import APIRouter
from fastapi.responses import JSONResponse
from src.database.mongo_client import get_collection
from src.models.models import Recipe, SuccessResponse
from src.utils.successResponse import create_success_response
from src.utils.errorResponse import create_error_response, server_error_response
from src.utils.response_docs import OBJECTID_VALIDATION_RESPONSES
from bson import ObjectId, errors

router = APIRouter()


@router.get(
    "/{id}",
    response_model=SuccessResponse[Recipe],
    status_code=200,
    summary="Retrieve a single recipe by its ID.",
    responses=OBJECTID_VALIDATION_RESPONSES
)
async def get_recipe_by_id(id: str):
    try:
        object_id = ObjectId(id)
    except errors.InvalidId:
        return JSONResponse(
            status_code=400,
            content=create_error_response(
                message=f"The provided ID '{id}' is not a valid ObjectId",
                code="INVALID_OBJECT_ID"
            )
        )

    recipes_collection = get_collection("recipes")
    try:
        recipe = await recipes_collection.find_one({"_id": object_id})
    except Exception:
        return server_error_response(
            "Database error occurred.",
            "DATABASE_ERROR",
            log_context="get_recipe_by_id",
        )

    if recipe is None:
        return JSONResponse(
            status_code=404,
            content=create_error_response(
                message=f"No recipe found with ID: {id}",
                code="RECIPE_NOT_FOUND"
            )
        )

    recipe["_id"] = str(recipe["_id"])
    return create_success_response(recipe, "Recipe retrieved successfully")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd server && pytest tests/test_recipe_routes.py -v`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add server/src/routers/recipes.py server/tests/test_recipe_routes.py
git commit -m "Add GET /api/recipes/{id} endpoint"
```

---

### Task 7: GET /api/recipes/ (list, filter, sort, paginate)

**Files:**
- Modify: `server/src/routers/recipes.py`
- Modify: `server/tests/test_recipe_routes.py`

**Interfaces:**
- Consumes: everything from Task 6, plus `Query` from `fastapi` and `List` from `typing`.
- Produces: `get_all_recipes(...)` route handler.

- [ ] **Step 1: Write the failing tests**

Append to `server/tests/test_recipe_routes.py`:

```python
class _AsyncCursorStub:
    """
    Minimal stand-in for a pymongo cursor: .sort()/.skip()/.limit() are
    synchronous chain calls (like the real driver), but iteration is async.
    Deliberately not a MagicMock — configuring __aiter__/__anext__ on Mock
    objects to behave correctly is version-sensitive, so a small real class
    is the reliable way to fake this protocol.
    """

    def __init__(self, items):
        self._iter = iter(items)

    def sort(self, *args, **kwargs):
        return self

    def skip(self, *args, **kwargs):
        return self

    def limit(self, *args, **kwargs):
        return self

    def __aiter__(self):
        return self

    async def __anext__(self):
        try:
            return next(self._iter)
        except StopIteration:
            raise StopAsyncIteration


@pytest.mark.unit
@pytest.mark.asyncio
class TestGetAllRecipes:
    """Tests for GET /api/recipes/ endpoint."""

    @patch('src.routers.recipes.get_collection')
    async def test_get_all_recipes_returns_list(self, mock_get_collection):
        mock_collection = MagicMock()
        recipes = [
            {"_id": ObjectId(TEST_RECIPE_ID), "title": "Recipe A", "cuisine": "Italian"},
            {"_id": ObjectId("507f1f77bcf86cd799439012"), "title": "Recipe B", "cuisine": "Mexican"},
        ]
        mock_collection.find.return_value = _AsyncCursorStub(recipes)
        mock_get_collection.return_value = mock_collection

        from src.routers.recipes import get_all_recipes
        result = await get_all_recipes()

        assert result.success is True
        assert len(result.data) == 2
        assert result.data[0]["_id"] == TEST_RECIPE_ID

    @patch('src.routers.recipes.get_collection')
    async def test_get_all_recipes_applies_cuisine_filter(self, mock_get_collection):
        mock_collection = MagicMock()
        mock_collection.find.return_value = _AsyncCursorStub([])
        mock_get_collection.return_value = mock_collection

        from src.routers.recipes import get_all_recipes
        await get_all_recipes(cuisine="Italian")

        called_filter = mock_collection.find.call_args[0][0]
        assert called_filter["cuisine"] == {"$regex": "Italian", "$options": "i"}

    @patch('src.routers.recipes.get_collection')
    async def test_get_all_recipes_applies_min_rating_filter(self, mock_get_collection):
        mock_collection = MagicMock()
        mock_collection.find.return_value = _AsyncCursorStub([])
        mock_get_collection.return_value = mock_collection

        from src.routers.recipes import get_all_recipes
        await get_all_recipes(min_rating=4.0)

        called_filter = mock_collection.find.call_args[0][0]
        assert called_filter["averageRating"] == {"$gte": 4.0}

    @patch('src.routers.recipes.get_collection')
    async def test_get_all_recipes_database_error(self, mock_get_collection):
        mock_collection = MagicMock()
        mock_collection.find.side_effect = Exception("boom")
        mock_get_collection.return_value = mock_collection

        from src.routers.recipes import get_all_recipes
        response = await get_all_recipes()

        assert isinstance(response, JSONResponse)
        assert response.status_code == 500
        body = json.loads(response.body.decode())
        assert body["error"]["code"] == "DATABASE_ERROR"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd server && pytest tests/test_recipe_routes.py::TestGetAllRecipes -v`
Expected: FAIL with `ImportError: cannot import name 'get_all_recipes'`

- [ ] **Step 3: Add the imports and endpoint**

Add to the imports at the top of `server/src/routers/recipes.py`:

```python
from fastapi import APIRouter, Query
from typing import List
```

(Replace the existing `from fastapi import APIRouter` line with the one above.)

Append to `server/src/routers/recipes.py`:

```python
@router.get(
    "/",
    response_model=SuccessResponse[List[Recipe]],
    status_code=200,
    summary="Retrieve a list of recipes with optional filtering, sorting, and pagination.",
    responses=DATABASE_OPERATION_RESPONSES
)
async def get_all_recipes(
    cuisine: str = Query(default=None),
    difficulty: str = Query(default=None),
    max_prep_time: int = Query(default=None, alias="maxPrepTime"),
    min_rating: float = Query(default=None, alias="minRating"),
    limit: int = Query(default=20, ge=1, le=100),
    skip: int = Query(default=0, ge=0),
    sort_by: str = Query(default="title", alias="sortBy"),
    sort_order: str = Query(default="asc", alias="sortOrder")
):
    recipes_collection = get_collection("recipes")
    filter_dict = {}
    if cuisine:
        filter_dict["cuisine"] = {"$regex": cuisine, "$options": "i"}
    if difficulty:
        filter_dict["difficulty"] = difficulty
    if max_prep_time is not None:
        filter_dict["prepTimeMinutes"] = {"$lte": max_prep_time}
    if min_rating is not None:
        filter_dict["averageRating"] = {"$gte": min_rating}

    sort_order_value = -1 if sort_order == "desc" else 1
    sort = [(sort_by, sort_order_value)]

    try:
        result = recipes_collection.find(filter_dict).sort(sort).skip(skip).limit(limit)
        recipes = []
        async for recipe in result:
            recipe["_id"] = str(recipe["_id"])
            recipes.append(recipe)
    except Exception:
        return server_error_response(
            "An error occurred while fetching recipes.",
            "DATABASE_ERROR",
            log_context="get_all_recipes",
        )

    return create_success_response(recipes, f"Found {len(recipes)} recipes.")
```

Also add `DATABASE_OPERATION_RESPONSES` to the `response_docs` import line:

```python
from src.utils.response_docs import OBJECTID_VALIDATION_RESPONSES, DATABASE_OPERATION_RESPONSES
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd server && pytest tests/test_recipe_routes.py -v`
Expected: 8 passed

- [ ] **Step 5: Commit**

```bash
git add server/src/routers/recipes.py server/tests/test_recipe_routes.py
git commit -m "Add GET /api/recipes/ list endpoint with filter/sort/pagination"
```

---

### Task 8: POST /api/recipes/ and POST /api/recipes/batch

**Files:**
- Modify: `server/src/routers/recipes.py`
- Modify: `server/tests/test_recipe_routes.py`

**Interfaces:**
- Consumes: `CreateRecipeRequest` (Task 3), `CRUD_OPERATION_RESPONSES` (Task 4).
- Produces: `create_recipe(recipe: CreateRecipeRequest)` and `create_recipes_batch(recipes: List[CreateRecipeRequest])` route handlers.

- [ ] **Step 1: Write the failing tests**

Append to `server/tests/test_recipe_routes.py`:

```python
from src.models.models import CreateRecipeRequest


@pytest.mark.unit
@pytest.mark.asyncio
class TestCreateRecipe:
    """Tests for POST /api/recipes/ endpoint."""

    @patch('src.routers.recipes.get_collection')
    async def test_create_recipe_success(self, mock_get_collection):
        mock_collection = AsyncMock()
        mock_result = MagicMock()
        mock_result.acknowledged = True
        mock_result.inserted_id = ObjectId(TEST_RECIPE_ID)
        mock_collection.insert_one.return_value = mock_result
        mock_collection.find_one.return_value = {"_id": ObjectId(TEST_RECIPE_ID), "title": "New Recipe"}
        mock_get_collection.return_value = mock_collection

        from src.routers.recipes import create_recipe
        result = await create_recipe(CreateRecipeRequest(title="New Recipe"))

        assert result.success is True
        assert result.data["title"] == "New Recipe"
        mock_collection.insert_one.assert_called_once()

    @patch('src.routers.recipes.get_collection')
    async def test_create_recipe_database_error(self, mock_get_collection):
        mock_collection = AsyncMock()
        mock_collection.insert_one.side_effect = Exception("Insert failed")
        mock_get_collection.return_value = mock_collection

        from src.routers.recipes import create_recipe
        response = await create_recipe(CreateRecipeRequest(title="New Recipe"))

        assert isinstance(response, JSONResponse)
        assert response.status_code == 500
        body = json.loads(response.body.decode())
        assert body["error"]["code"] == "DATABASE_ERROR"


@pytest.mark.unit
@pytest.mark.asyncio
class TestCreateRecipesBatch:
    """Tests for POST /api/recipes/batch endpoint."""

    @patch('src.routers.recipes.get_collection')
    async def test_create_recipes_batch_success(self, mock_get_collection):
        mock_collection = AsyncMock()
        mock_result = MagicMock()
        mock_result.inserted_ids = [ObjectId(TEST_RECIPE_ID), ObjectId("507f1f77bcf86cd799439012")]
        mock_collection.insert_many.return_value = mock_result
        mock_get_collection.return_value = mock_collection

        from src.routers.recipes import create_recipes_batch
        result = await create_recipes_batch([
            CreateRecipeRequest(title="Recipe A"),
            CreateRecipeRequest(title="Recipe B"),
        ])

        assert result.success is True
        assert result.data["insertedCount"] == 2

    async def test_create_recipes_batch_empty_list(self):
        from src.routers.recipes import create_recipes_batch
        response = await create_recipes_batch([])

        assert isinstance(response, JSONResponse)
        assert response.status_code == 400
        body = json.loads(response.body.decode())
        assert body["error"]["code"] == "EMPTY_REQUEST"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd server && pytest tests/test_recipe_routes.py::TestCreateRecipe tests/test_recipe_routes.py::TestCreateRecipesBatch -v`
Expected: FAIL with `ImportError`

- [ ] **Step 3: Implement the endpoints**

Append to `server/src/routers/recipes.py`:

```python
@router.post(
    "/",
    response_model=SuccessResponse[Recipe],
    status_code=201,
    summary="Create a new recipe.",
    responses=CRUD_OPERATION_RESPONSES
)
async def create_recipe(recipe: CreateRecipeRequest):
    recipe_data = recipe.model_dump(exclude_none=True)

    recipes_collection = get_collection("recipes")
    try:
        result = await recipes_collection.insert_one(recipe_data)
    except Exception:
        return server_error_response(
            "Database error occurred.",
            "DATABASE_ERROR",
            log_context="create_recipe_insert",
        )

    if not result.acknowledged:
        return JSONResponse(
            status_code=500,
            content=create_error_response(
                message="Failed to create recipe: The database did not acknowledge the insert operation",
                code="DATABASE_ERROR"
            )
        )

    try:
        created_recipe = await recipes_collection.find_one({"_id": result.inserted_id})
    except Exception:
        return server_error_response(
            "Database error occurred.",
            "DATABASE_ERROR",
            log_context="create_recipe_fetch",
        )

    created_recipe["_id"] = str(created_recipe["_id"])
    return create_success_response(created_recipe, f"Recipe '{recipe_data['title']}' created successfully")


@router.post(
    "/batch",
    response_model=SuccessResponse[dict],
    status_code=201,
    summary="Create multiple recipes in a single request.",
    responses=CRUD_OPERATION_RESPONSES
)
async def create_recipes_batch(recipes: List[CreateRecipeRequest]) -> SuccessResponse[dict]:
    if not recipes:
        return JSONResponse(
            status_code=400,
            content=create_error_response(
                message="Request body must be a non-empty list of recipes.",
                code="EMPTY_REQUEST"
            )
        )

    recipes_collection = get_collection("recipes")
    recipe_dicts = [recipe.model_dump(exclude_none=True) for recipe in recipes]

    try:
        result = await recipes_collection.insert_many(recipe_dicts)
    except Exception:
        return server_error_response(
            "Database error occurred.",
            "DATABASE_ERROR",
            log_context="create_recipes_batch",
        )

    return create_success_response({
        "insertedCount": len(result.inserted_ids),
        "insertedIds": [str(_id) for _id in result.inserted_ids]
    }, f"Successfully created {len(result.inserted_ids)} recipes.")
```

Add `CreateRecipeRequest` to the `models.models` import line:

```python
from src.models.models import Recipe, CreateRecipeRequest, SuccessResponse
```

Add `CRUD_OPERATION_RESPONSES` to the `response_docs` import:

```python
from src.utils.response_docs import OBJECTID_VALIDATION_RESPONSES, DATABASE_OPERATION_RESPONSES, CRUD_OPERATION_RESPONSES
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd server && pytest tests/test_recipe_routes.py -v`
Expected: 14 passed

- [ ] **Step 5: Commit**

```bash
git add server/src/routers/recipes.py server/tests/test_recipe_routes.py
git commit -m "Add POST /api/recipes/ and /batch create endpoints"
```

---

### Task 9: PATCH /api/recipes/{id} and PATCH /api/recipes/

**Files:**
- Modify: `server/src/routers/recipes.py`
- Modify: `server/tests/test_recipe_routes.py`

**Interfaces:**
- Consumes: `UpdateRecipeRequest` (Task 3), `CRUD_WITH_OBJECTID_RESPONSES` (Task 4), `Path`/`Body` from `fastapi`.
- Produces: `update_recipe(recipe_data, recipe_id)` and `update_recipes_batch(request_body)` route handlers.

- [ ] **Step 1: Write the failing tests**

Append to `server/tests/test_recipe_routes.py`:

```python
from src.models.models import UpdateRecipeRequest


@pytest.mark.unit
@pytest.mark.asyncio
class TestUpdateRecipe:
    """Tests for PATCH /api/recipes/{id} endpoint."""

    @patch('src.routers.recipes.get_collection')
    async def test_update_recipe_success(self, mock_get_collection):
        mock_collection = AsyncMock()
        mock_result = MagicMock()
        mock_result.matched_count = 1
        mock_collection.update_one.return_value = mock_result
        mock_collection.find_one.return_value = {"_id": ObjectId(TEST_RECIPE_ID), "title": "Updated"}
        mock_get_collection.return_value = mock_collection

        from src.routers.recipes import update_recipe
        result = await update_recipe(UpdateRecipeRequest(title="Updated"), recipe_id=TEST_RECIPE_ID)

        assert result.success is True
        assert result.data["title"] == "Updated"

    async def test_update_recipe_no_fields_provided(self):
        from src.routers.recipes import update_recipe
        response = await update_recipe(UpdateRecipeRequest(), recipe_id=TEST_RECIPE_ID)

        assert isinstance(response, JSONResponse)
        assert response.status_code == 400
        body = json.loads(response.body.decode())
        assert body["error"]["code"] == "NO_UPDATE_DATA"

    @patch('src.routers.recipes.get_collection')
    async def test_update_recipe_not_found(self, mock_get_collection):
        mock_collection = AsyncMock()
        mock_result = MagicMock()
        mock_result.matched_count = 0
        mock_collection.update_one.return_value = mock_result
        mock_get_collection.return_value = mock_collection

        from src.routers.recipes import update_recipe
        response = await update_recipe(UpdateRecipeRequest(title="Updated"), recipe_id=TEST_RECIPE_ID)

        assert isinstance(response, JSONResponse)
        assert response.status_code == 404
        body = json.loads(response.body.decode())
        assert body["error"]["code"] == "RECIPE_NOT_FOUND"

    async def test_update_recipe_invalid_id(self):
        from src.routers.recipes import update_recipe
        response = await update_recipe(UpdateRecipeRequest(title="Updated"), recipe_id=INVALID_RECIPE_ID)

        assert isinstance(response, JSONResponse)
        assert response.status_code == 400
        body = json.loads(response.body.decode())
        assert body["error"]["code"] == "INVALID_OBJECT_ID"


@pytest.mark.unit
@pytest.mark.asyncio
class TestUpdateRecipesBatch:
    """Tests for PATCH /api/recipes/ endpoint."""

    @patch('src.routers.recipes.get_collection')
    async def test_update_recipes_batch_success(self, mock_get_collection):
        mock_collection = AsyncMock()
        mock_result = MagicMock()
        mock_result.matched_count = 3
        mock_result.modified_count = 3
        mock_collection.update_many.return_value = mock_result
        mock_get_collection.return_value = mock_collection

        from src.routers.recipes import update_recipes_batch
        result = await update_recipes_batch({"filter": {"cuisine": "Italian"}, "update": {"difficulty": "easy"}})

        assert result.success is True
        assert result.data["matchedCount"] == 3
        assert result.data["modifiedCount"] == 3

    async def test_update_recipes_batch_missing_filter(self):
        from src.routers.recipes import update_recipes_batch
        response = await update_recipes_batch({"update": {"difficulty": "easy"}})

        assert isinstance(response, JSONResponse)
        assert response.status_code == 400
        body = json.loads(response.body.decode())
        assert body["error"]["code"] == "MISSING_FILTER"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd server && pytest tests/test_recipe_routes.py::TestUpdateRecipe tests/test_recipe_routes.py::TestUpdateRecipesBatch -v`
Expected: FAIL with `ImportError`

- [ ] **Step 3: Implement the endpoints**

Update the `fastapi` import to include `Path` and `Body`:

```python
from fastapi import APIRouter, Query, Path, Body
```

Add `UpdateRecipeRequest` to the models import and `CRUD_WITH_OBJECTID_RESPONSES` to the response_docs import:

```python
from src.models.models import Recipe, CreateRecipeRequest, UpdateRecipeRequest, SuccessResponse
from src.utils.response_docs import (
    OBJECTID_VALIDATION_RESPONSES,
    DATABASE_OPERATION_RESPONSES,
    CRUD_OPERATION_RESPONSES,
    CRUD_WITH_OBJECTID_RESPONSES,
)
```

Append to `server/src/routers/recipes.py`:

```python
@router.patch(
    "/{id}",
    response_model=SuccessResponse[Recipe],
    status_code=200,
    summary="Update a single recipe by its ID.",
    responses=CRUD_WITH_OBJECTID_RESPONSES
)
async def update_recipe(
    recipe_data: UpdateRecipeRequest,
    recipe_id: str = Path(..., alias="id")
) -> SuccessResponse[Recipe]:
    recipes_collection = get_collection("recipes")

    try:
        recipe_id = ObjectId(recipe_id)
    except Exception:
        return JSONResponse(
            status_code=400,
            content=create_error_response(
                message=f"Invalid recipe_id format: {recipe_id}",
                code="INVALID_OBJECT_ID"
            )
        )

    update_dict = recipe_data.model_dump(exclude_unset=True, exclude_none=True)
    if not update_dict:
        return JSONResponse(
            status_code=400,
            content=create_error_response(
                message="No valid fields provided for update.",
                code="NO_UPDATE_DATA"
            )
        )

    try:
        result = await recipes_collection.update_one({"_id": recipe_id}, {"$set": update_dict})
    except Exception:
        return server_error_response(
            "An error occurred while updating the recipe.",
            "DATABASE_ERROR",
            log_context="update_recipe",
        )

    if result.matched_count == 0:
        return JSONResponse(
            status_code=404,
            content=create_error_response(
                message=f"No recipe with that _id was found: {recipe_id}",
                code="RECIPE_NOT_FOUND"
            )
        )

    updated_recipe = await recipes_collection.find_one({"_id": recipe_id})
    updated_recipe["_id"] = str(updated_recipe["_id"])
    return create_success_response(updated_recipe, f"Recipe updated successfully. Modified {len(update_dict)} fields.")


@router.patch(
    "/",
    response_model=SuccessResponse[dict],
    status_code=200,
    summary="Batch update recipes matching the given filter.",
    responses=CRUD_OPERATION_RESPONSES
)
async def update_recipes_batch(request_body: dict = Body(...)) -> SuccessResponse[dict]:
    recipes_collection = get_collection("recipes")

    filter_data = request_body.get("filter", {})
    update_data = request_body.get("update", {})

    if not filter_data or not update_data:
        return JSONResponse(
            status_code=400,
            content=create_error_response(
                message="Both filter and update objects are required",
                code="MISSING_FILTER"
            )
        )

    try:
        result = await recipes_collection.update_many(filter_data, {"$set": update_data})
    except Exception:
        return server_error_response(
            "An error occurred while updating recipes.",
            "DATABASE_ERROR",
            log_context="update_recipes_batch",
        )

    return create_success_response({
        "matchedCount": result.matched_count,
        "modifiedCount": result.modified_count
    }, f"Update operation completed. Matched {result.matched_count} recipe(s), modified {result.modified_count} recipe(s).")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd server && pytest tests/test_recipe_routes.py -v`
Expected: 20 passed

- [ ] **Step 5: Commit**

```bash
git add server/src/routers/recipes.py server/tests/test_recipe_routes.py
git commit -m "Add PATCH /api/recipes/{id} and batch update endpoints"
```

---

### Task 10: DELETE endpoints (single, atomic find-and-delete, batch)

**Files:**
- Modify: `server/src/routers/recipes.py`
- Modify: `server/tests/test_recipe_routes.py`

**Interfaces:**
- Consumes: everything from prior router tasks.
- Produces: `delete_recipe_by_id(id)`, `find_and_delete_recipe(id)`, `delete_recipes_batch(request_body)` route handlers.

- [ ] **Step 1: Write the failing tests**

Append to `server/tests/test_recipe_routes.py`:

```python
@pytest.mark.unit
@pytest.mark.asyncio
class TestDeleteRecipeById:
    """Tests for DELETE /api/recipes/{id} endpoint."""

    @patch('src.routers.recipes.get_collection')
    async def test_delete_recipe_by_id_success(self, mock_get_collection):
        mock_collection = AsyncMock()
        mock_result = MagicMock()
        mock_result.deleted_count = 1
        mock_collection.delete_one.return_value = mock_result
        mock_get_collection.return_value = mock_collection

        from src.routers.recipes import delete_recipe_by_id
        result = await delete_recipe_by_id(TEST_RECIPE_ID)

        assert result.success is True
        assert result.data["deletedCount"] == 1

    @patch('src.routers.recipes.get_collection')
    async def test_delete_recipe_by_id_not_found(self, mock_get_collection):
        mock_collection = AsyncMock()
        mock_result = MagicMock()
        mock_result.deleted_count = 0
        mock_collection.delete_one.return_value = mock_result
        mock_get_collection.return_value = mock_collection

        from src.routers.recipes import delete_recipe_by_id
        response = await delete_recipe_by_id(TEST_RECIPE_ID)

        assert isinstance(response, JSONResponse)
        assert response.status_code == 404
        body = json.loads(response.body.decode())
        assert body["error"]["code"] == "RECIPE_NOT_FOUND"

    async def test_delete_recipe_by_id_invalid_id(self):
        from src.routers.recipes import delete_recipe_by_id
        response = await delete_recipe_by_id(INVALID_RECIPE_ID)

        assert isinstance(response, JSONResponse)
        assert response.status_code == 400


@pytest.mark.unit
@pytest.mark.asyncio
class TestFindAndDeleteRecipe:
    """Tests for DELETE /api/recipes/{id}/find-and-delete endpoint."""

    @patch('src.routers.recipes.get_collection')
    async def test_find_and_delete_recipe_success(self, mock_get_collection):
        mock_collection = AsyncMock()
        mock_collection.find_one_and_delete.return_value = {"_id": ObjectId(TEST_RECIPE_ID), "title": "Deleted Recipe"}
        mock_get_collection.return_value = mock_collection

        from src.routers.recipes import find_and_delete_recipe
        result = await find_and_delete_recipe(TEST_RECIPE_ID)

        assert result.success is True
        assert result.data["title"] == "Deleted Recipe"

    @patch('src.routers.recipes.get_collection')
    async def test_find_and_delete_recipe_not_found(self, mock_get_collection):
        mock_collection = AsyncMock()
        mock_collection.find_one_and_delete.return_value = None
        mock_get_collection.return_value = mock_collection

        from src.routers.recipes import find_and_delete_recipe
        response = await find_and_delete_recipe(TEST_RECIPE_ID)

        assert isinstance(response, JSONResponse)
        assert response.status_code == 404


@pytest.mark.unit
@pytest.mark.asyncio
class TestDeleteRecipesBatch:
    """Tests for DELETE /api/recipes/ endpoint."""

    @patch('src.routers.recipes.get_collection')
    async def test_delete_recipes_batch_success(self, mock_get_collection):
        mock_collection = AsyncMock()
        mock_result = MagicMock()
        mock_result.deleted_count = 3
        mock_collection.delete_many.return_value = mock_result
        mock_get_collection.return_value = mock_collection

        from src.routers.recipes import delete_recipes_batch
        result = await delete_recipes_batch({"filter": {"cuisine": "Italian"}})

        assert result.success is True
        assert result.data["deletedCount"] == 3

    async def test_delete_recipes_batch_missing_filter(self):
        from src.routers.recipes import delete_recipes_batch
        response = await delete_recipes_batch({})

        assert isinstance(response, JSONResponse)
        assert response.status_code == 400
        body = json.loads(response.body.decode())
        assert body["error"]["code"] == "MISSING_FILTER"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd server && pytest tests/test_recipe_routes.py::TestDeleteRecipeById tests/test_recipe_routes.py::TestFindAndDeleteRecipe tests/test_recipe_routes.py::TestDeleteRecipesBatch -v`
Expected: FAIL with `ImportError`

- [ ] **Step 3: Implement the endpoints**

Append to `server/src/routers/recipes.py`:

```python
@router.delete(
    "/{id}",
    response_model=SuccessResponse[dict],
    status_code=200,
    summary="Delete a single recipe by its ID.",
    responses=OBJECTID_VALIDATION_RESPONSES
)
async def delete_recipe_by_id(id: str):
    try:
        object_id = ObjectId(id)
    except errors.InvalidId:
        return JSONResponse(
            status_code=400,
            content=create_error_response(
                message=f"Invalid recipe ID format: The provided ID '{id}' is not a valid ObjectId",
                code="INVALID_OBJECT_ID"
            )
        )

    recipes_collection = get_collection("recipes")
    try:
        result = await recipes_collection.delete_one({"_id": object_id})
    except Exception:
        return server_error_response(
            "Database error occurred.",
            "DATABASE_ERROR",
            log_context="delete_recipe_by_id",
        )

    if result.deleted_count == 0:
        return JSONResponse(
            status_code=404,
            content=create_error_response(
                message=f"No recipe found with ID: {id}",
                code="RECIPE_NOT_FOUND"
            )
        )

    return create_success_response({"deletedCount": result.deleted_count}, "Recipe deleted successfully")


@router.delete(
    "/{id}/find-and-delete",
    response_model=SuccessResponse[Recipe],
    status_code=200,
    summary="Find and delete a recipe in a single atomic operation.",
    responses=OBJECTID_VALIDATION_RESPONSES
)
async def find_and_delete_recipe(id: str):
    try:
        object_id = ObjectId(id)
    except errors.InvalidId:
        return JSONResponse(
            status_code=400,
            content=create_error_response(
                message=f"Invalid recipe ID format: The provided ID '{id}' is not a valid ObjectId",
                code="INVALID_OBJECT_ID"
            )
        )

    recipes_collection = get_collection("recipes")
    try:
        deleted_recipe = await recipes_collection.find_one_and_delete({"_id": object_id})
    except Exception:
        return server_error_response(
            "Database error occurred.",
            "DATABASE_ERROR",
            log_context="find_and_delete_recipe",
        )

    if deleted_recipe is None:
        return JSONResponse(
            status_code=404,
            content=create_error_response(
                message=f"No recipe found with ID: {id}",
                code="RECIPE_NOT_FOUND"
            )
        )

    deleted_recipe["_id"] = str(deleted_recipe["_id"])
    return create_success_response(deleted_recipe, "Recipe found and deleted successfully")


@router.delete(
    "/",
    response_model=SuccessResponse[dict],
    status_code=200,
    summary="Delete multiple recipes matching the given filter.",
    responses=CRUD_OPERATION_RESPONSES
)
async def delete_recipes_batch(request_body: dict = Body(...)) -> SuccessResponse[dict]:
    recipes_collection = get_collection("recipes")
    filter_data = request_body.get("filter", {})

    if not filter_data:
        return JSONResponse(
            status_code=400,
            content=create_error_response(
                message="Filter object is required and cannot be empty.",
                code="MISSING_FILTER"
            )
        )

    try:
        result = await recipes_collection.delete_many(filter_data)
    except Exception:
        return server_error_response(
            "An error occurred while deleting recipes.",
            "DATABASE_ERROR",
            log_context="delete_recipes_batch",
        )

    return create_success_response({"deletedCount": result.deleted_count}, f"Delete operation completed. Removed {result.deleted_count} recipes.")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd server && pytest tests/test_recipe_routes.py -v`
Expected: 27 passed

- [ ] **Step 5: Commit**

```bash
git add server/src/routers/recipes.py server/tests/test_recipe_routes.py
git commit -m "Add DELETE endpoints: single, find-and-delete, and batch"
```

---

### Task 11: GET /api/recipes/cuisines

**Files:**
- Modify: `server/src/routers/recipes.py` (insert **above** `get_recipe_by_id`)
- Modify: `server/tests/test_recipe_routes.py`

**Interfaces:**
- Consumes: `distinct()` on the `recipes` collection.
- Produces: `get_distinct_cuisines()` route handler.

FastAPI matches routes in the order they're defined. `/cuisines` must be registered **before** `/{id}` in the file, or a request to `/api/recipes/cuisines` will be captured by the `{id}` path parameter instead.

- [ ] **Step 1: Write the failing test**

Append to `server/tests/test_recipe_routes.py`:

```python
@pytest.mark.unit
@pytest.mark.asyncio
class TestGetDistinctCuisines:
    """Tests for GET /api/recipes/cuisines endpoint."""

    @patch('src.routers.recipes.get_collection')
    async def test_get_distinct_cuisines_returns_sorted_list(self, mock_get_collection):
        mock_collection = AsyncMock()
        mock_collection.distinct.return_value = ["Mexican", "Italian", None, "", "Italian"]
        mock_get_collection.return_value = mock_collection

        from src.routers.recipes import get_distinct_cuisines
        result = await get_distinct_cuisines()

        assert result.success is True
        assert result.data == ["Italian", "Italian", "Mexican"]

    @patch('src.routers.recipes.get_collection')
    async def test_get_distinct_cuisines_database_error(self, mock_get_collection):
        mock_collection = AsyncMock()
        mock_collection.distinct.side_effect = Exception("boom")
        mock_get_collection.return_value = mock_collection

        from src.routers.recipes import get_distinct_cuisines
        response = await get_distinct_cuisines()

        assert isinstance(response, JSONResponse)
        assert response.status_code == 500
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd server && pytest tests/test_recipe_routes.py::TestGetDistinctCuisines -v`
Expected: FAIL with `ImportError`

- [ ] **Step 3: Insert the endpoint above `get_recipe_by_id`**

In `server/src/routers/recipes.py`, insert this function immediately before the `@router.get("/{id}", ...)` route (i.e., right after `router = APIRouter()` and its imports, not at the end of the file):

```python
@router.get(
    "/cuisines",
    response_model=SuccessResponse[List[str]],
    status_code=200,
    summary="Retrieve all distinct cuisines from the recipes collection.",
    responses=DATABASE_OPERATION_RESPONSES
)
async def get_distinct_cuisines():
    recipes_collection = get_collection("recipes")

    try:
        cuisines = await recipes_collection.distinct("cuisine")
    except Exception:
        return server_error_response(
            "Database error occurred.",
            "DATABASE_ERROR",
            log_context="get_distinct_cuisines",
        )

    valid_cuisines = sorted([c for c in cuisines if isinstance(c, str) and len(c) > 0])
    return create_success_response(valid_cuisines, f"Found {len(valid_cuisines)} distinct cuisines")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd server && pytest tests/test_recipe_routes.py -v`
Expected: 29 passed

- [ ] **Step 5: Commit**

```bash
git add server/src/routers/recipes.py server/tests/test_recipe_routes.py
git commit -m "Add GET /api/recipes/cuisines endpoint"
```

---

### Task 12: POST /api/recipes/{id}/reviews (nested resource, denormalized rating)

**Files:**
- Modify: `server/src/routers/recipes.py`
- Modify: `server/tests/test_recipe_routes.py`

**Interfaces:**
- Consumes: `CreateReviewRequest` (Task 3), `datetime`/`timezone`.
- Produces: `create_review(id, review)` route handler. This is the first endpoint to touch the `reviews` collection, and the first to write `averageRating`/`reviewCount` back onto a `recipes` document — a pattern not present in the reference project, since `sample_mflix`'s `comments` collection is read-only from the API's perspective.

- [ ] **Step 1: Write the failing tests**

Append to `server/tests/test_recipe_routes.py`:

```python
from src.models.models import CreateReviewRequest


@pytest.mark.unit
@pytest.mark.asyncio
class TestCreateReview:
    """Tests for POST /api/recipes/{id}/reviews endpoint."""

    def _mock_collections(self, recipe=None, insert_result=None, created_review=None, stats=None):
        mock_recipes = AsyncMock()
        mock_recipes.find_one.return_value = recipe

        mock_reviews = AsyncMock()
        mock_reviews.insert_one.return_value = insert_result
        mock_reviews.find_one.return_value = created_review

        mock_cursor = AsyncMock()
        mock_cursor.to_list.return_value = stats or []
        mock_reviews.aggregate.return_value = mock_cursor

        def side_effect(name):
            return mock_recipes if name == "recipes" else mock_reviews

        return mock_recipes, mock_reviews, side_effect

    @patch('src.routers.recipes.get_collection')
    async def test_create_review_success(self, mock_get_collection):
        recipe = {"_id": ObjectId(TEST_RECIPE_ID), "title": "Test Recipe"}
        insert_result = MagicMock()
        insert_result.inserted_id = ObjectId("507f1f77bcf86cd799439099")
        created_review = {
            "_id": ObjectId("507f1f77bcf86cd799439099"),
            "recipe_id": ObjectId(TEST_RECIPE_ID),
            "reviewerName": "Alex",
            "rating": 5,
            "comment": "Great!",
        }
        stats = [{"averageRating": 5.0, "reviewCount": 1}]

        mock_recipes, mock_reviews, side_effect = self._mock_collections(
            recipe=recipe, insert_result=insert_result, created_review=created_review, stats=stats
        )
        mock_get_collection.side_effect = side_effect

        from src.routers.recipes import create_review
        result = await create_review(TEST_RECIPE_ID, CreateReviewRequest(reviewerName="Alex", rating=5, comment="Great!"))

        assert result.success is True
        assert result.data["reviewerName"] == "Alex"
        mock_recipes.update_one.assert_called_once()
        update_call_kwargs = mock_recipes.update_one.call_args[0][1]
        assert update_call_kwargs["$set"]["averageRating"] == 5.0
        assert update_call_kwargs["$set"]["reviewCount"] == 1

    @patch('src.routers.recipes.get_collection')
    async def test_create_review_recipe_not_found(self, mock_get_collection):
        mock_recipes, mock_reviews, side_effect = self._mock_collections(recipe=None)
        mock_get_collection.side_effect = side_effect

        from src.routers.recipes import create_review
        response = await create_review(TEST_RECIPE_ID, CreateReviewRequest(reviewerName="Alex", rating=5))

        assert isinstance(response, JSONResponse)
        assert response.status_code == 404
        body = json.loads(response.body.decode())
        assert body["error"]["code"] == "RECIPE_NOT_FOUND"

    async def test_create_review_invalid_recipe_id(self):
        from src.routers.recipes import create_review
        response = await create_review(INVALID_RECIPE_ID, CreateReviewRequest(reviewerName="Alex", rating=5))

        assert isinstance(response, JSONResponse)
        assert response.status_code == 400
        body = json.loads(response.body.decode())
        assert body["error"]["code"] == "INVALID_OBJECT_ID"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd server && pytest tests/test_recipe_routes.py::TestCreateReview -v`
Expected: FAIL with `ImportError`

- [ ] **Step 3: Implement the endpoint**

Add `from datetime import datetime, timezone` and `CreateReviewRequest` to the top of `server/src/routers/recipes.py`:

```python
from datetime import datetime, timezone
from src.models.models import Recipe, CreateRecipeRequest, UpdateRecipeRequest, CreateReviewRequest, SuccessResponse
```

Append to `server/src/routers/recipes.py`:

```python
@router.post(
    "/{id}/reviews",
    status_code=201,
    summary="Add a review to a recipe.",
    responses=OBJECTID_VALIDATION_RESPONSES
)
async def create_review(id: str, review: CreateReviewRequest):
    try:
        recipe_object_id = ObjectId(id)
    except errors.InvalidId:
        return JSONResponse(
            status_code=400,
            content=create_error_response(
                message=f"The provided ID '{id}' is not a valid ObjectId",
                code="INVALID_OBJECT_ID"
            )
        )

    recipes_collection = get_collection("recipes")
    reviews_collection = get_collection("reviews")

    try:
        recipe = await recipes_collection.find_one({"_id": recipe_object_id})
    except Exception:
        return server_error_response(
            "Database error occurred.",
            "DATABASE_ERROR",
            log_context="create_review_lookup_recipe",
        )

    if recipe is None:
        return JSONResponse(
            status_code=404,
            content=create_error_response(
                message=f"No recipe found with ID: {id}",
                code="RECIPE_NOT_FOUND"
            )
        )

    review_doc = review.model_dump()
    review_doc["recipe_id"] = recipe_object_id
    review_doc["date"] = datetime.now(timezone.utc)

    try:
        result = await reviews_collection.insert_one(review_doc)
    except Exception:
        return server_error_response(
            "Database error occurred.",
            "DATABASE_ERROR",
            log_context="create_review_insert",
        )

    # Recompute the recipe's denormalized averageRating/reviewCount so that
    # GET /api/recipes/ can filter by minRating without a $lookup on every read.
    stats_pipeline = [
        {"$match": {"recipe_id": recipe_object_id}},
        {"$group": {"_id": None, "averageRating": {"$avg": "$rating"}, "reviewCount": {"$sum": 1}}}
    ]
    stats_cursor = await reviews_collection.aggregate(stats_pipeline)
    stats = await stats_cursor.to_list(length=None)

    if stats:
        await recipes_collection.update_one(
            {"_id": recipe_object_id},
            {"$set": {
                "averageRating": round(stats[0]["averageRating"], 2),
                "reviewCount": stats[0]["reviewCount"]
            }}
        )

    created_review = await reviews_collection.find_one({"_id": result.inserted_id})
    created_review["_id"] = str(created_review["_id"])
    created_review["recipe_id"] = str(created_review["recipe_id"])

    return create_success_response(created_review, "Review added successfully")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd server && pytest tests/test_recipe_routes.py -v`
Expected: 32 passed

- [ ] **Step 5: Commit**

```bash
git add server/src/routers/recipes.py server/tests/test_recipe_routes.py
git commit -m "Add POST /api/recipes/{id}/reviews with denormalized rating recompute"
```

---

### Task 13: Aggregations — byCuisine and topIngredients

**Files:**
- Modify: `server/src/routers/recipes.py`
- Modify: `server/tests/test_recipe_routes.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: `aggregate_recipes_by_cuisine()`, `aggregate_top_ingredients(limit)`, and the shared helper `execute_aggregation(pipeline) -> list`, reused by Task 14, 15, and 16.

`byCuisine` groups directly on the `recipes` collection's denormalized `averageRating` field rather than `$lookup`-ing into `reviews` on every request — the same pattern the reference project uses for `reportingByYear` (grouping on `imdb.rating`, which is embedded on the movie document, not looked up). The `$lookup` pattern is covered by Task 14 instead.

- [ ] **Step 1: Write the failing tests**

Append to `server/tests/test_recipe_routes.py`:

```python
@pytest.mark.unit
@pytest.mark.asyncio
class TestAggregateByCuisine:
    """Tests for GET /api/recipes/aggregations/byCuisine endpoint."""

    @patch('src.routers.recipes.get_collection')
    async def test_aggregate_by_cuisine_success(self, mock_get_collection):
        mock_collection = AsyncMock()
        mock_cursor = AsyncMock()
        mock_cursor.to_list.return_value = [
            {"cuisine": "Italian", "recipeCount": 5, "averageRating": 4.2},
            {"cuisine": "Mexican", "recipeCount": 3, "averageRating": 3.8},
        ]
        mock_collection.aggregate.return_value = mock_cursor
        mock_get_collection.return_value = mock_collection

        from src.routers.recipes import aggregate_recipes_by_cuisine
        result = await aggregate_recipes_by_cuisine()

        assert result.success is True
        assert len(result.data) == 2
        assert result.data[0]["cuisine"] == "Italian"

    @patch('src.routers.recipes.get_collection')
    async def test_aggregate_by_cuisine_database_error(self, mock_get_collection):
        mock_collection = AsyncMock()
        mock_collection.aggregate.side_effect = Exception("boom")
        mock_get_collection.return_value = mock_collection

        from src.routers.recipes import aggregate_recipes_by_cuisine
        response = await aggregate_recipes_by_cuisine()

        assert isinstance(response, JSONResponse)
        assert response.status_code == 500


@pytest.mark.unit
@pytest.mark.asyncio
class TestAggregateTopIngredients:
    """Tests for GET /api/recipes/aggregations/topIngredients endpoint."""

    @patch('src.routers.recipes.get_collection')
    async def test_aggregate_top_ingredients_success(self, mock_get_collection):
        mock_collection = AsyncMock()
        mock_cursor = AsyncMock()
        mock_cursor.to_list.return_value = [
            {"ingredient": "salt", "recipeCount": 20},
            {"ingredient": "garlic", "recipeCount": 15},
        ]
        mock_collection.aggregate.return_value = mock_cursor
        mock_get_collection.return_value = mock_collection

        from src.routers.recipes import aggregate_top_ingredients
        result = await aggregate_top_ingredients()

        assert result.success is True
        assert result.data[0]["ingredient"] == "salt"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd server && pytest tests/test_recipe_routes.py::TestAggregateByCuisine tests/test_recipe_routes.py::TestAggregateTopIngredients -v`
Expected: FAIL with `ImportError`

- [ ] **Step 3: Implement the endpoints and shared helper**

Append to `server/src/routers/recipes.py`:

```python
@router.get(
    "/aggregations/byCuisine",
    response_model=SuccessResponse[List[dict]],
    status_code=200,
    summary="Aggregate recipes by cuisine with average rating and recipe count.",
    responses=DATABASE_OPERATION_RESPONSES
)
async def aggregate_recipes_by_cuisine():
    pipeline = [
        {"$match": {"cuisine": {"$exists": True, "$ne": None}}},
        {"$group": {
            "_id": "$cuisine",
            "recipeCount": {"$sum": 1},
            "averageRating": {"$avg": "$averageRating"}
        }},
        {"$project": {
            "cuisine": "$_id",
            "recipeCount": 1,
            "averageRating": {"$round": ["$averageRating", 2]},
            "_id": 0
        }},
        {"$sort": {"recipeCount": -1}}
    ]

    try:
        results = await execute_aggregation(pipeline)
    except Exception:
        return server_error_response(
            "Database error occurred during aggregation.",
            "DATABASE_ERROR",
            log_context="aggregate_recipes_by_cuisine",
        )

    return create_success_response(results, f"Aggregated statistics for {len(results)} cuisines")


@router.get(
    "/aggregations/topIngredients",
    response_model=SuccessResponse[List[dict]],
    status_code=200,
    summary="Aggregate the most frequently used ingredients across all recipes.",
    responses=DATABASE_OPERATION_RESPONSES
)
async def aggregate_top_ingredients(limit: int = Query(default=20, ge=1, le=100)):
    pipeline = [
        {"$match": {"ingredients": {"$exists": True, "$ne": None, "$ne": []}}},
        {"$unwind": "$ingredients"},
        {"$match": {"ingredients": {"$ne": None, "$ne": ""}}},
        {"$group": {"_id": "$ingredients", "recipeCount": {"$sum": 1}}},
        {"$sort": {"recipeCount": -1}},
        {"$limit": limit},
        {"$project": {"ingredient": "$_id", "recipeCount": 1, "_id": 0}}
    ]

    try:
        results = await execute_aggregation(pipeline)
    except Exception:
        return server_error_response(
            "Database error occurred during aggregation.",
            "DATABASE_ERROR",
            log_context="aggregate_top_ingredients",
        )

    return create_success_response(results, f"Found {len(results)} distinct ingredients")


#------------------------------------
# Helper Functions
#------------------------------------

async def execute_aggregation(pipeline: list) -> list:
    """Run an aggregation pipeline against the recipes collection and collect all results."""
    recipes_collection = get_collection("recipes")
    cursor = await recipes_collection.aggregate(pipeline)
    return await cursor.to_list(length=None)


async def execute_aggregation_on_collection(collection, pipeline: list) -> list:
    """Run an aggregation pipeline against an arbitrary collection and collect all results."""
    cursor = await collection.aggregate(pipeline)
    return await cursor.to_list(length=None)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd server && pytest tests/test_recipe_routes.py -v`
Expected: 36 passed

- [ ] **Step 5: Commit**

```bash
git add server/src/routers/recipes.py server/tests/test_recipe_routes.py
git commit -m "Add byCuisine and topIngredients aggregation endpoints"
```

---

### Task 14: Aggregation — recentReviews ($lookup)

**Files:**
- Modify: `server/src/routers/recipes.py`
- Modify: `server/tests/test_recipe_routes.py`

**Interfaces:**
- Consumes: `execute_aggregation` (Task 13).
- Produces: `aggregate_recipes_recent_reviews(limit, recipe_id)` route handler — the `$lookup` teaching example, joining `recipes` with `reviews`.

- [ ] **Step 1: Write the failing tests**

Append to `server/tests/test_recipe_routes.py`:

```python
@pytest.mark.unit
@pytest.mark.asyncio
class TestAggregateRecentReviews:
    """Tests for GET /api/recipes/aggregations/recentReviews endpoint."""

    @patch('src.routers.recipes.get_collection')
    async def test_aggregate_recent_reviews_success(self, mock_get_collection):
        mock_collection = AsyncMock()
        mock_cursor = AsyncMock()
        mock_cursor.to_list.return_value = [
            {
                "_id": ObjectId(TEST_RECIPE_ID),
                "title": "Test Recipe",
                "cuisine": "Italian",
                "recentReviews": [{"reviewerName": "Alex", "rating": 5, "comment": "Great", "date": "2026-01-01"}],
                "totalReviews": 1
            }
        ]
        mock_collection.aggregate.return_value = mock_cursor
        mock_get_collection.return_value = mock_collection

        from src.routers.recipes import aggregate_recipes_recent_reviews
        result = await aggregate_recipes_recent_reviews()

        assert result.success is True
        assert result.data[0]["_id"] == TEST_RECIPE_ID
        assert result.data[0]["totalReviews"] == 1

    async def test_aggregate_recent_reviews_invalid_recipe_id(self):
        from src.routers.recipes import aggregate_recipes_recent_reviews
        response = await aggregate_recipes_recent_reviews(recipe_id=INVALID_RECIPE_ID)

        assert isinstance(response, JSONResponse)
        assert response.status_code == 400
        body = json.loads(response.body.decode())
        assert body["error"]["code"] == "INVALID_OBJECT_ID"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd server && pytest tests/test_recipe_routes.py::TestAggregateRecentReviews -v`
Expected: FAIL with `ImportError`

- [ ] **Step 3: Implement the endpoint**

Add `Optional` to the `typing` import at the top of the file:

```python
from typing import List, Optional
```

Append to `server/src/routers/recipes.py`:

```python
@router.get(
    "/aggregations/recentReviews",
    response_model=SuccessResponse[List[dict]],
    status_code=200,
    summary="Aggregate recipes with their most recent reviews.",
    responses=DATABASE_OPERATION_RESPONSES
)
async def aggregate_recipes_recent_reviews(
    limit: int = Query(default=10, ge=1, le=50),
    recipe_id: str = Query(default=None)
):
    pipeline: list = [{"$match": {"title": {"$exists": True}}}]

    if recipe_id:
        try:
            object_id = ObjectId(recipe_id)
            pipeline[0]["$match"]["_id"] = object_id
        except Exception:
            return JSONResponse(
                status_code=400,
                content=create_error_response(
                    message="The provided recipe_id is not a valid ObjectId",
                    code="INVALID_OBJECT_ID"
                )
            )

    pipeline.extend([
        # Join each recipe with all of its reviews (like a SQL LEFT JOIN)
        {"$lookup": {"from": "reviews", "localField": "_id", "foreignField": "recipe_id", "as": "reviews"}},
        # Only keep recipes that have at least one review
        {"$match": {"reviews": {"$ne": []}}},
        {"$addFields": {
            "recentReviews": {"$slice": [{"$sortArray": {"input": "$reviews", "sortBy": {"date": -1}}}, limit]},
            "mostRecentReviewDate": {"$max": "$reviews.date"}
        }},
        {"$sort": {"mostRecentReviewDate": -1}},
        {"$limit": 50 if recipe_id else 20},
        {"$project": {
            "title": 1,
            "cuisine": 1,
            "_id": 1,
            "recentReviews": {
                "$map": {
                    "input": "$recentReviews",
                    "as": "review",
                    "in": {
                        "reviewerName": "$$review.reviewerName",
                        "rating": "$$review.rating",
                        "comment": "$$review.comment",
                        "date": "$$review.date"
                    }
                }
            },
            "totalReviews": {"$size": "$reviews"}
        }}
    ])

    try:
        results = await execute_aggregation(pipeline)
    except Exception:
        return server_error_response(
            "Database error occurred during aggregation.",
            "DATABASE_ERROR",
            log_context="aggregate_recipes_recent_reviews",
        )

    for result in results:
        result["_id"] = str(result["_id"])

    total_reviews = sum(r.get("totalReviews", 0) for r in results)
    return create_success_response(results, f"Found {total_reviews} reviews from {len(results)} recipe(s)")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd server && pytest tests/test_recipe_routes.py -v`
Expected: 38 passed

- [ ] **Step 5: Commit**

```bash
git add server/src/routers/recipes.py server/tests/test_recipe_routes.py
git commit -m "Add recentReviews aggregation endpoint with $lookup"
```

---

### Task 15: GET /api/recipes/search (Atlas Search)

**Files:**
- Modify: `server/src/routers/recipes.py` (insert **above** `get_recipe_by_id`)
- Modify: `server/tests/test_recipe_routes.py`

**Interfaces:**
- Consumes: `SearchRecipesResponse` (Task 3), `SEARCH_ENDPOINT_RESPONSES` (Task 4), `execute_aggregation` (Task 13).
- Produces: `search_recipes(...)` route handler. Won't return real matches until the Atlas Search index exists (Task 16) — these tests mock the aggregation entirely, so they don't depend on it.

Like `/cuisines`, this must be inserted **above** `/{id}` — otherwise `/api/recipes/search` gets captured by the `{id}` path parameter.

- [ ] **Step 1: Write the failing tests**

Append to `server/tests/test_recipe_routes.py`:

```python
@pytest.mark.unit
@pytest.mark.asyncio
class TestSearchRecipes:
    """Tests for GET /api/recipes/search endpoint."""

    @patch('src.routers.recipes.execute_aggregation')
    async def test_search_recipes_success(self, mock_execute_aggregation):
        mock_execute_aggregation.return_value = [{
            "totalCount": [{"count": 1}],
            "results": [{"_id": ObjectId(TEST_RECIPE_ID), "title": "Garlic Pasta", "description": "Garlicky and rich"}]
        }]

        from src.routers.recipes import search_recipes
        result = await search_recipes(description="garlic")

        assert result.success is True
        assert result.data.totalCount == 1
        assert result.data.recipes[0].title == "Garlic Pasta"

    async def test_search_recipes_missing_params(self):
        from src.routers.recipes import search_recipes
        response = await search_recipes()

        assert isinstance(response, JSONResponse)
        assert response.status_code == 400
        body = json.loads(response.body.decode())
        assert body["error"]["code"] == "MISSING_SEARCH_PARAMS"

    async def test_search_recipes_invalid_operator(self):
        from src.routers.recipes import search_recipes
        response = await search_recipes(description="garlic", search_operator="invalid")

        assert isinstance(response, JSONResponse)
        assert response.status_code == 400
        body = json.loads(response.body.decode())
        assert body["error"]["code"] == "INVALID_SEARCH_OPERATOR"

    @patch('src.routers.recipes.execute_aggregation')
    async def test_search_recipes_no_results(self, mock_execute_aggregation):
        mock_execute_aggregation.return_value = []

        from src.routers.recipes import search_recipes
        result = await search_recipes(description="nonexistent")

        assert result.success is True
        assert result.data.totalCount == 0
        assert result.data.recipes == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd server && pytest tests/test_recipe_routes.py::TestSearchRecipes -v`
Expected: FAIL with `ImportError`

- [ ] **Step 3: Insert the endpoint above `get_recipe_by_id`**

Add `SearchRecipesResponse` to the models import and `SEARCH_ENDPOINT_RESPONSES` to the response_docs import at the top of `server/src/routers/recipes.py`:

```python
from src.models.models import Recipe, CreateRecipeRequest, UpdateRecipeRequest, CreateReviewRequest, SearchRecipesResponse, SuccessResponse
from src.utils.response_docs import (
    OBJECTID_VALIDATION_RESPONSES,
    DATABASE_OPERATION_RESPONSES,
    CRUD_OPERATION_RESPONSES,
    CRUD_WITH_OBJECTID_RESPONSES,
    SEARCH_ENDPOINT_RESPONSES,
)
```

Insert this function above `@router.get("/{id}", ...)` (it can go right below `get_distinct_cuisines`, still above `/{id}`):

```python
@router.get(
    "/search",
    response_model=SuccessResponse[SearchRecipesResponse],
    status_code=200,
    summary="Search recipes using MongoDB Atlas Search.",
    responses=SEARCH_ENDPOINT_RESPONSES
)
async def search_recipes(
    description: Optional[str] = None,
    instructions: Optional[str] = None,
    tags: Optional[str] = None,
    limit: int = Query(default=20, ge=1, le=100),
    skip: int = Query(default=0, ge=0),
    search_operator: str = Query(default="must", alias="searchOperator")
):
    valid_operators = {"must", "should", "mustNot", "filter"}
    if search_operator not in valid_operators:
        return JSONResponse(
            status_code=400,
            content=create_error_response(
                message=f"Invalid search operator '{search_operator}'. The search operator must be one of {valid_operators}.",
                code="INVALID_SEARCH_OPERATOR"
            )
        )

    search_phrases = []
    if description is not None:
        search_phrases.append({"phrase": {"query": description, "path": "description"}})
    if instructions is not None:
        search_phrases.append({"phrase": {"query": instructions, "path": "instructions"}})
    if tags is not None:
        search_phrases.append({
            "compound": {
                "should": [
                    {"phrase": {"query": tags, "path": "tags"}},
                    {"text": {"query": tags, "path": "tags", "matchCriteria": "all",
                              "fuzzy": {"maxEdits": 1, "prefixLength": 2}}}
                ],
                "minimumShouldMatch": 1
            }
        })

    if not search_phrases:
        return JSONResponse(
            status_code=400,
            content=create_error_response(
                message="At least one search parameter must be provided.",
                code="MISSING_SEARCH_PARAMS"
            )
        )

    aggregation_pipeline = [
        {"$search": {"index": "recipeSearchIndex", "compound": {search_operator: search_phrases}}},
        {"$facet": {
            "totalCount": [{"$count": "count"}],
            "results": [
                {"$skip": skip},
                {"$limit": limit},
                {"$project": {
                    "_id": 1, "title": 1, "description": 1, "instructions": 1,
                    "cuisine": 1, "difficulty": 1, "prepTimeMinutes": 1,
                    "cookTimeMinutes": 1, "servings": 1, "ingredients": 1,
                    "tags": 1, "averageRating": 1, "reviewCount": 1
                }}
            ]
        }}
    ]

    try:
        results = await execute_aggregation(aggregation_pipeline)
    except Exception:
        return server_error_response(
            "An error occurred while performing the search.",
            "SEARCH_ERROR",
            log_context="search_recipes",
        )

    if not results:
        return create_success_response(
            SearchRecipesResponse(recipes=[], totalCount=0),
            "No recipes found matching the search criteria."
        )

    facet_result = results[0]
    total_count_array = facet_result.get("totalCount", [])
    total_count = total_count_array[0].get("count", 0) if total_count_array else 0
    recipes_data = facet_result.get("results", [])

    recipes = []
    for recipe in recipes_data:
        recipe["_id"] = str(recipe["_id"])
        recipes.append(recipe)

    return create_success_response(
        SearchRecipesResponse(recipes=recipes, totalCount=total_count),
        f"Found {total_count} recipes matching the search criteria."
    )
```

Note: `execute_aggregation` is defined later in the file (Task 13), but that's fine — Python resolves names inside a function body at call time, not at definition time, so forward references between module-level functions work.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd server && pytest tests/test_recipe_routes.py -v`
Expected: 42 passed

- [ ] **Step 5: Commit**

```bash
git add server/src/routers/recipes.py server/tests/test_recipe_routes.py
git commit -m "Add GET /api/recipes/search Atlas Search endpoint"
```

---

### Task 16: GET /api/recipes/vector-search + startup index creation

**Files:**
- Modify: `server/src/routers/recipes.py` (insert **above** `get_recipe_by_id`)
- Modify: `server/main.py`
- Modify: `server/tests/test_recipe_routes.py`

**Interfaces:**
- Consumes: `VectorSearchResult` (Task 3), `VECTOR_SEARCH_RESPONSES` (Task 4), `VoyageAuthError`/`VoyageAPIError` (Task 4), `voyage_ai_available` (Task 2), `execute_aggregation_on_collection` (Task 13).
- Produces: `vector_search_recipes(...)`, `get_embedding(...)` in `recipes.py`; `lifespan` (with `ensure_search_index`, `ensure_vector_search_index`, `ensure_standard_index`) and the Voyage exception handlers in `main.py`.

Unlike the reference project, which stores embeddings on a separate `embedded_movies` collection, this project stores each recipe's embedding directly on its own `recipes` document (`description_embedding_voyage_3_large`) — there's no reason to split it out here since every recipe gets one. Vector search runs directly against `recipes`.

- [ ] **Step 1: Write the failing tests**

Append to `server/tests/test_recipe_routes.py`:

```python
from src.utils.exceptions import VoyageAuthError, VoyageAPIError


@pytest.mark.unit
@pytest.mark.asyncio
class TestVectorSearchRecipes:
    """Tests for GET /api/recipes/vector-search endpoint."""

    @patch('src.routers.recipes.voyage_ai_available')
    async def test_vector_search_unavailable_without_api_key(self, mock_available):
        mock_available.return_value = None

        from src.routers.recipes import vector_search_recipes
        response = await vector_search_recipes(q="garlicky pasta")

        assert isinstance(response, JSONResponse)
        assert response.status_code == 503
        body = json.loads(response.body.decode())
        assert body["error"]["code"] == "SERVICE_UNAVAILABLE"

    @patch('src.routers.recipes.execute_aggregation_on_collection')
    @patch('src.routers.recipes.get_embedding')
    @patch('src.routers.recipes.voyage_ai_available')
    @patch('src.routers.recipes.get_collection')
    async def test_vector_search_success(
        self, mock_get_collection, mock_available, mock_get_embedding, mock_execute_aggregation
    ):
        mock_available.return_value = "fake-key"
        mock_get_embedding.return_value = [0.1] * 2048
        mock_get_collection.return_value = AsyncMock()
        mock_execute_aggregation.return_value = [
            {"_id": ObjectId(TEST_RECIPE_ID), "title": "Garlic Pasta", "description": "Rich and garlicky", "cuisine": "Italian", "score": 0.95}
        ]

        from src.routers.recipes import vector_search_recipes
        result = await vector_search_recipes(q="garlicky pasta")

        assert result.success is True
        assert result.data[0].title == "Garlic Pasta"
        assert result.data[0].score == 0.95

    @patch('src.routers.recipes.voyage_ai_available')
    @patch('src.routers.recipes.get_embedding')
    async def test_vector_search_propagates_voyage_auth_error(self, mock_get_embedding, mock_available):
        mock_available.return_value = "fake-key"
        mock_get_embedding.side_effect = VoyageAuthError("bad key")

        from src.routers.recipes import vector_search_recipes
        with pytest.raises(VoyageAuthError):
            await vector_search_recipes(q="garlicky pasta")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd server && pytest tests/test_recipe_routes.py::TestVectorSearchRecipes -v`
Expected: FAIL with `ImportError`

- [ ] **Step 3: Insert the endpoint above `get_recipe_by_id`**

Add these imports to the top of `server/src/routers/recipes.py`:

```python
from src.database.mongo_client import get_collection, voyage_ai_available
from src.models.models import Recipe, CreateRecipeRequest, UpdateRecipeRequest, CreateReviewRequest, SearchRecipesResponse, VectorSearchResult, SuccessResponse
from src.utils.exceptions import VoyageAuthError, VoyageAPIError
from src.utils.logger import logger
import voyageai
import voyageai.error as voyage_error
from src.utils.response_docs import (
    OBJECTID_VALIDATION_RESPONSES,
    DATABASE_OPERATION_RESPONSES,
    CRUD_OPERATION_RESPONSES,
    CRUD_WITH_OBJECTID_RESPONSES,
    SEARCH_ENDPOINT_RESPONSES,
    VECTOR_SEARCH_RESPONSES,
)
```

Insert this above `@router.get("/{id}", ...)` (below `search_recipes` is fine, as long as it's above `/{id}`):

```python
model = "voyage-3-large"
outputDimension = 2048


@router.get(
    "/vector-search",
    response_model=SuccessResponse[List[VectorSearchResult]],
    responses=VECTOR_SEARCH_RESPONSES
)
async def vector_search_recipes(
    q: str = Query(..., description="Search query to find similar recipes by description"),
    limit: int = Query(default=10, ge=1, le=50)
):
    if not voyage_ai_available():
        return JSONResponse(
            status_code=503,
            content=create_error_response(
                message="Vector search unavailable: VOYAGE_API_KEY not configured. Please add your API key to the .env file",
                code="SERVICE_UNAVAILABLE"
            )
        )

    try:
        query_embedding = get_embedding(q, input_type="query")
        recipes_collection = get_collection("recipes")

        pipeline = [
            {"$vectorSearch": {
                "index": "vector_index",
                "path": "description_embedding_voyage_3_large",
                "queryVector": query_embedding,
                "numCandidates": limit * 20,
                "limit": limit
            }},
            {"$project": {
                "_id": 1, "title": 1, "description": 1, "cuisine": 1,
                "score": {"$meta": "vectorSearchScore"}
            }}
        ]

        raw_results = await execute_aggregation_on_collection(recipes_collection, pipeline)
        for result in raw_results:
            result["_id"] = str(result["_id"])

        results = [VectorSearchResult(**doc) for doc in raw_results]

        return create_success_response(results, f"Found {len(results)} similar recipes for query: '{q}'")

    except VoyageAuthError:
        raise
    except VoyageAPIError:
        raise
    except Exception:
        return server_error_response(
            "Error performing vector search.",
            "VECTOR_SEARCH_ERROR",
            log_context="vector_search_recipes",
        )


def get_embedding(data, input_type="document", client=None):
    try:
        if client is None:
            client = voyageai.Client()
        embeddings = client.embed(
            data, model=model, output_dimension=outputDimension, input_type=input_type
        ).embeddings
        return embeddings[0]
    except voyage_error.AuthenticationError:
        logger.exception("Voyage AI authentication failed")
        raise VoyageAuthError("Invalid Voyage AI API key. Please check your VOYAGE_API_KEY in the .env file")
    except voyage_error.InvalidRequestError:
        logger.exception("Voyage AI invalid request")
        raise VoyageAPIError("Invalid request to Voyage AI API.", 400)
    except voyage_error.RateLimitError:
        logger.exception("Voyage AI rate limit")
        raise VoyageAPIError("Voyage AI API rate limit exceeded.", 429)
    except voyage_error.ServiceUnavailableError:
        logger.exception("Voyage AI service unavailable")
        raise VoyageAPIError("Voyage AI service unavailable.", 503)
    except voyage_error.VoyageError as e:
        logger.exception("Voyage AI API error")
        raise VoyageAPIError("Voyage AI API error.", getattr(e, "http_status", 500) or 500)
    except Exception:
        logger.exception("Failed to generate embedding")
        raise VoyageAPIError("Failed to generate embedding.", 500)
```

- [ ] **Step 4: Rewrite `server/main.py` to add startup index creation**

Replace the entire contents of `server/main.py`:

```python
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from src.routers import recipes
from src.database.mongo_client import db, get_collection
from src.utils.exceptions import VoyageAuthError, VoyageAPIError
from src.utils.errorResponse import create_error_response
from src.utils.logger import logger
from src.middleware.request_logging import RequestLoggingMiddleware

import os
from dotenv import load_dotenv

load_dotenv()


@asynccontextmanager
async def lifespan(app: FastAPI):
    await ensure_search_index()
    await ensure_vector_search_index()
    await ensure_standard_index()

    logger.info("=" * 60)
    logger.info(f"  Server started at http://127.0.0.1:{os.getenv('PORT', '3011')}")
    logger.info("  Documentation at /docs")
    logger.info("=" * 60)

    yield


async def ensure_search_index():
    try:
        recipes_collection = db.get_collection("recipes")
        result = await recipes_collection.list_search_indexes()
        indexes = [idx async for idx in result]
        index_names = [index["name"] for index in indexes]
        if "recipeSearchIndex" in index_names:
            return

        index_definition = {
            "mappings": {
                "dynamic": False,
                "fields": {
                    "description": {"type": "string", "analyzer": "lucene.standard"},
                    "instructions": {"type": "string", "analyzer": "lucene.standard"},
                    "tags": {"type": "string", "analyzer": "lucene.standard"}
                }
            }
        }
        await db.command({
            "createSearchIndexes": "recipes",
            "indexes": [{"name": "recipeSearchIndex", "definition": index_definition}]
        })
    except Exception as e:
        raise RuntimeError(
            f"Failed to create search index 'recipeSearchIndex': {str(e)}. "
            f"Search functionality may not work properly. "
            f"Please check your MongoDB Atlas configuration and ensure the cluster supports search indexes."
        )


async def ensure_vector_search_index():
    try:
        recipes_collection = get_collection("recipes")
        existing_indexes_cursor = await recipes_collection.list_search_indexes()
        existing_indexes = await existing_indexes_cursor.to_list(length=None)
        index_names = [index.get("name") for index in existing_indexes]

        if "vector_index" not in index_names:
            index_definition = {
                "name": "vector_index",
                "type": "vectorSearch",
                "definition": {
                    "fields": [{
                        "type": "vector",
                        "path": "description_embedding_voyage_3_large",
                        "numDimensions": 2048,
                        "similarity": "cosine"
                    }]
                }
            }
            await recipes_collection.create_search_index(index_definition)
    except Exception as e:
        raise RuntimeError(
            f"Failed to create vector search index 'vector_index': {str(e)}. "
            f"Vector search functionality will not be available. "
            f"Please check your MongoDB Atlas configuration and ensure the cluster supports vector search."
        )


async def ensure_standard_index():
    try:
        reviews_collection = db.get_collection("reviews")
        existing_indexes_cursor = await reviews_collection.list_indexes()
        existing_indexes = [index async for index in existing_indexes_cursor]
        index_names = [index.get("name") for index in existing_indexes]
        standard_index_name = "recipe_id_index"
        if standard_index_name not in index_names:
            await reviews_collection.create_index([("recipe_id", 1)], name=standard_index_name)
    except Exception as e:
        logger.warning(f"Failed to create standard index on 'reviews' collection: {str(e)}")
        logger.warning("Performance may be degraded. Please check your MongoDB configuration.")


app = FastAPI(lifespan=lifespan)


@app.exception_handler(VoyageAuthError)
async def voyage_auth_error_handler(request: Request, exc: VoyageAuthError):
    return JSONResponse(
        status_code=401,
        content=create_error_response(
            message=exc.message,
            code="VOYAGE_AUTH_ERROR",
            details="Please verify your VOYAGE_API_KEY is correct in the .env file"
        )
    )


@app.exception_handler(VoyageAPIError)
async def voyage_api_error_handler(request: Request, exc: VoyageAPIError):
    client_messages = {
        400: "Invalid vector search request.",
        429: "Vector search rate limit exceeded. Please try again later.",
        503: "Vector search service unavailable.",
    }
    return JSONResponse(
        status_code=exc.status_code,
        content=create_error_response(
            message=client_messages.get(exc.status_code, "Vector search failed."),
            code="VOYAGE_API_ERROR",
        )
    )


cors_origins = os.getenv("CORS_ORIGINS", "http://localhost:3000,http://localhost:3011").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in cors_origins],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_middleware(RequestLoggingMiddleware)

app.include_router(recipes.router, prefix="/api/recipes", tags=["recipes"])
```

- [ ] **Step 5: Run all unit tests to verify they pass**

Run: `cd server && pytest -m unit -v`
Expected: all tests pass, including `tests/test_app.py` (still lifespan-free, since it calls `app.openapi()` directly rather than issuing an ASGI request).

- [ ] **Step 6: Manually confirm the server boots and creates indexes**

```bash
uvicorn main:app --reload --port 3011
```

Watch the console — you should see log lines about index creation (or "already exists" on a second run), followed by the "Server started" banner. Check `http://localhost:3011/docs` to see all endpoints now listed, in this order: `search`, `vector-search`, `cuisines`, `{id}`, `/`, `POST /`, `POST /batch`, `PATCH /{id}`, `PATCH /`, `DELETE /{id}`, `DELETE /`, `DELETE /{id}/find-and-delete`, `POST /{id}/reviews`, and the three `aggregations/*` routes.

- [ ] **Step 7: Commit**

```bash
git add server/src/routers/recipes.py server/main.py server/tests/test_recipe_routes.py
git commit -m "Add vector search endpoint and startup index creation"
```

---

### Task 17: Seed Data Script

**Files:**
- Create: `server/scripts/seed_data.py`

**Interfaces:**
- Consumes: `get_collection`, `voyage_ai_available` (Task 2), `get_embedding` (Task 16).
- Produces: a `recipes`/`reviews` dataset in your Atlas cluster. No automated test — this is a manually-run data-generation script, verified by inspecting its printed output and querying the database directly.

- [ ] **Step 1: Write the script**

```python
# server/scripts/seed_data.py
"""
Seed script: generates synthetic recipes and reviews for local development.

Run from the server/ directory (with .venv activated and .env configured):

    python -m scripts.seed_data

This clears any existing `recipes` and `reviews` documents in the configured
database before inserting fresh data, so it is safe to re-run.
"""

import asyncio
import random
from datetime import datetime, timedelta, timezone

from src.database.mongo_client import get_collection, voyage_ai_available
from src.routers.recipes import get_embedding

CUISINES = ["Italian", "Mexican", "Japanese", "Indian", "French", "Thai", "Greek", "American"]
DIFFICULTIES = ["easy", "medium", "hard"]
TAG_POOL = ["vegetarian", "vegan", "gluten-free", "quick", "kid-friendly", "spicy", "budget", "comfort-food"]
INGREDIENT_POOL = [
    "flour", "eggs", "milk", "butter", "sugar", "salt", "pepper", "garlic",
    "onion", "olive oil", "tomato", "basil", "chicken", "rice", "soy sauce",
    "ginger", "lime", "cilantro", "cheese", "cream", "chili powder", "cumin",
]
REVIEWER_NAMES = ["Alex", "Jordan", "Sam", "Taylor", "Casey", "Morgan", "Riley", "Jamie"]

RECIPE_TITLES = [
    "Garlic Butter Pasta", "Spicy Chicken Tacos", "Miso Ramen Bowl",
    "Butter Chicken Curry", "Classic Ratatouille", "Pad Thai Noodles",
    "Greek Salad with Feta", "BBQ Pulled Pork Sliders", "Lemon Herb Roast Chicken",
    "Vegetable Stir Fry", "Margherita Pizza", "Beef Bourguignon",
    "Tom Yum Soup", "Falafel Wrap", "Shrimp Scampi",
    "Chana Masala", "Coq au Vin", "Sushi Rolls",
    "Chicken Tikka Masala", "Minestrone Soup", "Fish Tacos",
    "Mushroom Risotto", "Pho Bo", "Baba Ganoush",
    "Chicken Parmesan", "Vegetable Curry", "Beef Stroganoff",
    "Caprese Salad", "Korean Bibimbap", "Moussaka",
]


def build_recipe(title: str) -> dict:
    cuisine = random.choice(CUISINES)
    ingredients = random.sample(INGREDIENT_POOL, k=random.randint(4, 8))
    return {
        "title": title,
        "description": f"A {random.choice(DIFFICULTIES)} {cuisine} dish featuring {', '.join(ingredients[:3])}.",
        "instructions": f"1. Prep the {ingredients[0]}. 2. Cook the {ingredients[1]} until done. 3. Combine everything and serve warm.",
        "cuisine": cuisine,
        "difficulty": random.choice(DIFFICULTIES),
        "prepTimeMinutes": random.randint(5, 40),
        "cookTimeMinutes": random.randint(10, 90),
        "servings": random.randint(2, 6),
        "ingredients": ingredients,
        "tags": random.sample(TAG_POOL, k=random.randint(1, 3)),
        "averageRating": None,
        "reviewCount": 0,
        "createdAt": datetime.now(timezone.utc),
    }


def build_reviews(recipe_id) -> list[dict]:
    review_count = random.randint(0, 6)
    reviews = []
    for _ in range(review_count):
        days_ago = random.randint(0, 365)
        reviews.append({
            "recipe_id": recipe_id,
            "reviewerName": random.choice(REVIEWER_NAMES),
            "rating": random.randint(1, 5),
            "comment": random.choice([
                "Delicious, will make again!", "A bit too salty for my taste.",
                "Easy to follow and tasty.", "My family loved it.",
                "Took longer than expected but worth it.", "Great weeknight meal."
            ]),
            "date": datetime.now(timezone.utc) - timedelta(days=days_ago),
        })
    return reviews


async def seed():
    recipes_collection = get_collection("recipes")
    reviews_collection = get_collection("reviews")

    print("Clearing existing recipes and reviews...")
    await recipes_collection.delete_many({})
    await reviews_collection.delete_many({})

    embeddings_enabled = voyage_ai_available()
    if not embeddings_enabled:
        print("VOYAGE_API_KEY not configured — skipping embeddings (vector search will be unavailable).")

    inserted_recipes = 0
    inserted_reviews = 0

    for title in RECIPE_TITLES:
        recipe_doc = build_recipe(title)

        if embeddings_enabled:
            recipe_doc["description_embedding_voyage_3_large"] = get_embedding(
                recipe_doc["description"], input_type="document"
            )

        result = await recipes_collection.insert_one(recipe_doc)
        recipe_id = result.inserted_id
        inserted_recipes += 1

        reviews = build_reviews(recipe_id)
        if reviews:
            await reviews_collection.insert_many(reviews)
            inserted_reviews += len(reviews)

            ratings = [r["rating"] for r in reviews]
            await recipes_collection.update_one(
                {"_id": recipe_id},
                {"$set": {
                    "averageRating": round(sum(ratings) / len(ratings), 2),
                    "reviewCount": len(ratings),
                }}
            )

    print(f"Inserted {inserted_recipes} recipes and {inserted_reviews} reviews.")


if __name__ == "__main__":
    asyncio.run(seed())
```

- [ ] **Step 2: Run the script against your Atlas cluster**

```bash
cd server
python -m scripts.seed_data
```

Expected output: `Inserted 30 recipes and NN reviews.` (review count varies — it's randomized).

- [ ] **Step 3: Manually verify the data landed**

```bash
python -c "import asyncio; from src.database.mongo_client import get_collection; asyncio.run(get_collection('recipes').count_documents({})) "
```

If that one-liner is awkward in your shell, just hit `http://localhost:3011/api/recipes/?limit=5` with the server running and confirm you get real recipes back.

- [ ] **Step 4: Commit**

```bash
git add server/scripts/seed_data.py
git commit -m "Add synthetic data seed script for recipes and reviews"
```

---

### Task 18: Integration Test Suite

**Files:**
- Create: `server/tests/integration/__init__.py`
- Create: `server/tests/integration/conftest.py`
- Create: `server/tests/integration/test_recipe_routes_integration.py`

**Interfaces:**
- Consumes: a running Atlas cluster (via `.env`) and the seeded data from Task 17 (or the app will simply create-and-clean-up its own test documents, which works either way).
- Produces: nothing consumed by later tasks — this is the last automated test layer.

These tests start the real server in a subprocess (on a dedicated test port) and drive it over real HTTP with `httpx.AsyncClient`, avoiding `AsyncMongoClient`'s event-loop-binding quirks when run directly in-process under pytest-asyncio.

- [ ] **Step 1: Create the package marker**

```bash
touch server/tests/integration/__init__.py
```

- [ ] **Step 2: Write `server/tests/integration/conftest.py`**

```python
"""Shared fixtures for integration tests: spins up a real server in a subprocess."""

import uuid
import time
import subprocess
import sys
import os
import socket
import pytest
import pytest_asyncio
from httpx import AsyncClient


def is_port_in_use(port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(('localhost', port)) == 0


@pytest.fixture(scope="session")
def server():
    test_port = 8011

    if is_port_in_use(test_port):
        pytest.skip(f"Port {test_port} is already in use. Cannot start test server.")

    test_dir = os.path.dirname(os.path.abspath(__file__))
    server_dir = os.path.abspath(os.path.join(test_dir, "..", ".."))

    process = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "main:app", "--host", "127.0.0.1", "--port", str(test_port)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        cwd=server_dir
    )

    max_wait = 30
    start_time = time.time()
    while time.time() - start_time < max_wait:
        if is_port_in_use(test_port):
            time.sleep(0.5)
            break
        time.sleep(0.1)
    else:
        process.kill()
        pytest.fail(f"Server failed to start within {max_wait} seconds")

    yield f"http://127.0.0.1:{test_port}"

    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()


@pytest_asyncio.fixture
async def client(server):
    async with AsyncClient(base_url=server, timeout=30.0) as ac:
        yield ac


@pytest.fixture
def test_recipe_data():
    unique_id = str(uuid.uuid4())[:8]
    return {
        "title": f"Integration Test Recipe {unique_id}",
        "cuisine": "Test Cuisine",
        "difficulty": "easy",
        "description": f"A recipe created during integration testing. ID: {unique_id}",
        "ingredients": ["test-ingredient-1", "test-ingredient-2"],
        "prepTimeMinutes": 10,
    }


@pytest_asyncio.fixture
async def created_recipe(client, test_recipe_data):
    response = await client.post("/api/recipes/", json=test_recipe_data)
    assert response.status_code == 201, f"Failed to create test recipe: {response.text}"

    recipe_id = response.json()["data"]["_id"]
    yield recipe_id

    cleanup_response = await client.delete(f"/api/recipes/{recipe_id}")
    assert cleanup_response.status_code in [200, 404], f"Failed to clean up test recipe {recipe_id}"
```

- [ ] **Step 3: Write `server/tests/integration/test_recipe_routes_integration.py`**

```python
"""
Integration tests for recipe routes.

These validate the full request/response cycle against a real MongoDB Atlas
cluster. Tests create and clean up their own data.
"""

import pytest


@pytest.mark.integration
class TestRecipeCRUDIntegration:

    @pytest.mark.asyncio
    async def test_create_and_retrieve_recipe(self, client, test_recipe_data):
        create_response = await client.post("/api/recipes/", json=test_recipe_data)
        assert create_response.status_code == 201
        create_data = create_response.json()
        assert create_data["success"] is True
        assert create_data["data"]["title"] == test_recipe_data["title"]

        recipe_id = create_data["data"]["_id"]

        try:
            get_response = await client.get(f"/api/recipes/{recipe_id}")
            assert get_response.status_code == 200
            get_data = get_response.json()
            assert get_data["data"]["_id"] == recipe_id
            assert get_data["data"]["title"] == test_recipe_data["title"]
        finally:
            delete_response = await client.delete(f"/api/recipes/{recipe_id}")
            assert delete_response.status_code in [200, 404]

    @pytest.mark.asyncio
    async def test_update_recipe(self, client, created_recipe):
        update_data = {"title": "Updated Integration Test Title", "difficulty": "hard"}
        update_response = await client.patch(f"/api/recipes/{created_recipe}", json=update_data)

        assert update_response.status_code == 200
        assert update_response.json()["success"] is True

        get_response = await client.get(f"/api/recipes/{created_recipe}")
        recipe_data = get_response.json()["data"]
        assert recipe_data["title"] == update_data["title"]
        assert recipe_data["difficulty"] == update_data["difficulty"]

    @pytest.mark.asyncio
    async def test_add_review_updates_recipe_rating(self, client, created_recipe):
        review_response = await client.post(
            f"/api/recipes/{created_recipe}/reviews",
            json={"reviewerName": "Integration Tester", "rating": 4, "comment": "Solid recipe"}
        )
        assert review_response.status_code == 201

        get_response = await client.get(f"/api/recipes/{created_recipe}")
        recipe_data = get_response.json()["data"]
        assert recipe_data["averageRating"] == 4.0
        assert recipe_data["reviewCount"] == 1

    @pytest.mark.asyncio
    async def test_delete_recipe(self, client, test_recipe_data):
        create_response = await client.post("/api/recipes/", json=test_recipe_data)
        recipe_id = create_response.json()["data"]["_id"]

        delete_response = await client.delete(f"/api/recipes/{recipe_id}")
        assert delete_response.status_code == 200

        get_response = await client.get(f"/api/recipes/{recipe_id}")
        assert get_response.status_code == 404
```

- [ ] **Step 4: Run the integration suite**

Run: `cd server && pytest -m integration -v`
Expected: 4 passed (requires `.env` pointed at a real Atlas cluster; will be skipped with a clear message if port 8011 is already in use).

- [ ] **Step 5: Run the full suite one more time**

Run: `cd server && pytest -v`
Expected: all unit tests (Tasks 2–16) plus all 4 integration tests pass.

- [ ] **Step 6: Commit**

```bash
git add server/tests/integration
git commit -m "Add integration test suite against a real MongoDB Atlas cluster"
```

---

### Task 19: Project README

**Files:**
- Modify: `README.md` (the placeholder created by the initial git init)

**Interfaces:**
- Consumes: nothing.
- Produces: setup documentation for future-you (or anyone else cloning this repo).

- [ ] **Step 1: Write `README.md`**

```markdown
# Foodies API

A FastAPI + MongoDB backend for browsing recipes and reviews, built as a learning
project mirroring the architecture of MongoDB's `sample-app-python-mflix`:
CRUD, filtering/pagination, batch operations, aggregations ($group, $unwind,
$lookup), Atlas Search, and Vector Search.

## Prerequisites

- Python 3.10–3.13
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

Edit `.env` and set `MONGODB_URI` (and optionally `VOYAGE_API_KEY`).

## Seed sample data

```bash
python -m scripts.seed_data
```

## Run the server

```bash
uvicorn main:app --reload --port 3011
```

- API: http://localhost:3011/api/recipes
- Swagger UI: http://localhost:3011/docs
- ReDoc: http://localhost:3011/redoc

## Run tests

```bash
pytest -m unit -v          # fast, mocked, no database required
pytest -m integration -v   # requires the Atlas cluster from .env
pytest -v                  # everything
```

## Project structure

```
server/
├── main.py                 # FastAPI app, startup index creation, CORS, exception handlers
├── src/
│   ├── database/            # MongoDB client
│   ├── models/               # Pydantic request/response schemas
│   ├── routers/               # /api/recipes endpoints
│   ├── middleware/             # Request logging
│   └── utils/                   # Response envelopes, errors, logging, OpenAPI docs
├── scripts/seed_data.py    # Generates synthetic recipes + reviews
└── tests/                  # Unit, schema, and integration tests
```
```

- [ ] **Step 2: Commit**

```bash
git add README.md
git commit -m "Document setup, seeding, and testing instructions"
```
