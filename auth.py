import hashlib
import os
import sqlite3
from typing import Optional

DB_PATH = "users.db"


def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _hash_password(password: str, salt: str) -> str:
    return hashlib.sha256((salt + password).encode()).hexdigest()


def init_db() -> None:
    with _get_conn() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                salt TEXT NOT NULL,
                administrator TEXT NOT NULL,
                allowed_customers TEXT NOT NULL DEFAULT 'all',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

        try:
            conn.execute(
                "ALTER TABLE users ADD COLUMN allowed_customers TEXT NOT NULL DEFAULT 'all'"
            )
        except sqlite3.OperationalError:
            pass

        row = conn.execute("SELECT COUNT(*) AS cnt FROM users").fetchone()
        if row and row["cnt"] == 0:
            salt = os.urandom(16).hex()
            conn.execute(
                """
                INSERT INTO users (username, password_hash, salt, administrator, allowed_customers)
                VALUES (?, ?, ?, ?, ?)
                """,
                ("admin", _hash_password("admin", salt), salt, "admin", "all"),
            )


def create_user(
    username: str, password: str, administrator: str, allowed_customers: str = "all"
) -> bool:
    """Returns True on success, False if username already exists."""
    salt = os.urandom(16).hex()
    pw_hash = _hash_password(password, salt)

    try:
        with _get_conn() as conn:
            conn.execute(
                """
                INSERT INTO users (username, password_hash, salt, administrator, allowed_customers)
                VALUES (?, ?, ?, ?, ?)
                """,
                (username, pw_hash, salt, administrator, allowed_customers),
            )
        return True
    except sqlite3.IntegrityError:
        return False


def authenticate(username: str, password: str) -> Optional[dict]:
    """Returns user dict on success, None on failure."""
    with _get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM users WHERE username = ?", (username,)
        ).fetchone()

    if row is None:
        return None
    if _hash_password(password, row["salt"]) != row["password_hash"]:
        return None
    return dict(row)


def is_admin(user: dict) -> bool:
    return user.get("administrator", "").lower() == "admin"


def list_users() -> list[dict]:
    with _get_conn() as conn:
        rows = conn.execute(
            """
            SELECT id, username, administrator, allowed_customers, created_at
            FROM users
            ORDER BY id
            """
        ).fetchall()
    return [dict(row) for row in rows]


def delete_user(user_id: int) -> bool:
    with _get_conn() as conn:
        cur = conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
    return cur.rowcount > 0


def update_password(user_id: int, new_password: str) -> bool:
    salt = os.urandom(16).hex()
    pw_hash = _hash_password(new_password, salt)
    with _get_conn() as conn:
        cur = conn.execute(
            "UPDATE users SET password_hash = ?, salt = ? WHERE id = ?",
            (pw_hash, salt, user_id),
        )
    return cur.rowcount > 0
