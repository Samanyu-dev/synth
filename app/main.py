"""
Synth MVP — FastAPI application entry point.

Start with: uvicorn app.main:app --reload
"""

import logging

from fastapi import FastAPI

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(name)s | %(levelname)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("synth")

app = FastAPI(
    title="Synth MVP",
    description="Athletic performance data pipeline with AI-powered insights",
    version="0.1.0",
)


@app.get("/health")
async def health():
    """Basic health check — confirms the server is running."""
    return {"status": "ok"}
