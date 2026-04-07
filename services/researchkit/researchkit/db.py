import os

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

MONGODB_URL = os.getenv("MONGODB_URL", "mongodb://localhost:27017/sharelatex")

_client: AsyncIOMotorClient | None = None


def get_client() -> AsyncIOMotorClient:
    global _client
    if _client is None:
        _client = AsyncIOMotorClient(MONGODB_URL)
    return _client


def get_db() -> AsyncIOMotorDatabase:
    client = get_client()
    db_name = MONGODB_URL.rsplit("/", 1)[-1] if "/" in MONGODB_URL else "sharelatex"
    return client[db_name]


async def close_client():
    global _client
    if _client is not None:
        _client.close()
        _client = None
