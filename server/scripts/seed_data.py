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

import voyageai

from src.database.mongo_client import get_collection, voyage_ai_available
from src.routers.recipes import model, outputDimension

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


def embed_descriptions(descriptions: list[str]) -> list[list[float]]:
    """
    Embed every recipe description in a single Voyage API call.

    Voyage's free tier (no payment method on file) is rate-limited to 3
    requests/minute. Calling get_embedding() once per recipe would burn
    through that in seconds; embed() natively accepts a list of texts, so
    one batched call covers the whole seed set instead of RECIPE_TITLES
    separate ones.
    """
    client = voyageai.Client()
    result = client.embed(descriptions, model=model, output_dimension=outputDimension, input_type="document")
    return result.embeddings


async def seed():
    recipes_collection = get_collection("recipes")
    reviews_collection = get_collection("reviews")

    print("Clearing existing recipes and reviews...")
    await recipes_collection.delete_many({})
    await reviews_collection.delete_many({})

    recipe_docs = [build_recipe(title) for title in RECIPE_TITLES]

    embeddings_enabled = voyage_ai_available()
    if embeddings_enabled:
        embeddings = embed_descriptions([doc["description"] for doc in recipe_docs])
        for doc, embedding in zip(recipe_docs, embeddings):
            doc["description_embedding_voyage_3_large"] = embedding
    else:
        print("VOYAGE_API_KEY not configured — skipping embeddings (vector search will be unavailable).")

    inserted_recipes = 0
    inserted_reviews = 0

    for recipe_doc in recipe_docs:
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
