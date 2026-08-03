from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse
from typing import List
from src.database.mongo_client import get_collection
from src.models.models import Recipe, CreateRecipeRequest, SuccessResponse
from src.utils.successResponse import create_success_response
from src.utils.errorResponse import create_error_response, server_error_response
from src.utils.response_docs import OBJECTID_VALIDATION_RESPONSES, DATABASE_OPERATION_RESPONSES, CRUD_OPERATION_RESPONSES
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
