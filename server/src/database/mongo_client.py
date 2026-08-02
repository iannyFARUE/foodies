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
    """Return the configured Voyage API key, or None if it isn't set/usable."""
    api_key = os.getenv("VOYAGE_API_KEY")
    if api_key is None or api_key == "your_voyage_api_key" or api_key.strip() == "":
        return None
    return api_key
