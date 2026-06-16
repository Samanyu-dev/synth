"""
Synth MVP — Data models.

All Pydantic schemas for the pipeline. Every data transformation targets
one of these models. Every API response is validated against them.

Design principle: the models define the contract between layers.
Ingestion produces them, heuristics consume and extend them,
synthesis summarises them, and the API returns them.

How to read this file:
  1. TRIATHLON DOMAIN — models for individual athlete training data
  2. ROWING DOMAIN — models for team erg test results  
  3. SYNTHESIS / API — models for Claude output and API responses
"""

from __future__ import annotations

from datetime import date, datetime
from typing import List, Optional

from pydantic import BaseModel, Field, field_validator


# =============================================================================
# TRIATHLON DOMAIN
# =============================================================================

class DailySummary(BaseModel):
    """
    One row from the triathlon daily_summary CSV.
    
    This is the primary data unit for triathlon analysis. Each row 
    represents one calendar day with aggregated training metrics.

    Key facts about the data:
      - 141 rows, Dec 25 2025 → May 14 2026
      - All training columns are 100% populated
      - HR data is 96% populated (missing on some rest/walk-only days)
      - Bike power: 40% (only on bike days)
      - Run pace: 44% (only on run days)
      - ALL WELLNESS COLUMNS ARE EMPTY (sleep, HRV, rhr, weight = 0%)
    """

    date: date

    # === Session counts ===
    # How many of each sport the athlete did that day
    run_count: int = 0
    bike_count: int = 0
    swim_count: int = 0
    walk_count: int = 0
    strength_count: int = 0
    other_count: int = 0
    tri_session_count: int = 0      # run + bike + swim only
    total_session_count: int = 0    # everything including walk/strength

    # === Distances (miles) ===
    run_miles: float = 0.0
    bike_miles: float = 0.0
    swim_miles: float = 0.0

    # === Volume ===
    training_minutes: float = 0.0       # total across all activities
    tri_training_minutes: float = 0.0   # run + bike + swim only
    total_elevation_ft: float = 0.0

    # === Intensity (Optional — not every day has these) ===
    avg_hr_all: Optional[float] = None          # average HR across all sessions
    max_hr_all: Optional[float] = None          # max HR across all sessions
    avg_power_bike: Optional[float] = None      # avg watts (bike days only)
    weighted_power_bike: Optional[float] = None # normalized power (bike days only)
    avg_cadence_bike: Optional[float] = None    # RPM (bike days only)
    avg_cadence_run: Optional[float] = None     # steps/min (run days only)
    avg_pace_run_min_per_mi: Optional[float] = None  # min/mile (run days only)

    # === Wellness / Recovery (ALL EMPTY in current data) ===
    # Schema is ready for when this data becomes available
    rhr: Optional[float] = None              # resting heart rate
    hrv: Optional[float] = None              # heart rate variability
    sleep_hours: Optional[float] = Field(default=None, ge=0, le=24)
    body_weight_lb: Optional[float] = None

    # === Misc ===
    sauna_mins: Optional[float] = None

    @field_validator("training_minutes", "tri_training_minutes")
    @classmethod
    def non_negative_minutes(cls, v: float) -> float:
        """Training minutes can't be negative — catch bad data early."""
        if v < 0:
            raise ValueError("Training minutes cannot be negative")
        return v


