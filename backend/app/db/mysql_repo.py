import os
from contextlib import contextmanager
from typing import Any, Dict, Iterable, Iterator, Optional

import pymysql
from dotenv import load_dotenv

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
load_dotenv(os.path.join(PROJECT_ROOT, ".env"))


def _env_bool(value: Optional[str], default: bool = False) -> bool:
    if value is None:
        return default
    return str(value).strip().lower() in ("1", "true", "yes", "on")


def _connect(dict_cursor: bool = True) -> pymysql.connections.Connection:
    host = os.getenv("MYSQL_HOST", "localhost")
    port = int(os.getenv("MYSQL_PORT", "3306"))
    user = os.getenv("MYSQL_USER", "root")
    password = os.getenv("MYSQL_PASSWORD", "")
    database = os.getenv("MYSQL_DB") or None
    use_ssl = _env_bool(os.getenv("MYSQL_SSL"), default=False)

    kwargs: Dict[str, Any] = {
        "host": host,
        "port": port,
        "user": user,
        "password": password,
        "database": database,
        "charset": "utf8mb4",
        "autocommit": True,
    }
    if dict_cursor:
        kwargs["cursorclass"] = pymysql.cursors.DictCursor
    if use_ssl:
        kwargs["ssl"] = {"ssl": {}}
    return pymysql.connect(**kwargs)


@contextmanager
def mysql_cursor(dict_cursor: bool = True) -> Iterator[tuple[pymysql.connections.Connection, Any]]:
    conn = _connect(dict_cursor=dict_cursor)
    try:
        with conn.cursor() as cursor:
            yield conn, cursor
    finally:
        conn.close()


def fetch_one(sql: str, params: Optional[Iterable[Any]] = None) -> Optional[Dict[str, Any]]:
    with mysql_cursor(dict_cursor=True) as (_, cursor):
        cursor.execute(sql, params)
        row = cursor.fetchone()
        return row if isinstance(row, dict) else None


def fetch_all(sql: str, params: Optional[Iterable[Any]] = None) -> list[Dict[str, Any]]:
    with mysql_cursor(dict_cursor=True) as (_, cursor):
        cursor.execute(sql, params)
        rows = cursor.fetchall() or []
        return rows if isinstance(rows, list) else list(rows)


def execute(sql: str, params: Optional[Iterable[Any]] = None) -> int:
    with mysql_cursor(dict_cursor=True) as (_, cursor):
        return int(cursor.execute(sql, params))


def insert(sql: str, params: Optional[Iterable[Any]] = None) -> int:
    with mysql_cursor(dict_cursor=True) as (_, cursor):
        cursor.execute(sql, params)
        return int(cursor.lastrowid or 0)
