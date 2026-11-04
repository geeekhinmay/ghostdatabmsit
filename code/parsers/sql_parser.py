"""
SQL evidence parser.

Reads SQLite-compatible SQL snapshot exports (CREATE TABLE + INSERT statements).
These may represent primary databases, regional replicas, reporting replicas,
or failover replicas.

The parser:
  1. Executes the SQL in an in-memory SQLite database.
  2. Discovers all tables.
  3. Reads every row from every table.
  4. Converts each row into an EvidenceRecord.

Owned by: Member 2 — Chinmay Motagi
"""

from __future__ import annotations

import logging
import re
import sqlite3
from pathlib import Path
from typing import Any

from code.models.enums import EvidenceFormat
from code.models.schemas import EvidenceFileEntry, EvidenceRecord
from code.parsers.common import (
    build_base_record,
    extract_identifiers,
    infer_record_type_and_system,
    safe_parse_datetime,
)

logger = logging.getLogger(__name__)


def parse_sql_evidence(
    abs_path: Path,
    entry: EvidenceFileEntry,
) -> list[EvidenceRecord]:
    """
    Load a SQL snapshot file into an in-memory SQLite database and extract
    all rows as EvidenceRecords.

    Parameters
    ----------
    abs_path:
        Absolute path to the .sql file.
    entry:
        The manifest entry for this file.

    Returns
    -------
    list[EvidenceRecord]
        One record per database row across all tables.
    """
    records: list[EvidenceRecord] = []

    try:
        sql_text = abs_path.read_text(encoding="utf-8-sig")
    except Exception as exc:  # noqa: BLE001
        logger.error("Cannot read SQL file %s: %s", abs_path, exc)
        return records

    # Execute in-memory SQLite
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    try:
        # Strip MySQL-specific syntax that SQLite doesn't support
        sql_text = _sanitise_for_sqlite(sql_text)
        conn.executescript(sql_text)
    except sqlite3.Error as exc:
        logger.warning("SQL execution warning for %s: %s — will try to read partial schema", abs_path.name, exc)

    try:
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [row[0] for row in cursor.fetchall()]

        for table in tables:
            try:
                cursor.execute(f"SELECT * FROM [{table}]")  # noqa: S608
                col_names = [desc[0] for desc in cursor.description]
                rows = cursor.fetchall()
                for row in rows:
                    flat = {col: (str(val) if val is not None else "") for col, val in zip(col_names, row)}
                    flat["_sql_table"] = table
                    try:
                        base = build_base_record(entry, EvidenceFormat.SQL)
                        ids = extract_identifiers(flat)
                        rtype, sys_id = infer_record_type_and_system(flat, entry, hint=table)
                        resource_id = _extract_resource_id(flat, table)
                        ts = _extract_timestamp(flat)

                        rec = EvidenceRecord(
                            **base,
                            record_type=rtype,
                            system_id=sys_id,
                            resource_id=resource_id,
                            user_id=ids.get("user_id"),
                            email=ids.get("email"),
                            email_hash=ids.get("email_hash"),
                            phone=ids.get("phone"),
                            name=ids.get("name"),
                            record_timestamp=ts,
                            raw_fields=flat,
                        )
                        records.append(rec)
                    except Exception as exc2:  # noqa: BLE001
                        logger.warning(
                            "SQL row in table %s of %s skipped: %s",
                            table, entry.file_id, exc2
                        )
            except sqlite3.Error as exc:
                logger.warning("Cannot read table %s from %s: %s", table, entry.file_id, exc)
    finally:
        conn.close()

    logger.debug("SQL %s -> %d records from %d tables", entry.file_id, len(records), len(tables) if 'tables' in dir() else 0)
    return records


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_RESOURCE_ID_KEYS = [
    "id", "resource_id", "account_id", "search_id", "support_id",
    "export_id", "analytics_id", "backup_id", "data_flow_id",
    "audit_record_id", "tombstone_id", "connector_id",
    "marketing_id", "record_id", "user_id",
]

_TIMESTAMP_KEYS = [
    "created_at", "updated_at", "event_time", "timestamp",
    "captured_at", "deleted_at", "exported_at", "retained_at",
    "snapshot_time", "audit_time",
]


def _sanitise_for_sqlite(sql: str) -> str:
    """
    Strip / replace MySQL-specific DDL constructs so SQLite can execute the
    dump.  This is best-effort and covers common patterns from mysqldump.
    """
    # Remove ENGINE=, CHARSET= etc.
    sql = re.sub(r'\bENGINE\s*=\s*\w+', '', sql, flags=re.IGNORECASE)
    sql = re.sub(r'\bDEFAULT CHARSET\s*=\s*\w+', '', sql, flags=re.IGNORECASE)
    sql = re.sub(r'\bCHARSET\s*=\s*\w+', '', sql, flags=re.IGNORECASE)
    sql = re.sub(r'\bCOLLATE\s*=\s*\S+', '', sql, flags=re.IGNORECASE)
    sql = re.sub(r'\bCOLLATE\s+\S+', '', sql, flags=re.IGNORECASE)
    # Remove USING BTREE / HASH index hints
    sql = re.sub(r'\bUSING\s+(BTREE|HASH)', '', sql, flags=re.IGNORECASE)
    # Remove AUTO_INCREMENT=N table option
    sql = re.sub(r'\bAUTO_INCREMENT\s*=\s*\d+', '', sql, flags=re.IGNORECASE)
    # Remove KEY ... definitions inside CREATE TABLE (SQLite uses CREATE INDEX)
    # Keep PRIMARY KEY lines; remove plain KEY and UNIQUE KEY lines
    sql = re.sub(r',?\s*\b(?:KEY|INDEX)\s+`?\w+`?\s*\([^)]+\)', '', sql, flags=re.IGNORECASE)
    # Replace backtick identifiers with double-quoted ones (SQLite compatible)
    sql = sql.replace('`', '"')
    # Remove MySQL session variable sets
    sql = re.sub(r'SET\s+@@\S+\s*=.*?;', '', sql, flags=re.IGNORECASE)
    sql = re.sub(r'SET\s+@\S+\s*=.*?;', '', sql, flags=re.IGNORECASE)
    # Remove LOCK/UNLOCK TABLE statements
    sql = re.sub(r'LOCK\s+TABLES.*?;', '', sql, flags=re.IGNORECASE | re.DOTALL)
    sql = re.sub(r'UNLOCK\s+TABLES\s*;', '', sql, flags=re.IGNORECASE)
    return sql


def _extract_resource_id(flat: dict, table: str) -> str | None:
    # Prefer table-specific id keys
    table_lower = table.lower()
    for key in _RESOURCE_ID_KEYS:
        if key in flat and flat[key]:
            return flat[key].strip()
    # Fallback
    for k, v in flat.items():
        if k.endswith("_id") and v and k != "_sql_table":
            return v.strip()
    return None


def _extract_timestamp(flat: dict):
    for key in _TIMESTAMP_KEYS:
        if key in flat and flat[key]:
            return safe_parse_datetime(flat[key])
    return None
