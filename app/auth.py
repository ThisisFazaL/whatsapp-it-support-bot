import os
import hmac
import hashlib
import time
import json
import base64
from typing import Optional, Dict, Set, List, Any
from fastapi import Request, HTTPException

# Security secret for signing session cookies
SECRET_KEY = os.getenv("DASHBOARD_SECRET_KEY", "tg_enterprise_sec_key_2026_98xLa9!#")

# Hardened Credentials (overridable via environment variables)
USERS_DB = {
    "admin": {
        "username": "admin",
        "password": os.getenv("DASHBOARD_ADMIN_PASS", "Admin@Tagoneswa2026!"),
        "role": "MASTER_ADMIN",
        "name": "Master Administrator",
        "allowed_domains": ["it", "projects", "logistics", "fleet", "accounts", "admin"]
    },
    "accounts": {
        "username": "accounts",
        "password": os.getenv("DASHBOARD_ACCOUNTS_PASS", "Accounts@Tagoneswa2026!"),
        "role": "ACCOUNTS_USER",
        "name": "Accounts & Finance Lead",
        "allowed_domains": ["accounts", "fleet"]
    },
    "logisticsmgr": {
        "username": "logisticsmgr",
        "password": os.getenv("DASHBOARD_LOGISTICSMGR_PASS", "LogisticsMgr@2026!"),
        "role": "LOGISTICS_MANAGER",
        "name": "Logistics Operations Manager",
        "allowed_domains": ["logistics", "fleet"]
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
    },

    # ── Sales Admins (individual named logins) ────────────────────────────────
    "everjoy": {
        "username": "everjoy",
        "password": os.getenv("DASHBOARD_EVERJOY_PASS", "Everjoy@Kreckle2026!"),
        "role": "SALES_ADMIN",
        "name": "Everjoy Tias",
        "company": "Kreckle Foods",
        "phone": "263780216289",
        "allowed_domains": ["fleet"]
    },
    "onelly": {
        "username": "onelly",
        "password": os.getenv("DASHBOARD_ONELLY_PASS", "Onelly@LGPlast2026!"),
        "role": "SALES_ADMIN",
        "name": "Onelly Madziro",
        "company": "LG Plast",
        "phone": "263787381215",
        "allowed_domains": ["fleet"]
    },
    "christine": {
        "username": "christine",
        "password": os.getenv("DASHBOARD_CHRISTINE_PASS", "Christine@TG2026!"),
        "role": "SALES_ADMIN",
        "name": "Christine Chiweshe",
        "company": "Tagoneswa Hardware",
        "phone": "263783498457",
        "allowed_domains": ["fleet"]
    },
    "mazviita": {
        "username": "mazviita",
        "password": os.getenv("DASHBOARD_MAZVIITA_PASS", "Mazviita@LGPlast2026!"),
        "role": "SALES_ADMIN",
        "name": "Mazviita Sibongile Ruzvidzo",
        "company": "LG Plast",
        "phone": "263718174894",
        "allowed_domains": ["fleet"]
    },

    # ── Accounts (individual named logins) ────────────────────────────────────
    "vigilance": {
        "username": "vigilance",
        "password": os.getenv("DASHBOARD_VIGILANCE_PASS", "Vigilance@Accounts2026!"),
        "role": "ACCOUNTS_USER",
        "name": "Vigilance Bangezhano",
        "phone": "263780100288",
        "allowed_domains": ["accounts", "fleet"]
    },
    "munashe": {
        "username": "munashe",
        "password": os.getenv("DASHBOARD_MUNASHE_PASS", "Munashe@Accounts2026!"),
        "role": "ACCOUNTS_USER",
        "name": "Munashe Milca",
        "phone": "263788068567",
        "allowed_domains": ["accounts", "fleet"]
    },
}

COOKIE_NAME = "tagoneswa_session"
SESSION_MAX_AGE = 60 * 60 * 24 * 7  # 7 days

# =========================================================================
# RBAC Governance & Granular Permissions Engine
# =========================================================================
ALL_PERMISSIONS: List[str] = [
    "view_fleet_workspace",
    "manage_trucks",
    "manage_drivers",
    "manage_fuel_price",
    "manage_fleet_rules",
    "approve_trips",
    "manage_city_minimums",
    "clear_sales_rep_debt",
    "manage_meal_rate",
    "manage_accommodation_rate",
    "manage_sales_pipeline",
    "view_customer_schedules",
    "view_sales_rep_balances",
    "view_workshop_workspace",
    "manage_workshop_tickets",
    "view_it_workspace",
    "view_projects_workspace",
    "view_audit_logs",
    "manage_user_permissions",
    "view_analytics"
]

