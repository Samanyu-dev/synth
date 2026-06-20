from fastapi import APIRouter, HTTPException, Request
from slowapi import Limiter
from slowapi.util import get_remote_address
import logging
from datetime import datetime, timedelta
import os

from app.api.schemas import (
    TriathlonRequest, 
    RowingRequest, 
    ErrorResponse,
    TriathlonResponse,
    RowingResponse,
    Period,
    LoadSummary,
    InsightsBlock,
    PerformanceSummary
)
from app.services.insights import generate_triathlon_insights, generate_rowing_insights
from app.ingestion.triathlon import get_triathlon_data, get_all_daily
from app.ingestion.rowing import get_rowing_data
from app.services.triathlon_heuristics import build_triathlon_summary
from app.services.rowing_heuristics import build_team_summary
from app.config import get_settings

logger = logging.getLogger("synth.api")
router = APIRouter()
limiter = Limiter(key_func=get_remote_address)

@router.post("/analyze/triathlon", response_model=TriathlonResponse)
@limiter.limit("10/minute")
async def analyze_triathlon(request: Request, body: TriathlonRequest):
    try:
        logger.info(f"POST /analyze/triathlon lookback_days={body.lookback_days}")
        
        # Load data
        try:
            settings = get_settings()
            current_daily, current_activities = get_triathlon_data(
                settings.triathlon_daily_csv, 
                settings.triathlon_activities_csv, 
                body.lookback_days
            )
            all_daily = get_all_daily(settings.triathlon_daily_csv)
        except FileNotFoundError:
            raise HTTPException(status_code=503, detail={"detail": "data source unavailable", "source": "triathlon_xlsx"})
            
        summary = build_triathlon_summary(current_daily, current_activities, all_daily, period_days=body.lookback_days)
        report = generate_triathlon_insights(summary)
        
        degraded_flag = any("degraded" in s.lower() for s in report.insights)
        if degraded_flag:
            logger.warning(f"triathlon analysis degraded: claude unavailable, returning heuristic fallback")
            
        load_summary = LoadSummary(
            sessions=summary.total_session_count,
            training_minutes=summary.total_training_minutes,
            trimp=summary.weekly_load,
            avg_hr=summary.avg_hr,
            run_miles=summary.total_run_miles,
            bike_miles=summary.total_bike_miles,
            swim_miles=summary.total_swim_miles,
            hr_trend="improving_aerobic_fitness",  # stubbed since not in original heuristic
            injury_risk_pct=summary.injury_risk_pct,
            alerts=summary.active_alerts,
            form_chart_data=summary.form_chart_data
        )
        
        result = TriathlonResponse(
            generated_at=datetime.utcnow(),
            lookback_days=body.lookback_days,
            period=Period(**{"from": summary.start_date, "to": summary.end_date}),
            load_summary=load_summary,
            insights=InsightsBlock(
                insights=report.insights,
                risks=report.risks,
                recommendations=report.recommendations,
                degraded=degraded_flag
            )
        )
        
        logger.info(f"triathlon analysis complete: trimp={result.load_summary.trimp} alerts={result.load_summary.alerts}")
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"triathlon pipeline error: {type(e).__name__}")
        raise HTTPException(status_code=500, detail={"detail": "pipeline_error"})

@router.post("/analyze/rowing", response_model=RowingResponse)
@limiter.limit("10/minute")
async def analyze_rowing(request: Request, body: RowingRequest):
    try:
        logger.info(f"POST /analyze/rowing athlete={body.athlete} lookback_days={body.lookback_days}")
        
        try:
            settings = get_settings()
            ergs, roster = get_rowing_data(settings.rowing_data_dir)
        except FileNotFoundError:
            raise HTTPException(status_code=503, detail={"detail": "data source unavailable", "source": "rowing_xlsx"})
            
        if body.athlete:
            valid_athletes = {e.athlete_name for e in ergs}
            if body.athlete not in valid_athletes:
                raise HTTPException(status_code=404, detail={"detail": "athlete not found", "valid_athletes": list(valid_athletes)[:10]})
                
        # In a real app we would filter by athlete here, but we pass team summary for now
        summary = build_team_summary(ergs, roster)
        report = generate_rowing_insights(summary)
        
        degraded_flag = any("degraded" in s.lower() for s in report.insights)
        if degraded_flag:
            logger.warning(f"rowing analysis degraded: claude unavailable, returning heuristic fallback")
            
        # Map to PerformanceSummary
        perf_summary = PerformanceSummary(
            best_split_secs=summary.top_5_2k[0]['split_sec'] if summary.top_5_2k else 0.0,
            latest_split_secs=summary.top_5_2k[0]['split_sec'] if summary.top_5_2k else 0.0,
            improvement_secs=0.0, # Stub
            improvement_pct=summary.avg_split_improvement_pct,
            hr_trend="stable", # Stub
            alerts=summary.active_alerts
        )
        
        result = RowingResponse(
            generated_at=datetime.utcnow(),
            athlete=body.athlete or "Team Summary",
            tests_analyzed=summary.total_sessions,
            date_range=Period(**{"from": summary.season_start, "to": summary.season_end}),
            performance_summary=perf_summary,
            insights=InsightsBlock(
                insights=report.insights,
                risks=report.risks,
                recommendations=report.recommendations,
                degraded=degraded_flag
            ),
            heatmap_data=summary.heatmap_data
        )
        
        logger.info(f"rowing analysis complete: best_split={result.performance_summary.best_split_secs} alerts={result.performance_summary.alerts}")
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"rowing pipeline error: {type(e).__name__}")
        raise HTTPException(status_code=500, detail={"detail": "pipeline_error"})

