from fastapi import Security, HTTPException, status
from fastapi.security import APIKeyHeader
from app.config import get_settings

# We use a custom header X-API-Key for secure access to the API
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

def verify_api_key(api_key_header: str = Security(api_key_header)):
    """
    Validates that the incoming request has the correct API key.
    This fulfills the "secure end to end" requirement for the MVP.
    In a real app, this would check against a DB of client tokens.
    """
    settings = get_settings()
    
    if not api_key_header:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API Key is missing",
            headers={"WWW-Authenticate": "ApiKey"},
        )
        
    # We use a dummy static key for the MVP, read from env
    expected_api_key = getattr(settings, 'synth_api_key', 'dev_secret_key_123')
    
    if api_key_header != expected_api_key:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Could not validate API key",
        )
        
    return api_key_header
