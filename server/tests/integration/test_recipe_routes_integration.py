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
