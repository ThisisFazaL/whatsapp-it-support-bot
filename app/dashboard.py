# -*- coding: utf-8 -*-
import logging
import datetime
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
    WebUser, UserCustomPermission, get_sales_rep_pending_balance
)
from app.workshop.models import (
    WorkshopTicket, WorkshopTruck, WorkshopStaff, WorkshopPartsRequest
)
from app.auth import (
    authenticate_user, create_session_token, get_current_user_from_request,
    COOKIE_NAME, SESSION_MAX_AGE, USERS_DB,
    require_permission, user_has_permission, get_effective_permissions,
    ALL_PERMISSIONS, ROLE_DEFAULT_PERMISSIONS, set_user_custom_permission,
    USER_CUSTOM_PERMISSIONS_CACHE
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

            <button type="submit" class="w-full bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-700 hover:to-indigo-700 active:scale-[0.99] text-white font-bold py-3.5 rounded-xl shadow-lg shadow-blue-500/25 transition duration-150 text-sm sm:text-base flex items-center justify-center gap-2 cursor-pointer" id="loginBtn">
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
    """Verifies credentials via JSON or Form, generates signed session token, and sets HttpOnly cookie."""
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

    user = authenticate_user(str(username), str(password))
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials. Access restricted to authorized personnel."
        )

    token = create_session_token(user["username"], user["role"])
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
async def logout():
    """Invalidates session cookie and redirects directly to login."""
    resp = RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)
    resp.delete_cookie(key=COOKIE_NAME, path="/")
    return resp

