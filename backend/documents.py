"""One document per plan: nested meals and the exact inputs/targets used."""
from datetime import datetime, timezone
import json
from pathlib import Path
from uuid import uuid4


def new_plan(user_id, result):
    return dict(result, id=uuid4().hex, user_id=user_id, created_at=datetime.now(timezone.utc).isoformat())


class LocalDocuments:
    """Small offline store for the demo; one folder per account."""
    kind = "local"

    def __init__(self, root: Path):
        self.root = root

    def save(self, user_id, result):
        doc = new_plan(user_id, result)
        folder = self.root / str(user_id)
        folder.mkdir(parents=True, exist_ok=True)
        temp = folder / f"{doc['id']}.tmp"
        temp.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
        temp.replace(temp.with_suffix(".json"))
        return doc

    def get(self, user_id, plan_id):
        path = self.root / str(user_id) / f"{plan_id}.json"
        return self.read(path) if path.is_file() else None

    @staticmethod
    def read(path):
        return json.loads(path.read_text(encoding="utf-8"))

    def list(self, user_id, offset, limit):
        files = sorted((self.root / str(user_id)).glob("*.json"),
                       key=lambda p: (p.stat().st_mtime_ns, p.name), reverse=True)
        return [self.read(path) for path in files[offset:offset + limit]], len(files)


class MongoDocuments:
    kind = "mongodb"

    def __init__(self, uri):
        from pymongo import MongoClient

        self.client = MongoClient(uri, serverSelectionTimeoutMS=4000)
        try:
            self.collection = self.client["food_sequence"]["plans"]
            self.collection.create_index([("user_id", 1), ("created_at", -1), ("id", -1)])
            self.collection.create_index("id", unique=True)
        except Exception:
            self.client.close()
            raise

    def save(self, user_id, result):
        doc = new_plan(user_id, result)
        self.collection.insert_one(doc.copy())
        return doc

    def get(self, user_id, plan_id):
        return self.collection.find_one({"user_id": user_id, "id": plan_id}, {"_id": 0})

    def list(self, user_id, offset, limit):
        query = {"user_id": user_id}
        docs = self.collection.find(query, {"_id": 0}).sort([("created_at", -1), ("id", -1)]).skip(offset).limit(limit)
        return list(docs), self.collection.count_documents(query)
