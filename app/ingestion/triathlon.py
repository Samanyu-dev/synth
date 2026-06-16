"""
Triathlon data ingestion — parses CSV files into typed models.

Sources (MVP):
  - daily_summary CSV → List[DailySummary] (141 rows)
  - activities_raw CSV → List[ActivityRecord] (375 rows)

Design decisions:
  - CSV instead of xlsx: lighter dependency, faster parsing, git-diffable
  - Parse once, cache in memory: files don't change during a session
  - NaN handling: pandas reads empty CSV cells as NaN, we convert to None
  - Wellness columns: all empty in current data, handled gracefully
"""

from __future__ import annotations

import logging
import math
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import List, Optional, Tuple

import pandas as pd

from app.models.schemas import ActivityRecord, DailySummary

logger = logging.getLogger("synth.ingestion.triathlon")

# ---- Module-level cache ----
# Why cache? The CSV files don't change during a session.
# Parsing 141 rows is fast, but we don't want to do it on every API call.
_daily_cache: Optional[List[DailySummary]] = None
_activities_cache: Optional[List[ActivityRecord]] = None


def ingest_daily_summary(filepath: str) -> List[DailySummary]:
    """
    Parse the daily_summary CSV into DailySummary models.

    What this does:
      1. Reads the CSV with pandas
      2. Converts each row to a DailySummary Pydantic model
      3. Handles NaN → None for Optional fields
      4. Skips rows that fail validation (logs a warning)
      5. Returns sorted by date (oldest first)

    Args:
        filepath: Path to the daily_summary CSV file

    Returns:
        List of validated DailySummary records, sorted by date
    """
    global _daily_cache
    if _daily_cache is not None:
        logger.info(
            "triathlon.daily_summary: returning cached %d rows", len(_daily_cache)
        )
        return _daily_cache

    path = Path(filepath)
    if not path.exists():
        raise FileNotFoundError(f"Triathlon daily summary not found: {filepath}")

    # Read CSV — pandas handles the parsing
    df = pd.read_csv(filepath)
    df["date"] = pd.to_datetime(df["date"]).dt.date
    df = df.sort_values("date").reset_index(drop=True)

    records: List[DailySummary] = []
    skipped = 0

    for _, row in df.iterrows():
        try:
            record = DailySummary(
                date=row["date"],
                # Session counts — always populated, default to 0
                run_count=_safe_int(row.get("run_count")) or 0,
                bike_count=_safe_int(row.get("bike_count")) or 0,
                swim_count=_safe_int(row.get("swim_count")) or 0,
                walk_count=_safe_int(row.get("walk_count")) or 0,
                strength_count=_safe_int(row.get("strength_count")) or 0,
                other_count=_safe_int(row.get("other_count")) or 0,
                tri_session_count=_safe_int(row.get("tri_session_count")) or 0,
                total_session_count=_safe_int(row.get("total_session_count")) or 0,
                # Distances — always populated
                run_miles=_safe_float(row.get("run_miles")) or 0.0,
                bike_miles=_safe_float(row.get("bike_miles")) or 0.0,
                swim_miles=_safe_float(row.get("swim_miles")) or 0.0,
                # Volume — always populated
                training_minutes=_safe_float(row.get("training_minutes")) or 0.0,
                tri_training_minutes=_safe_float(row.get("tri_training_minutes")) or 0.0,
                total_elevation_ft=_safe_float(row.get("total_elevation_ft")) or 0.0,
                # Intensity — Optional, some days missing
                avg_hr_all=_safe_float(row.get("avg_hr_all")),
                max_hr_all=_safe_float(row.get("max_hr_all")),
                avg_power_bike=_safe_float(row.get("avg_power_bike")),
                weighted_power_bike=_safe_float(row.get("weighted_power_bike")),
                avg_cadence_bike=_safe_float(row.get("avg_cadence_bike")),
                avg_cadence_run=_safe_float(row.get("avg_cadence_run")),
                avg_pace_run_min_per_mi=_safe_float(row.get("avg_pace_run_min_per_mi")),
                # Wellness — ALL EMPTY in current data
                rhr=_safe_float(row.get("rhr")),
                hrv=_safe_float(row.get("hrv")),
                sleep_hours=_safe_float(row.get("asleep")),  # column is "asleep"
                body_weight_lb=_safe_float(row.get("body_weight_lb")),
                # Misc
                sauna_mins=_safe_float(row.get("sauna_mins")),
            )
            records.append(record)
        except Exception as e:
            skipped += 1
            logger.warning(
                "triathlon.daily_summary: skipped row date=%s error=%s",
                row.get("date"),
                str(e),
            )

    logger.info(
        "triathlon.daily_summary: parsed %d rows, skipped %d, "
        "date_range=%s to %s",
        len(records),
        skipped,
        records[0].date if records else "N/A",
        records[-1].date if records else "N/A",
    )

    _daily_cache = records
    return records


