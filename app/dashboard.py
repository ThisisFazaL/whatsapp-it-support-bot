# -*- coding: utf-8 -*-
import logging
import datetime
from typing import Set, Dict, List, Optional, Any
from fastapi import APIRouter, Depends, Request, Response, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload

from app.database import (
    get_db, Ticket, MaintenanceTicket, TicketAssignment, MaintenanceTicketAssignment,
    SupportAdmin, Employee, Department, Location, Category, Subcategory, IssueType, Priority, TicketStatus,
    FleetTripApproval, FleetPendingLedger, FleetTripRequest, FleetCustomerSchedule,
    FleetEmergencyExpense, SalesRepPayment, AuditLog, FleetRouteRule, SystemSetting,
    WebUser, UserCustomPermission, RevokedUser, get_sales_rep_pending_balance
)
from app.workshop.models import (
    WorkshopTicket, WorkshopTruck, WorkshopStaff, WorkshopPartsRequest
)
from app.auth import (
    authenticate_user, create_session_token, get_current_user_from_request,
    COOKIE_NAME, SESSION_MAX_AGE, USERS_DB,
    require_permission, user_has_permission, get_effective_permissions,
    ALL_PERMISSIONS, ROLE_DEFAULT_PERMISSIONS, set_user_custom_permission,
    USER_CUSTOM_PERMISSIONS_CACHE, generate_session_id, set_user_session,
    invalidate_user_session, revoke_user_account, restore_user_account,
    register_user_in_memory, is_user_active, ACTIVE_USER_SESSIONS, REVOKED_USERS
)
from app.services.config_service import (
    get_fuel_price, get_meal_rate, get_accommodation_rate, get_expense_budget_pct, get_van_minimum_surcharge,
    get_all_cached_city_rules, update_system_setting, update_city_rule, recalculate_all_city_minimums,
    update_meal_rate, update_accommodation_rate
)

logger = logging.getLogger("dashboard")
router = APIRouter()

IT_SUPPORT_ADMIN_PHONES = {"263783709724", "263788843579", "263780100503"}

OFFICIAL_SALES_REPS_DIRECTORY = {
    # ── LG Plast Sales Reps (7) ───────────────────────────────────────────────
    "263779214825": {"name": "Ashraf Nedziwe",      "company": "LG Plast"},
    "263711421201": {"name": "Mercy Mungoriwo",      "company": "LG Plast"},
    "263777425204": {"name": "Callistus Keche",      "company": "LG Plast"},
    "263781337103": {"name": "Primrose Makumbe",     "company": "LG Plast"},
    "263712498581": {"name": "Sharon Mushava",       "company": "LG Plast"},
    "263787448975": {"name": "Tatenda Mombechena",   "company": "LG Plast"},
    "263786032376": {"name": "Wallace Muzarurwi",    "company": "LG Plast"},

    # ── Tagoneswa Hardware Sales Reps (6) ─────────────────────────────────────
    "263718643451": {"name": "Stuart Chaleka",       "company": "Tagoneswa Hardware"},
    "263782723251": {"name": "Vanessa Zimbiti",      "company": "Tagoneswa Hardware"},
    "263717905914": {"name": "Tafadzwa Sungiso",     "company": "Tagoneswa Hardware"},
    "263717905915": {"name": "Talent Ruziwe",        "company": "Tagoneswa Hardware"},
    "263788231069": {"name": "Tafadzwa Chikove",     "company": "Tagoneswa Hardware"},
    "263780435477": {"name": "Tanaka Mupfumi",       "company": "Tagoneswa Hardware"},

    # ── Kreckle Foods Sales Reps (5) ──────────────────────────────────────────
    "263780543771": {"name": "David Mungadzi",           "company": "Kreckle Foods"},
    "263780806954": {"name": "Patience Ndlovu",          "company": "Kreckle Foods"},
    "263783103611": {"name": "Mufaro Gambiza",           "company": "Kreckle Foods"},
    "263784566997": {"name": "Kudzai Marevesa",          "company": "Kreckle Foods"},
    "263780573092": {"name": "Ndiwande Samihembo Rosa",  "company": "Kreckle Foods"},
}

SALES_ADMIN_PHONES = {
    "263780216289",  # Everjoy Tias (Kreckle Foods)
    "263787381215",  # Onelly Madziro (LG Plast)
    "263783498457",  # Christine Chiweshe (Tagoneswa Hardware)
    "263718174894",  # Mazviita Sibongile Ruzvidzo (LG Plast)
}

REMOVED_SALES_REPS: Set[str] = set()

def get_client_ip(request: Request) -> str:
    """Extracts client IP address safely from headers or connection."""
    try:
        if hasattr(request, "headers"):
            forwarded = request.headers.get("x-forwarded-for")
            if isinstance(forwarded, str) and forwarded.strip():
                return forwarded.split(",")[0].strip()
        if hasattr(request, "client") and request.client:
            host = getattr(request.client, "host", None)
            if isinstance(host, str) and host.strip():
                return host.strip()
    except Exception:
        pass
    return "127.0.0.1"

def format_duration(seconds: float) -> str:
    """Formats time duration in seconds to clean string (e.g. 1h 25m)."""
    if seconds is None or seconds < 0:
        return "--"
    mins = int(seconds // 60)
    if mins < 1:
        return "< 1m"
    if mins < 60:
        return f"{mins}m"
    hours = mins // 60
    rem_mins = mins % 60
    if hours < 24:
        return f"{hours}h {rem_mins}m"
    days = hours // 24
    rem_hours = hours % 24
    return f"{days}d {rem_hours}h"

# -------------------------------------------------------------
# Authentication Routes (/login, /logout, /api/logout)
# -------------------------------------------------------------
@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    """Renders clean mobile-friendly white-themed login page with Tagoneswa branding."""
    user = get_current_user_from_request(request)
    if user:
        return RedirectResponse(url="/dashboard", status_code=status.HTTP_302_FOUND)

    html_content = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <title>Tagoneswa Operations Portal — Secure Login</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <script>
        tailwind.config = {
            darkMode: 'class',
            theme: {
                extend: {
                    fontFamily: {
                        sans: ['Plus Jakarta Sans', 'sans-serif'],
                    }
                }
            }
        };
        if (localStorage.getItem('tagoneswa_theme') === 'dark' || (!('tagoneswa_theme' in localStorage) && window.matchMedia('(prefers-color-scheme: dark)').matches)) {
            document.documentElement.classList.add('dark');
        } else {
            document.documentElement.classList.remove('dark');
        }
    </script>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&display=swap" rel="stylesheet">
    <style>
        body { font-family: 'Plus Jakarta Sans', sans-serif; }
    </style>
</head>
<body class="bg-slate-50 dark:bg-black text-slate-800 dark:text-zinc-100 min-h-screen flex items-center justify-center p-3 sm:p-6 transition-colors duration-200">
    <div class="bg-white dark:bg-[#0a0a0d] border border-slate-200 dark:border-zinc-800/80 rounded-3xl shadow-2xl w-full max-w-md p-6 sm:p-10 transition-colors duration-200">
        <div class="text-center mb-6 sm:mb-8">
            <div class="inline-flex items-center gap-2 bg-blue-50 dark:bg-blue-500/10 border border-blue-200 dark:border-blue-500/30 text-blue-700 dark:text-blue-300 px-3.5 py-1 rounded-full text-xs font-bold mb-3 sm:mb-4">
                Enterprise Security
            </div>
            <h1 class="text-2xl sm:text-3xl font-extrabold text-slate-900 dark:text-zinc-100 tracking-tight">Tagoneswa Portal</h1>
            <p class="text-slate-500 dark:text-zinc-400 text-xs sm:text-sm mt-1">Fleet Approval • IT Support • Projects • Workshop</p>
        </div>

        <div id="errorBox" class="hidden bg-red-50 dark:bg-red-950/40 border border-red-200 dark:border-red-900/60 text-red-700 dark:text-red-300 px-4 py-3 rounded-xl text-xs sm:text-sm mb-5 font-medium"></div>

        <form id="loginForm" class="space-y-4 sm:space-y-5">
            <div>
                <label class="block text-xs font-bold text-slate-700 dark:text-zinc-300 uppercase tracking-wider mb-1.5 sm:mb-2" for="username">Username</label>
                <input class="w-full bg-slate-50 dark:bg-[#121216] border border-slate-300 dark:border-zinc-750 rounded-xl px-4 py-3 text-slate-900 dark:text-zinc-100 text-base sm:text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:bg-white dark:focus:bg-[#181820] transition" type="text" id="username" name="username" placeholder="e.g. admin, logistics, itsupport, projects" required autofocus autocomplete="username">
            </div>

            <div>
                <label class="block text-xs font-bold text-slate-700 dark:text-zinc-300 uppercase tracking-wider mb-1.5 sm:mb-2" for="password">Password</label>
                <div class="relative">
                    <input class="w-full bg-slate-50 dark:bg-[#121216] border border-slate-300 dark:border-zinc-750 rounded-xl px-4 py-3 text-slate-900 dark:text-zinc-100 text-base sm:text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:bg-white dark:focus:bg-[#181820] transition" type="password" id="password" name="password" placeholder="••••••••••••" required autocomplete="current-password">
                    <button type="button" class="absolute right-3.5 top-1/2 -translate-y-1/2 text-xs font-semibold text-slate-400 hover:text-slate-600 dark:hover:text-zinc-200 px-2 py-1 cursor-pointer" onclick="togglePassword()">Show</button>
                </div>
            </div>

            <button type="submit" class="w-full bg-zinc-900 hover:bg-zinc-800 dark:bg-zinc-50 dark:hover:bg-zinc-200 text-white dark:text-zinc-900 font-semibold py-3 rounded-lg shadow-xs transition duration-150 text-sm sm:text-base flex items-center justify-center gap-2 cursor-pointer" id="loginBtn">
                Sign In to Dashboard →
            </button>
        </form>

        <div class="mt-6 sm:mt-8 text-center text-[11px] sm:text-xs text-slate-400 dark:text-zinc-500 border-t border-slate-100 dark:border-zinc-850 pt-5 sm:pt-6">
            Tagoneswa Holdings • Internal Management System
        </div>
    </div>

    <script>
        function togglePassword() {
            const pw = document.getElementById('password');
            const btn = event.target;
            if (pw.type === 'password') {
                pw.type = 'text';
                btn.textContent = 'Hide';
            } else {
                pw.type = 'password';
                btn.textContent = 'Show';
            }
        }

        document.getElementById('loginForm').addEventListener('submit', async (e) => {
            e.preventDefault();
            const errBox = document.getElementById('errorBox');
            const btn = document.getElementById('loginBtn');
            errBox.classList.add('hidden');
            btn.disabled = true;
            btn.textContent = 'Authenticating...';

            const username = document.getElementById('username').value.trim();
            const password = document.getElementById('password').value.trim();

            try {
                const res = await fetch('/login', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ username, password })
                });

                const data = await res.json();
                if (res.ok && data.status === 'success') {
                    window.location.href = data.redirect || '/dashboard';
                } else {
                    errBox.textContent = data.detail || 'Invalid credentials. Please verify your password.';
                    errBox.classList.remove('hidden');
                    btn.disabled = false;
                    btn.textContent = 'Sign In to Dashboard →';
                }
            } catch (err) {
                errBox.textContent = 'Network error. Please check your connection.';
                errBox.classList.remove('hidden');
                btn.disabled = false;
                btn.textContent = 'Sign In to Dashboard →';
            }
        });
    </script>
