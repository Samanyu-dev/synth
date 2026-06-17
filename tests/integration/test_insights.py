"""
Integration tests for the Insights service using a mocked Claude client.
Ensures prompt construction, JSON parsing, and fallback logic work.
"""

import os
os.environ["ANTHROPIC_API_KEY"] = "mock_key_for_testing"

from unittest.mock import MagicMock, patch

from app.models.schemas import (
    InsightReport,
    RowingTeamSummary,
    TriathlonWeeklySummary,
)
from app.services.insights import generate_triathlon_insights, generate_rowing_insights

import pytest
from datetime import date


@pytest.fixture
def mock_tri_summary():
    return TriathlonWeeklySummary(
        period_days=7,
        start_date=date(2026, 5, 8),
        end_date=date(2026, 5, 14),
        weekly_load=600.0,
        load_change_pct=15.0,
        total_training_minutes=400.0,
        tri_session_count=5,
        total_session_count=6,
        total_run_miles=15.0,
        total_bike_miles=50.0,
        total_swim_miles=1.5,
        run_pct=25.0,
        bike_pct=70.0,
        swim_pct=5.0,
        avg_hr=145.0,
        baseline_hr=140.0,
        max_hr=180.0,
        recovery_proxy=0.8,
        days_since_rest=6,
        hr_drift_pct=3.5,
        active_alerts=["NO_REST_DAYS_6"]
    )


@patch("app.services.insights.Anthropic")
def test_generate_triathlon_insights_success(mock_anthropic, mock_tri_summary):
    # Mock the anthropic client response
    mock_client = MagicMock()
    mock_anthropic.return_value = mock_client
    
    mock_response = MagicMock()
    mock_response.content = [
        MagicMock(text='{"insights": ["Good volume this week.", "Bike focus."], "risks": ["No rest days.", "HR drift."], "recommendations": ["Take a rest day."]}')
    ]
    mock_client.messages.create.return_value = mock_response

    report = generate_triathlon_insights(mock_tri_summary)

    # Validate parsing and schema matching
    assert isinstance(report, InsightReport)
    assert len(report.insights) == 2
    assert report.insights[0] == "Good volume this week."
    assert len(report.risks) == 2
    assert len(report.recommendations) == 1
    
    # Verify the prompt contained our heuristic data
    call_args = mock_client.messages.create.call_args[1]
    prompt = call_args["messages"][0]["content"]
    assert "600.0" in prompt
    assert "15.0" in prompt
    assert "NO_REST_DAYS_6" in prompt


@patch("app.services.insights.Anthropic")
def test_generate_triathlon_insights_fallback_on_api_error(mock_anthropic, mock_tri_summary):
    from anthropic import APIError
    
    # Mock an API error
    mock_anthropic.side_effect = APIError("API Error", MagicMock(), body=None)

    report = generate_triathlon_insights(mock_tri_summary)

    # Should gracefully degrade to heuristic alerts
    assert isinstance(report, InsightReport)
    assert "degraded mode" in report.insights[0].lower()
    assert len(report.risks) == 1
    assert "NO_REST_DAYS_6" in report.risks[0]
