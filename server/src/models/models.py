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
