from fastapi import APIRouter, Depends, HTTPException
from typing import Dict, Any
import pandas as pd
from datetime import datetime
import os

from app.security.validation import verify_api_key
from app.ingestion.triathlon import get_triathlon_data, get_all_daily
from app.ingestion.rowing import get_rowing_data
from app.services.triathlon_heuristics import build_triathlon_summary
from app.services.rowing_heuristics import build_team_summary
from app.services.insights import generate_triathlon_insights, generate_rowing_insights
from app.models.schemas import AnalysisResponse

router = APIRouter(dependencies=[Depends(verify_api_key)])


def _write_back_to_csv(domain: str, insights: Dict[str, Any]):
    """
    Simulates the Google Sheet "Write Back" requirement.
    Since we are using CSVs for the MVP, we append the generated insights
    to a local CSV file, acting as our two-way sync.
    """
    filepath = f"data/{domain}_insights_sync.csv"
    
    # Flatten the data for CSV
    row = {
        "timestamp": datetime.now().isoformat(),
        "insights": " | ".join(insights.get("insights", [])),
        "risks": " | ".join(insights.get("risks", [])),
        "recommendations": " | ".join(insights.get("recommendations", []))
    }
    
    df = pd.DataFrame([row])
    
    # Append if exists, else write new
    if os.path.exists(filepath):
        df.to_csv(filepath, mode='a', header=False, index=False)
    else:
        df.to_csv(filepath, index=False)


@router.post("/analyze/triathlon", response_model=AnalysisResponse)
def analyze_triathlon():
    """
    1. Reads triathlon CSVs.
    2. Runs pure Python heuristics (Load, Recovery Proxy).
    3. Synthesizes with Claude 3.5.
    4. Writes insights back to CSV (simulating Google Sheet 2-way sync).
    """
    try:
        daily_path = 'data/Copy of Triathlon Training Sync-daily_summary.csv'
        activity_path = 'data/Copy of Triathlon Training Sync-activities_raw.csv'
        
        # 1. Ingestion
        all_daily = get_all_daily(daily_path)
        current_daily, current_activities = get_triathlon_data(daily_path, activity_path, date_range_days=7)
        
        # 2. Heuristics
        prev_daily = all_daily # Simplified for MVP, usually you'd slice the dates
        summary = build_triathlon_summary(current_daily, current_activities, prev_daily, 7)
        
        # 3. AI Synthesis
        report = generate_triathlon_insights(summary)
        
        # 4. Write Back (Two-Way Sync Requirement)
        _write_back_to_csv("triathlon", report.model_dump())
        
        degraded_flag = any("degraded" in s.lower() for s in report.insights)
        
        return AnalysisResponse(
            generated_at=datetime.now(),
            domain="triathlon",
            period_days=7,
            triathlon_summary=summary,
            insights=report,
            degraded=degraded_flag
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/analyze/rowing", response_model=AnalysisResponse)
def analyze_rowing():
    """
    1. Reads 16 rowing CSVs (7 formats).
    2. Runs Python heuristics (Progression, Consistency).
    3. Synthesizes team report with Claude 3.5.
    4. Writes insights back to CSV (simulating Google Sheet 2-way sync).
    """
    try:
        # 1. Ingestion
        results, roster = get_rowing_data('data')
        
        # 2. Heuristics
        summary = build_team_summary(results, roster)
        
        # 3. AI Synthesis
        report = generate_rowing_insights(summary)
        
        # 4. Write Back (Two-Way Sync Requirement)
        _write_back_to_csv("rowing", report.model_dump())
        
        degraded_flag = any("degraded" in s.lower() for s in report.insights)
        
        return AnalysisResponse(
            generated_at=datetime.now(),
            domain="rowing",
            rowing_summary=summary,
            insights=report,
            degraded=degraded_flag
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
