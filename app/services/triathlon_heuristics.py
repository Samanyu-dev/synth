"""
Triathlon heuristics engine.

Calculates deterministic metrics from ingested Pydantic models.
This layer guarantees Claude never sees raw rows, only pre-computed,
mathematically sound summaries.

Key Heuristics:
1. Training Load (TRIMP-inspired)
2. Recovery Proxy (compensating for empty wellness data)
3. Alert Generation (spikes, fatigue)
"""

from __future__ import annotations

from datetime import date
from typing import List
import os
import numpy as np
import xgboost as xgb

from app.models.schemas import ActivityRecord, DailySummary, TriathlonWeeklySummary

# Load XGBoost Model
MODEL_PATH = os.path.join(os.path.dirname(__file__), "..", "models", "xgboost_injury_model.json")
try:
    xgb_model = xgb.XGBClassifier()
    xgb_model.load_model(MODEL_PATH)
except Exception:
    xgb_model = None


def build_triathlon_summary(
    current_daily: List[DailySummary],
    current_activities: List[ActivityRecord],
    prev_daily: List[DailySummary] = None,
    period_days: int = 7,
) -> TriathlonWeeklySummary:
    """
    Build a weekly summary for Claude from raw daily and activity records.
    
    Args:
        current_daily: Daily records for the target period.
        current_activities: Activity records for the target period.
        prev_daily: Daily records for the preceding period (for baseline comparison).
        period_days: The length of the summary period in days.
    """
    if not current_daily:
        raise ValueError("Cannot build summary without current daily records")

    # Dates
    start_date = current_daily[0].date
    end_date = current_daily[-1].date
    
    # Volume
    total_training_minutes = sum(d.training_minutes for d in current_daily)
    tri_session_count = sum(d.tri_session_count for d in current_daily)
    total_session_count = sum(d.total_session_count for d in current_daily)
    
    total_run_miles = sum(d.run_miles for d in current_daily)
    total_bike_miles = sum(d.bike_miles for d in current_daily)
    total_swim_miles = sum(d.swim_miles for d in current_daily)
    
    total_miles = total_run_miles + total_bike_miles + total_swim_miles
    
    # Sport balance
    run_pct = (total_run_miles / total_miles * 100) if total_miles > 0 else 0
    bike_pct = (total_bike_miles / total_miles * 100) if total_miles > 0 else 0
    swim_pct = (total_swim_miles / total_miles * 100) if total_miles > 0 else 0

    # Intensity
    hrs = [d.avg_hr_all for d in current_daily if d.avg_hr_all]
    avg_hr = sum(hrs) / len(hrs) if hrs else 0.0
    
    max_hrs = [d.max_hr_all for d in current_daily if d.max_hr_all]
    max_hr = max(max_hrs) if max_hrs else 0.0

    power = [d.avg_power_bike for d in current_daily if d.avg_power_bike]
    avg_power = sum(power) / len(power) if power else None

    # Baselines from previous period
    prev_hrs = [d.avg_hr_all for d in prev_daily if d.avg_hr_all] if prev_daily else []
    baseline_hr = sum(prev_hrs) / len(prev_hrs) if prev_hrs else avg_hr
    
    prev_load = _calculate_load(prev_daily) if prev_daily else 0.0

    # Current Load & Trends
    weekly_load = _calculate_load(current_daily)
    load_change_pct = ((weekly_load - prev_load) / prev_load * 100) if prev_load > 0 else 0.0

    # Recovery Proxy
    days_since_rest = _calculate_days_since_rest(current_daily)
    hr_drift_pct = ((avg_hr - baseline_hr) / baseline_hr * 100) if baseline_hr > 0 else 0.0
    recovery_proxy = _calculate_recovery_proxy(days_since_rest, hr_drift_pct, load_change_pct)

    # ML Predictive Injury Risk
    injury_risk_pct = 0.0
    if xgb_model is not None:
        try:
            features = np.array([[load_change_pct, days_since_rest, hr_drift_pct, recovery_proxy]])
            prob = xgb_model.predict_proba(features)[0][1]
            injury_risk_pct = round(float(prob) * 100, 1)
        except Exception:
            pass

    # Alerts
    alerts = _generate_alerts(
        weekly_load=weekly_load,
        load_change_pct=load_change_pct,
        days_since_rest=days_since_rest,
        hr_drift_pct=hr_drift_pct,
        recovery_proxy=recovery_proxy,
        injury_risk_pct=injury_risk_pct,
    )

    return TriathlonWeeklySummary(
        period_days=period_days,
        start_date=start_date,
        end_date=end_date,
        weekly_load=round(weekly_load, 1),
        prev_weekly_load=round(prev_load, 1),
        load_change_pct=round(load_change_pct, 1),
        total_training_minutes=round(total_training_minutes, 1),
        tri_session_count=tri_session_count,
        total_session_count=total_session_count,
        total_run_miles=round(total_run_miles, 2),
        total_bike_miles=round(total_bike_miles, 2),
        total_swim_miles=round(total_swim_miles, 2),
        run_pct=round(run_pct, 1),
        bike_pct=round(bike_pct, 1),
        swim_pct=round(swim_pct, 1),
        avg_hr=round(avg_hr, 1),
        baseline_hr=round(baseline_hr, 1),
        max_hr=round(max_hr, 1),
        avg_power=round(avg_power, 1) if avg_power else None,
        recovery_proxy=round(recovery_proxy, 2),
        days_since_rest=days_since_rest,
        hr_drift_pct=round(hr_drift_pct, 1),
        injury_risk_pct=injury_risk_pct,
        active_alerts=alerts,
    )


