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
    coll.create_index("status")
    return coll


def ping():
    _client().admin.command("ping")