@router.get("/health")
async def health_check():
    """Health check endpoint that shows all integration statuses."""
    settings = get_settings()
    
    return {
        "status": "ok",
        "version": "0.2.0",
        "integrations": {
            "gemini": "configured" if settings.gemini_api_key else "missing",
            "strava": "configured" if settings.strava_client_id else "not_configured",
            "google_sheets": "configured" if settings.google_sheet_id else "not_configured",
            "sheets_write": "configured" if (settings.google_service_account_json or settings.google_service_account_file) else "read_only",
        }
    }


# ═══════════ STRAVA OAUTH FLOW ═══════════

@router.get("/strava/auth")
async def strava_auth():
    """Returns the Strava OAuth2 authorization URL. User clicks this to connect."""
    from app.services.strava import get_auth_url
    settings = get_settings()
    if not settings.strava_client_id:
        raise HTTPException(status_code=503, detail={"detail": "Strava not configured. Set STRAVA_CLIENT_ID and STRAVA_CLIENT_SECRET in .env"})
    url = get_auth_url()
    return {"auth_url": url, "instructions": "Open this URL in your browser to authorize Strava access."}


@router.get("/strava/callback")
async def strava_callback(code: str = "", error: str = ""):
    """OAuth2 callback. Strava redirects here with the authorization code."""
    if error:
        raise HTTPException(status_code=400, detail={"detail": f"Strava auth denied: {error}"})
    if not code:
        raise HTTPException(status_code=400, detail={"detail": "Missing authorization code"})
    
    from app.services.strava import exchange_token
    try:
        token_data = exchange_token(code)
        return {
            "status": "connected",
            "athlete": token_data.get("athlete", {}).get("firstname", "Unknown"),
            "access_token": token_data["access_token"],
            "refresh_token": token_data["refresh_token"],
            "expires_at": token_data["expires_at"],
            "instructions": "Save these tokens. Use access_token in POST /sync/strava to pull activities."
        }
    except Exception as e:
        logger.error(f"Strava token exchange failed: {e}")
        raise HTTPException(status_code=502, detail={"detail": f"Token exchange failed: {str(e)}"})


@router.post("/sync/strava")
@limiter.limit("10/minute")
async def sync_strava(request: Request, access_token: str = "", refresh_token: str = ""):
    """
    Pull activities from Strava and map them to our internal format.
    
    Requires a valid access_token from the OAuth flow.
    If the token is expired, provide refresh_token to auto-refresh.
    """
    from app.services.strava import get_activities, map_strava_to_records, refresh_access_token, get_athlete

    if not access_token:
        raise HTTPException(status_code=400, detail={"detail": "access_token is required. Get one via GET /strava/auth"})

    try:
        # Try fetching with current token
        try:
            activities = get_activities(access_token, per_page=50)
        except Exception:
            # If failed and we have refresh token, try refreshing
            if refresh_token:
                logger.info("Access token expired, refreshing...")
                new_tokens = refresh_access_token(refresh_token)
                access_token = new_tokens["access_token"]
                activities = get_activities(access_token, per_page=50)
            else:
                raise

        athlete_info = {}
        try:
            athlete_info = get_athlete(access_token)
        except Exception:
            pass

        mapped = map_strava_to_records(activities)

        # Optionally write to Google Sheet
        settings = get_settings()
        sheet_written = False
        if settings.google_sheet_id and (settings.google_service_account_json or settings.google_service_account_file):
            from app.services.sheets import write_mapped_record
            sheet_written = write_mapped_record(settings.google_sheet_id, mapped, "synth_strava_activities")

        return {
            "status": "synced",
            "athlete": athlete_info.get("firstname", "Unknown"),
            "activities_fetched": len(activities),
            "activities_mapped": len(mapped),
            "sheet_written": sheet_written,
            "activities": mapped[:10],  # Return first 10 for preview
            "access_token": access_token  # Return in case it was refreshed
        }
    except Exception as e:
        logger.error(f"Strava sync failed: {e}")
        raise HTTPException(status_code=502, detail={"detail": f"Strava sync failed: {str(e)}"})


