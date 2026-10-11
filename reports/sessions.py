"""MongoDB-backed Django sessions with server-side revocation on logout."""
from datetime import datetime, timezone

from django.contrib.sessions.backends.base import CreateError, SessionBase

from .repository import sessions_collection


class SessionStore(SessionBase):
    def load(self):
        if not self.session_key:
            return {}
        row = sessions_collection().find_one({
            "_id": self.session_key,
            "expire_date": {"$gt": datetime.now(timezone.utc)},
        })
        if row is None:
            return {}
        try:
            return self.decode(row["session_data"])
        except Exception:
            self.delete(self.session_key)
            return {}

    def exists(self, session_key):
        return sessions_collection().find_one({"_id": session_key}, {"_id": 1}) is not None

    def create(self):
        while True:
            self._session_key = self._get_new_session_key()
            row = {
                "_id": self._session_key,
                "session_data": self.encode({}),
                "expire_date": self.get_expiry_date(),
            }
            try:
                sessions_collection().insert_one(row)
                self._session_cache = {}
                return
            except Exception as exc:
                from pymongo.errors import DuplicateKeyError
                if isinstance(exc, DuplicateKeyError):
                    self._session_key = None
                    continue
                self._session_key = None
                raise

    def save(self, must_create=False):
        row = {
            "session_data": self.encode(self._get_session(no_load=must_create)),
            "expire_date": self.get_expiry_date(),
        }
        if self.session_key is None:
            if must_create:
                self._session_key = self._get_new_session_key()
                row["_id"] = self.session_key
                try:
                    sessions_collection().insert_one(row)
                    return
                except Exception as exc:
                    from pymongo.errors import DuplicateKeyError
                    self._session_key = None
                    if isinstance(exc, DuplicateKeyError):
                        raise CreateError from exc
                    raise
            self.create()
        if must_create:
            row["_id"] = self.session_key
            try:
                sessions_collection().insert_one(row)
            except Exception as exc:
                from pymongo.errors import DuplicateKeyError
                if isinstance(exc, DuplicateKeyError):
                    raise CreateError from exc
                raise
            return
        result = sessions_collection().update_one({"_id": self.session_key}, {"$set": row})
        if not result.matched_count:
            # A session can expire between request loading and saving. Rotate
            # to a fresh server-side key and keep the current request's data.
            self._session_key = self._get_new_session_key()
            row["_id"] = self.session_key
            try:
                sessions_collection().insert_one(row)
            except Exception as exc:
                from pymongo.errors import DuplicateKeyError
                self._session_key = None
                if isinstance(exc, DuplicateKeyError):
                    raise CreateError from exc
                raise

    def delete(self, session_key=None):
        key = session_key or self.session_key
        if key:
            sessions_collection().delete_one({"_id": key})

    @classmethod
    def clear_expired(cls):
        sessions_collection().delete_many({"expire_date": {"$lte": datetime.now(timezone.utc)}})
