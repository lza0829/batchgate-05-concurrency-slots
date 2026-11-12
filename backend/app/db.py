import sqlite3
from pathlib import Path

from app.config import DATA_DIR, DB_FILENAME

DB_PATH = DATA_DIR / DB_FILENAME


def connect() -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn
