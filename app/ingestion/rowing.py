"""
Rowing erg data ingestion — parses 16 CSV files into typed models.

Each CSV file was exported from one Excel sheet. The filename tells us
the test date and workout type:
  "rowing_women_2025-2026 ERGS-2-316 2k.csv" → March 16, 2k test

Handles 7 distinct workout formats:
  2k:      TIME, AVG SPLIT, AVG RATE, AVG WATTS, 500m segments
  6k:      SPLIT, TIME, RATE
  2x6k:    AVG SPLIT, SPLIT 1/2, RATE 1/2, TIME 1/2
  4x1k:    AVG SPLIT, AVG WATTS, 4× SPLIT/RATE
  9x2k:    AVERAGE, 9× SPLIT
  3x12:    AVG SPLIT, 3× SPLIT/RATE
  30min:   AVG SPLIT, METERS, AVG RATE
  2k_prep: AVG SPLIT, AVG WATTS, 3 segment splits + rates

Special rows in the CSVs:
  - "RP3" or "BERG" → marks start of different ergometer section
  - "Out" → marks athletes who didn't participate
  - Athletes with "sick" in their split column → missed due to illness
"""

from __future__ import annotations

import logging
import math
import re
from datetime import date
from pathlib import Path
from typing import List, Optional, Tuple

import pandas as pd

from app.models.schemas import ErgResult

logger = logging.getLogger("synth.ingestion.rowing")

# ---- Module-level cache ----
_results_cache: Optional[List[ErgResult]] = None
_roster_cache: Optional[List[str]] = None

# ---- Filename → (month, day, workout_type) mapping ----
# Each rowing CSV filename contains a sheet identifier like "316 2k"
# We extract the date and workout type from this.
# Month 9-12 = year 2025, month 1-3 = year 2026 (the season spans both)
SHEET_PATTERNS = {
    "316 2k":     (3, 16, "2k"),
    "311 2x6k":   (3, 11, "2x6k"),
    "32 2k prep": (3, 2,  "2k_prep"),
    "223 4x1k":   (2, 23, "4x1k"),
    "217 9x2k":   (2, 17, "9x2k"),
    "29 2x6k":    (2, 9,  "2x6k"),
    "130 6k":     (1, 30, "6k"),
    "126 2x6k":   (1, 26, "2x6k"),
    "113 6K":     (1, 13, "6k"),
    "1027 3x12":  (10, 27, "3x12"),
    "1020 30":    (10, 20, "30min"),
    "1013 2x6k":  (10, 13, "2x6k"),
    "929 2x6k":   (9, 29, "2x6k"),
    "919 6k":     (9, 19, "6k"),
    "915 2x6k":   (9, 15, "2x6k"),
    "98 2x6k":    (9, 8,  "2x6k"),
}


def ingest_rowing_ergs(data_dir: str) -> List[ErgResult]:
    """
    Parse all rowing erg CSV files from a directory into ErgResult models.

    How it works:
      1. Scans data_dir for files matching "rowing_women_*-<sheet_id>.csv"
      2. Extracts the sheet identifier from the filename
      3. Looks up (month, day, workout_type) from SHEET_PATTERNS
      4. Dispatches to the format-specific parser
      5. Returns a flat list of all results across all sessions

    Args:
        data_dir: Directory containing the rowing CSV files

    Returns:
        List of all ErgResult models across all 16 test sessions
    """
    global _results_cache
    if _results_cache is not None:
        logger.info("rowing.ergs: returning cached %d results", len(_results_cache))
        return _results_cache

    dir_path = Path(data_dir)
    if not dir_path.exists():
        raise FileNotFoundError(f"Data directory not found: {data_dir}")

    all_results: List[ErgResult] = []

    # Find all rowing CSV files and match them to known sheets
    for csv_file in sorted(dir_path.glob("rowing_women_*.csv")):
        # Extract the sheet identifier from filename
        # "rowing_women_2025-2026 ERGS-2-316 2k.csv" → "316 2k"
        sheet_id = _extract_sheet_id(csv_file.name)
        if sheet_id is None or sheet_id == "Names":
            continue

        if sheet_id not in SHEET_PATTERNS:
            logger.warning("rowing.ergs: unknown sheet '%s' in %s", sheet_id, csv_file.name)
            continue

        month, day, workout_type = SHEET_PATTERNS[sheet_id]
        year = 2025 if month >= 9 else 2026
        test_date = date(year, month, day)

        # Parse the CSV
        results = _parse_csv_file(str(csv_file), test_date, workout_type)
        all_results.extend(results)

        logger.info(
            "rowing.ergs: '%s' → %d results (date=%s, type=%s)",
            csv_file.name,
            len(results),
            test_date,
            workout_type,
        )

    logger.info(
        "rowing.ergs: total %d results from %d sessions",
        len(all_results),
        len(set(r.test_date for r in all_results)),
    )

    _results_cache = all_results
    return all_results


