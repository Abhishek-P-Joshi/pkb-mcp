from src.config import config

def get_auth_middleware():
    """
    Returns None locally (no auth).
    NOTE[remote]: When auth_enabled=true this activates automatically.
    Generate your key with:
        python3 -c "import secrets; print(secrets.token_hex(32))"
    Then set PKB_API_KEY in your .env file.
    """
    if not config.auth_enabled:
        return None

    import os
    from fastapi import Request
    from fastapi.responses import JSONResponse

    api_key = os.environ.get("PKB_API_KEY")
    if not api_key:
        raise RuntimeError("auth_enabled=true but PKB_API_KEY is not set in .env")

    async def verify_key(request: Request, call_next):
        token = request.headers.get("Authorization", "").replace("Bearer ", "")
        if token != api_key:
            return JSONResponse({"error": "unauthorized"}, status_code=401)
        return await call_next(request)

    return verify_key
