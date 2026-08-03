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