def ingest_activities(filepath: str) -> List[ActivityRecord]:
    """
    Parse the activities_raw CSV into ActivityRecord models.

    375 individual activities with per-session detail. This gives us
    sport-type granularity that daily_summary aggregates away.

    Args:
        filepath: Path to the activities_raw CSV file

    Returns:
        List of validated ActivityRecord records, sorted by date
    """
    global _activities_cache
    if _activities_cache is not None:
        logger.info(
            "triathlon.activities: returning cached %d rows",
            len(_activities_cache),
        )
        return _activities_cache

    path = Path(filepath)
    if not path.exists():
        raise FileNotFoundError(f"Triathlon activities not found: {filepath}")

    df = pd.read_csv(filepath)
    df["start_date_local"] = pd.to_datetime(df["start_date_local"])
    df = df.sort_values("start_date_local").reset_index(drop=True)

    records: List[ActivityRecord] = []
    skipped = 0

    for _, row in df.iterrows():
        try:
            start_dt = row["start_date_local"]
            record = ActivityRecord(
                activity_id=str(row["activity_id"]),
                start_date_local=start_dt,
                date=start_dt.date(),
                name=_safe_str(row.get("name")),
                sport_type=str(row.get("sport_type", "Unknown")),
                trainer=_safe_bool(row.get("trainer")),
                commute=_safe_bool(row.get("commute")),
                moving_time_sec=_safe_int(row.get("moving_time_sec")) or 0,
                elapsed_time_sec=_safe_int(row.get("elapsed_time_sec")) or 0,
                distance_m=_safe_float(row.get("distance_m")) or 0.0,
                distance_mi=_safe_float(row.get("distance_mi")) or 0.0,
                elevation_gain_m=_safe_float(row.get("total_elevation_gain_m")) or 0.0,
                elevation_gain_ft=_safe_float(row.get("total_elevation_gain_ft")) or 0.0,
                avg_hr=_safe_float(row.get("average_heartrate")),
                max_hr=_safe_float(row.get("max_heartrate")),
                avg_watts=_safe_float(row.get("average_watts")),
                weighted_watts=_safe_float(row.get("weighted_average_watts")),
                avg_cadence=_safe_float(row.get("average_cadence")),
                kilojoules=_safe_float(row.get("kilojoules")),
                calories=_safe_float(row.get("calories")),
                device_name=_safe_str(row.get("device_name")),
                suffer_score=_safe_float(row.get("suffer_score")),
                perceived_exertion=_safe_float(row.get("perceived_exertion")),
            )
            records.append(record)
        except Exception as e:
            skipped += 1
            logger.warning(
                "triathlon.activities: skipped row id=%s error=%s",
                row.get("activity_id"),
                str(e),
            )

    logger.info(
        "triathlon.activities: parsed %d activities, skipped %d",
        len(records),
        skipped,
    )

    _activities_cache = records
    return records


def get_triathlon_data(
    daily_path: str,
    activities_path: str,
    date_range_days: int = 7,
    end_date: Optional[date] = None,
) -> Tuple[List[DailySummary], List[ActivityRecord]]:
    """
    Get triathlon data filtered to a date range.

    This is the main entry point for the triathlon domain.
    Returns both daily summaries and activities for the specified window,
    plus the previous window (for comparison metrics).

    Args:
        daily_path: Path to daily_summary CSV
        activities_path: Path to activities_raw CSV
        date_range_days: Number of days to analyze (default 7)
        end_date: End of the analysis window (default: latest in data)

    Returns:
        Tuple of (filtered_daily, filtered_activities) for the date range
    """
    all_daily = ingest_daily_summary(daily_path)
    all_activities = ingest_activities(activities_path)

    if not all_daily:
        return [], []

    # Default end_date to the latest date in the data
    if end_date is None:
        end_date = max(r.date for r in all_daily)

    start_date = end_date - timedelta(days=date_range_days - 1)

    filtered_daily = [r for r in all_daily if start_date <= r.date <= end_date]
    filtered_activities = [
        r for r in all_activities if start_date <= r.date <= end_date
    ]

    logger.info(
        "triathlon.filter: %d daily rows, %d activities for %s to %s",
        len(filtered_daily),
        len(filtered_activities),
        start_date,
        end_date,
    )

    return filtered_daily, filtered_activities


def get_all_daily(daily_path: str) -> List[DailySummary]:
    """Get all daily summaries (unfiltered). Used for baseline calculations."""
    return ingest_daily_summary(daily_path)


def clear_cache() -> None:
    """Clear the module-level cache. Call this in tests."""
    global _daily_cache, _activities_cache
    _daily_cache = None
    _activities_cache = None


# =============================================================================
# Type-safe conversion helpers
# =============================================================================
# Why do we need these? CSV data comes in as strings or NaN.
# Pydantic expects Python types. These bridge the gap safely.

def _safe_float(value) -> Optional[float]:
    """Convert a value to float, returning None for NaN/None/empty."""
    if value is None:
        return None
    try:
        f = float(value)
        return None if math.isnan(f) else f
    except (ValueError, TypeError):
        return None


def _safe_int(value) -> Optional[int]:
    """Convert to int, None for NaN/invalid."""
    f = _safe_float(value)
    return int(f) if f is not None else None


def _safe_str(value) -> Optional[str]:
    """Convert to string, None for NaN/None/empty."""
    if value is None:
        return None
    s = str(value).strip()
    if s.lower() in ("nan", "none", ""):
        return None
    return s


def _safe_bool(value) -> bool:
    """Convert to bool — handles CSV 'TRUE'/'FALSE' strings."""
    if value is None:
        return False
    if isinstance(value, bool):
        return value
    s = str(value).strip().upper()
    return s in ("TRUE", "1", "YES")
