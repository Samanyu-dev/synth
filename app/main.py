from fastapi import FastAPI, Response
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from fastapi.staticfiles import StaticFiles
from app.api.routes import router
import logging
import sys
import warnings

# Suppress XGBoost deprecation warnings from scikit-learn
warnings.filterwarnings("ignore", category=FutureWarning, module="sklearn.utils._tags")

# Force logging to stdout instead of stderr to prevent misclassification as errors
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    stream=sys.stdout
)

limiter = Limiter(key_func=get_remote_address)

app = FastAPI(
    title="Synth MVP",
    description="Training load and erg performance synthesis",
    version="0.1.0"
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Suppress Favicon 404s
@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    return Response(status_code=204)

@app.get("/apple-touch-icon.png", include_in_schema=False)
@app.get("/apple-touch-icon-precomposed.png", include_in_schema=False)
async def apple_touch_icon():
    return Response(status_code=204)

app.include_router(router)

# Serve the frontend UI
app.mount("/", StaticFiles(directory="frontend", html=True), name="frontend")
