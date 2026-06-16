"""
Rowing heuristics engine.

Calculates deterministic metrics for the team and individual athletes.
Handles tracking progression across multiple erg tests, calculating
pacing consistency (standard deviation of splits), and aggregating
team-wide performance trends.
"""

from __future__ import annotations

import statistics
from datetime import date
from typing import Dict, List, Optional

from app.models.schemas import AthleteProfile, ErgResult, RowingTeamSummary


def build_team_summary(results: List[ErgResult], roster: List[str]) -> RowingTeamSummary:
    """
    Build a team-wide summary and individual profiles for all athletes.
    
    This converts hundreds of individual test results into a single 
    structured team overview and a list of detailed athlete profiles.
    """
    if not results:
        return RowingTeamSummary(season_start=date.today(), season_end=date.today())

    season_start = min(r.test_date for r in results)
    season_end = max(r.test_date for r in results)
    
    # Group results by athlete
    athlete_results: Dict[str, List[ErgResult]] = {name: [] for name in roster}
    for r in results:
        if r.athlete_name in athlete_results:
            athlete_results[r.athlete_name].append(r)
        else:
            # Handle athletes in results who aren't in the roster sheet
            athlete_results[r.athlete_name] = [r]

    # Build profiles
    profiles = []
    for name, user_results in athlete_results.items():
        if user_results:
            profiles.append(_build_athlete_profile(name, user_results))

    # Aggregate Team Metrics
    improving = sum(1 for p in profiles if p.trend == "improving")
    plateau = sum(1 for p in profiles if p.trend == "plateau")
    declining = sum(1 for p in profiles if p.trend == "declining")
    insufficient = sum(1 for p in profiles if p.trend == "insufficient_data")
    
    # Avg improvement (only for those who improved/declined)
    improvements = [p.split_improvement_pct for p in profiles if p.split_improvement_pct is not None]
    avg_improvement = sum(improvements) / len(improvements) if improvements else 0.0
    
    # Top 2k performers
    two_k_results = [r for r in results if r.workout_type == "2k" and r.status == "completed" and r.total_time_seconds]
    # Keep the best 2k for each athlete
    best_2k_by_athlete = {}
    for r in two_k_results:
        if r.athlete_name not in best_2k_by_athlete or r.total_time_seconds < best_2k_by_athlete[r.athlete_name].total_time_seconds:
            best_2k_by_athlete[r.athlete_name] = r
            
    top_2k_sorted = sorted(best_2k_by_athlete.values(), key=lambda x: x.total_time_seconds)
    top_5 = [
        {"name": r.athlete_name, "time": r.total_time, "split_sec": r.avg_split_seconds}
        for r in top_2k_sorted[:5]
    ]
    
    # Attendance
    absences = {p.name: p.tests_missed for p in profiles}
    highest_absence_name = max(absences, key=absences.get) if absences else None
    highest_absence_count = absences[highest_absence_name] if highest_absence_name else 0

    alerts = []
    if declining > len(profiles) * 0.2:
        alerts.append("TEAM_WIDE_FATIGUE_POSSIBLE")
    if highest_absence_count >= 3:
        alerts.append("HIGH_INDIVIDUAL_ABSENCE_RATE")

    return RowingTeamSummary(
        total_athletes=len(profiles),
        total_sessions=len(set(r.test_date for r in results)),
        season_start=season_start,
        season_end=season_end,
        top_5_2k=top_5,
        athletes_improving=improving,
        athletes_plateau=plateau,
        athletes_declining=declining,
        athletes_insufficient=insufficient,
        avg_split_improvement_pct=round(avg_improvement, 2),
        avg_neg_split_rate=0.0,  # Could be aggregated from profiles
        avg_consistency=0.0,     # Could be aggregated from profiles
        highest_absence_name=highest_absence_name,
        highest_absence_count=highest_absence_count,
        active_alerts=alerts,
    )


# =============================================================================
# Core Heuristic Functions
# =============================================================================

def _build_athlete_profile(name: str, results: List[ErgResult]) -> AthleteProfile:
    """Build a detailed profile for a single athlete based on all their tests."""
    completed = [r for r in results if r.status == "completed"]
    missed = [r for r in results if r.status in ("sick", "out", "dns")]
    
    # Best performances
    best_2k = _get_best_result(completed, "2k")
    best_6k = _get_best_result(completed, "6k")
    best_2x6k = _get_best_result(completed, "2x6k")
    
    # Progression: compare first and last test of same type (e.g. 2k)
    # If they only have one 2k, try 6k.
    trend = "insufficient_data"
    improvement_pct = None
    
    for w_type in ["2k", "6k", "2x6k"]:
        type_results = sorted([r for r in completed if r.workout_type == w_type], key=lambda x: x.test_date)
        if len(type_results) >= 2:
            first_split = type_results[0].avg_split_seconds
            last_split = type_results[-1].avg_split_seconds
            if first_split and last_split:
                # Positive pct means faster (split time decreased)
                improvement_pct = ((first_split - last_split) / first_split) * 100
                if improvement_pct > 1.0:
                    trend = "improving"
                elif improvement_pct < -1.0:
                    trend = "declining"
                else:
                    trend = "plateau"
                break # Found a valid progression metric
                
    # Pacing consistency: std dev of interval splits across multi-piece tests
    consistency_scores = []
    neg_split_count = 0
    multi_piece_tests = [r for r in completed if r.workout_type in ("2x6k", "4x1k", "3x12", "9x2k")]
    
    for r in multi_piece_tests:
        valid_splits = [s for s in r.interval_splits if s is not None]
        if len(valid_splits) >= 2:
            try:
                std_dev = statistics.stdev(valid_splits)
                consistency_scores.append(std_dev)
                # Negative split: last interval is faster than first
                if valid_splits[-1] < valid_splits[0]:
                    neg_split_count += 1
            except statistics.StatisticsError:
                pass
                
    avg_consistency = sum(consistency_scores) / len(consistency_scores) if consistency_scores else None
    neg_split_rate = (neg_split_count / len(multi_piece_tests) * 100) if multi_piece_tests else None

    # Alerts
    alerts = []
    if len(missed) >= 3:
        alerts.append("CHRONIC_ABSENCE")
    if trend == "declining":
        alerts.append("PERFORMANCE_DECLINE")
    if avg_consistency and avg_consistency > 5.0:
        alerts.append("ERRATIC_PACING")

    return AthleteProfile(
        name=name,
        tests_completed=len(completed),
        tests_missed=len(missed),
        best_2k_time=best_2k.total_time if best_2k else None,
        best_2k_time_seconds=best_2k.total_time_seconds if best_2k else None,
        best_2k_split=best_2k.avg_split_seconds if best_2k else None,
        best_6k_split=best_6k.avg_split_seconds if best_6k else None,
        best_2x6k_split=best_2x6k.avg_split_seconds if best_2x6k else None,
        split_improvement_pct=round(improvement_pct, 2) if improvement_pct is not None else None,
        trend=trend,
        consistency_score=round(avg_consistency, 2) if avg_consistency is not None else None,
        negative_split_rate=round(neg_split_rate, 1) if neg_split_rate is not None else None,
        alerts=alerts
    )


def _get_best_result(results: List[ErgResult], workout_type: str) -> Optional[ErgResult]:
    """Find the result with the lowest average split for a given workout type."""
    type_results = [r for r in results if r.workout_type == workout_type and r.avg_split_seconds is not None]
    if not type_results:
        return None
    return min(type_results, key=lambda x: x.avg_split_seconds)
