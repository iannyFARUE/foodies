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
