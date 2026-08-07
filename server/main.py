from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from src.routers import recipes
from src.database.mongo_client import db, get_collection
from src.utils.exceptions import VoyageAuthError, VoyageAPIError, APIKeyError, RateLimitExceededError
from src.utils.errorResponse import create_error_response
from src.utils.logger import logger
from src.middleware.request_logging import RequestLoggingMiddleware

import os
from dotenv import load_dotenv

load_dotenv()


@asynccontextmanager
async def lifespan(app: FastAPI):
    await ensure_collections_exist()
    await ensure_search_index()
    await ensure_vector_search_index()
    await ensure_standard_index()

    logger.info("=" * 60)
    logger.info(f"  Server started at http://127.0.0.1:{os.getenv('PORT', '3011')}")
    logger.info("  Documentation at /docs")
    logger.info("=" * 60)

    yield


async def ensure_collections_exist():
    """
    Atlas Search indexes can only be attached to a collection that already
    exists as a namespace — unlike normal writes, `createSearchIndexes`
    won't auto-create it. On a brand-new database (before the seed script
    has ever run), create empty collections up front so index creation
    below has something to attach to.
    """
    existing_names = await db.list_collection_names()
    for name in ("recipes", "reviews"):
        if name not in existing_names:
            await db.create_collection(name)


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


@app.exception_handler(APIKeyError)
async def api_key_error_handler(request: Request, exc: APIKeyError):
    return JSONResponse(
        status_code=401,
        content=create_error_response(
            message=exc.message,
            code="INVALID_API_KEY"
        )
    )


@app.exception_handler(RateLimitExceededError)
async def rate_limit_exceeded_handler(request: Request, exc: RateLimitExceededError):
    return JSONResponse(
        status_code=429,
        content=create_error_response(
            message=exc.message,
            code="RATE_LIMIT_EXCEEDED"
        ),
        headers={"Retry-After": str(int(exc.retry_after) + 1)}
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
