"""
Google Sheets Two-Way Sync Service.

Reads training data from AG's shared Google Sheet and writes back
synthesized insights, mapped records, and derived values.

Uses gspread with API key for reading (public/shared sheets) and
Service Account for writing (requires credentials).
"""

import json
import logging
from datetime import datetime
from typing import Dict, List, Optional, Tuple

import gspread
from google.oauth2.service_account import Credentials

from app.config import get_settings

logger = logging.getLogger("synth.services.sheets")

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]


def _get_client() -> gspread.Client:
    """
    Get an authenticated gspread client.
    Uses a service account if credentials JSON is available,
    otherwise falls back to API key (read-only).
    """
    settings = get_settings()

    if settings.google_service_account_json:
        try:
            creds_data = json.loads(settings.google_service_account_json)
            creds = Credentials.from_service_account_info(creds_data, scopes=SCOPES)
            return gspread.authorize(creds)
        except Exception as e:
            logger.error(f"Service account auth failed: {e}")
            raise

    if settings.google_service_account_file:
        try:
            creds = Credentials.from_service_account_file(
                settings.google_service_account_file, scopes=SCOPES
            )
            return gspread.authorize(creds)
        except Exception as e:
            logger.error(f"Service account file auth failed: {e}")
            raise

    raise ValueError(
        "No Google credentials configured. Set GOOGLE_SERVICE_ACCOUNT_JSON or GOOGLE_SERVICE_ACCOUNT_FILE in .env"
    )


def read_sheet(sheet_id: str, worksheet_name: Optional[str] = None) -> List[Dict]:
    """
    Read all rows from a Google Sheet as a list of dicts.
    
    Args:
        sheet_id: The Google Sheet ID (from the URL).
        worksheet_name: Optional specific worksheet/tab name.
    
    Returns:
        List of dicts where keys are column headers.
    """
    client = _get_client()
    spreadsheet = client.open_by_key(sheet_id)

    if worksheet_name:
        worksheet = spreadsheet.worksheet(worksheet_name)
    else:
        worksheet = spreadsheet.sheet1

    records = worksheet.get_all_records()
    logger.info(f"Read {len(records)} rows from sheet {sheet_id} / {worksheet.title}")
    return records


def read_all_worksheets(sheet_id: str) -> Dict[str, List[Dict]]:
    """
    Read all worksheets from a Google Sheet.
    
    Returns:
        Dict mapping worksheet name -> list of row dicts.
    """
    client = _get_client()
    spreadsheet = client.open_by_key(sheet_id)
    
    result = {}
    for ws in spreadsheet.worksheets():
        try:
            records = ws.get_all_records()
            result[ws.title] = records
            logger.info(f"Read {len(records)} rows from tab '{ws.title}'")
        except Exception as e:
            logger.warning(f"Failed to read tab '{ws.title}': {e}")
            result[ws.title] = []

    return result


