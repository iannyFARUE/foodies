import re
from datetime import datetime, timezone
from fastapi import APIRouter, Query, Path, Body, Depends
from fastapi.responses import JSONResponse
from typing import List, Optional
from src.database.mongo_client import get_collection, voyage_ai_available
from src.models.models import Recipe, CreateRecipeRequest, UpdateRecipeRequest, CreateReviewRequest, SearchRecipesResponse, VectorSearchResult, SuccessResponse
from src.utils.successResponse import create_success_response
from src.utils.errorResponse import create_error_response, server_error_response
from src.utils.exceptions import VoyageAuthError, VoyageAPIError
from src.utils.logger import logger
from src.utils.query_validation import validate_recipe_filter, validate_recipe_update
from src.utils.auth import require_api_key
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
from bson import ObjectId, errors

router = APIRouter()

# Fields clients may reference in batch filter/update request bodies. Filters may
# target any real recipe field; updates exclude server-managed fields
# (averageRating/reviewCount are recomputed from reviews, not client-writable).
BATCH_FILTER_ALLOWED_FIELDS = set(Recipe.model_fields.keys()) - {"id"}
BATCH_UPDATE_ALLOWED_FIELDS = set(UpdateRecipeRequest.model_fields.keys())


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
        # Escape regex metacharacters so a client can't submit a pattern like
        # "(a+)+$" that causes catastrophic backtracking (ReDoS) against every
        # document scanned.
        filter_dict["cuisine"] = {"$regex": re.escape(cuisine), "$options": "i"}
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

    filter_error = validate_recipe_filter(filter_data, BATCH_FILTER_ALLOWED_FIELDS)
    if filter_error:
        return JSONResponse(
            status_code=400,
            content=create_error_response(message=filter_error, code="INVALID_FILTER_FIELD")
        )

    update_error = validate_recipe_update(update_data, BATCH_UPDATE_ALLOWED_FIELDS)
    if update_error:
        return JSONResponse(
            status_code=400,
            content=create_error_response(message=update_error, code="INVALID_UPDATE_FIELD")
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

    filter_error = validate_recipe_filter(filter_data, BATCH_FILTER_ALLOWED_FIELDS)
    if filter_error:
        return JSONResponse(
            status_code=400,
            content=create_error_response(message=filter_error, code="INVALID_FILTER_FIELD")
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
