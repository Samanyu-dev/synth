"""
Strava API Integration Service.

Connects to the Strava API using OAuth2 to pull real athlete
activity data. Maps Strava activities into our existing
ActivityRecord Pydantic model for cross-source correlation.
"""

import logging
from datetime import datetime
from typing import Dict, List, Optional

import requests

from app.config import get_settings

logger = logging.getLogger("synth.services.strava")

STRAVA_AUTH_URL = "https://www.strava.com/oauth/authorize"
STRAVA_TOKEN_URL = "https://www.strava.com/oauth/token"
STRAVA_API_BASE = "https://www.strava.com/api/v3"


def get_auth_url(redirect_uri: str = "http://localhost:8000/strava/callback") -> str:
    """
    Generate the Strava OAuth2 authorization URL.
    The user clicks this to grant access to their Strava data.
    """
    settings = get_settings()
    params = {
        "client_id": settings.strava_client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "approval_prompt": "auto",
        "scope": "read,activity:read_all"
    }
    url = f"{STRAVA_AUTH_URL}?" + "&".join(f"{k}={v}" for k, v in params.items())
    return url


def exchange_token(code: str) -> Dict:
    """
    Exchange the authorization code for access & refresh tokens.
    
    Returns:
        Dict with access_token, refresh_token, expires_at, athlete info.
    """
    settings = get_settings()
    response = requests.post(STRAVA_TOKEN_URL, data={
        "client_id": settings.strava_client_id,
        "client_secret": settings.strava_client_secret,
        "code": code,
        "grant_type": "authorization_code"
    })
    response.raise_for_status()
    data = response.json()
    logger.info(f"Strava token exchange successful for athlete: {data.get('athlete', {}).get('firstname', 'unknown')}")
    return data


def refresh_access_token(refresh_token: str) -> Dict:
    """
    Refresh an expired access token using the refresh token.
    """
    settings = get_settings()
    response = requests.post(STRAVA_TOKEN_URL, data={
        "client_id": settings.strava_client_id,
        "client_secret": settings.strava_client_secret,
        "refresh_token": refresh_token,
        "grant_type": "refresh_token"
    })
    response.raise_for_status()
    return response.json()


def get_activities(
    access_token: str,
    per_page: int = 30,
    page: int = 1,
    after: Optional[int] = None,
    before: Optional[int] = None
) -> List[Dict]:
    """
    Fetch the athlete's activities from Strava.
    
    Args:
        access_token: Valid Strava access token.
        per_page: Number of activities per page (max 200).
        page: Page number.
        after: Only activities after this epoch timestamp.
        before: Only activities before this epoch timestamp.
    
    Returns:
        List of activity dicts from Strava API.
    """
    headers = {"Authorization": f"Bearer {access_token}"}
    params = {"per_page": per_page, "page": page}
    if after:
        params["after"] = after
    if before:
        params["before"] = before

    response = requests.get(
        f"{STRAVA_API_BASE}/athlete/activities",
        headers=headers,
        params=params
    )
    response.raise_for_status()
    activities = response.json()
    logger.info(f"Fetched {len(activities)} activities from Strava")
    return activities


def get_athlete(access_token: str) -> Dict:
    """Fetch the authenticated athlete's profile."""
    headers = {"Authorization": f"Bearer {access_token}"}
    response = requests.get(f"{STRAVA_API_BASE}/athlete", headers=headers)
    response.raise_for_status()
    return response.json()


def map_strava_to_records(activities: List[Dict]) -> List[Dict]:
    """
    Map raw Strava API activity data into our internal record format.
    
    Converts Strava's schema into something compatible with our
    existing DailySummary/ActivityRecord models for cross-source
    correlation with the Google Sheet data.
    """
    records = []
    for act in activities:
        sport_type = act.get("sport_type", act.get("type", "unknown")).lower()
        
        # Map Strava sport types to our disciplines
        discipline = "other"
        if sport_type in ("run", "virtualrun", "trailrun"):
            discipline = "run"
        elif sport_type in ("ride", "virtualride", "ebikeride"):
            discipline = "bike"
        elif sport_type in ("swim"):
            discipline = "swim"
        elif sport_type in ("rowing", "kayaking"):
            discipline = "row"

        distance_miles = round((act.get("distance", 0) or 0) / 1609.34, 2)
        moving_time_min = round((act.get("moving_time", 0) or 0) / 60, 1)
        elapsed_time_min = round((act.get("elapsed_time", 0) or 0) / 60, 1)
        avg_hr = act.get("average_heartrate")
        max_hr = act.get("max_heartrate")
        avg_watts = act.get("average_watts")
        elevation_gain = act.get("total_elevation_gain", 0)

        # Pace for running (min/mile)
        avg_pace = None
        if discipline == "run" and distance_miles > 0 and moving_time_min > 0:
            avg_pace = round(moving_time_min / distance_miles, 2)

        start_date = act.get("start_date_local", act.get("start_date", ""))
        if start_date:
            try:
                start_date = datetime.fromisoformat(start_date.replace("Z", "+00:00")).strftime("%Y-%m-%d")
            except (ValueError, TypeError):
                pass

        records.append({
            "source": "strava",
            "strava_id": act.get("id"),
            "date": start_date,
            "name": act.get("name", ""),
            "discipline": discipline,
            "sport_type": sport_type,
            "distance_miles": distance_miles,
            "moving_time_min": moving_time_min,
            "elapsed_time_min": elapsed_time_min,
            "avg_hr": avg_hr,
            "max_hr": max_hr,
            "avg_watts": avg_watts,
            "elevation_gain_ft": round(elevation_gain * 3.28084, 1) if elevation_gain else 0,
            "avg_pace_min_per_mile": avg_pace,
            "suffer_score": act.get("suffer_score"),
            "has_heartrate": act.get("has_heartrate", False),
            "calories": act.get("calories", 0),
        })

    logger.info(f"Mapped {len(records)} Strava activities to internal format")
    return records