def write_insights_to_sheet(
    sheet_id: str,
    insights: List[str],
    risks: List[str],
    recommendations: List[str],
    metadata: Dict,
    worksheet_name: str = "synth_insights"
) -> bool:
    """
    Write synthesized insights back to the Google Sheet.
    
    Creates or updates a 'synth_insights' worksheet with the latest
    AI-generated insights, risks, and recommendations.
    
    Args:
        sheet_id: The Google Sheet ID.
        insights: List of insight strings.
        risks: List of risk strings.
        recommendations: List of recommendation strings.
        metadata: Dict of extra metadata (e.g. domain, generated_at).
        worksheet_name: Name of the tab to write to.
    
    Returns:
        True if successful, False otherwise.
    """
    try:
        client = _get_client()
        spreadsheet = client.open_by_key(sheet_id)

        # Get or create the insights worksheet
        try:
            worksheet = spreadsheet.worksheet(worksheet_name)
            worksheet.clear()
        except gspread.exceptions.WorksheetNotFound:
            worksheet = spreadsheet.add_worksheet(
                title=worksheet_name, rows=50, cols=4
            )

        # Build the data to write
        timestamp = metadata.get("generated_at", datetime.utcnow().isoformat())
        domain = metadata.get("domain", "unknown")
        degraded = metadata.get("degraded", False)

        rows = [
            ["Synth MVP — AI Insights Report", "", "", ""],
            [f"Generated: {timestamp}", f"Domain: {domain}", f"Degraded: {degraded}", ""],
            ["", "", "", ""],
            ["Category", "Item", "Priority", "Status"],
        ]

        for i, insight in enumerate(insights, 1):
            rows.append(["Insight", insight, f"#{i}", "Active"])

        rows.append(["", "", "", ""])

        for i, risk in enumerate(risks, 1):
            priority = "High" if "SPIKE" in risk or "FATIGUE" in risk else "Medium"
            rows.append(["Risk", risk, priority, "Active"])

        rows.append(["", "", "", ""])

        for i, rec in enumerate(recommendations, 1):
            rows.append(["Recommendation", rec, f"#{i}", "Pending"])

        # Write all at once (efficient)
        worksheet.update(
            values=rows,
            range_name=f"A1:D{len(rows)}"
        )

        logger.info(
            f"Wrote {len(insights)} insights, {len(risks)} risks, "
            f"{len(recommendations)} recommendations to sheet '{worksheet_name}'"
        )
        return True

    except Exception as e:
        logger.error(f"Failed to write insights to sheet: {e}")
        return False


def write_mapped_record(
    sheet_id: str,
    records: List[Dict],
    worksheet_name: str = "synth_mapped_data"
) -> bool:
    """
    Write mapped/derived records back to the Google Sheet.
    
    This satisfies the two-way sync requirement by writing computed
    heuristic values back where the athlete can see them.
    """
    try:
        client = _get_client()
        spreadsheet = client.open_by_key(sheet_id)

        try:
            worksheet = spreadsheet.worksheet(worksheet_name)
            worksheet.clear()
        except gspread.exceptions.WorksheetNotFound:
            worksheet = spreadsheet.add_worksheet(
                title=worksheet_name, rows=200, cols=10
            )

        if not records:
            return True

        # Headers from the first record
        headers = list(records[0].keys())
        rows = [headers]
        for rec in records:
            rows.append([str(rec.get(h, "")) for h in headers])

        worksheet.update(
            values=rows,
            range_name=f"A1:{chr(65 + len(headers) - 1)}{len(rows)}"
        )

        logger.info(f"Wrote {len(records)} mapped records to '{worksheet_name}'")
        return True

    except Exception as e:
        logger.error(f"Failed to write mapped data: {e}")
        return False

def insert_custom_record(sheet_id: str, payload: Dict, worksheet_name: str = "synth_manual_entries") -> bool:
    """
    Appends a single JSON payload as a new row in the spreadsheet.
    Creates the worksheet if it doesn't exist, and ensures headers match.
    """
    try:
        client = _get_client()
        spreadsheet = client.open_by_key(sheet_id)

        try:
            worksheet = spreadsheet.worksheet(worksheet_name)
        except gspread.exceptions.WorksheetNotFound:
            worksheet = spreadsheet.add_worksheet(title=worksheet_name, rows=100, cols=20)
            
        headers = list(payload.keys())
        
        # Get headers from the first row
        existing_headers = worksheet.row_values(1)
        # Filter out empty strings that gspread might return for blank cells
        existing_headers = [h for h in existing_headers if str(h).strip()]
        
        # If the sheet is completely empty (no valid headers), add the headers first
        if not existing_headers:
            worksheet.clear() # Clear out default blank cells
            worksheet.append_row(headers)
            existing_headers = headers
            
        # Build the row to insert, aligning with existing headers
        row_to_insert = []
        for h in existing_headers:
            row_to_insert.append(str(payload.get(h, "")))
            
        worksheet.append_row(row_to_insert)

        logger.info(f"Appended custom record to '{worksheet_name}'")
        return True

    except Exception as e:
        logger.error(f"Failed to insert custom data: {e}")
        return False
