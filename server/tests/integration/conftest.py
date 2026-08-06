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
from dotenv import load_dotenv

load_dotenv()


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
    headers = {"X-API-Key": os.getenv("API_KEY", "")}
    async with AsyncClient(base_url=server, timeout=30.0, headers=headers) as ac:
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
