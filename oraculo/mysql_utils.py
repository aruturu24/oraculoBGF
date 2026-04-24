import os
from urllib.parse import quote_plus

import pymysql
import streamlit as st
from langchain_community.utilities import SQLDatabase

from oraculo.constants import MAX_ATTACHMENT_PATHS


def _mysql_settings() -> dict[str, str] | None:
    host = os.getenv("MYSQL_HOST", "").strip()
    user = os.getenv("MYSQL_USER", "").strip()
    password = os.getenv("MYSQL_PASSWORD", "").strip()
    database = os.getenv("MYSQL_DATABASE", "").strip()
    if not all([host, user, password]):
        return None
    return {
        "host": host,
        "user": user,
        "password": password,
        "database": database,
    }


def _open_mysql_connection(dict_cursor: bool = False):
    settings = _mysql_settings()
    if not settings:
        return None

    kwargs = {
        "host": settings["host"],
        "user": settings["user"],
        "password": settings["password"],
        "database": settings["database"],
        "charset": "utf8mb4",
    }
    if dict_cursor:
        kwargs["cursorclass"] = pymysql.cursors.DictCursor

    try:
        return pymysql.connect(**kwargs)
    except pymysql.Error:
        return None


def get_sql_database(
    include_tables: tuple[str, ...], sample_rows_in_table_info: int = 2
) -> SQLDatabase | None:
    settings = _mysql_settings()
    if not settings:
        return None

    uri = (
        f"mysql+pymysql://{quote_plus(settings['user'])}:"
        f"{quote_plus(settings['password'])}@{settings['host']}/{settings['database']}"
    )
    try:
        return SQLDatabase.from_uri(
            uri,
            include_tables=list(include_tables),
            sample_rows_in_table_info=sample_rows_in_table_info,
        )
    except Exception:
        return None


def _dedupe_paths(paths: list[str], max_paths: int = MAX_ATTACHMENT_PATHS) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for raw in paths:
        path = str(raw).strip()
        if not path or path in seen:
            continue
        seen.add(path)
        out.append(path)
        if len(out) >= max_paths:
            break
    return out


def _parse_allowed_ids(allowed_customers: str) -> list[str]:
    value = (allowed_customers or "").strip()
    if not value or value == "all":
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


def verify_attachment_paths_for_user(
    paths: list[str], user: dict
) -> list[tuple[str, str | None]]:
    deduped_paths = _dedupe_paths(paths)
    if not deduped_paths:
        return []

    conn = _open_mysql_connection(dict_cursor=False)
    if conn is None:
        return []

    administrator = (user or {}).get("administrator", "") or ""
    allowed_customers = (user or {}).get("allowed_customers", "all")

    placeholders = ",".join(["%s"] * len(deduped_paths))
    base_sql = f"""
        SELECT DISTINCT att.`file_Path`, att.`file_Name`
        FROM `tbl_attachment_audit` att
        INNER JOIN `tbl_audit` au ON att.`id_audit` = au.`id`
        INNER JOIN `tbl_customer` c ON au.`customer_id` = c.`id`
        WHERE att.`file_Path` IN ({placeholders})
    """

    try:
        with conn.cursor() as cur:
            if administrator.strip().lower() == "admin":
                cur.execute(base_sql, deduped_paths)
            else:
                allowed_ids = _parse_allowed_ids(allowed_customers)
                if allowed_customers != "all" and not allowed_ids:
                    return []
                if allowed_ids:
                    allowed_ph = ",".join(["%s"] * len(allowed_ids))
                    sql = base_sql + f" AND c.`id` IN ({allowed_ph})"
                    cur.execute(sql, deduped_paths + allowed_ids)
                else:
                    sql = base_sql + " AND c.`administrator` = %s"
                    cur.execute(sql, deduped_paths + [administrator])
            rows = cur.fetchall()
    except pymysql.Error:
        return []
    finally:
        conn.close()

    verified_map = {row[0]: (row[1] if len(row) > 1 else None) for row in rows if row and row[0]}
    return [(path, verified_map.get(path)) for path in deduped_paths if path in verified_map]


def resolve_attachment_fs_path(db_path: str) -> str | None:
    raw_path = (db_path or "").strip()
    if not raw_path:
        return None

    attachment_root = (os.getenv("ATTACHMENT_FILES_ROOT") or "").strip()
    if os.path.isabs(raw_path) and os.path.isfile(raw_path):
        return raw_path
    if attachment_root:
        joined = os.path.normpath(os.path.join(attachment_root, raw_path.lstrip("/\\")))
        if os.path.isfile(joined):
            return joined
    if os.path.isfile(raw_path):
        return raw_path
    return None


def resolved_attachments_for_display(
    verified: list[tuple[str, str | None]],
) -> list[tuple[str, str | None]]:
    out: list[tuple[str, str | None]] = []
    seen_fs: set[str] = set()
    for db_path, file_name in verified:
        resolved = resolve_attachment_fs_path(db_path)
        if not resolved or resolved in seen_fs:
            continue
        seen_fs.add(resolved)
        caption = file_name or os.path.basename(db_path)
        out.append((resolved, caption))
    return out


@st.cache_data(ttl=300, show_spinner=False)
def fetch_administrator_options() -> list[str]:
    conn = _open_mysql_connection(dict_cursor=True)
    if conn is None:
        return []
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT DISTINCT administrator
                FROM tbl_customer
                WHERE administrator IS NOT NULL AND administrator <> ''
                ORDER BY administrator
                """
            )
            rows = cur.fetchall()
    except pymysql.Error:
        return []
    finally:
        conn.close()

    return [str(row["administrator"]) for row in rows if row.get("administrator")]


@st.cache_data(ttl=300, show_spinner=False)
def fetch_customers_by_admin(administrator: str) -> list[dict[str, str]]:
    admin = (administrator or "").strip()
    if not admin:
        return []

    conn = _open_mysql_connection(dict_cursor=True)
    if conn is None:
        return []

    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT CAST(id AS CHAR) AS id, cust_name AS name
                FROM tbl_customer
                WHERE administrator = %s
                ORDER BY name
                """,
                (admin,),
            )
            rows = cur.fetchall()
    except pymysql.Error:
        return []
    finally:
        conn.close()

    return [{"id": str(row["id"]), "name": str(row["name"])} for row in rows]