class ActivityRecord(BaseModel):
    """
    One row from the activities_raw CSV — a single workout session.

    Key facts:
      - 375 activities across 136 unique dates
      - Sport types: Walk(145), Swim(50), VirtualRide(47), 
        WeightTraining(45), VirtualRun(40), Run(27), Ride(16), Yoga(5)
      - Provides per-session granularity that daily_summary aggregates away
    
    Why we ingest this alongside daily_summary:
      - Activity-level sport type lets us analyze discipline-specific trends
      - Per-session HR lets us detect intensity patterns within a day
      - Activity names (e.g. "Zwift - Tempus Fugit") provide workout context
    """

    activity_id: str
    start_date_local: datetime
    date: date                      # derived from start_date_local
    name: Optional[str] = None      # e.g. "Afternoon Run", "Zwift - Tempus Fugit"
    sport_type: str                 # VirtualRide, Run, Swim, Walk, etc.
    trainer: bool = False           # indoor trainer session?
    commute: bool = False

    # Duration
    moving_time_sec: int = 0
    elapsed_time_sec: int = 0

    # Distance
    distance_m: float = 0.0
    distance_mi: float = 0.0

    # Elevation
    elevation_gain_m: float = 0.0
    elevation_gain_ft: float = 0.0

    # Intensity
    avg_hr: Optional[float] = None
    max_hr: Optional[float] = None
    avg_watts: Optional[float] = None
    weighted_watts: Optional[float] = None
    avg_cadence: Optional[float] = None
    kilojoules: Optional[float] = None
    calories: Optional[float] = None

    # Device & metadata
    device_name: Optional[str] = None
    suffer_score: Optional[float] = None
    perceived_exertion: Optional[float] = None


# =============================================================================
# ROWING DOMAIN
# =============================================================================

class ErgResult(BaseModel):
    """
    Normalised erg test result — one athlete, one test session.

    This is the trickiest schema because it needs to handle 7 different
    CSV formats (2k, 6k, 2x6k, 4x1k, 9x2k, 3x12, 30min). Each format
    has different columns, so most fields are Optional.

    Key facts:
      - 52 athletes across 16 test sessions (Sep 2025 → Mar 2026)
      - Each CSV file = one test session
      - Filename encodes date and workout type: "316 2k" = March 16, 2k test
      - Special rows: "sick", "Out", RP3 section separator
    """

    athlete_name: str
    test_date: date
    workout_type: str   # "2k", "6k", "2x6k", "4x1k", "9x2k", "3x12", "30min", "2k_prep"

    # === Core metrics (not all formats have all fields) ===
    avg_split: Optional[str] = None          # "1:38.9" — human-readable
    avg_split_seconds: Optional[float] = None  # 98.9 — for computation
    total_time: Optional[str] = None         # "6:35.6" (2k/6k tests)
    total_time_seconds: Optional[float] = None
    avg_rate: Optional[int] = None           # strokes per minute
    avg_watts: Optional[float] = None        # power output

    # === Interval data (variable length by workout type) ===
    # 2x6k has 2 intervals, 4x1k has 4, 9x2k has 9, 3x12 has 3
    interval_splits: List[Optional[float]] = []   # seconds per 500m
    interval_rates: List[Optional[int]] = []      # SPM per interval

    # === 2k-specific: 500m segment splits ===
    segment_splits: List[Optional[float]] = []    # 500m, 1000m, 1500m, 2000m

    # === 30min-specific ===
    total_meters: Optional[int] = None

    # === Metadata ===
    status: str = "completed"    # "completed", "sick", "out", "progression"
    erg_type: str = "C2"         # "C2" or "RP3"
    notes: Optional[str] = None


class AthleteProfile(BaseModel):
    """
    Aggregated profile for one rower across all their test sessions.

    Built by the heuristics layer from a list of ErgResults for one athlete.
    This is what drives the rowing insights — not individual test results.
    """

    name: str
    tests_completed: int = 0
    tests_missed: int = 0           # sick + out

    # === Best performances ===
    best_2k_time: Optional[str] = None
    best_2k_time_seconds: Optional[float] = None
    best_2k_split: Optional[float] = None       # seconds per 500m
    best_6k_split: Optional[float] = None
    best_2x6k_split: Optional[float] = None

    # === Progression ===
    split_improvement_pct: Optional[float] = None  # positive = getting faster
    trend: str = "insufficient_data"   # "improving", "plateau", "declining"

    # === Pacing quality ===
    consistency_score: Optional[float] = None      # std dev of splits (lower = better)
    negative_split_rate: Optional[float] = None    # % of tests with negative split

    # === Team context ===
    avg_ranking: Optional[float] = None
    alerts: List[str] = []


