"""
Gemini AI Synthesis Engine.

Takes pre-computed heuristic summaries and uses Gemini 2.5 Flash
to generate human-readable insights, risks, and recommendations.

Features:
- Structured Output to ensure valid JSON responses.
- Pydantic validation of the LLM response to prevent hallucination.
- Graceful degradation: if the API fails, it returns a degraded InsightReport
  based purely on the deterministic heuristic alerts.
"""

import json
import logging
from typing import Optional

from google import genai
from google.genai import types

from app.config import get_settings
from app.models.schemas import (
    InsightReport,
    RowingTeamSummary,
    TriathlonWeeklySummary,
)
from app.services.rag import query_historical_context

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
"""
    
    # RAG Injection
    query = f"Triathlon training, {summary.period_days} days, load change {summary.load_change_pct}%, alerts: {', '.join(summary.active_alerts)}"
    history = query_historical_context(query)
    if history:
        prompt += f"\nRELEVANT HISTORICAL CONTEXT (from past 5 years):\n{history}\n"

    prompt += """
INSTRUCTIONS:
1. Provide exactly 1 to 5 factual, data-backed insights.
2. Provide exactly 0 to 4 risks based on the load changes, lack of rest, or alerts.
3. Provide exactly 1 to 5 actionable coaching recommendations.
4. Keep each string under 200 characters. Be concise. Do not hallucinate data that is not provided above.
"""
    return _call_gemini(prompt, fallback_alerts=summary.active_alerts)


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
"""
    
    # RAG Injection
    query = f"Rowing team progression, {summary.athletes_declining} declining, absences {summary.highest_absence_count}, alerts: {', '.join(summary.active_alerts)}"
    history = query_historical_context(query)
    if history:
        prompt += f"\nRELEVANT HISTORICAL CONTEXT (from past 5 years):\n{history}\n"

    prompt += """
INSTRUCTIONS:
1. Provide exactly 1 to 5 factual, data-backed insights focusing on team-wide trends.
2. Provide exactly 0 to 4 risks based on the declining athletes, absences, or alerts.
3. Provide exactly 1 to 5 actionable coaching recommendations for the team.
4. Keep each string under 200 characters. Be concise. Do not hallucinate data that is not provided above.
"""
    return _call_gemini(prompt, fallback_alerts=summary.active_alerts)


def _call_gemini(prompt: str, fallback_alerts: list[str]) -> InsightReport:
    """
    Execute the API call to Gemini and parse the JSON response.
    Implements graceful fallback if the API call fails or times out.
    """
    settings = get_settings()
    
    try:
        if not settings.gemini_api_key:
            raise ValueError("GEMINI_API_KEY is not set.")

        client = genai.Client(api_key=settings.gemini_api_key)
        
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=InsightReport,
                temperature=0.2,
            )
        )
        
        if hasattr(response, "parsed") and response.parsed:
            return response.parsed
        else:
            return InsightReport.model_validate_json(response.text)

    except Exception as e:
        logger.error(f"Gemini API or validation failed: {str(e)}")
        
        # Fallback to Anthropic Claude if Gemini fails
        if settings.anthropic_api_key:
            logger.info("Attempting fallback to Anthropic Claude 3.5 Sonnet...")
            try:
                import anthropic
                anthropic_client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
                
                # Anthropic doesn't support the same strict JSON schema enforcing as Gemini out of the box easily,
                # but we can instruct it to return raw JSON and parse it.
                claude_prompt = prompt + "\n\nReturn ONLY a raw JSON object with keys: 'insights' (list of strings), 'risks' (list of strings), 'recommendations' (list of strings). No markdown formatting or extra text."
                
                message = anthropic_client.messages.create(
                    model="claude-3-5-sonnet-20241022",
                    max_tokens=1000,
                    temperature=0.2,
                    messages=[
                        {"role": "user", "content": claude_prompt}
                    ]
                )
                
                response_text = message.content[0].text
                # Clean up any potential markdown wrapper
                if response_text.startswith("```json"):
                    response_text = response_text[7:]
                if response_text.endswith("```"):
                    response_text = response_text[:-3]
                    
                return InsightReport.model_validate_json(response_text.strip())
                
            except Exception as claude_e:
                logger.error(f"Claude fallback also failed: {str(claude_e)}")
                return _fallback_report(fallback_alerts, error="Both AI services unavailable")
                
        return _fallback_report(fallback_alerts, error="Gemini API unavailable")


def _fallback_report(alerts: list[str], error: str) -> InsightReport:
    """
    Generate a degraded report purely from heuristics if the LLM fails.
    """
    insights = [f"System running in degraded mode ({error})."]
    if alerts:
        insights.append(f"Heuristics triggered {len(alerts)} automated flags.")
    else:
        insights.append("Heuristics detected no immediate anomalies.")
        
    risks = [f"ALERT: {alert}" for alert in alerts[:4]] 
    
    recs = ["Review automated heuristic alerts.", "Try generating the report again later."]
    
    return InsightReport(
        insights=insights,
        risks=risks,
        recommendations=recs
    )
