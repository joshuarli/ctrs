"""W1 fixture API: JSON API backed by Postgres and Redis.

Real application surface used by the native-performance campaign:
readiness that depends on both datastores, persistent records that must
survive a database restart, and a seeded item table for load tests.
"""

import os
import time
from contextlib import asynccontextmanager

import psycopg
import redis
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

DSN = os.environ["DATABASE_URL"]
REDIS_URL = os.environ.get("REDIS_URL", "redis://cache:6379/0")
SEED_ROWS = int(os.environ.get("SEED_ROWS", "0"))


def _connect_db(deadline: float = 90.0) -> psycopg.Connection:
    end = time.monotonic() + deadline
    while True:
        try:
            conn = psycopg.connect(DSN, autocommit=True)
            conn.execute("SELECT 1")
            return conn
        except Exception as exc:  # datastore not up yet; keep retrying
            if time.monotonic() > end:
                raise
            print(f"db not ready, retrying: {exc}", flush=True)
            time.sleep(0.5)


def _connect_redis(deadline: float = 90.0) -> redis.Redis:
    end = time.monotonic() + deadline
    client = redis.from_url(REDIS_URL, socket_timeout=5)
    while True:
        try:
            client.ping()
            return client
        except Exception as exc:
            if time.monotonic() > end:
                raise
            print(f"redis not ready, retrying: {exc}", flush=True)
            time.sleep(0.5)


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.db = _connect_db()
    _db().execute(
        """
        CREATE TABLE IF NOT EXISTS records (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    app.state.redis = _connect_redis()
    yield


app = FastAPI(title="np-fixture-api", lifespan=lifespan)


def _db() -> psycopg.Connection:
    """Return a live connection, reconnecting after a datastore restart."""
    conn = app.state.db
    try:
        conn.execute("SELECT 1")
        return conn
    except Exception:
        app.state.db = _connect_db(60)
        return app.state.db


class RecordIn(BaseModel):
    key: str
    value: str


class ItemIn(BaseModel):
    name: str
    payload: str = ""


@app.get("/health")
def health():
    try:
        _db().execute("SELECT 1")
        app.state.redis.ping()
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"not ready: {exc}")
    return {"ok": True}


@app.get("/roundtrip")
def roundtrip():
    row = _db().execute(
        "SELECT id, name, payload FROM items WHERE id = 1"
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=503, detail="seed row missing")
    token = f"rt-{time.time_ns()}"
    app.state.redis.set("np:roundtrip", token)
    cached = app.state.redis.get("np:roundtrip")
    if cached is None or cached.decode() != token:
        raise HTTPException(status_code=503, detail="cache roundtrip failed")
    return {
        "ok": True,
        "db_row": {"id": row[0], "name": row[1], "payload": row[2]},
        "cache_token": token,
        "seed_rows": SEED_ROWS,
    }


@app.post("/records")
def put_record(body: RecordIn):
    _db().execute(
        "INSERT INTO records (key, value) VALUES (%s, %s) "
        "ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value",
        (body.key, body.value),
    )
    app.state.redis.set(f"rec:{body.key}", body.value)
    return {"stored": body.key}


@app.get("/records/{key}")
def get_record(key: str):
    row = _db().execute(
        "SELECT value FROM records WHERE key = %s", (key,)
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="no such record")
    cached = app.state.redis.get(f"rec:{key}")
    return {
        "key": key,
        "value": row[0],
        "cache_match": cached is not None and cached.decode() == row[0],
    }


@app.get("/items")
def list_items(limit: int = 50):
    limit = max(1, min(limit, 200))
    rows = _db().execute(
        "SELECT id, name FROM items ORDER BY id LIMIT %s", (limit,)
    ).fetchall()
    return {"items": [{"id": r[0], "name": r[1]} for r in rows]}


@app.post("/items", status_code=201)
def create_item(body: ItemIn):
    row = _db().execute(
        "INSERT INTO items (name, payload) VALUES (%s, %s) RETURNING id",
        (body.name, body.payload),
    ).fetchone()
    return {"id": row[0], "name": body.name}


@app.get("/stats")
def stats():
    items = _db().execute("SELECT count(*) FROM items").fetchone()[0]
    records = _db().execute("SELECT count(*) FROM records").fetchone()[0]
    app.state.redis.ping()
    return {"items": items, "records": records, "seed_rows": SEED_ROWS}