# =============================================================================
# SUMMARIES (what gets sent to Claude)
# =============================================================================

class TriathlonWeeklySummary(BaseModel):
    """
    Aggregated triathlon metrics for a date range.

    This is what Claude receives — pre-computed numbers, never raw rows.
    Every field here is computed by the heuristics layer.
    """

    period_days: int
    start_date: date
    end_date: date

    # Volume
    weekly_load: float = 0.0            # TRIMP-inspired: minutes × HR factor
    prev_weekly_load: float = 0.0       # previous period for comparison
    load_change_pct: float = 0.0        # week-over-week change
    total_training_minutes: float = 0.0
    tri_session_count: int = 0
    total_session_count: int = 0

    # Distances
    total_run_miles: float = 0.0
    total_bike_miles: float = 0.0
    total_swim_miles: float = 0.0

    # Sport balance (should each be ~33% for a balanced triathlete)
    run_pct: float = 0.0
    bike_pct: float = 0.0
    swim_pct: float = 0.0

    # Intensity
    avg_hr: float = 0.0
    baseline_hr: float = 0.0       # season-long average for comparison
    max_hr: float = 0.0
    avg_power: Optional[float] = None

    # Recovery signals (derived from training data since wellness is empty)
    recovery_proxy: float = 0.0
    days_since_rest: int = 0
    hr_drift_pct: float = 0.0

    # Alerts generated by heuristics
    active_alerts: List[str] = []


class RowingTeamSummary(BaseModel):
    """
    Aggregated team metrics for Claude synthesis.

    Built from all AthleteProfiles across the full season.
    """

    total_athletes: int = 0
    total_sessions: int = 0
    season_start: date
    season_end: date

    # Top performers (2k test results)
    top_5_2k: List[dict] = []

    # Team-wide progression
    athletes_improving: int = 0
    athletes_plateau: int = 0
    athletes_declining: int = 0
    athletes_insufficient: int = 0

    # Team-wide metrics
    avg_split_improvement_pct: float = 0.0
    avg_neg_split_rate: float = 0.0
    avg_consistency: float = 0.0

    # Attendance tracking
    highest_absence_name: Optional[str] = None
    highest_absence_count: int = 0

    # Alerts
    active_alerts: List[str] = []


# =============================================================================
# SYNTHESIS / API RESPONSE
# =============================================================================

class InsightReport(BaseModel):
    """
    Claude's structured response — validated before returning to the user.

    Anti-hallucination measures:
      - Array lengths bounded (1-5 insights, 0-4 risks, 1-5 recommendations)
      - Each string capped at 200 chars (long strings = model is rambling)
      - Validated with Pydantic before it reaches the API response
    """

    insights: List[str] = Field(min_length=1, max_length=5)
    risks: List[str] = Field(min_length=0, max_length=4)
    recommendations: List[str] = Field(min_length=1, max_length=5)

    @field_validator("insights", "risks", "recommendations")
    @classmethod
    def cap_string_length(cls, v: List[str]) -> List[str]:
        """Prevent Claude from writing essays in each array element."""
        return [s[:200] for s in v]


class AnalysisResponse(BaseModel):
    """
    Top-level API response for any /analyze endpoint.

    The 'degraded' flag tells the caller if Claude was unavailable
    and we fell back to heuristic flags only.
    """

    generated_at: datetime
    domain: str             # "triathlon", "rowing", "combined"
    period_days: Optional[int] = None
    degraded: bool = False  # True if Claude was unavailable

    # Domain-specific summaries (one or both populated)
    triathlon_summary: Optional[TriathlonWeeklySummary] = None
    rowing_summary: Optional[RowingTeamSummary] = None

    # Claude insights (None if degraded)
    insights: Optional[InsightReport] = None

    # Fallback alerts (populated when degraded=True)
    fallback_alerts: List[str] = []
