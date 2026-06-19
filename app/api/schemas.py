from typing import Optional, List
from datetime import datetime, date
from pydantic import BaseModel, Field, field_validator
import re

class TriathlonRequest(BaseModel):
    lookback_days: int = Field(default=7, ge=1, le=90)

class RowingRequest(BaseModel):
    athlete: Optional[str] = Field(default=None, max_length=100)
    lookback_days: int = Field(default=7, ge=1, le=90)
    
    @field_validator('athlete')
    @classmethod
    def validate_athlete_name(cls, v):
        if v is None:
            return v
        # Strict alphanumeric limits per spec (plus spaces, commas, hyphens, apostrophes, dots)
        if not re.match(r"^[a-zA-Z\s,'\-\.]+$", v):
            raise ValueError("athlete name contains invalid characters")
        if len(v.strip()) < 2:
            raise ValueError("athlete name too short")
        return v.strip()

class ErrorResponse(BaseModel):
    detail: str
    source: Optional[str] = None   # "triathlon_loader", "rowing_loader", "claude", "db"
    degraded: bool = False

# --- Response Models ---

class Period(BaseModel):
    from_: date = Field(alias="from")
    to: date

    class Config:
        populate_by_name = True

class LoadSummary(BaseModel):
    sessions: int
    training_minutes: float
    trimp: float
    avg_hr: float
    run_miles: float
    bike_miles: float
    swim_miles: float
    hr_trend: str
    injury_risk_pct: Optional[float] = None
    alerts: List[str]
    form_chart_data: List[dict] = []

class InsightsBlock(BaseModel):
    insights: List[str]
    risks: List[str]
    recommendations: List[str]
    degraded: bool = False

class TriathlonResponse(BaseModel):
    generated_at: datetime
    lookback_days: int
    period: Period
    load_summary: LoadSummary
    insights: InsightsBlock

class PerformanceSummary(BaseModel):
    best_split_secs: float
    latest_split_secs: float
    improvement_secs: float
    improvement_pct: float
    hr_trend: str
    alerts: List[str]

class RowingResponse(BaseModel):
    generated_at: datetime
    athlete: str
    tests_analyzed: int
    date_range: Period
    performance_summary: PerformanceSummary
    insights: InsightsBlock
    heatmap_data: dict = {}

# Note: Health response is returned directly as dict per spec, but we can define it here too
class HealthResponse(BaseModel):
    status: str
    data_sources: dict
    db: str
    anthropic: str