def ingest_roster(data_dir: str) -> List[str]:
    """
    Parse the Names CSV into a list of athlete names.

    Args:
        data_dir: Directory containing the rowing CSV files

    Returns:
        List of athlete names in "Last, First" format
    """
    global _roster_cache
    if _roster_cache is not None:
        return _roster_cache

    names_file = Path(data_dir) / "rowing_women_2025-2026 ERGS-2-Names.csv"
    if not names_file.exists():
        logger.warning("rowing.roster: Names CSV not found")
        return []

    df = pd.read_csv(str(names_file))
    names = []
    for _, row in df.iterrows():
        last = str(row.get("Last Name", "")).strip()
        first = str(row.get("First Name", "")).strip()
        if last and last.lower() != "nan":
            names.append(f"{last}, {first}")

    _roster_cache = names
    logger.info("rowing.roster: %d athletes", len(names))
    return names


def get_rowing_data(data_dir: str) -> Tuple[List[ErgResult], List[str]]:
    """
    Get all rowing erg results and the athlete roster.

    This is the main entry point for the rowing domain.

    Args:
        data_dir: Directory containing all rowing CSV files

    Returns:
        Tuple of (all_erg_results, athlete_roster)
    """
    results = ingest_rowing_ergs(data_dir)
    roster = ingest_roster(data_dir)
    return results, roster


def clear_cache() -> None:
    """Clear module-level cache. Call this in tests."""
    global _results_cache, _roster_cache
    _results_cache = None
    _roster_cache = None


# =============================================================================
# CSV file parsing
# =============================================================================

def _extract_sheet_id(filename: str) -> Optional[str]:
    """
    Extract the sheet identifier from a rowing CSV filename.

    "rowing_women_2025-2026 ERGS-2-316 2k.csv" → "316 2k"
    "rowing_women_2025-2026 ERGS-2-Names.csv" → "Names"
    """
    # Remove the common prefix and .csv suffix
    # Pattern: "rowing_women_2025-2026 ERGS-2-<sheet_id>.csv"
    match = re.search(r"ERGS-2-(.+)\.csv$", filename)
    if match:
        return match.group(1)
    return None


def _parse_csv_file(
    filepath: str, test_date: date, workout_type: str
) -> List[ErgResult]:
    """
    Parse a single rowing CSV file into ErgResult models.

    Handles:
      - Normal athlete rows → completed results
      - "RP3" separator → switches erg_type for subsequent rows
      - "Out" section → marks athletes as absent
      - "sick"/"DNS" in split column → marks as sick/dns
    """
    df = pd.read_csv(filepath)

    if df.empty:
        return []

    results: List[ErgResult] = []
    current_erg_type = "C2"
    in_out_section = False

    # The first column is always the athlete name
    name_col = df.columns[0]

    for _, row in df.iterrows():
        name_raw = row[name_col]

        # Skip fully empty rows
        if pd.isna(name_raw) or str(name_raw).strip() == "":
            continue

        name = str(name_raw).strip()
        name_upper = name.upper()

        # ---- Section separators ----
        if name_upper in ("RP3", "BERG"):
            current_erg_type = "RP3"
            continue

        if name_upper in ("OUT", "OUT:"):
            in_out_section = True
            continue

        if name_upper in ("PROGRESSION", "PROGRESSION:"):
            in_out_section = True
            continue

        # Clean name: remove trailing asterisks (indicate notes in original)
        clean_name = re.sub(r"\s*\*+\s*$", "", name).strip()

        # ---- Athletes in the "Out" section ----
        if in_out_section:
            results.append(
                ErgResult(
                    athlete_name=clean_name,
                    test_date=test_date,
                    workout_type=workout_type,
                    status="out",
                    erg_type=current_erg_type,
                )
            )
            continue

        # ---- Check if split column indicates non-participation ----
        # The second column (index 1) is usually AVG SPLIT or TIME
        split_col = df.columns[1] if len(df.columns) > 1 else None
        split_raw = ""
        if split_col is not None:
            split_raw = str(row[split_col]).strip() if not pd.isna(row[split_col]) else ""

        if split_raw.lower() in ("sick", "dns", "dnf", "injured", "out"):
            results.append(
                ErgResult(
                    athlete_name=clean_name,
                    test_date=test_date,
                    workout_type=workout_type,
                    status=split_raw.lower(),
                    erg_type=current_erg_type,
                )
            )
            continue

        # ---- Parse the actual result based on workout type ----
        try:
            result = _parse_result_row(
                row, df.columns.tolist(), clean_name,
                test_date, workout_type, current_erg_type,
            )
            if result:
                results.append(result)
        except Exception as e:
            logger.warning(
                "rowing.parse: failed %s on %s: %s",
                clean_name, test_date, str(e),
            )

    return results


