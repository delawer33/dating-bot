from __future__ import annotations

import os
import time
from dataclasses import dataclass
from datetime import datetime, timezone

import mysql.connector
from mysql.connector import MySQLConnection


@dataclass(frozen=True)
class DbCfg:
    host: str
    port: int
    user: str
    password: str
    database: str


def utc_ts() -> str:
    return datetime.now(tz=timezone.utc).strftime("%H:%M:%S.%f")[:-3] + "Z"


def cfg_from_env() -> DbCfg:
    return DbCfg(
        host=os.environ.get("DB_HOST", "127.0.0.1"),
        port=int(os.environ.get("DB_PORT", "3306")),
        user=os.environ.get("DB_USER", "app"),
        password=os.environ.get("DB_PASSWORD", "app"),
        database=os.environ.get("DB_NAME", "isolation"),
    )


def connect(cfg: DbCfg) -> MySQLConnection:
    # autocommit=False so we fully control transactions
    return mysql.connector.connect(
        host=cfg.host,
        port=cfg.port,
        user=cfg.user,
        password=cfg.password,
        database=cfg.database,
        autocommit=False,
    )


def wait_db(cfg: DbCfg, timeout_s: int = 60) -> None:
    deadline = time.time() + timeout_s
    last_err: Exception | None = None
    while time.time() < deadline:
        try:
            conn = connect(cfg)
            conn.close()
            return
        except Exception as e:  # noqa: BLE001 - ok in demo scripts
            last_err = e
            time.sleep(1)
    raise RuntimeError(f"DB not ready after {timeout_s}s: {last_err}")


def exec_sql_file(conn: MySQLConnection, path: str) -> None:
    with open(path, "r", encoding="utf-8") as f:
        sql = f.read()
    cur = conn.cursor()
    try:
        for stmt in _split_sql(sql):
            cur.execute(stmt)
        conn.commit()
    finally:
        cur.close()


def _split_sql(sql: str) -> list[str]:
    out: list[str] = []
    buff: list[str] = []
    for line in sql.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("--"):
            continue
        buff.append(line)
        if stripped.endswith(";"):
            out.append("\n".join(buff).strip().rstrip(";"))
            buff = []
    if buff:
        out.append("\n".join(buff).strip())
    return [s for s in (x.strip() for x in out) if s]


def reset_db(cfg: DbCfg) -> None:
    conn = connect(cfg)
    try:
        exec_sql_file(conn, "sql/00_schema.sql")
        exec_sql_file(conn, "sql/01_seed.sql")
    finally:
        conn.close()


def start_tx(conn: MySQLConnection, isolation_level: str) -> None:
    cur = conn.cursor()
    try:
        cur.execute(f"SET SESSION TRANSACTION ISOLATION LEVEL {isolation_level}")
        cur.execute("START TRANSACTION")
    finally:
        cur.close()


def q1(conn: MySQLConnection, sql: str, params: tuple | None = None):
    cur = conn.cursor()
    try:
        cur.execute(sql, params or ())
        row = cur.fetchone()
        return row[0] if row else None
    finally:
        cur.close()


def q(conn: MySQLConnection, sql: str, params: tuple | None = None) -> list[tuple]:
    cur = conn.cursor()
    try:
        cur.execute(sql, params or ())
        return list(cur.fetchall())
    finally:
        cur.close()


def x(conn: MySQLConnection, sql: str, params: tuple | None = None) -> None:
    cur = conn.cursor()
    try:
        cur.execute(sql, params or ())
    finally:
        cur.close()


def log(who: str, msg: str) -> None:
    print(f"[{utc_ts()}] {who}: {msg}", flush=True)
