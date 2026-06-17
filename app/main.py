from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import logging

from app.api.routes import router

# Configure application-level logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("synth")

app = FastAPI(
    title="Synth MVP API",
    description="Backend data pipeline for athletic heuristics and AI synthesis.",
    version="1.0.0"
)

# Standard CORS setup for modern web backends
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows all origins for MVP. In prod, restrict this.
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include our core routes
app.include_router(router)

@app.get("/health")
def health_check():
    """Basic health check endpoint for monitoring uptime."""
    return {"status": "ok", "service": "synth-backend"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