ROLE_DEFAULT_PERMISSIONS: Dict[str, Set[str]] = {
    "MASTER_ADMIN": set(ALL_PERMISSIONS),
    "FLEET_ADMIN": {
        "view_fleet_workspace",
        "manage_trucks",
        "manage_drivers",
        "manage_fuel_price",
        "manage_fleet_rules",
        "approve_trips",
        "view_customer_schedules",
        "manage_sales_pipeline",
        "view_workshop_workspace",
        "view_audit_logs"
    },
    "SALES_ADMIN": {
        "view_fleet_workspace",
        "manage_sales_pipeline",
        "view_customer_schedules",
        "view_sales_rep_balances"
    },
    "ACCOUNTS_USER": {
        "view_fleet_workspace",
        "view_sales_rep_balances",
        "view_customer_schedules",
        "view_audit_logs"
    },
    "LOGISTICS_MANAGER": {
        "view_fleet_workspace",
        "view_workshop_workspace",
        "manage_trucks",
        "manage_drivers",
        "manage_fuel_price",
        "manage_fleet_rules",
        "approve_trips",
        "view_customer_schedules",
        "view_audit_logs"
    },
    "LOGISTICS_ADMIN": {
        "view_fleet_workspace",
        "view_workshop_workspace",
        "manage_trucks",
        "manage_drivers",
        "manage_workshop_tickets"
    },
    "IT_ADMIN": {
        "view_it_workspace"
    },
    "PROJECTS_ADMIN": {
        "view_projects_workspace"
    },
    "EXECUTIVE_OBSERVER": {
        "view_fleet_workspace",
        "view_workshop_workspace",
        "view_it_workspace",
        "view_projects_workspace",
        "view_customer_schedules",
        "view_sales_rep_balances",
        "view_audit_logs"
    }
}

# In-memory synchronized user custom permission overrides: {username: {permission_key: is_granted}}
# Populated dynamically from user_custom_permissions database records at startup.
USER_CUSTOM_PERMISSIONS_CACHE: Dict[str, Dict[str, bool]] = {}

def sync_db_roles_to_users_db(user_roles: Dict[str, str]):
    """Synchronizes active WebUser database roles into runtime USERS_DB."""
    for username, role in user_roles.items():
        u = username.strip().lower()
        if u in USERS_DB and role:
            USERS_DB[u]["role"] = role

def set_user_custom_permission(username: str, permission_key: str, is_granted: bool):
    """Updates user custom permission in the memory cache."""
    u = username.strip().lower()
    if u not in USER_CUSTOM_PERMISSIONS_CACHE:
        USER_CUSTOM_PERMISSIONS_CACHE[u] = {}
    USER_CUSTOM_PERMISSIONS_CACHE[u][permission_key] = is_granted

def load_all_user_custom_permissions(perms_map: Dict[str, Dict[str, bool]]):
    """Bulk loads user custom permissions into the memory cache."""
    global USER_CUSTOM_PERMISSIONS_CACHE
    USER_CUSTOM_PERMISSIONS_CACHE.clear()
    for u, perms in perms_map.items():
        USER_CUSTOM_PERMISSIONS_CACHE[u.strip().lower()] = dict(perms)

def user_has_permission(user: Optional[Dict], permission_key: str) -> bool:
    """
    Evaluates effective permissions for a user:
    1. MASTER_ADMIN automatically passes all checks.
    2. Explicit user-level custom permission overrides (granted or revoked) take precedence.
    3. Base role defaults apply if no explicit user-level override is found.
    Zero hardcoded usernames in authorization logic.
    """
    if not user:
        return False
    role = user.get("role", "")
    if role == "MASTER_ADMIN":
        return True
    
    # Check user-level custom overrides
    custom_perms = user.get("custom_permissions")
    if custom_perms is None:
        u = user.get("username", "").strip().lower()
        custom_perms = USER_CUSTOM_PERMISSIONS_CACHE.get(u, {})
    
    if permission_key in custom_perms:
        return bool(custom_perms[permission_key])
        
    # Check base role defaults
    default_perms = ROLE_DEFAULT_PERMISSIONS.get(role, set())
    return permission_key in default_perms

def get_effective_permissions(user: Optional[Dict]) -> Set[str]:
    """Returns the complete set of effective permissions for a user."""
    if not user:
        return set()
    role = user.get("role", "")
    if role == "MASTER_ADMIN":
        return set(ALL_PERMISSIONS)
    
    perms = set(ROLE_DEFAULT_PERMISSIONS.get(role, set()))
    custom_perms = user.get("custom_permissions")
    if custom_perms is None:
        u = user.get("username", "").strip().lower()
        custom_perms = USER_CUSTOM_PERMISSIONS_CACHE.get(u, {})
        
    for p, granted in custom_perms.items():
        if granted:
            perms.add(p)
        else:
            perms.discard(p)
    return perms

def require_permission(user: Optional[Dict], permission_key: str):
    """Enforces authorization on sensitive endpoints. Raises HTTP 403 if unauthorized."""
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required.")
    if not user_has_permission(user, permission_key):
        role = user.get("role", "UNKNOWN")
        raise HTTPException(
            status_code=403,
            detail=f"Permission denied: '{permission_key}' required. Role '{role}' is not authorized."
        )

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
        user = dict(USERS_DB[u])
        if hmac.compare_digest(user["password"], password.strip()):
            user["custom_permissions"] = USER_CUSTOM_PERMISSIONS_CACHE.get(u, {})
            user["effective_permissions"] = list(get_effective_permissions(user))
            return user
    return None

def get_current_user_from_request(request: Request) -> Optional[Dict]:
    """Extracts and verifies the session token from HttpOnly cookie or Bearer header, attaching custom & effective permissions."""
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:].strip()
            
    payload = verify_session_token(token)
    if payload:
        username = payload.get("sub", "").strip().lower()
        if username in USERS_DB:
            user = dict(USERS_DB[username])
            user["custom_permissions"] = USER_CUSTOM_PERMISSIONS_CACHE.get(username, {})
            user["effective_permissions"] = list(get_effective_permissions(user))
            return user
    return None
