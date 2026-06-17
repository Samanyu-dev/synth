"""
Claude AI Synthesis Engine.

Takes pre-computed heuristic summaries and uses Anthropic's Claude 3.5 Sonnet
to generate human-readable insights, risks, and recommendations.

Features:
- Strict JSON output forcing (using Claude's prompt capabilities).
- Pydantic validation of the LLM response to prevent hallucination.
- Graceful degradation: if the API fails, it returns a degraded InsightReport
  based purely on the deterministic heuristic alerts.
"""

import json
import logging
from typing import Optional

from anthropic import Anthropic, APIError, APITimeoutError

from app.config import get_settings
from app.models.schemas import (
    InsightReport,
    RowingTeamSummary,
    TriathlonWeeklySummary,
)

logger = logging.getLogger("synth.services.insights")


def generate_triathlon_insights(summary: TriathlonWeeklySummary) -> InsightReport:
    """Generate AI insights for a single triathlete based on their weekly summary."""
    prompt = f"""
You are an elite endurance sports data analyst and coach.
Analyze the following weekly triathlon training summary and provide insights, risks, and recommendations.

DATA:
- Period: {summary.period_days} days ({summary.start_date} to {summary.end_date})
- Total Training Minutes: {summary.total_training_minutes}
- Training Load: {summary.weekly_load} (Change from last week: {summary.load_change_pct}%)
- Total Sessions: {summary.total_session_count} (Triathlon specific: {summary.tri_session_count})
- Distances: Run {summary.total_run_miles}mi, Bike {summary.total_bike_miles}mi, Swim {summary.total_swim_miles}mi
- Balance: Run {summary.run_pct}%, Bike {summary.bike_pct}%, Swim {summary.swim_pct}%
- Intensity: Avg HR {summary.avg_hr} bpm (Baseline {summary.baseline_hr} bpm)
- Days Since Rest: {summary.days_since_rest}
- Recovery Proxy Score: {summary.recovery_proxy} / 1.0
- Deterministic Alerts: {', '.join(summary.active_alerts) if summary.active_alerts else 'None'}

INSTRUCTIONS:
1. Provide exactly 1 to 5 factual, data-backed insights.
2. Provide exactly 0 to 4 risks based on the load changes, lack of rest, or alerts.
3. Provide exactly 1 to 5 actionable coaching recommendations.
4. Keep each string under 200 characters. Be concise. Do not hallucinate data that is not provided above.
5. Return ONLY a valid JSON object matching the requested schema. Do not wrap it in markdown blockquotes like ```json.
"""
    return _call_claude(prompt, fallback_alerts=summary.active_alerts)


def generate_rowing_insights(summary: RowingTeamSummary) -> InsightReport:
    """Generate AI insights for a rowing team based on their season summary."""
    top_performers = ", ".join([f"{p['name']} ({p['time']})" for p in summary.top_5_2k])
    
    prompt = f"""
You are an elite rowing coach and team performance analyst.
Analyze the following team-wide erg test summary and provide insights, risks, and recommendations.

DATA:
- Team Size: {summary.total_athletes} athletes
- Total Test Sessions: {summary.total_sessions}
- Season Range: {summary.season_start} to {summary.season_end}
- Team Progression: {summary.athletes_improving} improving, {summary.athletes_plateau} plateauing, {summary.athletes_declining} declining
- Average Split Improvement: {summary.avg_split_improvement_pct}%
- Top 2k Performers: {top_performers}
- Highest Absence: {summary.highest_absence_name} ({summary.highest_absence_count} missed tests)
- Deterministic Alerts: {', '.join(summary.active_alerts) if summary.active_alerts else 'None'}

INSTRUCTIONS:
1. Provide exactly 1 to 5 factual, data-backed insights focusing on team-wide trends.
2. Provide exactly 0 to 4 risks based on the declining athletes, absences, or alerts.
3. Provide exactly 1 to 5 actionable coaching recommendations for the team.
4. Keep each string under 200 characters. Be concise. Do not hallucinate data that is not provided above.
5. Return ONLY a valid JSON object matching the requested schema. Do not wrap it in markdown blockquotes like ```json.
"""
    return _call_claude(prompt, fallback_alerts=summary.active_alerts)


def _call_claude(prompt: str, fallback_alerts: list[str]) -> InsightReport:
    """
    Execute the API call to Anthropic and parse the JSON response.
    Implements graceful fallback if the API call fails or times out.
    """
    settings = get_settings()
    
    # Define the strict JSON schema we want Claude to return
    # This is a powerful prompt engineering technique for deterministic JSON
    json_schema = {
        "insights": ["insight 1", "insight 2"],
        "risks": ["risk 1"],
        "recommendations": ["recommendation 1"]
    }
    
    system_prompt = f"You are a strict JSON-only API. You output ONLY valid JSON matching this schema: {json.dumps(json_schema)}. Do not output any conversational text."

    try:
        client = Anthropic(api_key=settings.anthropic_api_key)
        response = client.messages.create(
            model=settings.claude_model,
            max_tokens=settings.claude_max_tokens,
            system=system_prompt,
            messages=[
                {"role": "user", "content": prompt}
            ],
            temperature=0.2,  # Low temperature for more deterministic, factual output
        )
        
        # Parse the response
        content = response.content[0].text.strip()
        
        # Sometimes models wrap JSON in markdown despite instructions
        if content.startswith("```json"):
            content = content[7:]
        if content.startswith("```"):
            content = content[3:]
        if content.endswith("```"):
            content = content[:-3]
            
        parsed_json = json.loads(content.strip())
        
        # Pydantic validation - this guarantees the schema matches our app's contract
        return InsightReport.model_validate(parsed_json)

    except (APIError, APITimeoutError) as e:
        logger.error(f"Claude API failed: {str(e)}")
        return _fallback_report(fallback_alerts, error="AI service unavailable")
    except json.JSONDecodeError as e:
        logger.error(f"Claude returned invalid JSON: {str(e)} | Content: {content}")
        return _fallback_report(fallback_alerts, error="AI format error")
    except Exception as e:
        logger.error(f"Validation or unexpected error in Claude synthesis: {str(e)}")
        return _fallback_report(fallback_alerts, error="AI validation error")


def _fallback_report(alerts: list[str], error: str) -> InsightReport:
    """
    Generate a degraded report purely from heuristics if the LLM fails.
    This guarantees the system never goes completely down.
    """
    insights = [f"System running in degraded mode ({error})."]
    if alerts:
        insights.append(f"Heuristics triggered {len(alerts)} automated flags.")
    else:
        insights.append("Heuristics detected no immediate anomalies.")
        
    risks = [f"ALERT: {alert}" for alert in alerts[:4]] # max 4 per schema
    
    recs = ["Review automated heuristic alerts.", "Try generating the report again later."]
    
    return InsightReport(
        insights=insights,
        risks=risks,
        recommendations=recs
    )
