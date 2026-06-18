from fastapi import FastAPI
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from fastapi.staticfiles import StaticFiles
from app.api.routes import router
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s"
)

limiter = Limiter(key_func=get_remote_address)

app = FastAPI(
    title="Synth MVP",
    description="Training load and erg performance synthesis",
    version="0.1.0"
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.include_router(router)

# Serve the frontend UI
app.mount("/", StaticFiles(directory="frontend", html=True), name="frontend")