@router.post("/api/logout")
async def api_logout():
    """API endpoint to explicitly invalidate session."""
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
    ledger_entry = FleetPendingLedger(
        salesperson_phone=phone,
        salesperson_name=name,
        entry_type="PAYMENT_CLEARED_BY_ACCOUNTS",
        amount=-cleared_amount,
        notes=f"Payment cleared via {payment_method}. Ref: {reference}. Notes: {remarks}",
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
            "is_active": wu.is_active,
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
                "email": "",
                "phone": "",
                "is_active": True,
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
        if full_name:
            USERS_DB[username]["name"] = full_name

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
                "category": f"{t.category_name} ➔ {t.subcategory_name}" if t.category_name else "General Defect",
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

        # A. Aggregate Salesperson Pending Balances & Performance
        salesperson_map = {}
        for entry in ledger_entries:
            p = entry.salesperson_phone
            if p not in salesperson_map:
                salesperson_map[p] = {
                    "phone": p,
                    "name": entry.salesperson_name or "Sales Rep",
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

        # Also register any salesperson who has trip approvals but no ledger entries yet
        for fa in fleet_approvals:
            p = fa.salesperson_phone
            if p and p not in salesperson_map:
                salesperson_map[p] = {
                    "phone": p,
                    "name": fa.salesperson_name or "Sales Rep",
                    "company": "Commercial Sales",
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
            .join(Department, Employee.department_id == Department.department_id, isouter=True)
            .options(selectinload(Employee.location), selectinload(Employee.department))
            .where(
                (Department.department_name.ilike("%Sales%")) |
                (Department.department_name.ilike("%Marketing%")) |
                (Employee.phone.in_(list(OFFICIAL_SALES_REPS_DIRECTORY.keys())))
            )
        )
        registered_sales_employees = (await db.execute(sales_dept_stmt)).scalars().all()
        for emp in registered_sales_employees:
            p = emp.phone
            comp = OFFICIAL_SALES_REPS_DIRECTORY.get(p, {}).get("company")
            if not comp and emp.location:
                comp = emp.location.location_name
            if not comp and emp.department:
                comp = emp.department.department_name
            if not comp:
                comp = "Commercial Sales"

            official_name = OFFICIAL_SALES_REPS_DIRECTORY.get(p, {}).get("name", emp.full_name)

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
                if str(salesperson_map[p].get("name", "")).startswith("Test Rep") or not salesperson_map[p].get("name"):
                    salesperson_map[p]["name"] = official_name

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

            approval_records.append({
                "id": fa.id,
                "trip_id": fa.trip_id,
                "salesperson_name": fa.salesperson_name or "Sales Rep",
                "salesperson_phone": fa.salesperson_phone,
                "destination_city": fa.destination_city,
                "route": fa.route or "--",
                "trip_sales_value": round(s_val, 2),
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

        fleet_stats["total_sales_value"] = round(fleet_stats["total_sales_value"], 2)
        fleet_stats["total_transport_charges"] = round(fleet_stats["total_transport_charges"], 2)
        fleet_stats["total_charged_customer"] = round(fleet_stats["total_charged_customer"], 2)
        fleet_stats["total_pending_recorded"] = round(fleet_stats["total_pending_recorded"], 2)

        # C. Detailed Ledger Entries Audit
        ledger_records = []
        for le in ledger_entries:
            ledger_records.append({
                "id": le.id,
                "salesperson_name": le.salesperson_name or "Sales Rep",
                "salesperson_phone": le.salesperson_phone,
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
            trips_list.append({
                "id": tr.id,
                "trip_id": tr.trip_id,
                "company_name": tr.company_name,
                "company": tr.company_name,
                "trip_sales_value": round(tr.trip_sales_value or 0.0, 2),
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
            payments_list.append({
                "id": pm.id,
                "salesperson_name": pm.salesperson_name or "Sales Rep",
                "salesperson_phone": pm.salesperson_phone,
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
            .join(Department, Employee.department_id == Department.department_id, isouter=True)
            .where(
                (Department.department_name.ilike("%Sales%")) |
                (Employee.phone.in_({sp["phone"] for sp in salespersons_list}))
            )
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
                "description": f"{needing_voucher} trip(s) approved awaiting fuel/allowance voucher; {needing_loading} awaiting loading & start odometer.{f' ⚠️ {discrepancy_trips} odometer discrepancy flagged!' if discrepancy_trips else ''}",
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
                sales_desc = f" (${fa['trip_sales_value']:,.2f})" if can_view_balances else ""
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
            "total_sales": round(tot_sales, 2),
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
            "avg_revenue_per_trip": avg_rev,
            "avg_opex_per_trip": avg_exp,
            "avg_allowance_per_trip": avg_alw,
            "fleet_utilization_pct": fleet_util,
            "workshop_impact_count": ws_impact,
            "shortfall_total": round(shortfall_tot, 2),
            "recovery_total": round(recovered_tot, 2),
            "recovery_rate_pct": rec_rate,
            "cleared_payments_total": round(cleared_tot, 2),
            "outstanding_debt_total": round(debt_tot, 2),
            "cities": top_cities,
            "routes": top_routes,
            "sales_trends": sales_trends
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
            "cities": [{"city": c["city"], "trips": c["trips"], "opex": c["opex"], "transport": c["transport"], "sales": 0.0} for c in top_cities],
            "routes": [{"route": r["route"], "city": r["city"], "trips": r["trips"], "opex": r["opex"], "transport": r["transport"], "sales": 0.0} for r in top_routes],
            "sales_trends": {
                "day_wise": {**sales_trends["day_wise"], "total": [0.0]*len(days_list), "lg_plast": [0.0]*len(days_list), "tagoneswa": [0.0]*len(days_list), "kreckle": [0.0]*len(days_list)},
                "month_wise": {**sales_trends["month_wise"], "total": [0.0]*len(months_list), "lg_plast": [0.0]*len(months_list), "tagoneswa": [0.0]*len(months_list), "kreckle": [0.0]*len(months_list)},
                "company_wise": {**sales_trends["company_wise"], "totals": [0.0, 0.0, 0.0], "day_lg": [0.0]*len(days_list), "day_tg": [0.0]*len(days_list), "day_kr": [0.0]*len(days_list), "month_lg": [0.0]*len(months_list), "month_tg": [0.0]*len(months_list), "month_kr": [0.0]*len(months_list)}
            }
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
    """Renders the executive white-themed 3-Domain Operations Dashboard with strict role-based domain access."""
    user = get_current_user_from_request(request)
    if not user:
        return RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)

    allowed = user.get("allowed_domains", ["it", "projects", "logistics", "fleet", "accounts", "admin"])
    default_tab = "fleet" if user["role"] in ("MASTER_ADMIN", "EXECUTIVE_OBSERVER", "FLEET_ADMIN", "SALES_ADMIN", "ACCOUNTS_USER", "LOGISTICS_MANAGER") else ("logistics" if user["role"] == "LOGISTICS_ADMIN" else ("projects" if user["role"] == "PROJECTS_ADMIN" else "it"))

    # Generate navigation tab buttons based on allowed domains
    tabs_html = []
    if "fleet" in allowed:
        tabs_html.append('<button id="btn-tab-fleet" onclick="switchDomain(\'fleet\')" class="tab-btn px-3.5 sm:px-4 py-2 rounded-xl text-xs font-bold text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-white transition flex items-center gap-1.5 whitespace-nowrap shrink-0 cursor-pointer">Sales to Fleet</button>')
    if "it" in allowed:
        tabs_html.append('<button id="btn-tab-it" onclick="switchDomain(\'it\')" class="tab-btn px-3.5 sm:px-4 py-2 rounded-xl text-xs font-bold text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-white transition flex items-center gap-1.5 whitespace-nowrap shrink-0 cursor-pointer">IT Support</button>')
    if "projects" in allowed:
        tabs_html.append('<button id="btn-tab-projects" onclick="switchDomain(\'projects\')" class="tab-btn px-3.5 sm:px-4 py-2 rounded-xl text-xs font-bold text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-white transition flex items-center gap-1.5 whitespace-nowrap shrink-0 cursor-pointer">Building Projects</button>')
    if "logistics" in allowed:
        tabs_html.append('<button id="btn-tab-logistics" onclick="switchDomain(\'logistics\')" class="tab-btn px-3.5 sm:px-4 py-2 rounded-xl text-xs font-bold text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-white transition flex items-center gap-1.5 whitespace-nowrap shrink-0 cursor-pointer">Workshop Fleet</button>')

    nav_tabs_markup = "\n".join(tabs_html)
    allowed_domains_json = str(allowed).replace("'", '"')

    # Construct Dynamic Role-Based Sidebar Navigation
    user_role = user.get("role", "LOGISTICS_USER")
    user_name = user.get("name", "User")

    can_manage_fuel = user_has_permission(user, "manage_fuel_price")
    can_manage_city = user_has_permission(user, "manage_city_minimums")
    can_clear_debt = user_has_permission(user, "clear_sales_rep_debt")
    can_view_audit = user_has_permission(user, "view_audit_logs")
    can_manage_users = user_has_permission(user, "manage_user_permissions")
    can_manage_trucks = user_has_permission(user, "manage_trucks")
    can_manage_drivers = user_has_permission(user, "manage_drivers")
    can_view_balances = user_has_permission(user, "view_sales_rep_balances")

    sidebar_links = []
    sidebar_links.append('<div class="px-4 pt-2 pb-1 text-[10px] font-extrabold uppercase tracking-wider text-slate-400 dark:text-zinc-500">Commercial Operations</div>')
    sidebar_links.append('<button onclick="switchFleetSubView(\'overview\'); toggleSidebar(false);" class="w-full text-left px-4 py-2.5 rounded-xl text-xs font-bold text-slate-700 dark:text-zinc-200 hover:bg-blue-50 dark:hover:bg-blue-500/10 hover:text-blue-600 dark:hover:text-blue-400 transition flex items-center gap-2.5">Operations Overview</button>')
    sidebar_links.append('<button onclick="switchFleetSubView(\'trips\'); toggleSidebar(false);" class="w-full text-left px-4 py-2.5 rounded-xl text-xs font-medium text-slate-600 dark:text-zinc-300 hover:bg-slate-100 dark:hover:bg-zinc-800 transition flex items-center gap-2.5">Trip Pipeline</button>')
    sidebar_links.append('<button onclick="switchFleetSubView(\'trucks\'); toggleSidebar(false);" class="w-full text-left px-4 py-2.5 rounded-xl text-xs font-medium text-slate-600 dark:text-zinc-300 hover:bg-slate-100 dark:hover:bg-zinc-800 transition flex items-center gap-2.5">Fleet Vehicles</button>')
    sidebar_links.append('<button onclick="switchFleetSubView(\'drivers\'); toggleSidebar(false);" class="w-full text-left px-4 py-2.5 rounded-xl text-xs font-medium text-slate-600 dark:text-zinc-300 hover:bg-slate-100 dark:hover:bg-zinc-800 transition flex items-center gap-2.5">Commercial Drivers</button>')
    sidebar_links.append('<button onclick="openCityConfigModal(); toggleSidebar(false);" class="w-full text-left px-4 py-2.5 rounded-xl text-xs font-medium text-slate-600 dark:text-zinc-300 hover:bg-slate-100 dark:hover:bg-zinc-800 transition flex items-center gap-2.5">Delivery Corridors</button>')

    if can_view_balances:
        sidebar_links.append('<div class="px-4 pt-3 pb-1 text-[10px] font-extrabold uppercase tracking-wider text-slate-400 dark:text-zinc-500">Finance & Ledgers</div>')
        sidebar_links.append('<button onclick="switchFleetSubView(\'salespersons\'); toggleSidebar(false);" class="w-full text-left px-4 py-2.5 rounded-xl text-xs font-medium text-slate-600 dark:text-zinc-300 hover:bg-slate-100 dark:hover:bg-zinc-800 transition flex items-center gap-2.5">Sales Representative Balances</button>')
        sidebar_links.append('<button onclick="switchFleetSubView(\'payments\'); toggleSidebar(false);" class="w-full text-left px-4 py-2.5 rounded-xl text-xs font-medium text-slate-600 dark:text-zinc-300 hover:bg-slate-100 dark:hover:bg-zinc-800 transition flex items-center gap-2.5">Payment History</button>')
        sidebar_links.append('<button onclick="switchFleetSubView(\'ledger\'); toggleSidebar(false);" class="w-full text-left px-4 py-2.5 rounded-xl text-xs font-medium text-slate-600 dark:text-zinc-300 hover:bg-slate-100 dark:hover:bg-zinc-800 transition flex items-center gap-2.5">Financial Audit Log</button>')

    is_master_admin = (user_role == "MASTER_ADMIN")

    if is_master_admin:
        sidebar_links.append('<div class="px-4 pt-3 pb-1 text-[10px] font-extrabold uppercase tracking-wider text-slate-400 dark:text-zinc-500">Analytics & Insights</div>')
        sidebar_links.append('<button onclick="switchFleetSubView(\'analytics\'); toggleSidebar(false);" class="w-full text-left px-4 py-2.5 rounded-xl text-xs font-medium text-slate-600 dark:text-zinc-300 hover:bg-slate-100 dark:hover:bg-zinc-800 transition flex items-center gap-2.5">Operations Analytics</button>')

    if can_manage_fuel or can_manage_city or can_view_audit or can_manage_users:
        sidebar_links.append('<div class="px-4 pt-3 pb-1 text-[10px] font-extrabold uppercase tracking-wider text-slate-400 dark:text-zinc-500">System Management</div>')
        if can_manage_fuel or can_manage_city:
            sidebar_links.append('<button onclick="openCityConfigModal(); toggleSidebar(false);" class="w-full text-left px-4 py-2.5 rounded-xl text-xs font-medium text-slate-600 dark:text-zinc-300 hover:bg-slate-100 dark:hover:bg-zinc-800 transition flex items-center gap-2.5">Fuel & City Rates</button>')
        if can_manage_users:
            sidebar_links.append('<button onclick="openUserManagementModal(); toggleSidebar(false);" class="w-full text-left px-4 py-2.5 rounded-xl text-xs font-medium text-slate-600 dark:text-zinc-300 hover:bg-slate-100 dark:hover:bg-zinc-800 transition flex items-center gap-2.5">User Permissions</button>')
        if can_view_audit:
            sidebar_links.append('<button onclick="openAuditLogsModal(); toggleSidebar(false);" class="w-full text-left px-4 py-2.5 rounded-xl text-xs font-medium text-slate-600 dark:text-zinc-300 hover:bg-slate-100 dark:hover:bg-zinc-800 transition flex items-center gap-2.5">System Audit Logs</button>')

    sidebar_markup = "\n".join(sidebar_links)

    nav_salespersons_opt = '<option value="salespersons">Sales Representative Balances</option>' if can_view_balances else ''
    nav_payments_opt = '<option value="payments">Payment History</option>' if can_view_balances else ''
    nav_ledger_opt = '<option value="ledger">Financial Audit Log</option>' if can_view_balances else ''
    nav_analytics_opt = '<option value="analytics">Data Analytics</option>' if is_master_admin else ''

    nav_salespersons_btn = '<button onclick="switchFleetSubView(\'salespersons\')" id="fleet-btn-salespersons" data-view="salespersons" class="fleet-quick-pill px-3 py-1.5 rounded-xl text-xs font-bold text-slate-600 dark:text-zinc-300 hover:bg-slate-100 dark:hover:bg-zinc-800 transition cursor-pointer whitespace-nowrap">Sales Reps</button>' if can_view_balances else ''
    nav_payments_btn = '<button onclick="switchFleetSubView(\'payments\')" id="fleet-btn-payments" data-view="payments" class="fleet-quick-pill px-3 py-1.5 rounded-xl text-xs font-bold text-slate-600 dark:text-zinc-300 hover:bg-slate-100 dark:hover:bg-zinc-800 transition cursor-pointer whitespace-nowrap">Payments</button>' if can_view_balances else ''
    nav_ledger_btn = '<button onclick="switchFleetSubView(\'ledger\')" id="fleet-btn-ledger" data-view="ledger" class="fleet-quick-pill px-3 py-1.5 rounded-xl text-xs font-bold text-slate-600 dark:text-zinc-300 hover:bg-slate-100 dark:hover:bg-zinc-800 transition cursor-pointer whitespace-nowrap">Audit Log</button>' if can_view_balances else ''
    nav_analytics_btn = '<button onclick="switchFleetSubView(\'analytics\')" id="fleet-btn-analytics" data-view="analytics" class="fleet-quick-pill px-3 py-1.5 rounded-xl text-xs font-bold text-slate-600 dark:text-zinc-300 hover:bg-slate-100 dark:hover:bg-zinc-800 transition cursor-pointer whitespace-nowrap">Analytics</button>' if is_master_admin else ''

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
                        sans: ['Plus Jakarta Sans', 'sans-serif'],
                        mono: ['JetBrains Mono', 'monospace'],
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
        body {{ font-family: 'Plus Jakarta Sans', sans-serif; }}
        .font-mono {{ font-family: 'JetBrains Mono', monospace; }}
        .tab-btn.active {{
            background: linear-gradient(135deg, #2563eb 0%, #1d4ed8 100%);
            color: #ffffff !important;
            box-shadow: 0 4px 14px rgba(37, 99, 235, 0.35);
        }}
        html.dark .tab-btn.active {{
            background: linear-gradient(135deg, #3b82f6 0%, #1d4ed8 100%);
            color: #ffffff !important;
            box-shadow: 0 4px 16px rgba(59, 130, 246, 0.4);
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
<body class="bg-slate-50 dark:bg-black text-slate-800 dark:text-zinc-100 min-h-screen pb-16 transition-colors duration-200">
    <!-- Sliding Sidebar Backdrop -->
    <div id="sidebar-backdrop" onclick="toggleSidebar(false)" class="fixed inset-0 bg-slate-900/60 backdrop-blur-xs z-40 hidden transition-opacity duration-300"></div>

    <!-- 3-Line Sliding Sidebar Navigation Menu -->
    <aside id="sliding-sidebar" class="fixed top-0 left-0 bottom-0 w-72 sm:w-80 bg-white dark:bg-[#0c0c10] border-r border-slate-200 dark:border-zinc-800 z-50 transform -translate-x-full transition-transform duration-300 ease-in-out shadow-2xl flex flex-col">
        <!-- Sidebar Header -->
        <div class="p-4 sm:p-5 border-b border-slate-200 dark:border-zinc-800 flex items-center justify-between">
            <div class="flex items-center gap-2.5">
                <div>
                    <h3 class="text-sm font-extrabold text-slate-900 dark:text-zinc-100">Tagoneswa Hub</h3>
                    <p class="text-[10px] text-slate-500 dark:text-zinc-400 font-medium">Enterprise Central Control</p>
                </div>
            </div>
            <button onclick="toggleSidebar(false)" class="p-2 rounded-xl text-slate-400 hover:text-slate-600 dark:hover:text-zinc-200 hover:bg-slate-100 dark:hover:bg-zinc-800 transition cursor-pointer" title="Close Menu">
                ✕
            </button>
        </div>

        <!-- User Profile Pill in Sidebar -->
        <div class="p-3.5 mx-3 mt-3 bg-slate-50 dark:bg-[#121216] border border-slate-200 dark:border-zinc-800 rounded-2xl flex items-center gap-3">
            <div class="w-9 h-9 rounded-xl bg-blue-100 dark:bg-blue-500/20 text-blue-700 dark:text-blue-300 font-extrabold text-sm flex items-center justify-center">
                {user_name[:2].upper()}
            </div>
            <div class="overflow-hidden">
                <div class="text-xs font-bold text-slate-900 dark:text-zinc-100 truncate">{user_name}</div>
                <div class="text-[10px] font-semibold text-emerald-600 dark:text-emerald-400 flex items-center gap-1">
                    <span class="w-1.5 h-1.5 rounded-full bg-emerald-500"></span> {user_role.replace('_', ' ')}
                </div>
            </div>
        </div>

        <!-- Navigation Links (Dynamic by Role) -->
        <nav id="sidebar-nav-container" class="flex-1 overflow-y-auto p-3 space-y-1 no-scrollbar">
            {sidebar_markup}
        </nav>

        <!-- Sidebar Footer -->
        <div class="p-3.5 border-t border-slate-200 dark:border-zinc-800 flex items-center justify-between text-[11px] text-slate-400 dark:text-zinc-500">
            <span>Enterprise Operations v2.4</span>
            <button onclick="handleLogout()" class="text-rose-500 hover:underline font-bold cursor-pointer">Logout</button>
        </div>
    </aside>

    <!-- Toast Notification -->
    <div id="toast" class="fixed bottom-5 right-5 z-50 transform translate-y-20 opacity-0 transition-all duration-300 pointer-events-none bg-slate-900 dark:bg-[#121216] text-white px-4 py-3 rounded-2xl shadow-2xl border border-slate-700 dark:border-zinc-800 text-xs font-semibold flex items-center gap-2">
        <span id="toastIcon">✅</span>
        <span id="toastMsg">Live data updated</span>
    </div>

    <!-- Top Sticky Header -->
    <header class="bg-white/95 dark:bg-[#07070a]/95 backdrop-blur-xl border-b border-slate-200/80 dark:border-zinc-800/80 sticky top-0 z-30 transition-colors duration-200 shadow-xs">
        <div class="w-full max-w-[1780px] mx-auto px-4 sm:px-6 lg:px-8 xl:px-10 py-2.5 sm:py-3.5">
            <div class="flex flex-col md:flex-row items-center justify-between gap-3">
                <!-- Top Row: Brand & Mobile Actions -->
                <div class="flex items-center justify-between w-full md:w-auto gap-3">
                    <div class="flex items-center gap-2 sm:gap-2.5">
                        <!-- 3-line hamburger menu toggle button -->
                        <button onclick="toggleSidebar(true)" class="p-2 rounded-xl text-slate-700 dark:text-zinc-200 hover:bg-slate-100 dark:hover:bg-zinc-800 transition cursor-pointer border border-slate-200 dark:border-zinc-800 shadow-xs flex items-center justify-center text-lg leading-none" title="Open Navigation Menu">
                            ☰
                        </button>
                        <div>
                            <div class="flex items-center gap-1.5">
                                <h1 class="text-base sm:text-lg font-extrabold text-slate-900 dark:text-zinc-100 tracking-tight leading-none">Tagoneswa</h1>
                                <span class="bg-blue-100 dark:bg-blue-500/10 text-blue-700 dark:text-blue-300 text-[9px] font-extrabold px-1.5 py-0.5 rounded border border-blue-200 dark:border-blue-500/30 uppercase tracking-wider">Enterprise</span>
                            </div>
                            <p class="text-[10px] sm:text-xs text-slate-500 dark:text-zinc-400 font-medium mt-0.5">Operations & Fleet Portal</p>
                        </div>
                    </div>

                    <!-- Right Controls for Mobile Screen -->
                    <div class="flex items-center gap-1.5 md:hidden">
                        <!-- Theme Toggle (Mobile) -->
                        <button onclick="toggleTheme()" class="theme-toggle-btn bg-slate-100 hover:bg-slate-200 dark:bg-[#121216] dark:hover:bg-[#1a1a20] text-slate-700 dark:text-zinc-200 p-2 rounded-xl text-xs font-bold transition flex items-center border border-slate-200 dark:border-zinc-800 cursor-pointer shadow-xs" title="Toggle Theme">
                            <span class="theme-toggle-icon">🌙</span>
                        </button>
                        <button onclick="manualRefresh()" id="mobileRefreshBtn" class="bg-slate-100 hover:bg-slate-200 dark:bg-[#121216] dark:hover:bg-[#1a1a20] text-slate-700 dark:text-zinc-200 p-2 rounded-xl text-xs font-bold transition flex items-center border border-slate-200 dark:border-zinc-800 cursor-pointer shadow-xs" title="Refresh Live Data">
                            <span id="mobileRefreshIcon" class="inline-block">🔄</span>
                        </button>
                        <button onclick="handleLogout()" class="bg-rose-50 hover:bg-rose-100 dark:bg-rose-950/30 dark:hover:bg-rose-900/50 text-rose-600 dark:text-rose-400 border border-rose-200 dark:border-rose-900/50 text-xs font-bold px-2.5 py-1.5 rounded-xl transition cursor-pointer">
                            Log Out
                        </button>
                    </div>
                </div>

                <!-- Domain Switcher (Filtered by User Permissions) -->
                <nav class="flex bg-slate-100 dark:bg-[#0d0d11] p-1 rounded-xl border border-slate-200 dark:border-zinc-800 gap-1 w-full md:w-auto overflow-x-auto justify-start sm:justify-center no-scrollbar scroll-smooth">
                    {nav_tabs_markup}
                </nav>

                <!-- User Pill, Theme Toggle, Desktop Refresh & Logout -->
                <div class="hidden md:flex items-center gap-2.5">
                    <!-- Theme Toggle Switch (Desktop) -->
                    <button onclick="toggleTheme()" class="theme-toggle-btn bg-slate-100 hover:bg-slate-200 dark:bg-[#121216] dark:hover:bg-[#1a1a20] text-slate-700 dark:text-zinc-200 px-3 py-2 rounded-xl text-xs font-bold transition flex items-center gap-1.5 border border-slate-200 dark:border-zinc-800 cursor-pointer shadow-xs" title="Toggle Dark / Light Theme">
                        <span class="theme-toggle-icon">🌙</span>
                        <span class="theme-toggle-label font-semibold">Dark</span>
                    </button>

                    <button onclick="manualRefresh()" id="desktopRefreshBtn" class="bg-slate-100 hover:bg-slate-200 dark:bg-[#121216] dark:hover:bg-[#1a1a20] text-slate-700 dark:text-zinc-200 px-3 py-2 rounded-xl text-xs font-bold transition flex items-center gap-1.5 border border-slate-200 dark:border-zinc-800 cursor-pointer shadow-xs" title="Refresh Live Data">
                        <span id="desktopRefreshIcon" class="inline-block">🔄</span>
                        <span>Refresh</span>
                    </button>

                    <div class="text-right pl-2 border-l border-slate-200 dark:border-zinc-800">
                        <div class="text-xs font-bold text-slate-900 dark:text-zinc-100 leading-tight" id="userDisplayName">{user["name"]}</div>
                        <div class="text-[10px] font-semibold text-emerald-600 dark:text-emerald-400 flex items-center justify-end gap-1 mt-0.5" id="userRoleBadge">
                            <span class="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse"></span> {user["role"].replace("_", " ")}
                        </div>
                    </div>

                    <button onclick="handleLogout()" class="bg-rose-50 hover:bg-rose-100 dark:bg-rose-950/30 dark:hover:bg-rose-900/50 text-rose-600 dark:text-rose-400 border border-rose-200 dark:border-rose-900/50 text-xs font-bold px-3.5 py-2 rounded-xl transition cursor-pointer">
                        Log Out
                    </button>
                </div>
            </div>
        </div>
    </header>

    <!-- Main Content Container (Widescreen Enterprise Fluid Layout) -->
    <main class="w-full max-w-[1780px] mx-auto px-4 sm:px-6 lg:px-8 xl:px-10 py-4 sm:py-8 space-y-6 sm:space-y-8">

        <!-- ========================================================= -->
        <!-- TAB 1: IT SUPPORT (Rendered only if permitted) -->
        <!-- ========================================================= -->
        <div id="view-it" class="domain-view space-y-6 sm:space-y-8" style="display: {'block' if 'it' in allowed and default_tab == 'it' else 'none'}">
            <!-- IT Stats -->
            <div class="grid grid-cols-2 lg:grid-cols-4 gap-3 sm:gap-4">
                <div class="bg-white dark:bg-[#0a0a0d] border border-slate-200/80 dark:border-zinc-800/80 rounded-2xl p-4 sm:p-5 shadow-xs hover:shadow-md transition-all duration-200">
                    <div class="text-[11px] sm:text-xs font-bold uppercase tracking-wider text-slate-400 dark:text-zinc-500">Total IT Tickets</div>
                    <div class="text-2xl sm:text-3xl font-extrabold text-slate-900 dark:text-zinc-100 mt-1.5" id="it-stat-total">0</div>
                    <div class="text-[11px] sm:text-xs text-blue-600 dark:text-blue-400 font-semibold mt-1">All IT Logs</div>
                </div>
                <div class="bg-white dark:bg-[#0a0a0d] border border-slate-200/80 dark:border-zinc-800/80 rounded-2xl p-4 sm:p-5 shadow-xs hover:shadow-md transition-all duration-200">
                    <div class="text-[11px] sm:text-xs font-bold uppercase tracking-wider text-slate-400 dark:text-zinc-500">Open & Active</div>
                    <div class="text-2xl sm:text-3xl font-extrabold text-amber-500 dark:text-amber-400 mt-1.5" id="it-stat-active">0</div>
                    <div class="text-[11px] sm:text-xs text-amber-600 dark:text-amber-400 font-semibold mt-1">Action Required</div>
                </div>
                <div class="bg-white dark:bg-[#0a0a0d] border border-slate-200/80 dark:border-zinc-800/80 rounded-2xl p-4 sm:p-5 shadow-xs hover:shadow-md transition-all duration-200">
                    <div class="text-[11px] sm:text-xs font-bold uppercase tracking-wider text-slate-400 dark:text-zinc-500">Resolved / Closed</div>
                    <div class="text-2xl sm:text-3xl font-extrabold text-emerald-500 dark:text-emerald-400 mt-1.5" id="it-stat-resolved">0</div>
                    <div class="text-[11px] sm:text-xs text-emerald-600 dark:text-emerald-400 font-semibold mt-1">Completed Solved</div>
                </div>
                <div class="bg-white dark:bg-[#0a0a0d] border border-slate-200/80 dark:border-zinc-800/80 rounded-2xl p-4 sm:p-5 shadow-xs hover:shadow-md transition-all duration-200">
                    <div class="text-[11px] sm:text-xs font-bold uppercase tracking-wider text-slate-400 dark:text-zinc-500">Avg Resolution</div>
                    <div class="text-2xl sm:text-3xl font-extrabold text-purple-600 dark:text-purple-400 mt-1.5" id="it-stat-avg-time">--</div>
                    <div class="text-[11px] sm:text-xs text-purple-600 dark:text-purple-400 font-semibold mt-1">SLA Speed Benchmark</div>
                </div>
            </div>

            <!-- IT Admin SLA Cards (Positioned at Top for Instant Visibility without scrolling 100 tickets) -->
            <div class="bg-white dark:bg-[#0a0a0d] border border-slate-200/80 dark:border-zinc-800/80 rounded-2xl p-5 sm:p-6 shadow-xs">
                <div class="flex flex-col sm:flex-row sm:items-center justify-between mb-4 gap-2">
                    <div>
                        <h2 class="text-xs sm:text-sm font-extrabold uppercase tracking-wider text-slate-900 dark:text-zinc-100 flex items-center gap-2">
                            <span>👨‍💻</span> IT Support Technicians Performance & SLA
                        </h2>
                        <p class="text-[11px] text-slate-500 dark:text-zinc-400 mt-0.5">Click any technician card to instantly filter their assigned tickets below</p>
                    </div>
                    <div class="flex items-center gap-2">
                        <button onclick="filterByITAdmin('ALL')" class="text-[11px] font-bold text-blue-600 dark:text-blue-400 hover:underline cursor-pointer bg-blue-50 dark:bg-blue-500/10 px-2.5 py-1 rounded-lg border border-blue-200 dark:border-blue-500/30">
                            Clear Filter / View All
                        </button>
                    </div>
                </div>
                <div class="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-3 sm:gap-4" id="it-admin-cards"></div>
            </div>

            <!-- IT Table Section -->
            <div id="it-table-card" class="bg-white dark:bg-[#0a0a0d] border border-slate-200/80 dark:border-zinc-800/80 rounded-2xl shadow-xs overflow-hidden transition-all duration-200">
                <!-- Controls & Filters -->
                <div class="p-4 sm:p-5 border-b border-slate-200 dark:border-zinc-850 flex flex-col md:flex-row items-stretch md:items-center justify-between gap-3 sm:gap-4 bg-slate-50/60 dark:bg-[#0e0e12]/80">
                    <div class="flex flex-col sm:flex-row flex-wrap items-stretch sm:items-center gap-2 sm:gap-3 w-full md:w-auto">
                        <input type="text" id="it-search" placeholder="Search employee, ticket #, issue..." oninput="filterITTable(true)" class="bg-white dark:bg-[#121216] border border-slate-300 dark:border-zinc-750 rounded-xl px-4 py-2.5 sm:py-2 text-xs font-medium text-slate-800 dark:text-zinc-100 placeholder-slate-400 dark:placeholder-zinc-500 focus:outline-none focus:ring-2 focus:ring-blue-500 w-full sm:w-64 transition">
                        
                        <!-- Admin Filter -->
                        <select id="it-admin-filter" onchange="filterITTable(true)" class="bg-white dark:bg-[#121216] border border-slate-300 dark:border-zinc-750 rounded-xl px-3 py-2.5 sm:py-2 text-xs font-medium text-slate-700 dark:text-zinc-200 focus:outline-none focus:ring-2 focus:ring-blue-500 w-full sm:w-auto transition">
                            <option value="ALL">All Support Admins</option>
                        </select>

                        <!-- Status Filter -->
                        <select id="it-status-filter" onchange="filterITTable(true)" class="bg-white dark:bg-[#121216] border border-slate-300 dark:border-zinc-750 rounded-xl px-3 py-2.5 sm:py-2 text-xs font-medium text-slate-700 dark:text-zinc-200 focus:outline-none focus:ring-2 focus:ring-blue-500 w-full sm:w-auto transition">
                            <option value="ALL">All Statuses</option>
                            <option value="Open">Open</option>
                            <option value="In Progress">In Progress</option>
                            <option value="Resolved">Resolved</option>
                            <option value="Closed">Closed</option>
                        </select>
                    </div>

                    <!-- Dynamic Count Badge -->
                    <div class="flex items-center justify-between sm:justify-end gap-2">
                        <span id="it-count-badge" class="bg-blue-50 dark:bg-blue-500/10 text-blue-700 dark:text-blue-300 border border-blue-200 dark:border-blue-500/30 text-xs font-bold px-3 py-1.5 rounded-full">
                            Showing 0 tickets
                        </span>
                    </div>
                </div>

                <!-- Swipe hint on mobile -->
                <div class="block md:hidden text-[11px] text-slate-400 dark:text-zinc-500 px-4 py-1.5 bg-slate-50 dark:bg-[#0c0c10] border-b border-slate-100 dark:border-zinc-850 flex items-center justify-between">
                    <span>👉 Swipe horizontally for full table</span>
                    <span class="font-mono text-slate-400 dark:text-zinc-500">⇄</span>
                </div>

                <!-- Table -->
                <div class="overflow-x-auto">
                    <table class="w-full text-left text-xs min-w-[760px]">
                        <thead class="bg-slate-100/75 dark:bg-[#0e0e12] text-slate-500 dark:text-zinc-400 font-bold uppercase tracking-wider border-b border-slate-200 dark:border-zinc-800">
                            <tr>
                                <th class="px-4 sm:px-5 py-3.5 whitespace-nowrap">Ticket #</th>
                                <th class="px-4 sm:px-5 py-3.5 whitespace-nowrap">Employee</th>
                                <th class="px-4 sm:px-5 py-3.5 whitespace-nowrap">Department & Location</th>
                                <th class="px-4 sm:px-5 py-3.5 whitespace-nowrap">Category & Issue</th>
                                <th class="px-4 sm:px-5 py-3.5 whitespace-nowrap">Priority</th>
                                <th class="px-4 sm:px-5 py-3.5 whitespace-nowrap">Status</th>
                                <th class="px-4 sm:px-5 py-3.5 whitespace-nowrap">Assigned Admin</th>
                                <th class="px-4 sm:px-5 py-3.5 whitespace-nowrap">Solving Time</th>
                            </tr>
                        </thead>
                        <tbody id="it-table-body" class="divide-y divide-slate-200 dark:divide-zinc-850 text-slate-700 dark:text-zinc-200"></tbody>
                    </table>
                </div>

                <!-- Pagination Footer -->
                <div class="p-3.5 sm:p-4 border-t border-slate-200 dark:border-zinc-850 flex flex-col sm:flex-row items-center justify-between gap-3 bg-slate-50/60 dark:bg-[#0c0c10]/80">
                    <div class="text-xs text-slate-500 dark:text-zinc-400 font-medium" id="it-pagination-info">
                        Showing 0 entries
                    </div>
                    <div class="flex items-center gap-1.5" id="it-pagination-controls"></div>
                </div>
            </div>

            <!-- Category & Issue Breakdown Tree -->
            <div class="bg-white dark:bg-[#0a0a0d] border border-slate-200/80 dark:border-zinc-800/80 rounded-2xl p-5 sm:p-6 shadow-xs">
                <div class="flex flex-col sm:flex-row sm:items-center justify-between mb-4 gap-1">
                    <h2 class="text-xs sm:text-sm font-extrabold uppercase tracking-wider text-slate-900 dark:text-zinc-100 flex items-center gap-2">
                        <span>🌳</span> Category, Subcategory & Specific Issue Breakdown
                    </h2>
                    <span class="text-[11px] font-semibold text-slate-400 dark:text-zinc-500">Hierarchical Fault Occurrences</span>
                </div>
                <div id="it-category-tree" class="space-y-3"></div>
            </div>
        </div>

        <!-- ========================================================= -->
        <!-- TAB 2: BUILDING PROJECTS (Rendered only if permitted) -->
        <!-- ========================================================= -->
        <div id="view-projects" class="domain-view space-y-6 sm:space-y-8" style="display: {'block' if 'projects' in allowed and default_tab == 'projects' else 'none'}">
            <!-- Projects Stats -->
            <div class="grid grid-cols-2 lg:grid-cols-4 gap-3 sm:gap-4">
                <div class="bg-white dark:bg-[#0a0a0d] border border-slate-200/80 dark:border-zinc-800/80 rounded-2xl p-4 sm:p-5 shadow-xs hover:shadow-md transition-all duration-200">
                    <div class="text-[11px] sm:text-xs font-bold uppercase tracking-wider text-slate-400 dark:text-zinc-500">Total Project Tickets</div>
                    <div class="text-2xl sm:text-3xl font-extrabold text-slate-900 dark:text-zinc-100 mt-1.5" id="proj-stat-total">0</div>
                    <div class="text-[11px] sm:text-xs text-blue-600 dark:text-blue-400 font-semibold mt-1">Building & Facilities</div>
                </div>
                <div class="bg-white dark:bg-[#0a0a0d] border border-slate-200/80 dark:border-zinc-800/80 rounded-2xl p-4 sm:p-5 shadow-xs hover:shadow-md transition-all duration-200">
                    <div class="text-[11px] sm:text-xs font-bold uppercase tracking-wider text-slate-400 dark:text-zinc-500">Active Work Orders</div>
                    <div class="text-2xl sm:text-3xl font-extrabold text-amber-500 dark:text-amber-400 mt-1.5" id="proj-stat-active">0</div>
                    <div class="text-[11px] sm:text-xs text-amber-600 dark:text-amber-400 font-semibold mt-1">On-Site in Progress</div>
                </div>
                <div class="bg-white dark:bg-[#0a0a0d] border border-slate-200/80 dark:border-zinc-800/80 rounded-2xl p-4 sm:p-5 shadow-xs hover:shadow-md transition-all duration-200">
                    <div class="text-[11px] sm:text-xs font-bold uppercase tracking-wider text-slate-400 dark:text-zinc-500">Completed Facilities</div>
                    <div class="text-2xl sm:text-3xl font-extrabold text-emerald-500 dark:text-emerald-400 mt-1.5" id="proj-stat-completed">0</div>
                    <div class="text-[11px] sm:text-xs text-emerald-600 dark:text-emerald-400 font-semibold mt-1">Inspected & Closed</div>
                </div>
                <div class="bg-white dark:bg-[#0a0a0d] border border-slate-200/80 dark:border-zinc-800/80 rounded-2xl p-4 sm:p-5 shadow-xs hover:shadow-md transition-all duration-200">
                    <div class="text-[11px] sm:text-xs font-bold uppercase tracking-wider text-slate-400 dark:text-zinc-500">Active Branches / Yards</div>
                    <div class="text-2xl sm:text-3xl font-extrabold text-purple-600 dark:text-purple-400 mt-1.5" id="proj-stat-locations">0</div>
                    <div class="text-[11px] sm:text-xs text-purple-600 dark:text-purple-400 font-semibold mt-1">Locations Serviced</div>
                </div>
            </div>

            <!-- Projects Table Section -->
            <div class="bg-white dark:bg-[#0a0a0d] border border-slate-200/80 dark:border-zinc-800/80 rounded-2xl shadow-xs overflow-hidden transition-all duration-200">
                <div class="p-4 sm:p-5 border-b border-slate-200 dark:border-zinc-850 flex flex-col md:flex-row items-stretch md:items-center justify-between gap-3 sm:gap-4 bg-slate-50/60 dark:bg-[#0e0e12]/80">
                    <div class="flex flex-col sm:flex-row flex-wrap items-stretch sm:items-center gap-2 sm:gap-3 w-full md:w-auto">
                        <input type="text" id="proj-search" placeholder="Search site, ticket #, repair..." oninput="filterProjectsTable(true)" class="bg-white dark:bg-[#121216] border border-slate-300 dark:border-zinc-750 rounded-xl px-4 py-2.5 sm:py-2 text-xs font-medium text-slate-800 dark:text-zinc-100 placeholder-slate-400 dark:placeholder-zinc-500 focus:outline-none focus:ring-2 focus:ring-blue-500 w-full sm:w-64 transition">
                        
                        <!-- Location Filter -->
                        <select id="proj-loc-filter" onchange="filterProjectsTable(true)" class="bg-white dark:bg-[#121216] border border-slate-300 dark:border-zinc-750 rounded-xl px-3 py-2.5 sm:py-2 text-xs font-medium text-slate-700 dark:text-zinc-200 focus:outline-none focus:ring-2 focus:ring-blue-500 w-full sm:w-auto transition">
                            <option value="ALL">All Branches & Yards</option>
                        </select>

                        <!-- Admin Filter -->
                        <select id="proj-admin-filter" onchange="filterProjectsTable(true)" class="bg-white dark:bg-[#121216] border border-slate-300 dark:border-zinc-750 rounded-xl px-3 py-2.5 sm:py-2 text-xs font-medium text-slate-700 dark:text-zinc-200 focus:outline-none focus:ring-2 focus:ring-blue-500 w-full sm:w-auto transition">
                            <option value="ALL">All Project Leads</option>
                        </select>

                        <!-- Status Filter -->
                        <select id="proj-status-filter" onchange="filterProjectsTable(true)" class="bg-white dark:bg-[#121216] border border-slate-300 dark:border-zinc-750 rounded-xl px-3 py-2.5 sm:py-2 text-xs font-medium text-slate-700 dark:text-zinc-200 focus:outline-none focus:ring-2 focus:ring-blue-500 w-full sm:w-auto transition">
                            <option value="ALL">All Statuses</option>
                            <option value="Open">Open</option>
                            <option value="In Progress">In Progress</option>
                            <option value="Closed">Closed</option>
                        </select>
                    </div>

                    <div class="flex items-center justify-between sm:justify-end gap-2">
                        <span id="proj-count-badge" class="bg-blue-50 dark:bg-blue-500/10 text-blue-700 dark:text-blue-300 border border-blue-200 dark:border-blue-500/30 text-xs font-bold px-3 py-1.5 rounded-full">
                            Showing 0 tickets
                        </span>
                    </div>
                </div>

                <!-- Swipe hint on mobile -->
                <div class="block md:hidden text-[11px] text-slate-400 dark:text-zinc-500 px-4 py-1.5 bg-slate-50 dark:bg-[#0c0c10] border-b border-slate-100 dark:border-zinc-850 flex items-center justify-between">
                    <span>👉 Swipe horizontally for full table</span>
                    <span class="font-mono text-slate-400 dark:text-zinc-500">⇄</span>
                </div>

                <div class="overflow-x-auto">
                    <table class="w-full text-left text-xs min-w-[760px]">
                        <thead class="bg-slate-100/75 dark:bg-[#0e0e12] text-slate-500 dark:text-zinc-400 font-bold uppercase tracking-wider border-b border-slate-200 dark:border-zinc-800">
                            <tr>
                                <th class="px-4 sm:px-5 py-3.5 whitespace-nowrap">Ticket #</th>
                                <th class="px-4 sm:px-5 py-3.5 whitespace-nowrap">Reporter</th>
                                <th class="px-4 sm:px-5 py-3.5 whitespace-nowrap">Site / Branch Location</th>
                                <th class="px-4 sm:px-5 py-3.5 whitespace-nowrap">Category & Description</th>
                                <th class="px-4 sm:px-5 py-3.5 whitespace-nowrap">Status</th>
                                <th class="px-4 sm:px-5 py-3.5 whitespace-nowrap">Assigned Lead</th>
                                <th class="px-4 sm:px-5 py-3.5 whitespace-nowrap">Date Created</th>
                            </tr>
                        </thead>
                        <tbody id="proj-table-body" class="divide-y divide-slate-200 dark:divide-zinc-850 text-slate-700 dark:text-zinc-200"></tbody>
                    </table>
                </div>

                <!-- Pagination Footer -->
                <div class="p-3.5 sm:p-4 border-t border-slate-200 dark:border-zinc-850 flex flex-col sm:flex-row items-center justify-between gap-3 bg-slate-50/60 dark:bg-[#0c0c10]/80">
                    <div class="text-xs text-slate-500 dark:text-zinc-400 font-medium" id="proj-pagination-info">
                        Showing 0 entries
                    </div>
                    <div class="flex items-center gap-1.5" id="proj-pagination-controls"></div>
                </div>
            </div>
        </div>

        <!-- ========================================================= -->
        <!-- TAB 3: WORKSHOP & FLEET LOGISTICS (Rendered only if permitted) -->
        <!-- ========================================================= -->
        <div id="view-logistics" class="domain-view space-y-6 sm:space-y-8" style="display: {'block' if 'logistics' in allowed and default_tab == 'logistics' else 'none'}">
            <!-- Fleet Stats -->
            <div class="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3 sm:gap-4">
                <div class="bg-white dark:bg-[#0a0a0d] border border-slate-200/80 dark:border-zinc-800/80 rounded-2xl p-4 sm:p-5 shadow-xs hover:shadow-md transition-all duration-200">
                    <div class="text-[11px] sm:text-xs font-bold uppercase tracking-wider text-slate-400 dark:text-zinc-500">Active Fleet</div>
                    <div class="text-2xl sm:text-3xl font-extrabold text-blue-600 dark:text-blue-400 mt-1.5" id="ws-stat-fleet">39</div>
                    <div class="text-[11px] sm:text-xs text-blue-600 dark:text-blue-400 font-semibold mt-1">Trucks Registered</div>
                </div>
                <div class="bg-white dark:bg-[#0a0a0d] border border-slate-200/80 dark:border-zinc-800/80 rounded-2xl p-4 sm:p-5 shadow-xs hover:shadow-md transition-all duration-200">
                    <div class="text-[11px] sm:text-xs font-bold uppercase tracking-wider text-slate-400 dark:text-zinc-500">Supervisor Review</div>
                    <div class="text-2xl sm:text-3xl font-extrabold text-amber-500 dark:text-amber-400 mt-1.5" id="ws-stat-review">0</div>
                    <div class="text-[11px] sm:text-xs text-amber-600 dark:text-amber-400 font-semibold mt-1">Gatekeeper Triage</div>
                </div>
                <div class="bg-white dark:bg-[#0a0a0d] border border-slate-200/80 dark:border-zinc-800/80 rounded-2xl p-4 sm:p-5 shadow-xs hover:shadow-md transition-all duration-200">
                    <div class="text-[11px] sm:text-xs font-bold uppercase tracking-wider text-slate-400 dark:text-zinc-500">In Workshop</div>
                    <div class="text-2xl sm:text-3xl font-extrabold text-indigo-600 dark:text-indigo-400 mt-1.5" id="ws-stat-floor">0</div>
                    <div class="text-[11px] sm:text-xs text-indigo-600 dark:text-indigo-400 font-semibold mt-1">Floor Wrenching</div>
                </div>
                <div class="bg-white dark:bg-[#0a0a0d] border border-slate-200/80 dark:border-zinc-800/80 rounded-2xl p-4 sm:p-5 shadow-xs hover:shadow-md transition-all duration-200">
                    <div class="text-[11px] sm:text-xs font-bold uppercase tracking-wider text-slate-400 dark:text-zinc-500">Awaiting Spares</div>
                    <div class="text-2xl sm:text-3xl font-extrabold text-rose-500 dark:text-rose-400 mt-1.5" id="ws-stat-parts">0</div>
                    <div class="text-[11px] sm:text-xs text-rose-600 dark:text-rose-400 font-semibold mt-1">Purchasing Queue</div>
                </div>
                <div class="bg-white dark:bg-[#0a0a0d] border border-slate-200/80 dark:border-zinc-800/80 rounded-2xl p-4 sm:p-5 shadow-xs hover:shadow-md transition-all duration-200 col-span-2 sm:col-span-1">
                    <div class="text-[11px] sm:text-xs font-bold uppercase tracking-wider text-slate-400 dark:text-zinc-500">QC Road-Test</div>
                    <div class="text-2xl sm:text-3xl font-extrabold text-emerald-500 dark:text-emerald-400 mt-1.5" id="ws-stat-qc">0</div>
                    <div class="text-[11px] sm:text-xs text-emerald-600 dark:text-emerald-400 font-semibold mt-1">Awaiting Sign-off</div>
                </div>
            </div>

            <!-- Fleet Table Section -->
            <div class="bg-white dark:bg-[#0a0a0d] border border-slate-200/80 dark:border-zinc-800/80 rounded-2xl shadow-xs overflow-hidden transition-all duration-200">
                <div class="p-4 sm:p-5 border-b border-slate-200 dark:border-zinc-850 flex flex-col md:flex-row items-stretch md:items-center justify-between gap-3 sm:gap-4 bg-slate-50/60 dark:bg-[#0e0e12]/80">
                    <div class="flex flex-col sm:flex-row flex-wrap items-stretch sm:items-center gap-2 sm:gap-3 w-full md:w-auto">
                        <input type="text" id="ws-search" placeholder="Search truck #, plate, fault notes..." oninput="filterFleetTable(true)" class="bg-white dark:bg-[#121216] border border-slate-300 dark:border-zinc-750 rounded-xl px-4 py-2.5 sm:py-2 text-xs font-medium text-slate-800 dark:text-zinc-100 placeholder-slate-400 dark:placeholder-zinc-500 focus:outline-none focus:ring-2 focus:ring-blue-500 w-full sm:w-64 transition">
                        
                        <!-- Mechanic Filter -->
                        <select id="ws-mech-filter" onchange="filterFleetTable(true)" class="bg-white dark:bg-[#121216] border border-slate-300 dark:border-zinc-750 rounded-xl px-3 py-2.5 sm:py-2 text-xs font-medium text-slate-700 dark:text-zinc-200 focus:outline-none focus:ring-2 focus:ring-blue-500 w-full sm:w-auto transition">
                            <option value="ALL">All Mechanics</option>
                        </select>

                        <!-- Status Filter -->
                        <select id="ws-status-filter" onchange="filterFleetTable(true)" class="bg-white dark:bg-[#121216] border border-slate-300 dark:border-zinc-750 rounded-xl px-3 py-2.5 sm:py-2 text-xs font-medium text-slate-700 dark:text-zinc-200 focus:outline-none focus:ring-2 focus:ring-blue-500 w-full sm:w-auto transition">
                            <option value="ALL">All Workshop Stages</option>
                            <option value="UNDER_REVIEW">Under Review</option>
                            <option value="WITH_MECHANIC">With Mechanic</option>
                            <option value="AWAITING_PARTS">Awaiting Parts</option>
                            <option value="AWAITING_TEST">Awaiting QC Test</option>
                            <option value="REWORK_REQUIRED">Rework Required</option>
                            <option value="CLOSED">Closed / Returned to Fleet</option>
                        </select>
                    </div>

                    <div class="flex items-center justify-between sm:justify-end gap-2">
                        <span id="ws-count-badge" class="bg-blue-50 dark:bg-blue-500/10 text-blue-700 dark:text-blue-300 border border-blue-200 dark:border-blue-500/30 text-xs font-bold px-3 py-1.5 rounded-full">
                            Showing 0 vehicles
                        </span>
                    </div>
                </div>

                <!-- Swipe hint on mobile -->
                <div class="block md:hidden text-[11px] text-slate-400 dark:text-zinc-500 px-4 py-1.5 bg-slate-50 dark:bg-[#0c0c10] border-b border-slate-100 dark:border-zinc-850 flex items-center justify-between">
                    <span>👉 Swipe horizontally for full table</span>
                    <span class="font-mono text-slate-400 dark:text-zinc-500">⇄</span>
                </div>

                <div class="overflow-x-auto">
                    <table class="w-full text-left text-xs min-w-[760px]">
                        <thead class="bg-slate-100/75 dark:bg-[#0e0e12] text-slate-500 dark:text-zinc-400 font-bold uppercase tracking-wider border-b border-slate-200 dark:border-zinc-800">
                            <tr>
                                <th class="px-4 sm:px-5 py-3.5 whitespace-nowrap">Ticket #</th>
                                <th class="px-4 sm:px-5 py-3.5 whitespace-nowrap">Truck & Plate</th>
                                <th class="px-4 sm:px-5 py-3.5 whitespace-nowrap">Vehicle Model</th>
                                <th class="px-4 sm:px-5 py-3.5 whitespace-nowrap">Fault Category & Description</th>
                                <th class="px-4 sm:px-5 py-3.5 whitespace-nowrap">Logged By</th>
                                <th class="px-4 sm:px-5 py-3.5 whitespace-nowrap">Mechanic & ETA</th>
                                <th class="px-4 sm:px-5 py-3.5 whitespace-nowrap">Parts Requisition</th>
                                <th class="px-4 sm:px-5 py-3.5 whitespace-nowrap">Costing</th>
                                <th class="px-4 sm:px-5 py-3.5 whitespace-nowrap">Status & QC</th>
                            </tr>
                        </thead>
                        <tbody id="ws-table-body" class="divide-y divide-slate-200 dark:divide-zinc-850 text-slate-700 dark:text-zinc-200"></tbody>
                    </table>
                </div>

                <!-- Pagination Footer -->
                <div class="p-3.5 sm:p-4 border-t border-slate-200 dark:border-zinc-850 flex flex-col sm:flex-row items-center justify-between gap-3 bg-slate-50/60 dark:bg-[#0c0c10]/80">
                    <div class="text-xs text-slate-500 dark:text-zinc-400 font-medium" id="ws-pagination-info">
                        Showing 0 entries
                    </div>
                    <div class="flex items-center gap-1.5" id="ws-pagination-controls"></div>
                </div>
            </div>
        </div>
        <!-- ========================================================= -->
        <!-- TAB 4: SALES TO FLEET OPERATIONS -->
        <!-- ========================================================= -->
        <div id="view-fleet" class="domain-view space-y-6 sm:space-y-8" style="display: {'block' if 'fleet' in allowed and default_tab == 'fleet' else 'none'}">
            <!-- Executive Fleet Command Center Banner -->
            <div id="master-kpi-banner" class="bg-gradient-to-r from-slate-900 via-blue-950 to-slate-900 dark:from-[#0a0a0f] dark:via-[#0c0c14] dark:to-[#08080c] text-white rounded-3xl p-5 sm:p-7 shadow-2xl border border-slate-800 dark:border-zinc-800">
                <div class="flex flex-col lg:flex-row lg:items-center justify-between gap-4 border-b border-slate-800/80 dark:border-zinc-800/80 pb-4 mb-5">
                    <div>
                        <div class="inline-flex items-center gap-2 bg-blue-500/20 text-blue-300 border border-blue-400/30 px-3 py-1 rounded-full text-[11px] font-bold tracking-wide uppercase mb-1.5">
                            Sales to Fleet Operations
                        </div>
                        <h2 class="text-xl sm:text-2xl font-extrabold tracking-tight">Enterprise Sales to Fleet Command Center</h2>
                        <p class="text-xs text-slate-400 mt-1">Multi-Company Operations: LG Plast, Tagoneswa Hardware & Kreckle Foods</p>
                    </div>
                    <!-- Quick Management Action Buttons -->
                    <div class="flex flex-wrap items-center gap-2 sm:gap-2.5">
                        {"" if not (can_manage_fuel or can_manage_city) else """
                        <button onclick="openCityConfigModal()" class="bg-blue-600 hover:bg-blue-500 text-white px-3.5 py-2 rounded-xl text-xs font-bold transition flex items-center gap-1.5 border border-blue-400/40 shadow-xs cursor-pointer">
                            Fuel & City Rates
                        </button>
                        """}
                        {"" if not can_clear_debt else """
                        <button onclick="openClearPaymentModal()" class="bg-emerald-600 hover:bg-emerald-500 text-white px-3.5 py-2 rounded-xl text-xs font-bold transition flex items-center gap-1.5 border border-emerald-400/40 shadow-xs cursor-pointer">
                            Clear Sales Rep Debt
                        </button>
                        """}
                        {"" if not can_manage_users else """
                        <button onclick="openUserManagementModal()" class="bg-indigo-600 hover:bg-indigo-500 text-white px-3.5 py-2 rounded-xl text-xs font-bold transition flex items-center gap-1.5 border border-indigo-400/40 shadow-xs cursor-pointer">
                            User Permissions
                        </button>
                        """}
                        {"" if not can_view_audit else """
                        <button onclick="openAuditLogsModal()" class="bg-slate-800 hover:bg-slate-700 text-slate-200 px-3 py-2 rounded-xl text-xs font-bold transition flex items-center gap-1.5 border border-slate-700 shadow-xs cursor-pointer">
                            Audit Logs
                        </button>
                        """}
                    </div>
                </div>

                <div class="grid grid-cols-2 md:grid-cols-4 gap-3 sm:gap-4">
                    <div class="bg-slate-800/60 dark:bg-[#121216]/90 backdrop-blur border border-slate-700/60 dark:border-zinc-800/80 rounded-2xl p-4 shadow-xs">
                        <div class="text-[11px] font-bold uppercase tracking-wider text-slate-400 dark:text-zinc-500">Pending Approvals</div>
                        <div class="text-2xl sm:text-3xl font-extrabold text-amber-400 mt-1 font-mono" id="master-active-ops">0</div>
                        <div class="text-[11px] text-slate-400 dark:text-zinc-400 mt-0.5 font-medium">Trips requiring review</div>
                    </div>
                    <div class="bg-slate-800/60 dark:bg-[#121216]/90 backdrop-blur border border-slate-700/60 dark:border-zinc-800/80 rounded-2xl p-4 shadow-xs">
                        <div class="text-[11px] font-bold uppercase tracking-wider text-slate-400 dark:text-zinc-500">Clearance Rate</div>
                        <div class="text-2xl sm:text-3xl font-extrabold text-emerald-400 mt-1 font-mono" id="master-res-rate">100%</div>
                        <div class="text-[11px] text-slate-400 dark:text-zinc-400 mt-0.5 font-medium">Approved vs dispatched</div>
                    </div>
                    {f"""
                    <div class="bg-slate-800/60 dark:bg-[#121216]/90 backdrop-blur border border-slate-700/60 dark:border-zinc-800/80 rounded-2xl p-4 shadow-xs">
                        <div class="text-[11px] font-bold uppercase tracking-wider text-slate-400 dark:text-zinc-500">Transport Billed</div>
                        <div class="text-2xl sm:text-3xl font-extrabold text-blue-400 mt-1 font-mono" id="master-transport-revenue">$0.00</div>
                        <div class="text-[11px] text-slate-400 dark:text-zinc-400 mt-0.5 font-medium">Shortfall recovery charges</div>
                    </div>
                    <div class="bg-slate-800/60 dark:bg-[#121216]/90 backdrop-blur border border-slate-700/60 dark:border-zinc-800/80 rounded-2xl p-4 shadow-xs">
                        <div class="text-[11px] font-bold uppercase tracking-wider text-slate-400 dark:text-zinc-500">Salesperson Debt Backlog</div>
                        <div class="text-2xl sm:text-3xl font-extrabold text-rose-400 mt-1 font-mono" id="master-financial-backlog">$0.00</div>
                        <div class="text-[11px] text-slate-400 dark:text-zinc-400 mt-0.5 font-medium">Pending shortfall recovery</div>
                    </div>
                    """ if can_view_balances else """
                    <div class="bg-slate-800/60 dark:bg-[#121216]/90 backdrop-blur border border-slate-700/60 dark:border-zinc-800/80 rounded-2xl p-4 shadow-xs">
                        <div class="text-[11px] font-bold uppercase tracking-wider text-slate-400 dark:text-zinc-500">Active In-Transit</div>
                        <div class="text-2xl sm:text-3xl font-extrabold text-emerald-400 mt-1 font-mono" id="master-in-transit-count">0</div>
                        <div class="text-[11px] text-slate-400 dark:text-zinc-400 mt-0.5 font-medium">Commercial trips rolling</div>
                    </div>
                    <div class="bg-slate-800/60 dark:bg-[#121216]/90 backdrop-blur border border-slate-700/60 dark:border-zinc-800/80 rounded-2xl p-4 shadow-xs">
                        <div class="text-[11px] font-bold uppercase tracking-wider text-slate-400 dark:text-zinc-500">Commercial Roster</div>
                        <div class="text-2xl sm:text-3xl font-extrabold text-blue-400 mt-1 font-mono" id="master-roster-count">Active Roster</div>
                        <div class="text-[11px] text-slate-400 dark:text-zinc-400 mt-0.5 font-medium">Fleet & Operations</div>
                    </div>
                    """}
                </div>
            </div>

            <!-- Multi-Company Division Selector Bar -->
            <div class="p-3 bg-white dark:bg-[#0c0c10] rounded-2xl border border-slate-200 dark:border-zinc-800 shadow-xs flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                <div class="flex items-center gap-2">
                    <span class="text-xs font-extrabold uppercase tracking-wider text-slate-800 dark:text-zinc-200 flex items-center gap-1.5">
                        <span>🏢</span> Company Division:
                    </span>
                    <span class="text-[11px] text-slate-400 dark:text-zinc-500 hidden md:inline">Partition operational metrics, trips & roster</span>
                </div>
                <div class="flex flex-wrap items-center gap-1.5" id="fleet-company-pills">
                    <button onclick="switchFleetCompany('ALL')" id="fleet-comp-ALL" class="fleet-company-pill px-3.5 py-1.5 rounded-xl text-xs font-bold bg-blue-600 text-white shadow-xs transition cursor-pointer">
                        🌐 All Companies (Master)
                    </button>
                    <button onclick="switchFleetCompany('LG Plast')" id="fleet-comp-LG" class="fleet-company-pill px-3.5 py-1.5 rounded-xl text-xs font-bold text-slate-600 dark:text-zinc-300 hover:bg-slate-100 dark:hover:bg-zinc-800 transition cursor-pointer">
                        🏢 LG Plast
                    </button>
                    <button onclick="switchFleetCompany('Tagoneswa Hardware')" id="fleet-comp-TG" class="fleet-company-pill px-3.5 py-1.5 rounded-xl text-xs font-bold text-slate-600 dark:text-zinc-300 hover:bg-slate-100 dark:hover:bg-zinc-800 transition cursor-pointer">
                        🔨 Tagoneswa Hardware
                    </button>
                    <button onclick="switchFleetCompany('Kreckle Foods')" id="fleet-comp-Kreckle" class="fleet-company-pill px-3.5 py-1.5 rounded-xl text-xs font-bold text-slate-600 dark:text-zinc-300 hover:bg-slate-100 dark:hover:bg-zinc-800 transition cursor-pointer">
                        🌾 Kreckle Foods
                    </button>
                </div>
            </div>

            <!-- Compact Fleet Navigation Control Area -->
            <div class="p-2 sm:p-2.5 bg-white dark:bg-[#0c0c10] rounded-2xl border border-slate-200 dark:border-zinc-800 shadow-xs flex flex-col sm:flex-row sm:items-center justify-between gap-2.5">
                <!-- Mobile Dropdown Selector (sm:hidden) -->
                <div class="sm:hidden w-full">
                    <select id="fleet-view-selector" onchange="switchFleetSubView(this.value)" class="w-full bg-slate-100 dark:bg-zinc-800/90 text-slate-900 dark:text-zinc-100 text-xs font-bold px-3 py-2 rounded-xl border border-slate-300 dark:border-zinc-700 focus:outline-hidden focus:ring-2 focus:ring-blue-500">
                        <option value="overview">Operations Overview</option>
                        <option value="trips">Trip Pipeline</option>
                        {nav_salespersons_opt}
                        {nav_payments_opt}
                        <option value="trucks">Fleet Vehicles</option>
                        <option value="drivers">Commercial Drivers</option>
                        <option value="approvals">Trip Approvals</option>
                        {nav_ledger_opt}
                        {nav_analytics_opt}
                        <option value="all">Consolidated View</option>
                    </select>
                </div>

                <!-- Desktop Segmented Fast-Nav Pills (hidden sm:flex) -->
                <div class="hidden sm:flex items-center gap-1 overflow-x-auto no-scrollbar" id="fleet-fast-nav">
                    <button onclick="switchFleetSubView('overview')" id="fleet-btn-overview" data-view="overview" class="fleet-quick-pill px-3 py-1.5 rounded-xl text-xs font-bold bg-blue-600 text-white shadow-xs transition cursor-pointer whitespace-nowrap">Overview</button>
                    <button onclick="switchFleetSubView('trips')" id="fleet-btn-trips" data-view="trips" class="fleet-quick-pill px-3 py-1.5 rounded-xl text-xs font-bold text-slate-600 dark:text-zinc-300 hover:bg-slate-100 dark:hover:bg-zinc-800 transition cursor-pointer whitespace-nowrap">Trips</button>
                    {nav_salespersons_btn}
                    {nav_payments_btn}
                    <button onclick="switchFleetSubView('trucks')" id="fleet-btn-trucks" data-view="trucks" class="fleet-quick-pill px-3 py-1.5 rounded-xl text-xs font-bold text-slate-600 dark:text-zinc-300 hover:bg-slate-100 dark:hover:bg-zinc-800 transition cursor-pointer whitespace-nowrap">Vehicles</button>
                    <button onclick="switchFleetSubView('drivers')" id="fleet-btn-drivers" data-view="drivers" class="fleet-quick-pill px-3 py-1.5 rounded-xl text-xs font-bold text-slate-600 dark:text-zinc-300 hover:bg-slate-100 dark:hover:bg-zinc-800 transition cursor-pointer whitespace-nowrap">Drivers</button>
                    <button onclick="switchFleetSubView('approvals')" id="fleet-btn-approvals" data-view="approvals" class="fleet-quick-pill px-3 py-1.5 rounded-xl text-xs font-bold text-slate-600 dark:text-zinc-300 hover:bg-slate-100 dark:hover:bg-zinc-800 transition cursor-pointer whitespace-nowrap">Approvals</button>
                    {nav_ledger_btn}
                    {nav_analytics_btn}
                    <button onclick="switchFleetSubView('all')" id="fleet-btn-all" data-view="all" class="fleet-quick-pill px-3 py-1.5 rounded-xl text-xs font-bold text-slate-600 dark:text-zinc-300 hover:bg-slate-100 dark:hover:bg-zinc-800 transition cursor-pointer whitespace-nowrap">All</button>
                </div>

                <!-- Right Live Status Indicator -->
                <div class="hidden sm:flex items-center gap-2 px-3 py-1 text-[11px] font-semibold text-slate-500 dark:text-zinc-400 shrink-0">
                    <span class="w-2 h-2 rounded-full bg-emerald-500 animate-pulse"></span>
                    <span class="font-mono">Live Sync</span>
                </div>
            </div>

            <!-- SUBVIEW 0: OPERATIONS OVERVIEW -->
            <div id="fleet-section-overview" class="fleet-subview-panel space-y-6 transition-all duration-200" style="display: block;">

                <!-- ═══ TIER 1: ACTION REQUIRED ═══ -->
                <div>
                    <div class="flex items-center gap-2 mb-3">
                        <span class="text-[10px] font-black uppercase tracking-widest text-rose-600 dark:text-rose-400">Action Required</span>
                        <span id="ov-alerts-count-badge" class="bg-amber-100 dark:bg-amber-500/10 text-amber-800 dark:text-amber-300 text-[10px] font-bold px-2.5 py-0.5 rounded-full border border-amber-200 dark:border-amber-500/30">0 active</span>
                    </div>
                    <!-- Urgent KPI pills + alert list -->
                    <div class="grid grid-cols-2 md:grid-cols-4 gap-3 mb-3">
                        <!-- Pending Approvals -->
                        <div class="bg-white dark:bg-[#0a0a0d] border border-amber-200/60 dark:border-amber-500/20 rounded-2xl p-4 shadow-xs hover:shadow-md transition">
                            <div class="flex items-center justify-between">
                                <span class="text-[11px] font-bold uppercase tracking-wider text-amber-600 dark:text-amber-400">Trip Approvals</span>
                                <span class="text-[10px] font-mono px-1.5 py-0.5 rounded bg-amber-500/10 text-amber-600 dark:text-amber-400 font-bold">QUEUE</span>
                            </div>
                            <div class="text-2xl sm:text-3xl font-extrabold text-amber-500 dark:text-amber-400 mt-1 font-mono" id="ov-kpi-pending-approvals">0</div>
                            <div class="text-[11px] text-amber-600 dark:text-amber-400 mt-0.5 font-medium truncate" id="ov-kpi-shortfall-sub">0 shortfalls</div>
                        </div>
                        <!-- Action Queue -->
                        <div class="bg-white dark:bg-[#0a0a0d] border border-rose-200/60 dark:border-rose-500/20 rounded-2xl p-4 shadow-xs hover:shadow-md transition">
                            <div class="flex items-center justify-between">
                                <span class="text-[11px] font-bold uppercase tracking-wider text-rose-600 dark:text-rose-400">Action Queue</span>
                                <span class="text-[10px] font-mono px-1.5 py-0.5 rounded bg-rose-500/10 text-rose-600 dark:text-rose-400 font-bold">URGENT</span>
                            </div>
                            <div class="text-2xl sm:text-3xl font-extrabold text-rose-600 dark:text-rose-400 mt-1 font-mono" id="ov-kpi-bottlenecks">0</div>
                            <div class="text-[11px] text-rose-600 dark:text-rose-400 mt-0.5 font-semibold truncate">Priority exceptions</div>
                        </div>
                        <!-- Role-Gated: Sales Pipeline / Rep Debt / Fleet Readiness -->
                        <div class="col-span-2 bg-white dark:bg-[#0a0a0d] border border-slate-200/80 dark:border-zinc-800/80 rounded-2xl p-4 shadow-xs hover:shadow-md transition" id="ov-kpi-card-slot5">
                            <div class="flex items-center justify-between">
                                <span class="text-[11px] font-bold uppercase tracking-wider text-slate-400 dark:text-zinc-500" id="ov-kpi-slot5-title">Commercial Balance</span>
                                <span class="text-[10px] font-mono px-1.5 py-0.5 rounded bg-slate-100 dark:bg-zinc-800 text-slate-500 dark:text-zinc-400 font-bold" id="ov-kpi-slot5-icon">BALANCE</span>
                            </div>
                            <div class="text-2xl sm:text-3xl font-extrabold text-rose-500 dark:text-rose-400 mt-1 font-mono truncate" id="ov-kpi-slot5-val">$0.00</div>
                            <div class="text-[11px] text-slate-500 dark:text-zinc-400 mt-0.5 font-medium truncate" id="ov-kpi-slot5-sub">Outstanding Rep Debt</div>
                        </div>
                    </div>
                    <!-- Prioritized alerts list -->
                    <div class="bg-white dark:bg-[#0a0a0d] border border-slate-200/80 dark:border-zinc-800/80 rounded-2xl shadow-xs overflow-hidden">
                        <div id="ov-alerts-list" class="p-4 sm:p-5 space-y-3 divide-y divide-slate-100 dark:divide-zinc-850/50">
                            <div class="text-center py-8 text-slate-400 dark:text-zinc-500 text-xs">Loading live operations stream...</div>
                        </div>
                    </div>
                </div>

                <!-- ═══ TIER 2: TODAY'S OPERATIONS ═══ -->
                <div>
                    <div class="flex items-center gap-2 mb-3">
                        <span class="text-[10px] font-black uppercase tracking-widest text-blue-600 dark:text-blue-400">Today's Operations</span>
                    </div>
                    <div class="grid grid-cols-2 lg:grid-cols-4 gap-3">
                        <!-- Active Trips -->
                        <div class="bg-white dark:bg-[#0a0a0d] border border-slate-200/80 dark:border-zinc-800/80 rounded-2xl p-4 sm:p-5 shadow-xs hover:shadow-md transition">
                            <div class="flex items-center justify-between">
                                <span class="text-[11px] font-bold uppercase tracking-wider text-slate-400 dark:text-zinc-500">Active Trips</span>
                            </div>
                            <div class="text-2xl sm:text-3xl font-extrabold text-blue-600 dark:text-blue-400 mt-1 font-mono" id="ov-kpi-active-trips">0</div>
                            <div class="text-[11px] text-slate-500 dark:text-zinc-400 mt-0.5 font-medium truncate" id="ov-kpi-transit-trips">0 in transit</div>
                        </div>
                        <!-- Driver Roster -->
                        <div class="bg-white dark:bg-[#0a0a0d] border border-slate-200/80 dark:border-zinc-800/80 rounded-2xl p-4 sm:p-5 shadow-xs hover:shadow-md transition">
                            <div class="flex items-center justify-between">
                                <span class="text-[11px] font-bold uppercase tracking-wider text-slate-400 dark:text-zinc-500">Driver Roster</span>
                            </div>
                            <div class="text-2xl sm:text-3xl font-extrabold text-indigo-600 dark:text-indigo-400 mt-1 font-mono" id="ov-kpi-drivers-active">0</div>
                            <div class="text-[11px] text-slate-500 dark:text-zinc-400 mt-0.5 font-medium truncate" id="ov-kpi-drivers-total">of 0 on roster</div>
                        </div>
                        <!-- Completed Trips -->
                        <div class="bg-white dark:bg-[#0a0a0d] border border-slate-200/80 dark:border-zinc-800/80 rounded-2xl p-4 sm:p-5 shadow-xs hover:shadow-md transition">
                            <div class="flex items-center justify-between">
                                <span class="text-[11px] font-bold uppercase tracking-wider text-slate-400 dark:text-zinc-500">Trips Completed</span>
                            </div>
                            <div class="text-2xl sm:text-3xl font-extrabold text-emerald-600 dark:text-emerald-400 mt-1 font-mono" id="ov-kpi-completed-trips">0</div>
                            <div class="text-[11px] text-slate-500 dark:text-zinc-400 mt-0.5 font-medium truncate">Successfully settled</div>
                        </div>
                        <!-- Average Revenue per Trip -->
                        {f"""
                        <div class="bg-white dark:bg-[#0a0a0d] border border-slate-200/80 dark:border-zinc-800/80 rounded-2xl p-4 sm:p-5 shadow-xs hover:shadow-md transition">
                            <div class="flex items-center justify-between">
                                <span class="text-[11px] font-bold uppercase tracking-wider text-slate-400 dark:text-zinc-500">Avg Revenue / Trip</span>
                            </div>
                            <div class="text-2xl sm:text-3xl font-extrabold text-slate-800 dark:text-zinc-100 mt-1 font-mono truncate" id="ov-kpi-avg-revenue">$0.00</div>
                            <div class="text-[11px] text-slate-500 dark:text-zinc-400 mt-0.5 font-medium truncate">Manifest revenue mean</div>
                        </div>
                        """ if can_view_balances else """
                        <div class="bg-white dark:bg-[#0a0a0d] border border-slate-200/80 dark:border-zinc-800/80 rounded-2xl p-4 sm:p-5 shadow-xs hover:shadow-md transition">
                            <div class="flex items-center justify-between">
                                <span class="text-[11px] font-bold uppercase tracking-wider text-slate-400 dark:text-zinc-500">Active In-Transit</span>
                            </div>
                            <div class="text-2xl sm:text-3xl font-extrabold text-blue-600 dark:text-blue-400 mt-1 font-mono truncate" id="ov-kpi-transit-ops">0</div>
                            <div class="text-[11px] text-slate-500 dark:text-zinc-400 mt-0.5 font-medium truncate">Currently rolling</div>
                        </div>
                        """}
                    </div>
                </div>

                <!-- ═══ TIER 3: FLEET STATUS ═══ -->
                <div>
                    <div class="flex items-center gap-2 mb-3">
                        <span class="text-[10px] font-black uppercase tracking-widest text-emerald-600 dark:text-emerald-400">Fleet Status</span>
                        <span class="text-[10px] text-slate-400 dark:text-zinc-500 font-medium">Live from workshop tickets</span>
                    </div>
                    <div class="bg-white dark:bg-[#0a0a0d] border border-slate-200/80 dark:border-zinc-800/80 rounded-2xl shadow-xs overflow-hidden">
                        <div class="grid grid-cols-2 md:grid-cols-5 divide-y md:divide-y-0 md:divide-x divide-slate-100 dark:divide-zinc-800/60">
                            <!-- Available -->
                            <div class="p-4 sm:p-5 text-center hover:bg-slate-50 dark:hover:bg-[#0e0e12] transition">
                                <div class="text-[10px] font-bold uppercase tracking-wider text-slate-400 dark:text-zinc-500 mb-1">Available</div>
                                <div class="text-2xl sm:text-3xl font-extrabold text-emerald-600 dark:text-emerald-400 font-mono" id="ov-kpi-trucks-ready">0</div>
                                <div class="text-[10px] text-emerald-600 dark:text-emerald-400 mt-0.5 font-semibold">Field Ready</div>
                            </div>
                            <!-- In Workshop -->
                            <div class="p-4 sm:p-5 text-center hover:bg-slate-50 dark:hover:bg-[#0e0e12] transition">
                                <div class="text-[10px] font-bold uppercase tracking-wider text-slate-400 dark:text-zinc-500 mb-1">In Workshop</div>
                                <div class="text-2xl sm:text-3xl font-extrabold text-orange-500 dark:text-orange-400 font-mono" id="ov-kpi-trucks-in-workshop">0</div>
                                <div class="text-[10px] text-orange-500 dark:text-orange-400 mt-0.5 font-semibold">Under Repair</div>
                            </div>
                            <!-- Awaiting Parts -->
                            <div class="p-4 sm:p-5 text-center hover:bg-slate-50 dark:hover:bg-[#0e0e12] transition">
                                <div class="text-[10px] font-bold uppercase tracking-wider text-slate-400 dark:text-zinc-500 mb-1">Awaiting Parts</div>
                                <div class="text-2xl sm:text-3xl font-extrabold text-amber-500 dark:text-amber-400 font-mono" id="ov-kpi-trucks-awaiting-parts">0</div>
                                <div class="text-[10px] text-amber-500 dark:text-amber-400 mt-0.5 font-semibold">Parts Requisition</div>
                            </div>
                            <!-- Awaiting QC -->
                            <div class="p-4 sm:p-5 text-center hover:bg-slate-50 dark:hover:bg-[#0e0e12] transition">
                                <div class="text-[10px] font-bold uppercase tracking-wider text-slate-400 dark:text-zinc-500 mb-1">Awaiting QC</div>
                                <div class="text-2xl sm:text-3xl font-extrabold text-blue-500 dark:text-blue-400 font-mono" id="ov-kpi-trucks-awaiting-qc">0</div>
                                <div class="text-[10px] text-blue-500 dark:text-blue-400 mt-0.5 font-semibold">QC Sign-Off</div>
                            </div>
                            <!-- Total -->
                            <div class="p-4 sm:p-5 text-center hover:bg-slate-50 dark:hover:bg-[#0e0e12] transition bg-slate-50/50 dark:bg-[#0e0e12]/50">
                                <div class="text-[10px] font-bold uppercase tracking-wider text-slate-400 dark:text-zinc-500 mb-1">Total Fleet</div>
                                <div class="text-2xl sm:text-3xl font-extrabold text-slate-700 dark:text-zinc-200 font-mono" id="ov-kpi-trucks-total">0</div>
                                <div class="text-[10px] text-slate-500 dark:text-zinc-400 mt-0.5 font-medium">Commercial vehicles</div>
                            </div>
                        </div>
                    </div>
                </div>

                <!-- ═══ TIER 4: FINANCIAL OVERVIEW ═══ -->
                {f"""
                <div id="ov-financial-tier-4">
                    <div class="flex items-center gap-2 mb-3">
                        <span class="text-[10px] font-black uppercase tracking-widest text-indigo-600 dark:text-indigo-400">Financial Overview</span>
                        <span class="text-[10px] text-slate-400 dark:text-zinc-500 font-medium">Trip manifests, billings & ledger totals</span>
                    </div>
                    <div class="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
                        <div class="bg-white dark:bg-[#0a0a0d] border border-slate-200/80 dark:border-zinc-800/80 rounded-2xl p-4 shadow-xs">
                            <div class="text-[10px] font-bold uppercase tracking-wider text-slate-400 dark:text-zinc-500">Total Sales Value</div>
                            <div class="text-lg sm:text-xl font-extrabold text-emerald-600 dark:text-emerald-400 font-mono mt-1 truncate" id="ov-fin-total-sales">$0.00</div>
                            <div class="text-[10px] text-slate-500 dark:text-zinc-400 mt-0.5 truncate">Across all trips</div>
                        </div>
                        <div class="bg-white dark:bg-[#0a0a0d] border border-slate-200/80 dark:border-zinc-800/80 rounded-2xl p-4 shadow-xs">
                            <div class="text-[10px] font-bold uppercase tracking-wider text-slate-400 dark:text-zinc-500">Transport Charges</div>
                            <div class="text-lg sm:text-xl font-extrabold text-blue-600 dark:text-blue-400 font-mono mt-1 truncate" id="ov-fin-transport-charges">$0.00</div>
                            <div class="text-[10px] text-slate-500 dark:text-zinc-400 mt-0.5 truncate">Direct shortfall fees</div>
                        </div>
                        <div class="bg-white dark:bg-[#0a0a0d] border border-slate-200/80 dark:border-zinc-800/80 rounded-2xl p-4 shadow-xs">
                            <div class="text-[10px] font-bold uppercase tracking-wider text-slate-400 dark:text-zinc-500">Total Opex</div>
                            <div class="text-lg sm:text-xl font-extrabold text-orange-600 dark:text-orange-400 font-mono mt-1 truncate" id="ov-fin-total-opex">$0.00</div>
                            <div class="text-[10px] text-slate-500 dark:text-zinc-400 mt-0.5 truncate">Allowances & fuel</div>
                        </div>
                        <div class="bg-white dark:bg-[#0a0a0d] border border-slate-200/80 dark:border-zinc-800/80 rounded-2xl p-4 shadow-xs">
                            <div class="text-[10px] font-bold uppercase tracking-wider text-slate-400 dark:text-zinc-500">Net Position</div>
                            <div class="text-lg sm:text-xl font-extrabold text-indigo-600 dark:text-indigo-400 font-mono mt-1 truncate" id="ov-fin-net-margin">$0.00</div>
                            <div class="text-[10px] text-slate-500 dark:text-zinc-400 mt-0.5 truncate">Sales less opex</div>
                        </div>
                        <div class="bg-white dark:bg-[#0a0a0d] border border-slate-200/80 dark:border-zinc-800/80 rounded-2xl p-4 shadow-xs">
                            <div class="text-[10px] font-bold uppercase tracking-wider text-slate-400 dark:text-zinc-500">Outstanding Debt</div>
                            <div class="text-lg sm:text-xl font-extrabold text-rose-600 dark:text-rose-400 font-mono mt-1 truncate" id="ov-fin-debt-backlog">$0.00</div>
                            <div class="text-[10px] text-slate-500 dark:text-zinc-400 mt-0.5 truncate">Pending recovery</div>
                        </div>
                        <div class="bg-white dark:bg-[#0a0a0d] border border-slate-200/80 dark:border-zinc-800/80 rounded-2xl p-4 shadow-xs">
                            <div class="text-[10px] font-bold uppercase tracking-wider text-slate-400 dark:text-zinc-500">Cleared Payments</div>
                            <div class="text-lg sm:text-xl font-extrabold text-teal-600 dark:text-teal-400 font-mono mt-1 truncate" id="ov-fin-cleared-payments">$0.00</div>
                            <div class="text-[10px] text-slate-500 dark:text-zinc-400 mt-0.5 truncate">Accounts settled</div>
                        </div>
                    </div>
                </div>
                """ if can_view_balances else ""}

                <!-- ═══ TIER 5: OPERATIONAL EXPENSES ═══ -->
                <div>
                    <div class="flex items-center gap-2 mb-3">
                        <span class="text-[10px] font-black uppercase tracking-widest text-orange-600 dark:text-orange-400">Operational Expenses</span>
                        <span class="text-[10px] text-slate-400 dark:text-zinc-500 font-medium">Allowances breakdown & roadside incidents</span>
                    </div>
                    <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
                        <!-- Driver Allowances Summary -->
                        <div class="bg-white dark:bg-[#0a0a0d] border border-slate-200/80 dark:border-zinc-800/80 rounded-2xl p-4 sm:p-5 shadow-xs space-y-2.5">
                            <div class="flex items-center justify-between">
                                <span class="text-xs font-bold text-slate-700 dark:text-zinc-300">Driver Allowances</span>
                                <span class="text-xs font-extrabold font-mono text-slate-900 dark:text-zinc-100" id="ov-exp-total-allowances">$0.00</span>
                            </div>
                            <div class="space-y-1.5 pt-1 text-[11px] text-slate-500 dark:text-zinc-400">
                                <div class="flex items-center justify-between">
                                    <span>Meals</span>
                                    <strong class="font-mono text-slate-700 dark:text-zinc-200" id="ov-exp-meals">$0.00</strong>
                                </div>
                                <div class="flex items-center justify-between">
                                    <span>Accommodation</span>
                                    <strong class="font-mono text-slate-700 dark:text-zinc-200" id="ov-exp-accommodation">$0.00</strong>
                                </div>
                                <div class="flex items-center justify-between">
                                    <span>Toll Fees</span>
                                    <strong class="font-mono text-slate-700 dark:text-zinc-200" id="ov-exp-tolls">$0.00</strong>
                                </div>
                            </div>
                        </div>
                        <!-- Emergency Incidents -->
                        <div class="bg-white dark:bg-[#0a0a0d] border border-slate-200/80 dark:border-zinc-800/80 rounded-2xl p-4 sm:p-5 shadow-xs space-y-2.5">
                            <div class="flex items-center justify-between">
                                <span class="text-xs font-bold text-slate-700 dark:text-zinc-300">Emergency & Incident Expenses</span>
                                <span class="text-xs font-extrabold font-mono text-rose-600 dark:text-rose-400" id="ov-exp-total-emergency">$0.00</span>
                            </div>
                            <div class="space-y-1.5 pt-1 text-[11px] text-slate-500 dark:text-zinc-400">
                                <div class="flex items-center justify-between">
                                    <span>Emergency Fuel</span>
                                    <strong class="font-mono text-slate-700 dark:text-zinc-200" id="ov-exp-emergency-fuel">$0.00</strong>
                                </div>
                                <div class="flex items-center justify-between">
                                    <span>Breakdowns & Other</span>
                                    <strong class="font-mono text-slate-700 dark:text-zinc-200" id="ov-exp-emergency-other">$0.00</strong>
                                </div>
                            </div>
                        </div>
                        <!-- Cost per Trip Metrics -->
                        <div class="bg-white dark:bg-[#0a0a0d] border border-slate-200/80 dark:border-zinc-800/80 rounded-2xl p-4 sm:p-5 shadow-xs space-y-2.5">
                            <div class="text-xs font-bold text-slate-700 dark:text-zinc-300">Averages per Trip</div>
                            <div class="space-y-2 pt-1 text-[11px] text-slate-500 dark:text-zinc-400">
                                <div class="flex items-center justify-between">
                                    <span>Avg Opex / Trip</span>
                                    <strong class="font-mono text-orange-600 dark:text-orange-400" id="ov-exp-avg-opex">$0.00</strong>
                                </div>
                                <div class="flex items-center justify-between">
                                    <span>Avg Allowance / Trip</span>
                                    <strong class="font-mono text-indigo-600 dark:text-indigo-400" id="ov-exp-avg-allowance">$0.00</strong>
                                </div>
                            </div>
                        </div>
                        <!-- Recovery & Deficit Ratio -->
                        <div class="bg-white dark:bg-[#0a0a0d] border border-slate-200/80 dark:border-zinc-800/80 rounded-2xl p-4 sm:p-5 shadow-xs space-y-2.5">
                            <div class="text-xs font-bold text-slate-700 dark:text-zinc-300">Shortfall Recovery Rate</div>
                            <div class="text-2xl font-extrabold text-emerald-600 dark:text-emerald-400 font-mono mt-1" id="ov-rev-recovery-rate">100%</div>
                            <div class="text-[11px] text-slate-500 dark:text-zinc-400">
                                Total Shortfall: <strong class="font-mono text-slate-700 dark:text-zinc-200" id="ov-rev-shortfall-total">$0.00</strong><br>
                                Total Recovered: <strong class="font-mono text-emerald-600 dark:text-emerald-400" id="ov-rev-recovered-total">$0.00</strong>
                            </div>
                        </div>
                    </div>
                </div>

                <!-- ═══ TIER 6 & 7: ROUTE / CITY PERFORMANCE & FLEET WORKSHOP IMPACT (two columns) ═══ -->
                <div class="grid grid-cols-1 lg:grid-cols-12 gap-5">
                    <!-- Top Destinations & Routes (7 cols) -->
                    <div class="lg:col-span-7 space-y-3">
                        <div class="flex items-center justify-between">
                            <span class="text-[10px] font-black uppercase tracking-widest text-slate-600 dark:text-zinc-400">Route & City Performance</span>
                            <span class="text-[10px] text-slate-400 font-medium">Historical trip volume</span>
                        </div>
                        <div class="bg-white dark:bg-[#0a0a0d] border border-slate-200/80 dark:border-zinc-800/80 rounded-2xl shadow-xs overflow-hidden">
                            <div class="overflow-x-auto">
                                <table class="w-full text-left text-xs min-w-[420px]">
                                    <thead class="bg-slate-50 dark:bg-[#121216] text-slate-500 dark:text-zinc-400 font-bold uppercase tracking-wider border-b border-slate-200 dark:border-zinc-800">
                                        <tr>
                                            <th class="px-4 py-2.5">Destination City</th>
                                            <th class="px-4 py-2.5 text-center">Trips</th>
                                            <th class="px-4 py-2.5 text-right">Sales Value</th>
                                            <th class="px-4 py-2.5 text-right">Allowances</th>
                                        </tr>
                                    </thead>
                                    <tbody id="ov-top-cities-body" class="divide-y divide-slate-100 dark:divide-zinc-850/60 text-slate-700 dark:text-zinc-200">
                                        <tr><td colspan="4" class="px-4 py-4 text-center text-slate-400 text-xs">Loading destinations...</td></tr>
                                    </tbody>
                                </table>
                            </div>
                        </div>
                    </div>

                    <!-- Fleet & Workshop Impact (5 cols) -->
                    <div class="lg:col-span-5 space-y-3">
                        <div class="flex items-center justify-between">
                            <span class="text-[10px] font-black uppercase tracking-widest text-slate-600 dark:text-zinc-400">Fleet & Workshop Performance</span>
                        </div>
                        <div class="bg-white dark:bg-[#0a0a0d] border border-slate-200/80 dark:border-zinc-800/80 rounded-2xl p-4 sm:p-5 shadow-xs space-y-4">
                            <div>
                                <div class="flex items-center justify-between text-xs mb-1">
                                    <span class="text-slate-600 dark:text-zinc-400 font-bold">Fleet Utilization</span>
                                    <span class="font-extrabold font-mono text-blue-600 dark:text-blue-400" id="ov-perf-utilization">0%</span>
                                </div>
                                <div class="w-full bg-slate-100 dark:bg-zinc-800 rounded-full h-2 overflow-hidden">
                                    <div id="ov-perf-util-bar" class="bg-blue-600 h-2 rounded-full" style="width: 0%"></div>
                                </div>
                                <div class="text-[10px] text-slate-400 mt-1">Active dispatched trips relative to field-ready trucks</div>
                            </div>
                            <div class="pt-2 border-t border-slate-100 dark:border-zinc-800/60 flex items-center justify-between">
                                <span class="text-xs text-slate-600 dark:text-zinc-400">Vehicles in Workshop</span>
                                <span class="text-sm font-extrabold text-orange-500 font-mono" id="ov-perf-ws-impact">0 trucks</span>
                            </div>
                            <div class="pt-2 border-t border-slate-100 dark:border-zinc-800/60" id="ov-financial-section">
                                <div class="text-xs font-bold text-slate-700 dark:text-zinc-300 mb-2">Financial Exceptions Summary</div>
                                <div id="ov-financial-body" class="space-y-1.5 text-xs">
                                    <div class="text-center py-2 text-slate-400 text-xs">Loading financial exceptions...</div>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>

                <!-- ═══ TIER 8 & 9: RECENT OPERATIONS ACTIVITY & RECENT AUDIT (two columns) ═══ -->
                <div class="grid grid-cols-1 lg:grid-cols-12 gap-5">
                    <!-- Recent Activity Feed (6 cols) -->
                    <div class="lg:col-span-6 space-y-3">
                        <div class="flex items-center gap-2">
                            <span class="text-[10px] font-black uppercase tracking-widest text-slate-600 dark:text-zinc-400">Recent Operations Activity</span>
                            <span class="flex items-center gap-1 text-[10px] font-semibold text-emerald-600 dark:text-emerald-400">
                                <span class="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse"></span> Live
                            </span>
                        </div>
                        <div class="bg-white dark:bg-[#0a0a0d] border border-slate-200/80 dark:border-zinc-800/80 rounded-2xl shadow-xs overflow-hidden">
                            <div id="ov-activity-list" class="p-4 space-y-3 max-h-[460px] overflow-y-auto no-scrollbar">
                                <div class="text-center py-8 text-slate-400 dark:text-zinc-500 text-xs">Loading recent activity...</div>
                            </div>
                        </div>
                    </div>

                    <!-- Tier 10: Recent Financial Audit Trail (6 cols) -->
                    <div class="lg:col-span-6 space-y-3">
                        <div class="flex items-center justify-between">
                            <span class="text-[10px] font-black uppercase tracking-widest text-slate-600 dark:text-zinc-400">Financial Audit Log</span>
                            <button onclick="switchFleetSubView('ledger')" class="text-[11px] font-bold text-blue-600 hover:text-blue-500 cursor-pointer">View Full Ledger →</button>
                        </div>
                        <div class="bg-white dark:bg-[#0a0a0d] border border-slate-200/80 dark:border-zinc-800/80 rounded-2xl shadow-xs overflow-hidden">
                            <div class="overflow-x-auto">
                                <table class="w-full text-left text-xs min-w-[420px]">
                                    <thead class="bg-slate-50 dark:bg-[#121216] text-slate-500 dark:text-zinc-400 font-bold uppercase tracking-wider border-b border-slate-200 dark:border-zinc-800">
                                        <tr>
                                            <th class="px-4 py-2.5">Time</th>
                                            <th class="px-4 py-2.5">Actor</th>
                                            <th class="px-4 py-2.5">Event</th>
                                            <th class="px-4 py-2.5">Details</th>
                                        </tr>
                                    </thead>
                                    <tbody id="ov-recent-audit-body" class="divide-y divide-slate-100 dark:divide-zinc-850/60 text-slate-700 dark:text-zinc-200">
                                        <tr><td colspan="4" class="px-4 py-4 text-center text-slate-400 text-xs">Loading audit trail...</td></tr>
                                    </tbody>
                                </table>
                            </div>
                        </div>
                    </div>
                </div>

            </div>


            <!-- SUBVIEW 1: TRIP PIPELINE -->
            <div id="fleet-section-trips" class="fleet-subview-panel bg-white dark:bg-[#0a0a0d] border border-slate-200/80 dark:border-zinc-800/80 rounded-2xl shadow-xs overflow-hidden transition-all duration-200" style="display: none;">
                <div class="p-4 sm:p-5 border-b border-slate-200 dark:border-zinc-850 flex flex-col md:flex-row items-stretch md:items-center justify-between gap-3 sm:gap-4 bg-slate-50/60 dark:bg-[#0e0e12]/80">
                    <div class="flex flex-col sm:flex-row flex-wrap items-stretch sm:items-center gap-2 sm:gap-3 w-full md:w-auto">
                        <input type="text" id="trips-search" placeholder="Search Trip #, Driver, Truck, City..." oninput="filterTripsTable(true)" class="bg-white dark:bg-[#121216] border border-slate-300 dark:border-zinc-750 rounded-xl px-4 py-2 text-xs font-medium text-slate-800 dark:text-zinc-100 placeholder-slate-400 dark:placeholder-zinc-500 focus:outline-none focus:ring-2 focus:ring-blue-500 w-full sm:w-64 transition">
                        
                        <select id="trips-stage-filter" onchange="filterTripsTable(true)" class="bg-white dark:bg-[#121216] border border-slate-300 dark:border-zinc-750 rounded-xl px-3 py-2 text-xs font-medium text-slate-700 dark:text-zinc-200 focus:outline-none focus:ring-2 focus:ring-blue-500 w-full sm:w-auto transition">
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
                        <span id="trips-count-badge" class="bg-blue-50 dark:bg-blue-500/10 text-blue-700 dark:text-blue-300 border border-blue-200 dark:border-blue-500/30 text-xs font-bold px-3 py-1.5 rounded-full">
                            Showing 0 trips
                        </span>
                    </div>
                </div>

                <div class="overflow-x-auto">
                    <table class="w-full text-left text-xs min-w-[900px]">
                        <thead class="bg-slate-100/75 dark:bg-[#0e0e12] text-slate-500 dark:text-zinc-400 font-bold uppercase tracking-wider border-b border-slate-200 dark:border-zinc-800">
                            <tr>
                                <th class="px-4 sm:px-5 py-3.5 whitespace-nowrap">Trip ID</th>
                                <th class="px-4 sm:px-5 py-3.5 whitespace-nowrap">Stage & Status</th>
                                <th class="px-4 sm:px-5 py-3.5 whitespace-nowrap">Sales Rep & Client</th>
                                <th class="px-4 sm:px-5 py-3.5 whitespace-nowrap">Destination & Route</th>
                                <th class="px-4 sm:px-5 py-3.5 whitespace-nowrap">Truck & Driver</th>
                                <th class="px-4 sm:px-5 py-3.5 whitespace-nowrap">Allowance / Transport</th>
                                <th class="px-4 sm:px-5 py-3.5 whitespace-nowrap">Timestamps</th>
                                <th class="px-4 sm:px-5 py-3.5 whitespace-nowrap">Odometer (KM)</th>
                            </tr>
                        </thead>
                        <tbody id="fleet-trips-table-body" class="divide-y divide-slate-200 dark:divide-zinc-850 text-slate-700 dark:text-zinc-200"></tbody>
                    </table>
                </div>

                <div class="p-3.5 sm:p-4 border-t border-slate-200 dark:border-zinc-850 flex flex-col sm:flex-row items-center justify-between gap-3 bg-slate-50/60 dark:bg-[#0c0c10]/80">
                    <div class="text-xs text-slate-500 dark:text-zinc-400 font-medium" id="trips-pagination-info">Showing 0 entries</div>
                    <div class="flex items-center gap-1.5" id="trips-pagination-controls"></div>
                </div>
            </div>

            <!-- SUBVIEW 2: SALESPERSON DEBT LEDGER & BALANCES -->
            {f"""
            <div id="fleet-section-salespersons" class="fleet-subview-panel bg-white dark:bg-[#0a0a0d] border border-slate-200/80 dark:border-zinc-800/80 rounded-2xl p-5 sm:p-6 shadow-xs">
                <div class="flex flex-col sm:flex-row sm:items-center justify-between mb-4 gap-2">
                    <div>
                        <h2 class="text-xs sm:text-sm font-extrabold uppercase tracking-wider text-slate-900 dark:text-zinc-100 flex items-center gap-2">
                            """ + ("Sales Representative Balances" if can_view_balances else "Sales Representative Directory") + f"""
                        </h2>
                        <p class="text-[11px] text-slate-500 dark:text-zinc-400 mt-0.5">""" + ("Real-time balances tracked per sales representative with instant clearance action" if can_view_balances else "Commercial sales representative roster and contact directory across LG Plast, Tagoneswa Hardware and Kreckle") + f"""</p>
                    </div>
                    <div class="flex items-center gap-2.5">
                        {"" if not (user_has_permission(user, "manage_sales_pipeline") or can_manage_trucks) else '''
                        <button onclick="openAddSalesRepModal()" class="bg-indigo-600 hover:bg-indigo-700 text-white font-bold px-3 py-1.5 rounded-xl text-xs transition flex items-center gap-1.5 shadow-xs cursor-pointer">
                            <span>+</span> Add Sales Rep / Admin
                        </button>
                        '''}
                        {"" if not can_clear_debt else '''
                        <button onclick="openClearPaymentModal()" class="bg-emerald-600 hover:bg-emerald-700 text-white font-bold px-3 py-1.5 rounded-xl text-xs transition flex items-center gap-1.5 shadow-xs cursor-pointer">
                            Clear Debt Payment
                        </button>
                        '''}
                        {f"""
                        <div class="text-right">
                            <span class="text-xs font-bold text-slate-500 dark:text-zinc-400">Total Pending: </span>
                            <span class="text-sm font-extrabold text-rose-600 dark:text-rose-400 font-mono" id="fleet-total-pending-pill">$0.00</span>
                        </div>
                        """ if can_view_balances else ""}
                    </div>
                </div>
                <div class="flex flex-col sm:flex-row items-stretch sm:items-center justify-between gap-2.5 mb-4 pb-3 border-b border-slate-100 dark:border-zinc-850">
                    <div class="flex flex-wrap items-center gap-1.5" id="sp-company-filters">
                        <button onclick="filterSalespersonsByCompany('ALL')" id="sp-filter-ALL" class="sp-filter-btn px-3 py-1.5 rounded-xl text-xs font-bold bg-blue-600 text-white shadow-xs transition cursor-pointer">All Divisions</button>
                        <button onclick="filterSalespersonsByCompany('LG Plast')" id="sp-filter-LG" class="sp-filter-btn px-3 py-1.5 rounded-xl text-xs font-bold text-slate-600 dark:text-zinc-300 hover:bg-slate-100 dark:hover:bg-zinc-800 transition cursor-pointer">LG Plast</button>
                        <button onclick="filterSalespersonsByCompany('Tagoneswa Hardware')" id="sp-filter-TG" class="sp-filter-btn px-3 py-1.5 rounded-xl text-xs font-bold text-slate-600 dark:text-zinc-300 hover:bg-slate-100 dark:hover:bg-zinc-800 transition cursor-pointer">Tagoneswa Hardware</button>
                        <button onclick="filterSalespersonsByCompany('Kreckle Foods')" id="sp-filter-Kreckle" class="sp-filter-btn px-3 py-1.5 rounded-xl text-xs font-bold text-slate-600 dark:text-zinc-300 hover:bg-slate-100 dark:hover:bg-zinc-800 transition cursor-pointer">Kreckle Foods</button>
                    </div>
                    <div class="relative sm:w-64">
                        <input type="text" id="sp-search-input" onkeyup="filterSalespersonsSearch()" placeholder="Search rep or phone..." class="w-full px-3 py-1.5 text-xs rounded-xl bg-slate-50 dark:bg-[#121216] border border-slate-200 dark:border-zinc-800 text-slate-800 dark:text-zinc-200 focus:outline-none focus:ring-1 focus:ring-blue-500">
                    </div>
                </div>
                <div class="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-3 sm:gap-4" id="fleet-salesperson-cards">
                    <!-- Populated dynamically -->
                </div>
            </div>

            <!-- SUBVIEW 3: PAYMENT HISTORY -->
            <div id="fleet-section-payments" class="fleet-subview-panel bg-white dark:bg-[#0a0a0d] border border-slate-200/80 dark:border-zinc-800/80 rounded-2xl shadow-xs overflow-hidden transition-all duration-200">
                <div class="p-4 sm:p-5 border-b border-slate-200 dark:border-zinc-850 flex flex-col md:flex-row items-stretch md:items-center justify-between gap-3 sm:gap-4 bg-slate-50/60 dark:bg-[#0e0e12]/80">
                    <div>
                        <h3 class="text-xs sm:text-sm font-extrabold uppercase tracking-wider text-slate-900 dark:text-zinc-100 flex items-center gap-2">
                            Payment History
                        </h3>
                        <p class="text-[11px] text-slate-500 dark:text-zinc-400">Official accounting verification and payment offset audit history</p>
                    </div>
                    {"" if not can_clear_debt else '''
                    <button onclick="openClearPaymentModal()" class="bg-emerald-600 hover:bg-emerald-700 text-white font-bold px-3.5 py-1.5 rounded-xl text-xs transition flex items-center gap-1.5 shadow-xs cursor-pointer self-start sm:self-auto">
                        <span>+</span> Record New Clearance
                    </button>
                    '''}
                </div>

                <div class="overflow-x-auto">
                    <table class="w-full text-left text-xs min-w-[850px]">
                        <thead class="bg-slate-100/75 dark:bg-[#0e0e12] text-slate-500 dark:text-zinc-400 font-bold uppercase tracking-wider border-b border-slate-200 dark:border-zinc-800">
                            <tr>
                                <th class="px-4 sm:px-5 py-3.5 whitespace-nowrap">Payment Date</th>
                                <th class="px-4 sm:px-5 py-3.5 whitespace-nowrap">Sales Representative</th>
                                <th class="px-4 sm:px-5 py-3.5 whitespace-nowrap">Amount Cleared</th>
                                <th class="px-4 sm:px-5 py-3.5 whitespace-nowrap">Method & Reference</th>
                                <th class="px-4 sm:px-5 py-3.5 whitespace-nowrap">Balance Impact</th>
                                <th class="px-4 sm:px-5 py-3.5 whitespace-nowrap">Recorded By</th>
                                <th class="px-4 sm:px-5 py-3.5 whitespace-nowrap">Remarks / Notes</th>
                            </tr>
                        </thead>
                        <tbody id="fleet-payments-table-body" class="divide-y divide-slate-200 dark:divide-zinc-850 text-slate-700 dark:text-zinc-200"></tbody>
                    </table>
                </div>

                <div class="p-3.5 sm:p-4 border-t border-slate-200 dark:border-zinc-850 flex flex-col sm:flex-row items-center justify-between gap-3 bg-slate-50/60 dark:bg-[#0c0c10]/80">
                    <div class="text-xs text-slate-500 dark:text-zinc-400 font-medium" id="payments-pagination-info">Showing 0 entries</div>
                    <div class="flex items-center gap-1.5" id="payments-pagination-controls"></div>
                </div>
            </div>
            """ if can_view_balances else ""}

            <!-- SUBVIEW 4: FLEET VEHICLES -->
            <div id="fleet-section-trucks" class="fleet-subview-panel bg-white dark:bg-[#0a0a0d] border border-slate-200/80 dark:border-zinc-800/80 rounded-2xl shadow-xs overflow-hidden transition-all duration-200">
                <div class="p-4 sm:p-5 border-b border-slate-200 dark:border-zinc-850 flex flex-col md:flex-row items-stretch md:items-center justify-between gap-3 sm:gap-4 bg-slate-50/60 dark:bg-[#0e0e12]/80">
                    <div>
                        <h3 class="text-xs sm:text-sm font-extrabold uppercase tracking-wider text-slate-900 dark:text-zinc-100 flex items-center gap-2">
                            Fleet Vehicles
                        </h3>
                        <p class="text-[11px] text-slate-500 dark:text-zinc-400">Verified commercial delivery vehicles registered in Tagoneswa database</p>
                    </div>
                    <div class="flex items-center gap-2 w-full sm:w-auto">
                        <input type="text" id="trucks-search" placeholder="Search Truck #, Plate, Model..." oninput="filterTrucksTable(true)" class="bg-white dark:bg-[#121216] border border-slate-300 dark:border-zinc-750 rounded-xl px-4 py-2 text-xs font-medium text-slate-800 dark:text-zinc-100 placeholder-slate-400 dark:placeholder-zinc-500 focus:outline-none focus:ring-2 focus:ring-blue-500 w-full sm:w-64 transition">
                        <button onclick="openAddTruckModal()" class="bg-blue-600 hover:bg-blue-700 text-white font-bold px-3.5 py-2 rounded-xl text-xs transition flex items-center gap-1.5 shadow-xs cursor-pointer whitespace-nowrap">
                            <span>+</span> Add Truck
                        </button>
                    </div>
                </div>

                <div class="overflow-x-auto">
                    <table class="w-full text-left text-xs min-w-[800px]">
                        <thead class="bg-slate-100/75 dark:bg-[#0e0e12] text-slate-500 dark:text-zinc-400 font-bold uppercase tracking-wider border-b border-slate-200 dark:border-zinc-800">
                            <tr>
                                <th class="px-4 sm:px-5 py-3.5 whitespace-nowrap">Truck #</th>
                                <th class="px-4 sm:px-5 py-3.5 whitespace-nowrap">Plate Number</th>
                                <th class="px-4 sm:px-5 py-3.5 whitespace-nowrap">Model & Make</th>
                                <th class="px-4 sm:px-5 py-3.5 whitespace-nowrap">Body Type</th>
                                <th class="px-4 sm:px-5 py-3.5 whitespace-nowrap">Home Depot</th>
                                <th class="px-4 sm:px-5 py-3.5 whitespace-nowrap">Active Status</th>
                                <th class="px-4 sm:px-5 py-3.5 text-right whitespace-nowrap">Action</th>
                            </tr>
                        </thead>
                        <tbody id="fleet-trucks-table-body" class="divide-y divide-slate-200 dark:divide-zinc-850 text-slate-700 dark:text-zinc-200"></tbody>
                    </table>
                </div>

                <div class="p-3.5 sm:p-4 border-t border-slate-200 dark:border-zinc-850 flex flex-col sm:flex-row items-center justify-between gap-3 bg-slate-50/60 dark:bg-[#0c0c10]/80">
                    <div class="text-xs text-slate-500 dark:text-zinc-400 font-medium" id="trucks-pagination-info">Showing 0 entries</div>
                    <div class="flex items-center gap-1.5" id="trucks-pagination-controls"></div>
                </div>
            </div>

            <!-- SUBVIEW 5: COMMERCIAL DRIVERS -->
            <div id="fleet-section-drivers" class="fleet-subview-panel bg-white dark:bg-[#0a0a0d] border border-slate-200/80 dark:border-zinc-800/80 rounded-2xl shadow-xs overflow-hidden transition-all duration-200">
                <div class="p-4 sm:p-5 border-b border-slate-200 dark:border-zinc-850 flex flex-col md:flex-row items-stretch md:items-center justify-between gap-3 sm:gap-4 bg-slate-50/60 dark:bg-[#0e0e12]/80">
                    <div>
                        <h3 class="text-xs sm:text-sm font-extrabold uppercase tracking-wider text-slate-900 dark:text-zinc-100 flex items-center gap-2">
                            Commercial Drivers
                        </h3>
                        <p class="text-[11px] text-slate-500 dark:text-zinc-400">Verified commercial drivers registered in Tagoneswa database</p>
                    </div>
                    <div class="flex items-center gap-2 w-full sm:w-auto">
                        <input type="text" id="drivers-search" placeholder="Search Driver Name, Phone..." oninput="filterDriversTable(true)" class="bg-white dark:bg-[#121216] border border-slate-300 dark:border-zinc-750 rounded-xl px-4 py-2 text-xs font-medium text-slate-800 dark:text-zinc-100 placeholder-slate-400 dark:placeholder-zinc-500 focus:outline-none focus:ring-2 focus:ring-blue-500 w-full sm:w-64 transition">
                        <button onclick="openAddDriverModal()" class="bg-purple-600 hover:bg-purple-700 text-white font-bold px-3.5 py-2 rounded-xl text-xs transition flex items-center gap-1.5 shadow-xs cursor-pointer whitespace-nowrap">
                            <span>+</span> Add Driver
                        </button>
                    </div>
                </div>

                <div class="overflow-x-auto">
                    <table class="w-full text-left text-xs min-w-[800px]">
                        <thead class="bg-slate-100/75 dark:bg-[#0e0e12] text-slate-500 dark:text-zinc-400 font-bold uppercase tracking-wider border-b border-slate-200 dark:border-zinc-800">
                            <tr>
                                <th class="px-4 sm:px-5 py-3.5 whitespace-nowrap">Staff ID</th>
                                <th class="px-4 sm:px-5 py-3.5 whitespace-nowrap">Full Name</th>
                                <th class="px-4 sm:px-5 py-3.5 whitespace-nowrap">WhatsApp Phone</th>
                                <th class="px-4 sm:px-5 py-3.5 whitespace-nowrap">Role Designation</th>
                                <th class="px-4 sm:px-5 py-3.5 whitespace-nowrap">Active Status</th>
                                <th class="px-4 sm:px-5 py-3.5 text-right whitespace-nowrap">Action</th>
                            </tr>
                        </thead>
                        <tbody id="fleet-drivers-table-body" class="divide-y divide-slate-200 dark:divide-zinc-850 text-slate-700 dark:text-zinc-200"></tbody>
                    </table>
                </div>

                <div class="p-3.5 sm:p-4 border-t border-slate-200 dark:border-zinc-850 flex flex-col sm:flex-row items-center justify-between gap-3 bg-slate-50/60 dark:bg-[#0c0c10]/80">
                    <div class="text-xs text-slate-500 dark:text-zinc-400 font-medium" id="drivers-pagination-info">Showing 0 entries</div>
                    <div class="flex items-center gap-1.5" id="drivers-pagination-controls"></div>
                </div>
            </div>

            <!-- SUBVIEW 6: SHORTFALL APPROVALS & DISPATCH AUDITS -->
            <div id="fleet-section-approvals" class="fleet-subview-panel space-y-4 transition-all duration-200" style="display: none;">
                <!-- Fleet Approval Top Stats Cards -->
                <div class="grid grid-cols-2 sm:grid-cols-3 {f'lg:grid-cols-5' if can_view_balances else 'lg:grid-cols-4'} gap-3 sm:gap-4">
                    <div class="bg-white dark:bg-[#0a0a0d] border border-slate-200/80 dark:border-zinc-800/80 rounded-2xl p-4 sm:p-5 shadow-xs hover:shadow-md transition-all duration-200">
                        <div class="text-[11px] sm:text-xs font-bold uppercase tracking-wider text-slate-400 dark:text-zinc-500">Total Trips Verified</div>
                        <div class="text-2xl sm:text-3xl font-extrabold text-blue-600 dark:text-blue-400 mt-1.5" id="fleet-stat-trips">0</div>
                        <div class="text-[11px] sm:text-xs text-blue-600 dark:text-blue-400 font-semibold mt-1" id="fleet-stat-sales-val">""" + (f"""$0.00 ERP Sales""" if can_view_balances else f"""Trips Logged""") + f"""</div>
                    </div>
                    <div class="bg-white dark:bg-[#0a0a0d] border border-slate-200/80 dark:border-zinc-800/80 rounded-2xl p-4 sm:p-5 shadow-xs hover:shadow-md transition-all duration-200">
                        <div class="text-[11px] sm:text-xs font-bold uppercase tracking-wider text-slate-400 dark:text-zinc-500">Approved for Dispatch</div>
                        <div class="text-2xl sm:text-3xl font-extrabold text-emerald-500 dark:text-emerald-400 mt-1.5" id="fleet-stat-approved">0</div>
                        <div class="text-[11px] sm:text-xs text-emerald-600 dark:text-emerald-400 font-semibold mt-1">Cleared Trips</div>
                    </div>
                    <div class="bg-white dark:bg-[#0a0a0d] border border-slate-200/80 dark:border-zinc-800/80 rounded-2xl p-4 sm:p-5 shadow-xs hover:shadow-md transition-all duration-200">
                        <div class="text-[11px] sm:text-xs font-bold uppercase tracking-wider text-slate-400 dark:text-zinc-500">Shortfalls Detected</div>
                        <div class="text-2xl sm:text-3xl font-extrabold text-amber-500 dark:text-amber-400 mt-1.5" id="fleet-stat-shortfalls">0</div>
                        <div class="text-[11px] sm:text-xs text-amber-600 dark:text-amber-400 font-semibold mt-1">Below City Threshold</div>
                    </div>
                    <div class="bg-white dark:bg-[#0a0a0d] border border-slate-200/80 dark:border-zinc-800/80 rounded-2xl p-4 sm:p-5 shadow-xs hover:shadow-md transition-all duration-200">
                        <div class="text-[11px] sm:text-xs font-bold uppercase tracking-wider text-slate-400 dark:text-zinc-500">Transport Charges</div>
                        <div class="text-2xl sm:text-3xl font-extrabold text-indigo-600 dark:text-indigo-400 mt-1.5" id="fleet-stat-transport">$0.00</div>
                        <div class="text-[11px] sm:text-xs text-indigo-600 dark:text-indigo-400 font-semibold mt-1">Total Fee Assessed</div>
                    </div>
                    {f"""
                    <div class="bg-white dark:bg-[#0a0a0d] border border-slate-200/80 dark:border-zinc-800/80 rounded-2xl p-4 sm:p-5 shadow-xs hover:shadow-md transition-all duration-200 col-span-2 sm:col-span-1">
                        <div class="text-[11px] sm:text-xs font-bold uppercase tracking-wider text-slate-400 dark:text-zinc-500">Salesperson Debt</div>
                        <div class="text-2xl sm:text-3xl font-extrabold text-rose-500 dark:text-rose-400 mt-1.5" id="fleet-stat-backlog">$0.00</div>
                        <div class="text-[11px] sm:text-xs text-rose-600 dark:text-rose-400 font-semibold mt-1">Pending Shortfall Ledger</div>
                    </div>
                    """ if can_view_balances else ""}
                </div>

                <div class="bg-white dark:bg-[#0a0a0d] border border-slate-200/80 dark:border-zinc-800/80 rounded-2xl shadow-xs overflow-hidden">
                    <div class="p-4 sm:p-5 border-b border-slate-200 dark:border-zinc-850 flex flex-col md:flex-row items-stretch md:items-center justify-between gap-3 sm:gap-4 bg-slate-50/60 dark:bg-[#0e0e12]/80">
                    <div class="flex flex-col sm:flex-row flex-wrap items-stretch sm:items-center gap-2 sm:gap-3 w-full md:w-auto">
                        <input type="text" id="fleet-search" placeholder="Search Trip ID, Salesperson, City..." oninput="filterFleetApprovalsTable(true)" class="bg-white dark:bg-[#121216] border border-slate-300 dark:border-zinc-750 rounded-xl px-4 py-2.5 sm:py-2 text-xs font-medium text-slate-800 dark:text-zinc-100 placeholder-slate-400 dark:placeholder-zinc-500 focus:outline-none focus:ring-2 focus:ring-blue-500 w-full sm:w-64 transition">
                        
                        <!-- City Filter -->
                        <select id="fleet-city-filter" onchange="filterFleetApprovalsTable(true)" class="bg-white dark:bg-[#121216] border border-slate-300 dark:border-zinc-750 rounded-xl px-3 py-2.5 sm:py-2 text-xs font-medium text-slate-700 dark:text-zinc-200 focus:outline-none focus:ring-2 focus:ring-blue-500 w-full sm:w-auto transition">
                            <option value="ALL">All Destination Cities</option>
                        </select>

                        <!-- Status Filter -->
                        <select id="fleet-status-filter" onchange="filterFleetApprovalsTable(true)" class="bg-white dark:bg-[#121216] border border-slate-300 dark:border-zinc-750 rounded-xl px-3 py-2.5 sm:py-2 text-xs font-medium text-slate-700 dark:text-zinc-200 focus:outline-none focus:ring-2 focus:ring-blue-500 w-full sm:w-auto transition">
                            <option value="ALL">All Statuses</option>
                            <option value="APPROVED">Approved for Dispatch</option>
                            <option value="SHORTFALL_RECORDED">Shortfall Pending Resolution</option>
                            <option value="DISPATCHED">Dispatched</option>
                        </select>
                    </div>

                    <div class="flex items-center justify-between sm:justify-end gap-2">
                        <span id="fleet-count-badge" class="bg-blue-50 dark:bg-blue-500/10 text-blue-700 dark:text-blue-300 border border-blue-200 dark:border-blue-500/30 text-xs font-bold px-3 py-1.5 rounded-full">
                            Showing 0 trips
                        </span>
                    </div>
                </div>

                <!-- Table -->
                <div class="overflow-x-auto">
                    <table class="w-full text-left text-xs min-w-[850px]">
                        <thead class="bg-slate-100/75 dark:bg-[#0e0e12] text-slate-500 dark:text-zinc-400 font-bold uppercase tracking-wider border-b border-slate-200 dark:border-zinc-800">
                            <tr>
                                <th class="px-4 sm:px-5 py-3.5 whitespace-nowrap">Trip ID</th>
                                <th class="px-4 sm:px-5 py-3.5 whitespace-nowrap">Salesperson</th>
                                <th class="px-4 sm:px-5 py-3.5 whitespace-nowrap">Destination & Route</th>
                                {f"""
                                <th class="px-4 sm:px-5 py-3.5 whitespace-nowrap">ERP Valuation</th>
                                <th class="px-4 sm:px-5 py-3.5 whitespace-nowrap">Shortfall / Transport</th>
                                <th class="px-4 sm:px-5 py-3.5 whitespace-nowrap">Settlement (Customer vs Debt)</th>
                                """ if can_view_balances else f"""
                                <th class="px-4 sm:px-5 py-3.5 whitespace-nowrap">Valuation Status</th>
                                <th class="px-4 sm:px-5 py-3.5 whitespace-nowrap">Shortfall Status</th>
                                <th class="px-4 sm:px-5 py-3.5 whitespace-nowrap">Accounting Status</th>
                                """}
                                <th class="px-4 sm:px-5 py-3.5 whitespace-nowrap">Audit Check</th>
                                <th class="px-4 sm:px-5 py-3.5 whitespace-nowrap">Status</th>
                                <th class="px-4 sm:px-5 py-3.5 whitespace-nowrap">Date</th>
                            </tr>
                        </thead>
                        <tbody id="fleet-approvals-table-body" class="divide-y divide-slate-200 dark:divide-zinc-850 text-slate-700 dark:text-zinc-200"></tbody>
                    </table>
                </div>

                <!-- Approvals Pagination Footer -->
                <div class="p-3.5 sm:p-4 border-t border-slate-200 dark:border-zinc-850 flex flex-col sm:flex-row items-center justify-between gap-3 bg-slate-50/60 dark:bg-[#0c0c10]/80">
                    <div class="text-xs text-slate-500 dark:text-zinc-400 font-medium" id="fleet-pagination-info">
                        Showing 0 entries
                    </div>
                    <div class="flex items-center gap-1.5" id="fleet-pagination-controls"></div>
                </div>
            </div>
        </div>

            <!-- SUBVIEW 7: FINANCIAL AUDIT & RECOVERY LEDGER -->
            {f"""
            <div id="fleet-section-ledger" class="fleet-subview-panel bg-white dark:bg-[#0a0a0d] border border-slate-200/80 dark:border-zinc-800/80 rounded-2xl shadow-xs overflow-hidden transition-all duration-200">
                <div class="p-4 sm:p-5 border-b border-slate-200 dark:border-zinc-850 bg-slate-50/75 dark:bg-[#0e0e12]/80">
                    <div class="flex flex-col md:flex-row md:items-center justify-between gap-4">
                        <div>
                            <div class="inline-flex items-center gap-1.5 bg-indigo-50 dark:bg-indigo-500/10 text-indigo-700 dark:text-indigo-300 border border-indigo-200 dark:border-indigo-500/30 px-2.5 py-0.5 rounded-full text-[10px] font-bold uppercase tracking-wider mb-1">
                                Anti-Cheating & Parity Guard
                            </div>
                            <h3 class="text-xs sm:text-sm font-extrabold uppercase tracking-wider text-slate-900 dark:text-zinc-100">
                                Financial Audit Log & Recovery Ledger
                            </h3>
                            <p class="text-[11px] text-slate-500 dark:text-zinc-400">Verifies system actions, rate edits, customer charges, debt records, and accounts clearances</p>
                        </div>

                        <!-- Date & Mode Filters -->
                        <div class="flex flex-wrap items-center gap-2 self-start md:self-auto">
                            <!-- Mode Selector -->
                            <div class="flex items-center gap-1 bg-white dark:bg-[#121216] p-1 rounded-xl border border-slate-300 dark:border-zinc-750">
                                <button onclick="setAuditMode('TRAIL')" id="audit-mode-btn-TRAIL" class="audit-mode-btn px-2.5 py-1 rounded-lg text-xs font-bold bg-blue-600 text-white transition cursor-pointer">System Audit Trail</button>
                                <button onclick="setAuditMode('SHORTFALL')" id="audit-mode-btn-SHORTFALL" class="audit-mode-btn px-2.5 py-1 rounded-lg text-xs font-bold text-slate-600 dark:text-zinc-300 hover:text-slate-900 dark:hover:text-white transition cursor-pointer">Debt Ledger Entries</button>
                            </div>

                            <!-- Date Filters -->
                            <div class="flex items-center gap-1 bg-white dark:bg-[#121216] p-1 rounded-xl border border-slate-300 dark:border-zinc-750">
                                <button onclick="setAuditTimeframe('ALL')" id="timeframe-btn-ALL" class="audit-tf-btn px-3 py-1 rounded-lg text-xs font-bold bg-blue-600 text-white transition cursor-pointer">All Dates</button>
                                <button onclick="setAuditTimeframe('TODAY')" id="timeframe-btn-TODAY" class="audit-tf-btn px-3 py-1 rounded-lg text-xs font-bold text-slate-600 dark:text-zinc-300 hover:text-slate-900 dark:hover:text-white transition cursor-pointer">Today</button>
                                <button onclick="setAuditTimeframe('YESTERDAY')" id="timeframe-btn-YESTERDAY" class="audit-tf-btn px-3 py-1 rounded-lg text-xs font-bold text-slate-600 dark:text-zinc-300 hover:text-slate-900 dark:hover:text-white transition cursor-pointer">Yesterday</button>
                                <button onclick="setAuditTimeframe('WEEK')" id="timeframe-btn-WEEK" class="audit-tf-btn px-3 py-1 rounded-lg text-xs font-bold text-slate-600 dark:text-zinc-300 hover:text-slate-900 dark:hover:text-white transition cursor-pointer">Last 7 Days</button>
                            </div>
                        </div>
                    </div>

                    <!-- Daily Audit Metrics Bar -->
                    <div class="grid grid-cols-2 sm:grid-cols-4 gap-3 mt-4 pt-4 border-t border-slate-200/80 dark:border-zinc-800/80">
                        <div class="bg-white dark:bg-[#121216] border border-slate-200 dark:border-zinc-800 rounded-xl p-3 shadow-xs">
                            <div class="text-[10px] font-bold text-slate-400 dark:text-zinc-500 uppercase">Customer Paid</div>
                            <div class="text-base sm:text-lg font-extrabold text-emerald-600 dark:text-emerald-400 font-mono mt-0.5" id="audit-stat-customer-paid">$0.00</div>
                            <div class="text-[10px] text-slate-500 dark:text-zinc-400">Collected at dispatch</div>
                        </div>
                        <div class="bg-white dark:bg-[#121216] border border-slate-200 dark:border-zinc-800 rounded-xl p-3 shadow-xs">
                            <div class="text-[10px] font-bold text-slate-400 dark:text-zinc-500 uppercase">Deferred to Ledger</div>
                            <div class="text-base sm:text-lg font-extrabold text-amber-600 dark:text-amber-400 font-mono mt-0.5" id="audit-stat-deferred">$0.00</div>
                            <div class="text-[10px] text-slate-500 dark:text-zinc-400">Added to sales debt</div>
                        </div>
                        <div class="bg-white dark:bg-[#121216] border border-slate-200 dark:border-zinc-800 rounded-xl p-3 shadow-xs">
                            <div class="text-[10px] font-bold text-slate-400 dark:text-zinc-500 uppercase">Surplus Recovered</div>
                            <div class="text-base sm:text-lg font-extrabold text-purple-600 dark:text-purple-400 font-mono mt-0.5" id="audit-stat-recovered">$0.00</div>
                            <div class="text-[10px] text-slate-500 dark:text-zinc-400">Cleared from debt</div>
                        </div>
                        <div class="bg-white dark:bg-[#121216] border border-slate-200 dark:border-zinc-800 rounded-xl p-3 shadow-xs">
                            <div class="text-[10px] font-bold text-slate-400 dark:text-zinc-500 uppercase">Audit Alert Flags</div>
                            <div class="text-base sm:text-lg font-extrabold text-slate-800 dark:text-zinc-100 font-mono mt-0.5" id="audit-stat-flags">0</div>
                            <div class="text-[10px] text-slate-500 dark:text-zinc-400" id="audit-stat-flags-note">100% Math Match</div>
                        </div>
                    </div>
                </div>

                <!-- Ledger Audit Table -->
                <div class="overflow-x-auto">
                    <table class="w-full text-left text-xs min-w-[760px]">
                        <thead id="fleet-ledger-table-head" class="bg-slate-100/75 dark:bg-[#0e0e12] text-slate-500 dark:text-zinc-400 font-bold uppercase tracking-wider border-b border-slate-200 dark:border-zinc-800">
                            <tr>
                                <th class="px-4 sm:px-5 py-3 whitespace-nowrap">Timestamp</th>
                                <th class="px-4 sm:px-5 py-3 whitespace-nowrap">Actor</th>
                                <th class="px-4 sm:px-5 py-3 whitespace-nowrap">Event / Action</th>
                                <th class="px-4 sm:px-5 py-3 whitespace-nowrap">Module / Ref</th>
                                <th class="px-4 sm:px-5 py-3 whitespace-nowrap">Details & Remarks</th>
                            </tr>
                        </thead>
                        <tbody id="fleet-ledger-table-body" class="divide-y divide-slate-200 dark:divide-zinc-850 text-slate-700 dark:text-zinc-200"></tbody>
                    </table>
                </div>

                <!-- Ledger Pagination Footer -->
                <div class="p-3.5 sm:p-4 border-t border-slate-200 dark:border-zinc-850 flex flex-col sm:flex-row items-center justify-between gap-3 bg-slate-50/60 dark:bg-[#0c0c10]/80">
                    <div class="text-xs text-slate-500 dark:text-zinc-400 font-medium" id="ledger-pagination-info">
                        Showing 0 entries
                    </div>
                    <div class="flex items-center gap-1.5" id="ledger-pagination-controls"></div>
                </div>
            </div>
            """ if can_view_balances else ""}

            <!-- SUBVIEW 8: DATA ANALYTICS & FLEET METRICS -->
            {f"""
            <div id="fleet-section-analytics" class="fleet-subview-panel space-y-6 transition-all duration-200" style="display: none;">
                <!-- Analytics Header Card -->
                <div class="bg-white dark:bg-[#0a0a0d] border border-slate-200/80 dark:border-zinc-800/80 rounded-2xl p-5 sm:p-6 shadow-xs flex flex-col sm:flex-row sm:items-center justify-between gap-4">
                    <div>
                        <div class="flex items-center gap-2">
                            <span class="text-[10px] font-black uppercase tracking-widest text-blue-600 dark:text-blue-400 bg-blue-50 dark:bg-blue-500/10 px-2.5 py-0.5 rounded-full border border-blue-200 dark:border-blue-500/30">Intelligence</span>
                            <span class="text-xs font-bold text-slate-400 dark:text-zinc-500 font-mono">Real-time DB Telemetry</span>
                        </div>
                        <h2 class="text-base sm:text-lg font-extrabold text-slate-900 dark:text-zinc-100 tracking-tight mt-1.5">Fleet Operations & Financial Analytics</h2>
                        <p class="text-xs text-slate-500 dark:text-zinc-400 mt-0.5">Aggregated metrics calculated live across trip records, WhatsApp expenses, debt recovery, and workshop operations.</p>
                    </div>
                    <div class="flex items-center gap-2 shrink-0">
                        <button onclick="manualRefresh()" class="bg-slate-100 dark:bg-zinc-800 text-slate-700 dark:text-zinc-200 hover:bg-slate-200 dark:hover:bg-zinc-700 font-bold px-3.5 py-2 rounded-xl text-xs transition flex items-center gap-1.5 cursor-pointer">
                            <span id="analyticsRefreshIcon">🔄</span> Refresh Analytics
                        </button>
                    </div>
                </div>

                <!-- 4 Top Executive Analytics Summary KPI Cards -->
                <div class="grid grid-cols-2 lg:grid-cols-4 gap-3 sm:gap-4">
                    <div class="bg-white dark:bg-[#0a0a0d] border border-slate-200/80 dark:border-zinc-800/80 rounded-2xl p-4 sm:p-5 shadow-xs">
                        <div class="text-[11px] font-bold uppercase tracking-wider text-slate-400 dark:text-zinc-500">Trip Volume & Completion</div>
                        <div class="text-2xl sm:text-3xl font-extrabold text-slate-900 dark:text-zinc-100 mt-1 font-mono" id="an-stat-trips-total">0</div>
                        <div class="text-[11px] text-emerald-600 dark:text-emerald-400 font-medium mt-1" id="an-stat-trips-completed">0 completed</div>
                    </div>
                    <div class="bg-white dark:bg-[#0a0a0d] border border-slate-200/80 dark:border-zinc-800/80 rounded-2xl p-4 sm:p-5 shadow-xs">
                        <div class="text-[11px] font-bold uppercase tracking-wider text-slate-400 dark:text-zinc-500">Avg Revenue / Trip</div>
                        <div class="text-2xl sm:text-3xl font-extrabold text-blue-600 dark:text-blue-400 mt-1 font-mono" id="an-stat-avg-revenue">$0.00</div>
                        <div class="text-[11px] text-slate-500 dark:text-zinc-400 font-medium mt-1" id="an-stat-avg-opex">Avg Opex: $0.00</div>
                    </div>
                    <div class="bg-white dark:bg-[#0a0a0d] border border-slate-200/80 dark:border-zinc-800/80 rounded-2xl p-4 sm:p-5 shadow-xs">
                        <div class="text-[11px] font-bold uppercase tracking-wider text-slate-400 dark:text-zinc-500">Fleet Utilization</div>
                        <div class="text-2xl sm:text-3xl font-extrabold text-indigo-600 dark:text-indigo-400 mt-1 font-mono" id="an-stat-utilization">0%</div>
                        <div class="text-[11px] text-slate-500 dark:text-zinc-400 font-medium mt-1" id="an-stat-ws-impact">0 trucks in workshop</div>
                    </div>
                    <div class="bg-white dark:bg-[#0a0a0d] border border-slate-200/80 dark:border-zinc-800/80 rounded-2xl p-4 sm:p-5 shadow-xs">
                        <div class="text-[11px] font-bold uppercase tracking-wider text-slate-400 dark:text-zinc-500">Shortfall Recovery Rate</div>
                        <div class="text-2xl sm:text-3xl font-extrabold text-emerald-600 dark:text-emerald-400 mt-1 font-mono" id="an-stat-recovery-rate">0%</div>
                        <div class="text-[11px] text-slate-500 dark:text-zinc-400 font-medium mt-1" id="an-stat-recovery-sub">$0 recovered of $0</div>
                    </div>
                </div>

                <!-- Dedicated Line Chart: Total Sales Revenue Trends (Day-Wise, Month-Wise, Company-Wise) -->
                <div class="bg-white dark:bg-[#0a0a0d] border border-slate-200/80 dark:border-zinc-800/80 rounded-2xl p-5 sm:p-6 shadow-xs">
                    <div class="flex flex-col md:flex-row md:items-center justify-between gap-4 mb-4">
                        <div>
                            <div class="flex items-center gap-2">
                                <span class="text-[10px] font-black uppercase tracking-widest text-emerald-600 dark:text-emerald-400 bg-emerald-50 dark:bg-emerald-500/10 px-2.5 py-0.5 rounded-full border border-emerald-200 dark:border-emerald-500/30">Commercial Trajectory</span>
                                <span class="text-xs font-bold text-slate-400 dark:text-zinc-500 font-mono">Live ERP Sales</span>
                            </div>
                            <h3 class="text-sm sm:text-base font-extrabold uppercase tracking-tight text-slate-900 dark:text-zinc-100 mt-1">
                                Total Sales Revenue Trends
                            </h3>
                            <p class="text-xs text-slate-500 dark:text-zinc-400 mt-0.5">
                                Real-time sales trajectory tracked day-wise, month-wise, and company-wise across divisions.
                            </p>
                        </div>
                        
                        <!-- Line Chart View Selector: Day-Wise, Month-Wise, Company-Wise -->
                        <div class="flex flex-wrap items-center gap-1.5 bg-slate-100 dark:bg-[#121216] p-1 rounded-xl border border-slate-200 dark:border-zinc-800 self-start md:self-auto">
                            <button onclick="switchSalesChartMode('DAY')" id="btn-sales-chart-DAY" class="sales-chart-mode-btn px-3 py-1.5 rounded-lg text-xs font-bold bg-blue-600 text-white shadow-xs transition cursor-pointer">
                                📅 Day-Wise
                            </button>
                            <button onclick="switchSalesChartMode('MONTH')" id="btn-sales-chart-MONTH" class="sales-chart-mode-btn px-3 py-1.5 rounded-lg text-xs font-bold text-slate-600 dark:text-zinc-300 hover:text-slate-900 dark:hover:text-white transition cursor-pointer">
                                📆 Month-Wise
                            </button>
                            <button onclick="switchSalesChartMode('COMPANY')" id="btn-sales-chart-COMPANY" class="sales-chart-mode-btn px-3 py-1.5 rounded-lg text-xs font-bold text-slate-600 dark:text-zinc-300 hover:text-slate-900 dark:hover:text-white transition cursor-pointer">
                                🏢 Company-Wise (3 Lines)
                            </button>
                        </div>
                    </div>

                    <!-- Revenue KPI Mini-Bar for Chart -->
                    <div class="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-4 pt-3 border-t border-slate-100 dark:border-zinc-850">
                        <div class="p-2.5 rounded-xl bg-slate-50 dark:bg-[#121216] border border-slate-200/80 dark:border-zinc-800">
                            <div class="text-[10px] font-bold text-slate-400 dark:text-zinc-500 uppercase">Selected Total</div>
                            <div class="text-base sm:text-lg font-extrabold text-emerald-600 dark:text-emerald-400 font-mono mt-0.5" id="sales-chart-total-val">$0.00</div>
                        </div>
                        <div class="p-2.5 rounded-xl bg-slate-50 dark:bg-[#121216] border border-slate-200/80 dark:border-zinc-800">
                            <div class="text-[10px] font-bold text-slate-400 dark:text-zinc-500 uppercase">LG Plast Sales</div>
                            <div class="text-base sm:text-lg font-extrabold text-blue-600 dark:text-blue-400 font-mono mt-0.5" id="sales-chart-lg-val">$0.00</div>
                        </div>
                        <div class="p-2.5 rounded-xl bg-slate-50 dark:bg-[#121216] border border-slate-200/80 dark:border-zinc-800">
                            <div class="text-[10px] font-bold text-slate-400 dark:text-zinc-500 uppercase">Tagoneswa Sales</div>
                            <div class="text-base sm:text-lg font-extrabold text-amber-600 dark:text-amber-400 font-mono mt-0.5" id="sales-chart-tg-val">$0.00</div>
                        </div>
                        <div class="p-2.5 rounded-xl bg-slate-50 dark:bg-[#121216] border border-slate-200/80 dark:border-zinc-800">
                            <div class="text-[10px] font-bold text-slate-400 dark:text-zinc-500 uppercase">Kreckle Foods Sales</div>
                            <div class="text-base sm:text-lg font-extrabold text-emerald-600 dark:text-emerald-400 font-mono mt-0.5" id="sales-chart-kreckle-val">$0.00</div>
                        </div>
                    </div>

                    <!-- Line Chart Canvas Container -->
                    <div class="h-72 sm:h-80 relative w-full">
                        <canvas id="an-sales-trend-line-chart"></canvas>
                    </div>
                </div>

                <!-- Deep Analytics Grid: Operational Breakdown & Corridors -->
                <div class="grid grid-cols-1 lg:grid-cols-2 gap-4 sm:gap-6">
                    <!-- Panel 1: Trip Pipeline Operational Distribution -->
                    <div class="bg-white dark:bg-[#0a0a0d] border border-slate-200/80 dark:border-zinc-800/80 rounded-2xl p-5 shadow-xs flex flex-col justify-between">
                        <div>
                            <div class="flex items-center justify-between mb-2">
                                <h3 class="text-xs sm:text-sm font-extrabold uppercase tracking-wider text-slate-900 dark:text-zinc-100">Pipeline Stage Volume</h3>
                                <span class="text-[10px] font-mono px-2 py-0.5 rounded-full bg-blue-50 dark:bg-blue-900/30 text-blue-600 dark:text-blue-400 font-bold border border-blue-200 dark:border-blue-800">Lifecycle</span>
                            </div>
                            <p class="text-[11px] text-slate-500 dark:text-zinc-400 mb-3">Trips distributed across operational stages & delivery pipeline</p>
                            <div class="h-56 relative w-full mb-3">
                                <canvas id="an-pipeline-chart"></canvas>
                            </div>
                        </div>
                        <div class="space-y-2.5 pt-3 border-t border-slate-100 dark:border-zinc-850" id="an-pipeline-bars">
                            <!-- Populated dynamically -->
                        </div>
                    </div>

                    <!-- Panel 2: Operational Cost Composition -->
                    <div class="bg-white dark:bg-[#0a0a0d] border border-slate-200/80 dark:border-zinc-800/80 rounded-2xl p-5 shadow-xs flex flex-col justify-between">
                        <div>
                            <div class="flex items-center justify-between mb-2">
                                <h3 class="text-xs sm:text-sm font-extrabold uppercase tracking-wider text-slate-900 dark:text-zinc-100">Operational Cost Composition</h3>
                                <span class="text-[10px] font-mono px-2 py-0.5 rounded-full bg-emerald-50 dark:bg-emerald-900/30 text-emerald-600 dark:text-emerald-400 font-bold border border-emerald-200 dark:border-emerald-800">OPEX Split</span>
                            </div>
                            <p class="text-[11px] text-slate-500 dark:text-zinc-400 mb-3">Live breakdown of fuel, crew allowances, meals, accommodation & tolls</p>
                            <div class="h-56 relative w-full mb-3">
                                <canvas id="an-cost-donut-chart"></canvas>
                            </div>
                        </div>
                        <div class="space-y-2.5 pt-3 border-t border-slate-100 dark:border-zinc-850" id="an-cost-bars">
                            <!-- Populated dynamically -->
                        </div>
                    </div>
                </div>

                <!-- Panel 3: Top Corridors & Financial Ledger Health -->
                <div class="grid grid-cols-1 lg:grid-cols-2 gap-4 sm:gap-6">
                    <!-- Top Destinations & Routes -->
                    <div class="bg-white dark:bg-[#0a0a0d] border border-slate-200/80 dark:border-zinc-800/80 rounded-2xl p-5 shadow-xs flex flex-col justify-between">
                        <div>
                            <div class="flex items-center justify-between mb-2">
                                <h3 class="text-xs sm:text-sm font-extrabold uppercase tracking-wider text-slate-900 dark:text-zinc-100">Top Corridors & City Traffic</h3>
                                <span class="text-[10px] font-mono px-2 py-0.5 rounded-full bg-indigo-50 dark:bg-indigo-900/30 text-indigo-600 dark:text-indigo-400 font-bold border border-indigo-200 dark:border-indigo-800">Regional</span>
                            </div>
                            <p class="text-[11px] text-slate-500 dark:text-zinc-400 mb-3">Trip volume and frequency across key Zimbabwe commercial routes</p>
                            <div class="h-56 relative w-full mb-3">
                                <canvas id="an-corridors-bar-chart"></canvas>
                            </div>
                        </div>
                        <div class="divide-y divide-slate-100 dark:divide-zinc-850 pt-2 border-t border-slate-100 dark:border-zinc-850" id="an-top-cities-list">
                            <!-- Populated dynamically -->
                        </div>
                    </div>

                    <!-- Debt Ledger & Clearance Liquidity Health -->
                    <div class="bg-white dark:bg-[#0a0a0d] border border-slate-200/80 dark:border-zinc-800/80 rounded-2xl p-5 shadow-xs flex flex-col justify-between">
                        <div>
                            <div class="flex items-center justify-between mb-2">
                                <h3 class="text-xs sm:text-sm font-extrabold uppercase tracking-wider text-slate-900 dark:text-zinc-100">Financial Ledger & Recovery</h3>
                                <span class="text-[10px] font-mono px-2 py-0.5 rounded-full bg-purple-50 dark:bg-purple-900/30 text-purple-600 dark:text-purple-400 font-bold border border-purple-200 dark:border-purple-800">Audit</span>
                            </div>
                            <p class="text-[11px] text-slate-500 dark:text-zinc-400 mb-3">Settlement clearance comparison and deficit liquidity</p>
                            <div class="h-56 relative w-full mb-3">
                                <canvas id="an-financial-overview-chart"></canvas>
                            </div>
                            <div class="space-y-3">
                                <div class="bg-slate-50 dark:bg-[#121216] border border-slate-200 dark:border-zinc-800 rounded-xl p-3 flex items-center justify-between">
                                    <div>
                                        <div class="text-[10px] uppercase font-bold text-slate-400">Total Cleared Payments</div>
                                        <div class="text-base font-extrabold font-mono text-emerald-600 dark:text-emerald-400 mt-0.5" id="an-cleared-total">$0.00</div>
                                    </div>
                                    <span class="text-xs text-slate-400 dark:text-zinc-500 font-mono">Bank Verified</span>
                                </div>
                                <div class="bg-slate-50 dark:bg-[#121216] border border-slate-200 dark:border-zinc-800 rounded-xl p-3 flex items-center justify-between">
                                    <div>
                                        <div class="text-[10px] uppercase font-bold text-slate-400">Outstanding Debt Backlog</div>
                                        <div class="text-base font-extrabold font-mono text-rose-600 dark:text-rose-400 mt-0.5" id="an-outstanding-total">$0.00</div>
                                    </div>
                                    <span class="text-xs text-slate-400 dark:text-zinc-500 font-mono">Pending Offset</span>
                                </div>
                            </div>
                        </div>
                        <div class="mt-3 pt-3 border-t border-slate-100 dark:border-zinc-850 flex items-center justify-between">
                            <span class="text-[11px] text-slate-500 dark:text-zinc-400">Accounts Reconciliation Status</span>
                            <span class="text-xs font-bold text-blue-600 dark:text-blue-400">Synchronized</span>
                        </div>
                    </div>
                </div>
            </div>
            """ if is_master_admin else ""}
        </div>
    </main>

    <!-- Modal 1: Dynamic Fuel Price & 45 City Delivery Corridors Configuration -->
    <div id="cityMinimumsModal" class="modal-overlay fixed inset-0 z-50 hidden flex items-center justify-center p-3 sm:p-4 bg-slate-900/70 backdrop-blur-xs overscroll-contain">
        <div class="modal-card bg-white dark:bg-[#0c0c10] border border-slate-200 dark:border-zinc-800 rounded-3xl w-full max-w-4xl max-h-[90vh] flex flex-col shadow-2xl overflow-hidden animate-in fade-in zoom-in-95 duration-150 overscroll-contain">
            <!-- Modal Header -->
            <div class="p-4 sm:p-5 border-b border-slate-200 dark:border-zinc-800 flex items-center justify-between bg-slate-50 dark:bg-[#121216] shrink-0">
                <div class="flex items-center gap-2.5">
                    <div class="w-9 h-9 rounded-xl bg-blue-100 dark:bg-blue-500/20 text-blue-600 dark:text-blue-400 flex items-center justify-center text-lg font-bold">
                        ⚙️
                    </div>
                    <div>
                        <h3 class="text-sm sm:text-base font-extrabold text-slate-900 dark:text-zinc-100">Delivery Corridors & City Minimums</h3>
                        <p class="text-[11px] text-slate-500 dark:text-zinc-400 font-medium">Dynamic fuel rates, 4% expense formula & 45 Zimbabwe route minimums</p>
                    </div>
                </div>
                <button onclick="closeCityConfigModal()" class="p-2 rounded-xl text-slate-400 hover:text-slate-600 dark:hover:text-zinc-200 hover:bg-slate-200/60 dark:hover:bg-zinc-800 transition cursor-pointer">
                    ✕
                </button>
            </div>

            <!-- Modal Content (Scrollable) -->
            <div class="p-4 sm:p-6 overflow-y-auto space-y-6 flex-1 overscroll-contain">
                <!-- Top Fuel Price Controller Card -->
                <div class="bg-gradient-to-r from-blue-50 to-indigo-50 dark:from-blue-950/20 dark:to-indigo-950/20 border border-blue-200/80 dark:border-blue-900/40 rounded-2xl p-4 sm:p-5">
                    <div class="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
                        <div>
                            <span class="text-[10px] font-extrabold uppercase tracking-wider text-blue-700 dark:text-blue-400 bg-blue-100 dark:bg-blue-500/20 px-2.5 py-0.5 rounded-full border border-blue-200 dark:border-blue-500/30">
                                ⛽ Global Fuel Price Formula Engine
                            </span>
                            <h4 class="text-sm font-extrabold text-slate-900 dark:text-zinc-100 mt-1">Active Diesel / Fuel Rate ($/L)</h4>
                            <p class="text-[11px] text-slate-600 dark:text-zinc-400 mt-0.5">Changing the fuel price automatically updates trip operating costs across all corridors</p>
                        </div>
                        <div class="flex items-center gap-2">
                            <div class="relative">
                                <span class="absolute left-3 top-2.5 text-xs text-slate-400 font-bold">$</span>
                                <input type="number" id="modal-fuel-price" step="0.01" min="0.5" max="10.0" value="1.55" class="pl-6 pr-3 py-2 w-28 bg-white dark:bg-[#121216] border border-slate-300 dark:border-zinc-700 rounded-xl text-xs font-mono font-bold text-slate-900 dark:text-zinc-100 focus:ring-2 focus:ring-blue-500 focus:outline-none">
                            </div>
                            <button onclick="saveFuelPrice()" id="modal-save-fuel-btn" class="bg-blue-600 hover:bg-blue-700 text-white px-4 py-2 rounded-xl text-xs font-bold transition shadow-xs cursor-pointer flex items-center gap-1.5 whitespace-nowrap">
                                <span>💾</span> Save & Recalculate 45 Cities
                            </button>
                        </div>
                    </div>
                    <div id="fuel-update-feedback" class="mt-2 text-xs font-semibold hidden"></div>
                </div>

                <!-- Operational Allowance Rates & Vehicle Surcharges Card -->
                <div class="bg-gradient-to-r from-emerald-50 to-teal-50 dark:from-emerald-950/20 dark:to-teal-950/20 border border-emerald-200/80 dark:border-emerald-900/40 rounded-2xl p-4 sm:p-5">
                    <div class="flex flex-col sm:flex-row sm:items-center justify-between gap-3 mb-3">
                        <div>
                            <span class="text-[10px] font-extrabold uppercase tracking-wider text-emerald-700 dark:text-emerald-400 bg-emerald-100 dark:bg-emerald-500/20 px-2.5 py-0.5 rounded-full border border-emerald-200 dark:border-emerald-500/30">
                                💵 Operational Allowance Rates & Surcharges
                            </span>
                            <h4 class="text-sm font-extrabold text-slate-900 dark:text-zinc-100 mt-1">Crew Allowances & Vehicle Costing Matrix</h4>
                            <p class="text-[11px] text-slate-600 dark:text-zinc-400 mt-0.5">Edit live meal rates, nightly accommodation, expense allocations, and van surcharges</p>
                        </div>
                        <button onclick="saveOperationalParams()" id="modal-save-ops-btn" class="bg-emerald-600 hover:bg-emerald-700 text-white px-4 py-2 rounded-xl text-xs font-bold transition shadow-xs cursor-pointer flex items-center gap-1.5 whitespace-nowrap self-start sm:self-auto">
                            <span>💾</span> Save Operational Rates
                        </button>
                    </div>
                    <div class="grid grid-cols-2 sm:grid-cols-4 gap-3">
                        <div>
                            <label class="block text-[10px] font-bold text-slate-600 dark:text-zinc-400 uppercase mb-1">Meal Rate ($/meal)</label>
                            <div class="relative">
                                <span class="absolute left-2.5 top-2 text-xs text-slate-400 font-bold">$</span>
                                <input type="number" id="modal-meal-rate" step="0.50" min="0" value="2.00" class="pl-6 pr-2 py-1.5 w-full bg-white dark:bg-[#121216] border border-slate-300 dark:border-zinc-700 rounded-xl text-xs font-mono font-bold text-slate-900 dark:text-zinc-100 focus:ring-2 focus:ring-emerald-500 focus:outline-none">
                            </div>
                        </div>
                        <div>
                            <label class="block text-[10px] font-bold text-slate-600 dark:text-zinc-400 uppercase mb-1">Accommodation ($/night)</label>
                            <div class="relative">
                                <span class="absolute left-2.5 top-2 text-xs text-slate-400 font-bold">$</span>
                                <input type="number" id="modal-accom-rate" step="1.00" min="0" value="15.00" class="pl-6 pr-2 py-1.5 w-full bg-white dark:bg-[#121216] border border-slate-300 dark:border-zinc-700 rounded-xl text-xs font-mono font-bold text-slate-900 dark:text-zinc-100 focus:ring-2 focus:ring-emerald-500 focus:outline-none">
                            </div>
                        </div>
                        <div>
                            <label class="block text-[10px] font-bold text-slate-600 dark:text-zinc-400 uppercase mb-1">Expense Budget (%)</label>
                            <div class="relative">
                                <input type="number" id="modal-budget-pct" step="0.5" min="1" max="50" value="4.0" class="pl-3 pr-6 py-1.5 w-full bg-white dark:bg-[#121216] border border-slate-300 dark:border-zinc-700 rounded-xl text-xs font-mono font-bold text-slate-900 dark:text-zinc-100 focus:ring-2 focus:ring-emerald-500 focus:outline-none">
                                <span class="absolute right-2.5 top-2 text-xs text-slate-400 font-bold">%</span>
                            </div>
                        </div>
                        <div>
                            <label class="block text-[10px] font-bold text-slate-600 dark:text-zinc-400 uppercase mb-1">Van Surcharge ($)</label>
                            <div class="relative">
                                <span class="absolute left-2.5 top-2 text-xs text-slate-400 font-bold">$</span>
                                <input type="number" id="modal-van-surcharge" step="50" min="0" value="1500.00" class="pl-6 pr-2 py-1.5 w-full bg-white dark:bg-[#121216] border border-slate-300 dark:border-zinc-700 rounded-xl text-xs font-mono font-bold text-slate-900 dark:text-zinc-100 focus:ring-2 focus:ring-emerald-500 focus:outline-none">
                            </div>
                        </div>
                    </div>
                    <div id="ops-update-feedback" class="mt-2 text-xs font-semibold hidden"></div>
                </div>

                <!-- 45 Cities Search & Table -->
                <div class="border border-slate-200 dark:border-zinc-800 rounded-2xl overflow-hidden">
                    <div class="p-3.5 bg-slate-50/75 dark:bg-[#121216] border-b border-slate-200 dark:border-zinc-800 flex flex-col sm:flex-row items-stretch sm:items-center justify-between gap-3">
                        <div class="flex items-center gap-2">
                            <input type="text" id="modal-city-search" placeholder="Search city or route..." oninput="filterCityRulesModal()" class="bg-white dark:bg-[#181820] border border-slate-300 dark:border-zinc-700 rounded-xl px-3.5 py-1.5 text-xs font-medium text-slate-800 dark:text-zinc-100 placeholder-slate-400 dark:placeholder-zinc-500 focus:outline-none focus:ring-2 focus:ring-blue-500 w-full sm:w-60 transition">
                            <span id="modal-city-count" class="text-xs text-slate-500 dark:text-zinc-400 font-bold whitespace-nowrap">45 Cities</span>
                        </div>
                        <span class="text-[11px] text-slate-400 dark:text-zinc-500 italic">Values saved dynamically into database without hardcoding</span>
                    </div>

                    <div class="max-h-[46vh] overflow-y-auto overscroll-contain">
                        <table class="w-full text-left text-xs">
                            <thead class="bg-slate-100 dark:bg-[#14141a] text-slate-500 dark:text-zinc-400 font-bold uppercase tracking-wider border-b border-slate-200 dark:border-zinc-800 sticky top-0 z-10">
                                <tr>
                                    <th class="px-4 py-2.5">City & Destination</th>
                                    <th class="px-4 py-2.5">Route / Corridor</th>
                                    <th class="px-4 py-2.5">Distance (KM)</th>
                                    <th class="px-4 py-2.5">Min Sales ($)</th>
                                    <th class="px-4 py-2.5">Van Min ($)</th>
                                    <th class="px-4 py-2.5 text-right">Action</th>
                                </tr>
                            </thead>
                            <tbody id="modal-city-rules-tbody" class="divide-y divide-slate-200 dark:divide-zinc-800 text-slate-700 dark:text-zinc-200">
                                <!-- Populated dynamically -->
                            </tbody>
                        </table>
                    </div>
                </div>
            </div>

            <!-- Modal Footer -->
            <div class="p-3.5 sm:p-4 border-t border-slate-200 dark:border-zinc-800 bg-slate-50 dark:bg-[#121216] flex items-center justify-between shrink-0">
                <span class="text-[11px] text-slate-500 dark:text-zinc-400">All trip pricing calculations update instantly in WhatsApp</span>
                <button onclick="closeCityConfigModal()" class="px-4 py-2 rounded-xl text-xs font-bold bg-slate-200 dark:bg-zinc-800 text-slate-700 dark:text-zinc-200 hover:bg-slate-300 dark:hover:bg-zinc-700 transition cursor-pointer">
                    Done / Close
                </button>
            </div>
        </div>
    </div>

    <!-- Modal 2: Financial Debt Settlement & Payment Clearance -->
    <div id="clearPaymentModal" class="modal-overlay fixed inset-0 z-50 hidden flex items-center justify-center p-3 sm:p-4 bg-slate-900/70 backdrop-blur-xs overscroll-contain">
        <div class="modal-card bg-white dark:bg-[#0c0c10] border border-slate-200 dark:border-zinc-800 rounded-3xl w-full max-w-lg max-h-[90vh] flex flex-col shadow-2xl overflow-hidden animate-in fade-in zoom-in-95 duration-150 overscroll-contain">
            <!-- Modal Header -->
            <div class="p-4 sm:p-5 border-b border-slate-200 dark:border-zinc-800 flex items-center justify-between bg-slate-50 dark:bg-[#121216] shrink-0">
                <div class="flex items-center gap-2.5">
                    <div class="w-9 h-9 rounded-xl bg-emerald-100 dark:bg-emerald-500/20 text-emerald-600 dark:text-emerald-400 flex items-center justify-center text-lg font-bold">
                        💳
                    </div>
                    <div>
                        <h3 class="text-sm sm:text-base font-extrabold text-slate-900 dark:text-zinc-100">Clear Sales Rep Debt</h3>
                        <p class="text-[11px] text-slate-500 dark:text-zinc-400 font-medium">Verify payment settlement and offset shortfall ledger</p>
                    </div>
                </div>
                <button onclick="closeClearPaymentModal()" class="p-2 rounded-xl text-slate-400 hover:text-slate-600 dark:hover:text-zinc-200 hover:bg-slate-200/60 dark:hover:bg-zinc-800 transition cursor-pointer">
                    ✕
                </button>
            </div>

            <!-- Modal Content Form -->
            <div class="p-4 sm:p-6 space-y-4 overflow-y-auto flex-1 overscroll-contain">
                <!-- Salesperson Selector -->
                <div>
                    <label class="block text-xs font-bold text-slate-700 dark:text-zinc-300 mb-1">Select Sales Representative</label>
                    <select id="modal-pay-salesperson" onchange="onSelectPaySalesperson()" class="w-full bg-slate-50 dark:bg-[#121216] border border-slate-300 dark:border-zinc-700 rounded-xl px-3.5 py-2.5 text-xs font-medium text-slate-800 dark:text-zinc-100 focus:outline-none focus:ring-2 focus:ring-emerald-500">
                        <option value="">-- Choose Sales Rep --</option>
                    </select>
                </div>

                <!-- Current Balance Display -->
                <div class="bg-slate-50 dark:bg-[#14141a] border border-slate-200 dark:border-zinc-800 rounded-xl p-3.5 flex items-center justify-between">
                    <div>
                        <div class="text-[10px] uppercase font-bold text-slate-400 dark:text-zinc-500">Current Outstanding Debt</div>
                        <div class="text-xl font-extrabold font-mono text-rose-600 dark:text-rose-400 mt-0.5" id="modal-pay-current-balance">$0.00</div>
                    </div>
                    <button type="button" onclick="fillFullClearance()" class="text-[11px] font-bold text-emerald-600 dark:text-emerald-400 hover:underline bg-emerald-50 dark:bg-emerald-500/10 px-2.5 py-1 rounded-lg border border-emerald-200 dark:border-emerald-500/30 cursor-pointer">
                        Clear 100% Full Balance
                    </button>
                </div>

                <!-- Cleared Amount -->
                <div>
                    <label class="block text-xs font-bold text-slate-700 dark:text-zinc-300 mb-1">Amount to Clear (USD $)</label>
                    <div class="relative">
                        <span class="absolute left-3.5 top-2.5 text-xs text-slate-400 font-bold">$</span>
                        <input type="number" id="modal-pay-amount" step="0.01" min="0.01" placeholder="0.00" class="pl-8 pr-3.5 py-2.5 w-full bg-slate-50 dark:bg-[#121216] border border-slate-300 dark:border-zinc-700 rounded-xl text-xs font-mono font-bold text-slate-900 dark:text-zinc-100 focus:ring-2 focus:ring-emerald-500 focus:outline-none">
                    </div>
                </div>

                <!-- Payment Method -->
                <div>
                    <label class="block text-xs font-bold text-slate-700 dark:text-zinc-300 mb-1">Payment Method</label>
                    <select id="modal-pay-method" class="w-full bg-slate-50 dark:bg-[#121216] border border-slate-300 dark:border-zinc-700 rounded-xl px-3.5 py-2.5 text-xs font-medium text-slate-800 dark:text-zinc-100 focus:outline-none focus:ring-2 focus:ring-emerald-500">
                        <option value="BANK_TRANSFER">Bank Transfer (Stanbic / CABS / Ecocash USD)</option>
                        <option value="CASH_USD">Cash USD (Receipted at Cash Office)</option>
                        <option value="DIRECT_DEPOSIT">Direct Bank Deposit</option>
                        <option value="CREDIT_NOTE">ERP Credit Note / Commission Offset</option>
                        <option value="CHEQUE">Corporate Cheque</option>
                    </select>
                </div>

                <!-- Reference Number -->
                <div>
                    <label class="block text-xs font-bold text-slate-700 dark:text-zinc-300 mb-1">Reference / Transaction / Receipt #</label>
                    <input type="text" id="modal-pay-ref" placeholder="e.g. TXN-89214, REC-0045" class="w-full bg-slate-50 dark:bg-[#121216] border border-slate-300 dark:border-zinc-700 rounded-xl px-3.5 py-2.5 text-xs font-mono text-slate-800 dark:text-zinc-100 focus:outline-none focus:ring-2 focus:ring-emerald-500">
                </div>

                <!-- Remarks / Notes -->
                <div>
                    <label class="block text-xs font-bold text-slate-700 dark:text-zinc-300 mb-1">Verification Remarks / Notes</label>
                    <textarea id="modal-pay-remarks" rows="2" placeholder="e.g. Verified by Accounts. Bank confirmation received." class="w-full bg-slate-50 dark:bg-[#121216] border border-slate-300 dark:border-zinc-700 rounded-xl px-3.5 py-2 text-xs text-slate-800 dark:text-zinc-100 focus:outline-none focus:ring-2 focus:ring-emerald-500"></textarea>
                </div>

                <div id="modal-pay-feedback" class="text-xs font-bold hidden"></div>
            </div>

            <!-- Modal Footer -->
            <div class="p-4 border-t border-slate-200 dark:border-zinc-800 bg-slate-50 dark:bg-[#121216] flex items-center justify-end gap-2.5 shrink-0">
                <button type="button" onclick="closeClearPaymentModal()" class="px-4 py-2.5 rounded-xl text-xs font-bold bg-slate-200 dark:bg-zinc-800 text-slate-700 dark:text-zinc-200 hover:bg-slate-300 dark:hover:bg-zinc-700 transition cursor-pointer">
                    Cancel
                </button>
                <button type="button" onclick="submitClearPayment()" id="modal-submit-pay-btn" class="bg-emerald-600 hover:bg-emerald-700 text-white font-extrabold px-5 py-2.5 rounded-xl text-xs transition shadow-md cursor-pointer flex items-center gap-1.5">
                    <span>✅</span> Confirm Debt Clearance
                </button>
            </div>
        </div>
    </div>

    <!-- Modal 3: System Audit Logs & Financial Trail -->
    <div id="auditLogsModal" class="modal-overlay fixed inset-0 z-50 hidden flex items-center justify-center p-3 sm:p-4 bg-slate-900/70 backdrop-blur-xs overscroll-contain">
        <div class="modal-card bg-white dark:bg-[#0c0c10] border border-slate-200 dark:border-zinc-800 rounded-3xl w-full max-w-4xl max-h-[90vh] flex flex-col shadow-2xl overflow-hidden animate-in fade-in zoom-in-95 duration-150 overscroll-contain">
            <!-- Modal Header -->
            <div class="p-4 sm:p-5 border-b border-slate-200 dark:border-zinc-800 flex items-center justify-between bg-slate-50 dark:bg-[#121216] shrink-0">
                <div class="flex items-center gap-2.5">
                    <div class="w-9 h-9 rounded-xl bg-purple-100 dark:bg-purple-500/20 text-purple-600 dark:text-purple-400 flex items-center justify-center text-lg font-bold">
                        🛡️
                    </div>
                    <div>
                        <h3 class="text-sm sm:text-base font-extrabold text-slate-900 dark:text-zinc-100">Enterprise System Audit Trail</h3>
                        <p class="text-[11px] text-slate-500 dark:text-zinc-400 font-medium">Immutable audit trail of configuration changes and debt settlements</p>
                    </div>
                </div>
                <div class="flex items-center gap-2">
                    <button onclick="loadAuditLogs()" class="p-2 rounded-xl text-slate-600 dark:text-zinc-300 hover:bg-slate-200 dark:hover:bg-zinc-800 text-xs font-bold transition flex items-center gap-1 cursor-pointer">
                        <span>🔄</span> Refresh
                    </button>
                    <button onclick="closeAuditLogsModal()" class="p-2 rounded-xl text-slate-400 hover:text-slate-600 dark:hover:text-zinc-200 hover:bg-slate-200/60 dark:hover:bg-zinc-800 transition cursor-pointer">
                        ✕
                    </button>
                </div>
            </div>

            <!-- Modal Content Table -->
            <div class="overflow-y-auto flex-1 p-4 overscroll-contain">
                <table class="w-full text-left text-xs min-w-[700px]">
                    <thead class="bg-slate-100 dark:bg-[#14141a] text-slate-500 dark:text-zinc-400 font-bold uppercase tracking-wider border-b border-slate-200 dark:border-zinc-800 sticky top-0 z-10">
                        <tr>
                            <th class="px-4 py-2.5 whitespace-nowrap">Timestamp</th>
                            <th class="px-4 py-2.5 whitespace-nowrap">User & Role</th>
                            <th class="px-4 py-2.5 whitespace-nowrap">Action</th>
                            <th class="px-4 py-2.5 whitespace-nowrap">Module</th>
                            <th class="px-4 py-2.5 whitespace-nowrap">Entity / Target</th>
                            <th class="px-4 py-2.5 whitespace-nowrap">Changes & Remarks</th>
                        </tr>
                    </thead>
                    <tbody id="modal-audit-tbody" class="divide-y divide-slate-200 dark:divide-zinc-800 text-slate-700 dark:text-zinc-200">
                        <!-- Populated dynamically -->
                    </tbody>
                </table>
            </div>

            <!-- Modal Footer -->
            <div class="p-3.5 border-t border-slate-200 dark:border-zinc-800 bg-slate-50 dark:bg-[#121216] flex items-center justify-between shrink-0">
                <span class="text-[11px] text-slate-400 dark:text-zinc-500">Security & compliance logs cannot be purged or modified</span>
                <button onclick="closeAuditLogsModal()" class="px-4 py-2 rounded-xl text-xs font-bold bg-slate-200 dark:bg-zinc-800 text-slate-700 dark:text-zinc-200 hover:bg-slate-300 dark:hover:bg-zinc-700 transition cursor-pointer">
                    Close
                </button>
            </div>
        </div>
    </div>

    <!-- Modal 4: Commercial Truck Registry (Add / Edit) -->
    <div id="addTruckModal" class="modal-overlay fixed inset-0 z-50 hidden flex items-center justify-center p-3 sm:p-4 bg-slate-900/70 backdrop-blur-xs overscroll-contain">
        <div class="modal-card bg-white dark:bg-[#0c0c10] border border-slate-200 dark:border-zinc-800 rounded-3xl w-full max-w-lg max-h-[90vh] flex flex-col shadow-2xl overflow-hidden animate-in fade-in zoom-in-95 duration-150">
            <div class="p-4 sm:p-5 border-b border-slate-200 dark:border-zinc-800 flex items-center justify-between bg-slate-50 dark:bg-[#121216] shrink-0">
                <div class="flex items-center gap-2.5">
                    <div class="w-9 h-9 rounded-xl bg-blue-100 dark:bg-blue-500/20 text-blue-600 dark:text-blue-400 flex items-center justify-center text-lg font-bold">
                        🚚
                    </div>
                    <div>
                        <h3 class="text-sm sm:text-base font-extrabold text-slate-900 dark:text-zinc-100" id="truck-modal-title">Commercial Truck Registry</h3>
                        <p class="text-[11px] text-slate-500 dark:text-zinc-400 font-medium">Register or edit Tagoneswa commercial fleet vehicle</p>
                    </div>
                </div>
                <button onclick="closeAddTruckModal()" class="p-2 rounded-xl text-slate-400 hover:text-slate-600 dark:hover:text-zinc-200 hover:bg-slate-200/60 dark:hover:bg-zinc-800 transition cursor-pointer">
                    ✕
                </button>
            </div>
            <div class="p-5 space-y-4 overflow-y-auto flex-1 overscroll-contain">
                <input type="hidden" id="modal-truck-id" value="">
                <div class="grid grid-cols-2 gap-3">
                    <div>
                        <label class="block text-xs font-bold text-slate-700 dark:text-zinc-300 mb-1">Truck Number *</label>
                        <input type="text" id="modal-truck-number" placeholder="e.g. 1045" class="w-full bg-slate-50 dark:bg-[#121216] border border-slate-300 dark:border-zinc-700 rounded-xl px-3.5 py-2.5 text-xs font-mono font-bold text-slate-900 dark:text-zinc-100 focus:outline-none focus:ring-2 focus:ring-blue-500" required>
                    </div>
                    <div>
                        <label class="block text-xs font-bold text-slate-700 dark:text-zinc-300 mb-1">Plate Number *</label>
                        <input type="text" id="modal-truck-plate" placeholder="e.g. ABZ 1045" class="w-full bg-slate-50 dark:bg-[#121216] border border-slate-300 dark:border-zinc-700 rounded-xl px-3.5 py-2.5 text-xs font-mono font-bold uppercase text-slate-900 dark:text-zinc-100 focus:outline-none focus:ring-2 focus:ring-blue-500" required>
                    </div>
                </div>
                <div>
                    <label class="block text-xs font-bold text-slate-700 dark:text-zinc-300 mb-1">Make & Model</label>
                    <input type="text" id="modal-truck-make" placeholder="e.g. Volvo FH16 540 / Scania G460" class="w-full bg-slate-50 dark:bg-[#121216] border border-slate-300 dark:border-zinc-700 rounded-xl px-3.5 py-2.5 text-xs text-slate-900 dark:text-zinc-100 focus:outline-none focus:ring-2 focus:ring-blue-500">
                </div>
                <div class="grid grid-cols-2 gap-3">
                    <div>
                        <label class="block text-xs font-bold text-slate-700 dark:text-zinc-300 mb-1">Body Type</label>
                        <select id="modal-truck-body" class="w-full bg-slate-50 dark:bg-[#121216] border border-slate-300 dark:border-zinc-700 rounded-xl px-3.5 py-2.5 text-xs font-medium text-slate-800 dark:text-zinc-100 focus:outline-none focus:ring-2 focus:ring-blue-500">
                            <option value="Horse">Horse (Tractor Unit)</option>
                            <option value="Rigid">Rigid Truck</option>
                            <option value="Tipper">Tipper</option>
                            <option value="Tanker">Fuel / Water Tanker</option>
                            <option value="Van">Delivery Van</option>
                            <option value="Dropside">Dropside Trailer</option>
                        </select>
                    </div>
                    <div>
                        <label class="block text-xs font-bold text-slate-700 dark:text-zinc-300 mb-1">Home Depot</label>
                        <input type="text" id="modal-truck-depot" placeholder="e.g. Harare Central" value="Harare Central" class="w-full bg-slate-50 dark:bg-[#121216] border border-slate-300 dark:border-zinc-700 rounded-xl px-3.5 py-2.5 text-xs text-slate-900 dark:text-zinc-100 focus:outline-none focus:ring-2 focus:ring-blue-500">
                    </div>
                </div>
                <div class="flex items-center gap-2 pt-2">
                    <input type="checkbox" id="modal-truck-active" checked class="w-4 h-4 rounded text-blue-600 focus:ring-blue-500 border-slate-300">
                    <label for="modal-truck-active" class="text-xs font-bold text-slate-700 dark:text-zinc-300 cursor-pointer">Active in Commercial Fleet Operations</label>
                </div>
                <div id="modal-truck-feedback" class="text-xs font-bold hidden"></div>
            </div>
            <div class="p-4 border-t border-slate-200 dark:border-zinc-800 bg-slate-50 dark:bg-[#121216] flex items-center justify-end gap-2.5 shrink-0">
                <button type="button" onclick="closeAddTruckModal()" class="px-4 py-2.5 rounded-xl text-xs font-bold bg-slate-200 dark:bg-zinc-800 text-slate-700 dark:text-zinc-200 hover:bg-slate-300 dark:hover:bg-zinc-700 transition cursor-pointer">
                    Cancel
                </button>
                <button type="button" onclick="submitSaveTruck()" id="modal-submit-truck-btn" class="bg-blue-600 hover:bg-blue-700 text-white font-extrabold px-5 py-2.5 rounded-xl text-xs transition shadow-md cursor-pointer flex items-center gap-1.5">
                    <span>💾</span> Save Truck Details
                </button>
            </div>
        </div>
    </div>

    <!-- Modal 5: Commercial Driver Registry (Add / Edit) -->
    <div id="addDriverModal" class="modal-overlay fixed inset-0 z-50 hidden flex items-center justify-center p-3 sm:p-4 bg-slate-900/70 backdrop-blur-xs overscroll-contain">
        <div class="modal-card bg-white dark:bg-[#0c0c10] border border-slate-200 dark:border-zinc-800 rounded-3xl w-full max-w-lg max-h-[90vh] flex flex-col shadow-2xl overflow-hidden animate-in fade-in zoom-in-95 duration-150">
            <div class="p-4 sm:p-5 border-b border-slate-200 dark:border-zinc-800 flex items-center justify-between bg-slate-50 dark:bg-[#121216] shrink-0">
                <div class="flex items-center gap-2.5">
                    <div class="w-9 h-9 rounded-xl bg-purple-100 dark:bg-purple-500/20 text-purple-600 dark:text-purple-400 flex items-center justify-center text-lg font-bold">
                        👤
                    </div>
                    <div>
                        <h3 class="text-sm sm:text-base font-extrabold text-slate-900 dark:text-zinc-100" id="driver-modal-title">Commercial Driver Registry</h3>
                        <p class="text-[11px] text-slate-500 dark:text-zinc-400 font-medium">Register driver for WhatsApp trip dispatches & allowances</p>
                    </div>
                </div>
                <button onclick="closeAddDriverModal()" class="p-2 rounded-xl text-slate-400 hover:text-slate-600 dark:hover:text-zinc-200 hover:bg-slate-200/60 dark:hover:bg-zinc-800 transition cursor-pointer">
                    ✕
                </button>
            </div>
            <div class="p-5 space-y-4 overflow-y-auto flex-1 overscroll-contain">
                <input type="hidden" id="modal-driver-id" value="">
                <div>
                    <label class="block text-xs font-bold text-slate-700 dark:text-zinc-300 mb-1">Full Legal Name *</label>
                    <input type="text" id="modal-driver-name" placeholder="e.g. Munashe Milcah" class="w-full bg-slate-50 dark:bg-[#121216] border border-slate-300 dark:border-zinc-700 rounded-xl px-3.5 py-2.5 text-xs text-slate-900 dark:text-zinc-100 focus:outline-none focus:ring-2 focus:ring-purple-500" required>
                </div>
                <div>
                    <label class="block text-xs font-bold text-slate-700 dark:text-zinc-300 mb-1">WhatsApp Phone Number *</label>
                    <input type="text" id="modal-driver-phone" placeholder="e.g. 263772123456" class="w-full bg-slate-50 dark:bg-[#121216] border border-slate-300 dark:border-zinc-700 rounded-xl px-3.5 py-2.5 text-xs font-mono font-bold text-slate-900 dark:text-zinc-100 focus:outline-none focus:ring-2 focus:ring-purple-500" required>
                    <span class="text-[10px] text-slate-400 mt-1 block">Must match the driver's active WhatsApp line (e.g. 263...)</span>
                </div>
                <div>
                    <label class="block text-xs font-bold text-slate-700 dark:text-zinc-300 mb-1">Role Designation</label>
                    <select id="modal-driver-role" class="w-full bg-slate-50 dark:bg-[#121216] border border-slate-300 dark:border-zinc-700 rounded-xl px-3.5 py-2.5 text-xs font-medium text-slate-800 dark:text-zinc-100 focus:outline-none focus:ring-2 focus:ring-purple-500">
                        <option value="COMMERCIAL DRIVER">COMMERCIAL DRIVER (Long Distance)</option>
                        <option value="LOCAL DELIVERY DRIVER">LOCAL DELIVERY DRIVER (Harare)</option>
                        <option value="RELIEF DRIVER">RELIEF DRIVER</option>
                    </select>
                </div>
                <div class="flex items-center gap-2 pt-2">
                    <input type="checkbox" id="modal-driver-active" checked class="w-4 h-4 rounded text-purple-600 focus:ring-purple-500 border-slate-300">
                    <label for="modal-driver-active" class="text-xs font-bold text-slate-700 dark:text-zinc-300 cursor-pointer">Active Driver on Roster</label>
                </div>
                <div id="modal-driver-feedback" class="text-xs font-bold hidden"></div>
            </div>
            <div class="p-4 border-t border-slate-200 dark:border-zinc-800 bg-slate-50 dark:bg-[#121216] flex items-center justify-end gap-2.5 shrink-0">
                <button type="button" onclick="closeAddDriverModal()" class="px-4 py-2.5 rounded-xl text-xs font-bold bg-slate-200 dark:bg-zinc-800 text-slate-700 dark:text-zinc-200 hover:bg-slate-300 dark:hover:bg-zinc-700 transition cursor-pointer">
                    Cancel
                </button>
                <button type="button" onclick="submitSaveDriver()" id="modal-submit-driver-btn" class="bg-purple-600 hover:bg-purple-700 text-white font-extrabold px-5 py-2.5 rounded-xl text-xs transition shadow-md cursor-pointer flex items-center gap-1.5">
                    <span>💾</span> Save Driver
                </button>
            </div>
        </div>
    </div>

    <!-- Modal 6: Sales Representative Registry (Add / Edit) -->
    <div id="addSalesRepModal" class="modal-overlay fixed inset-0 z-50 hidden flex items-center justify-center p-3 sm:p-4 bg-slate-900/70 backdrop-blur-xs overscroll-contain">
        <div class="modal-card bg-white dark:bg-[#0c0c10] border border-slate-200 dark:border-zinc-800 rounded-3xl w-full max-w-lg max-h-[90vh] flex flex-col shadow-2xl overflow-hidden animate-in fade-in zoom-in-95 duration-150">
            <div class="p-4 sm:p-5 border-b border-slate-200 dark:border-zinc-800 flex items-center justify-between bg-slate-50 dark:bg-[#121216] shrink-0">
                <div class="flex items-center gap-2.5">
                    <div class="w-9 h-9 rounded-xl bg-indigo-100 dark:bg-indigo-500/20 text-indigo-600 dark:text-indigo-400 flex items-center justify-center text-lg font-bold">
                        💼
                    </div>
                    <div>
                        <h3 class="text-sm sm:text-base font-extrabold text-slate-900 dark:text-zinc-100" id="salesrep-modal-title">Sales Representative Registry</h3>
                        <p class="text-[11px] text-slate-500 dark:text-zinc-400 font-medium">Register sales reps for trip requests & shortfall tracking</p>
                    </div>
                </div>
                <button onclick="closeAddSalesRepModal()" class="p-2 rounded-xl text-slate-400 hover:text-slate-600 dark:hover:text-zinc-200 hover:bg-slate-200/60 dark:hover:bg-zinc-800 transition cursor-pointer">
                    ✕
                </button>
            </div>
            <div class="p-5 space-y-4 overflow-y-auto flex-1 overscroll-contain">
                <input type="hidden" id="modal-salesrep-id" value="">
                <div>
                    <label class="block text-xs font-bold text-slate-700 dark:text-zinc-300 mb-1">Full Legal Name *</label>
                    <input type="text" id="modal-salesrep-name" placeholder="e.g. Panashe Mazai" class="w-full bg-slate-50 dark:bg-[#121216] border border-slate-300 dark:border-zinc-700 rounded-xl px-3.5 py-2.5 text-xs text-slate-900 dark:text-zinc-100 focus:outline-none focus:ring-2 focus:ring-indigo-500" required>
                </div>
                <div>
                    <label class="block text-xs font-bold text-slate-700 dark:text-zinc-300 mb-1">WhatsApp Phone Number *</label>
                    <input type="text" id="modal-salesrep-phone" placeholder="e.g. 263772111222" class="w-full bg-slate-50 dark:bg-[#121216] border border-slate-300 dark:border-zinc-700 rounded-xl px-3.5 py-2.5 text-xs font-mono font-bold text-slate-900 dark:text-zinc-100 focus:outline-none focus:ring-2 focus:ring-indigo-500" required>
                    <span class="text-[10px] text-slate-400 mt-1 block">WhatsApp number used to submit trip requests</span>
                </div>
                <div>
                    <label class="block text-xs font-bold text-slate-700 dark:text-zinc-300 mb-1">Company Division *</label>
                    <select id="modal-salesrep-company" class="w-full bg-slate-50 dark:bg-[#121216] border border-slate-300 dark:border-zinc-700 rounded-xl px-3.5 py-2.5 text-xs text-slate-900 dark:text-zinc-100 focus:outline-none focus:ring-2 focus:ring-indigo-500" required>
                        <option value="LG Plast">LG Plast</option>
                        <option value="Tagoneswa Hardware">Tagoneswa Hardware</option>
                        <option value="Kreckle Foods">Kreckle Foods</option>
                    </select>
                    <span class="text-[10px] text-slate-400 mt-1 block">Partitions trips, shortfall ledgers and reporting by company</span>
                </div>
                <div>
                    <label class="block text-xs font-bold text-slate-700 dark:text-zinc-300 mb-1">Role Designation *</label>
                    <select id="modal-salesrep-role" class="w-full bg-slate-50 dark:bg-[#121216] border border-slate-300 dark:border-zinc-700 rounded-xl px-3.5 py-2.5 text-xs text-slate-900 dark:text-zinc-100 focus:outline-none focus:ring-2 focus:ring-indigo-500" required>
                        <option value="SALES_REP">Commercial Sales Representative</option>
                        <option value="SALES_ADMIN">Sales Administrator / Dispatch Lead</option>
                    </select>
                </div>
                <div>
                    <label class="block text-xs font-bold text-slate-700 dark:text-zinc-300 mb-1">Email Address (Optional)</label>
                    <input type="email" id="modal-salesrep-email" placeholder="e.g. sales@tagoneswa.co.zw" class="w-full bg-slate-50 dark:bg-[#121216] border border-slate-300 dark:border-zinc-700 rounded-xl px-3.5 py-2.5 text-xs text-slate-900 dark:text-zinc-100 focus:outline-none focus:ring-2 focus:ring-indigo-500">
                </div>
                <div class="flex items-center gap-2 pt-2">
                    <input type="checkbox" id="modal-salesrep-active" checked class="w-4 h-4 rounded text-indigo-600 focus:ring-indigo-500 border-slate-300">
                    <label for="modal-salesrep-active" class="text-xs font-bold text-slate-700 dark:text-zinc-300 cursor-pointer">Active Commercial Roster</label>
                </div>
                <div id="modal-salesrep-feedback" class="text-xs font-bold hidden"></div>
            </div>
            <div class="p-4 border-t border-slate-200 dark:border-zinc-800 bg-slate-50 dark:bg-[#121216] flex items-center justify-end gap-2.5 shrink-0">
                <button type="button" onclick="closeAddSalesRepModal()" class="px-4 py-2.5 rounded-xl text-xs font-bold bg-slate-200 dark:bg-zinc-800 text-slate-700 dark:text-zinc-200 hover:bg-slate-300 dark:hover:bg-zinc-700 transition cursor-pointer">
                    Cancel
                </button>
                <button type="button" onclick="submitSaveSalesRep()" id="modal-submit-salesrep-btn" class="bg-indigo-600 hover:bg-indigo-700 text-white font-extrabold px-5 py-2.5 rounded-xl text-xs transition shadow-md cursor-pointer flex items-center gap-1.5">
                    <span>💾</span> Save Sales Rep
                </button>
            </div>
        </div>
    </div>

    <!-- Modal 7: User Management & Granular Permissions (MASTER_ADMIN only) -->
    <div id="userManagementModal" class="modal-overlay fixed inset-0 z-50 hidden flex items-center justify-center p-3 sm:p-4 bg-slate-900/70 backdrop-blur-xs overscroll-contain">
        <div class="modal-card bg-white dark:bg-[#0c0c10] border border-slate-200 dark:border-zinc-800 rounded-3xl w-full max-w-5xl max-h-[90vh] flex flex-col shadow-2xl overflow-hidden animate-in fade-in zoom-in-95 duration-150">
            <!-- Modal Header -->
            <div class="p-4 sm:p-5 border-b border-slate-200 dark:border-zinc-800 flex items-center justify-between bg-slate-50 dark:bg-[#121216] shrink-0">
                <div class="flex items-center gap-2.5">
                    <div class="w-9 h-9 rounded-xl bg-indigo-100 dark:bg-indigo-500/20 text-indigo-600 dark:text-indigo-400 flex items-center justify-center text-lg font-bold">
                        👥
                    </div>
                    <div>
                        <h3 class="text-sm sm:text-base font-extrabold text-slate-900 dark:text-zinc-100">User Management & Granular Permissions</h3>
                        <p class="text-[11px] text-slate-500 dark:text-zinc-400 font-medium">Manage user accounts, roles, and delegated permission overrides</p>
                    </div>
                </div>
                <div class="flex items-center gap-2">
                    <button onclick="loadUsersList()" class="p-2 rounded-xl text-slate-600 dark:text-zinc-300 hover:bg-slate-200 dark:hover:bg-zinc-800 text-xs font-bold transition flex items-center gap-1 cursor-pointer">
                        <span>🔄</span> Refresh
                    </button>
                    <button onclick="closeUserManagementModal()" class="p-2 rounded-xl text-slate-400 hover:text-slate-600 dark:hover:text-zinc-200 hover:bg-slate-200/60 dark:hover:bg-zinc-800 transition cursor-pointer">
                        ✕
                    </button>
                </div>
            </div>

            <!-- Modal Content (Scrollable) -->
            <div class="p-4 sm:p-6 overflow-y-auto space-y-6 flex-1 overscroll-contain">
                <!-- User Accounts Overview Table -->
                <div class="border border-slate-200 dark:border-zinc-800 rounded-2xl overflow-hidden">
                    <div class="p-3.5 bg-slate-50/75 dark:bg-[#121216] border-b border-slate-200 dark:border-zinc-800 flex items-center justify-between">
                        <span class="text-xs font-bold text-slate-800 dark:text-zinc-200">Registered Accounts & Roles</span>
                        <span id="user-mgmt-count" class="text-[11px] text-slate-500 font-medium">Loading...</span>
                    </div>
                    <div class="max-h-[30vh] overflow-y-auto">
                        <table class="w-full text-left text-xs">
                            <thead class="bg-slate-100 dark:bg-[#14141a] text-slate-500 dark:text-zinc-400 font-bold uppercase tracking-wider border-b border-slate-200 dark:border-zinc-800 sticky top-0 z-10">
                                <tr>
                                    <th class="px-4 py-2.5">User</th>
                                    <th class="px-4 py-2.5">Role</th>
                                    <th class="px-4 py-2.5">Status</th>
                                    <th class="px-4 py-2.5">Custom Overrides</th>
                                    <th class="px-4 py-2.5 text-right">Actions</th>
                                </tr>
                            </thead>
                            <tbody id="user-mgmt-tbody" class="divide-y divide-slate-200 dark:divide-zinc-800 text-slate-700 dark:text-zinc-200">
                                <tr><td colspan="5" class="p-4 text-center text-slate-400">Loading accounts...</td></tr>
                            </tbody>
                        </table>
                    </div>
                </div>

                <!-- Selected User Permission Configuration Panel -->
                <div id="user-mgmt-detail-panel" class="hidden bg-slate-50/60 dark:bg-[#121216]/60 border border-slate-200 dark:border-zinc-800 rounded-2xl p-4 sm:p-5 space-y-5">
                    <div class="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-slate-200 dark:border-zinc-800 pb-3">
                        <div>
                            <span class="text-[10px] font-bold uppercase tracking-wider text-indigo-600 dark:text-indigo-400 bg-indigo-50 dark:bg-indigo-500/10 px-2.5 py-0.5 rounded-full border border-indigo-200 dark:border-indigo-500/30">
                                Account Configuration
                            </span>
                            <h4 class="text-base font-extrabold text-slate-900 dark:text-zinc-100 mt-1" id="selected-user-header">--</h4>
                        </div>
                        <!-- Role change and active toggle form -->
                        <div class="flex flex-wrap items-center gap-2">
                            <select id="selected-user-role" class="bg-white dark:bg-[#181820] border border-slate-300 dark:border-zinc-700 rounded-xl px-3 py-1.5 text-xs font-bold text-slate-800 dark:text-zinc-100">
                                <option value="MASTER_ADMIN">MASTER_ADMIN</option>
                                <option value="FLEET_ADMIN">FLEET_ADMIN</option>
                                <option value="SALES_ADMIN">SALES_ADMIN</option>
                                <option value="ACCOUNTS_USER">ACCOUNTS_USER</option>
                                <option value="LOGISTICS_MANAGER">LOGISTICS_MANAGER</option>
                                <option value="LOGISTICS_ADMIN">LOGISTICS_ADMIN</option>
                                <option value="IT_ADMIN">IT_ADMIN</option>
                                <option value="PROJECTS_ADMIN">PROJECTS_ADMIN</option>
                                <option value="EXECUTIVE_OBSERVER">EXECUTIVE_OBSERVER</option>
                            </select>
                            <label class="flex items-center gap-1.5 text-xs font-bold text-slate-700 dark:text-zinc-300">
                                <input type="checkbox" id="selected-user-active" class="w-4 h-4 rounded text-blue-600">
                                Active
                            </label>
                            <button onclick="saveSelectedUserRole()" class="bg-indigo-600 hover:bg-indigo-700 text-white font-bold px-3 py-1.5 rounded-xl text-xs transition cursor-pointer shadow-xs">
                                Update Role
                            </button>
                        </div>
                    </div>

                    <!-- Granular Permission Overrides Matrix -->
                    <div>
                        <div class="flex items-center justify-between mb-2">
                            <h5 class="text-xs font-bold uppercase tracking-wider text-slate-700 dark:text-zinc-300">
                                Granular Permission Overrides (Delegation Engine)
                            </h5>
                            <span class="text-[11px] text-slate-500 italic">Overrides take precedence over role defaults</span>
                        </div>
                        <div class="grid grid-cols-1 md:grid-cols-2 gap-2.5" id="user-perms-matrix">
                            <!-- Populated dynamically -->
                        </div>
                    </div>
                </div>

                <div id="user-mgmt-feedback" class="text-xs font-bold hidden"></div>
            </div>

            <!-- Modal Footer -->
            <div class="p-3.5 sm:p-4 border-t border-slate-200 dark:border-zinc-800 bg-slate-50 dark:bg-[#121216] flex items-center justify-between shrink-0">
                <span class="text-[11px] text-slate-500 dark:text-zinc-400">All permission changes are recorded in System Audit Logs</span>
                <button onclick="closeUserManagementModal()" class="px-4 py-2 rounded-xl text-xs font-bold bg-slate-200 dark:bg-zinc-800 text-slate-700 dark:text-zinc-200 hover:bg-slate-300 dark:hover:bg-zinc-700 transition cursor-pointer">
                    Close
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
    <script src="/static/js/dashboard.js?v=2.4.2"></script>
</body>
</html>"""
    return HTMLResponse(content=html_content)