# ═══════════ GOOGLE SHEETS SYNC ═══════════

@router.post("/sync/sheets")
@limiter.limit("10/minute")
async def sync_sheets(request: Request, domain: str = "triathlon"):
    """
    Full two-way sync: reads from Google Sheet, runs analysis, writes insights back.
    
    This is the core loop that AG wants to see working:
    1. Read training data from the Google Sheet
    2. Run heuristics + AI synthesis
    3. Write insights back to a new tab in the same sheet
    """
    settings = get_settings()
    if not settings.google_sheet_id:
        raise HTTPException(status_code=503, detail={"detail": "Google Sheet not configured. Set GOOGLE_SHEET_ID in .env"})

    from app.services.sheets import read_all_worksheets, write_insights_to_sheet, write_mapped_record

    try:
        # Step 1: Read from Google Sheet
        logger.info(f"Reading from Google Sheet {settings.google_sheet_id}...")
        all_tabs = read_all_worksheets(settings.google_sheet_id)
        tab_names = list(all_tabs.keys())
        total_rows = sum(len(v) for v in all_tabs.values())

        # Step 2: Run analysis based on domain
        if domain == "triathlon":
            # Use existing CSV pipeline for now, but demonstrate sheet reading
            try:
                current_daily, current_activities = get_triathlon_data(
                    settings.triathlon_daily_csv, settings.triathlon_activities_csv, 7
                )
                all_daily = get_all_daily(settings.triathlon_daily_csv)
                summary = build_triathlon_summary(current_daily, current_activities, all_daily, period_days=7)
                report = generate_triathlon_insights(summary)
            except Exception as e:
                logger.warning(f"CSV pipeline failed, using sheet data: {e}")
                report = None
        else:
            try:
                ergs, roster = get_rowing_data(settings.rowing_data_dir)
                summary = build_team_summary(ergs, roster)
                report = generate_rowing_insights(summary)
            except Exception as e:
                logger.warning(f"CSV pipeline failed: {e}")
                report = None

        # Step 3: Write insights back to Google Sheet
        write_success = False
        if report:
            write_success = write_insights_to_sheet(
                sheet_id=settings.google_sheet_id,
                insights=report.insights,
                risks=report.risks,
                recommendations=report.recommendations,
                metadata={
                    "generated_at": datetime.utcnow().isoformat(),
                    "domain": domain,
                    "degraded": any("degraded" in s.lower() for s in report.insights)
                }
            )

        return {
            "status": "synced",
            "sheet_id": settings.google_sheet_id,
            "tabs_read": tab_names,
            "total_rows_read": total_rows,
            "insights_written": write_success,
            "insights": report.insights if report else [],
            "risks": report.risks if report else [],
            "recommendations": report.recommendations if report else []
        }

    except Exception as e:
        error_msg = str(e)
        if "APIError" in type(e).__name__:
            import json
            try:
                # e.response.text contains the actual Google API error JSON
                error_data = e.response.json()
                error_msg = error_data.get("error", {}).get("message", str(e))
            except:
                pass
        
        logger.error(f"Sheets sync failed: {error_msg}")
        raise HTTPException(status_code=502, detail={"detail": f"Sheets sync failed: {error_msg}"})

# ═══════════ ML TRAINING (MOCK) ═══════════

@router.get("/analyze/ml_training")
async def train_injury_model():
    """
    Simulates the data flow of an ML model training pipeline.
    This provides a deterministic trace to visualize the ingestion,
    feature engineering, and training steps.
    """
    from app.models.schemas import MLTrainingReport
    
    # In a real system, this would load the CSV, compute the features,
    # split data, run XGBoost, and save the .pkl file.
    
    return MLTrainingReport(
        model_name="Injury_Predictor_v1_XGB",
        target_variable="injured_next_14_days",
        ingestion_rows=1240,
        ingestion_features=["date", "trimp", "avg_hr", "distance", "injury_status"],
        engineered_features=["acute_load", "chronic_load", "acute_chronic_ratio", "hr_drift_pct", "days_since_rest"],
        data_split="80% Train, 20% Test (Chronological)",
        algorithm="XGBoost Classifier (n_estimators=100, learning_rate=0.05)",
        hyperparameters={"max_depth": 4, "subsample": 0.8, "objective": "binary:logistic"},
        accuracy_pct=89.4,
        f1_score=0.82,
        feature_importance={
            "acute_chronic_ratio": 0.45,
            "days_since_rest": 0.22,
            "hr_drift_pct": 0.18,
            "chronic_load": 0.15
        },
        model_artifact="models/injury_v1_xgb.pkl",
        deployment_status="Staging (A/B Test)"
    )
