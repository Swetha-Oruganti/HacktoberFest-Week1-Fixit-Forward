"""Small MongoDB persistence boundary for civic reports."""
from functools import lru_cache

from django.conf import settings
from pymongo import DESCENDING, MongoClient


@lru_cache(maxsize=1)
def _client():
    return MongoClient(settings.MONGODB_URI, serverSelectionTimeoutMS=2500, connectTimeoutMS=2500)


@lru_cache(maxsize=1)
def collection():
    coll = _client()[settings.MONGODB_DATABASE]["reports"]
    coll.create_index([("created_at", DESCENDING)])
    coll.create_index([("owner_id", 1), ("created_at", DESCENDING)])
    coll.create_index("status")
    return coll


@lru_cache(maxsize=1)
def users_collection():
    coll = _client()[settings.MONGODB_DATABASE]["users"]
    coll.create_index("email_normalized", unique=True)
    return coll


@lru_cache(maxsize=1)
def sessions_collection():
    coll = _client()[settings.MONGODB_DATABASE]["sessions"]
    coll.create_index("expire_date", expireAfterSeconds=0)
    return coll


@lru_cache(maxsize=1)
def auth_attempts_collection():
    coll = _client()[settings.MONGODB_DATABASE]["auth_attempts"]
    coll.create_index("expires_at", expireAfterSeconds=0)
    return coll


def ping():
    _client().admin.command("ping")