</body>
</html>"""
    return HTMLResponse(content=html_content)

@router.post("/login")
async def process_login(request: Request):
    """Verifies credentials, enforces single-active-session per account, updates session tokens, and sets HttpOnly cookie."""
    content_type = request.headers.get("content-type", "")
    username = ""
    password = ""
    
    if "application/json" in content_type:
        try:
            body = await request.json()
            username = body.get("username", "")
            password = body.get("password", "")
        except Exception:
            pass
    else:
        try:
            form = await request.form()
            username = form.get("username", "")
            password = form.get("password", "")
        except Exception:
            from urllib.parse import parse_qs
            raw = (await request.body()).decode("utf-8", errors="ignore")
            parsed = parse_qs(raw)
            username = parsed.get("username", [""])[0]
            password = parsed.get("password", [""])[0]

    clean_user = str(username).strip().lower()
    if not is_user_active(clean_user):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Account deactivated or access has been revoked. Contact system administrator."
        )

    user = authenticate_user(str(username), str(password))
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials. Access restricted to authorized personnel."
        )

    # Generate a cryptographically unique session ID for this login
    sid = generate_session_id()

    # Persist session token and device login telemetry into database
    try:
        async with async_session_factory() as db_session:
            stmt = select(WebUser).where(func.lower(WebUser.username) == clean_user)
            wu = (await db_session.execute(stmt)).scalars().first()
            if wu:
                wu.current_session_token = sid
                wu.session_version = (wu.session_version or 1) + 1
                wu.last_login_at = datetime.datetime.utcnow()
                wu.last_login_ip = get_client_ip(request)
                await db_session.commit()
    except Exception as db_err:
        logger.warning(f"Could not persist session token for {clean_user}: {db_err}")

    # Set in memory active session cache
    set_user_session(clean_user, sid)

    token = create_session_token(user["username"], user["role"], session_id=sid)
    default_tab = "fleet" if user["role"] in ("FLEET_ADMIN", "SALES_ADMIN", "ACCOUNTS_USER", "LOGISTICS_MANAGER") else ("logistics" if user["role"] == "LOGISTICS_ADMIN" else ("projects" if user["role"] == "PROJECTS_ADMIN" else "it"))
    
    resp = JSONResponse({
        "status": "success",
        "redirect": f"/dashboard#{default_tab}",
        "user": user["name"],
        "role": user["role"]
    })
    resp.set_cookie(
        key=COOKIE_NAME,
        value=token,
        max_age=SESSION_MAX_AGE,
        httponly=True,
        samesite="lax",
        secure=False,
        path="/"
    )
    return resp

@router.get("/logout")
async def logout(request: Request):
    """Invalidates session cookie, revokes active session, and redirects directly to login."""
    user = get_current_user_from_request(request)
    if user:
        uname = user.get("username", "").strip().lower()
        invalidate_user_session(uname)
        try:
            async with async_session_factory() as db_session:
                stmt = select(WebUser).where(func.lower(WebUser.username) == uname)
                wu = (await db_session.execute(stmt)).scalars().first()
                if wu:
                    wu.current_session_token = None
                    await db_session.commit()
        except Exception:
            pass
    resp = RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)
    resp.delete_cookie(key=COOKIE_NAME, path="/")
    return resp

@router.post("/api/logout")
async def api_logout(request: Request):
    """API endpoint to explicitly invalidate session."""
    user = get_current_user_from_request(request)
    if user:
        uname = user.get("username", "").strip().lower()
        invalidate_user_session(uname)
        try:
            async with async_session_factory() as db_session:
                stmt = select(WebUser).where(func.lower(WebUser.username) == uname)
                wu = (await db_session.execute(stmt)).scalars().first()
                if wu:
                    wu.current_session_token = None
                    await db_session.commit()
        except Exception:
            pass
    resp = JSONResponse({"status": "logged_out"})
    resp.delete_cookie(key=COOKIE_NAME, path="/")
    return resp

# -------------------------------------------------------------
# Configuration & Management APIs (V2)
# -------------------------------------------------------------
@router.get("/api/v2/config/settings")
async def api_get_settings(request: Request):
    """Returns current active business rules and all 45 city minimum thresholds."""
    user = get_current_user_from_request(request)
    if not user:
        raise HTTPException(status_code=401, detail="Unauthorized")
    return {
        "fuel_price_usd": get_fuel_price(),
        "expense_budget_pct": get_expense_budget_pct(),
        "meal_rate_usd": get_meal_rate(),
        "accommodation_rate_usd": get_accommodation_rate(),
        "route_rules": get_all_cached_city_rules()
    }


@router.post("/api/v2/config/update-fuel")
@router.post("/api/v2/config/fuel-price")
async def api_update_fuel(request: Request, db: AsyncSession = Depends(get_db)):
    """Updates active fuel price and optionally auto-recalculates all 45 city minimums."""
    user = get_current_user_from_request(request)
    require_permission(user, "manage_fuel_price")
    
    body = await request.json()
    new_price = float(body.get("fuel_price") or body.get("fuel_price_usd") or 1.55)
    recalc = bool(body.get("recalculate_cities", False))
    uname = user.get("name", "Admin")
    urole = user.get("role", "FLEET_ADMIN")
    old_price = get_fuel_price()

    if recalc:
        res = await recalculate_all_city_minimums(db, new_price, updated_by=uname)
        audit = AuditLog(
            username=uname,
            user_role=urole,
            action="UPDATE_FUEL_PRICE",
            module="CONFIG",
            permission_used="manage_fuel_price",
            entity_id="fuel_price_usd",
            previous_value={"fuel_price": old_price},
            new_value={"fuel_price": new_price, "recalculate_cities": True},
            remarks=f"Fuel price updated to ${new_price:.2f}/L with city recalculation",
            ip_address=get_client_ip(request),
            created_at=datetime.datetime.utcnow()
        )
        db.add(audit)
        await db.commit()
        return res
    else:
        await update_system_setting(db, "fuel_price_usd", new_price, changed_by=uname, reason=f"Fuel price updated to ${new_price:.2f}/L")
        audit = AuditLog(
            username=uname,
            user_role=urole,
            action="UPDATE_FUEL_PRICE",
            module="CONFIG",
            permission_used="manage_fuel_price",
            entity_id="fuel_price_usd",
            previous_value={"fuel_price": old_price},
            new_value={"fuel_price": new_price, "recalculate_cities": False},
            remarks=f"Fuel price updated to ${new_price:.2f}/L without city recalculation",
            ip_address=get_client_ip(request),
            created_at=datetime.datetime.utcnow()
        )
        db.add(audit)
        await db.commit()
        return {"status": "success", "fuel_price": new_price}


@router.post("/api/v2/config/update-city-minimum")
@router.post("/api/v2/config/city-rules/save")
async def api_update_city_min(request: Request, db: AsyncSession = Depends(get_db)):
    """Updates minimum sales and van minimum for a specific city."""
    user = get_current_user_from_request(request)
    require_permission(user, "manage_city_minimums")
    
    body = await request.json()
    city_key = body.get("city_key", "").strip().lower()
    min_sales = float(body.get("min_sales", 0.0))
    van_min = float(body.get("van_min", 0.0))
    uname = user.get("name", "Admin")

    ok = await update_city_rule(db, city_key, min_sales, van_min, updated_by=uname)
    if not ok:
        raise HTTPException(status_code=404, detail=f"City corridor '{city_key}' not found.")

    audit = AuditLog(
        username=uname,
        user_role=user.get("role", "FLEET_ADMIN"),
        action="UPDATE_CITY_MINIMUM",
        module="CONFIG",
        permission_used="manage_city_minimums",
        entity_id=city_key,
        previous_value={"city_key": city_key},
        new_value={"min_sales": min_sales, "van_min": van_min},
        remarks=f"Updated minimum sales thresholds for {city_key}",
        ip_address=get_client_ip(request),
        created_at=datetime.datetime.utcnow()
    )
    db.add(audit)
    await db.commit()
    return {"status": "success", "city_key": city_key, "min_sales": min_sales, "van_min": van_min}


@router.post("/api/v2/config/update-meal-rate")
async def api_update_meal_rate(request: Request, db: AsyncSession = Depends(get_db)):
    """Updates meal rate allowance per qualifying meal."""
    user = get_current_user_from_request(request)
    require_permission(user, "manage_meal_rate")
    
    body = await request.json()
    rate = float(body.get("meal_rate") if "meal_rate" in body else (body.get("meal_rate_usd") or 0.0))
    if rate < 0:
        raise HTTPException(status_code=400, detail="Meal rate cannot be negative.")
    
    reason = str(body.get("reason") or "Meal allowance rate updated").strip()
    uname = user.get("name", "Admin")
    await update_meal_rate(db, rate, updated_by=uname, reason=reason)
    return {"status": "success", "meal_rate_usd": rate}


@router.post("/api/v2/config/update-accommodation-rate")
async def api_update_accommodation_rate(request: Request, db: AsyncSession = Depends(get_db)):
    """Updates nightly accommodation allowance rate."""
    user = get_current_user_from_request(request)
    require_permission(user, "manage_accommodation_rate")
    
    body = await request.json()
    rate = float(body.get("accommodation_rate") if "accommodation_rate" in body else (body.get("accommodation_rate_usd") or 0.0))
    if rate < 0:
        raise HTTPException(status_code=400, detail="Accommodation rate cannot be negative.")
    
    reason = str(body.get("reason") or "Accommodation allowance rate updated").strip()
    uname = user.get("name", "Admin")
    await update_accommodation_rate(db, rate, updated_by=uname, reason=reason)
    return {"status": "success", "accommodation_rate_usd": rate}


@router.post("/api/v2/finance/clear-sales-rep-payment")
@router.post("/api/v2/finance/clear-payment")
async def api_clear_sales_rep_payment(request: Request, db: AsyncSession = Depends(get_db)):
    """Clears pending sales rep shortfall debt with audit trail and ledger offsetting."""
    user = get_current_user_from_request(request)
    require_permission(user, "clear_sales_rep_debt")
    
    body = await request.json()
    phone = body.get("salesperson_phone", "").replace("+", "").strip()
    name = body.get("salesperson_name", "")
    cleared_amount = round(float(body.get("cleared_amount", 0.0)), 2)
    payment_method = body.get("payment_method", "CASH")
    reference = body.get("reference_number", "").strip()
    remarks = body.get("remarks", "").strip()

    if cleared_amount <= 0:
        raise HTTPException(status_code=400, detail="Cleared amount must be greater than zero.")

    current_balance = await get_sales_rep_pending_balance(db, phone)
    if current_balance <= 0:
        raise HTTPException(status_code=400, detail="Sales representative has no outstanding shortfall debt to clear.")
    if cleared_amount > current_balance:
        raise HTTPException(status_code=400, detail=f"Cleared amount (${cleared_amount:.2f}) cannot exceed current debt (${current_balance:.2f}).")

    if not reference:
        reference = "WAIVER-SUJIT" if payment_method == "DEBT_WRITE_OFF" else "OFFICIAL-OFFSET"

    remaining_balance = round(current_balance - cleared_amount, 2)
    uname = user.get("name", "Officer")

    # 1. Record payment clearance
    payment_rec = SalesRepPayment(
        salesperson_phone=phone,
        salesperson_name=name,
        cleared_amount=cleared_amount,
        payment_method=payment_method,
        reference_number=reference,
        previous_balance=current_balance,
        remaining_balance=remaining_balance,
        recorded_by=uname,
        remarks=remarks,
        payment_date=datetime.datetime.utcnow(),
        created_at=datetime.datetime.utcnow()
    )
    db.add(payment_rec)

    # 2. Add offsetting recovery entry into FleetPendingLedger (negative amount offsets debt)
    if payment_method == "DEBT_WRITE_OFF":
        ledger_note = f"Management Debt Write-Off / Waiver (Approved by Sujit). Amount: ${cleared_amount:.2f}. Notes: {remarks}"
    else:
        ledger_note = f"Payment cleared via {payment_method}. Ref: {reference}. Notes: {remarks}"

    ledger_entry = FleetPendingLedger(
        salesperson_phone=phone,
        salesperson_name=name,
        entry_type="PAYMENT_CLEARED_BY_ACCOUNTS",
        amount=-cleared_amount,
        notes=ledger_note,
        created_at=datetime.datetime.utcnow()
    )
    db.add(ledger_entry)

    # 3. Add Audit Log with permission_used and client IP
    audit = AuditLog(
        username=uname,
        user_role=user.get("role", "FLEET_ADMIN"),
        action="CLEAR_SALES_REP_DEBT",
        module="FINANCE",
        permission_used="clear_sales_rep_debt",
        entity_id=phone,
        previous_value={"balance": current_balance},
        new_value={"cleared": cleared_amount, "remaining": remaining_balance, "method": payment_method, "ref": reference},
        remarks=remarks,
        ip_address=get_client_ip(request),
        created_at=datetime.datetime.utcnow()
    )
    db.add(audit)
    await db.commit()

    return {
        "status": "success",
        "salesperson_phone": phone,
        "cleared_amount": cleared_amount,
        "remaining_balance": remaining_balance
    }


@router.get("/api/v2/audit/logs")
async def api_get_audit_logs(request: Request, db: AsyncSession = Depends(get_db)):
    """Returns recent audit logs across finance, config, and fleet operations."""
    user = get_current_user_from_request(request)
    require_permission(user, "view_audit_logs")
    
    stmt = select(AuditLog).order_by(AuditLog.id.desc()).limit(100)
    res = await db.execute(stmt)
    logs = res.scalars().all()
    records = []
    for l in logs:
        records.append({
            "id": l.id,
            "username": l.username,
            "user_role": l.user_role or "--",
            "action": l.action,
            "module": l.module,
            "permission_used": getattr(l, "permission_used", None) or "--",
            "entity_id": l.entity_id or "--",
            "previous_value": l.previous_value,
            "new_value": l.new_value,
            "remarks": l.remarks or "",
            "created_at": l.created_at.strftime("%Y-%m-%d %H:%M:%S") if l.created_at else ""
        })
    return {"status": "success", "logs": records}


@router.post("/api/v2/config/update-operational-params")
async def api_update_operational_params(request: Request, db: AsyncSession = Depends(get_db)):
    """Updates global rates: meal allowance, accommodation rate, expense budget %, van surcharge."""
    user = get_current_user_from_request(request)
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required.")
    
    body = await request.json()
    uname = user.get("name", "Admin")
    updated = {}

    meal_rate = body.get("meal_rate_usd") if "meal_rate_usd" in body else body.get("meal_rate")
    if meal_rate is not None:
        require_permission(user, "manage_meal_rate")
        val = round(float(meal_rate), 2)
        await update_system_setting(db, "meal_rate_usd", val, changed_by=uname, reason="Updated meal rate allowance")
        updated["meal_rate_usd"] = val

    accom_rate = body.get("accommodation_rate_usd") if "accommodation_rate_usd" in body else body.get("accommodation_rate")
    if accom_rate is not None:
        require_permission(user, "manage_accommodation_rate")
        val = round(float(accom_rate), 2)
        await update_system_setting(db, "accommodation_rate_usd", val, changed_by=uname, reason="Updated accommodation rate allowance")
        updated["accommodation_rate_usd"] = val

    if "expense_budget_pct" in body:
        require_permission(user, "manage_fuel_price")
        val = round(float(body["expense_budget_pct"]), 4)
        await update_system_setting(db, "expense_budget_pct", val, changed_by=uname, reason="Updated expense budget pct")
        updated["expense_budget_pct"] = val

    if "van_minimum_surcharge" in body:
        require_permission(user, "manage_city_minimums")
        val = round(float(body["van_minimum_surcharge"]), 2)
        await update_system_setting(db, "van_minimum_surcharge", val, changed_by=uname, reason="Updated van surcharge")
        updated["van_minimum_surcharge"] = val

    return {"status": "success", "updated": updated}


# -------------------------------------------------------------
# User Management & RBAC Administration (MASTER_ADMIN only)
# -------------------------------------------------------------
@router.get("/api/v2/admin/users")
async def api_get_users(request: Request, db: AsyncSession = Depends(get_db)):
    """Returns all users with roles, inherited permissions, custom overrides, and effective permissions."""
    user = get_current_user_from_request(request)
    require_permission(user, "manage_user_permissions")

    # Fetch from web_users
    stmt = select(WebUser).order_by(WebUser.id.asc())
    web_users = (await db.execute(stmt)).scalars().all()
    
    # Fetch all custom permissions
    stmt_perms = select(UserCustomPermission)
    all_custom = (await db.execute(stmt_perms)).scalars().all()
    custom_by_user = {}
    for cp in all_custom:
        if cp.user_id not in custom_by_user:
            custom_by_user[cp.user_id] = []
        custom_by_user[cp.user_id].append({
            "permission_key": cp.permission_key,
            "is_granted": cp.is_granted,
            "granted_by": cp.granted_by,
            "granted_at": cp.granted_at.strftime("%Y-%m-%d %H:%M") if cp.granted_at else "",
            "reason": cp.reason or ""
        })

    result = []
    seen_usernames = set()
    for wu in web_users:
        u_clean = wu.username.lower()
        seen_usernames.add(u_clean)
        custom_dict = {
            p["permission_key"]: p["is_granted"] for p in custom_by_user.get(wu.id, [])
        }
        # overlay with in-memory cache if any
        cached = USER_CUSTOM_PERMISSIONS_CACHE.get(u_clean, {})
        for k, v in cached.items():
            if k not in custom_dict:
                custom_dict[k] = v

        u_dict = {
            "username": wu.username,
            "role": wu.role,
            "custom_permissions": custom_dict
        }
        inherited = list(ROLE_DEFAULT_PERMISSIONS.get(wu.role, set()))
        custom_granted = [k for k, v in custom_dict.items() if v]
        custom_revoked = [k for k, v in custom_dict.items() if not v]
        effective = list(get_effective_permissions(u_dict))

        result.append({
            "id": wu.id,
            "username": wu.username,
            "full_name": wu.full_name,
            "role": wu.role,
            "email": wu.email or "",
            "phone": wu.phone or "",
            "company": wu.company or USERS_DB.get(wu.username.lower(), {}).get("company", ""),
            "is_active": wu.is_active and (u_clean not in REVOKED_USERS),
            "has_active_session": bool(ACTIVE_USER_SESSIONS.get(u_clean)),
            "last_login_at": wu.last_login_at.strftime("%Y-%m-%d %H:%M") if wu.last_login_at else "--",
            "last_login_ip": wu.last_login_ip or "--",
            "inherited_permissions": inherited,
            "custom_granted_permissions": custom_granted,
            "custom_revoked_permissions": custom_revoked,
            "effective_permissions": effective,
            "custom_details": custom_by_user.get(wu.id, []),
            "updated_at": wu.updated_at.strftime("%Y-%m-%d %H:%M") if wu.updated_at else ""
        })

    # Also include any USERS_DB users not in web_users
    for uname, udata in USERS_DB.items():
        if uname.lower() not in seen_usernames:
            inherited = list(ROLE_DEFAULT_PERMISSIONS.get(udata["role"], set()))
            cached_custom = USER_CUSTOM_PERMISSIONS_CACHE.get(uname.lower(), {})
            custom_granted = [k for k, v in cached_custom.items() if v]
            custom_revoked = [k for k, v in cached_custom.items() if not v]
            u_dict = {"username": uname, "role": udata["role"], "custom_permissions": cached_custom}
            effective = list(get_effective_permissions(u_dict))
            result.append({
                "id": None,
                "username": uname,
                "full_name": udata["name"],
                "role": udata["role"],
                "company": udata.get("company", ""),
                "email": "",
                "phone": udata.get("phone", ""),
                "is_active": is_user_active(uname),
                "has_active_session": bool(ACTIVE_USER_SESSIONS.get(uname.lower())),
                "last_login_at": "--",
                "last_login_ip": "--",
                "inherited_permissions": inherited,
                "custom_granted_permissions": custom_granted,
                "custom_revoked_permissions": custom_revoked,
                "effective_permissions": effective,
                "custom_details": [],
                "updated_at": ""
            })

    return {
        "status": "success",
        "users": result,
        "all_permissions": ALL_PERMISSIONS,
        "role_default_permissions": {r: list(p) for r, p in ROLE_DEFAULT_PERMISSIONS.items()}
    }


@router.post("/api/v2/admin/users/create")
async def api_create_user(request: Request, db: AsyncSession = Depends(get_db)):
    """Creates a new user account with role, password, and optional company/phone (MASTER_ADMIN only)."""
    user = get_current_user_from_request(request)
    require_permission(user, "manage_user_permissions")

    body = await request.json()
    username = body.get("username", "").strip().lower()
    password = body.get("password", "").strip()
    full_name = body.get("full_name", "").strip()
    role = body.get("role", "").strip()
    company = body.get("company", "").strip()
    phone = body.get("phone", "").strip()

    if not username or len(username) < 3:
        raise HTTPException(status_code=400, detail="Username must be at least 3 characters long.")
    if not password or len(password) < 6:
        raise HTTPException(status_code=400, detail="Password must be at least 6 characters long.")
    if role not in ROLE_DEFAULT_PERMISSIONS:
        raise HTTPException(status_code=400, detail=f"Invalid role '{role}'.")

    # Check if user already exists
    stmt = select(WebUser).where(func.lower(WebUser.username) == username)
    existing = (await db.execute(stmt)).scalars().first()
    if existing:
        raise HTTPException(status_code=400, detail=f"User account '{username}' already exists.")

    # Remove from revoked_users if present
    stmt_rev = select(RevokedUser).where(func.lower(RevokedUser.username) == username)
    rev_record = (await db.execute(stmt_rev)).scalars().first()
    if rev_record:
        await db.delete(rev_record)
    restore_user_account(username)

    new_user = WebUser(
        username=username,
        password_hash=password,
        full_name=full_name or username.title(),
        role=role,
        company=company or None,
        phone=phone or None,
        is_active=True,
        session_version=1,
        created_at=datetime.datetime.utcnow(),
        updated_at=datetime.datetime.utcnow()
    )
    db.add(new_user)

    register_user_in_memory(username, {
        "password": password,
        "role": role,
        "name": full_name or username.title(),
        "company": company,
        "phone": phone,
        "is_active": True
    })

    audit = AuditLog(
        username=user.get("username", "admin"),
        user_role=user.get("role", "MASTER_ADMIN"),
        action="CREATE_USER_ACCOUNT",
        module="USER_MANAGEMENT",
        permission_used="manage_user_permissions",
        entity_id=username,
        previous_value=None,
        new_value={"role": role, "company": company, "phone": phone},
        remarks=f"Created user account '{username}' ({role}) by {user.get('username')}",
        ip_address=get_client_ip(request),
        created_at=datetime.datetime.utcnow()
    )
    db.add(audit)
    await db.commit()
    await db.refresh(new_user)

    return {"status": "success", "username": username, "message": f"User account '{username}' created successfully."}


@router.post("/api/v2/admin/users/revoke-sessions")
async def api_revoke_user_sessions(request: Request, db: AsyncSession = Depends(get_db)):
    """Terminates active sessions across all devices for a given user account (MASTER_ADMIN only)."""
    user = get_current_user_from_request(request)
    require_permission(user, "manage_user_permissions")

    body = await request.json()
    username = body.get("username", "").strip().lower()
    if not username:
        raise HTTPException(status_code=400, detail="Username is required.")

    stmt = select(WebUser).where(func.lower(WebUser.username) == username)
    w_user = (await db.execute(stmt)).scalars().first()
    if w_user:
        w_user.current_session_token = None
        w_user.session_version = (w_user.session_version or 1) + 1
        w_user.updated_at = datetime.datetime.utcnow()

    invalidate_user_session(username)

    audit = AuditLog(
        username=user.get("username", "admin"),
        user_role=user.get("role", "MASTER_ADMIN"),
        action="REVOKE_USER_SESSIONS",
        module="SECURITY",
        permission_used="manage_user_permissions",
        entity_id=username,
        previous_value=None,
        new_value={"sessions_revoked": True},
        remarks=f"Revoked active device sessions for '{username}' by {user.get('username')}",
        ip_address=get_client_ip(request),
        created_at=datetime.datetime.utcnow()
    )
    db.add(audit)
    await db.commit()

    return {
        "status": "success",
        "username": username,
        "message": f"Active sessions revoked for '{username}'. Any active device is now disconnected."
    }


@router.post("/api/v2/admin/users/toggle-status")
async def api_toggle_user_status(request: Request, db: AsyncSession = Depends(get_db)):
    """Deactivates/suspends or reactivates a user account (MASTER_ADMIN only)."""
    user = get_current_user_from_request(request)
    require_permission(user, "manage_user_permissions")

    body = await request.json()
    username = body.get("username", "").strip().lower()
    is_active = bool(body.get("is_active", False))

    if not username:
        raise HTTPException(status_code=400, detail="Username is required.")
    if username == "admin" and not is_active:
        raise HTTPException(status_code=400, detail="Cannot deactivate super administrator 'admin'.")

    stmt = select(WebUser).where(func.lower(WebUser.username) == username)
    w_user = (await db.execute(stmt)).scalars().first()
    if not w_user:
        if username in USERS_DB:
            u_data = USERS_DB[username]
            w_user = WebUser(
                username=username,
                password_hash=u_data.get("password", "TempPass@2026!"),
                full_name=u_data.get("name", username.title()),
                role=u_data.get("role", "LOGISTICS_USER"),
                is_active=is_active,
                created_at=datetime.datetime.utcnow()
            )
            db.add(w_user)
        else:
            raise HTTPException(status_code=404, detail=f"User '{username}' not found.")
    else:
        w_user.is_active = is_active
        w_user.updated_at = datetime.datetime.utcnow()

    if not is_active:
        w_user.current_session_token = None
        invalidate_user_session(username)
        if username in USERS_DB:
            USERS_DB[username]["is_active"] = False
    else:
        restore_user_account(username)

    audit = AuditLog(
        username=user.get("username", "admin"),
        user_role=user.get("role", "MASTER_ADMIN"),
        action="SUSPEND_USER_ACCOUNT" if not is_active else "ACTIVATE_USER_ACCOUNT",
        module="USER_MANAGEMENT",
        permission_used="manage_user_permissions",
        entity_id=username,
        previous_value={"is_active": not is_active},
        new_value={"is_active": is_active},
        remarks=f"{'Deactivated/Suspended' if not is_active else 'Reactivated'} account '{username}' by {user.get('username')}",
        ip_address=get_client_ip(request),
        created_at=datetime.datetime.utcnow()
    )
    db.add(audit)
    await db.commit()

    action_text = "activated" if is_active else "deactivated and disconnected"
    return {"status": "success", "username": username, "is_active": is_active, "message": f"Account '{username}' has been {action_text}."}


@router.post("/api/v2/admin/users/save")
async def api_save_user(request: Request, db: AsyncSession = Depends(get_db)):
    """Creates or updates a user role, name, active status (MASTER_ADMIN only)."""
    user = get_current_user_from_request(request)
    require_permission(user, "manage_user_permissions")

    body = await request.json()
    username = body.get("username", "").strip().lower()
    full_name = body.get("full_name", "").strip()
    role = body.get("role", "").strip()
    is_active = bool(body.get("is_active", True))
    reason = str(body.get("reason", "")).strip()

    if not username or not role:
        raise HTTPException(status_code=400, detail="Username and Role are required.")
    if role not in ROLE_DEFAULT_PERMISSIONS:
        raise HTTPException(status_code=400, detail=f"Invalid role '{role}'.")
    if not reason:
        raise HTTPException(status_code=400, detail="A reason is required for user account modifications.")

    stmt = select(WebUser).where(WebUser.username == username)
    w_user = (await db.execute(stmt)).scalars().first()
    old_role = w_user.role if w_user else (USERS_DB.get(username, {}).get("role", "--"))

    if w_user:
        w_user.full_name = full_name or w_user.full_name
        w_user.role = role
        w_user.is_active = is_active
        w_user.updated_at = datetime.datetime.utcnow()
        if not is_active:
            w_user.current_session_token = None
            invalidate_user_session(username)
    else:
        w_user = WebUser(
            username=username,
            password_hash="TempPassword@2026!",
            full_name=full_name or username.title(),
            role=role,
            is_active=is_active,
            created_at=datetime.datetime.utcnow(),
            updated_at=datetime.datetime.utcnow()
        )
        db.add(w_user)

    # Sync USERS_DB in memory
    if username in USERS_DB:
        USERS_DB[username]["role"] = role
        USERS_DB[username]["is_active"] = is_active
        if full_name:
            USERS_DB[username]["name"] = full_name

    if not is_active:
        invalidate_user_session(username)
    else:
        restore_user_account(username)

    audit = AuditLog(
        username=user.get("name", "Admin"),
        user_role=user.get("role", "MASTER_ADMIN"),
        action="CHANGE_USER_ROLE",
        module="AUTH",
        permission_used="manage_user_permissions",
        entity_id=username,
        previous_value={"role": old_role},
        new_value={"role": role, "active": is_active},
        remarks=reason,
        ip_address=get_client_ip(request),
        created_at=datetime.datetime.utcnow()
    )
    db.add(audit)
    await db.commit()
    await db.refresh(w_user)

    return {"status": "success", "username": username, "role": role, "is_active": is_active}


@router.post("/api/v2/admin/users/delete")
async def api_delete_user(request: Request, db: AsyncSession = Depends(get_db)):
    """Permanently deletes or deactivates a user account and blacklists it from logins (MASTER_ADMIN only)."""
    user = get_current_user_from_request(request)
    require_permission(user, "manage_user_permissions")

    body = await request.json()
    username = body.get("username", "").strip().lower()
    reason = str(body.get("reason", "Deleted by administrator")).strip()
    if not username:
        raise HTTPException(status_code=400, detail="Username is required.")
    if username == "admin":
        raise HTTPException(status_code=400, detail="Cannot delete super administrator 'admin'.")

    # Record tombstone in revoked_users
    stmt_rev = select(RevokedUser).where(func.lower(RevokedUser.username) == username)
    existing_rev = (await db.execute(stmt_rev)).scalars().first()
    if not existing_rev:
        db.add(RevokedUser(
            username=username,
            revoked_at=datetime.datetime.utcnow(),
            revoked_by=user.get("username", "admin"),
            reason=reason
        ))

    # Delete from web_users table
    stmt = select(WebUser).where(WebUser.username == username)
    w_user = (await db.execute(stmt)).scalars().first()
    deleted_role = "UNKNOWN"
    if w_user:
        deleted_role = w_user.role
        await db.delete(w_user)

    # Invalidate runtime memory security caches
    revoke_user_account(username)

    # Audit log
    audit = AuditLog(
        username=user.get("username", "admin"),
        user_role=user.get("role", "MASTER_ADMIN"),
        action="DELETE_USER_ACCOUNT",
        module="USER_MANAGEMENT",
        permission_used="manage_user_permissions",
        entity_id=username,
        previous_value={"role": deleted_role},
        new_value=None,
        remarks=f"Permanently deleted and revoked user account '{username}': {reason}",
        ip_address=get_client_ip(request),
        created_at=datetime.datetime.utcnow()
    )
    db.add(audit)
    await db.commit()

    return {"status": "success", "username": username, "message": f"User account '{username}' permanently removed and revoked."}


@router.post("/api/v2/admin/users/permissions")
async def api_toggle_user_permission(request: Request, db: AsyncSession = Depends(get_db)):
    """Grants or revokes a custom delegated permission for a specific user (MASTER_ADMIN only)."""
    user = get_current_user_from_request(request)
    require_permission(user, "manage_user_permissions")

    body = await request.json()
    target_username = body.get("username", "").strip().lower()
    permission_key = body.get("permission_key", "").strip()
    is_granted = bool(body.get("is_granted", True))
    reason = str(body.get("reason", "")).strip()

    if not target_username or not permission_key:
        raise HTTPException(status_code=400, detail="Username and permission_key are required.")
    if permission_key not in ALL_PERMISSIONS:
        raise HTTPException(status_code=400, detail=f"Invalid permission key '{permission_key}'.")
    if not reason:
        raise HTTPException(status_code=400, detail="A reason is required for permission grant or revocation.")

    # Find or create web_user
    stmt = select(WebUser).where(WebUser.username == target_username)
    w_user = (await db.execute(stmt)).scalars().first()
    if not w_user:
        if target_username in USERS_DB:
            u_data = USERS_DB[target_username]
            w_user = WebUser(
                username=target_username,
                password_hash=u_data["password"],
                full_name=u_data["name"],
                role=u_data["role"],
                is_active=True
            )
            db.add(w_user)
            await db.flush()
        else:
            raise HTTPException(status_code=404, detail=f"User '{target_username}' not found.")

    stmt_perm = select(UserCustomPermission).where(
        UserCustomPermission.user_id == w_user.id,
        UserCustomPermission.permission_key == permission_key
    )
    perm_record = (await db.execute(stmt_perm)).scalars().first()
    old_state = perm_record.is_granted if perm_record else None

    if perm_record:
        perm_record.is_granted = is_granted
        perm_record.granted_by = user.get("name", "Admin")
        perm_record.granted_at = datetime.datetime.utcnow()
        perm_record.reason = reason
    else:
        perm_record = UserCustomPermission(
            user_id=w_user.id,
            permission_key=permission_key,
            is_granted=is_granted,
            granted_by=user.get("name", "Admin"),
            granted_at=datetime.datetime.utcnow(),
            reason=reason
        )
        db.add(perm_record)

    set_user_custom_permission(target_username, permission_key, is_granted)

    action = "GRANT_USER_PERMISSION" if is_granted else "REVOKE_USER_PERMISSION"
    audit = AuditLog(
        username=user.get("name", "Admin"),
        user_role=user.get("role", "MASTER_ADMIN"),
        action=action,
        module="AUTH",
        permission_used="manage_user_permissions",
        entity_id=f"{target_username}:{permission_key}",
        previous_value={"is_granted": old_state},
        new_value={"is_granted": is_granted},
        remarks=reason,
        ip_address=get_client_ip(request),
        created_at=datetime.datetime.utcnow()
    )
    db.add(audit)
    await db.commit()

    u_dict = {
        "username": target_username,
        "role": w_user.role,
        "custom_permissions": USER_CUSTOM_PERMISSIONS_CACHE.get(target_username, {})
    }
    effective = list(get_effective_permissions(u_dict))

    return {
        "status": "success",
        "username": target_username,
        "permission_key": permission_key,
        "is_granted": is_granted,
        "action": action,
        "effective_permissions": effective
    }



@router.post("/api/v2/fleet/trucks/save")
async def api_save_truck(request: Request, db: AsyncSession = Depends(get_db)):
    """Creates or updates a commercial truck in the fleet database."""
    user = get_current_user_from_request(request)
    require_permission(user, "manage_trucks")
    
    body = await request.json()
    truck_id = body.get("truck_id")
    truck_number = str(body.get("truck_number", "")).strip()
    plate_number = str(body.get("plate_number", "")).strip().upper()
    model_make = str(body.get("model_make", "")).strip()
    body_type = str(body.get("body_type", "Horse")).strip()
    home_depot = str(body.get("home_depot", "Harare Central")).strip()
    is_active = bool(body.get("active", True))

    if not truck_number or not plate_number:
        raise HTTPException(status_code=400, detail="Truck number and plate number are required.")

    uname = user.get("name", "Admin")

    if truck_id:
        stmt = select(WorkshopTruck).where(WorkshopTruck.truck_id == int(truck_id))
        truck = (await db.execute(stmt)).scalars().first()
        if not truck:
            raise HTTPException(status_code=404, detail="Truck not found.")
        prev_vals = {"truck_number": truck.truck_number, "plate_number": truck.plate_number, "active": truck.active}
        truck.truck_number = truck_number
        truck.plate_number = plate_number
        truck.model_make = model_make or truck.model_make
        truck.body_type = body_type
        truck.home_depot = home_depot
        truck.active = is_active
        action = "UPDATE_COMMERCIAL_TRUCK"
    else:
        stmt = select(WorkshopTruck).where((WorkshopTruck.truck_number == truck_number) | (WorkshopTruck.plate_number == plate_number))
        existing = (await db.execute(stmt)).scalars().first()
        if existing:
            raise HTTPException(status_code=400, detail=f"Truck {truck_number} or plate {plate_number} already exists.")
        truck = WorkshopTruck(
            truck_number=truck_number,
            plate_number=plate_number,
            model_make=model_make or "Commercial Fleet",
            body_type=body_type,
            home_depot=home_depot,
            active=is_active
        )
        db.add(truck)
        prev_vals = None
        action = "ADD_COMMERCIAL_TRUCK"

    audit = AuditLog(
        username=uname,
        user_role=user.get("role", "FLEET_ADMIN"),
        action=action,
        module="FLEET_MANAGEMENT",
        permission_used="manage_trucks",
        entity_id=plate_number,
        previous_value=prev_vals,
        new_value={"truck_number": truck_number, "plate_number": plate_number, "model": model_make, "active": is_active},
        remarks=f"{action} by {uname}",
        ip_address=get_client_ip(request),
        created_at=datetime.datetime.utcnow()
    )
    db.add(audit)
    await db.commit()
    await db.refresh(truck)

    return {
        "status": "success",
        "truck": {
            "truck_id": truck.truck_id,
            "truck_number": truck.truck_number,
            "plate_number": truck.plate_number,
            "model_make": truck.model_make,
            "body_type": truck.body_type,
            "home_depot": truck.home_depot,
            "active": truck.active
        }
    }


@router.post("/api/v2/fleet/trucks/delete")
async def api_delete_truck(request: Request, db: AsyncSession = Depends(get_db)):
    """Deletes a commercial truck from the fleet database."""
    user = get_current_user_from_request(request)
    require_permission(user, "manage_trucks")

    body = await request.json()
    truck_id = body.get("truck_id")
    if not truck_id:
        raise HTTPException(status_code=400, detail="Truck ID is required.")

    stmt = select(WorkshopTruck).where(WorkshopTruck.truck_id == int(truck_id))
    truck = (await db.execute(stmt)).scalars().first()
    if not truck:
        raise HTTPException(status_code=404, detail="Truck not found.")

    uname = user.get("name", "Admin")
    plate_number = truck.plate_number
    truck_number = truck.truck_number

    await db.delete(truck)

    audit = AuditLog(
        username=uname,
        user_role=user.get("role", "FLEET_ADMIN"),
        action="DELETE_COMMERCIAL_TRUCK",
        module="FLEET_MANAGEMENT",
        permission_used="manage_trucks",
        entity_id=plate_number,
        previous_value={"truck_number": truck_number, "plate_number": plate_number},
        new_value=None,
        remarks=f"Deleted truck #{truck_number} ({plate_number}) by {uname}",
        ip_address=get_client_ip(request),
        created_at=datetime.datetime.utcnow()
    )
    db.add(audit)
    await db.commit()

    return {"status": "success", "message": f"Truck #{truck_number} ({plate_number}) removed."}


@router.post("/api/v2/fleet/drivers/save")
async def api_save_driver(request: Request, db: AsyncSession = Depends(get_db)):
    """Creates or updates a commercial driver in staff and employee directories."""
    user = get_current_user_from_request(request)
    require_permission(user, "manage_drivers")
    
    body = await request.json()
    staff_id = body.get("staff_id")
    full_name = str(body.get("full_name", "")).strip()
    phone = str(body.get("phone", "")).replace("+", "").strip()
    role = str(body.get("role", "COMMERCIAL DRIVER")).strip()
    is_active = bool(body.get("active", True))

    if not full_name or not phone:
        raise HTTPException(status_code=400, detail="Driver name and phone number are required.")

    uname = user.get("name", "Admin")

    if staff_id:
        stmt = select(WorkshopStaff).where(WorkshopStaff.staff_id == int(staff_id))
        staff = (await db.execute(stmt)).scalars().first()
        if not staff:
            raise HTTPException(status_code=404, detail="Driver not found.")
        prev_vals = {"full_name": staff.full_name, "phone": staff.phone, "active": staff.active}
        staff.full_name = full_name
        staff.phone = phone
        staff.role = role
        staff.active = is_active
        action = "UPDATE_COMMERCIAL_DRIVER"
    else:
        stmt = select(WorkshopStaff).where(WorkshopStaff.phone == phone)
        existing = (await db.execute(stmt)).scalars().first()
        if existing:
            raise HTTPException(status_code=400, detail=f"Driver with phone {phone} already exists.")
        staff = WorkshopStaff(
            full_name=full_name,
            phone=phone,
            role=role,
            active=is_active
        )
        db.add(staff)
        prev_vals = None
        action = "ADD_COMMERCIAL_DRIVER"

    # Sync to Employee table
    emp_stmt = select(Employee).where(Employee.phone == phone)
    emp = (await db.execute(emp_stmt)).scalars().first()
    if emp:
        emp.full_name = full_name
        emp.active = is_active
    else:
        dept_stmt = select(Department).where(Department.department_name.ilike("%Logistics%"))
        dept = (await db.execute(dept_stmt)).scalars().first()
        loc_stmt = select(Location).limit(1)
        loc = (await db.execute(loc_stmt)).scalars().first()
        new_emp = Employee(
            full_name=full_name,
            phone=phone,
            department_id=dept.department_id if dept else None,
            location_id=loc.location_id if loc else None,
            active=is_active
        )
        db.add(new_emp)

    audit = AuditLog(
        username=uname,
        user_role=user.get("role", "FLEET_ADMIN"),
        action=action,
        module="FLEET_MANAGEMENT",
        permission_used="manage_drivers",
        entity_id=phone,
        previous_value=prev_vals,
        new_value={"full_name": full_name, "phone": phone, "role": role, "active": is_active},
        remarks=f"{action} by {uname}",
        ip_address=get_client_ip(request),
        created_at=datetime.datetime.utcnow()
    )
    db.add(audit)
    await db.commit()
    await db.refresh(staff)

    return {
        "status": "success",
        "driver": {
            "staff_id": staff.staff_id,
            "full_name": staff.full_name,
            "phone": staff.phone,
            "role": staff.role,
            "active": staff.active
        }
    }


@router.post("/api/v2/fleet/sales-reps/save")
async def api_save_sales_rep(request: Request, db: AsyncSession = Depends(get_db)):
    """Creates or updates a sales representative in the employee directory."""
    user = get_current_user_from_request(request)
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required.")
    if not (user_has_permission(user, "manage_sales_pipeline") or user_has_permission(user, "manage_trucks")):
        raise HTTPException(status_code=403, detail="Permission denied. Sales or fleet management permission required.")
    
    body = await request.json()
    emp_id = body.get("employee_id")
    full_name = str(body.get("full_name") or body.get("name") or "").strip()
    phone = str(body.get("phone", "")).replace("+", "").strip()
    email = str(body.get("email", "")).strip() or None
    is_active = bool(body.get("active", True))
    company = str(body.get("company", "")).strip() or "LG Plast"
    role = str(body.get("role", "SALES_REP")).strip()

    if not full_name or not phone:
        raise HTTPException(status_code=400, detail="Sales rep name and phone number are required.")

    uname = user.get("name", "Admin")

    # Match company to Location
    loc_search = "%" + ("Kreckle" if "kreckle" in company.lower() else ("Tagoneswa" if "tagoneswa" in company.lower() or "tg" in company.lower() else "LG Plast")) + "%"
    loc_stmt = select(Location).where(Location.location_name.ilike(loc_search))
    loc = (await db.execute(loc_stmt)).scalars().first()
    if not loc:
        loc_stmt_fallback = select(Location).limit(1)
        loc = (await db.execute(loc_stmt_fallback)).scalars().first()

    # Match role to Department
    if role == "SALES_ADMIN":
        dept_stmt = select(Department).where(Department.department_name.ilike("%Sales Admin%"))
        sales_dept = (await db.execute(dept_stmt)).scalars().first()
    else:
        sales_dept = None
    if not sales_dept:
        dept_stmt = select(Department).where(Department.department_name.ilike("%Sales%"))
        sales_dept = (await db.execute(dept_stmt)).scalars().first()

    if emp_id:
        stmt = select(Employee).where(Employee.employee_id == int(emp_id))
        emp = (await db.execute(stmt)).scalars().first()
        if not emp:
            raise HTTPException(status_code=404, detail="Sales representative not found.")
        prev_vals = {"full_name": emp.full_name, "phone": emp.phone, "active": emp.active}
        emp.full_name = full_name
        emp.phone = phone
        emp.email = email
        emp.active = is_active
        if sales_dept:
            emp.department_id = sales_dept.department_id
        if loc:
            emp.location_id = loc.location_id
        action = "UPDATE_SALES_REP"
    else:
        stmt = select(Employee).where(Employee.phone == phone)
        existing = (await db.execute(stmt)).scalars().first()
        if existing:
            emp = existing
            prev_vals = {"full_name": emp.full_name, "phone": emp.phone, "active": emp.active}
            emp.full_name = full_name
            emp.email = email
            emp.active = is_active
            if sales_dept:
                emp.department_id = sales_dept.department_id
            if loc:
                emp.location_id = loc.location_id
            action = "UPDATE_SALES_REP"
        else:
            emp = Employee(
                full_name=full_name,
                phone=phone,
                email=email,
                department_id=sales_dept.department_id if sales_dept else None,
                location_id=loc.location_id if loc else None,
                active=is_active
            )
            db.add(emp)
            prev_vals = None
            action = "ADD_SALES_REP"

    # Update in-memory official directory cache
    OFFICIAL_SALES_REPS_DIRECTORY[phone] = {"name": full_name, "company": company, "role": role}

    perm_used = "manage_sales_pipeline" if user_has_permission(user, "manage_sales_pipeline") else "manage_trucks"
    audit = AuditLog(
        username=uname,
        user_role=user.get("role", "SALES_ADMIN"),
        action=action,
        module="SALES_MANAGEMENT",
        permission_used=perm_used,
        entity_id=phone,
        previous_value=prev_vals,
        new_value={"full_name": full_name, "phone": phone, "email": email, "company": company, "role": role, "active": is_active},
        remarks=f"{action} ({company} - {role}) by {uname}",
        ip_address=get_client_ip(request),
        created_at=datetime.datetime.utcnow()
    )
    db.add(audit)
    await db.commit()
    await db.refresh(emp)

    return {
        "status": "success",
        "sales_rep": {
            "employee_id": emp.employee_id,
            "full_name": emp.full_name,
            "phone": emp.phone,
            "email": emp.email,
            "company": company,
            "role": role,
            "active": emp.active
        }
    }


@router.post("/api/fleet/salespersons/delete")
async def api_delete_sales_rep(request: Request, db: AsyncSession = Depends(get_db)):
    """Removes a sales representative from the directory and dashboard."""
    user = get_current_user_from_request(request)
    if not (user_has_permission(user, "manage_sales_pipeline") or user_has_permission(user, "manage_trucks") or user.get("role") == "MASTER_ADMIN"):
        raise HTTPException(status_code=403, detail="You do not have permission to remove sales representatives.")

    body = await request.json()
    phone = str(body.get("phone", "")).strip().lstrip("+")
    if not phone:
        raise HTTPException(status_code=400, detail="Sales rep phone number is required.")

    removed_name = "Unknown"
    if phone in OFFICIAL_SALES_REPS_DIRECTORY:
        removed_name = OFFICIAL_SALES_REPS_DIRECTORY[phone].get("name", "Sales Rep")
        del OFFICIAL_SALES_REPS_DIRECTORY[phone]

    REMOVED_SALES_REPS.add(phone)

    # Deactivate in Employee table if exists
    stmt = select(Employee).where(Employee.phone == phone)
    emp = (await db.execute(stmt)).scalars().first()
    if emp:
        emp.active = False
        removed_name = emp.full_name

    audit = AuditLog(
        username=user.get("username", "admin"),
        user_role=user.get("role", "SALES_ADMIN"),
        action="REMOVE_SALES_REP",
        module="SALES_MANAGEMENT",
        permission_used="manage_sales_pipeline",
        entity_id=phone,
        previous_value={"name": removed_name, "phone": phone},
        new_value=None,
        remarks=f"Removed sales representative {removed_name} (+{phone}) by {user.get('username')}",
        ip_address=get_client_ip(request),
        created_at=datetime.datetime.utcnow()
    )
    db.add(audit)
    await db.commit()

    return {"status": "success", "phone": phone, "name": removed_name}


# -------------------------------------------------------------
# Data API: Partitioned & Role-Gated Metrics & Records
# -------------------------------------------------------------
@router.get("/api/dashboard/data")
async def get_dashboard_data(request: Request, db: AsyncSession = Depends(get_db)):
    """
    Returns live operational metrics strictly partitioned according to user allowed_domains.
    Sorted in descending order (newest tickets first).
    1. IT Support (only for MASTER_ADMIN and IT_ADMIN)
    2. Building Projects (only for MASTER_ADMIN and PROJECTS_ADMIN)
    3. Workshop & Fleet Logistics (only for MASTER_ADMIN and LOGISTICS_ADMIN)
    """
    user = get_current_user_from_request(request)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized session. Please log in.")

    allowed = user.get("allowed_domains", ["it", "projects", "logistics", "fleet"])
    
    it_payload = None
    projects_payload = None
    logistics_payload = None
    fleet_payload = None

    # 1. Process IT Support Domain (only if permitted - newest first)
    if "it" in allowed:
        admins_stmt = select(SupportAdmin).where(
            SupportAdmin.active == True,
            SupportAdmin.phone.in_(IT_SUPPORT_ADMIN_PHONES)
        )
        support_admins = (await db.execute(admins_stmt)).scalars().all()

        it_stmt = select(Ticket).options(
            selectinload(Ticket.employee).selectinload(Employee.department),
            selectinload(Ticket.employee).selectinload(Employee.location),
            selectinload(Ticket.category),
            selectinload(Ticket.subcategory),
            selectinload(Ticket.issue_type),
            selectinload(Ticket.priority),
            selectinload(Ticket.status)
        ).order_by(Ticket.ticket_id.desc())
        it_tickets = (await db.execute(it_stmt)).scalars().all()

        asg_stmt = select(TicketAssignment).options(selectinload(TicketAssignment.admin))
        asgs = (await db.execute(asg_stmt)).scalars().all()
        asg_map = {f"IT_{a.ticket_id}": a.admin for a in asgs if a.admin}

        it_records = []
        it_stats = {"total": len(it_tickets), "open": 0, "in_progress": 0, "resolved": 0, "closed": 0, "avg_resolution": "--"}
        it_res_times = []
        category_tree_map = {}
        admin_stats_map = {
            sa.admin_id: {
                "admin_id": sa.admin_id, "full_name": sa.full_name, "phone": sa.phone,
                "pending_count": 0, "resolved_count": 0, "total_assigned": 0, "res_list": []
            } for sa in support_admins
        }

        for t in it_tickets:
            s_id = t.status_id
            if s_id == 1: it_stats["open"] += 1
            elif s_id == 2: it_stats["in_progress"] += 1
            elif s_id == 3: it_stats["resolved"] += 1
            elif s_id == 4: it_stats["closed"] += 1

            cat_name = t.category.category_name if t.category else "Hardware & Devices"
            sub_name = t.subcategory.subcategory_name if t.subcategory else "General Facilities"
            issue_name = t.issue_type.issue_name if t.issue_type else "Custom Support Issue"

            if cat_name not in category_tree_map:
                category_tree_map[cat_name] = {"count": 0, "subcategories": {}}
            category_tree_map[cat_name]["count"] += 1

            if sub_name not in category_tree_map[cat_name]["subcategories"]:
                category_tree_map[cat_name]["subcategories"][sub_name] = {"count": 0, "issues": {}}
            category_tree_map[cat_name]["subcategories"][sub_name]["count"] += 1

            if issue_name not in category_tree_map[cat_name]["subcategories"][sub_name]["issues"]:
                category_tree_map[cat_name]["subcategories"][sub_name]["issues"][issue_name] = 0
            category_tree_map[cat_name]["subcategories"][sub_name]["issues"][issue_name] += 1

            res_sec = None
            solving_str = "Active"
            if s_id in (3, 4) and t.created_at:
                end_t = t.closed_at or t.updated_at
                if end_t and end_t > t.created_at:
                    res_sec = (end_t - t.created_at).total_seconds()
                    it_res_times.append(res_sec)
                    solving_str = format_duration(res_sec)
                else:
                    solving_str = "< 1m"

            admin = asg_map.get(f"IT_{t.ticket_id}")
            if admin and admin.admin_id in admin_stats_map:
                ast = admin_stats_map[admin.admin_id]
                ast["total_assigned"] += 1
                if s_id in (1, 2): ast["pending_count"] += 1
                elif s_id in (3, 4):
                    ast["resolved_count"] += 1
                    if res_sec is not None: ast["res_list"].append(res_sec)

            emp = t.employee
            it_records.append({
                "ticket_id": t.ticket_id,
                "ticket_number": t.ticket_number,
                "employee_name": emp.full_name if emp else "Staff",
                "employee_phone": emp.phone if emp else "",
                "department": emp.department.department_name if emp and emp.department else "General",
                "location": emp.location.location_name if emp and emp.location else "Headquarters",
                "category": cat_name,
                "subcategory": sub_name,
                "issue": issue_name,
                "priority": t.priority.priority_name if t.priority else "Medium",
                "status": t.status.status_name if t.status else "Open",
                "description": t.description,
                "assigned_admin": admin.full_name if admin else "Unassigned",
                "created_at": t.created_at.strftime("%Y-%m-%d %H:%M") if t.created_at else "",
                "resolution_time": solving_str
            })

        if it_res_times:
            it_stats["avg_resolution"] = format_duration(sum(it_res_times) / len(it_res_times))

        it_admin_performance = []
        for a_id, ast in admin_stats_map.items():
            avg_s = sum(ast["res_list"]) / len(ast["res_list"]) if ast["res_list"] else 0
            total_a = ast["total_assigned"]
            res_count = ast["resolved_count"]
            sla_pct = int((res_count / total_a) * 100) if total_a > 0 else 100
            it_admin_performance.append({
                "name": ast["full_name"], "phone": ast["phone"],
                "pending": ast["pending_count"], "resolved": res_count,
                "total": total_a, "sla_pct": sla_pct,
                "avg_time": format_duration(avg_s) if avg_s > 0 else "--"
            })

        category_tree_list = []
        for c_name, c_data in category_tree_map.items():
            sub_list = []
            for s_name, s_data in c_data["subcategories"].items():
                iss_list = [{"issue_name": ik, "count": iv} for ik, iv in s_data["issues"].items()]
                sub_list.append({
                    "subcategory_name": s_name,
                    "count": s_data["count"],
                    "issues": iss_list
                })
            category_tree_list.append({
                "category_name": c_name,
                "count": c_data["count"],
                "subcategories": sub_list
            })

        it_payload = {
            "stats": it_stats,
            "records": it_records,
            "admins": it_admin_performance,
            "category_tree": category_tree_list
        }

    # 2. Process Building Projects Domain (only if permitted - newest first)
    if "projects" in allowed:
        maint_stmt = select(MaintenanceTicket).options(
            selectinload(MaintenanceTicket.employee).selectinload(Employee.department),
            selectinload(MaintenanceTicket.employee).selectinload(Employee.location),
            selectinload(MaintenanceTicket.category),
            selectinload(MaintenanceTicket.subcategory),
            selectinload(MaintenanceTicket.issue_type),
            selectinload(MaintenanceTicket.priority),
            selectinload(MaintenanceTicket.status)
        ).order_by(MaintenanceTicket.ticket_id.desc())
        maint_tickets = (await db.execute(maint_stmt)).scalars().all()

        m_asg_stmt = select(MaintenanceTicketAssignment).options(selectinload(MaintenanceTicketAssignment.admin))
        m_asgs = (await db.execute(m_asg_stmt)).scalars().all()
        m_asg_map = {f"MAINT_{ma.ticket_id}": ma.admin for ma in m_asgs if ma.admin}

        maint_records = []
        maint_stats = {"total": len(maint_tickets), "open": 0, "in_progress": 0, "resolved": 0, "closed": 0, "locations_count": 0}
        loc_set = set()

        for t in maint_tickets:
            s_id = t.status_id
            if s_id == 1: maint_stats["open"] += 1
            elif s_id == 2: maint_stats["in_progress"] += 1
            elif s_id == 3: maint_stats["resolved"] += 1
            elif s_id == 4: maint_stats["closed"] += 1

            admin = m_asg_map.get(f"MAINT_{t.ticket_id}")
            emp = t.employee
            loc_name = emp.location.location_name if emp and emp.location else "HQ"
            loc_set.add(loc_name)

            maint_records.append({
                "ticket_id": t.ticket_id,
                "ticket_number": t.ticket_number,
                "employee_name": emp.full_name if emp else "Staff",
                "employee_phone": emp.phone if emp else "",
                "location": loc_name,
                "category": t.category.category_name if t.category else "Building Maintenance",
                "subcategory": t.subcategory.subcategory_name if t.subcategory else "General Repairs",
                "priority": t.priority.priority_name if t.priority else "Medium",
                "status": t.status.status_name if t.status else "Open",
                "description": t.description,
                "assigned_admin": admin.full_name if admin else "Omar / Stanclea",
                "created_at": t.created_at.strftime("%Y-%m-%d %H:%M") if t.created_at else ""
            })
        maint_stats["locations_count"] = len(loc_set)
        projects_payload = {
            "stats": maint_stats,
            "records": maint_records
        }

    # 3. Process Workshop & Fleet Logistics Domain (only if permitted - newest first)
    if "logistics" in allowed:
        ws_ticket_stmt = select(WorkshopTicket).options(
            selectinload(WorkshopTicket.truck),
            selectinload(WorkshopTicket.logged_by),
            selectinload(WorkshopTicket.assigned_mechanic)
        ).order_by(WorkshopTicket.ticket_id.desc())
        ws_tickets = (await db.execute(ws_ticket_stmt)).scalars().all()

        ws_trucks_stmt = select(WorkshopTruck).where(WorkshopTruck.active == True)
        ws_trucks = (await db.execute(ws_trucks_stmt)).scalars().all()

        ws_parts_stmt = select(WorkshopPartsRequest).order_by(WorkshopPartsRequest.request_id.desc())
        ws_parts = (await db.execute(ws_parts_stmt)).scalars().all()
        parts_map = {}
        for p in ws_parts:
            if p.ticket_id not in parts_map:
                parts_map[p.ticket_id] = []
            parts_map[p.ticket_id].append(p)

        ws_records = []
        ws_stats = {
            "fleet_total": len(ws_trucks),
            "in_workshop": 0,
            "awaiting_parts": 0,
            "awaiting_qc": 0,
            "under_review": 0,
            "closed_fleet": 0
        }

        for t in ws_tickets:
            st = t.status
            if st == "UNDER_REVIEW": ws_stats["under_review"] += 1
            elif st in ("WITH_MECHANIC", "REPAIR_IN_PROGRESS", "REWORK_REQUIRED"): ws_stats["in_workshop"] += 1
            elif st == "AWAITING_PARTS": ws_stats["awaiting_parts"] += 1
            elif st == "AWAITING_TEST": ws_stats["awaiting_qc"] += 1
            elif st == "CLOSED": ws_stats["closed_fleet"] += 1

            parts_list = parts_map.get(t.ticket_id, [])
            parts_summary = "None Needed"
            if parts_list:
                p_items = [f"{p.part_name} ({p.status})" for p in parts_list]
                parts_summary = ", ".join(p_items)

            truck = t.truck
            truck_label = f"#{truck.truck_number} ({truck.plate_number})" if truck else "Fleet Vehicle"
            truck_model = truck.model_make if truck else "Truck"

            ws_records.append({
                "ticket_id": t.ticket_id,
                "ticket_number": t.ticket_number,
                "truck_number": truck.truck_number if truck else "",
                "plate_number": truck.plate_number if truck else "",
                "truck_label": truck_label,
                "truck_model": truck_model,
                "category": f"{t.category_name} / {t.subcategory_name}" if t.category_name else "General Defect",
                "description": t.description,
                "status": t.status,
                "logged_by": t.logged_by.full_name if t.logged_by else "Driver",
                "assigned_mechanic": t.assigned_mechanic.full_name if t.assigned_mechanic else "Sajid (Mechanic)",
                "eta": t.expected_completion_time or "Pending Assessment",
                "parts_status": parts_summary,
                "costing": t.cost_total or "--",
                "qc_result": "Passed" if t.qc_passed else ("Failed / Rework" if t.qc_passed is False else "Pending QC"),
                "image_id": t.image_id,
                "created_at": t.created_at.strftime("%Y-%m-%d %H:%M") if t.created_at else ""
            })

        # --- Fleet Availability: distinct-truck mapping from open WorkshopTickets ---
        # Priority order: higher value = operationally worse state.
        # When a truck has multiple open tickets, we report it under its worst current state.
        _STATUS_PRIORITY = {
            "OPEN": 1,
            "UNDER_REVIEW": 2,
            "AWAITING_TEST": 3,
            "AWAITING_PARTS": 4,
            "WITH_MECHANIC": 5,
            "REPAIR_IN_PROGRESS": 6,
            "REWORK_REQUIRED": 7,
        }
        busy_truck_ids: dict = {}  # truck_id -> worst open ticket status
        for t in ws_tickets:
            if t.status == "CLOSED" or t.truck_id is None:
                continue
            existing = busy_truck_ids.get(t.truck_id)
            if existing is None:
                busy_truck_ids[t.truck_id] = t.status
            else:
                if _STATUS_PRIORITY.get(t.status, 0) > _STATUS_PRIORITY.get(existing, 0):
                    busy_truck_ids[t.truck_id] = t.status

        logistics_payload = {
            "stats": ws_stats,
            "records": ws_records,
            "fleet_count": len(ws_trucks),
            "busy_truck_ids": busy_truck_ids,  # truck_id -> worst open ticket status
        }

    # 4. Process Fleet Approval Domain (only if permitted - newest first)
    if "fleet" in allowed:
        fleet_stmt = select(FleetTripApproval).order_by(FleetTripApproval.created_at.desc())
        fleet_approvals = (await db.execute(fleet_stmt)).scalars().all()

        ledger_stmt = select(FleetPendingLedger).order_by(FleetPendingLedger.created_at.desc())
        ledger_entries = (await db.execute(ledger_stmt)).scalars().all()

        # A. Aggregate Salesperson Pending Balances & Performance (Only verified official sales reps)
        salesperson_map = {}
        for entry in ledger_entries:
            p = entry.salesperson_phone
            if not p or p in SALES_ADMIN_PHONES or p in REMOVED_SALES_REPS or p not in OFFICIAL_SALES_REPS_DIRECTORY:
                continue
            if p not in salesperson_map:
                official = OFFICIAL_SALES_REPS_DIRECTORY.get(p, {})
                salesperson_map[p] = {
                    "phone": p,
                    "name": official.get("name", entry.salesperson_name or "Sales Rep"),
                    "company": official.get("company", "Commercial Sales"),
                    "total_shortfalls": 0.0,
                    "total_recovered": 0.0,
                    "net_balance": 0.0,
                    "entries_count": 0,
                    "trips": set(),
                    "recent_date": entry.created_at.strftime("%Y-%m-%d %H:%M") if entry.created_at else ""
                }
            s_obj = salesperson_map[p]
            s_obj["entries_count"] += 1
            if entry.trip_id:
                s_obj["trips"].add(entry.trip_id)
            if entry.amount > 0:
                s_obj["total_shortfalls"] += entry.amount
            else:
                s_obj["total_recovered"] += abs(entry.amount)
            s_obj["net_balance"] += entry.amount

        # Also register any official salesperson who has trip approvals
        for fa in fleet_approvals:
            p = fa.salesperson_phone
            if not p or p in SALES_ADMIN_PHONES or p in REMOVED_SALES_REPS or p not in OFFICIAL_SALES_REPS_DIRECTORY:
                continue
            if p not in salesperson_map:
                official = OFFICIAL_SALES_REPS_DIRECTORY.get(p, {})
                salesperson_map[p] = {
                    "phone": p,
                    "name": official.get("name", fa.salesperson_name or "Sales Rep"),
                    "company": official.get("company", "Commercial Sales"),
                    "total_shortfalls": 0.0,
                    "total_recovered": 0.0,
                    "net_balance": 0.0,
                    "entries_count": 0,
                    "trips": {fa.trip_id} if fa.trip_id else set(),
                    "recent_date": fa.created_at.strftime("%Y-%m-%d %H:%M") if fa.created_at else ""
                }
            elif p and fa.trip_id:
                salesperson_map[p]["trips"].add(fa.trip_id)

        # Guarantee all registered commercial sales representatives from Employee directory are included
        sales_dept_stmt = (
            select(Employee)
            .options(selectinload(Employee.location), selectinload(Employee.department))
            .where(
                (Employee.phone.in_(list(OFFICIAL_SALES_REPS_DIRECTORY.keys()))) &
                (~Employee.phone.in_(list(SALES_ADMIN_PHONES)))
            )
        )
        registered_sales_employees = (await db.execute(sales_dept_stmt)).scalars().all()
        for emp in registered_sales_employees:
            p = emp.phone
            if p in REMOVED_SALES_REPS or p in SALES_ADMIN_PHONES:
                continue
            official = OFFICIAL_SALES_REPS_DIRECTORY.get(p, {})
            comp = official.get("company", "Commercial Sales")
            official_name = official.get("name", emp.full_name)

            if p not in salesperson_map:
                salesperson_map[p] = {
                    "phone": p,
                    "name": official_name,
                    "company": comp,
                    "total_shortfalls": 0.0,
                    "total_recovered": 0.0,
                    "net_balance": 0.0,
                    "entries_count": 0,
                    "trips": set(),
                    "recent_date": "Active Commercial Roster",
                    "employee_id": emp.employee_id,
                    "email": emp.email or "",
                    "active": emp.active,
                    "is_official": True
                }
            else:
                salesperson_map[p]["company"] = comp
                salesperson_map[p]["employee_id"] = emp.employee_id
                salesperson_map[p]["email"] = emp.email or ""
                salesperson_map[p]["active"] = emp.active
                salesperson_map[p]["is_official"] = True
                salesperson_map[p]["name"] = official_name

        # Ensure all official sales reps in OFFICIAL_SALES_REPS_DIRECTORY are present
        for p, rep_info in OFFICIAL_SALES_REPS_DIRECTORY.items():
            if p in SALES_ADMIN_PHONES or p in REMOVED_SALES_REPS:
                continue
            if p not in salesperson_map:
                salesperson_map[p] = {
                    "phone": p,
                    "name": rep_info.get("name", "Sales Rep"),
                    "company": rep_info.get("company", "Commercial Sales"),
                    "total_shortfalls": 0.0,
                    "total_recovered": 0.0,
                    "net_balance": 0.0,
                    "entries_count": 0,
                    "trips": set(),
                    "recent_date": "Active Commercial Roster",
                    "employee_id": None,
                    "email": "",
                    "active": True,
                    "is_official": True
                }

        salespersons_list = []
        for p, s in salesperson_map.items():
            net = round(s["net_balance"], 2)
            risk = "HEALTHY"
            if net > 250:
                risk = "HIGH_ALERT"
            elif net > 0:
                risk = "ACTIVE_PENDING"

            salespersons_list.append({
                "phone": p,
                "name": s["name"],
                "company": s.get("company", "Commercial Sales"),
                "employee_id": s.get("employee_id"),
                "email": s.get("email", ""),
                "active": s.get("active", True),
                "is_official": s.get("is_official", p in OFFICIAL_SALES_REPS_DIRECTORY),
                "total_shortfalls": round(s["total_shortfalls"], 2),
                "total_recovered": round(s["total_recovered"], 2),
                "net_balance": net,
                "trips_count": len(s["trips"]),
                "entries_count": s["entries_count"],
                "recent_date": s["recent_date"],
                "risk_level": risk
            })

        salespersons_list.sort(key=lambda x: (
            -x["net_balance"],
            0 if x["is_official"] else 1,
            x["company"],
            x["name"]
        ))

        # B. Trip Approvals Records & Anti-Fraud Audit
        approval_records = []
        fleet_stats = {
            "total_trips": len(fleet_approvals),
            "approved_trips": 0,
            "shortfall_trips": 0,
            "total_sales_value": 0.0,
            "total_transport_charges": 0.0,
            "total_charged_customer": 0.0,
            "total_pending_recorded": 0.0,
            "total_outstanding_backlog": round(sum(s["net_balance"] for s in salespersons_list if s["net_balance"] > 0), 2),
            "total_recovered": round(sum(s["total_recovered"] for s in salespersons_list), 2),
            "audit_flags_count": 0
        }

        cities_set = set()
        for fa in fleet_approvals:
            if fa.destination_city:
                cities_set.add(fa.destination_city)
            is_app = fa.status in ("APPROVED", "DISPATCHED")
            if is_app:
                fleet_stats["approved_trips"] += 1
            if fa.has_shortfall:
                fleet_stats["shortfall_trips"] += 1

            s_val = fa.trip_sales_value or 0.0
            t_charge = fa.transport_charge or 0.0
            c_charged = getattr(fa, "amount_charged_to_customer", 0.0) or 0.0
            p_rec = getattr(fa, "pending_balance_recorded", 0.0) or 0.0

            fleet_stats["total_sales_value"] += s_val
            fleet_stats["total_transport_charges"] += t_charge
            fleet_stats["total_charged_customer"] += c_charged
            fleet_stats["total_pending_recorded"] += p_rec

            # Anti-Fraud Audit Check
            audit_flags = []
            if fa.has_shortfall and t_charge > 0:
                expected_total = round(t_charge, 2)
                declared_total = round(c_charged + p_rec, 2)
                if abs(expected_total - declared_total) > 0.05:
                    audit_flags.append(f"Math Mismatch: Required ${expected_total:.2f} vs Declared ${declared_total:.2f}")
                    fleet_stats["audit_flags_count"] += 1

            is_erp_grounded = bool(s_val > 0)
            if not is_erp_grounded:
                audit_flags.append("ERP Data Missing: Trip not validated in live Favlogix ERP")
                fleet_stats["audit_flags_count"] += 1

            rep_info = OFFICIAL_SALES_REPS_DIRECTORY.get(fa.salesperson_phone or "")
            co_name = getattr(fa, "company_name", None) or (rep_info.get("company") if rep_info else "Tagoneswa Hardware")
            approval_records.append({
                "id": fa.id,
                "trip_id": fa.trip_id,
                "company_name": co_name,
                "company": co_name,
                "salesperson_name": fa.salesperson_name or "Sales Rep",
                "salesperson_phone": fa.salesperson_phone,
                "destination_city": fa.destination_city,
                "route": fa.route or "--",
                "trip_sales_value": 0.0,
                "required_minimum": round(fa.required_minimum or 0.0, 2),
                "shortfall": round(fa.shortfall or 0.0, 2),
                "transport_charge": round(t_charge, 2),
                "amount_charged_to_customer": round(c_charged, 2),
                "pending_balance_recorded": round(p_rec, 2),
                "dispatch_option": getattr(fa, "dispatch_option", "STANDARD"),
                "has_shortfall": bool(fa.has_shortfall),
                "status": fa.status,
                "audit_flags": audit_flags,
                "is_clean": len(audit_flags) == 0,
                "created_at": fa.created_at.strftime("%Y-%m-%d %H:%M") if fa.created_at else "",
                "date_only": fa.created_at.strftime("%Y-%m-%d") if fa.created_at else ""
            })

        fleet_stats["total_sales_value"] = 0.0
        fleet_stats["total_transport_charges"] = round(fleet_stats["total_transport_charges"], 2)
        fleet_stats["total_charged_customer"] = round(fleet_stats["total_charged_customer"], 2)
        fleet_stats["total_pending_recorded"] = round(fleet_stats["total_pending_recorded"], 2)

        # C. Detailed Ledger Entries Audit
        ledger_records = []
        for le in ledger_entries:
            rep_info = OFFICIAL_SALES_REPS_DIRECTORY.get(le.salesperson_phone or "")
            co_name = getattr(le, "company_name", None) or (rep_info.get("company") if rep_info else "Tagoneswa Hardware")
            ledger_records.append({
                "id": le.id,
                "salesperson_name": le.salesperson_name or "Sales Rep",
                "salesperson_phone": le.salesperson_phone,
                "company_name": co_name,
                "company": co_name,
                "trip_id": le.trip_id or "--",
                "entry_type": le.entry_type,
                "amount": round(le.amount, 2),
                "is_recovery": le.amount < 0,
                "notes": le.notes or "",
                "created_at": le.created_at.strftime("%Y-%m-%d %H:%M") if le.created_at else "",
                "date_only": le.created_at.strftime("%Y-%m-%d") if le.created_at else ""
            })

        # D. All 7-stage Trips
        trips_stmt = select(FleetTripRequest).order_by(FleetTripRequest.created_at.desc())
        raw_trips = (await db.execute(trips_stmt)).scalars().all()
        trips_list = []
        for tr in raw_trips:
            rep_info = OFFICIAL_SALES_REPS_DIRECTORY.get(tr.salesperson_phone or "")
            co_name = tr.company_name or (rep_info.get("company") if rep_info else "Tagoneswa Hardware")
            trips_list.append({
                "id": tr.id,
                "trip_id": tr.trip_id,
                "company_name": co_name,
                "company": co_name,
                "trip_sales_value": 0.0,
                "salesperson_name": tr.salesperson_name or "Sales Rep",
                "salesperson_phone": tr.salesperson_phone,
                "destination_city": tr.destination_city,
                "route": tr.route or tr.destination_city,
                "truck_plate": tr.truck_plate or "Pending Allocation",
                "driver_name": tr.driver_name or "Pending Allocation",
                "driver_phone": tr.driver_phone or "",
                "total_allowance": round(tr.total_allowance or 0.0, 2),
                "transport_charge": round(tr.transport_charge or 0.0, 2),
                "status": tr.status,
                "distance_km": tr.distance_km or 0.0,
                "start_odometer": tr.start_odometer or 0.0,
                "end_odometer": tr.end_odometer or 0.0,
                "discrepancy_amount": round(tr.discrepancy_amount or 0.0, 2),
                "discrepancy_reason": tr.discrepancy_reason or "",
                "created_at": tr.created_at.strftime("%Y-%m-%d %H:%M") if tr.created_at else "",
                "departed_at": tr.departed_at.strftime("%Y-%m-%d %H:%M") if tr.departed_at else "",
                "returned_at": tr.returned_at.strftime("%Y-%m-%d %H:%M") if tr.returned_at else "",
                "closed_at": tr.closed_at.strftime("%Y-%m-%d %H:%M") if tr.closed_at else ""
            })

        # E. Payment Settlements
        payments_stmt = select(SalesRepPayment).order_by(SalesRepPayment.created_at.desc()).limit(100)
        raw_payments = (await db.execute(payments_stmt)).scalars().all()
        payments_list = []
        for pm in raw_payments:
            rep_info = OFFICIAL_SALES_REPS_DIRECTORY.get(pm.salesperson_phone or "")
            co_name = getattr(pm, "company_name", None) or (rep_info.get("company") if rep_info else "Tagoneswa Hardware")
            payments_list.append({
                "id": pm.id,
                "salesperson_name": pm.salesperson_name or "Sales Rep",
                "salesperson_phone": pm.salesperson_phone,
                "company_name": co_name,
                "company": co_name,
                "cleared_amount": round(pm.cleared_amount, 2),
                "payment_method": pm.payment_method,
                "reference_number": pm.reference_number or "--",
                "previous_balance": round(pm.previous_balance, 2),
                "remaining_balance": round(pm.remaining_balance, 2),
                "recorded_by": pm.recorded_by or "Accounts",
                "remarks": pm.remarks or "",
                "payment_date": pm.payment_date.strftime("%Y-%m-%d %H:%M") if pm.payment_date else ""
            })

        # F. Workshop Trucks and Drivers
        ws_trucks_all = (await db.execute(select(WorkshopTruck))).scalars().all()
        trucks_list = [{
            "truck_id": wt.truck_id,
            "truck_number": wt.truck_number,
            "plate_number": wt.plate_number,
            "model_make": wt.model_make,
            "body_type": wt.body_type,
            "home_depot": wt.home_depot,
            "active": wt.active
        } for wt in ws_trucks_all]

        ws_drivers_all = (await db.execute(select(WorkshopStaff).where(WorkshopStaff.role.ilike("%DRIVER%")))).scalars().all()
        drivers_list = [{
            "staff_id": wd.staff_id,
            "full_name": wd.full_name,
            "phone": wd.phone,
            "role": wd.role,
            "active": wd.active
        } for wd in ws_drivers_all]

        # G. Registered Sales Representatives
        sales_reps_stmt = (
            select(Employee)
            .where(Employee.phone.in_({sp["phone"] for sp in salespersons_list}))
        )
        raw_reps = (await db.execute(sales_reps_stmt)).scalars().all()
        reps_map = {}
        for r in raw_reps:
            reps_map[r.phone] = {
                "employee_id": r.employee_id,
                "full_name": r.full_name,
                "phone": r.phone,
                "email": r.email or "",
                "active": r.active
            }
        for sp in salespersons_list:
            p = sp["phone"]
            rep_info = reps_map.get(p)
            if rep_info:
                sp["employee_id"] = rep_info.get("employee_id")
                sp["email"] = rep_info.get("email") or ""
            else:
                sp["employee_id"] = None
                sp["email"] = ""
                reps_map[p] = {
                    "employee_id": None,
                    "full_name": sp["name"],
                    "phone": p,
                    "email": "",
                    "active": True
                }
        sales_reps_list = list(reps_map.values())

        # H. Enterprise Operations Overview: Role-Gated KPIs, Alerts & Recent Activity
        can_view_schedules = user_has_permission(user, "view_customer_schedules") or user_has_permission(user, "manage_sales_pipeline")
        can_view_balances = user_has_permission(user, "view_sales_rep_balances")
        can_approve_trips = user_has_permission(user, "approve_trips")
        can_view_analytics = (user.get("role") == "MASTER_ADMIN")
        can_clear_debt = user_has_permission(user, "clear_sales_rep_debt")
        can_view_workshop = user_has_permission(user, "view_workshop_workspace")
        is_observer = (user.get("role") == "EXECUTIVE_OBSERVER")

        # 1. Active / Ongoing Trips
        active_trips_count = sum(1 for tr in raw_trips if (tr.status or "").upper() in ("APPROVED", "DISPATCH_APPROVED", "VOUCHER_ISSUED", "LOADED", "IN_TRANSIT", "OFFLOADED", "ACTIVE", "TRANSFERRED"))
        in_transit_trips = sum(1 for tr in raw_trips if "TRANSIT" in (tr.status or "").upper())

        # 2. Pending Approvals
        pending_approvals_count = sum(1 for fa in fleet_approvals if fa.status == "SHORTFALL_RECORDED")
        quoted_trips_count = sum(1 for tr in raw_trips if (tr.status or "").upper() in ("QUOTED", "CREATED", "PENDING_ASSIGNMENT"))
        total_pending_approvals = pending_approvals_count + quoted_trips_count

        # 3. Trucks & Drivers — fleet availability from WorkshopTicket open tickets (distinct trucks)
        trucks_total = len(trucks_list)
        drivers_total = len(drivers_list)
        drivers_active = sum(1 for d in drivers_list if d["active"])

        if logistics_payload:
            # Use distinct truck_id mapping built in logistics section (Section 3).
            busy = logistics_payload["busy_truck_ids"]  # truck_id -> worst open status
            _in_workshop_statuses = {"WITH_MECHANIC", "REPAIR_IN_PROGRESS", "REWORK_REQUIRED"}
            trucks_in_workshop = sum(1 for s in busy.values() if s in _in_workshop_statuses)
            trucks_awaiting_parts = sum(1 for s in busy.values() if s == "AWAITING_PARTS")
            trucks_awaiting_qc = sum(1 for s in busy.values() if s == "AWAITING_TEST")
            trucks_under_review = sum(1 for s in busy.values() if s == "UNDER_REVIEW")
            trucks_busy_total = len(busy)  # distinct trucks with ANY open ticket
            trucks_available = trucks_total - trucks_busy_total
            if trucks_available < 0:
                trucks_available = 0  # guard: shouldn't happen but be safe
        else:
            # No logistics access — fall back to roster-only (no workshop data available)
            trucks_available = sum(1 for t in trucks_list if t["active"])
            trucks_in_workshop = 0
            trucks_awaiting_parts = 0
            trucks_awaiting_qc = 0
            trucks_under_review = 0

        # Legacy aliases used in existing alert text and KPI payload
        trucks_active = trucks_available  # "available" trucks (renamed for clarity in payload below)
        trucks_maintenance = trucks_total - trucks_available  # trucks NOT available

        # 4. Sales Pipeline / Customer Schedules Summary (Role Gated)
        sales_pipeline_summary = None
        if can_view_schedules:
            sched_stmt = select(FleetCustomerSchedule).order_by(FleetCustomerSchedule.created_at.desc())
            raw_schedules = (await db.execute(sched_stmt)).scalars().all()
            sched_total = len(raw_schedules)
            sched_pending = sum(1 for s in raw_schedules if s.status == "PENDING")
            sched_matched = sum(1 for s in raw_schedules if s.status == "MATCHED")
            sched_variance = sum(1 for s in raw_schedules if s.status == "VARIANCE")
            sched_expected_rev = round(sum(s.expected_charge or 0.0 for s in raw_schedules), 2)
            sched_collected_rev = round(sum(s.collected_charge or 0.0 for s in raw_schedules), 2)
            sales_pipeline_summary = {
                "total_schedules": sched_total,
                "pending_collection": sched_pending,
                "matched_collection": sched_matched,
                "variance_collection": sched_variance,
                "expected_revenue": sched_expected_rev,
                "collected_revenue": sched_collected_rev
            }

        # 5. Sales Rep Balance Summary (Role Gated)
        sales_rep_balance_summary = None
        reps_in_debt = sum(1 for sp in salespersons_list if sp["net_balance"] > 0)
        reps_high_alert = sum(1 for sp in salespersons_list if sp["risk_level"] == "HIGH_ALERT")
        if can_view_balances:
            sales_rep_balance_summary = {
                "total_backlog": fleet_stats["total_outstanding_backlog"],
                "reps_in_debt": reps_in_debt,
                "reps_high_alert": reps_high_alert,
                "total_recovered": fleet_stats["total_recovered"]
            }

        # 6. Prioritized Operational Exceptions & Alerts
        operations_alerts = []
        if total_pending_approvals > 0:
            operations_alerts.append({
                "id": "alert-pending-approvals",
                "severity": "urgent" if pending_approvals_count > 0 else "warning",
                "category": "APPROVALS",
                "title": f"{total_pending_approvals} Trip(s) Awaiting Management Sign-off",
                "description": f"{pending_approvals_count} commercial shortfall exception(s) requiring decision; {quoted_trips_count} quote(s) awaiting dispatch approval.",
                "action_label": "Review Approvals",
                "target_subview": "approvals",
                "can_action": can_approve_trips and not is_observer
            })

        needing_voucher = sum(1 for tr in raw_trips if (tr.status or "").upper() == "APPROVED")
        needing_loading = sum(1 for tr in raw_trips if "VOUCHER" in (tr.status or "").upper())
        discrepancy_trips = sum(1 for tr in raw_trips if (tr.discrepancy_amount or 0.0) > 0)
        if needing_voucher > 0 or needing_loading > 0 or discrepancy_trips > 0:
            operations_alerts.append({
                "id": "alert-dispatch-action",
                "severity": "urgent" if discrepancy_trips > 0 else "warning",
                "category": "DISPATCH",
                "title": f"Dispatch Actions Required ({needing_voucher + needing_loading} in queue)",
                "description": f"{needing_voucher} trip(s) approved awaiting fuel/allowance voucher; {needing_loading} awaiting loading & start odometer.{f' - {discrepancy_trips} odometer discrepancy flagged!' if discrepancy_trips else ''}",
                "action_label": "Open Trips Pipeline",
                "target_subview": "trips",
                "can_action": True
            })

        if can_view_balances and reps_in_debt > 0:
            operations_alerts.append({
                "id": "alert-rep-debt",
                "severity": "urgent" if reps_high_alert > 0 else "warning",
                "category": "FINANCE",
                "title": f"${fleet_stats['total_outstanding_backlog']:,.2f} Outstanding Sales Rep Debt",
                "description": f"{reps_in_debt} sales representative(s) currently carry deficit balances. {reps_high_alert} rep(s) flagged on HIGH DEBT ALERT (> $250.00).",
                "action_label": "Clear Debt Settlement" if can_clear_debt and not is_observer else "View Debt Ledger",
                "target_subview": "salespersons",
                "modal_target": "clearPaymentModal" if can_clear_debt and not is_observer else None,
                "can_action": (can_clear_debt or can_view_balances) and not is_observer
            })

        ws_in_floor = trucks_in_workshop  # from distinct-truck ticket analysis
        ws_awaiting_parts = trucks_awaiting_parts
        if (can_view_workshop or user_has_permission(user, "manage_trucks")) and (trucks_maintenance > 0 or ws_in_floor > 0 or ws_awaiting_parts > 0):
            operations_alerts.append({
                "id": "alert-fleet-maintenance",
                "severity": "warning" if ws_awaiting_parts > 0 else "info",
                "category": "FLEET",
                "title": f"{trucks_maintenance} Commercial Truck(s) Not Field-Ready",
                "description": f"{trucks_available} of {trucks_total} commercial vehicles available. {ws_in_floor} on workshop floor, {ws_awaiting_parts} awaiting parts, {trucks_awaiting_qc} awaiting QC sign-off.",
                "action_label": "Inspect Fleet Vehicles",
                "target_subview": "trucks",
                "can_action": True
            })

        if can_view_schedules and sales_pipeline_summary and sales_pipeline_summary.get("variance_collection", 0) > 0:
            operations_alerts.append({
                "id": "alert-customer-variance",
                "severity": "warning",
                "category": "SALES",
                "title": f"{sales_pipeline_summary['variance_collection']} Customer Payment Variance(s) Flagged",
                "description": f"Customer delivery schedules report collected payment differing from expected invoiced manifest amounts.",
                "action_label": "View Trips Pipeline",
                "target_subview": "trips",
                "can_action": True
            })

        # 7. Recent Operational Activity Feed (Audit logs + Real operational events)
        recent_activity_list = []
        audit_stmt = select(AuditLog).order_by(AuditLog.created_at.desc()).limit(100)
        raw_audits = (await db.execute(audit_stmt)).scalars().all()

        audit_records = []
        for al in raw_audits:
            audit_records.append({
                "id": al.id,
                "timestamp": al.created_at.strftime("%Y-%m-%d %H:%M:%S") if al.created_at else "",
                "date_only": al.created_at.strftime("%Y-%m-%d") if al.created_at else "",
                "username": al.username or "System",
                "user_role": al.user_role or "--",
                "action": al.action,
                "module": al.module,
                "permission_used": al.permission_used or "--",
                "entity_id": al.entity_id or "--",
                "previous_value": al.previous_value,
                "new_value": al.new_value,
                "remarks": al.remarks or "",
            })

        for idx, al in enumerate(raw_audits[:10]):
            cat = "CONFIG"
            badge = "bg-blue-500/10 text-blue-700 dark:text-blue-300 border-blue-200 dark:border-blue-500/30"
            if "PAYMENT" in al.action or "CLEAR" in al.action:
                cat = "FINANCE"
                badge = "bg-emerald-500/10 text-emerald-700 dark:text-emerald-300 border-emerald-200 dark:border-emerald-500/30"
            elif "FUEL" in al.action or "ROUTE" in al.action or "RATE" in al.action:
                cat = "PRICING"
                badge = "bg-purple-500/10 text-purple-700 dark:text-purple-300 border-purple-200 dark:border-purple-500/30"
            elif "USER" in al.action or "PERMISSION" in al.action:
                cat = "SECURITY"
                badge = "bg-indigo-500/10 text-indigo-700 dark:text-indigo-300 border-indigo-200 dark:border-indigo-500/30"

            recent_activity_list.append({
                "id": f"aud-{al.id}",
                "timestamp": al.created_at.strftime("%Y-%m-%d %H:%M") if al.created_at else "",
                "category": cat,
                "title": al.action.replace("_", " ").title(),
                "description": al.remarks or f"{al.action} performed on {al.module} ({al.entity_id or ''})",
                "actor": al.username or "Admin",
                "badge_class": badge
            })

        # If audit logs are fewer than 6, blend with real recent payments & trip approvals
        if len(recent_activity_list) < 6:
            if can_view_balances:
                for pm in payments_list[:4]:
                    recent_activity_list.append({
                        "id": f"pay-{pm['id']}",
                        "timestamp": pm["payment_date"],
                        "category": "FINANCE",
                        "title": f"Cleared ${pm['cleared_amount']:,.2f} Debt",
                        "description": f"Settlement recorded for {pm['salesperson_name']} via {pm['payment_method']}",
                        "actor": pm["recorded_by"],
                        "badge_class": "bg-emerald-500/10 text-emerald-700 dark:text-emerald-300 border-emerald-200 dark:border-emerald-500/30"
                    })
            for fa in approval_records[:4]:
                sales_desc = ""
                recent_activity_list.append({
                    "id": f"app-{fa['id']}",
                    "timestamp": fa["created_at"],
                    "category": "APPROVALS",
                    "title": f"Trip {fa['trip_id']} Approved",
                    "description": f"{fa['salesperson_name']} to {fa['destination_city']}{sales_desc}",
                    "actor": "Fleet Operations",
                    "badge_class": "bg-blue-500/10 text-blue-700 dark:text-blue-300 border-blue-200 dark:border-blue-500/30"
                })

        recent_activity_list.sort(key=lambda x: x["timestamp"], reverse=True)
        recent_activity_list = recent_activity_list[:10]

        # 8. Real Historical Operations & Financial Analytics
        tot_sales = sum(tr.trip_sales_value or 0.0 for tr in raw_trips)
        tot_trans = sum(tr.transport_charge or 0.0 for tr in raw_trips)
        tot_allow = sum(tr.total_allowance or 0.0 for tr in raw_trips)
        tot_meals = sum(tr.food_allowance or 0.0 for tr in raw_trips)
        tot_accom = sum(tr.accommodation_allowance or 0.0 for tr in raw_trips)
        tot_tolls = sum(tr.toll_cost or 0.0 for tr in raw_trips)

        emerg_stmt = select(FleetEmergencyExpense).order_by(FleetEmergencyExpense.created_at.desc())
        emerg_entries = (await db.execute(emerg_stmt)).scalars().all()
        tot_emerg_fuel = sum(e.amount or 0.0 for e in emerg_entries if (e.charge_type or "").upper() == "EMERGENCY_FUEL")
        tot_emerg_other = sum(e.amount or 0.0 for e in emerg_entries if (e.charge_type or "").upper() != "EMERGENCY_FUEL")
        tot_opex = tot_allow + tot_emerg_fuel + tot_emerg_other
        net_margin = tot_sales - tot_opex

        trips_count_total = len(raw_trips)
        trips_completed = sum(1 for tr in raw_trips if (tr.status or "").upper() in ("CLOSED", "SETTLED", "RETURNED", "BALANCED"))
        trips_pending = sum(1 for tr in raw_trips if (tr.status or "").upper() in (
            "CREATED", "QUOTED", "APPROVED", "PENDING_ASSIGNMENT", "ASSIGNED", "ALLOWANCE_APPROVED", "TRANSFERRED", "LOADED", "IN_TRANSIT", "ACTIVE", "RETURNING", "OFFLOADED"
        ))
        trips_cancelled = sum(1 for tr in raw_trips if (tr.status or "").upper() in ("CANCELLED", "REJECTED"))

        # City & Route Aggregations
        city_stats = {}
        route_stats = {}
        for tr in raw_trips:
            c = tr.destination_city or "Unknown"
            r = tr.route or c or "Unassigned"
            s = tr.trip_sales_value or 0.0
            o = tr.total_allowance or 0.0
            t = tr.transport_charge or 0.0

            if c not in city_stats:
                city_stats[c] = {"city": c, "trips": 0, "sales": 0.0, "opex": 0.0, "transport": 0.0}
            city_stats[c]["trips"] += 1
            city_stats[c]["sales"] = round(city_stats[c]["sales"] + s, 2)
            city_stats[c]["opex"] = round(city_stats[c]["opex"] + o, 2)
            city_stats[c]["transport"] = round(city_stats[c]["transport"] + t, 2)

            if r not in route_stats:
                route_stats[r] = {"route": r, "city": c, "trips": 0, "sales": 0.0, "opex": 0.0, "transport": 0.0}
            route_stats[r]["trips"] += 1
            route_stats[r]["sales"] = round(route_stats[r]["sales"] + s, 2)
            route_stats[r]["opex"] = round(route_stats[r]["opex"] + o, 2)
            route_stats[r]["transport"] = round(route_stats[r]["transport"] + t, 2)

        top_cities = sorted(city_stats.values(), key=lambda x: x["trips"], reverse=True)
        top_routes = sorted(route_stats.values(), key=lambda x: x["sales"], reverse=True)

        avg_rev = round(tot_sales / trips_count_total, 2) if trips_count_total > 0 else 0.0
        avg_exp = round(tot_opex / trips_count_total, 2) if trips_count_total > 0 else 0.0
        avg_alw = round(tot_allow / trips_count_total, 2) if trips_count_total > 0 else 0.0

        shortfall_tot = fleet_stats.get("total_outstanding_backlog", 0.0) + fleet_stats.get("total_recovered", 0.0)
        recovered_tot = fleet_stats.get("total_recovered", 0.0)
        rec_rate = round((recovered_tot / shortfall_tot * 100), 1) if shortfall_tot > 0 else 100.0

        cleared_tot = sum(p["cleared_amount"] for p in payments_list)
        debt_tot = fleet_stats.get("total_outstanding_backlog", 0.0)
        fleet_util = round((active_trips_count / trucks_available * 100), 1) if trucks_available > 0 else 0.0
        ws_impact = trucks_total - trucks_available

        # 8b. Real Time-Series Sales Trends: Day-Wise, Month-Wise, and Company-Wise
        def _normalize_co(comp_str, ph_str=""):
            s = (comp_str or "").lower()
            if "lg" in s or "plast" in s:
                return "LG Plast"
            elif "tagoneswa" in s or "hardware" in s or "tg" in s:
                return "Tagoneswa Hardware"
            elif "kreckle" in s or "food" in s:
                return "Kreckle Foods"
            if ph_str and ph_str in OFFICIAL_SALES_REPS_DIRECTORY:
                sp_c = OFFICIAL_SALES_REPS_DIRECTORY[ph_str].get("company", "").lower()
                if "lg" in sp_c:
                    return "LG Plast"
                elif "tagoneswa" in sp_c or "tg" in sp_c:
                    return "Tagoneswa Hardware"
                elif "kreckle" in sp_c:
                    return "Kreckle Foods"
            return "LG Plast"

        now_utc = datetime.datetime.utcnow()
        # Day-wise: Last 14 days
        days_list = [(now_utc - datetime.timedelta(days=i)).strftime("%Y-%m-%d") for i in range(13, -1, -1)]
        day_map = {d: {"total": 0.0, "LG Plast": 0.0, "Tagoneswa Hardware": 0.0, "Kreckle Foods": 0.0, "trips": 0} for d in days_list}

        # Month-wise: Last 6 months
        months_list = []
        for i in range(5, -1, -1):
            m_date = now_utc - datetime.timedelta(days=i * 30)
            m_key = m_date.strftime("%b %Y")
            if m_key not in months_list:
                months_list.append(m_key)
        month_map = {m: {"total": 0.0, "LG Plast": 0.0, "Tagoneswa Hardware": 0.0, "Kreckle Foods": 0.0, "trips": 0} for m in months_list}

        co_totals = {
            "LG Plast": {"sales": 0.0, "trips": 0},
            "Tagoneswa Hardware": {"sales": 0.0, "trips": 0},
            "Kreckle Foods": {"sales": 0.0, "trips": 0}
        }

        for tr in raw_trips:
            s_val = round(tr.trip_sales_value or 0.0, 2)
            co = _normalize_co(tr.company_name, tr.salesperson_phone)
            co_totals[co]["sales"] = round(co_totals[co]["sales"] + s_val, 2)
            co_totals[co]["trips"] += 1

            if tr.created_at:
                d_str = tr.created_at.strftime("%Y-%m-%d")
                if d_str in day_map:
                    day_map[d_str]["total"] = round(day_map[d_str]["total"] + s_val, 2)
                    day_map[d_str][co] = round(day_map[d_str][co] + s_val, 2)
                    day_map[d_str]["trips"] += 1

                m_str = tr.created_at.strftime("%b %Y")
                if m_str in month_map:
                    month_map[m_str]["total"] = round(month_map[m_str]["total"] + s_val, 2)
                    month_map[m_str][co] = round(month_map[m_str][co] + s_val, 2)
                    month_map[m_str]["trips"] += 1

        sales_trends = {
            "day_wise": {
                "labels": [datetime.datetime.strptime(d, "%Y-%m-%d").strftime("%d %b") for d in days_list],
                "dates": days_list,
                "total": [day_map[d]["total"] for d in days_list],
                "lg_plast": [day_map[d]["LG Plast"] for d in days_list],
                "tagoneswa": [day_map[d]["Tagoneswa Hardware"] for d in days_list],
                "kreckle": [day_map[d]["Kreckle Foods"] for d in days_list],
                "trips": [day_map[d]["trips"] for d in days_list]
            },
            "month_wise": {
                "labels": months_list,
                "total": [month_map[m]["total"] for m in months_list],
                "lg_plast": [month_map[m]["LG Plast"] for m in months_list],
                "tagoneswa": [month_map[m]["Tagoneswa Hardware"] for m in months_list],
                "kreckle": [month_map[m]["Kreckle Foods"] for m in months_list],
                "trips": [month_map[m]["trips"] for m in months_list]
            },
            "company_wise": {
                "companies": ["LG Plast", "Tagoneswa Hardware", "Kreckle Foods"],
                "totals": [co_totals["LG Plast"]["sales"], co_totals["Tagoneswa Hardware"]["sales"], co_totals["Kreckle Foods"]["sales"]],
                "trips": [co_totals["LG Plast"]["trips"], co_totals["Tagoneswa Hardware"]["trips"], co_totals["Kreckle Foods"]["trips"]],
                "day_labels": [datetime.datetime.strptime(d, "%Y-%m-%d").strftime("%d %b") for d in days_list],
                "day_lg": [day_map[d]["LG Plast"] for d in days_list],
                "day_tg": [day_map[d]["Tagoneswa Hardware"] for d in days_list],
                "day_kr": [day_map[d]["Kreckle Foods"] for d in days_list],
                "month_labels": months_list,
                "month_lg": [month_map[m]["LG Plast"] for m in months_list],
                "month_tg": [month_map[m]["Tagoneswa Hardware"] for m in months_list],
                "month_kr": [month_map[m]["Kreckle Foods"] for m in months_list]
            }
        }

        operations_analytics = {
            "total_sales": 0.0,
            "total_transport_charges": round(tot_trans, 2),
            "total_allowances": round(tot_allow, 2),
            "total_meals": round(tot_meals, 2),
            "total_accommodation": round(tot_accom, 2),
            "total_tolls": round(tot_tolls, 2),
            "total_emergency_fuel": round(tot_emerg_fuel, 2),
            "total_emergency_other": round(tot_emerg_other, 2),
            "total_operational_expenses": round(tot_opex, 2),
            "net_amount": round(net_margin, 2),
            "trips_total": trips_count_total,
            "trips_completed": trips_completed,
            "trips_pending": trips_pending,
            "trips_cancelled": trips_cancelled,
            "avg_revenue_per_trip": 0.0,
            "avg_opex_per_trip": avg_exp,
            "avg_allowance_per_trip": avg_alw,
            "fleet_utilization_pct": fleet_util,
            "workshop_impact_count": ws_impact,
            "shortfall_total": round(shortfall_tot, 2),
            "recovery_total": round(recovered_tot, 2),
            "recovery_rate_pct": rec_rate,
            "cleared_payments_total": round(cleared_tot, 2),
            "outstanding_debt_total": round(debt_tot, 2),
            "cities": [{"city": c["city"], "trips": c["trips"], "opex": c["opex"], "transport": c["transport"], "sales": 0.0} for c in top_cities],
            "routes": [{"route": r["route"], "city": r["city"], "trips": r["trips"], "opex": r["opex"], "transport": r["transport"], "sales": 0.0} for r in top_routes],
            "sales_trends": {}
        }

        # Role-filtered analytics and payloads
        filtered_analytics = operations_analytics if can_view_balances else {
            **operations_analytics,
            "total_sales": 0.0,
            "avg_revenue_per_trip": 0.0,
            "net_amount": 0.0,
            "shortfall_total": 0.0,
            "recovery_total": 0.0,
            "cleared_payments_total": 0.0,
            "outstanding_debt_total": 0.0,
            "cities": operations_analytics["cities"],
            "routes": operations_analytics["routes"],
            "sales_trends": {}
        }

        fleet_payload = {
            "stats": fleet_stats if can_view_balances else {
                **fleet_stats,
                "total_sales_value": 0.0,
                "total_outstanding_backlog": 0.0,
                "total_recovered": 0.0,
            },
            "salespersons": salespersons_list if can_view_balances else [
                {
                    "phone": sp["phone"],
                    "name": sp["name"],
                    "company": sp.get("company", "Commercial Sales"),
                    "employee_id": sp.get("employee_id"),
                    "email": sp.get("email", ""),
                    "active": sp.get("active", True),
                    "is_official": sp.get("is_official", True),
                    "total_shortfalls": 0.0,
                    "total_recovered": 0.0,
                    "net_balance": 0.0,
                    "trips_count": sp.get("trips_count", 0),
                    "entries_count": 0,
                    "recent_date": sp.get("recent_date", "Active Commercial Roster"),
                    "risk_level": "HEALTHY",
                    "hide_financials": True
                }
                for sp in salespersons_list
            ],
            "sales_reps": sales_reps_list if can_view_balances else [
                {
                    "employee_id": r.get("employee_id"),
                    "full_name": r.get("full_name"),
                    "phone": r.get("phone"),
                    "email": r.get("email", ""),
                    "company": r.get("company", "Commercial Sales"),
                    "active": r.get("active", True)
                }
                for r in sales_reps_list
            ],
            "records": approval_records if can_view_balances else [
                {**r, "trip_sales_value": 0.0, "shortfall": 0.0, "pending_balance_recorded": 0.0}
                for r in approval_records
            ],
            "trips": trips_list if can_view_balances else [
                {**t, "trip_sales_value": 0.0}
                for t in trips_list
            ],
            "payments": payments_list if can_view_balances else [],
            "ledger": ledger_records if can_view_balances else [],
            "audit_logs": audit_records,
            "analytics": filtered_analytics if can_view_analytics else {},
            "cities": sorted(list(cities_set)),
            "route_rules": get_all_cached_city_rules(),
            "fuel_price": get_fuel_price(),
            "meal_rate": get_meal_rate(),
            "accommodation_rate": get_accommodation_rate(),
            "expense_budget_pct": get_expense_budget_pct(),
            "van_minimum_surcharge": get_van_minimum_surcharge(),
            "trucks": trucks_list,
            "drivers": drivers_list,
            "overview": {
                "kpis": {
                    "active_ongoing_trips": active_trips_count,
                    "in_transit_trips": in_transit_trips,
                    "pending_trip_approvals": total_pending_approvals,
                    "pending_approvals_shortfall": pending_approvals_count,
                    "pending_quotes_count": quoted_trips_count,
                    "trucks_total": trucks_total,
                    "trucks_available": trucks_available,
                    "trucks_in_workshop": trucks_in_workshop,
                    "trucks_awaiting_parts": trucks_awaiting_parts,
                    "trucks_awaiting_qc": trucks_awaiting_qc,
                    # Legacy aliases (keep for JS backwards compat)
                    "trucks_active": trucks_available,
                    "trucks_maintenance": trucks_maintenance,
                    "drivers_total": drivers_total,
                    "drivers_active": drivers_active,
                    "sales_pipeline": sales_pipeline_summary,
                    "sales_rep_balance": sales_rep_balance_summary,
                    "pending_bottlenecks_count": len(operations_alerts)
                },
                "alerts": operations_alerts,
                "recent_activity": recent_activity_list,
                "analytics": filtered_analytics,
                "audit_logs": audit_records[:15],
                "role": user.get("role"),
                "is_read_only": is_observer
            }
        }

    # Master Cross-Domain Executive KPI Calculation
    active_ops = 0
    resolved_ops = 0
    total_ops = 0
    if it_payload:
        active_ops += (it_payload["stats"]["open"] + it_payload["stats"]["in_progress"])
        resolved_ops += (it_payload["stats"]["resolved"] + it_payload["stats"]["closed"])
        total_ops += it_payload["stats"]["total"]
    if projects_payload:
        active_ops += (projects_payload["stats"]["open"] + projects_payload["stats"]["in_progress"])
        resolved_ops += (projects_payload["stats"]["resolved"] + projects_payload["stats"]["closed"])
        total_ops += projects_payload["stats"]["total"]
    if logistics_payload:
        active_ops += (logistics_payload["stats"]["in_workshop"] + logistics_payload["stats"]["under_review"] + logistics_payload["stats"]["awaiting_parts"])
        resolved_ops += logistics_payload["stats"]["closed_fleet"]
        total_ops += len(logistics_payload["records"])
    if fleet_payload:
        active_ops += (fleet_payload["stats"]["shortfall_trips"] - fleet_payload["stats"]["approved_trips"] if fleet_payload["stats"]["shortfall_trips"] > fleet_payload["stats"]["approved_trips"] else 0)
        resolved_ops += fleet_payload["stats"]["approved_trips"]
        total_ops += fleet_payload["stats"]["total_trips"]

    res_rate = int((resolved_ops / total_ops) * 100) if total_ops > 0 else 100
    pending_fleet_approvals = sum(1 for fa in fleet_approvals if fa.status == "SHORTFALL_RECORDED") if fleet_payload else 0
    master_kpis = {
        "active_operations": active_ops,
        "pending_approvals": pending_fleet_approvals,
        "resolved_operations": resolved_ops,
        "total_operations": total_ops,
        "resolution_rate_pct": res_rate,
        "total_financial_backlog": fleet_payload["stats"]["total_outstanding_backlog"] if (fleet_payload and can_view_balances) else 0.0,
        "transport_revenue": fleet_payload["stats"]["total_transport_charges"] if fleet_payload else 0.0
    }

    return {
        "user": {
            "username": user["username"],
            "name": user["name"],
            "role": user["role"],
            "allowed_domains": allowed,
            "effective_permissions": list(user.get("effective_permissions", [])),
            "custom_permissions": user.get("custom_permissions", {})
        },
        "master_kpis": master_kpis,
        "it": it_payload,
        "projects": projects_payload,
        "logistics": logistics_payload,
        "fleet": fleet_payload
    }

# -------------------------------------------------------------
# Main Secured Dashboard View (GET /dashboard)
# -------------------------------------------------------------
@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard_view(request: Request):
    """Renders the executive shadcn/ui-styled Operations Dashboard with role-based domain access."""
    user = get_current_user_from_request(request)
    if not user:
        return RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)

    allowed = user.get("allowed_domains", ["it", "projects", "logistics", "fleet", "accounts", "admin"])
    default_tab = "fleet" if user["role"] in ("MASTER_ADMIN", "EXECUTIVE_OBSERVER", "FLEET_ADMIN", "SALES_ADMIN", "ACCOUNTS_USER", "LOGISTICS_MANAGER") else ("logistics" if user["role"] == "LOGISTICS_ADMIN" else ("projects" if user["role"] == "PROJECTS_ADMIN" else "it"))

    # Generate navigation tab buttons based on allowed domains
    tabs_html = []
    if "fleet" in allowed:
        tabs_html.append('<button id="btn-tab-fleet" onclick="switchDomain(\'fleet\')" class="tab-btn px-3.5 py-1.5 rounded-md text-xs font-medium text-zinc-600 dark:text-zinc-400 hover:text-zinc-900 dark:hover:text-zinc-100 transition-colors whitespace-nowrap cursor-pointer">Sales to Fleet</button>')
    if "it" in allowed:
        tabs_html.append('<button id="btn-tab-it" onclick="switchDomain(\'it\')" class="tab-btn px-3.5 py-1.5 rounded-md text-xs font-medium text-zinc-600 dark:text-zinc-400 hover:text-zinc-900 dark:hover:text-zinc-100 transition-colors whitespace-nowrap cursor-pointer">IT Support</button>')
    if "projects" in allowed:
        tabs_html.append('<button id="btn-tab-projects" onclick="switchDomain(\'projects\')" class="tab-btn px-3.5 py-1.5 rounded-md text-xs font-medium text-zinc-600 dark:text-zinc-400 hover:text-zinc-900 dark:hover:text-zinc-100 transition-colors whitespace-nowrap cursor-pointer">Building Projects</button>')
    if "logistics" in allowed:
        tabs_html.append('<button id="btn-tab-logistics" onclick="switchDomain(\'logistics\')" class="tab-btn px-3.5 py-1.5 rounded-md text-xs font-medium text-zinc-600 dark:text-zinc-400 hover:text-zinc-900 dark:hover:text-zinc-100 transition-colors whitespace-nowrap cursor-pointer">Workshop Fleet</button>')

    nav_tabs_markup = "\n".join(tabs_html)
    allowed_domains_json = str(allowed).replace("'", '"')

    # Construct Dynamic Role-Based Sidebar Navigation
    user_role = user.get("role", "LOGISTICS_USER")
    user_name = user.get("name", "User")
    is_master_admin = (user_role == "MASTER_ADMIN")

    # Professional Lucide SVG Icons for 100% offline, crisp, zero-flicker rendering
    icon_menu = '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="w-4 h-4"><line x1="4" x2="20" y1="12" y2="12"/><line x1="4" x2="20" y1="6" y2="6"/><line x1="4" x2="20" y1="18" y2="18"/></svg>'
    icon_close = '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="w-4 h-4"><path d="M18 6 6 18"/><path d="m6 6 12 12"/></svg>'
    icon_moon = '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="w-4 h-4 theme-toggle-svg"><path d="M12 3a6 6 0 0 0 9 9 9 9 0 1 1-9-9Z"/></svg>'
    icon_refresh = '<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="w-3.5 h-3.5"><path d="M3 12a9 9 0 0 1 9-9 9.75 9.75 0 0 1 6.74 2.74L21 8"/><path d="M21 3v5h-5"/><path d="M21 12a9 9 0 0 1-9 9 9.75 9.75 0 0 1-6.74-2.74L3 16"/><path d="M8 16H3v5"/></svg>'
    icon_check = '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="w-4 h-4 text-emerald-500"><circle cx="12" cy="12" r="10"/><path d="m9 12 2 2 4-4"/></svg>'
    icon_clipboard = '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="w-4 h-4 text-zinc-500"><rect width="8" height="4" x="8" y="2" rx="1" ry="1"/><path d="M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2"/><path d="M12 11h4"/><path d="M12 16h4"/><path d="M8 11h.01"/><path d="M8 16h.01"/></svg>'
    icon_clock = '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="w-4 h-4 text-amber-500"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>'
    icon_timer = '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="w-4 h-4 text-zinc-500"><line x1="10" x2="14" y1="2" y2="2"/><line x1="12" x2="12" y1="14" y2="8"/><circle cx="12" cy="14" r="8"/></svg>'
    icon_building = '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="w-4 h-4 text-emerald-500"><path d="M6 22V4a2 2 0 0 1 2-2h8a2 2 0 0 1 2 2v18Z"/><path d="M6 12H4a2 2 0 0 0-2 2v6a2 2 0 0 0 2 2h2"/><path d="M18 9h2a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2h-2"/><path d="M10 6h4"/><path d="M10 10h4"/><path d="M10 14h4"/><path d="M10 18h4"/></svg>'
    icon_hardhat = '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="w-4 h-4 text-zinc-500"><path d="M2 18a1 1 0 0 0 1 1h18a1 1 0 0 0 1-1v-2a1 1 0 0 0-1-1H3a1 1 0 0 0-1 1v2z"/><path d="M10 10V5a1 1 0 0 1 1-1h2a1 1 0 0 1 1 1v5"/><path d="M4 15v-3a6 6 0 0 1 6-6h0"/><path d="M14 6h0a6 6 0 0 1 6 6v3"/></svg>'
    icon_hammer = '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="w-4 h-4 text-amber-500"><path d="m15 12-8.5 8.5c-.83.83-2.17.83-3 0 0 0 0 0 0 0a2.12 2.12 0 0 1 0-3L12 9"/><path d="M17.64 15 22 10.64"/><path d="m20.91 3.26-1.7-1.7c-.59-.59-1.54-.59-2.12 0L10.8 7.84a1.5 1.5 0 0 0 0 2.12l3.24 3.24a1.5 1.5 0 0 0 2.12 0l6.28-6.28c.58-.59.58-1.54 0-2.12l-1.53-1.54Z"/></svg>'
    icon_map_pin = '<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="w-3.5 h-3.5 text-zinc-400"><path d="M20 10c0 4.993-5.539 10.193-7.399 11.799a1 1 0 0 1-1.202 0C9.539 20.193 4 14.993 4 10a8 8 0 0 1 16 0"/><circle cx="12" cy="10" r="3"/></svg>'
    icon_wrench = '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="w-4 h-4 text-zinc-500"><path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z"/></svg>'
    icon_truck = '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="w-4 h-4 text-zinc-500"><path d="M14 18V6a2 2 0 0 0-2-2H4a2 2 0 0 0-2 2v11a1 1 0 0 1 1 1h2"/><path d="M15 18H9"/><path d="M19 18h2a1 1 0 0 0 1-1v-3.65a1 1 0 0 0-.22-.624l-3.48-4.35A1 1 0 0 0 17.52 8H14"/><circle cx="17" cy="18" r="2"/><circle cx="7" cy="18" r="2"/></svg>'
    icon_gear = '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="w-4 h-4 text-rose-500"><path d="M12.22 2h-.44a2 2 0 0 0-2 2v.18a2 2 0 0 1-1 1.73l-.43.25a2 2 0 0 1-2 0l-.15-.08a2 2 0 0 0-2.73.73l-.22.38a2 2 0 0 0 .73 2.73l.15.1a2 2 0 0 1 1 1.72v.51a2 2 0 0 1-1 1.74l-.15.09a2 2 0 0 0-.73 2.73l.22.38a2 2 0 0 0 2.73.73l.15-.08a2 2 0 0 1 2 0l.43.25a2 2 0 0 1 1 1.73V20a2 2 0 0 0 2 2h.44a2 2 0 0 0 2-2v-.18a2 2 0 0 1 1-1.73l.43-.25a2 2 0 0 1 2 0l.15.08a2 2 0 0 0 2.73-.73l.22-.39a2 2 0 0 0-.73-2.73l-.15-.08a2 2 0 0 1-1-1.74v-.5a2 2 0 0 1 1-1.74l.15-.09a2 2 0 0 0 .73-2.73l-.22-.38a2 2 0 0 0-2.73-.73l-.15.08a2 2 0 0 1-2 0l-.43-.25a2 2 0 0 1-1-1.73V4a2 2 0 0 0-2-2z"/><circle cx="12" cy="12" r="3"/></svg>'
    icon_traffic = '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="w-4 h-4 text-emerald-500"><rect width="8" height="18" x="8" y="3" rx="2"/><circle cx="12" cy="7" r="1.5"/><circle cx="12" cy="12" r="1.5"/><circle cx="12" cy="17" r="1.5"/></svg>'

    can_manage_fuel = user_has_permission(user, "manage_fuel_price")
    can_manage_city = user_has_permission(user, "manage_city_minimums")
    can_clear_debt = user_has_permission(user, "clear_sales_rep_debt")
    can_view_audit = user_has_permission(user, "view_audit_logs")
    can_manage_users = user_has_permission(user, "manage_user_permissions")
    can_manage_trucks = user_has_permission(user, "manage_trucks")
    can_manage_drivers = user_has_permission(user, "manage_drivers")
    can_view_balances = user_has_permission(user, "view_sales_rep_balances")

    sidebar_links = []
    # Domain Navigation (fast jumping across operational modules from drawer sidebar)
    sidebar_links.append('<div class="px-3 pt-2 pb-1 text-[11px] font-semibold uppercase tracking-wider text-zinc-400 dark:text-zinc-500">Domain Navigation</div>')
    if "fleet" in allowed:
        sidebar_links.append('<button onclick="switchDomain(\'fleet\'); toggleSidebar(false);" class="w-full text-left px-3 py-2 rounded-lg text-xs font-medium text-zinc-700 dark:text-zinc-300 hover:bg-zinc-100 dark:hover:bg-zinc-800 hover:text-zinc-950 dark:hover:text-zinc-50 transition flex items-center gap-2">Sales to Fleet</button>')
    if "it" in allowed:
        sidebar_links.append('<button onclick="switchDomain(\'it\'); toggleSidebar(false);" class="w-full text-left px-3 py-2 rounded-lg text-xs font-medium text-zinc-700 dark:text-zinc-300 hover:bg-zinc-100 dark:hover:bg-zinc-800 hover:text-zinc-950 dark:hover:text-zinc-50 transition flex items-center gap-2">IT Support</button>')
    if "projects" in allowed:
        sidebar_links.append('<button onclick="switchDomain(\'projects\'); toggleSidebar(false);" class="w-full text-left px-3 py-2 rounded-lg text-xs font-medium text-zinc-700 dark:text-zinc-300 hover:bg-zinc-100 dark:hover:bg-zinc-800 hover:text-zinc-950 dark:hover:text-zinc-50 transition flex items-center gap-2">Building Projects</button>')
    if "logistics" in allowed:
        sidebar_links.append('<button onclick="switchDomain(\'logistics\'); toggleSidebar(false);" class="w-full text-left px-3 py-2 rounded-lg text-xs font-medium text-zinc-700 dark:text-zinc-300 hover:bg-zinc-100 dark:hover:bg-zinc-800 hover:text-zinc-950 dark:hover:text-zinc-50 transition flex items-center gap-2">Workshop Fleet</button>')

    # Unique Operational Actions (only actions not present in horizontal fast-nav row)
    if can_manage_fuel or can_manage_city or can_manage_trucks or can_manage_drivers or can_clear_debt or can_manage_users or can_view_audit:
        sidebar_links.append('<div class="px-3 pt-3 pb-1 text-[11px] font-semibold uppercase tracking-wider text-zinc-400 dark:text-zinc-500">Operational Actions</div>')
        if can_manage_fuel or can_manage_city:
            sidebar_links.append('<button onclick="openCityConfigModal(); toggleSidebar(false);" class="w-full text-left px-3 py-2 rounded-lg text-xs font-medium text-zinc-700 dark:text-zinc-300 hover:bg-zinc-100 dark:hover:bg-zinc-800 hover:text-zinc-950 dark:hover:text-zinc-50 transition flex items-center gap-2">Fuel & City Rates</button>')
        if can_manage_trucks:
            sidebar_links.append('<button onclick="openAddTruckModal(); toggleSidebar(false);" class="w-full text-left px-3 py-2 rounded-lg text-xs font-medium text-zinc-700 dark:text-zinc-300 hover:bg-zinc-100 dark:hover:bg-zinc-800 hover:text-zinc-950 dark:hover:text-zinc-50 transition flex items-center gap-2">Register Fleet Vehicle</button>')
        if can_manage_drivers:
            sidebar_links.append('<button onclick="openAddDriverModal(); toggleSidebar(false);" class="w-full text-left px-3 py-2 rounded-lg text-xs font-medium text-zinc-700 dark:text-zinc-300 hover:bg-zinc-100 dark:hover:bg-zinc-800 hover:text-zinc-950 dark:hover:text-zinc-50 transition flex items-center gap-2">Register Commercial Driver</button>')
        if user_has_permission(user, "manage_sales_pipeline") or can_manage_trucks:
            sidebar_links.append('<button onclick="openAddSalesRepModal(); toggleSidebar(false);" class="w-full text-left px-3 py-2 rounded-lg text-xs font-medium text-zinc-700 dark:text-zinc-300 hover:bg-zinc-100 dark:hover:bg-zinc-800 hover:text-zinc-950 dark:hover:text-zinc-50 transition flex items-center gap-2">Register Sales Rep</button>')
        if can_clear_debt:
            sidebar_links.append('<button onclick="openClearPaymentModal(); toggleSidebar(false);" class="w-full text-left px-3 py-2 rounded-lg text-xs font-medium text-zinc-700 dark:text-zinc-300 hover:bg-zinc-100 dark:hover:bg-zinc-800 hover:text-zinc-950 dark:hover:text-zinc-50 transition flex items-center gap-2">Clear Rep Balance</button>')
        if can_manage_users:
            sidebar_links.append('<button onclick="openUserManagementModal(); toggleSidebar(false);" class="w-full text-left px-3 py-2 rounded-lg text-xs font-medium text-zinc-700 dark:text-zinc-300 hover:bg-zinc-100 dark:hover:bg-zinc-800 hover:text-zinc-950 dark:hover:text-zinc-50 transition flex items-center gap-2">User Permissions</button>')
        if can_view_audit:
            sidebar_links.append('<button onclick="openAuditLogsModal(); toggleSidebar(false);" class="w-full text-left px-3 py-2 rounded-lg text-xs font-medium text-zinc-700 dark:text-zinc-300 hover:bg-zinc-100 dark:hover:bg-zinc-800 hover:text-zinc-950 dark:hover:text-zinc-50 transition flex items-center gap-2">System Audit Logs</button>')

    sidebar_markup = "\n".join(sidebar_links)

    nav_salespersons_opt = '<option value="salespersons">Sales Rep Balances</option>' if can_view_balances else ''
    nav_payments_opt = '<option value="payments">Payment History</option>' if can_view_balances else ''
    nav_ledger_opt = '<option value="ledger">Financial Audit Log</option>' if can_view_balances else ''
    nav_analytics_opt = '<option value="analytics">Data Analytics</option>' if is_master_admin else ''

    nav_salespersons_btn = '<button onclick="switchFleetSubView(\'salespersons\')" id="fleet-btn-salespersons" data-view="salespersons" class="fleet-quick-pill px-3 py-1.5 rounded-md text-xs font-medium bg-white/60 dark:bg-zinc-900/60 backdrop-blur-sm border border-zinc-200/80 dark:border-zinc-800/80 text-zinc-700 dark:text-zinc-300 hover:bg-zinc-100 dark:hover:bg-zinc-800 hover:text-zinc-950 dark:hover:text-zinc-50 transition cursor-pointer whitespace-nowrap">Sales Reps</button>' if can_view_balances else ''
    nav_payments_btn = '<button onclick="switchFleetSubView(\'payments\')" id="fleet-btn-payments" data-view="payments" class="fleet-quick-pill px-3 py-1.5 rounded-md text-xs font-medium bg-white/60 dark:bg-zinc-900/60 backdrop-blur-sm border border-zinc-200/80 dark:border-zinc-800/80 text-zinc-700 dark:text-zinc-300 hover:bg-zinc-100 dark:hover:bg-zinc-800 hover:text-zinc-950 dark:hover:text-zinc-50 transition cursor-pointer whitespace-nowrap">Payments</button>' if can_view_balances else ''
    nav_ledger_btn = '<button onclick="switchFleetSubView(\'ledger\')" id="fleet-btn-ledger" data-view="ledger" class="fleet-quick-pill px-3 py-1.5 rounded-md text-xs font-medium bg-white/60 dark:bg-zinc-900/60 backdrop-blur-sm border border-zinc-200/80 dark:border-zinc-800/80 text-zinc-700 dark:text-zinc-300 hover:bg-zinc-100 dark:hover:bg-zinc-800 hover:text-zinc-950 dark:hover:text-zinc-50 transition cursor-pointer whitespace-nowrap">Audit Log</button>' if can_view_balances else ''
    nav_analytics_btn = '<button onclick="switchFleetSubView(\'analytics\')" id="fleet-btn-analytics" data-view="analytics" class="fleet-quick-pill px-3 py-1.5 rounded-md text-xs font-medium bg-white/60 dark:bg-zinc-900/60 backdrop-blur-sm border border-zinc-200/80 dark:border-zinc-800/80 text-zinc-700 dark:text-zinc-300 hover:bg-zinc-100 dark:hover:bg-zinc-800 hover:text-zinc-950 dark:hover:text-zinc-50 transition cursor-pointer whitespace-nowrap">Analytics</button>' if is_master_admin else ''

    # Pre-render conditional blocks for cleaner template
    rates_btn_html = '<button onclick="openCityConfigModal()" class="px-3 py-1.5 rounded-md text-xs font-medium border border-zinc-200 bg-white hover:bg-zinc-100 dark:border-zinc-800 dark:bg-zinc-900 dark:hover:bg-zinc-800 text-zinc-800 dark:text-zinc-200 transition shadow-xs cursor-pointer">Fuel & City Rates</button>' if (can_manage_fuel or can_manage_city) else ''
    clear_debt_btn_html = '<button onclick="openClearPaymentModal()" class="px-3 py-1.5 rounded-md text-xs font-medium bg-emerald-600 hover:bg-emerald-700 text-white transition shadow-xs cursor-pointer">Clear Rep Debt</button>' if can_clear_debt else ''
    user_mgmt_btn_html = '<button onclick="openUserManagementModal()" class="px-3 py-1.5 rounded-md text-xs font-medium bg-zinc-900 hover:bg-zinc-800 dark:bg-zinc-100 dark:hover:bg-zinc-200 text-zinc-50 dark:text-zinc-900 transition shadow-xs cursor-pointer">User Permissions</button>' if can_manage_users else ''
    audit_logs_btn_html = '<button onclick="openAuditLogsModal()" class="px-3 py-1.5 rounded-md text-xs font-medium border border-zinc-200 bg-white hover:bg-zinc-100 dark:border-zinc-800 dark:bg-zinc-900 dark:hover:bg-zinc-800 text-zinc-800 dark:text-zinc-200 transition shadow-xs cursor-pointer">Audit Logs</button>' if can_view_audit else ''

    if can_view_balances:
        master_kpi_cards_3_4 = """
        <div class="rounded-lg border border-zinc-200/80 bg-zinc-50/60 p-4 dark:border-zinc-800/80 dark:bg-zinc-900/40">
            <div class="text-xs font-medium text-zinc-500 dark:text-zinc-400">Transport Billed</div>
            <div class="text-2xl font-bold tracking-tight text-zinc-900 dark:text-zinc-100 mt-1 font-mono" id="master-transport-revenue">$0.00</div>
            <div class="text-xs text-zinc-500 dark:text-zinc-400 mt-0.5">Shortfall recovery fee</div>
        </div>
        <div class="rounded-lg border border-zinc-200/80 bg-zinc-50/60 p-4 dark:border-zinc-800/80 dark:bg-zinc-900/40">
            <div class="text-xs font-medium text-zinc-500 dark:text-zinc-400">Sales Rep Debt Backlog</div>
            <div class="text-2xl font-bold tracking-tight text-rose-600 dark:text-rose-400 mt-1 font-mono" id="master-financial-backlog">$0.00</div>
            <div class="text-xs text-zinc-500 dark:text-zinc-400 mt-0.5">Pending settlement recovery</div>
        </div>
        """
        ov_card4_html = """
        <div class="rounded-xl border border-zinc-200 bg-white p-4 sm:p-5 shadow-xs dark:border-zinc-800 dark:bg-zinc-950">
            <div class="text-xs font-medium text-zinc-500 dark:text-zinc-400">Average Revenue / Trip</div>
            <div class="text-2xl font-bold tracking-tight text-zinc-900 dark:text-zinc-100 mt-1 font-mono truncate" id="ov-kpi-avg-revenue">$0.00</div>
            <div class="text-xs text-zinc-500 dark:text-zinc-400 mt-0.5 truncate">Average trip revenue</div>
        </div>
        """
        approvals_cols_head = """
        <th class="px-4 py-3 whitespace-nowrap">ERP Valuation</th>
        <th class="px-4 py-3 whitespace-nowrap">Shortfall / Transport</th>
        <th class="px-4 py-3 whitespace-nowrap">Settlement (Customer vs Debt)</th>
        """
        approvals_card5_stat = """
        <div class="rounded-xl border border-zinc-200 bg-white p-4 shadow-xs dark:border-zinc-800 dark:bg-zinc-950 col-span-2 sm:col-span-1">
            <div class="text-xs font-medium text-zinc-500 dark:text-zinc-400">Sales Rep Debt</div>
            <div class="text-2xl font-bold tracking-tight text-rose-600 dark:text-rose-400 mt-1 font-mono" id="fleet-stat-backlog">$0.00</div>
            <div class="text-xs text-rose-600 dark:text-rose-400 mt-0.5">Pending Shortfall</div>
        </div>
        """
    else:
        master_kpi_cards_3_4 = """
        <div class="rounded-lg border border-zinc-200/80 bg-zinc-50/60 p-4 dark:border-zinc-800/80 dark:bg-zinc-900/40">
            <div class="text-xs font-medium text-zinc-500 dark:text-zinc-400">Active In-Transit</div>
            <div class="text-2xl font-bold tracking-tight text-emerald-600 dark:text-emerald-400 mt-1 font-mono" id="master-in-transit-count">0</div>
            <div class="text-xs text-zinc-500 dark:text-zinc-400 mt-0.5">Commercial trips rolling</div>
        </div>
        <div class="rounded-lg border border-zinc-200/80 bg-zinc-50/60 p-4 dark:border-zinc-800/80 dark:bg-zinc-900/40">
            <div class="text-xs font-medium text-zinc-500 dark:text-zinc-400">Commercial Roster</div>
            <div class="text-2xl font-bold tracking-tight text-zinc-900 dark:text-zinc-100 mt-1 font-mono" id="master-roster-count">Active Roster</div>
            <div class="text-xs text-zinc-500 dark:text-zinc-400 mt-0.5">Fleet & Operations</div>
        </div>
        """
        ov_card4_html = """
        <div class="rounded-xl border border-zinc-200 bg-white p-4 sm:p-5 shadow-xs dark:border-zinc-800 dark:bg-zinc-950">
            <div class="text-xs font-medium text-zinc-500 dark:text-zinc-400">Active In-Transit</div>
            <div class="text-2xl font-bold tracking-tight text-zinc-900 dark:text-zinc-100 mt-1 font-mono truncate" id="ov-kpi-transit-ops">0</div>
            <div class="text-xs text-zinc-500 dark:text-zinc-400 mt-0.5 truncate">Currently rolling</div>
        </div>
        """
        approvals_cols_head = """
        <th class="px-4 py-3 whitespace-nowrap">Valuation Status</th>
        <th class="px-4 py-3 whitespace-nowrap">Shortfall Status</th>
        <th class="px-4 py-3 whitespace-nowrap">Accounting Status</th>
        """
        approvals_card5_stat = ""

    add_rep_btn = '<button onclick="openAddSalesRepModal()" class="px-3 py-1.5 rounded-md text-xs font-medium bg-zinc-900 hover:bg-zinc-800 dark:bg-zinc-100 dark:hover:bg-zinc-200 text-zinc-50 dark:text-zinc-900 transition shadow-xs cursor-pointer">+ Add Sales Rep</button>' if (user_has_permission(user, "manage_sales_pipeline") or can_manage_trucks) else ''
    rep_clear_btn = '<button onclick="openClearPaymentModal()" class="px-3 py-1.5 rounded-md text-xs font-medium bg-emerald-600 hover:bg-emerald-700 text-white transition shadow-xs cursor-pointer">Clear Debt Payment</button>' if can_clear_debt else ''
    total_pending_pill = '<div class="text-right"><span class="text-xs text-zinc-500 dark:text-zinc-400">Total Pending: </span><span class="text-sm font-bold text-rose-600 dark:text-rose-400 font-mono" id="fleet-total-pending-pill">$0.00</span></div>' if can_view_balances else ''

    if can_view_balances:
        salespersons_section_html = f"""
        <div id="fleet-section-salespersons" class="fleet-subview-panel rounded-xl border border-zinc-200 bg-white p-5 shadow-xs dark:border-zinc-800 dark:bg-zinc-950" style="display: none;">
            <div class="flex flex-col sm:flex-row sm:items-center justify-between mb-4 gap-2">
                <div>
                    <h3 class="text-sm font-semibold text-zinc-900 dark:text-zinc-100">Sales Representative Balances</h3>
                    <p class="text-xs text-zinc-500 dark:text-zinc-400 mt-0.5">Real-time balances tracked per sales representative with settlement action</p>
                </div>
                <div class="flex items-center gap-2">
                    {add_rep_btn}
                    {rep_clear_btn}
                    {total_pending_pill}
                </div>
            </div>

            <div class="flex flex-col sm:flex-row items-stretch sm:items-center justify-between gap-2.5 mb-4 pb-3 border-b border-zinc-100 dark:border-zinc-800">
                <div class="flex flex-wrap items-center gap-1.5" id="sp-company-filters">
                    <button onclick="filterSalespersonsByCompany('ALL')" id="sp-filter-ALL" class="sp-filter-btn px-3 py-1.5 rounded-md text-xs font-medium bg-zinc-900 text-zinc-50 dark:bg-zinc-50 dark:text-zinc-900 shadow-xs transition cursor-pointer">All Divisions</button>
                    <button onclick="filterSalespersonsByCompany('LG Plast')" id="sp-filter-LG" class="sp-filter-btn px-3 py-1.5 rounded-md text-xs font-medium text-zinc-600 dark:text-zinc-400 hover:bg-zinc-100 dark:hover:bg-zinc-800 transition cursor-pointer">LG Plast</button>
                    <button onclick="filterSalespersonsByCompany('Tagoneswa Hardware')" id="sp-filter-TG" class="sp-filter-btn px-3 py-1.5 rounded-md text-xs font-medium text-zinc-600 dark:text-zinc-400 hover:bg-zinc-100 dark:hover:bg-zinc-800 transition cursor-pointer">Tagoneswa Hardware</button>
                    <button onclick="filterSalespersonsByCompany('Kreckle Foods')" id="sp-filter-Kreckle" class="sp-filter-btn px-3 py-1.5 rounded-md text-xs font-medium text-zinc-600 dark:text-zinc-400 hover:bg-zinc-100 dark:hover:bg-zinc-800 transition cursor-pointer">Kreckle Foods</button>
                </div>
                <div class="relative sm:w-64">
                    <input type="text" id="sp-search-input" onkeyup="filterSalespersonsSearch()" placeholder="Search rep or phone..." class="w-full px-3 py-1.5 text-xs rounded-md bg-white dark:bg-zinc-900 border border-zinc-300 dark:border-zinc-700 text-zinc-900 dark:text-zinc-100 focus:outline-none focus:ring-1 focus:ring-zinc-950 dark:focus:ring-zinc-300">
                </div>
            </div>

            <div class="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-3 sm:gap-4" id="fleet-salesperson-cards"></div>
        </div>
        """
        payments_section_html = f"""
        <div id="fleet-section-payments" class="fleet-subview-panel rounded-xl border border-zinc-200 bg-white shadow-xs dark:border-zinc-800 dark:bg-zinc-950 overflow-hidden" style="display: none;">
            <div class="p-4 border-b border-zinc-200 dark:border-zinc-800 flex flex-col md:flex-row items-stretch md:items-center justify-between gap-3 bg-zinc-50/50 dark:bg-zinc-900/30">
                <div>
                    <h3 class="text-sm font-semibold text-zinc-900 dark:text-zinc-100">Payment History</h3>
                    <p class="text-xs text-zinc-500 dark:text-zinc-400">Accounting verification and payment offset audit history</p>
                </div>
                {rep_clear_btn}
            </div>

            <div id="payments-cards-list" class="block md:hidden divide-y divide-zinc-200 dark:divide-zinc-800"></div>

            <div class="hidden md:block overflow-x-auto">
                <table class="w-full text-left text-xs">
                    <thead class="bg-zinc-50/75 dark:bg-zinc-900/50 text-zinc-500 dark:text-zinc-400 font-medium uppercase tracking-wider border-b border-zinc-200 dark:border-zinc-800">
                        <tr>
                            <th class="px-4 py-3 whitespace-nowrap">Payment Date</th>
                            <th class="px-4 py-3 whitespace-nowrap">Sales Representative</th>
                            <th class="px-4 py-3 whitespace-nowrap">Amount Cleared</th>
                            <th class="px-4 py-3 whitespace-nowrap">Method & Reference</th>
                            <th class="px-4 py-3 whitespace-nowrap">Balance Impact</th>
                            <th class="px-4 py-3 whitespace-nowrap">Recorded By</th>
                            <th class="px-4 py-3 whitespace-nowrap">Remarks / Notes</th>
                        </tr>
                    </thead>
                    <tbody id="fleet-payments-table-body" class="divide-y divide-zinc-200 dark:divide-zinc-800 text-zinc-800 dark:text-zinc-200"></tbody>
                </table>
            </div>

            <div class="p-3.5 border-t border-zinc-200 dark:border-zinc-800 flex flex-col sm:flex-row items-center justify-between gap-3 bg-zinc-50/50 dark:bg-zinc-900/30">
                <div class="text-xs text-zinc-500 dark:text-zinc-400 font-medium" id="payments-pagination-info">Showing 0 entries</div>
                <div class="flex items-center gap-1.5" id="payments-pagination-controls"></div>
            </div>
        </div>
        """
        ledger_section_html = f"""
        <div id="fleet-section-ledger" class="fleet-subview-panel rounded-xl border border-zinc-200 bg-white shadow-xs dark:border-zinc-800 dark:bg-zinc-950 overflow-hidden" style="display: none;">
            <div class="p-4 border-b border-zinc-200 dark:border-zinc-800 bg-zinc-50/50 dark:bg-zinc-900/30">
                <div class="flex flex-col md:flex-row md:items-center justify-between gap-4">
                    <div>
                        <div class="inline-flex items-center gap-1.5 px-2 py-0.5 rounded text-[11px] font-medium bg-zinc-100 dark:bg-zinc-800 text-zinc-700 dark:text-zinc-300 mb-1">
                            Parity Guard
                        </div>
                        <h3 class="text-sm font-semibold text-zinc-900 dark:text-zinc-100">Financial Audit Log & Recovery Ledger</h3>
                        <p class="text-xs text-zinc-500 dark:text-zinc-400">Verifies system actions, rate edits, customer charges, debt records, and clearances</p>
                    </div>
                    <div class="flex items-center gap-2">
                        <span class="text-xs text-zinc-500">Period:</span>
                        <select id="ledger-timeframe-selector" onchange="setAuditTimeframe(this.value)" class="bg-white dark:bg-zinc-900 border border-zinc-300 dark:border-zinc-700 rounded-md px-2.5 py-1.5 text-xs text-zinc-800 dark:text-zinc-200">
                            <option value="all">All Time</option>
                            <option value="today">Today</option>
                            <option value="week">Last 7 Days</option>
                            <option value="month" selected>Last 30 Days</option>
                        </select>
                    </div>
                </div>
            </div>

            <div id="ledger-cards-list" class="block md:hidden divide-y divide-zinc-200 dark:divide-zinc-800"></div>

            <div class="hidden md:block overflow-x-auto">
                <table class="w-full text-left text-xs">
                    <thead id="fleet-ledger-table-head" class="bg-zinc-50/75 dark:bg-zinc-900/50 text-zinc-500 dark:text-zinc-400 font-medium uppercase tracking-wider border-b border-zinc-200 dark:border-zinc-800"></thead>
                    <tbody id="fleet-ledger-table-body" class="divide-y divide-zinc-200 dark:divide-zinc-800 text-zinc-800 dark:text-zinc-200"></tbody>
                </table>
            </div>

            <div class="p-3.5 border-t border-zinc-200 dark:border-zinc-800 flex flex-col sm:flex-row items-center justify-between gap-3 bg-zinc-50/50 dark:bg-zinc-900/30">
                <div class="text-xs text-zinc-500 dark:text-zinc-400 font-medium" id="ledger-pagination-info">Showing 0 entries</div>
                <div class="flex items-center gap-1.5" id="ledger-pagination-controls"></div>
            </div>
        </div>
        """
    else:
        salespersons_section_html = ""
        payments_section_html = ""
        ledger_section_html = ""

    if is_master_admin:
        analytics_section_html = f"""
        <div id="fleet-section-analytics" class="fleet-subview-panel space-y-6 transition-all duration-200" style="display: none;">
            <div class="rounded-xl border border-zinc-200/80 bg-white/75 backdrop-blur-md p-5 shadow-xs dark:border-zinc-800/80 dark:bg-zinc-950/75 flex flex-col sm:flex-row sm:items-center justify-between gap-4">
                <div>
                    <div class="flex items-center gap-2">
                        <span class="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-semibold border border-zinc-200 bg-zinc-100 text-zinc-800 dark:border-zinc-800 dark:bg-zinc-800 dark:text-zinc-200">Live Telemetry</span>
                    </div>
                    <h3 class="text-base font-bold text-zinc-900 dark:text-zinc-100 tracking-tight mt-1">Fleet Operations & Financial Analytics</h3>
                    <p class="text-xs text-zinc-500 dark:text-zinc-400 mt-0.5">Aggregated metrics calculated live across trip records, road expenses, debt recovery, and workshop operations.</p>
                </div>
                <button onclick="manualRefresh()" class="px-3 py-1.5 rounded-md text-xs font-medium border border-zinc-200/80 bg-white/80 hover:bg-zinc-100 dark:border-zinc-800/80 dark:bg-zinc-900/80 dark:hover:bg-zinc-800 text-zinc-800 dark:text-zinc-200 transition cursor-pointer self-start sm:self-auto flex items-center gap-1.5 shadow-xs">
                    <span id="analyticsRefreshIcon" class="inline-block">{icon_refresh}</span>
                    <span>Refresh Analytics</span>
                </button>
            </div>

            <div class="grid grid-cols-2 lg:grid-cols-4 gap-3 sm:gap-4">
                <div class="rounded-xl border border-zinc-200/80 bg-white/75 backdrop-blur-md p-4 sm:p-5 shadow-xs dark:border-zinc-800/80 dark:bg-zinc-950/75">
                    <div class="text-xs font-medium text-zinc-500 dark:text-zinc-400">Trip Volume & Completion</div>
                    <div class="text-2xl font-bold tracking-tight text-zinc-900 dark:text-zinc-100 mt-1 font-mono" id="an-stat-trips-total">0</div>
                    <div class="text-xs text-emerald-600 dark:text-emerald-400 font-medium mt-1" id="an-stat-trips-completed">0 completed</div>
                </div>
                <div class="rounded-xl border border-zinc-200/80 bg-white/75 backdrop-blur-md p-4 sm:p-5 shadow-xs dark:border-zinc-800/80 dark:bg-zinc-950/75">
                    <div class="text-xs font-medium text-zinc-500 dark:text-zinc-400">Route Compliance</div>
                    <div class="text-2xl font-bold tracking-tight text-emerald-600 dark:text-emerald-400 mt-1 font-mono" id="an-stat-compliance">100%</div>
                    <div class="text-xs text-zinc-500 dark:text-zinc-400 mt-1" id="an-stat-avg-opex">Avg Opex: $0.00</div>
                </div>
                <div class="rounded-xl border border-zinc-200/80 bg-white/75 backdrop-blur-md p-4 sm:p-5 shadow-xs dark:border-zinc-800/80 dark:bg-zinc-950/75">
                    <div class="text-xs font-medium text-zinc-500 dark:text-zinc-400">Fleet Utilization</div>
                    <div class="text-2xl font-bold tracking-tight text-zinc-900 dark:text-zinc-100 mt-1 font-mono" id="an-stat-utilization">0%</div>
                    <div class="text-xs text-zinc-500 dark:text-zinc-400 mt-1" id="an-stat-ws-impact">0 trucks in workshop</div>
                </div>
                <div class="rounded-xl border border-zinc-200/80 bg-white/75 backdrop-blur-md p-4 sm:p-5 shadow-xs dark:border-zinc-800/80 dark:bg-zinc-950/75">
                    <div class="text-xs font-medium text-zinc-500 dark:text-zinc-400">Shortfall Recovery Rate</div>
                    <div class="text-2xl font-bold tracking-tight text-emerald-600 dark:text-emerald-400 mt-1 font-mono" id="an-stat-recovery-rate">0%</div>
                    <div class="text-xs text-zinc-500 dark:text-zinc-400 mt-1" id="an-stat-recovery-sub">$0 recovered of $0</div>
                </div>
            </div>

            <div class="grid grid-cols-1 lg:grid-cols-2 gap-4 sm:gap-6">
                <div class="rounded-xl border border-zinc-200 bg-white p-5 shadow-xs dark:border-zinc-800 dark:bg-zinc-950 flex flex-col justify-between">
                    <div>
                        <div class="flex items-center justify-between mb-1">
                            <h4 class="text-sm font-semibold text-zinc-900 dark:text-zinc-100">Pipeline Stage Volume</h4>
                            <span class="text-[10px] font-mono px-2 py-0.5 rounded bg-zinc-100 dark:bg-zinc-800 text-zinc-600 dark:text-zinc-400 font-medium">Lifecycle</span>
                        </div>
                        <p class="text-xs text-zinc-500 dark:text-zinc-400 mb-3">Trips distributed across operational stages</p>
                        <div class="h-56 relative w-full mb-3">
                            <canvas id="an-pipeline-chart"></canvas>
                        </div>
                    </div>
                    <div class="space-y-2 pt-3 border-t border-zinc-100 dark:border-zinc-800" id="an-pipeline-bars"></div>
                </div>

                <div class="rounded-xl border border-zinc-200 bg-white p-5 shadow-xs dark:border-zinc-800 dark:bg-zinc-950 flex flex-col justify-between">
                    <div>
                        <div class="flex items-center justify-between mb-1">
                            <h4 class="text-sm font-semibold text-zinc-900 dark:text-zinc-100">Operational Cost Composition</h4>
                            <span class="text-[10px] font-mono px-2 py-0.5 rounded bg-zinc-100 dark:bg-zinc-800 text-zinc-600 dark:text-zinc-400 font-medium">OPEX Split</span>
                        </div>
                        <p class="text-xs text-zinc-500 dark:text-zinc-400 mb-3">Fuel, driver allowances, meals, accommodation & tolls</p>
                        <div class="h-56 relative w-full mb-3">
                            <canvas id="an-cost-donut-chart"></canvas>
                        </div>
                    </div>
                    <div class="space-y-2 pt-3 border-t border-zinc-100 dark:border-zinc-800" id="an-cost-bars"></div>
                </div>
            </div>

            <div class="grid grid-cols-1 lg:grid-cols-2 gap-4 sm:gap-6">
                <div class="rounded-xl border border-zinc-200 bg-white p-5 shadow-xs dark:border-zinc-800 dark:bg-zinc-950 flex flex-col justify-between">
                    <div>
                        <div class="flex items-center justify-between mb-1">
                            <h4 class="text-sm font-semibold text-zinc-900 dark:text-zinc-100">Top Corridors & City Traffic</h4>
                            <span class="text-[10px] font-mono px-2 py-0.5 rounded bg-zinc-100 dark:bg-zinc-800 text-zinc-600 dark:text-zinc-400 font-medium">Regional</span>
                        </div>
                        <p class="text-xs text-zinc-500 dark:text-zinc-400 mb-3">Trip volume across Zimbabwe commercial delivery routes</p>
                        <div class="h-56 relative w-full mb-3">
                            <canvas id="an-corridors-bar-chart"></canvas>
                        </div>
                    </div>
                    <div class="divide-y divide-zinc-100 dark:divide-zinc-850 pt-2 border-t border-zinc-100 dark:border-zinc-800" id="an-top-cities-list"></div>
                </div>

                <div class="rounded-xl border border-zinc-200 bg-white p-5 shadow-xs dark:border-zinc-800 dark:bg-zinc-950 flex flex-col justify-between">
                    <div>
                        <div class="flex items-center justify-between mb-1">
                            <h4 class="text-sm font-semibold text-zinc-900 dark:text-zinc-100">Financial Ledger & Recovery</h4>
                            <span class="text-[10px] font-mono px-2 py-0.5 rounded bg-zinc-100 dark:bg-zinc-800 text-zinc-600 dark:text-zinc-400 font-medium">Audit</span>
                        </div>
                        <p class="text-xs text-zinc-500 dark:text-zinc-400 mb-3">Settlement clearance comparison and deficit liquidity</p>
                        <div class="h-56 relative w-full mb-3">
                            <canvas id="an-financial-overview-chart"></canvas>
                        </div>
                        <div class="p-3 bg-zinc-50 dark:bg-zinc-900/60 rounded-lg border border-zinc-200/80 dark:border-zinc-800/80 flex items-center justify-between">
                            <div>
                                <div class="text-[10px] font-semibold uppercase text-zinc-500">Total Cleared Payments</div>
                                <div class="text-base font-bold font-mono text-emerald-600 dark:text-emerald-400 mt-0.5" id="an-cleared-total">$0.00</div>
                            </div>
                            <span class="text-xs text-zinc-500 font-mono">Bank Verified</span>
                        </div>
                    </div>
                </div>
            </div>
        </div>
        """
    else:
        analytics_section_html = ""

    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <title>Tagoneswa Operations Console</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.7/dist/chart.umd.min.js"></script>
    <script>
        tailwind.config = {{
            darkMode: 'class',
            theme: {{
                extend: {{
                    fontFamily: {{
                        sans: ['Plus Jakarta Sans', 'Inter', 'sans-serif'],
                        mono: ['JetBrains Mono', 'monospace'],
                    }},
                    colors: {{
                        border: 'hsl(var(--border))',
                        input: 'hsl(var(--input))',
                        ring: 'hsl(var(--ring))',
                        background: 'hsl(var(--background))',
                        foreground: 'hsl(var(--foreground))',
                    }},
                    borderRadius: {{
                        lg: 'var(--radius)',
                        md: 'calc(var(--radius) - 2px)',
                        sm: 'calc(var(--radius) - 4px)',
                    }}
                }}
            }}
        }};
        if (localStorage.getItem('tagoneswa_theme') === 'dark' || (!('tagoneswa_theme' in localStorage) && window.matchMedia('(prefers-color-scheme: dark)').matches)) {{
            document.documentElement.classList.add('dark');
        }} else {{
            document.documentElement.classList.remove('dark');
        }}
    </script>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&family=JetBrains+Mono:wght@500;700&display=swap" rel="stylesheet">
    <style>
        :root {{
            --background: 0 0% 100%;
            --foreground: 240 10% 3.9%;
            --card: 0 0% 100%;
            --card-foreground: 240 10% 3.9%;
            --muted: 240 4.8% 95.9%;
            --muted-foreground: 240 3.8% 46.1%;
            --border: 240 5.9% 90%;
            --input: 240 5.9% 90%;
            --radius: 0.625rem;
        }}
        .dark {{
            --background: 240 10% 3.9%;
            --foreground: 0 0% 98%;
            --card: 240 10% 3.9%;
            --card-foreground: 0 0% 98%;
            --muted: 240 3.7% 15.9%;
            --muted-foreground: 240 5% 64.9%;
            --border: 240 3.7% 15.9%;
            --input: 240 3.7% 15.9%;
        }}
        body {{ font-family: 'Plus Jakarta Sans', sans-serif; }}
        .font-mono {{ font-family: 'JetBrains Mono', monospace; }}
        .tab-btn.active {{
            background-color: #ffffff !important;
            color: #09090b !important;
            box-shadow: 0 1px 3px 0 rgba(0, 0, 0, 0.1), 0 1px 2px -1px rgba(0, 0, 0, 0.1) !important;
        }}
        html.dark .tab-btn.active {{
            background-color: #18181b !important;
            color: #fafafa !important;
            box-shadow: 0 1px 3px 0 rgba(0, 0, 0, 0.4) !important;
        }}
        .domain-view {{ display: none; }}
        .domain-view.active {{ display: block; }}
        .no-scrollbar::-webkit-scrollbar {{ display: none; }}
        .no-scrollbar {{ -ms-overflow-style: none; scrollbar-width: none; }}
        @keyframes spinFast {{
            0% {{ transform: rotate(0deg); }}
            100% {{ transform: rotate(360deg); }}
        }}
        .spinning {{
            animation: spinFast 0.6s linear infinite;
        }}
        body.modal-open {{
            overflow: hidden !important;
            height: 100vh !important;
        }}
        .modal-overlay {{
            overscroll-behavior: contain;
        }}
        .modal-card {{
            overscroll-behavior: contain;
        }}
    </style>
</head>
<body class="bg-zinc-50/50 dark:bg-zinc-950 text-zinc-900 dark:text-zinc-100 min-h-screen transition-colors duration-150">
    <!-- Sliding Sidebar Backdrop -->
    <div id="sidebar-backdrop" onclick="toggleSidebar(false)" class="fixed inset-0 bg-zinc-950/40 backdrop-blur-xs z-40 hidden transition-opacity duration-200"></div>

    <!-- Sliding Sidebar Navigation Menu -->
    <aside id="sliding-sidebar" class="fixed top-0 left-0 bottom-0 w-64 bg-white dark:bg-zinc-950 border-r border-zinc-200 dark:border-zinc-800 z-50 transform -translate-x-full transition-transform duration-200 ease-in-out shadow-xl flex flex-col">
        <!-- Sidebar Brand Header -->
        <div class="h-16 px-4 border-b border-zinc-200 dark:border-zinc-800 flex items-center justify-between">
            <div class="flex items-center gap-2.5">
                <div class="w-8 h-8 rounded-lg bg-zinc-900 text-zinc-50 dark:bg-zinc-50 dark:text-zinc-900 flex items-center justify-center font-bold text-sm tracking-tight shadow-xs">
                    T
                </div>
                <div>
                    <h3 class="text-sm font-semibold text-zinc-900 dark:text-zinc-100 tracking-tight leading-none">Tagoneswa</h3>
                    <p class="text-[11px] text-zinc-500 dark:text-zinc-400 font-normal mt-0.5">Operations Portal</p>
                </div>
            </div>
            <button onclick="toggleSidebar(false)" class="p-1.5 rounded-md text-zinc-400 hover:text-zinc-600 dark:hover:text-zinc-200 hover:bg-zinc-100 dark:hover:bg-zinc-800 transition cursor-pointer" title="Close Menu">
                {icon_close}
            </button>
        </div>

        <!-- User Profile Pill in Sidebar -->
        <div class="p-3 mx-3 mt-3 bg-zinc-50 dark:bg-zinc-900/60 border border-zinc-200/80 dark:border-zinc-800/80 rounded-xl flex items-center gap-2.5">
            <div class="w-8 h-8 rounded-full bg-zinc-200 dark:bg-zinc-800 text-zinc-800 dark:text-zinc-200 font-semibold text-xs flex items-center justify-center shrink-0">
                {user_name[:2].upper()}
            </div>
            <div class="min-w-0 flex-1">
                <div class="text-xs font-semibold text-zinc-900 dark:text-zinc-100 truncate">{user_name}</div>
                <div class="text-[10px] text-zinc-500 dark:text-zinc-400 flex items-center gap-1">
                    <span class="w-1.5 h-1.5 rounded-full bg-emerald-500"></span>
                    <span class="truncate">{user_role.replace('_', ' ')}</span>
                </div>
            </div>
        </div>

        <!-- Navigation Links (Dynamic by Role) -->
        <nav id="sidebar-nav-container" class="flex-1 overflow-y-auto p-3 space-y-1 no-scrollbar">
            {sidebar_markup}
        </nav>

        <!-- Sidebar Footer -->
        <div class="p-3 border-t border-zinc-200 dark:border-zinc-800 flex items-center justify-between text-xs text-zinc-500 dark:text-zinc-400">
            <span class="font-mono text-[11px]">v2.5.0</span>
            <button onclick="handleLogout()" class="text-xs font-medium text-rose-600 dark:text-rose-400 hover:underline cursor-pointer">Logout</button>
        </div>
    </aside>

    <!-- Toast Notification -->
    <div id="toast" class="fixed bottom-5 right-5 z-50 transform translate-y-20 opacity-0 transition-all duration-200 pointer-events-none bg-zinc-900 dark:bg-zinc-100 text-zinc-50 dark:text-zinc-900 px-4 py-2.5 rounded-lg shadow-lg border border-zinc-800 dark:border-zinc-200 text-xs font-medium flex items-center gap-2">
        <span id="toastIcon">{icon_check}</span>
        <span id="toastMsg">Live data updated</span>
    </div>

    <!-- Top Sticky Header with Liquid Glass styling -->
    <header class="bg-white/80 dark:bg-zinc-950/80 backdrop-blur-md border-b border-zinc-200/80 dark:border-zinc-800/80 sticky top-0 z-30 transition-colors">
        <div class="w-full max-w-[1780px] mx-auto px-4 sm:px-6 lg:px-8 py-2.5 sm:py-3">
            <div class="flex flex-col md:flex-row items-center justify-between gap-3">
                <!-- Top Row: Brand & Mobile Actions -->
                <div class="flex items-center justify-between w-full md:w-auto gap-3">
                    <div class="flex items-center gap-3">
                        <button onclick="toggleSidebar(true)" class="p-2 rounded-lg text-zinc-600 dark:text-zinc-300 hover:bg-zinc-100 dark:hover:bg-zinc-800 transition border border-zinc-200 dark:border-zinc-800 cursor-pointer flex items-center justify-center text-sm" title="Toggle Navigation Menu">
                            {icon_menu}
                        </button>
                        <div class="flex items-center gap-2 text-xs">
                            <span class="font-semibold text-zinc-900 dark:text-zinc-100">Tagoneswa</span>
                            <span class="text-zinc-400 dark:text-zinc-600">/</span>
                            <span class="text-zinc-500 dark:text-zinc-400">Operations</span>
                            <span class="text-zinc-400 dark:text-zinc-600">/</span>
                            <span id="current-domain-breadcrumb" class="font-medium text-zinc-900 dark:text-zinc-100">Sales to Fleet</span>
                        </div>
                    </div>

                    <!-- Right Controls for Mobile Screen -->
                    <div class="flex items-center gap-1.5 md:hidden">
                        <button onclick="toggleTheme()" class="p-2 rounded-lg text-zinc-600 dark:text-zinc-300 hover:bg-zinc-100 dark:hover:bg-zinc-800 border border-zinc-200 dark:border-zinc-800 transition cursor-pointer" title="Toggle Theme">
                            <span class="theme-toggle-icon">{icon_moon}</span>
                        </button>
                        <button onclick="manualRefresh()" id="mobileRefreshBtn" class="p-2 rounded-lg text-zinc-600 dark:text-zinc-300 hover:bg-zinc-100 dark:hover:bg-zinc-800 border border-zinc-200 dark:border-zinc-800 transition cursor-pointer" title="Refresh Live Data">
                            <span id="mobileRefreshIcon" class="inline-block">{icon_refresh}</span>
                        </button>
                        <button onclick="handleLogout()" class="px-2.5 py-1.5 rounded-lg text-xs font-medium text-rose-600 hover:bg-rose-50 dark:hover:bg-rose-950/40 border border-zinc-200 dark:border-zinc-800 transition cursor-pointer">
                            Log Out
                        </button>
                    </div>
                </div>

                <!-- Domain Switcher (Segmented Tabs) -->
                <nav class="flex bg-zinc-100/90 dark:bg-zinc-900/90 backdrop-blur-xs p-1 rounded-lg border border-zinc-200/80 dark:border-zinc-800/80 gap-1 w-full md:w-auto overflow-x-auto justify-start sm:justify-center no-scrollbar">
                    {nav_tabs_markup}
                </nav>

                <!-- Desktop Utility Controls -->
                <div class="hidden md:flex items-center gap-2.5">
                    <div class="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs font-medium bg-emerald-50 text-emerald-700 border border-emerald-200 dark:bg-emerald-950/40 dark:text-emerald-300 dark:border-emerald-800/60">
                        <span class="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse"></span>
                        <span class="font-mono text-[11px]">Live Sync</span>
                    </div>

                    <button onclick="toggleTheme()" class="theme-toggle-btn px-2.5 py-1.5 rounded-md text-xs font-medium text-zinc-700 dark:text-zinc-300 hover:bg-zinc-100 dark:hover:bg-zinc-800 border border-zinc-200 dark:border-zinc-800 transition flex items-center gap-1.5 cursor-pointer" title="Toggle Dark / Light Theme">
                        <span class="theme-toggle-icon">{icon_moon}</span>
                        <span class="theme-toggle-label">Dark</span>
                    </button>

                    <button onclick="manualRefresh()" id="desktopRefreshBtn" class="px-3 py-1.5 rounded-md text-xs font-medium text-zinc-700 dark:text-zinc-300 hover:bg-zinc-100 dark:hover:bg-zinc-800 border border-zinc-200 dark:border-zinc-800 transition flex items-center gap-1.5 cursor-pointer" title="Refresh Live Data">
                        <span id="desktopRefreshIcon" class="inline-block">{icon_refresh}</span>
                        <span id="desktopRefreshLabel">Refresh</span>
                    </button>

                    <div class="text-right pl-2 border-l border-zinc-200 dark:border-zinc-800">
                        <div class="text-xs font-semibold text-zinc-900 dark:text-zinc-100 leading-tight" id="userDisplayName">{user["name"]}</div>
                        <div class="text-[10px] text-zinc-500 dark:text-zinc-400 mt-0.5" id="userRoleBadge">{user["role"].replace("_", " ")}</div>
                    </div>

                    <button onclick="handleLogout()" class="px-3 py-1.5 rounded-md text-xs font-medium text-rose-600 hover:bg-rose-50 dark:hover:bg-rose-950/40 border border-zinc-200 dark:border-zinc-800 transition cursor-pointer">
                        Log Out
                    </button>
                </div>
            </div>
        </div>
    </header>

    <!-- Main Content Container -->
    <main class="w-full max-w-[1780px] mx-auto px-4 sm:px-6 lg:px-8 py-6 space-y-6">

        <!-- ========================================================= -->
        <!-- TAB 1: IT SUPPORT -->
        <!-- ========================================================= -->
        <div id="view-it" class="domain-view space-y-6" style="display: {'block' if 'it' in allowed and default_tab == 'it' else 'none'}">
            <div class="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
                <div>
                    <h2 class="text-xl font-bold tracking-tight text-zinc-900 dark:text-zinc-100">IT Helpdesk Support</h2>
                    <p class="text-xs text-zinc-500 dark:text-zinc-400">Technical issues, hardware maintenance, and WhatsApp diagnostics</p>
                </div>
            </div>

            <!-- IT Metric Cards -->
            <div class="grid grid-cols-2 lg:grid-cols-4 gap-3 sm:gap-4">
                <div class="rounded-xl border border-zinc-200/80 bg-white/75 backdrop-blur-md p-5 shadow-xs dark:border-zinc-800/80 dark:bg-zinc-950/75">
                    <div class="flex items-center justify-between text-xs font-medium text-zinc-500 dark:text-zinc-400">
                        <span>Total Tickets</span>
                        <span>{icon_clipboard}</span>
                    </div>
                    <div class="text-2xl font-bold tracking-tight text-zinc-900 dark:text-zinc-100 mt-2 font-mono" id="it-stat-total">0</div>
                    <div class="text-xs text-zinc-500 dark:text-zinc-400 mt-1">Logged tickets across branches</div>
                </div>
                <div class="rounded-xl border border-zinc-200/80 bg-white/75 backdrop-blur-md p-5 shadow-xs dark:border-zinc-800/80 dark:bg-zinc-950/75">
                    <div class="flex items-center justify-between text-xs font-medium text-zinc-500 dark:text-zinc-400">
                        <span>Open & Active</span>
                        <span>{icon_clock}</span>
                    </div>
                    <div class="text-2xl font-bold tracking-tight text-amber-600 dark:text-amber-400 mt-2 font-mono" id="it-stat-active">0</div>
                    <div class="text-xs text-zinc-500 dark:text-zinc-400 mt-1">Requiring technician triage</div>
                </div>
                <div class="rounded-xl border border-zinc-200/80 bg-white/75 backdrop-blur-md p-5 shadow-xs dark:border-zinc-800/80 dark:bg-zinc-950/75">
                    <div class="flex items-center justify-between text-xs font-medium text-zinc-500 dark:text-zinc-400">
                        <span>Resolved Tickets</span>
                        <span>{icon_check}</span>
                    </div>
                    <div class="text-2xl font-bold tracking-tight text-emerald-600 dark:text-emerald-400 mt-2 font-mono" id="it-stat-resolved">0</div>
                    <div class="text-xs text-zinc-500 dark:text-zinc-400 mt-1">Solved and verified</div>
                </div>
                <div class="rounded-xl border border-zinc-200/80 bg-white/75 backdrop-blur-md p-5 shadow-xs dark:border-zinc-800/80 dark:bg-zinc-950/75">
                    <div class="flex items-center justify-between text-xs font-medium text-zinc-500 dark:text-zinc-400">
                        <span>Average Resolution Time</span>
                        <span>{icon_timer}</span>
                    </div>
                    <div class="text-2xl font-bold tracking-tight text-zinc-900 dark:text-zinc-100 mt-2 font-mono" id="it-stat-avg-time">--</div>
                    <div class="text-xs text-zinc-500 dark:text-zinc-400 mt-1">SLA turnaround pace</div>
                </div>
            </div>

            <!-- IT Technician SLA Performance -->
            <div class="rounded-xl border border-zinc-200 bg-white p-5 shadow-xs dark:border-zinc-800 dark:bg-zinc-950">
                <div class="flex flex-col sm:flex-row sm:items-center justify-between mb-4 gap-2">
                    <div>
                        <h3 class="text-sm font-semibold text-zinc-900 dark:text-zinc-100">Technician Workload & SLA Performance</h3>
                        <p class="text-xs text-zinc-500 dark:text-zinc-400 mt-0.5">Click any technician card to filter their assigned tickets</p>
                    </div>
                    <button onclick="filterByITAdmin('ALL')" class="text-xs font-medium text-zinc-600 dark:text-zinc-400 hover:text-zinc-900 dark:hover:text-zinc-100 border border-zinc-200 dark:border-zinc-800 px-2.5 py-1 rounded-md transition cursor-pointer self-start sm:self-auto">
                        View All Admins
                    </button>
                </div>
                <div class="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-3" id="it-admin-cards"></div>
            </div>

            <!-- IT Tickets Data Table Card -->
            <div id="it-table-card" class="rounded-xl border border-zinc-200 bg-white shadow-xs dark:border-zinc-800 dark:bg-zinc-950 overflow-hidden">
                <!-- Filters & Controls Bar -->
                <div class="p-4 border-b border-zinc-200 dark:border-zinc-800 flex flex-col md:flex-row items-stretch md:items-center justify-between gap-3 bg-zinc-50/50 dark:bg-zinc-900/30">
                    <div class="flex flex-col sm:flex-row flex-wrap items-stretch sm:items-center gap-2 sm:gap-3 w-full md:w-auto">
                        <input type="text" id="it-search" placeholder="Search ticket #, employee, issue..." oninput="filterITTable(true)" class="bg-white dark:bg-zinc-900 border border-zinc-300 dark:border-zinc-700 rounded-md px-3 py-1.5 text-xs text-zinc-900 dark:text-zinc-100 placeholder-zinc-400 focus:outline-none focus:ring-1 focus:ring-zinc-950 dark:focus:ring-zinc-300 w-full sm:w-64 transition">
                        
                        <select id="it-admin-filter" onchange="filterITTable(true)" class="bg-white dark:bg-zinc-900 border border-zinc-300 dark:border-zinc-700 rounded-md px-2.5 py-1.5 text-xs text-zinc-800 dark:text-zinc-200 focus:outline-none focus:ring-1 focus:ring-zinc-950 dark:focus:ring-zinc-300 transition">
                            <option value="ALL">All Support Admins</option>
                        </select>

                        <select id="it-status-filter" onchange="filterITTable(true)" class="bg-white dark:bg-zinc-900 border border-zinc-300 dark:border-zinc-700 rounded-md px-2.5 py-1.5 text-xs text-zinc-800 dark:text-zinc-200 focus:outline-none focus:ring-1 focus:ring-zinc-950 dark:focus:ring-zinc-300 transition">
                            <option value="ALL">All Statuses</option>
                            <option value="Open">Open</option>
                            <option value="In Progress">In Progress</option>
                            <option value="Resolved">Resolved</option>
                            <option value="Closed">Closed</option>
                        </select>
                    </div>

                    <div class="flex items-center justify-between sm:justify-end gap-2">
                        <span id="it-count-badge" class="inline-flex items-center px-2.5 py-1 rounded-md text-xs font-medium border border-zinc-200 bg-zinc-100 text-zinc-800 dark:border-zinc-800 dark:bg-zinc-800 dark:text-zinc-200">
                            Showing 0 tickets
                        </span>
                    </div>
                </div>

                <!-- Responsive Mobile Card List -->
                <div id="it-cards-list" class="block md:hidden divide-y divide-zinc-200 dark:divide-zinc-800"></div>

                <!-- Desktop Multi-Column Table -->
                <div class="hidden md:block overflow-x-auto">
                    <table class="w-full text-left text-xs">
                        <thead class="bg-zinc-50/75 dark:bg-zinc-900/50 text-zinc-500 dark:text-zinc-400 font-medium uppercase tracking-wider border-b border-zinc-200 dark:border-zinc-800">
                            <tr>
                                <th class="px-4 py-3 whitespace-nowrap">Ticket #</th>
                                <th class="px-4 py-3 whitespace-nowrap">Employee</th>
                                <th class="px-4 py-3 whitespace-nowrap">Department & Location</th>
                                <th class="px-4 py-3 whitespace-nowrap">Category & Issue</th>
                                <th class="px-4 py-3 whitespace-nowrap">Priority</th>
                                <th class="px-4 py-3 whitespace-nowrap">Status</th>
                                <th class="px-4 py-3 whitespace-nowrap">Assigned Admin</th>
                                <th class="px-4 py-3 whitespace-nowrap">Solving Time</th>
                            </tr>
                        </thead>
                        <tbody id="it-table-body" class="divide-y divide-zinc-200 dark:divide-zinc-800 text-zinc-800 dark:text-zinc-200">
                            <!-- Skeleton Row Placeholders -->
                            <tr class="animate-pulse">
                                <td class="px-4 py-3"><div class="h-4 bg-zinc-200 dark:bg-zinc-800 rounded w-16"></div></td>
                                <td class="px-4 py-3"><div class="h-4 bg-zinc-200 dark:bg-zinc-800 rounded w-28"></div></td>
                                <td class="px-4 py-3"><div class="h-4 bg-zinc-200 dark:bg-zinc-800 rounded w-36"></div></td>
                                <td class="px-4 py-3"><div class="h-4 bg-zinc-200 dark:bg-zinc-800 rounded w-44"></div></td>
                                <td class="px-4 py-3"><div class="h-4 bg-zinc-200 dark:bg-zinc-800 rounded w-16"></div></td>
                                <td class="px-4 py-3"><div class="h-4 bg-zinc-200 dark:bg-zinc-800 rounded w-20"></div></td>
                                <td class="px-4 py-3"><div class="h-4 bg-zinc-200 dark:bg-zinc-800 rounded w-24"></div></td>
                                <td class="px-4 py-3"><div class="h-4 bg-zinc-200 dark:bg-zinc-800 rounded w-16"></div></td>
                            </tr>
                        </tbody>
                    </table>
                </div>

                <!-- Pagination Footer -->
                <div class="p-3.5 border-t border-zinc-200 dark:border-zinc-800 flex flex-col sm:flex-row items-center justify-between gap-3 bg-zinc-50/50 dark:bg-zinc-900/30">
                    <div class="text-xs text-zinc-500 dark:text-zinc-400 font-medium" id="it-pagination-info">Showing 0 entries</div>
                    <div class="flex items-center gap-1.5" id="it-pagination-controls"></div>
                </div>
            </div>

            <!-- Category Breakdown Tree -->
            <div class="rounded-xl border border-zinc-200 bg-white p-5 shadow-xs dark:border-zinc-800 dark:bg-zinc-950">
                <div class="flex flex-col sm:flex-row sm:items-center justify-between mb-4 gap-1">
                    <h3 class="text-sm font-semibold text-zinc-900 dark:text-zinc-100">Category & Issue Breakdown</h3>
                    <span class="text-xs text-zinc-500 dark:text-zinc-400">Reported Fault Occurrences</span>
                </div>
                <div id="it-category-tree" class="space-y-3"></div>
            </div>
        </div>

        <!-- ========================================================= -->
        <!-- TAB 2: BUILDING PROJECTS -->
        <!-- ========================================================= -->
        <div id="view-projects" class="domain-view space-y-6" style="display: {'block' if 'projects' in allowed and default_tab == 'projects' else 'none'}">
            <div class="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
                <div>
                    <h2 class="text-xl font-bold tracking-tight text-zinc-900 dark:text-zinc-100">Building & Facilities Projects</h2>
                    <p class="text-xs text-zinc-500 dark:text-zinc-400">Construction, renovation, branch work orders, and site materials</p>
                </div>
            </div>

            <!-- Projects Stats -->
            <div class="grid grid-cols-2 lg:grid-cols-4 gap-3 sm:gap-4">
                <div class="rounded-xl border border-zinc-200/80 bg-white/75 backdrop-blur-md p-5 shadow-xs dark:border-zinc-800/80 dark:bg-zinc-950/75">
                    <div class="flex items-center justify-between text-xs font-medium text-zinc-500 dark:text-zinc-400">
                        <span>Total Project Tickets</span>
                        <span>{icon_hardhat}</span>
                    </div>
                    <div class="text-2xl font-bold tracking-tight text-zinc-900 dark:text-zinc-100 mt-2 font-mono" id="proj-stat-total">0</div>
                    <div class="text-xs text-zinc-500 dark:text-zinc-400 mt-1">Building & facility jobs</div>
                </div>
                <div class="rounded-xl border border-zinc-200/80 bg-white/75 backdrop-blur-md p-5 shadow-xs dark:border-zinc-800/80 dark:bg-zinc-950/75">
                    <div class="flex items-center justify-between text-xs font-medium text-zinc-500 dark:text-zinc-400">
                        <span>Active Work Orders</span>
                        <span>{icon_hammer}</span>
                    </div>
                    <div class="text-2xl font-bold tracking-tight text-amber-600 dark:text-amber-400 mt-2 font-mono" id="proj-stat-active">0</div>
                    <div class="text-xs text-zinc-500 dark:text-zinc-400 mt-1">In progress on site</div>
                </div>
                <div class="rounded-xl border border-zinc-200/80 bg-white/75 backdrop-blur-md p-5 shadow-xs dark:border-zinc-800/80 dark:bg-zinc-950/75">
                    <div class="flex items-center justify-between text-xs font-medium text-zinc-500 dark:text-zinc-400">
                        <span>Completed Facilities</span>
                        <span>{icon_building}</span>
                    </div>
                    <div class="text-2xl font-bold tracking-tight text-emerald-600 dark:text-emerald-400 mt-2 font-mono" id="proj-stat-completed">0</div>
                    <div class="text-xs text-zinc-500 dark:text-zinc-400 mt-1">Signed off & inspected</div>
                </div>
                <div class="rounded-xl border border-zinc-200/80 bg-white/75 backdrop-blur-md p-5 shadow-xs dark:border-zinc-800/80 dark:bg-zinc-950/75">
                    <div class="flex items-center justify-between text-xs font-medium text-zinc-500 dark:text-zinc-400">
                        <span>Active Branches & Yards</span>
                        <span>{icon_map_pin}</span>
                    </div>
                    <div class="text-2xl font-bold tracking-tight text-zinc-900 dark:text-zinc-100 mt-2 font-mono" id="proj-stat-locations">0</div>
                    <div class="text-xs text-zinc-500 dark:text-zinc-400 mt-1">Serviced commercial locations</div>
                </div>
            </div>

            <!-- Projects Table Card -->
            <div class="rounded-xl border border-zinc-200 bg-white shadow-xs dark:border-zinc-800 dark:bg-zinc-950 overflow-hidden">
                <div class="p-4 border-b border-zinc-200 dark:border-zinc-800 flex flex-col md:flex-row items-stretch md:items-center justify-between gap-3 bg-zinc-50/50 dark:bg-zinc-900/30">
                    <div class="flex flex-col sm:flex-row flex-wrap items-stretch sm:items-center gap-2 sm:gap-3 w-full md:w-auto">
                        <input type="text" id="proj-search" placeholder="Search site, ticket #, repair..." oninput="filterProjectsTable(true)" class="bg-white dark:bg-zinc-900 border border-zinc-300 dark:border-zinc-700 rounded-md px-3 py-1.5 text-xs text-zinc-900 dark:text-zinc-100 placeholder-zinc-400 focus:outline-none focus:ring-1 focus:ring-zinc-950 dark:focus:ring-zinc-300 w-full sm:w-64 transition">
                        
                        <select id="proj-loc-filter" onchange="filterProjectsTable(true)" class="bg-white dark:bg-zinc-900 border border-zinc-300 dark:border-zinc-700 rounded-md px-2.5 py-1.5 text-xs text-zinc-800 dark:text-zinc-200 focus:outline-none focus:ring-1 focus:ring-zinc-950 dark:focus:ring-zinc-300 transition">
                            <option value="ALL">All Branches & Yards</option>
                        </select>

                        <select id="proj-admin-filter" onchange="filterProjectsTable(true)" class="bg-white dark:bg-zinc-900 border border-zinc-300 dark:border-zinc-700 rounded-md px-2.5 py-1.5 text-xs text-zinc-800 dark:text-zinc-200 focus:outline-none focus:ring-1 focus:ring-zinc-950 dark:focus:ring-zinc-300 transition">
                            <option value="ALL">All Project Leads</option>
                        </select>

                        <select id="proj-status-filter" onchange="filterProjectsTable(true)" class="bg-white dark:bg-zinc-900 border border-zinc-300 dark:border-zinc-700 rounded-md px-2.5 py-1.5 text-xs text-zinc-800 dark:text-zinc-200 focus:outline-none focus:ring-1 focus:ring-zinc-950 dark:focus:ring-zinc-300 transition">
                            <option value="ALL">All Statuses</option>
                            <option value="Open">Open</option>
                            <option value="In Progress">In Progress</option>
                            <option value="Closed">Closed</option>
                        </select>
                    </div>

                    <div class="flex items-center justify-between sm:justify-end gap-2">
                        <span id="proj-count-badge" class="inline-flex items-center px-2.5 py-1 rounded-md text-xs font-medium border border-zinc-200 bg-zinc-100 text-zinc-800 dark:border-zinc-800 dark:bg-zinc-800 dark:text-zinc-200">
                            Showing 0 tickets
                        </span>
                    </div>
                </div>

                <!-- Responsive Mobile Card List -->
                <div id="proj-cards-list" class="block md:hidden divide-y divide-zinc-200 dark:divide-zinc-800"></div>

                <!-- Desktop Table -->
                <div class="hidden md:block overflow-x-auto">
                    <table class="w-full text-left text-xs">
                        <thead class="bg-zinc-50/75 dark:bg-zinc-900/50 text-zinc-500 dark:text-zinc-400 font-medium uppercase tracking-wider border-b border-zinc-200 dark:border-zinc-800">
                            <tr>
                                <th class="px-4 py-3 whitespace-nowrap">Ticket #</th>
                                <th class="px-4 py-3 whitespace-nowrap">Reporter</th>
                                <th class="px-4 py-3 whitespace-nowrap">Site / Branch Location</th>
                                <th class="px-4 py-3 whitespace-nowrap">Category & Description</th>
                                <th class="px-4 py-3 whitespace-nowrap">Status</th>
                                <th class="px-4 py-3 whitespace-nowrap">Assigned Lead</th>
                                <th class="px-4 py-3 whitespace-nowrap">Date Created</th>
                            </tr>
                        </thead>
                        <tbody id="proj-table-body" class="divide-y divide-zinc-200 dark:divide-zinc-800 text-zinc-800 dark:text-zinc-200">
                            <tr class="animate-pulse">
                                <td class="px-4 py-3"><div class="h-4 bg-zinc-200 dark:bg-zinc-800 rounded w-16"></div></td>
                                <td class="px-4 py-3"><div class="h-4 bg-zinc-200 dark:bg-zinc-800 rounded w-28"></div></td>
                                <td class="px-4 py-3"><div class="h-4 bg-zinc-200 dark:bg-zinc-800 rounded w-36"></div></td>
                                <td class="px-4 py-3"><div class="h-4 bg-zinc-200 dark:bg-zinc-800 rounded w-44"></div></td>
                                <td class="px-4 py-3"><div class="h-4 bg-zinc-200 dark:bg-zinc-800 rounded w-20"></div></td>
                                <td class="px-4 py-3"><div class="h-4 bg-zinc-200 dark:bg-zinc-800 rounded w-24"></div></td>
                                <td class="px-4 py-3"><div class="h-4 bg-zinc-200 dark:bg-zinc-800 rounded w-20"></div></td>
                            </tr>
                        </tbody>
                    </table>
                </div>

                <!-- Pagination Footer -->
                <div class="p-3.5 border-t border-zinc-200 dark:border-zinc-800 flex flex-col sm:flex-row items-center justify-between gap-3 bg-zinc-50/50 dark:bg-zinc-900/30">
                    <div class="text-xs text-zinc-500 dark:text-zinc-400 font-medium" id="proj-pagination-info">Showing 0 entries</div>
                    <div class="flex items-center gap-1.5" id="proj-pagination-controls"></div>
                </div>
            </div>
        </div>

        <!-- ========================================================= -->
        <!-- TAB 3: WORKSHOP & FLEET LOGISTICS -->
        <!-- ========================================================= -->
        <div id="view-logistics" class="domain-view space-y-6" style="display: {'block' if 'logistics' in allowed and default_tab == 'logistics' else 'none'}">
            <div class="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
                <div>
                    <h2 class="text-xl font-bold tracking-tight text-zinc-900 dark:text-zinc-100">Workshop & Maintenance Fleet</h2>
                    <p class="text-xs text-zinc-500 dark:text-zinc-400">Truck repairs, spare parts requisition, mechanic logs, and road-worthiness inspections</p>
                </div>
            </div>

            <!-- Fleet Stats -->
            <div class="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3 sm:gap-4">
                <div class="rounded-xl border border-zinc-200/80 bg-white/75 backdrop-blur-md p-5 shadow-xs dark:border-zinc-800/80 dark:bg-zinc-950/75">
                    <div class="flex items-center justify-between text-xs font-medium text-zinc-500 dark:text-zinc-400">
                        <span>Active Fleet</span>
                        <span>{icon_truck}</span>
                    </div>
                    <div class="text-2xl font-bold tracking-tight text-zinc-900 dark:text-zinc-100 mt-2 font-mono" id="ws-stat-fleet">39</div>
                    <div class="text-xs text-zinc-500 dark:text-zinc-400 mt-1">Trucks registered</div>
                </div>
                <div class="rounded-xl border border-zinc-200/80 bg-white/75 backdrop-blur-md p-5 shadow-xs dark:border-zinc-800/80 dark:bg-zinc-950/75">
                    <div class="flex items-center justify-between text-xs font-medium text-zinc-500 dark:text-zinc-400">
                        <span>Pending Review</span>
                        <span>{icon_clipboard}</span>
                    </div>
                    <div class="text-2xl font-bold tracking-tight text-amber-600 dark:text-amber-400 mt-2 font-mono" id="ws-stat-review">0</div>
                    <div class="text-xs text-zinc-500 dark:text-zinc-400 mt-1">Supervisor triage</div>
                </div>
                <div class="rounded-xl border border-zinc-200/80 bg-white/75 backdrop-blur-md p-5 shadow-xs dark:border-zinc-800/80 dark:bg-zinc-950/75">
                    <div class="flex items-center justify-between text-xs font-medium text-zinc-500 dark:text-zinc-400">
                        <span>In Workshop</span>
                        <span>{icon_wrench}</span>
                    </div>
                    <div class="text-2xl font-bold tracking-tight text-zinc-900 dark:text-zinc-100 mt-2 font-mono" id="ws-stat-floor">0</div>
                    <div class="text-xs text-zinc-500 dark:text-zinc-400 mt-1">Mechanical repairs</div>
                </div>
                <div class="rounded-xl border border-zinc-200/80 bg-white/75 backdrop-blur-md p-5 shadow-xs dark:border-zinc-800/80 dark:bg-zinc-950/75">
                    <div class="flex items-center justify-between text-xs font-medium text-zinc-500 dark:text-zinc-400">
                        <span>Awaiting Spares</span>
                        <span>{icon_gear}</span>
                    </div>
                    <div class="text-2xl font-bold tracking-tight text-rose-600 dark:text-rose-400 mt-2 font-mono" id="ws-stat-parts">0</div>
                    <div class="text-xs text-zinc-500 dark:text-zinc-400 mt-1">Parts requisition</div>
                </div>
                <div class="rounded-xl border border-zinc-200/80 bg-white/75 backdrop-blur-md p-5 shadow-xs dark:border-zinc-800/80 dark:bg-zinc-950/75 col-span-2 sm:col-span-1">
                    <div class="flex items-center justify-between text-xs font-medium text-zinc-500 dark:text-zinc-400">
                        <span>Quality Inspection</span>
                        <span>{icon_traffic}</span>
                    </div>
                    <div class="text-2xl font-bold tracking-tight text-emerald-600 dark:text-emerald-400 mt-2 font-mono" id="ws-stat-qc">0</div>
                    <div class="text-xs text-zinc-500 dark:text-zinc-400 mt-1">Road-test sign-off</div>
                </div>
            </div>

            <!-- Fleet Table Card -->
            <div class="rounded-xl border border-zinc-200 bg-white shadow-xs dark:border-zinc-800 dark:bg-zinc-950 overflow-hidden">
                <div class="p-4 border-b border-zinc-200 dark:border-zinc-800 flex flex-col md:flex-row items-stretch md:items-center justify-between gap-3 bg-zinc-50/50 dark:bg-zinc-900/30">
                    <div class="flex flex-col sm:flex-row flex-wrap items-stretch sm:items-center gap-2 sm:gap-3 w-full md:w-auto">
                        <input type="text" id="ws-search" placeholder="Search truck #, plate, fault notes..." oninput="filterFleetTable(true)" class="bg-white dark:bg-zinc-900 border border-zinc-300 dark:border-zinc-700 rounded-md px-3 py-1.5 text-xs text-zinc-900 dark:text-zinc-100 placeholder-zinc-400 focus:outline-none focus:ring-1 focus:ring-zinc-950 dark:focus:ring-zinc-300 w-full sm:w-64 transition">
                        
                        <select id="ws-mech-filter" onchange="filterFleetTable(true)" class="bg-white dark:bg-zinc-900 border border-zinc-300 dark:border-zinc-700 rounded-md px-2.5 py-1.5 text-xs text-zinc-800 dark:text-zinc-200 focus:outline-none focus:ring-1 focus:ring-zinc-950 dark:focus:ring-zinc-300 transition">
                            <option value="ALL">All Mechanics</option>
                        </select>

                        <select id="ws-status-filter" onchange="filterFleetTable(true)" class="bg-white dark:bg-zinc-900 border border-zinc-300 dark:border-zinc-700 rounded-md px-2.5 py-1.5 text-xs text-zinc-800 dark:text-zinc-200 focus:outline-none focus:ring-1 focus:ring-zinc-950 dark:focus:ring-zinc-300 transition">
                            <option value="ALL">All Workshop Stages</option>
                            <option value="UNDER_REVIEW">Under Review</option>
                            <option value="WITH_MECHANIC">With Mechanic</option>
                            <option value="AWAITING_PARTS">Awaiting Parts</option>
                            <option value="AWAITING_TEST">Quality Inspection</option>
                            <option value="REWORK_REQUIRED">Rework Required</option>
                            <option value="CLOSED">Returned to Fleet</option>
                        </select>
                    </div>

                    <div class="flex items-center justify-between sm:justify-end gap-2">
                        <span id="ws-count-badge" class="inline-flex items-center px-2.5 py-1 rounded-md text-xs font-medium border border-zinc-200 bg-zinc-100 text-zinc-800 dark:border-zinc-800 dark:bg-zinc-800 dark:text-zinc-200">
                            Showing 0 vehicles
                        </span>
                    </div>
                </div>

                <!-- Responsive Mobile Card List -->
                <div id="ws-cards-list" class="block md:hidden divide-y divide-zinc-200 dark:divide-zinc-800"></div>

                <!-- Desktop Table -->
                <div class="hidden md:block overflow-x-auto">
                    <table class="w-full text-left text-xs">
                        <thead class="bg-zinc-50/75 dark:bg-zinc-900/50 text-zinc-500 dark:text-zinc-400 font-medium uppercase tracking-wider border-b border-zinc-200 dark:border-zinc-800">
                            <tr>
                                <th class="px-4 py-3 whitespace-nowrap">Ticket #</th>
                                <th class="px-4 py-3 whitespace-nowrap">Truck & Plate</th>
                                <th class="px-4 py-3 whitespace-nowrap">Vehicle Model</th>
                                <th class="px-4 py-3 whitespace-nowrap">Fault & Description</th>
                                <th class="px-4 py-3 whitespace-nowrap">Logged By</th>
                                <th class="px-4 py-3 whitespace-nowrap">Mechanic & ETA</th>
                                <th class="px-4 py-3 whitespace-nowrap">Parts Requisition</th>
                                <th class="px-4 py-3 whitespace-nowrap">Costing</th>
                                <th class="px-4 py-3 whitespace-nowrap">Status & QC</th>
                            </tr>
                        </thead>
                        <tbody id="ws-table-body" class="divide-y divide-zinc-200 dark:divide-zinc-800 text-zinc-800 dark:text-zinc-200">
                            <tr class="animate-pulse">
                                <td class="px-4 py-3"><div class="h-4 bg-zinc-200 dark:bg-zinc-800 rounded w-16"></div></td>
                                <td class="px-4 py-3"><div class="h-4 bg-zinc-200 dark:bg-zinc-800 rounded w-28"></div></td>
                                <td class="px-4 py-3"><div class="h-4 bg-zinc-200 dark:bg-zinc-800 rounded w-24"></div></td>
                                <td class="px-4 py-3"><div class="h-4 bg-zinc-200 dark:bg-zinc-800 rounded w-44"></div></td>
                                <td class="px-4 py-3"><div class="h-4 bg-zinc-200 dark:bg-zinc-800 rounded w-20"></div></td>
                                <td class="px-4 py-3"><div class="h-4 bg-zinc-200 dark:bg-zinc-800 rounded w-24"></div></td>
                                <td class="px-4 py-3"><div class="h-4 bg-zinc-200 dark:bg-zinc-800 rounded w-28"></div></td>
                                <td class="px-4 py-3"><div class="h-4 bg-zinc-200 dark:bg-zinc-800 rounded w-16"></div></td>
                                <td class="px-4 py-3"><div class="h-4 bg-zinc-200 dark:bg-zinc-800 rounded w-20"></div></td>
                            </tr>
                        </tbody>
                    </table>
                </div>

                <!-- Pagination Footer -->
                <div class="p-3.5 border-t border-zinc-200 dark:border-zinc-800 flex flex-col sm:flex-row items-center justify-between gap-3 bg-zinc-50/50 dark:bg-zinc-900/30">
                    <div class="text-xs text-zinc-500 dark:text-zinc-400 font-medium" id="ws-pagination-info">Showing 0 entries</div>
                    <div class="flex items-center gap-1.5" id="ws-pagination-controls"></div>
                </div>
            </div>
        </div>

        <!-- ========================================================= -->
        <!-- TAB 4: SALES TO FLEET OPERATIONS -->
        <!-- ========================================================= -->
        <div id="view-fleet" class="domain-view space-y-6" style="display: {'block' if 'fleet' in allowed and default_tab == 'fleet' else 'none'}">
            <!-- Operations Command Center Header Card -->
            <div id="master-kpi-banner" class="rounded-xl border border-zinc-200 bg-white p-5 sm:p-6 shadow-xs dark:border-zinc-800 dark:bg-zinc-950">
                <div class="flex flex-col lg:flex-row lg:items-center justify-between gap-4 pb-4 border-b border-zinc-100 dark:border-zinc-850 mb-5">
                    <div>
                        <div class="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-md text-xs font-medium border border-zinc-200 bg-zinc-100 text-zinc-800 dark:border-zinc-800 dark:bg-zinc-800 dark:text-zinc-200 mb-2">
                            Commercial Fleet Operations
                        </div>
                        <h2 class="text-xl sm:text-2xl font-bold tracking-tight text-zinc-900 dark:text-zinc-100">Operations Command Center</h2>
                        <p class="text-xs text-zinc-500 dark:text-zinc-400 mt-0.5">Multi-Company Operations: LG Plast, Tagoneswa Hardware & Kreckle Foods</p>
                    </div>

                    <!-- Action Controls -->
                    <div class="flex flex-wrap items-center gap-2">
                        {rates_btn_html}
                        {clear_debt_btn_html}
                        {user_mgmt_btn_html}
                        {audit_logs_btn_html}
                    </div>
                </div>

                <!-- 4 Master KPI Summary Cards -->
                <div class="grid grid-cols-2 md:grid-cols-4 gap-3 sm:gap-4">
                    <div class="rounded-lg border border-zinc-200/80 bg-zinc-50/60 p-4 dark:border-zinc-800/80 dark:bg-zinc-900/40">
                        <div class="text-xs font-medium text-zinc-500 dark:text-zinc-400">Pending Approvals</div>
                        <div class="text-2xl font-bold tracking-tight text-amber-600 dark:text-amber-400 mt-1 font-mono" id="master-active-ops">0</div>
                        <div class="text-xs text-zinc-500 dark:text-zinc-400 mt-0.5">Trips requiring review</div>
                    </div>
                    <div class="rounded-lg border border-zinc-200/80 bg-zinc-50/60 p-4 dark:border-zinc-800/80 dark:bg-zinc-900/40">
                        <div class="text-xs font-medium text-zinc-500 dark:text-zinc-400">Clearance Rate</div>
                        <div class="text-2xl font-bold tracking-tight text-emerald-600 dark:text-emerald-400 mt-1 font-mono" id="master-res-rate">100%</div>
                        <div class="text-xs text-zinc-500 dark:text-zinc-400 mt-0.5">Approved vs dispatched</div>
                    </div>
                    {master_kpi_cards_3_4}
                </div>
            </div>

            <!-- Multi-Company Division Selector Bar -->
            <div class="p-3 bg-white dark:bg-zinc-950 rounded-xl border border-zinc-200 dark:border-zinc-800 shadow-xs flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                <div class="flex items-center gap-2">
                    <span class="text-xs font-semibold uppercase tracking-wider text-zinc-700 dark:text-zinc-300">
                        Company Division:
                    </span>
                    <span class="text-xs text-zinc-500 dark:text-zinc-400 hidden md:inline">Partition operational metrics & trips</span>
                </div>
                <div class="flex flex-wrap items-center gap-1.5" id="fleet-company-pills">
                    <button onclick="switchFleetCompany('ALL')" id="fleet-comp-ALL" class="fleet-company-pill px-3 py-1.5 rounded-md text-xs font-medium bg-zinc-900 text-zinc-50 dark:bg-zinc-50 dark:text-zinc-900 shadow-xs transition cursor-pointer">
                        All Companies
                    </button>
                    <button onclick="switchFleetCompany('LG Plast')" id="fleet-comp-LG" class="fleet-company-pill px-3 py-1.5 rounded-md text-xs font-medium text-zinc-600 dark:text-zinc-400 hover:bg-zinc-100 dark:hover:bg-zinc-800 transition cursor-pointer">
                        LG Plast
                    </button>
                    <button onclick="switchFleetCompany('Tagoneswa Hardware')" id="fleet-comp-TG" class="fleet-company-pill px-3 py-1.5 rounded-md text-xs font-medium text-zinc-600 dark:text-zinc-400 hover:bg-zinc-100 dark:hover:bg-zinc-800 transition cursor-pointer">
                        Tagoneswa Hardware
                    </button>
                    <button onclick="switchFleetCompany('Kreckle Foods')" id="fleet-comp-Kreckle" class="fleet-company-pill px-3 py-1.5 rounded-md text-xs font-medium text-zinc-600 dark:text-zinc-400 hover:bg-zinc-100 dark:hover:bg-zinc-800 transition cursor-pointer">
                        Kreckle Foods
                    </button>
                </div>
            </div>

            <!-- Fleet Sub-View Navigation Bar -->
            <div class="p-2 sm:p-2.5 bg-white/75 dark:bg-zinc-950/75 backdrop-blur-md rounded-xl border border-zinc-200/80 dark:border-zinc-800/80 shadow-xs flex flex-col sm:flex-row sm:items-center justify-between gap-2.5">
                <!-- Mobile Select -->
                <div class="sm:hidden w-full">
                    <select id="fleet-view-selector" onchange="switchFleetSubView(this.value)" class="w-full bg-zinc-100 dark:bg-zinc-900 text-zinc-900 dark:text-zinc-100 text-xs font-medium px-3 py-2 rounded-md border border-zinc-300 dark:border-zinc-700">
                        <option value="overview">Operations Overview</option>
                        <option value="trips">Trip Pipeline</option>
                        {nav_salespersons_opt}
                        {nav_payments_opt}
                        <option value="trucks">Fleet Vehicles</option>
                        <option value="drivers">Commercial Drivers</option>
                        <option value="approvals">Trip Approvals</option>
                        {nav_ledger_opt}
                        {nav_analytics_opt}
                    </select>
                </div>

                <!-- Desktop Segmented Fast-Nav Pills -->
                <div class="hidden sm:flex items-center gap-1 overflow-x-auto no-scrollbar" id="fleet-fast-nav">
                    <button onclick="switchFleetSubView('overview')" id="fleet-btn-overview" data-view="overview" class="fleet-quick-pill px-3 py-1.5 rounded-md text-xs font-semibold bg-blue-600 text-white shadow-xs transition cursor-pointer whitespace-nowrap">Overview</button>
                    <button onclick="switchFleetSubView('trips')" id="fleet-btn-trips" data-view="trips" class="fleet-quick-pill px-3 py-1.5 rounded-md text-xs font-medium bg-white/60 dark:bg-zinc-900/60 backdrop-blur-sm border border-zinc-200/80 dark:border-zinc-800/80 text-zinc-700 dark:text-zinc-300 hover:bg-zinc-100 dark:hover:bg-zinc-800 hover:text-zinc-950 dark:hover:text-zinc-50 transition cursor-pointer whitespace-nowrap">Trips</button>
                    {nav_salespersons_btn}
                    {nav_payments_btn}
                    <button onclick="switchFleetSubView('trucks')" id="fleet-btn-trucks" data-view="trucks" class="fleet-quick-pill px-3 py-1.5 rounded-md text-xs font-medium bg-white/60 dark:bg-zinc-900/60 backdrop-blur-sm border border-zinc-200/80 dark:border-zinc-800/80 text-zinc-700 dark:text-zinc-300 hover:bg-zinc-100 dark:hover:bg-zinc-800 hover:text-zinc-950 dark:hover:text-zinc-50 transition cursor-pointer whitespace-nowrap">Vehicles</button>
                    <button onclick="switchFleetSubView('drivers')" id="fleet-btn-drivers" data-view="drivers" class="fleet-quick-pill px-3 py-1.5 rounded-md text-xs font-medium bg-white/60 dark:bg-zinc-900/60 backdrop-blur-sm border border-zinc-200/80 dark:border-zinc-800/80 text-zinc-700 dark:text-zinc-300 hover:bg-zinc-100 dark:hover:bg-zinc-800 hover:text-zinc-950 dark:hover:text-zinc-50 transition cursor-pointer whitespace-nowrap">Drivers</button>
                    <button onclick="switchFleetSubView('approvals')" id="fleet-btn-approvals" data-view="approvals" class="fleet-quick-pill px-3 py-1.5 rounded-md text-xs font-medium bg-white/60 dark:bg-zinc-900/60 backdrop-blur-sm border border-zinc-200/80 dark:border-zinc-800/80 text-zinc-700 dark:text-zinc-300 hover:bg-zinc-100 dark:hover:bg-zinc-800 hover:text-zinc-950 dark:hover:text-zinc-50 transition cursor-pointer whitespace-nowrap">Approvals</button>
                    {nav_ledger_btn}
                    {nav_analytics_btn}
                </div>

                <div class="hidden sm:flex items-center gap-2 px-3 py-1 text-xs text-zinc-500 dark:text-zinc-400 shrink-0">
                    <span class="w-2 h-2 rounded-full bg-emerald-500 animate-pulse"></span>
                    <span class="font-mono text-[11px]">Live Sync</span>
                </div>
            </div>

            <!-- SUBVIEW 0: OPERATIONS OVERVIEW -->
            <div id="fleet-section-overview" class="fleet-subview-panel space-y-6 transition-all duration-200" style="display: block;">
                <!-- TIER 1: ACTION REQUIRED -->
                <div>
                    <div class="flex items-center gap-2 mb-3">
                        <span class="text-xs font-bold uppercase tracking-wider text-rose-600 dark:text-rose-400">Action Required</span>
                        <span id="ov-alerts-count-badge" class="inline-flex items-center px-2 py-0.5 rounded-full text-[11px] font-semibold border border-amber-200 bg-amber-50 text-amber-700 dark:border-amber-800 dark:bg-amber-950/40 dark:text-amber-300">0 active</span>
                    </div>

                    <div class="grid grid-cols-2 md:grid-cols-4 gap-3 mb-3">
                        <div class="rounded-xl border border-zinc-200 bg-white p-4 shadow-xs dark:border-zinc-800 dark:bg-zinc-950">
                            <div class="flex items-center justify-between text-xs font-medium text-zinc-500 dark:text-zinc-400">
                                <span>Trip Approvals</span>
                                <span class="font-mono text-[10px] px-1.5 py-0.5 rounded bg-amber-50 dark:bg-amber-950/40 text-amber-700 dark:text-amber-300 font-semibold border border-amber-200 dark:border-amber-800/60">QUEUE</span>
                            </div>
                            <div class="text-2xl font-bold tracking-tight text-amber-600 dark:text-amber-400 mt-1 font-mono" id="ov-kpi-pending-approvals">0</div>
                            <div class="text-xs text-zinc-500 dark:text-zinc-400 mt-0.5 truncate" id="ov-kpi-shortfall-sub">0 shortfalls</div>
                        </div>

                        <div class="rounded-xl border border-zinc-200 bg-white p-4 shadow-xs dark:border-zinc-800 dark:bg-zinc-950">
                            <div class="flex items-center justify-between text-xs font-medium text-zinc-500 dark:text-zinc-400">
                                <span>Action Queue</span>
                                <span class="font-mono text-[10px] px-1.5 py-0.5 rounded bg-rose-50 dark:bg-rose-950/40 text-rose-700 dark:text-rose-300 font-semibold border border-rose-200 dark:border-rose-800/60">URGENT</span>
                            </div>
                            <div class="text-2xl font-bold tracking-tight text-rose-600 dark:text-rose-400 mt-1 font-mono" id="ov-kpi-bottlenecks">0</div>
                            <div class="text-xs text-zinc-500 dark:text-zinc-400 mt-0.5 truncate">Priority exceptions</div>
                        </div>

                        <div class="col-span-2 rounded-xl border border-zinc-200 bg-white p-4 shadow-xs dark:border-zinc-800 dark:bg-zinc-950" id="ov-kpi-card-slot5">
                            <div class="flex items-center justify-between text-xs font-medium text-zinc-500 dark:text-zinc-400">
                                <span id="ov-kpi-slot5-title">Commercial Balance</span>
                                <span class="font-mono text-[10px] px-1.5 py-0.5 rounded bg-zinc-100 dark:bg-zinc-800 text-zinc-600 dark:text-zinc-400 font-semibold" id="ov-kpi-slot5-icon">BALANCE</span>
                            </div>
                            <div class="text-2xl font-bold tracking-tight text-zinc-900 dark:text-zinc-100 mt-1 font-mono truncate" id="ov-kpi-slot5-val">$0.00</div>
                            <div class="text-xs text-zinc-500 dark:text-zinc-400 mt-0.5 truncate" id="ov-kpi-slot5-sub">Outstanding Rep Debt</div>
                        </div>
                    </div>

                    <!-- Prioritized Alerts List -->
                    <div class="rounded-xl border border-zinc-200 bg-white shadow-xs dark:border-zinc-800 dark:bg-zinc-950 overflow-hidden">
                        <div id="ov-alerts-list" class="p-4 sm:p-5 space-y-3 divide-y divide-zinc-100 dark:divide-zinc-850">
                            <div class="text-center py-6 text-zinc-400 dark:text-zinc-500 text-xs">Loading live operations stream...</div>
                        </div>
                    </div>
                </div>

                <!-- TIER 2: TODAY'S OPERATIONS -->
                <div>
                    <div class="flex items-center gap-2 mb-3">
                        <span class="text-xs font-bold uppercase tracking-wider text-zinc-700 dark:text-zinc-300">Today's Operations</span>
                    </div>
                    <div class="grid grid-cols-2 lg:grid-cols-4 gap-3">
                        <div class="rounded-xl border border-zinc-200 bg-white p-4 sm:p-5 shadow-xs dark:border-zinc-800 dark:bg-zinc-950">
                            <div class="text-xs font-medium text-zinc-500 dark:text-zinc-400">Active Trips</div>
                            <div class="text-2xl font-bold tracking-tight text-zinc-900 dark:text-zinc-100 mt-1 font-mono" id="ov-kpi-active-trips">0</div>
                            <div class="text-xs text-zinc-500 dark:text-zinc-400 mt-0.5 truncate" id="ov-kpi-transit-trips">0 in transit</div>
                        </div>

                        <div class="rounded-xl border border-zinc-200 bg-white p-4 sm:p-5 shadow-xs dark:border-zinc-800 dark:bg-zinc-950">
                            <div class="text-xs font-medium text-zinc-500 dark:text-zinc-400">Driver Roster</div>
                            <div class="text-2xl font-bold tracking-tight text-zinc-900 dark:text-zinc-100 mt-1 font-mono" id="ov-kpi-drivers-active">0</div>
                            <div class="text-xs text-zinc-500 dark:text-zinc-400 mt-0.5 truncate" id="ov-kpi-drivers-total">of 0 on roster</div>
                        </div>

                        <div class="rounded-xl border border-zinc-200 bg-white p-4 sm:p-5 shadow-xs dark:border-zinc-800 dark:bg-zinc-950">
                            <div class="text-xs font-medium text-zinc-500 dark:text-zinc-400">Trips Completed</div>
                            <div class="text-2xl font-bold tracking-tight text-emerald-600 dark:text-emerald-400 mt-1 font-mono" id="ov-kpi-completed-trips">0</div>
                            <div class="text-xs text-zinc-500 dark:text-zinc-400 mt-0.5 truncate">Successfully settled</div>
                        </div>

                        {ov_card4_html}
                    </div>
                </div>

                <!-- TIER 3: FLEET STATUS -->
                <div>
                    <div class="flex items-center gap-2 mb-3">
                        <span class="text-xs font-bold uppercase tracking-wider text-zinc-700 dark:text-zinc-300">Fleet Status</span>
                        <span class="text-xs text-zinc-500 dark:text-zinc-400">Live workshop reports</span>
                    </div>
                    <div class="rounded-xl border border-zinc-200 bg-white shadow-xs dark:border-zinc-800 dark:bg-zinc-950 overflow-hidden">
                        <div class="grid grid-cols-2 md:grid-cols-5 divide-y md:divide-y-0 md:divide-x divide-zinc-200 dark:divide-zinc-800">
                            <div class="p-4 sm:p-5 text-center">
                                <div class="text-xs font-medium text-zinc-500 dark:text-zinc-400 mb-1">Available</div>
                                <div class="text-2xl font-bold tracking-tight text-emerald-600 dark:text-emerald-400 font-mono" id="ov-kpi-trucks-ready">0</div>
                                <div class="text-xs text-zinc-500 dark:text-zinc-400 mt-0.5">Field Ready</div>
                            </div>
                            <div class="p-4 sm:p-5 text-center">
                                <div class="text-xs font-medium text-zinc-500 dark:text-zinc-400 mb-1">In Workshop</div>
                                <div class="text-2xl font-bold tracking-tight text-amber-600 dark:text-amber-400 font-mono" id="ov-kpi-trucks-in-workshop">0</div>
                                <div class="text-xs text-zinc-500 dark:text-zinc-400 mt-0.5">Under Repair</div>
                            </div>
                            <div class="p-4 sm:p-5 text-center">
                                <div class="text-xs font-medium text-zinc-500 dark:text-zinc-400 mb-1">Awaiting Spares</div>
                                <div class="text-2xl font-bold tracking-tight text-rose-600 dark:text-rose-400 font-mono" id="ov-kpi-trucks-awaiting-parts">0</div>
                                <div class="text-xs text-zinc-500 dark:text-zinc-400 mt-0.5">Parts Requisition</div>
                            </div>
                            <div class="p-4 sm:p-5 text-center">
                                <div class="text-xs font-medium text-zinc-500 dark:text-zinc-400 mb-1">Awaiting QC</div>
                                <div class="text-2xl font-bold tracking-tight text-blue-600 dark:text-blue-400 font-mono" id="ov-kpi-trucks-awaiting-qc">0</div>
                                <div class="text-xs text-zinc-500 dark:text-zinc-400 mt-0.5">Road Test</div>
                            </div>
                            <div class="p-4 sm:p-5 text-center col-span-2 md:col-span-1">
                                <div class="text-xs font-medium text-zinc-500 dark:text-zinc-400 mb-1">Total Fleet</div>
                                <div class="text-2xl font-bold tracking-tight text-zinc-900 dark:text-zinc-100 font-mono" id="ov-kpi-trucks-total">0</div>
                                <div class="text-xs text-zinc-500 dark:text-zinc-400 mt-0.5">Vehicles</div>
                            </div>
                        </div>
                    </div>
                </div>

                <!-- TIER 4: FINANCIAL SUMMARY -->
                <div id="ov-financial-section" class="space-y-3" style="display: {'block' if can_view_balances else 'none'};">
                    <div class="flex items-center gap-2 mb-2">
                        <span class="text-xs font-bold uppercase tracking-wider text-zinc-700 dark:text-zinc-300">Financial Summary</span>
                    </div>
                    <div class="grid grid-cols-2 md:grid-cols-4 gap-3">
                        <div class="rounded-xl border border-zinc-200 bg-white p-4 shadow-xs dark:border-zinc-800 dark:bg-zinc-950">
                            <div class="text-xs font-medium text-zinc-500 dark:text-zinc-400">Transport Charges</div>
                            <div class="text-xl font-bold tracking-tight text-zinc-900 dark:text-zinc-100 mt-1 font-mono" id="ov-fin-transport-charges">$0.00</div>
                        </div>
                        <div class="rounded-xl border border-zinc-200 bg-white p-4 shadow-xs dark:border-zinc-800 dark:bg-zinc-950">
                            <div class="text-xs font-medium text-zinc-500 dark:text-zinc-400">Operating Expenses</div>
                            <div class="text-xl font-bold tracking-tight text-zinc-900 dark:text-zinc-100 mt-1 font-mono" id="ov-fin-total-opex">$0.00</div>
                        </div>
                        <div class="rounded-xl border border-zinc-200 bg-white p-4 shadow-xs dark:border-zinc-800 dark:bg-zinc-950">
                            <div class="text-xs font-medium text-zinc-500 dark:text-zinc-400">Debt Backlog</div>
                            <div class="text-xl font-bold tracking-tight text-rose-600 dark:text-rose-400 mt-1 font-mono" id="ov-fin-debt-backlog">$0.00</div>
                        </div>
                        <div class="rounded-xl border border-zinc-200 bg-white p-4 shadow-xs dark:border-zinc-800 dark:bg-zinc-950">
                            <div class="text-xs font-medium text-zinc-500 dark:text-zinc-400">Cleared Payments</div>
                            <div class="text-xl font-bold tracking-tight text-emerald-600 dark:text-emerald-400 mt-1 font-mono" id="ov-fin-cleared-payments">$0.00</div>
                        </div>
                    </div>
                    <div id="ov-financial-body" class="p-3 rounded-lg border border-zinc-200 bg-white dark:border-zinc-800 dark:bg-zinc-950 text-xs"></div>
                </div>
            </div>

            <!-- SUBVIEW 1: TRIP PIPELINE -->
            <div id="fleet-section-trips" class="fleet-subview-panel rounded-xl border border-zinc-200 bg-white shadow-xs dark:border-zinc-800 dark:bg-zinc-950 overflow-hidden" style="display: none;">
                <div class="p-4 border-b border-zinc-200 dark:border-zinc-800 flex flex-col md:flex-row items-stretch md:items-center justify-between gap-3 bg-zinc-50/50 dark:bg-zinc-900/30">
                    <div class="flex flex-col sm:flex-row flex-wrap items-stretch sm:items-center gap-2 sm:gap-3 w-full md:w-auto">
                        <input type="text" id="trips-search" placeholder="Search Trip #, Driver, Truck, City..." oninput="filterTripsTable(true)" class="bg-white dark:bg-zinc-900 border border-zinc-300 dark:border-zinc-700 rounded-md px-3 py-1.5 text-xs text-zinc-900 dark:text-zinc-100 placeholder-zinc-400 focus:outline-none focus:ring-1 focus:ring-zinc-950 dark:focus:ring-zinc-300 w-full sm:w-64 transition">
                        
                        <select id="trips-stage-filter" onchange="filterTripsTable(true)" class="bg-white dark:bg-zinc-900 border border-zinc-300 dark:border-zinc-700 rounded-md px-2.5 py-1.5 text-xs text-zinc-800 dark:text-zinc-200 focus:outline-none focus:ring-1 focus:ring-zinc-950 dark:focus:ring-zinc-300 transition">
                            <option value="ALL">All Trip Stages (1–7)</option>
                            <option value="QUOTED">Stage 1: Quoted</option>
                            <option value="APPROVED">Stage 2: Dispatch Approved</option>
                            <option value="VOUCHER_ISSUED">Stage 3: Fuel & Allowance</option>
                            <option value="LOADED">Stage 4: Loading & Odometer</option>
                            <option value="IN_TRANSIT">Stage 5: In Transit</option>
                            <option value="OFFLOADED">Stage 6: Offloaded & POD</option>
                            <option value="SETTLED">Stage 7: Trip Settled</option>
                        </select>
                    </div>

                    <div class="flex items-center justify-between sm:justify-end gap-2">
                        <span id="trips-count-badge" class="inline-flex items-center px-2.5 py-1 rounded-md text-xs font-medium border border-zinc-200 bg-zinc-100 text-zinc-800 dark:border-zinc-800 dark:bg-zinc-800 dark:text-zinc-200">
                            Showing 0 trips
                        </span>
                    </div>
                </div>

                <!-- Responsive Mobile Card List -->
                <div id="trips-cards-list" class="block md:hidden divide-y divide-zinc-200 dark:divide-zinc-800"></div>

                <!-- Desktop Table -->
                <div class="hidden md:block overflow-x-auto">
                    <table class="w-full text-left text-xs">
                        <thead class="bg-zinc-50/75 dark:bg-zinc-900/50 text-zinc-500 dark:text-zinc-400 font-medium uppercase tracking-wider border-b border-zinc-200 dark:border-zinc-800">
                            <tr>
                                <th class="px-4 py-3 whitespace-nowrap">Trip ID</th>
                                <th class="px-4 py-3 whitespace-nowrap">Stage & Status</th>
                                <th class="px-4 py-3 whitespace-nowrap">Sales Rep & Client</th>
                                <th class="px-4 py-3 whitespace-nowrap">Destination & Route</th>
                                <th class="px-4 py-3 whitespace-nowrap">Truck & Driver</th>
                                <th class="px-4 py-3 whitespace-nowrap">Allowance / Transport</th>
                                <th class="px-4 py-3 whitespace-nowrap">Timestamps</th>
                                <th class="px-4 py-3 whitespace-nowrap">Odometer (KM)</th>
                            </tr>
                        </thead>
                        <tbody id="fleet-trips-table-body" class="divide-y divide-zinc-200 dark:divide-zinc-800 text-zinc-800 dark:text-zinc-200">
                            <tr class="animate-pulse">
                                <td class="px-4 py-3"><div class="h-4 bg-zinc-200 dark:bg-zinc-800 rounded w-16"></div></td>
                                <td class="px-4 py-3"><div class="h-4 bg-zinc-200 dark:bg-zinc-800 rounded w-20"></div></td>
                                <td class="px-4 py-3"><div class="h-4 bg-zinc-200 dark:bg-zinc-800 rounded w-28"></div></td>
                                <td class="px-4 py-3"><div class="h-4 bg-zinc-200 dark:bg-zinc-800 rounded w-32"></div></td>
                                <td class="px-4 py-3"><div class="h-4 bg-zinc-200 dark:bg-zinc-800 rounded w-28"></div></td>
                                <td class="px-4 py-3"><div class="h-4 bg-zinc-200 dark:bg-zinc-800 rounded w-20"></div></td>
                                <td class="px-4 py-3"><div class="h-4 bg-zinc-200 dark:bg-zinc-800 rounded w-24"></div></td>
                                <td class="px-4 py-3"><div class="h-4 bg-zinc-200 dark:bg-zinc-800 rounded w-16"></div></td>
                            </tr>
                        </tbody>
                    </table>
                </div>

                <div class="p-3.5 border-t border-zinc-200 dark:border-zinc-800 flex flex-col sm:flex-row items-center justify-between gap-3 bg-zinc-50/50 dark:bg-zinc-900/30">
                    <div class="text-xs text-zinc-500 dark:text-zinc-400 font-medium" id="trips-pagination-info">Showing 0 entries</div>
                    <div class="flex items-center gap-1.5" id="trips-pagination-controls"></div>
                </div>
            </div>

            <!-- SUBVIEW 2: SALESPERSON DEBT LEDGER & BALANCES -->
            {salespersons_section_html}

            <!-- SUBVIEW 3: PAYMENT HISTORY -->
            {payments_section_html}

            <!-- SUBVIEW 4: FLEET VEHICLES -->
            <div id="fleet-section-trucks" class="fleet-subview-panel rounded-xl border border-zinc-200 bg-white shadow-xs dark:border-zinc-800 dark:bg-zinc-950 overflow-hidden" style="display: none;">
                <div class="p-4 border-b border-zinc-200 dark:border-zinc-800 flex flex-col md:flex-row items-stretch md:items-center justify-between gap-3 bg-zinc-50/50 dark:bg-zinc-900/30">
                    <div>
                        <h3 class="text-sm font-semibold text-zinc-900 dark:text-zinc-100">Fleet Vehicles</h3>
                        <p class="text-xs text-zinc-500 dark:text-zinc-400">Commercial delivery vehicles registered in Tagoneswa database</p>
                    </div>
                    <div class="flex items-center gap-2 w-full sm:w-auto">
                        <input type="text" id="trucks-search" placeholder="Search Truck #, Plate, Model..." oninput="filterTrucksTable(true)" class="bg-white dark:bg-zinc-900 border border-zinc-300 dark:border-zinc-700 rounded-md px-3 py-1.5 text-xs text-zinc-900 dark:text-zinc-100 placeholder-zinc-400 focus:outline-none focus:ring-1 focus:ring-zinc-950 dark:focus:ring-zinc-300 w-full sm:w-64 transition">
                        <button onclick="openAddTruckModal()" class="px-3 py-1.5 rounded-md text-xs font-medium bg-zinc-900 hover:bg-zinc-800 dark:bg-zinc-100 dark:hover:bg-zinc-200 text-zinc-50 dark:text-zinc-900 transition shadow-xs cursor-pointer whitespace-nowrap">
                            + Add Truck
                        </button>
                    </div>
                </div>

                <!-- Responsive Mobile Card List -->
                <div id="trucks-cards-list" class="block md:hidden divide-y divide-zinc-200 dark:divide-zinc-800"></div>

                <!-- Desktop Table -->
                <div class="hidden md:block overflow-x-auto">
                    <table class="w-full text-left text-xs">
                        <thead class="bg-zinc-50/75 dark:bg-zinc-900/50 text-zinc-500 dark:text-zinc-400 font-medium uppercase tracking-wider border-b border-zinc-200 dark:border-zinc-800">
                            <tr>
                                <th class="px-4 py-3 whitespace-nowrap">Truck #</th>
                                <th class="px-4 py-3 whitespace-nowrap">Plate Number</th>
                                <th class="px-4 py-3 whitespace-nowrap">Model & Make</th>
                                <th class="px-4 py-3 whitespace-nowrap">Body Type</th>
                                <th class="px-4 py-3 whitespace-nowrap">Home Depot</th>
                                <th class="px-4 py-3 whitespace-nowrap">Active Status</th>
                                <th class="px-4 py-3 text-right whitespace-nowrap">Action</th>
                            </tr>
                        </thead>
                        <tbody id="fleet-trucks-table-body" class="divide-y divide-zinc-200 dark:divide-zinc-800 text-zinc-800 dark:text-zinc-200"></tbody>
                    </table>
                </div>

                <div class="p-3.5 border-t border-zinc-200 dark:border-zinc-800 flex flex-col sm:flex-row items-center justify-between gap-3 bg-zinc-50/50 dark:bg-zinc-900/30">
                    <div class="text-xs text-zinc-500 dark:text-zinc-400 font-medium" id="trucks-pagination-info">Showing 0 entries</div>
                    <div class="flex items-center gap-1.5" id="trucks-pagination-controls"></div>
                </div>
            </div>

            <!-- SUBVIEW 5: COMMERCIAL DRIVERS -->
            <div id="fleet-section-drivers" class="fleet-subview-panel rounded-xl border border-zinc-200 bg-white shadow-xs dark:border-zinc-800 dark:bg-zinc-950 overflow-hidden" style="display: none;">
                <div class="p-4 border-b border-zinc-200 dark:border-zinc-800 flex flex-col md:flex-row items-stretch md:items-center justify-between gap-3 bg-zinc-50/50 dark:bg-zinc-900/30">
                    <div>
                        <h3 class="text-sm font-semibold text-zinc-900 dark:text-zinc-100">Commercial Drivers</h3>
                        <p class="text-xs text-zinc-500 dark:text-zinc-400">Verified commercial drivers registered in Tagoneswa database</p>
                    </div>
                    <div class="flex items-center gap-2 w-full sm:w-auto">
                        <input type="text" id="drivers-search" placeholder="Search Driver Name, Phone..." oninput="filterDriversTable(true)" class="bg-white dark:bg-zinc-900 border border-zinc-300 dark:border-zinc-700 rounded-md px-3 py-1.5 text-xs text-zinc-900 dark:text-zinc-100 placeholder-zinc-400 focus:outline-none focus:ring-1 focus:ring-zinc-950 dark:focus:ring-zinc-300 w-full sm:w-64 transition">
                        <button onclick="openAddDriverModal()" class="px-3 py-1.5 rounded-md text-xs font-medium bg-zinc-900 hover:bg-zinc-800 dark:bg-zinc-100 dark:hover:bg-zinc-200 text-zinc-50 dark:text-zinc-900 transition shadow-xs cursor-pointer whitespace-nowrap">
                            + Add Driver
                        </button>
                    </div>
                </div>

                <!-- Responsive Mobile Card List -->
                <div id="drivers-cards-list" class="block md:hidden divide-y divide-zinc-200 dark:divide-zinc-800"></div>

                <!-- Desktop Table -->
                <div class="hidden md:block overflow-x-auto">
                    <table class="w-full text-left text-xs">
                        <thead class="bg-zinc-50/75 dark:bg-zinc-900/50 text-zinc-500 dark:text-zinc-400 font-medium uppercase tracking-wider border-b border-zinc-200 dark:border-zinc-800">
                            <tr>
                                <th class="px-4 py-3 whitespace-nowrap">Staff ID</th>
                                <th class="px-4 py-3 whitespace-nowrap">Full Name</th>
                                <th class="px-4 py-3 whitespace-nowrap">WhatsApp Phone</th>
                                <th class="px-4 py-3 whitespace-nowrap">Role Designation</th>
                                <th class="px-4 py-3 whitespace-nowrap">Active Status</th>
                                <th class="px-4 py-3 text-right whitespace-nowrap">Action</th>
                            </tr>
                        </thead>
                        <tbody id="fleet-drivers-table-body" class="divide-y divide-zinc-200 dark:divide-zinc-800 text-zinc-800 dark:text-zinc-200"></tbody>
                    </table>
                </div>

                <div class="p-3.5 border-t border-zinc-200 dark:border-zinc-800 flex flex-col sm:flex-row items-center justify-between gap-3 bg-zinc-50/50 dark:bg-zinc-900/30">
                    <div class="text-xs text-zinc-500 dark:text-zinc-400 font-medium" id="drivers-pagination-info">Showing 0 entries</div>
                    <div class="flex items-center gap-1.5" id="drivers-pagination-controls"></div>
                </div>
            </div>

            <!-- SUBVIEW 6: SHORTFALL APPROVALS & DISPATCH AUDITS -->
            <div id="fleet-section-approvals" class="fleet-subview-panel space-y-4 transition-all duration-200" style="display: none;">
                <!-- Approvals Stats Cards -->
                <div class="grid grid-cols-2 sm:grid-cols-3 {f'lg:grid-cols-5' if can_view_balances else 'lg:grid-cols-4'} gap-3 sm:gap-4">
                    <div class="rounded-xl border border-zinc-200 bg-white p-4 shadow-xs dark:border-zinc-800 dark:bg-zinc-950">
                        <div class="text-xs font-medium text-zinc-500 dark:text-zinc-400">Total Trips Verified</div>
                        <div class="text-2xl font-bold tracking-tight text-zinc-900 dark:text-zinc-100 mt-1 font-mono" id="fleet-stat-trips">0</div>
                        <div class="text-xs text-zinc-500 dark:text-zinc-400 mt-0.5" id="fleet-stat-sales-val">""" + (f"""$0.00 ERP Sales""" if can_view_balances else f"""Trips Logged""") + f"""</div>
                    </div>
                    <div class="rounded-xl border border-zinc-200 bg-white p-4 shadow-xs dark:border-zinc-800 dark:bg-zinc-950">
                        <div class="text-xs font-medium text-zinc-500 dark:text-zinc-400">Approved for Dispatch</div>
                        <div class="text-2xl font-bold tracking-tight text-emerald-600 dark:text-emerald-400 mt-1 font-mono" id="fleet-stat-approved">0</div>
                        <div class="text-xs text-emerald-600 dark:text-emerald-400 mt-0.5">Cleared Trips</div>
                    </div>
                    <div class="rounded-xl border border-zinc-200 bg-white p-4 shadow-xs dark:border-zinc-800 dark:bg-zinc-950">
                        <div class="text-xs font-medium text-zinc-500 dark:text-zinc-400">Shortfalls Detected</div>
                        <div class="text-2xl font-bold tracking-tight text-amber-600 dark:text-amber-400 mt-1 font-mono" id="fleet-stat-shortfalls">0</div>
                        <div class="text-xs text-amber-600 dark:text-amber-400 mt-0.5">Below Threshold</div>
                    </div>
                    <div class="rounded-xl border border-zinc-200 bg-white p-4 shadow-xs dark:border-zinc-800 dark:bg-zinc-950">
                        <div class="text-xs font-medium text-zinc-500 dark:text-zinc-400">Transport Charges</div>
                        <div class="text-2xl font-bold tracking-tight text-zinc-900 dark:text-zinc-100 mt-1 font-mono" id="fleet-stat-transport">$0.00</div>
                        <div class="text-xs text-zinc-500 dark:text-zinc-400 mt-0.5">Total Fee Assessed</div>
                    </div>
                    {approvals_card5_stat}
                </div>

                <!-- Approvals Table Card -->
                <div class="rounded-xl border border-zinc-200 bg-white shadow-xs dark:border-zinc-800 dark:bg-zinc-950 overflow-hidden">
                    <div class="p-4 border-b border-zinc-200 dark:border-zinc-800 flex flex-col md:flex-row items-stretch md:items-center justify-between gap-3 bg-zinc-50/50 dark:bg-zinc-900/30">
                        <div class="flex flex-col sm:flex-row flex-wrap items-stretch sm:items-center gap-2 sm:gap-3 w-full md:w-auto">
                            <input type="text" id="fleet-search" placeholder="Search Trip ID, Salesperson, City..." oninput="filterFleetApprovalsTable(true)" class="bg-white dark:bg-zinc-900 border border-zinc-300 dark:border-zinc-700 rounded-md px-3 py-1.5 text-xs text-zinc-900 dark:text-zinc-100 placeholder-zinc-400 focus:outline-none focus:ring-1 focus:ring-zinc-950 dark:focus:ring-zinc-300 w-full sm:w-64 transition">
                            
                            <select id="fleet-city-filter" onchange="filterFleetApprovalsTable(true)" class="bg-white dark:bg-zinc-900 border border-zinc-300 dark:border-zinc-700 rounded-md px-2.5 py-1.5 text-xs text-zinc-800 dark:text-zinc-200 focus:outline-none focus:ring-1 focus:ring-zinc-950 dark:focus:ring-zinc-300 transition">
                                <option value="ALL">All Destination Cities</option>
                            </select>

                            <select id="fleet-status-filter" onchange="filterFleetApprovalsTable(true)" class="bg-white dark:bg-zinc-900 border border-zinc-300 dark:border-zinc-700 rounded-md px-2.5 py-1.5 text-xs text-zinc-800 dark:text-zinc-200 focus:outline-none focus:ring-1 focus:ring-zinc-950 dark:focus:ring-zinc-300 transition">
                                <option value="ALL">All Statuses</option>
                                <option value="APPROVED">Approved for Dispatch</option>
                                <option value="SHORTFALL_RECORDED">Shortfall Pending Resolution</option>
                                <option value="DISPATCHED">Dispatched</option>
                            </select>
                        </div>

                        <div class="flex items-center justify-between sm:justify-end gap-2">
                            <span id="fleet-count-badge" class="inline-flex items-center px-2.5 py-1 rounded-md text-xs font-medium border border-zinc-200 bg-zinc-100 text-zinc-800 dark:border-zinc-800 dark:bg-zinc-800 dark:text-zinc-200">
                                Showing 0 trips
                            </span>
                        </div>
                    </div>

                    <!-- Responsive Mobile Card List -->
                    <div id="approvals-cards-list" class="block md:hidden divide-y divide-zinc-200 dark:divide-zinc-800"></div>

                    <!-- Desktop Table -->
                    <div class="hidden md:block overflow-x-auto">
                        <table class="w-full text-left text-xs">
                            <thead class="bg-zinc-50/75 dark:bg-zinc-900/50 text-zinc-500 dark:text-zinc-400 font-medium uppercase tracking-wider border-b border-zinc-200 dark:border-zinc-800">
                                <tr>
                                    <th class="px-4 py-3 whitespace-nowrap">Trip ID</th>
                                    <th class="px-4 py-3 whitespace-nowrap">Salesperson</th>
                                    <th class="px-4 py-3 whitespace-nowrap">Destination & Route</th>
                                    {approvals_cols_head}
                                    <th class="px-4 py-3 whitespace-nowrap">Audit Check</th>
                                    <th class="px-4 py-3 whitespace-nowrap">Status</th>
                                    <th class="px-4 py-3 whitespace-nowrap">Date</th>
                                </tr>
                            </thead>
                            <tbody id="fleet-approvals-table-body" class="divide-y divide-zinc-200 dark:divide-zinc-800 text-zinc-800 dark:text-zinc-200"></tbody>
                        </table>
                    </div>

                    <div class="p-3.5 border-t border-zinc-200 dark:border-zinc-800 flex flex-col sm:flex-row items-center justify-between gap-3 bg-zinc-50/50 dark:bg-zinc-900/30">
                        <div class="text-xs text-zinc-500 dark:text-zinc-400 font-medium" id="fleet-pagination-info">Showing 0 entries</div>
                        <div class="flex items-center gap-1.5" id="fleet-pagination-controls"></div>
                    </div>
                </div>
            </div>

            <!-- SUBVIEW 7: FINANCIAL AUDIT & RECOVERY LEDGER -->
            {ledger_section_html}

            <!-- SUBVIEW 8: DATA ANALYTICS & FLEET METRICS -->
            {analytics_section_html}
        </div>
    </main>

    <!-- ========================================================= -->
    <!-- MODALS (SHADCN DIALOG STYLE) -->
    <!-- ========================================================= -->

    <!-- Modal 1: City Minimums & Fuel Price -->
    <div id="cityMinimumsModal" class="modal-overlay fixed inset-0 z-50 hidden flex items-center justify-center p-3 sm:p-4 bg-zinc-950/60 backdrop-blur-xs overscroll-contain">
        <div class="modal-card bg-white dark:bg-zinc-950 border border-zinc-200 dark:border-zinc-800 rounded-xl w-full max-w-5xl max-h-[92vh] flex flex-col shadow-2xl overflow-hidden">
            <div class="p-4 border-b border-zinc-200 dark:border-zinc-800 flex items-center justify-between shrink-0">
                <div>
                    <h3 class="text-base font-semibold text-zinc-900 dark:text-zinc-100">Fuel & Corridor Rate Configuration</h3>
                    <p class="text-xs text-zinc-500 dark:text-zinc-400">Configure fuel prices, meal and accommodation rates, and city delivery minimums</p>
                </div>
                <button onclick="closeCityConfigModal()" class="p-1 rounded-md text-zinc-400 hover:text-zinc-600 dark:hover:text-zinc-200 hover:bg-zinc-100 dark:hover:bg-zinc-800 transition cursor-pointer">✕</button>
            </div>
            <div class="p-4 sm:p-6 overflow-y-auto space-y-5 flex-1 overscroll-contain text-xs">
                <!-- Diesel Price Card -->
                <div class="p-4 rounded-lg border border-zinc-200 bg-zinc-50/50 dark:border-zinc-800 dark:bg-zinc-900/40 space-y-2">
                    <label class="block font-semibold text-zinc-800 dark:text-zinc-200">Diesel Price per Litre (USD)</label>
                    <div class="flex items-center gap-2">
                        <input type="number" id="modal-fuel-price" step="0.01" min="0.5" max="5.0" class="w-32 bg-white dark:bg-zinc-900 border border-zinc-300 dark:border-zinc-700 rounded-md px-3 py-1.5 text-xs font-mono font-bold text-zinc-900 dark:text-zinc-100 focus:outline-none focus:ring-1 focus:ring-zinc-950 dark:focus:ring-zinc-300">
                        <button onclick="saveFuelPrice()" id="modal-save-fuel-btn" class="px-3 py-1.5 rounded-md text-xs font-medium bg-zinc-900 hover:bg-zinc-800 dark:bg-zinc-100 dark:hover:bg-zinc-200 text-zinc-50 dark:text-zinc-900 transition shadow-xs cursor-pointer">
                            Update Fuel Price
                        </button>
                    </div>
                </div>

                <!-- Operational Allowance Rates Card -->
                <div class="p-4 rounded-lg border border-zinc-200 bg-zinc-50/50 dark:border-zinc-800 dark:bg-zinc-900/40 space-y-3">
                    <div class="flex items-center justify-between">
                        <span class="font-semibold text-zinc-800 dark:text-zinc-200">Operational Allowance Rates</span>
                        <button onclick="saveOperationalParams()" id="modal-save-ops-btn" class="px-2.5 py-1 rounded-md text-xs font-medium bg-zinc-900 hover:bg-zinc-800 dark:bg-zinc-100 dark:hover:bg-zinc-200 text-zinc-50 dark:text-zinc-900 transition shadow-xs cursor-pointer">
                            Save Rates
                        </button>
                    </div>
                    <div class="grid grid-cols-2 sm:grid-cols-4 gap-2.5">
                        <div>
                            <label class="block text-[11px] text-zinc-500 mb-1">Meal Rate ($/meal)</label>
                            <input type="number" id="modal-meal-rate" step="0.5" class="w-full bg-white dark:bg-zinc-900 border border-zinc-300 dark:border-zinc-700 rounded-md px-2.5 py-1 text-xs font-mono">
                        </div>
                        <div>
                            <label class="block text-[11px] text-zinc-500 mb-1">Accom. Rate ($/night)</label>
                            <input type="number" id="modal-accom-rate" step="1.0" class="w-full bg-white dark:bg-zinc-900 border border-zinc-300 dark:border-zinc-700 rounded-md px-2.5 py-1 text-xs font-mono">
                        </div>
                        <div>
                            <label class="block text-[11px] text-zinc-500 mb-1">Budget Threshold (%)</label>
                            <input type="number" id="modal-budget-pct" step="0.5" class="w-full bg-white dark:bg-zinc-900 border border-zinc-300 dark:border-zinc-700 rounded-md px-2.5 py-1 text-xs font-mono">
                        </div>
                        <div>
                            <label class="block text-[11px] text-zinc-500 mb-1">Van Surcharge ($)</label>
                            <input type="number" id="modal-van-surcharge" step="1.0" class="w-full bg-white dark:bg-zinc-900 border border-zinc-300 dark:border-zinc-700 rounded-md px-2.5 py-1 text-xs font-mono">
                        </div>
                    </div>
                </div>

                <!-- City Delivery Rules Table -->
                <div class="space-y-2">
                    <div class="flex items-center justify-between">
                        <span class="font-semibold text-zinc-800 dark:text-zinc-200">Delivery Corridors & City Rules</span>
                        <div class="flex items-center gap-2">
                            <input type="text" id="modal-city-search" oninput="filterCityRulesModal()" placeholder="Search city or corridor..." class="px-2.5 py-1 rounded-md border border-zinc-300 dark:border-zinc-700 bg-white dark:bg-zinc-900 text-xs w-44">
                            <span id="modal-city-count" class="text-xs text-zinc-500"></span>
                        </div>
                    </div>
                    <div class="border border-zinc-200 dark:border-zinc-800 rounded-lg overflow-hidden max-h-72 overflow-y-auto">
                        <table class="w-full text-left text-xs">
                            <thead class="bg-zinc-50 dark:bg-zinc-900 text-zinc-500 sticky top-0 border-b border-zinc-200 dark:border-zinc-800 font-medium">
                                <tr>
                                    <th class="px-3.5 py-2.5">City</th>
                                    <th class="px-3.5 py-2.5">Corridor / Route</th>
                                    <th class="px-3.5 py-2.5">Distance (KM)</th>
                                    <th class="px-3.5 py-2.5">Min Sales (Truck)</th>
                                    <th class="px-3.5 py-2.5">Min Sales (Van)</th>
                                    <th class="px-3.5 py-2.5 text-right">Action</th>
                                </tr>
                            </thead>
                            <tbody id="modal-city-rules-tbody" class="divide-y divide-zinc-200 dark:divide-zinc-800 text-zinc-800 dark:text-zinc-200"></tbody>
                        </table>
                    </div>
                </div>
            </div>
            <div class="p-3 border-t border-zinc-200 dark:border-zinc-800 flex justify-end shrink-0">
                <button onclick="closeCityConfigModal()" class="px-4 py-1.5 rounded-md text-xs font-medium border border-zinc-200 bg-white hover:bg-zinc-100 dark:border-zinc-800 dark:bg-zinc-900 dark:hover:bg-zinc-800 transition cursor-pointer">
                    Close
                </button>
            </div>
        </div>
    </div>

    <!-- Modal 2: Clear Payment Modal -->
    <div id="clearPaymentModal" class="modal-overlay fixed inset-0 z-50 hidden flex items-center justify-center p-3 sm:p-4 bg-zinc-950/60 backdrop-blur-xs overscroll-contain">
        <div class="modal-card bg-white dark:bg-zinc-950 border border-zinc-200 dark:border-zinc-800 rounded-xl w-full max-w-md flex flex-col shadow-2xl overflow-hidden">
            <div class="p-4 border-b border-zinc-200 dark:border-zinc-800 flex items-center justify-between shrink-0">
                <div>
                    <h3 class="text-base font-semibold text-zinc-900 dark:text-zinc-100">Clear Sales Rep Debt Payment</h3>
                    <p class="text-xs text-zinc-500 dark:text-zinc-400">Record an accounts offset to reduce outstanding shortfall balance</p>
                </div>
                <button onclick="closeClearPaymentModal()" class="p-1 rounded-md text-zinc-400 hover:text-zinc-600 dark:hover:text-zinc-200 transition cursor-pointer">✕</button>
            </div>
            <div class="p-4 sm:p-5 space-y-3.5 text-xs">
                <div>
                    <label class="block font-medium text-zinc-700 dark:text-zinc-300 mb-1">Sales Representative</label>
                    <select id="modal-pay-salesperson" onchange="onSelectPaySalesperson(this.value)" class="w-full bg-white dark:bg-zinc-900 border border-zinc-300 dark:border-zinc-700 rounded-md px-3 py-1.5 text-xs font-medium"></select>
                </div>
                <div class="p-3 rounded-lg bg-zinc-50 dark:bg-zinc-900/60 border border-zinc-200/80 dark:border-zinc-800/80 flex items-center justify-between">
                    <span class="text-zinc-500">Current Outstanding Debt:</span>
                    <span class="text-sm font-bold font-mono text-rose-600 dark:text-rose-400" id="modal-pay-current-balance">$0.00</span>
                </div>
                <div>
                    <div class="flex items-center justify-between mb-1">
                        <label class="font-medium text-zinc-700 dark:text-zinc-300">Amount Cleared ($ USD)</label>
                        <button type="button" onclick="fillFullClearance()" class="text-[11px] text-blue-600 dark:text-blue-400 hover:underline cursor-pointer">Full Balance</button>
                    </div>
                    <input type="number" id="modal-pay-amount" step="0.01" min="0.01" class="w-full bg-white dark:bg-zinc-900 border border-zinc-300 dark:border-zinc-700 rounded-md px-3 py-1.5 text-xs font-mono font-bold">
                </div>
                <div>
                    <label class="block font-medium text-zinc-700 dark:text-zinc-300 mb-1">Payment Method</label>
                    <select id="modal-pay-method" class="w-full bg-white dark:bg-zinc-900 border border-zinc-300 dark:border-zinc-700 rounded-md px-3 py-1.5 text-xs">
                        <option value="DEBT_WRITE_OFF">Management Debt Write-Off / Waiver (Approved by Sujit)</option>
                        <option value="BANK_TRANSFER">Bank Transfer (Ecocash / Nostro / RTGS)</option>
                        <option value="CASH">Cash Deposit</option>
                        <option value="PAYROLL_DEDUCTION">Salary / Commission Deduction</option>
                        <option value="CREDIT_NOTE">Customer Credit Note Offset</option>
                    </select>
                </div>
                <div>
                    <label class="block font-medium text-zinc-700 dark:text-zinc-300 mb-1">Remarks / Audit Note</label>
                    <textarea id="modal-pay-remarks" rows="2" placeholder="Optional audit memo or justification" class="w-full bg-white dark:bg-zinc-900 border border-zinc-300 dark:border-zinc-700 rounded-md px-3 py-1.5 text-xs"></textarea>
                </div>
                <div id="modal-pay-feedback" class="text-xs font-medium hidden"></div>
            </div>
            <div class="p-3 border-t border-zinc-200 dark:border-zinc-800 flex items-center justify-end gap-2 shrink-0">
                <button type="button" onclick="closeClearPaymentModal()" class="px-3.5 py-1.5 rounded-md text-xs font-medium border border-zinc-200 bg-white hover:bg-zinc-100 dark:border-zinc-800 dark:bg-zinc-900 dark:hover:bg-zinc-800 transition cursor-pointer">
                    Cancel
                </button>
                <button type="button" onclick="submitClearPayment()" id="modal-submit-pay-btn" class="px-4 py-1.5 rounded-md text-xs font-medium bg-emerald-600 hover:bg-emerald-700 text-white transition shadow-xs cursor-pointer">
                    Record Payment
                </button>
            </div>
        </div>
    </div>

    <!-- Modal 3: Audit Logs Modal -->
    <div id="auditLogsModal" class="modal-overlay fixed inset-0 z-50 hidden flex items-center justify-center p-3 sm:p-4 bg-zinc-950/60 backdrop-blur-xs overscroll-contain">
        <div class="modal-card bg-white dark:bg-zinc-950 border border-zinc-200 dark:border-zinc-800 rounded-xl w-full max-w-4xl max-h-[90vh] flex flex-col shadow-2xl overflow-hidden">
            <div class="p-4 border-b border-zinc-200 dark:border-zinc-800 flex items-center justify-between shrink-0">
                <div>
                    <h3 class="text-base font-semibold text-zinc-900 dark:text-zinc-100">System Audit Logs</h3>
                    <p class="text-xs text-zinc-500 dark:text-zinc-400">Chronological history of rate changes, clearances, and security events</p>
                </div>
                <button onclick="closeAuditLogsModal()" class="p-1 rounded-md text-zinc-400 hover:text-zinc-600 dark:hover:text-zinc-200 transition cursor-pointer">✕</button>
            </div>
            <div class="p-4 overflow-y-auto flex-1 overscroll-contain">
                <div class="border border-zinc-200 dark:border-zinc-800 rounded-lg overflow-hidden">
                    <table class="w-full text-left text-xs">
                        <thead class="bg-zinc-50 dark:bg-zinc-900 text-zinc-500 font-medium border-b border-zinc-200 dark:border-zinc-800">
                            <tr>
                                <th class="px-3 py-2">Timestamp</th>
                                <th class="px-3 py-2">User</th>
                                <th class="px-3 py-2">Action</th>
                                <th class="px-3 py-2">Entity</th>
                                <th class="px-3 py-2">Details</th>
                            </tr>
                        </thead>
                        <tbody id="modal-audit-tbody" class="divide-y divide-zinc-200 dark:divide-zinc-800 text-zinc-800 dark:text-zinc-200">
                            <tr><td colspan="5" class="p-4 text-center text-zinc-400">Loading audit history...</td></tr>
                        </tbody>
                    </table>
                </div>
            </div>
            <div class="p-3 border-t border-zinc-200 dark:border-zinc-800 flex justify-end shrink-0">
                <button onclick="closeAuditLogsModal()" class="px-4 py-1.5 rounded-md text-xs font-medium border border-zinc-200 bg-white hover:bg-zinc-100 dark:border-zinc-800 dark:bg-zinc-900 dark:hover:bg-zinc-800 transition cursor-pointer">
                    Close
                </button>
            </div>
        </div>
    </div>

    <!-- Modal 4: Add / Edit Truck Modal -->
    <div id="addTruckModal" class="modal-overlay fixed inset-0 z-50 hidden flex items-center justify-center p-3 sm:p-4 bg-zinc-950/60 backdrop-blur-xs overscroll-contain">
        <div class="modal-card bg-white dark:bg-zinc-950 border border-zinc-200 dark:border-zinc-800 rounded-xl w-full max-w-md flex flex-col shadow-2xl overflow-hidden">
            <div class="p-4 border-b border-zinc-200 dark:border-zinc-800 flex items-center justify-between shrink-0">
                <div>
                    <h3 class="text-base font-semibold text-zinc-900 dark:text-zinc-100" id="truck-modal-title">Register Fleet Vehicle</h3>
                    <p class="text-xs text-zinc-500 dark:text-zinc-400">Add or update delivery truck details</p>
                </div>
                <button onclick="closeAddTruckModal()" class="p-1 rounded-md text-zinc-400 hover:text-zinc-600 dark:hover:text-zinc-200 transition cursor-pointer">✕</button>
            </div>
            <div class="p-4 sm:p-5 space-y-3.5 text-xs">
                <input type="hidden" id="modal-truck-id">
                <div>
                    <label class="block font-medium text-zinc-700 dark:text-zinc-300 mb-1">Truck Number *</label>
                    <input type="number" id="modal-truck-number" placeholder="e.g. 14" class="w-full bg-white dark:bg-zinc-900 border border-zinc-300 dark:border-zinc-700 rounded-md px-3 py-1.5 text-xs font-mono">
                </div>
                <div>
                    <label class="block font-medium text-zinc-700 dark:text-zinc-300 mb-1">Plate Number *</label>
                    <input type="text" id="modal-truck-plate" placeholder="e.g. AGZ 7331" class="w-full bg-white dark:bg-zinc-900 border border-zinc-300 dark:border-zinc-700 rounded-md px-3 py-1.5 text-xs font-mono uppercase">
                </div>
                <div>
                    <label class="block font-medium text-zinc-700 dark:text-zinc-300 mb-1">Make & Model</label>
                    <input type="text" id="modal-truck-make" placeholder="e.g. Isuzu Forward 8-Ton" class="w-full bg-white dark:bg-zinc-900 border border-zinc-300 dark:border-zinc-700 rounded-md px-3 py-1.5 text-xs">
                </div>
                <div>
                    <label class="block font-medium text-zinc-700 dark:text-zinc-300 mb-1">Body Type</label>
                    <select id="modal-truck-body" class="w-full bg-white dark:bg-zinc-900 border border-zinc-300 dark:border-zinc-700 rounded-md px-3 py-1.5 text-xs">
                        <option value="FLATBED">Flatbed Heavy</option>
                        <option value="CLOSED_BOX">Closed Box Cargo</option>
                        <option value="VAN">Delivery Van</option>
                        <option value="CURTAIN_SIDE">Curtain Side</option>
                    </select>
                </div>
                <div>
                    <label class="block font-medium text-zinc-700 dark:text-zinc-300 mb-1">Home Depot</label>
                    <input type="text" id="modal-truck-depot" placeholder="e.g. Harare Central" class="w-full bg-white dark:bg-zinc-900 border border-zinc-300 dark:border-zinc-700 rounded-md px-3 py-1.5 text-xs">
                </div>
                <div class="flex items-center gap-2 pt-1">
                    <input type="checkbox" id="modal-truck-active" checked class="rounded border-zinc-300">
                    <label for="modal-truck-active" class="text-xs font-medium text-zinc-700 dark:text-zinc-300 cursor-pointer">Active in fleet</label>
                </div>
                <div id="modal-truck-feedback" class="text-xs font-medium hidden"></div>
            </div>
            <div class="p-3 border-t border-zinc-200 dark:border-zinc-800 flex items-center justify-end gap-2 shrink-0">
                <button type="button" onclick="closeAddTruckModal()" class="px-3.5 py-1.5 rounded-md text-xs font-medium border border-zinc-200 bg-white hover:bg-zinc-100 dark:border-zinc-800 dark:bg-zinc-900 dark:hover:bg-zinc-800 transition cursor-pointer">
                    Cancel
                </button>
                <button type="button" onclick="submitSaveTruck()" id="modal-submit-truck-btn" class="px-4 py-1.5 rounded-md text-xs font-medium bg-zinc-900 hover:bg-zinc-800 dark:bg-zinc-100 dark:hover:bg-zinc-200 text-zinc-50 dark:text-zinc-900 transition shadow-xs cursor-pointer">
                    Save Vehicle
                </button>
            </div>
        </div>
    </div>

    <!-- Modal 5: Add / Edit Driver Modal -->
    <div id="addDriverModal" class="modal-overlay fixed inset-0 z-50 hidden flex items-center justify-center p-3 sm:p-4 bg-zinc-950/60 backdrop-blur-xs overscroll-contain">
        <div class="modal-card bg-white dark:bg-zinc-950 border border-zinc-200 dark:border-zinc-800 rounded-xl w-full max-w-md flex flex-col shadow-2xl overflow-hidden">
            <div class="p-4 border-b border-zinc-200 dark:border-zinc-800 flex items-center justify-between shrink-0">
                <div>
                    <h3 class="text-base font-semibold text-zinc-900 dark:text-zinc-100" id="driver-modal-title">Register Commercial Driver</h3>
                    <p class="text-xs text-zinc-500 dark:text-zinc-400">Add or update commercial driver details</p>
                </div>
                <button onclick="closeAddDriverModal()" class="p-1 rounded-md text-zinc-400 hover:text-zinc-600 dark:hover:text-zinc-200 transition cursor-pointer">✕</button>
            </div>
            <div class="p-4 sm:p-5 space-y-3.5 text-xs">
                <input type="hidden" id="modal-driver-id">
                <div>
                    <label class="block font-medium text-zinc-700 dark:text-zinc-300 mb-1">Full Name *</label>
                    <input type="text" id="modal-driver-name" placeholder="e.g. Farai Moyo" class="w-full bg-white dark:bg-zinc-900 border border-zinc-300 dark:border-zinc-700 rounded-md px-3 py-1.5 text-xs">
                </div>
                <div>
                    <label class="block font-medium text-zinc-700 dark:text-zinc-300 mb-1">WhatsApp Phone Number *</label>
                    <input type="text" id="modal-driver-phone" placeholder="e.g. 263771234567" class="w-full bg-white dark:bg-zinc-900 border border-zinc-300 dark:border-zinc-700 rounded-md px-3 py-1.5 text-xs font-mono">
                </div>
                <div>
                    <label class="block font-medium text-zinc-700 dark:text-zinc-300 mb-1">Role Designation</label>
                    <select id="modal-driver-role" class="w-full bg-white dark:bg-zinc-900 border border-zinc-300 dark:border-zinc-700 rounded-md px-3 py-1.5 text-xs">
                        <option value="Commercial Driver">Commercial Driver</option>
                        <option value="Fleet Relief Driver">Fleet Relief Driver</option>
                        <option value="Senior Long-Distance Driver">Senior Long-Distance Driver</option>
                    </select>
                </div>
                <div class="flex items-center gap-2 pt-1">
                    <input type="checkbox" id="modal-driver-active" checked class="rounded border-zinc-300">
                    <label for="modal-driver-active" class="text-xs font-medium text-zinc-700 dark:text-zinc-300 cursor-pointer">Active roster</label>
                </div>
                <div id="modal-driver-feedback" class="text-xs font-medium hidden"></div>
            </div>
            <div class="p-3 border-t border-zinc-200 dark:border-zinc-800 flex items-center justify-end gap-2 shrink-0">
                <button type="button" onclick="closeAddDriverModal()" class="px-3.5 py-1.5 rounded-md text-xs font-medium border border-zinc-200 bg-white hover:bg-zinc-100 dark:border-zinc-800 dark:bg-zinc-900 dark:hover:bg-zinc-800 transition cursor-pointer">
                    Cancel
                </button>
                <button type="button" onclick="submitSaveDriver()" id="modal-submit-driver-btn" class="px-4 py-1.5 rounded-md text-xs font-medium bg-zinc-900 hover:bg-zinc-800 dark:bg-zinc-100 dark:hover:bg-zinc-200 text-zinc-50 dark:text-zinc-900 transition shadow-xs cursor-pointer">
                    Save Driver
                </button>
            </div>
        </div>
    </div>

    <!-- Modal 6: Add / Edit Sales Rep Modal -->
    <div id="addSalesRepModal" class="modal-overlay fixed inset-0 z-50 hidden flex items-center justify-center p-3 sm:p-4 bg-zinc-950/60 backdrop-blur-xs overscroll-contain">
        <div class="modal-card bg-white dark:bg-zinc-950 border border-zinc-200 dark:border-zinc-800 rounded-xl w-full max-w-md flex flex-col shadow-2xl overflow-hidden">
            <div class="p-4 border-b border-zinc-200 dark:border-zinc-800 flex items-center justify-between shrink-0">
                <div>
                    <h3 class="text-base font-semibold text-zinc-900 dark:text-zinc-100" id="salesrep-modal-title">Register Sales Representative</h3>
                    <p class="text-xs text-zinc-500 dark:text-zinc-400">Add or update commercial sales rep details</p>
                </div>
                <button onclick="closeAddSalesRepModal()" class="p-1 rounded-md text-zinc-400 hover:text-zinc-600 dark:hover:text-zinc-200 transition cursor-pointer">✕</button>
            </div>
            <div class="p-4 sm:p-5 space-y-3.5 text-xs">
                <input type="hidden" id="modal-salesrep-id">
                <div>
                    <label class="block font-medium text-zinc-700 dark:text-zinc-300 mb-1">Full Name *</label>
                    <input type="text" id="modal-salesrep-name" placeholder="e.g. Kudzai Chidzero" class="w-full bg-white dark:bg-zinc-900 border border-zinc-300 dark:border-zinc-700 rounded-md px-3 py-1.5 text-xs">
                </div>
                <div>
                    <label class="block font-medium text-zinc-700 dark:text-zinc-300 mb-1">WhatsApp Phone *</label>
                    <input type="text" id="modal-salesrep-phone" placeholder="e.g. 263771234567" class="w-full bg-white dark:bg-zinc-900 border border-zinc-300 dark:border-zinc-700 rounded-md px-3 py-1.5 text-xs font-mono">
                </div>
                <div>
                    <label class="block font-medium text-zinc-700 dark:text-zinc-300 mb-1">Company Division *</label>
                    <select id="modal-salesrep-company" class="w-full bg-white dark:bg-zinc-900 border border-zinc-300 dark:border-zinc-700 rounded-md px-3 py-1.5 text-xs">
                        <option value="LG Plast">LG Plast</option>
                        <option value="Tagoneswa Hardware">Tagoneswa Hardware</option>
                        <option value="Kreckle Foods">Kreckle Foods</option>
                    </select>
                </div>
                <div>
                    <label class="block font-medium text-zinc-700 dark:text-zinc-300 mb-1">Role Designation</label>
                    <select id="modal-salesrep-role" class="w-full bg-white dark:bg-zinc-900 border border-zinc-300 dark:border-zinc-700 rounded-md px-3 py-1.5 text-xs">
                        <option value="SALES_REPRESENTATIVE">Sales Representative</option>
                        <option value="SENIOR_SALES_REPRESENTATIVE">Senior Sales Representative</option>
                        <option value="SALES_ADMIN">Sales Administrator</option>
                    </select>
                </div>
                <div>
                    <label class="block font-medium text-zinc-700 dark:text-zinc-300 mb-1">Email Address</label>
                    <input type="email" id="modal-salesrep-email" placeholder="e.g. kudzai@tagoneswa.co.zw" class="w-full bg-white dark:bg-zinc-900 border border-zinc-300 dark:border-zinc-700 rounded-md px-3 py-1.5 text-xs">
                </div>
                <div class="flex items-center gap-2 pt-1">
                    <input type="checkbox" id="modal-salesrep-active" checked class="rounded border-zinc-300">
                    <label for="modal-salesrep-active" class="text-xs font-medium text-zinc-700 dark:text-zinc-300 cursor-pointer">Active roster</label>
                </div>
                <div id="modal-salesrep-feedback" class="text-xs font-medium hidden"></div>
            </div>
            <div class="p-3 border-t border-zinc-200 dark:border-zinc-800 flex items-center justify-end gap-2 shrink-0">
                <button type="button" onclick="closeAddSalesRepModal()" class="px-3.5 py-1.5 rounded-md text-xs font-medium border border-zinc-200 bg-white hover:bg-zinc-100 dark:border-zinc-800 dark:bg-zinc-900 dark:hover:bg-zinc-800 transition cursor-pointer">
                    Cancel
                </button>
                <button type="button" onclick="submitSaveSalesRep()" id="modal-submit-salesrep-btn" class="px-4 py-1.5 rounded-md text-xs font-medium bg-zinc-900 hover:bg-zinc-800 dark:bg-zinc-100 dark:hover:bg-zinc-200 text-zinc-50 dark:text-zinc-900 transition shadow-xs cursor-pointer">
                    Save Rep
                </button>
            </div>
        </div>
    </div>

    <!-- Modal 7: User Management & Permissions (MASTER_ADMIN only) -->
    <div id="userManagementModal" class="modal-overlay fixed inset-0 z-50 hidden flex items-center justify-center p-3 sm:p-4 bg-zinc-950/60 backdrop-blur-xs overscroll-contain">
        <div class="modal-card bg-white dark:bg-zinc-950 border border-zinc-200 dark:border-zinc-800 rounded-xl w-full max-w-5xl xl:max-w-6xl max-h-[92vh] flex flex-col shadow-2xl overflow-hidden">
            <div class="p-4 border-b border-zinc-200 dark:border-zinc-800 flex items-center justify-between shrink-0">
                <div>
                    <h3 class="text-base font-semibold text-zinc-900 dark:text-zinc-100">User Management & Permissions</h3>
                    <p class="text-xs text-zinc-500 dark:text-zinc-400">Manage user accounts, roles, and delegated access</p>
                </div>
                <div class="flex items-center gap-2">
                    <button onclick="openCreateUserModal()" class="px-3 py-1.5 rounded-md text-xs font-medium bg-zinc-900 hover:bg-zinc-800 dark:bg-zinc-100 dark:hover:bg-zinc-200 text-zinc-50 dark:text-zinc-900 transition shadow-xs cursor-pointer">
                        + Add Account
                    </button>
                    <button onclick="loadUsersList()" class="p-1.5 rounded-md text-zinc-600 dark:text-zinc-400 hover:bg-zinc-100 dark:hover:bg-zinc-800 text-xs transition cursor-pointer" title="Refresh User Accounts">
                        <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"/></svg>
                    </button>
                    <button onclick="closeUserManagementModal()" class="p-1.5 rounded-md text-zinc-400 hover:text-zinc-600 dark:hover:text-zinc-200 transition cursor-pointer">✕</button>
                </div>
            </div>

            <div class="p-4 sm:p-5 overflow-y-auto space-y-5 flex-1 overscroll-contain text-xs">
                <!-- User Accounts Overview Table -->
                <div class="border border-zinc-200 dark:border-zinc-800 rounded-lg overflow-hidden">
                    <div class="p-3 bg-zinc-50 dark:bg-zinc-900/60 border-b border-zinc-200 dark:border-zinc-800 flex items-center justify-between">
                        <span class="font-semibold text-zinc-800 dark:text-zinc-200">Registered Accounts</span>
                        <span id="user-mgmt-count" class="text-xs text-zinc-500">Loading...</span>
                    </div>
                    <div class="max-h-[36vh] overflow-y-auto">
                        <table class="w-full text-left text-xs">
                            <thead class="bg-zinc-50 dark:bg-zinc-900 text-zinc-500 sticky top-0 border-b border-zinc-200 dark:border-zinc-800 font-medium">
                                <tr>
                                    <th class="px-3 py-2">User</th>
                                    <th class="px-3 py-2">Role</th>
                                    <th class="px-3 py-2">Status</th>
                                    <th class="px-3 py-2">Active Device</th>
                                    <th class="px-3 py-2">Overrides</th>
                                    <th class="px-3 py-2 text-right">Actions</th>
                                </tr>
                            </thead>
                            <tbody id="user-mgmt-tbody" class="divide-y divide-zinc-200 dark:divide-zinc-800 text-zinc-800 dark:text-zinc-200">
                                <tr><td colspan="6" class="p-4 text-center text-zinc-400">Loading accounts...</td></tr>
                            </tbody>
                        </table>
                    </div>
                </div>

                <!-- Selected User Panel -->
                <div id="user-mgmt-detail-panel" class="hidden bg-zinc-50/60 dark:bg-zinc-900/40 border border-zinc-200 dark:border-zinc-800 rounded-lg p-4 space-y-4">
                    <div class="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-zinc-200 dark:border-zinc-800 pb-3">
                        <div>
                            <span class="text-[10px] font-semibold uppercase tracking-wider text-zinc-500">Account Configuration</span>
                            <h4 class="text-sm font-bold text-zinc-900 dark:text-zinc-100 mt-0.5" id="selected-user-header">--</h4>
                        </div>
                        <div class="flex flex-wrap items-center gap-2">
                            <select id="selected-user-role" class="bg-white dark:bg-zinc-900 border border-zinc-300 dark:border-zinc-700 rounded-md px-2.5 py-1 text-xs font-medium"></select>
                            <label class="flex items-center gap-1.5 text-xs font-medium text-zinc-700 dark:text-zinc-300">
                                <input type="checkbox" id="selected-user-active" class="rounded border-zinc-300">
                                Active
                            </label>
                            <button onclick="saveSelectedUserRole()" class="px-3 py-1 rounded-md text-xs font-medium bg-zinc-900 hover:bg-zinc-800 dark:bg-zinc-100 dark:hover:bg-zinc-200 text-zinc-50 dark:text-zinc-900 transition shadow-xs cursor-pointer">
                                Update Role
                            </button>
                        </div>
                    </div>

                    <div class="bg-white dark:bg-zinc-900/60 rounded-md p-3 flex flex-wrap items-center justify-between gap-2 border border-zinc-200 dark:border-zinc-800">
                        <div class="text-[11px] text-zinc-500" id="selected-user-session-info">
                            Single active session enforced. Logins on secondary devices disconnect earlier sessions.
                        </div>
                        <div class="flex items-center gap-2">
                            <button id="btn-force-logout-panel" onclick="revokeUserSessions(selectedMgmtUsername)" class="px-2.5 py-1 rounded-md text-xs font-medium border border-amber-300 bg-amber-50 text-amber-800 hover:bg-amber-100 dark:border-amber-800 dark:bg-amber-950/40 dark:text-amber-300 transition cursor-pointer">
                                Disconnect Devices
                            </button>
                            <button id="btn-toggle-status-panel" onclick="toggleSelectedUserStatus()" class="px-2.5 py-1 rounded-md text-xs font-medium border border-zinc-300 bg-zinc-100 text-zinc-800 hover:bg-zinc-200 dark:border-zinc-700 dark:bg-zinc-800 dark:text-zinc-200 transition cursor-pointer">
                                Suspend Account
                            </button>
                            <button id="btn-delete-user-panel" onclick="deleteUserAccount(selectedMgmtUsername)" class="px-2.5 py-1 rounded-md text-xs font-medium bg-rose-600 hover:bg-rose-700 text-white transition shadow-xs cursor-pointer">
                                Delete Account
                            </button>
                        </div>
                    </div>

                    <!-- Permission Overrides Matrix -->
                    <div>
                        <div class="flex items-center justify-between mb-2">
                            <span class="font-semibold text-zinc-800 dark:text-zinc-200">Permission Overrides</span>
                            <span class="text-[11px] text-zinc-400">Overrides role default</span>
                        </div>
                        <div class="grid grid-cols-1 md:grid-cols-2 gap-2" id="user-perms-matrix"></div>
                    </div>
                </div>

                <div id="user-mgmt-feedback" class="text-xs font-medium hidden"></div>
            </div>

            <div class="p-3 border-t border-zinc-200 dark:border-zinc-800 flex justify-end shrink-0">
                <button onclick="closeUserManagementModal()" class="px-4 py-1.5 rounded-md text-xs font-medium border border-zinc-200 bg-white hover:bg-zinc-100 dark:border-zinc-800 dark:bg-zinc-900 dark:hover:bg-zinc-800 transition cursor-pointer">
                    Close
                </button>
            </div>
        </div>
    </div>

    <!-- Modal 8: Add New User Account Modal -->
    <div id="createUserModal" class="modal-overlay fixed inset-0 z-[70] hidden flex items-center justify-center p-3 sm:p-4 bg-zinc-950/70 backdrop-blur-xs overscroll-contain" style="z-index: 70;">
        <div class="modal-card bg-white dark:bg-zinc-950 border border-zinc-200 dark:border-zinc-800 rounded-xl w-full max-w-md flex flex-col shadow-2xl overflow-hidden" style="z-index: 71;">
            <div class="p-4 border-b border-zinc-200 dark:border-zinc-800 flex items-center justify-between shrink-0">
                <div>
                    <h3 class="text-base font-semibold text-zinc-900 dark:text-zinc-100">Create New User Account</h3>
                    <p class="text-xs text-zinc-500 dark:text-zinc-400">Add an authorized portal login</p>
                </div>
                <button onclick="closeCreateUserModal()" class="p-1 rounded-md text-zinc-400 hover:text-zinc-600 dark:hover:text-zinc-200 transition cursor-pointer">✕</button>
            </div>
            <div class="p-4 sm:p-5 space-y-3.5 text-xs">
                <div>
                    <label class="block font-medium text-zinc-700 dark:text-zinc-300 mb-1">Username (Login ID) *</label>
                    <input type="text" id="create-user-username" placeholder="e.g. jsmith" class="w-full bg-white dark:bg-zinc-900 border border-zinc-300 dark:border-zinc-700 rounded-md px-3 py-1.5 text-xs">
                </div>
                <div>
                    <label class="block font-medium text-zinc-700 dark:text-zinc-300 mb-1">Temporary Password *</label>
                    <input type="password" id="create-user-password" placeholder="Min. 6 characters" class="w-full bg-white dark:bg-zinc-900 border border-zinc-300 dark:border-zinc-700 rounded-md px-3 py-1.5 text-xs font-mono">
                </div>
                <div>
                    <label class="block font-medium text-zinc-700 dark:text-zinc-300 mb-1">Full Name</label>
                    <input type="text" id="create-user-fullname" placeholder="e.g. John Smith" class="w-full bg-white dark:bg-zinc-900 border border-zinc-300 dark:border-zinc-700 rounded-md px-3 py-1.5 text-xs">
                </div>
                <div>
                    <label class="block font-medium text-zinc-700 dark:text-zinc-300 mb-1">System Role *</label>
                    <select id="create-user-role" class="w-full bg-white dark:bg-zinc-900 border border-zinc-300 dark:border-zinc-700 rounded-md px-3 py-1.5 text-xs">
                        <option value="SALES_ADMIN">SALES_ADMIN (Sales Orders & Fleet Approvals)</option>
                        <option value="ACCOUNTS_USER">ACCOUNTS_USER (Finance & Cash Ledgers)</option>
                        <option value="FLEET_ADMIN">FLEET_ADMIN (Fleet & Dispatch Operations)</option>
                        <option value="LOGISTICS_MANAGER">LOGISTICS_MANAGER (Trips & Logistics Lead)</option>
                        <option value="LOGISTICS_ADMIN">LOGISTICS_ADMIN (Workshop & Maintenance)</option>
                        <option value="IT_ADMIN">IT_ADMIN (IT Support Tickets)</option>
                        <option value="PROJECTS_ADMIN">PROJECTS_ADMIN (Building Projects)</option>
                        <option value="EXECUTIVE_OBSERVER">EXECUTIVE_OBSERVER (Read-Only Observer)</option>
                    </select>
                </div>
                <div class="grid grid-cols-2 gap-2">
                    <div>
                        <label class="block font-medium text-zinc-700 dark:text-zinc-300 mb-1">Company</label>
                        <input type="text" id="create-user-company" placeholder="e.g. LG Plast" class="w-full bg-white dark:bg-zinc-900 border border-zinc-300 dark:border-zinc-700 rounded-md px-3 py-1.5 text-xs">
                    </div>
                    <div>
                        <label class="block font-medium text-zinc-700 dark:text-zinc-300 mb-1">Phone</label>
                        <input type="text" id="create-user-phone" placeholder="e.g. 26378..." class="w-full bg-white dark:bg-zinc-900 border border-zinc-300 dark:border-zinc-700 rounded-md px-3 py-1.5 text-xs font-mono">
                    </div>
                </div>
            </div>
            <div class="p-3 border-t border-zinc-200 dark:border-zinc-800 flex items-center justify-end gap-2 shrink-0">
                <button type="button" onclick="closeCreateUserModal()" class="px-3.5 py-1.5 rounded-md text-xs font-medium border border-zinc-200 bg-white hover:bg-zinc-100 dark:border-zinc-800 dark:bg-zinc-900 dark:hover:bg-zinc-800 transition cursor-pointer">
                    Cancel
                </button>
                <button type="button" onclick="submitCreateUser()" id="modal-submit-create-user-btn" class="px-4 py-1.5 rounded-md text-xs font-medium bg-zinc-900 hover:bg-zinc-800 dark:bg-zinc-100 dark:hover:bg-zinc-200 text-zinc-50 dark:text-zinc-900 transition shadow-xs cursor-pointer">
                    Create User
                </button>
            </div>
        </div>
    </div>

    <!-- Table pagination handled via renderPaginationControls in /static/js/dashboard.js -->
    <script>
        window.canViewBalances = {'true' if can_view_balances else 'false'};
        window.initialAllowedDomains = {allowed_domains_json};
        window.initialDefaultTab = '{default_tab}';
        window.currentUserRole = '{user.get("role", "")}';
        window.currentUserCompany = '{user.get("company", "")}';
        window.currentUserName = `{user.get("name", "")}`;
    </script>
    <script src="/static/js/dashboard.js?v=2.6.0"></script>
</body>
</html>"""
    return HTMLResponse(content=html_content)
