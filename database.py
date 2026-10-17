"""Simple DB-API adapter. PostgreSQL for durable Render storage, SQLite for local demos."""
import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

URL = os.environ.get("DATABASE_URL", "").strip()
IS_POSTGRES = URL.startswith(("postgres://", "postgresql://"))
SQLITE_PATH = Path(os.environ.get("SQLITE_PATH", str(Path(__file__).resolve().parent / "instance" / "suhail.db")))


@contextmanager
def connection():
    if IS_POSTGRES:
        import psycopg
        conn = psycopg.connect(URL, connect_timeout=10)
    else:
        SQLITE_PATH.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(SQLITE_PATH, timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA busy_timeout = 10000")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db():
    id_column = "BIGSERIAL PRIMARY KEY" if IS_POSTGRES else "INTEGER PRIMARY KEY AUTOINCREMENT"
    with connection() as conn:
        sql = f"""CREATE TABLE IF NOT EXISTS simulations (
            id {id_column}, created_at TEXT NOT NULL,
            patient_name TEXT NOT NULL, patient_id TEXT NOT NULL, notes TEXT NOT NULL,
            input_json TEXT NOT NULL, results_json TEXT NOT NULL
        )"""
        if IS_POSTGRES:
            with conn.cursor() as cur:
                cur.execute(sql)
        else:
            conn.execute(sql)


def save_simulation(req, results):
    sql = "INSERT INTO simulations (created_at, patient_name, patient_id, notes, input_json, results_json) VALUES ({})".format(
        ", ".join(["%s" if IS_POSTGRES else "?"] * 6))
    vals = (datetime.now(timezone.utc).isoformat(timespec="seconds"), req.patient_name,
            req.patient_id, req.notes, req.model_dump_json(), json.dumps(results, ensure_ascii=False))
    with connection() as conn:
        if IS_POSTGRES:
            with conn.cursor() as cur:
                cur.execute(sql + " RETURNING id", vals)
                return cur.fetchone()[0]
        else:
            cur = conn.execute(sql, vals)
            return cur.lastrowid


def _as_dict(row, cols=None):
    if row is None:
        return None
    if isinstance(row, sqlite3.Row):
        return dict(row)
    return dict(zip(cols, row))


def list_simulations(limit=100):
    sql = "SELECT id, created_at, patient_name, patient_id FROM simulations ORDER BY id DESC LIMIT " + ("%s" if IS_POSTGRES else "?")
    with connection() as conn:
        if IS_POSTGRES:
            with conn.cursor() as cur:
                cur.execute(sql, (limit,))
                rows = cur.fetchall()
                return [_as_dict(r, ["id", "created_at", "patient_name", "patient_id"]) for r in rows]
        return [dict(r) for r in conn.execute(sql, (limit,)).fetchall()]


def get_simulation(sim_id):
    sql = "SELECT id, created_at, patient_name, patient_id, notes, input_json, results_json FROM simulations WHERE id = " + ("%s" if IS_POSTGRES else "?")
    with connection() as conn:
        if IS_POSTGRES:
            with conn.cursor() as cur:
                cur.execute(sql, (sim_id,))
                row = _as_dict(cur.fetchone(), ["id", "created_at", "patient_name", "patient_id", "notes", "input_json", "results_json"])
        else:
            row = _as_dict(conn.execute(sql, (sim_id,)).fetchone())
    if row:
        row["inputs"] = json.loads(row.pop("input_json"))
        row["results"] = json.loads(row.pop("results_json"))
    return row