# =============================================================================
# Core Heuristic Functions
# =============================================================================

def _calculate_load(daily_records: List[DailySummary]) -> float:
    """
    Calculate a TRIMP-inspired training load.
    Formula: training_minutes * (avg_hr / 150)
    If HR is missing, assumes a moderate factor of 0.8.
    """
    total_load = 0.0
    for d in daily_records:
        intensity_factor = (d.avg_hr_all / 150.0) if d.avg_hr_all else 0.8
        total_load += (d.training_minutes * intensity_factor)
    return total_load


def _calculate_days_since_rest(daily_records: List[DailySummary]) -> int:
    """Count consecutive days with training_minutes > 0 looking backwards from the end."""
    days = 0
    for d in reversed(daily_records):
        if d.training_minutes > 0:
            days += 1
        else:
            break
    return days


def _calculate_recovery_proxy(
    days_since_rest: int, 
    hr_drift_pct: float, 
    load_change_pct: float
) -> float:
    """
    Calculate a Recovery Proxy score (0.0 to 1.0, higher is better).
    Used because true wellness data (sleep/HRV) is completely missing.
    
    Penalizes:
    - Many consecutive days without rest
    - High positive HR drift (working harder for same output)
    - Massive load spikes
    """
    score = 1.0
    
    # Rest penalty: lose 0.1 for every day over 4 without rest
    if days_since_rest > 4:
        score -= (days_since_rest - 4) * 0.1
        
    # HR drift penalty: if HR is elevated by >3% compared to baseline
    if hr_drift_pct > 3.0:
        score -= (hr_drift_pct / 10.0)
        
    # Load spike penalty
    if load_change_pct > 25.0:
        score -= 0.2
        
    return max(0.0, min(1.0, score))


def _generate_alerts(
    weekly_load: float,
    load_change_pct: float,
    days_since_rest: int,
    hr_drift_pct: float,
    recovery_proxy: float,
    injury_risk_pct: float = 0.0,
) -> List[str]:
    """Generate deterministic alert flags based on heuristic thresholds."""
    alerts = []
    
    if load_change_pct > 30.0:
        alerts.append("ACUTE_LOAD_SPIKE")
    elif load_change_pct < -30.0:
        alerts.append("ACUTE_LOAD_DROP")
        
    if days_since_rest >= 7:
        alerts.append("NO_REST_7_DAYS")
        
    if hr_drift_pct > 5.0:
        alerts.append("ELEVATED_HR_DRIFT")
        
    if recovery_proxy < 0.4:
        alerts.append("POOR_RECOVERY_PROXY")
        
    if injury_risk_pct > 70.0:
        alerts.append("HIGH_PREDICTIVE_INJURY_RISK")
        
    return alerts
