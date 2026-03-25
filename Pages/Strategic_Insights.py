from __future__ import annotations

import csv
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


EVENT_COLUMNS = [
    "event_id",
    "timestamp",
    "country",
    "event_type",
    "subcategory",
    "source",
    "sensitive",
]

BASE_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = BASE_DIR / "data"
EVENTS_CSV_PATH = DATA_DIR / "events.csv"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _safe_text(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _coerce_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    if isinstance(value, (int, float)):
        return bool(value)
    return _safe_text(value).lower() in {"1", "true", "yes", "y", "t"}


def _normalize_timestamp(value: Any) -> str:
    if value in (None, ""):
        return _utc_now_iso()

    if isinstance(value, datetime):
        timestamp = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        return timestamp.astimezone(timezone.utc).replace(microsecond=0).isoformat()

    raw_value = _safe_text(value)
    if not raw_value:
        return _utc_now_iso()

    try:
        # Support common ISO inputs, including values ending in "Z".
        iso_candidate = raw_value[:-1] + "+00:00" if raw_value.endswith("Z") else raw_value
        parsed = datetime.fromisoformat(iso_candidate)
        parsed = parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc).replace(microsecond=0).isoformat()
    except ValueError:
        return _utc_now_iso()


def _normalize_event(event: dict[str, Any]) -> dict[str, str]:
    if not isinstance(event, dict):
        raise TypeError("log_event expects a dictionary.")

    event_id = _safe_text(event.get("event_id"))
    if not event_id:
        raise ValueError("event_id is required.")

    return {
        "event_id": event_id,
        "timestamp": _normalize_timestamp(event.get("timestamp")),
        "country": _safe_text(event.get("country")),
        "event_type": _safe_text(event.get("event_type")),
        "subcategory": _safe_text(event.get("subcategory")),
        "source": _safe_text(event.get("source")),
        "sensitive": "true" if _coerce_bool(event.get("sensitive")) else "false",
    }


def _normalize_existing_row(row: dict[str, Any]) -> dict[str, str]:
    normalized = {column: _safe_text(row.get(column)) for column in EVENT_COLUMNS}
    normalized["timestamp"] = _normalize_timestamp(normalized.get("timestamp"))
    normalized["sensitive"] = "true" if _coerce_bool(normalized.get("sensitive")) else "false"
    return normalized


def _write_rows(rows: list[dict[str, str]]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with EVENTS_CSV_PATH.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=EVENT_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


def _read_rows() -> list[dict[str, str]]:
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    if not EVENTS_CSV_PATH.exists() or EVENTS_CSV_PATH.stat().st_size == 0:
        _write_rows([])
        return []

    with EVENTS_CSV_PATH.open("r", newline="", encoding="utf-8") as csv_file:
        reader = csv.DictReader(csv_file)
        rows = [_normalize_existing_row(row) for row in reader]
        schema_matches = reader.fieldnames == EVENT_COLUMNS

    if not schema_matches:
        _write_rows(rows)

    return rows


def log_event(event: dict[str, Any]) -> bool:
    """
    Append a single event row to data/events.csv.

    Returns True when a new event is written.
    Returns False when the event_id already exists.
    """

    normalized_event = _normalize_event(event)
    existing_rows = _read_rows()
    existing_ids = {row["event_id"] for row in existing_rows if row.get("event_id")}

    if normalized_event["event_id"] in existing_ids:
        return False

    existing_rows.append(normalized_event)
    _write_rows(existing_rows)
    return True