def _parse_result_row(
    row: pd.Series,
    columns: List[str],
    name: str,
    test_date: date,
    workout_type: str,
    erg_type: str,
) -> Optional[ErgResult]:
    """Dispatch to the format-specific parser based on workout type."""

    parsers = {
        "2k":      _parse_2k,
        "6k":      _parse_6k,
        "2x6k":    _parse_2x6k,
        "4x1k":    _parse_4x1k,
        "9x2k":    _parse_9x2k,
        "3x12":    _parse_3x12,
        "30min":   _parse_30min,
        "2k_prep": _parse_2k_prep,
    }

    parser = parsers.get(workout_type)
    if parser is None:
        logger.warning("rowing.parse: unknown workout type '%s'", workout_type)
        return None

    return parser(row, columns, name, test_date, erg_type)


# =============================================================================
# Format-specific parsers
# =============================================================================
# Each function handles one CSV column layout.
# They all return an ErgResult with the fields that format provides.

def _parse_2k(
    row: pd.Series, cols: List[str], name: str, test_date: date, erg_type: str
) -> ErgResult:
    """
    2k format columns:
    NAME, TIME, AVG SPLIT, AVG RATE, AVG WATTS, 500M, 1000M, 1500M, 2000M
    """
    return ErgResult(
        athlete_name=name,
        test_date=test_date,
        workout_type="2k",
        total_time=_safe_str(row.iloc[1]),
        total_time_seconds=_parse_split_to_seconds(row.iloc[1]),
        avg_split=_safe_str(row.iloc[2]),
        avg_split_seconds=_parse_split_to_seconds(row.iloc[2]),
        avg_rate=_safe_int(row.iloc[3]),
        avg_watts=_safe_float(row.iloc[4]),
        segment_splits=[
            _parse_split_to_seconds(row.iloc[i])
            for i in range(5, min(9, len(row)))
        ],
        erg_type=erg_type,
    )


def _parse_6k(
    row: pd.Series, cols: List[str], name: str, test_date: date, erg_type: str
) -> ErgResult:
    """
    6k format columns:
    NAME, SPLIT, TIME, RATE
    """
    return ErgResult(
        athlete_name=name,
        test_date=test_date,
        workout_type="6k",
        avg_split=_safe_str(row.iloc[1]),
        avg_split_seconds=_parse_split_to_seconds(row.iloc[1]),
        total_time=_safe_str(row.iloc[2]) if len(row) > 2 else None,
        total_time_seconds=_parse_split_to_seconds(row.iloc[2]) if len(row) > 2 else None,
        avg_rate=_safe_int(row.iloc[3]) if len(row) > 3 else None,
        erg_type=erg_type,
    )


def _parse_2x6k(
    row: pd.Series, cols: List[str], name: str, test_date: date, erg_type: str
) -> ErgResult:
    """
    2x6k format columns:
    NAME, AVG SPLIT, SPLIT 1, RATE 1, TIME 1, SPLIT 2, RATE 2, TIME 2
    """
    split1 = _parse_split_to_seconds(row.iloc[2]) if len(row) > 2 else None
    split2 = _parse_split_to_seconds(row.iloc[5]) if len(row) > 5 else None

    return ErgResult(
        athlete_name=name,
        test_date=test_date,
        workout_type="2x6k",
        avg_split=_safe_str(row.iloc[1]),
        avg_split_seconds=_parse_split_to_seconds(row.iloc[1]),
        interval_splits=[split1, split2],
        interval_rates=[
            _safe_int(row.iloc[3]) if len(row) > 3 else None,
            _safe_int(row.iloc[6]) if len(row) > 6 else None,
        ],
        erg_type=erg_type,
    )


def _parse_4x1k(
    row: pd.Series, cols: List[str], name: str, test_date: date, erg_type: str
) -> ErgResult:
    """
    4x1k format columns:
    NAME, AVG SPLIT, AVG WATTS, SPLIT 1, RATE 1, ..., SPLIT 4, RATE 4, NOTES
    """
    splits = []
    rates = []
    for i in range(4):
        split_idx = 3 + i * 2   # 3, 5, 7, 9
        rate_idx = 4 + i * 2    # 4, 6, 8, 10
        splits.append(
            _parse_split_to_seconds(row.iloc[split_idx])
            if split_idx < len(row) else None
        )
        rates.append(
            _safe_int(row.iloc[rate_idx])
            if rate_idx < len(row) else None
        )

    return ErgResult(
        athlete_name=name,
        test_date=test_date,
        workout_type="4x1k",
        avg_split=_safe_str(row.iloc[1]),
        avg_split_seconds=_parse_split_to_seconds(row.iloc[1]),
        avg_watts=_safe_float(row.iloc[2]),
        interval_splits=splits,
        interval_rates=rates,
        erg_type=erg_type,
    )


