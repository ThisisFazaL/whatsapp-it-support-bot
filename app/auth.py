import os
import hmac
import hashlib
import time
import json
import base64
from typing import Optional, Dict
from fastapi import Request

# Security secret for signing session cookies
SECRET_KEY = os.getenv("DASHBOARD_SECRET_KEY", "tg_enterprise_sec_key_2026_98xLa9!#")

# Hardened Credentials (overridable via environment variables)
USERS_DB = {
    "admin": {
        "username": "admin",
        "password": os.getenv("DASHBOARD_ADMIN_PASS", "Admin@Tagoneswa2026!"),
        "role": "MASTER_ADMIN",
        "name": "Master Administrator",
        "allowed_domains": ["it", "projects", "logistics", "fleet"]
    },
    "fleet": {
        "username": "fleet",
        "password": os.getenv("DASHBOARD_FLEET_PASS", "Fleet@Tagoneswa2026!"),
        "role": "FLEET_ADMIN",
        "name": "Fleet Operations Manager",
        "allowed_domains": ["fleet", "logistics"]
    },
    "sujit": {
        "username": "sujit",
        "password": os.getenv("DASHBOARD_SUJIT_PASS", "Sujit@Fleet2026!"),
        "role": "FLEET_ADMIN",
        "name": "Sujit (Fleet Admin)",
        "allowed_domains": ["fleet", "logistics"]
    },
    "sales": {
        "username": "sales",
        "password": os.getenv("DASHBOARD_SALES_PASS", "Sales@Tagoneswa2026!"),
        "role": "SALES_ADMIN",
        "name": "Sales & Commercial Lead",
        "allowed_domains": ["fleet"]
    },
    "logistics": {
        "username": "logistics",
        "password": os.getenv("DASHBOARD_LOGISTICS_PASS", "Logistics@2026!"),
        "role": "LOGISTICS_ADMIN",
        "name": "Logistics & Workshop Lead",
        "allowed_domains": ["logistics", "fleet"]
    },
    "itsupport": {
        "username": "itsupport",
        "password": os.getenv("DASHBOARD_IT_PASS", "ITSupport@2026!"),
        "role": "IT_ADMIN",
        "name": "IT Support Administrator",
        "allowed_domains": ["it"]
    },
    "projects": {
        "username": "projects",
        "password": os.getenv("DASHBOARD_PROJECTS_PASS", "Projects@2026!"),
        "role": "PROJECTS_ADMIN",
        "name": "Building Projects Administrator",
        "allowed_domains": ["projects"]
    },
    "executive": {
        "username": "executive",
        "password": os.getenv("DASHBOARD_EXECUTIVE_PASS", "Executive@Tagoneswa2026!"),
        "role": "EXECUTIVE_OBSERVER",
        "name": "Executive Observer",
        "allowed_domains": ["it", "projects", "logistics", "fleet"]
    }
}

COOKIE_NAME = "tagoneswa_session"
SESSION_MAX_AGE = 60 * 60 * 24 * 7  # 7 days

def create_session_token(username: str, role: str) -> str:
    """Creates a cryptographically signed, timestamped session token."""
    payload = {
        "sub": username,
        "role": role,
        "exp": int(time.time()) + SESSION_MAX_AGE
    }
    json_bytes = json.dumps(payload).encode("utf-8")
    b64_payload = base64.urlsafe_b64encode(json_bytes).decode("utf-8")
    signature = hmac.new(SECRET_KEY.encode("utf-8"), b64_payload.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"{b64_payload}.{signature}"

def verify_session_token(token: str) -> Optional[Dict]:
    """Verifies a signed session token using constant-time comparison and expiry check."""
    if not token or "." not in token:
        return None
    try:
        b64_payload, signature = token.split(".", 1)
        expected_sig = hmac.new(SECRET_KEY.encode("utf-8"), b64_payload.encode("utf-8"), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(signature, expected_sig):
            return None
        
        json_bytes = base64.urlsafe_b64decode(b64_payload.encode("utf-8"))
        payload = json.loads(json_bytes.decode("utf-8"))
        
        if payload.get("exp", 0) < time.time():
            return None  # Expired
            
        return payload
    except Exception:
        return None

def authenticate_user(username: str, password: str) -> Optional[Dict]:
    """Authenticates credentials against high-entropy store using constant-time comparison."""
    u = username.strip().lower()
    if u in USERS_DB:
        user = USERS_DB[u]
        if hmac.compare_digest(user["password"], password.strip()):
            return user
    return None

def get_current_user_from_request(request: Request) -> Optional[Dict]:
    """Extracts and verifies the session token from HttpOnly cookie or Bearer header."""
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:].strip()
            
    payload = verify_session_token(token)
    if payload:
        username = payload.get("sub")
        if username in USERS_DB:
            return USERS_DB[username]
    return None