def _parse_9x2k(
    row: pd.Series, cols: List[str], name: str, test_date: date, erg_type: str
) -> ErgResult:
    """
    9x2k format columns:
    NAME, AVERAGE, SPLIT 1, SPLIT 2, ..., SPLIT 9, Notes
    """
    splits = [
        _parse_split_to_seconds(row.iloc[i])
        for i in range(2, min(11, len(row)))
    ]

    return ErgResult(
        athlete_name=name,
        test_date=test_date,
        workout_type="9x2k",
        avg_split=_safe_str(row.iloc[1]),
        avg_split_seconds=_parse_split_to_seconds(row.iloc[1]),
        interval_splits=splits,
        erg_type=erg_type,
    )


def _parse_3x12(
    row: pd.Series, cols: List[str], name: str, test_date: date, erg_type: str
) -> ErgResult:
    """
    3x12min format columns:
    NAME, AVG SPLIT, SPLIT 1, RATE 1, SPLIT 2, RATE 2, SPLIT 3, RATE 3
    """
    splits = []
    rates = []
    for i in range(3):
        split_idx = 2 + i * 2   # 2, 4, 6
        rate_idx = 3 + i * 2    # 3, 5, 7
        splits.append(
            _parse_split_to_seconds(row.iloc[split_idx])
            if split_idx < len(row) else None
        )
        rates.append(
            _safe_int(row.iloc[rate_idx])
            if rate_idx < len(row) else None
        )

    return ErgResult(
        athlete_name=name,
        test_date=test_date,
        workout_type="3x12",
        avg_split=_safe_str(row.iloc[1]),
        avg_split_seconds=_parse_split_to_seconds(row.iloc[1]),
        interval_splits=splits,
        interval_rates=rates,
        erg_type=erg_type,
    )


def _parse_30min(
    row: pd.Series, cols: List[str], name: str, test_date: date, erg_type: str
) -> ErgResult:
    """
    30min format columns:
    NAME, AVG SPLIT, METERS, AVG RATE
    """
    return ErgResult(
        athlete_name=name,
        test_date=test_date,
        workout_type="30min",
        avg_split=_safe_str(row.iloc[1]),
        avg_split_seconds=_parse_split_to_seconds(row.iloc[1]),
        total_meters=_safe_int(row.iloc[2]),
        avg_rate=_safe_int(row.iloc[3]) if len(row) > 3 else None,
        erg_type=erg_type,
    )


def _parse_2k_prep(
    row: pd.Series, cols: List[str], name: str, test_date: date, erg_type: str
) -> ErgResult:
    """
    2k prep format columns:
    NAME, AVG SPLIT, AVG WATTS, 500m Split, 500m Rate, 1K Split, 1K Rate, 500m Split, 500m Rate
    """
    segments = []
    rates = []
    for i in range(3):
        split_idx = 3 + i * 2   # 3, 5, 7
        rate_idx = 4 + i * 2    # 4, 6, 8
        segments.append(
            _parse_split_to_seconds(row.iloc[split_idx])
            if split_idx < len(row) else None
        )
        rates.append(
            _safe_int(row.iloc[rate_idx])
            if rate_idx < len(row) else None
        )

    return ErgResult(
        athlete_name=name,
        test_date=test_date,
        workout_type="2k_prep",
        avg_split=_safe_str(row.iloc[1]),
        avg_split_seconds=_parse_split_to_seconds(row.iloc[1]),
        avg_watts=_safe_float(row.iloc[2]),
        segment_splits=segments,
        interval_rates=rates,
        erg_type=erg_type,
    )


# =============================================================================
# Parsing helpers
# =============================================================================

def _parse_split_to_seconds(value) -> Optional[float]:
    """
    Convert a rowing split string to seconds.

    Examples:
      "1:38.9" → 98.9 seconds
      "6:35.6" → 395.6 seconds  (also works for total times)
      "sick"   → None
      "—"      → None
      NaN      → None
    """
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None

    s = str(value).strip()
    if not s or s.lower() in ("nan", "sick", "out", "dns", "dnf", "—", "-", "injured"):
        return None

    try:
        parts = s.split(":")
        if len(parts) == 2:
            return float(parts[0]) * 60 + float(parts[1])
        return float(s)
    except (ValueError, IndexError):
        return None


def _safe_float(value) -> Optional[float]:
    """Convert to float, None for NaN/invalid."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
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
    """Convert to string, None for NaN/empty."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    s = str(value).strip()
    return None if s.lower() in ("nan", "none", "") else s
