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
    get_sales_rep_pending_balance
)
from app.workshop.models import (
    WorkshopTicket, WorkshopTruck, WorkshopStaff, WorkshopPartsRequest
)
from app.auth import (
    authenticate_user, create_session_token, get_current_user_from_request,
    COOKIE_NAME, SESSION_MAX_AGE, USERS_DB
)
from app.services.config_service import (
    get_fuel_price, get_meal_rate, get_accommodation_rate, get_expense_budget_pct,
    get_all_cached_city_rules, update_system_setting, update_city_rule, recalculate_all_city_minimums
)

logger = logging.getLogger("dashboard")
router = APIRouter()

IT_SUPPORT_ADMIN_PHONES = {"263718627526", "263788843579", "263780100503"}

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
            <div class="w-12 h-12 bg-gradient-to-tr from-blue-700 via-blue-600 to-indigo-500 rounded-2xl flex items-center justify-center text-white text-2xl font-bold shadow-md shadow-blue-500/20 mx-auto mb-3.5 border border-blue-400/30">
                🚚
            </div>
            <div class="inline-flex items-center gap-2 bg-blue-50 dark:bg-blue-500/10 border border-blue-200 dark:border-blue-500/30 text-blue-700 dark:text-blue-300 px-3.5 py-1 rounded-full text-xs font-bold mb-3 sm:mb-4">
                🔒 Enterprise Security
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
    default_tab = "fleet" if user["role"] in ("FLEET_ADMIN", "SALES_ADMIN") else ("logistics" if user["role"] == "LOGISTICS_ADMIN" else ("projects" if user["role"] == "PROJECTS_ADMIN" else "it"))
    
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
async def api_update_fuel(request: Request, db: AsyncSession = Depends(get_db)):
    """Updates active fuel price and optionally auto-recalculates all 45 city minimums."""
    user = get_current_user_from_request(request)
    if not user or user.get("role") not in ("MASTER_ADMIN", "FLEET_ADMIN", "LOGISTICS_MANAGER", "ACCOUNTS_USER"):
        raise HTTPException(status_code=403, detail="Permission denied. Admin or Manager role required.")
    
    body = await request.json()
    new_price = float(body.get("fuel_price", 1.55))
    recalc = bool(body.get("recalculate_cities", False))
    uname = user.get("name", "Admin")

    if recalc:
        res = await recalculate_all_city_minimums(db, new_price, updated_by=uname)
        return res
    else:
        await update_system_setting(db, "fuel_price_usd", new_price, changed_by=uname, reason=f"Fuel price updated to ${new_price:.2f}/L")
        return {"status": "success", "fuel_price": new_price}


@router.post("/api/v2/config/update-city-minimum")
async def api_update_city_min(request: Request, db: AsyncSession = Depends(get_db)):
    """Updates minimum sales and van minimum for a specific city."""
    user = get_current_user_from_request(request)
    if not user or user.get("role") not in ("MASTER_ADMIN", "FLEET_ADMIN", "LOGISTICS_MANAGER", "ACCOUNTS_USER"):
        raise HTTPException(status_code=403, detail="Permission denied.")
    
    body = await request.json()
    city_key = body.get("city_key", "").strip().lower()
    min_sales = float(body.get("min_sales", 0.0))
    van_min = float(body.get("van_min", 0.0))
    uname = user.get("name", "Admin")

    ok = await update_city_rule(db, city_key, min_sales, van_min, updated_by=uname)
    return {"status": "success" if ok else "not_found", "city_key": city_key}


@router.post("/api/v2/finance/clear-sales-rep-payment")
async def api_clear_sales_rep_payment(request: Request, db: AsyncSession = Depends(get_db)):
    """Clears pending sales rep shortfall debt with audit trail and ledger offsetting."""
    user = get_current_user_from_request(request)
    if not user or user.get("role") not in ("MASTER_ADMIN", "ACCOUNTS_USER", "FLEET_ADMIN", "SALES_ADMIN"):
        raise HTTPException(status_code=403, detail="Permission denied. Accounts or Admin role required.")
    
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
    remaining_balance = round(current_balance - cleared_amount, 2)
    uname = user.get("name", "Accounts")

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

    # 3. Add Audit Log
    audit = AuditLog(
        username=uname,
        user_role=user.get("role", "ACCOUNTS_USER"),
        action="CLEAR_SALES_REP_DEBT",
        module="FINANCE",
        entity_id=phone,
        previous_value={"balance": current_balance},
        new_value={"cleared": cleared_amount, "remaining": remaining_balance, "method": payment_method, "ref": reference},
        remarks=remarks,
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
    if not user:
        raise HTTPException(status_code=401, detail="Unauthorized")
    
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
            "entity_id": l.entity_id or "--",
            "previous_value": l.previous_value,
            "new_value": l.new_value,
            "remarks": l.remarks or "",
            "created_at": l.created_at.strftime("%Y-%m-%d %H:%M:%S") if l.created_at else ""
        })
    return {"status": "success", "logs": records}

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

        logistics_payload = {
            "stats": ws_stats,
            "records": ws_records,
            "fleet_count": len(ws_trucks)
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
                    "total_shortfalls": 0.0,
                    "total_recovered": 0.0,
                    "net_balance": 0.0,
                    "entries_count": 0,
                    "trips": {fa.trip_id} if fa.trip_id else set(),
                    "recent_date": fa.created_at.strftime("%Y-%m-%d %H:%M") if fa.created_at else ""
                }
            elif p and fa.trip_id:
                salesperson_map[p]["trips"].add(fa.trip_id)

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
                "total_shortfalls": round(s["total_shortfalls"], 2),
                "total_recovered": round(s["total_recovered"], 2),
                "net_balance": net,
                "trips_count": len(s["trips"]),
                "entries_count": s["entries_count"],
                "recent_date": s["recent_date"],
                "risk_level": risk
            })
        salespersons_list.sort(key=lambda x: x["net_balance"], reverse=True)

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

        fleet_payload = {
            "stats": fleet_stats,
            "salespersons": salespersons_list,
            "records": approval_records,
            "trips": trips_list,
            "payments": payments_list,
            "ledger": ledger_records,
            "cities": sorted(list(cities_set)),
            "route_rules": get_all_cached_city_rules(),
            "fuel_price": get_fuel_price(),
            "meal_rate": get_meal_rate(),
            "accommodation_rate": get_accommodation_rate(),
            "trucks": trucks_list,
            "drivers": drivers_list
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
    master_kpis = {
        "active_operations": active_ops,
        "resolved_operations": resolved_ops,
        "total_operations": total_ops,
        "resolution_rate_pct": res_rate,
        "total_financial_backlog": fleet_payload["stats"]["total_outstanding_backlog"] if fleet_payload else 0.0,
        "transport_revenue": fleet_payload["stats"]["total_transport_charges"] if fleet_payload else 0.0
    }

    return {
        "user": {
            "username": user["username"],
            "name": user["name"],
            "role": user["role"],
            "allowed_domains": allowed
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
    default_tab = "fleet" if user["role"] in ("FLEET_ADMIN", "SALES_ADMIN", "ACCOUNTS_USER", "LOGISTICS_MANAGER") else ("logistics" if user["role"] == "LOGISTICS_ADMIN" else ("projects" if user["role"] == "PROJECTS_ADMIN" else "it"))

    # Generate navigation tab buttons based on allowed domains
    tabs_html = []
    if "fleet" in allowed:
        tabs_html.append('<button id="btn-tab-fleet" onclick="switchDomain(\'fleet\')" class="tab-btn px-3.5 sm:px-4 py-2 rounded-xl text-xs font-bold text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-white transition flex items-center gap-1.5 whitespace-nowrap shrink-0 cursor-pointer"><span>🚚</span> Commercial Fleet Operations</button>')
    if "it" in allowed:
        tabs_html.append('<button id="btn-tab-it" onclick="switchDomain(\'it\')" class="tab-btn px-3.5 sm:px-4 py-2 rounded-xl text-xs font-bold text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-white transition flex items-center gap-1.5 whitespace-nowrap shrink-0 cursor-pointer"><span>💻</span> IT Support</button>')
    if "projects" in allowed:
        tabs_html.append('<button id="btn-tab-projects" onclick="switchDomain(\'projects\')" class="tab-btn px-3.5 sm:px-4 py-2 rounded-xl text-xs font-bold text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-white transition flex items-center gap-1.5 whitespace-nowrap shrink-0 cursor-pointer"><span>🏗️</span> Building Projects</button>')
    if "logistics" in allowed:
        tabs_html.append('<button id="btn-tab-logistics" onclick="switchDomain(\'logistics\')" class="tab-btn px-3.5 sm:px-4 py-2 rounded-xl text-xs font-bold text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-white transition flex items-center gap-1.5 whitespace-nowrap shrink-0 cursor-pointer"><span>🔧</span> Workshop Fleet</button>')

    nav_tabs_markup = "\n".join(tabs_html)
    allowed_domains_json = str(allowed).replace("'", '"')

    # Construct Dynamic Role-Based Sidebar Navigation
    user_role = user.get("role", "LOGISTICS_USER")
    user_name = user.get("name", "User")
    sidebar_links = []
    sidebar_links.append('<div class="px-4 pt-3 pb-1 text-[10px] font-extrabold uppercase tracking-wider text-slate-400 dark:text-zinc-500">Dashboards</div>')

    if user_role == "MASTER_ADMIN":
        sidebar_links.append('<button onclick="switchDomain(\'fleet\'); switchFleetSubView(\'trips\'); toggleSidebar(false);" class="w-full text-left px-4 py-2.5 rounded-xl text-xs font-bold text-slate-700 dark:text-zinc-200 hover:bg-blue-50 dark:hover:bg-blue-500/10 hover:text-blue-600 dark:hover:text-blue-400 transition flex items-center gap-2.5"><span>👑</span> Master Admin Dashboard</button>')

    if user_role in ("MASTER_ADMIN", "ACCOUNTS_USER") or "accounts" in allowed or "fleet" in allowed:
        sidebar_links.append('<button onclick="switchDomain(\'fleet\'); switchFleetSubView(\'salespersons\'); toggleSidebar(false);" class="w-full text-left px-4 py-2.5 rounded-xl text-xs font-bold text-slate-700 dark:text-zinc-200 hover:bg-blue-50 dark:hover:bg-blue-500/10 hover:text-blue-600 dark:hover:text-blue-400 transition flex items-center gap-2.5"><span>💼</span> Accounts & Finance</button>')

    if user_role in ("MASTER_ADMIN", "LOGISTICS_MANAGER") or "fleet" in allowed:
        sidebar_links.append('<button onclick="switchDomain(\'fleet\'); switchFleetSubView(\'trips\'); toggleSidebar(false);" class="w-full text-left px-4 py-2.5 rounded-xl text-xs font-bold text-slate-700 dark:text-zinc-200 hover:bg-blue-50 dark:hover:bg-blue-500/10 hover:text-blue-600 dark:hover:text-blue-400 transition flex items-center gap-2.5"><span>📈</span> Logistics Manager Hub</button>')

    if "logistics" in allowed or "fleet" in allowed:
        sidebar_links.append('<button onclick="switchDomain(\'fleet\'); switchFleetSubView(\'trips\'); toggleSidebar(false);" class="w-full text-left px-4 py-2.5 rounded-xl text-xs font-bold text-slate-700 dark:text-zinc-200 hover:bg-blue-50 dark:hover:bg-blue-500/10 hover:text-blue-600 dark:hover:text-blue-400 transition flex items-center gap-2.5"><span>🚛</span> Operations Execution</button>')

    sidebar_links.append('<div class="px-4 pt-4 pb-1 text-[10px] font-extrabold uppercase tracking-wider text-slate-400 dark:text-zinc-500">Operations & Fleet</div>')
    sidebar_links.append('<button onclick="switchDomain(\'fleet\'); switchFleetSubView(\'trips\'); toggleSidebar(false);" class="w-full text-left px-4 py-2.5 rounded-xl text-xs font-medium text-slate-600 dark:text-zinc-300 hover:bg-slate-100 dark:hover:bg-zinc-800 transition flex items-center gap-2.5"><span>🛣️</span> 7-Stage Trips Pipeline</button>')
    sidebar_links.append('<button onclick="switchDomain(\'fleet\'); switchFleetSubView(\'trucks\'); toggleSidebar(false);" class="w-full text-left px-4 py-2.5 rounded-xl text-xs font-medium text-slate-600 dark:text-zinc-300 hover:bg-slate-100 dark:hover:bg-zinc-800 transition flex items-center gap-2.5"><span>🚚</span> 39 Commercial Trucks</button>')
    sidebar_links.append('<button onclick="switchDomain(\'fleet\'); switchFleetSubView(\'drivers\'); toggleSidebar(false);" class="w-full text-left px-4 py-2.5 rounded-xl text-xs font-medium text-slate-600 dark:text-zinc-300 hover:bg-slate-100 dark:hover:bg-zinc-800 transition flex items-center gap-2.5"><span>👤</span> 21 Commercial Drivers</button>')
    sidebar_links.append('<button onclick="switchDomain(\'fleet\'); openCityConfigModal(); toggleSidebar(false);" class="w-full text-left px-4 py-2.5 rounded-xl text-xs font-medium text-slate-600 dark:text-zinc-300 hover:bg-slate-100 dark:hover:bg-zinc-800 transition flex items-center gap-2.5"><span>📍</span> 45 Delivery Corridors & Stops</button>')

    sidebar_links.append('<div class="px-4 pt-4 pb-1 text-[10px] font-extrabold uppercase tracking-wider text-slate-400 dark:text-zinc-500">Finance & Ledgers</div>')
    sidebar_links.append('<button onclick="switchDomain(\'fleet\'); switchFleetSubView(\'salespersons\'); toggleSidebar(false);" class="w-full text-left px-4 py-2.5 rounded-xl text-xs font-medium text-slate-600 dark:text-zinc-300 hover:bg-slate-100 dark:hover:bg-zinc-800 transition flex items-center gap-2.5"><span>👥</span> Sales Rep Debt Ledger</button>')
    sidebar_links.append('<button onclick="switchDomain(\'fleet\'); switchFleetSubView(\'payments\'); toggleSidebar(false);" class="w-full text-left px-4 py-2.5 rounded-xl text-xs font-medium text-slate-600 dark:text-zinc-300 hover:bg-slate-100 dark:hover:bg-zinc-800 transition flex items-center gap-2.5"><span>💳</span> Cleared Payments History</button>')
    sidebar_links.append('<button onclick="switchDomain(\'fleet\'); switchFleetSubView(\'ledger\'); toggleSidebar(false);" class="w-full text-left px-4 py-2.5 rounded-xl text-xs font-medium text-slate-600 dark:text-zinc-300 hover:bg-slate-100 dark:hover:bg-zinc-800 transition flex items-center gap-2.5"><span>📜</span> Shortfall Recovery Ledger</button>')

    sidebar_links.append('<div class="px-4 pt-4 pb-1 text-[10px] font-extrabold uppercase tracking-wider text-slate-400 dark:text-zinc-500">System Management</div>')
    sidebar_links.append('<button onclick="openCityConfigModal(); toggleSidebar(false);" class="w-full text-left px-4 py-2.5 rounded-xl text-xs font-medium text-slate-600 dark:text-zinc-300 hover:bg-slate-100 dark:hover:bg-zinc-800 transition flex items-center gap-2.5"><span>⚙️</span> Edit Fuel & City Minimums</button>')
    sidebar_links.append('<button onclick="openAuditLogsModal(); toggleSidebar(false);" class="w-full text-left px-4 py-2.5 rounded-xl text-xs font-medium text-slate-600 dark:text-zinc-300 hover:bg-slate-100 dark:hover:bg-zinc-800 transition flex items-center gap-2.5"><span>🛡️</span> System Audit Logs</button>')

    sidebar_markup = "\n".join(sidebar_links)

    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <title>Tagoneswa Operations Console</title>
    <script src="https://cdn.tailwindcss.com"></script>
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
                <div class="w-8 h-8 bg-blue-600 rounded-xl flex items-center justify-center text-white text-base font-bold shadow-md shadow-blue-500/20">
                    🚚
                </div>
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
        <nav class="flex-1 overflow-y-auto p-3 space-y-1 no-scrollbar">
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
                        <div class="w-9 h-9 sm:w-10 sm:h-10 bg-gradient-to-tr from-blue-700 via-blue-600 to-indigo-500 rounded-xl flex items-center justify-center text-white text-lg sm:text-xl font-bold shadow-md shadow-blue-500/20 shrink-0 border border-blue-400/30">
                            🚚
                        </div>
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
                        <input type="text" id="it-search" placeholder="🔍 Search employee, ticket #, issue..." oninput="filterITTable(true)" class="bg-white dark:bg-[#121216] border border-slate-300 dark:border-zinc-750 rounded-xl px-4 py-2.5 sm:py-2 text-xs font-medium text-slate-800 dark:text-zinc-100 placeholder-slate-400 dark:placeholder-zinc-500 focus:outline-none focus:ring-2 focus:ring-blue-500 w-full sm:w-64 transition">
                        
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
                        <input type="text" id="proj-search" placeholder="🔍 Search site, ticket #, repair..." oninput="filterProjectsTable(true)" class="bg-white dark:bg-[#121216] border border-slate-300 dark:border-zinc-750 rounded-xl px-4 py-2.5 sm:py-2 text-xs font-medium text-slate-800 dark:text-zinc-100 placeholder-slate-400 dark:placeholder-zinc-500 focus:outline-none focus:ring-2 focus:ring-blue-500 w-full sm:w-64 transition">
                        
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
                        <input type="text" id="ws-search" placeholder="🔍 Search truck #, plate, fault notes..." oninput="filterFleetTable(true)" class="bg-white dark:bg-[#121216] border border-slate-300 dark:border-zinc-750 rounded-xl px-4 py-2.5 sm:py-2 text-xs font-medium text-slate-800 dark:text-zinc-100 placeholder-slate-400 dark:placeholder-zinc-500 focus:outline-none focus:ring-2 focus:ring-blue-500 w-full sm:w-64 transition">
                        
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
        <!-- TAB 4: COMMERCIAL FLEET & LOGISTICS OPERATIONS -->
        <!-- ========================================================= -->
        <div id="view-fleet" class="domain-view space-y-6 sm:space-y-8" style="display: {'block' if 'fleet' in allowed and default_tab == 'fleet' else 'none'}">
            <!-- Executive Fleet Command Center Banner -->
            <div id="master-kpi-banner" class="bg-gradient-to-r from-slate-900 via-blue-950 to-slate-900 dark:from-[#0a0a0f] dark:via-[#0c0c14] dark:to-[#08080c] text-white rounded-3xl p-5 sm:p-7 shadow-2xl border border-slate-800 dark:border-zinc-800">
                <div class="flex flex-col lg:flex-row lg:items-center justify-between gap-4 border-b border-slate-800/80 dark:border-zinc-800/80 pb-4 mb-5">
                    <div>
                        <div class="inline-flex items-center gap-2 bg-blue-500/20 text-blue-300 border border-blue-400/30 px-3 py-1 rounded-full text-[11px] font-bold tracking-wide uppercase mb-1.5">
                            ⚡ Commercial Fleet & Logistics Operations
                        </div>
                        <h2 class="text-xl sm:text-2xl font-extrabold tracking-tight">Enterprise Fleet & Commercial Command Center</h2>
                        <p class="text-xs text-slate-400 mt-1">Full 7-Stage Trip Pipeline, 39 Commercial Trucks, 21 Drivers, 45 Zimbabwe Corridors & Financial Debt Ledgers</p>
                    </div>
                    <!-- Quick Management Action Buttons -->
                    <div class="flex flex-wrap items-center gap-2 sm:gap-2.5">
                        <button onclick="openCityConfigModal()" class="bg-blue-600 hover:bg-blue-500 text-white px-3.5 py-2 rounded-xl text-xs font-bold transition flex items-center gap-1.5 border border-blue-400/40 shadow-xs cursor-pointer">
                            <span>⚙️</span> Edit Fuel & City Minimums
                        </button>
                        <button onclick="openClearPaymentModal()" class="bg-emerald-600 hover:bg-emerald-500 text-white px-3.5 py-2 rounded-xl text-xs font-bold transition flex items-center gap-1.5 border border-emerald-400/40 shadow-xs cursor-pointer">
                            <span>💳</span> Clear Sales Rep Debt
                        </button>
                        <button onclick="openAuditLogsModal()" class="bg-slate-800 hover:bg-slate-700 text-slate-200 px-3 py-2 rounded-xl text-xs font-bold transition flex items-center gap-1.5 border border-slate-700 shadow-xs cursor-pointer">
                            <span>🛡️</span> Audit Logs
                        </button>
                    </div>
                </div>

                <div class="grid grid-cols-2 md:grid-cols-4 gap-3 sm:gap-4">
                    <div class="bg-slate-800/60 dark:bg-[#121216]/90 backdrop-blur border border-slate-700/60 dark:border-zinc-800/80 rounded-2xl p-4 shadow-xs">
                        <div class="text-[11px] font-bold uppercase tracking-wider text-slate-400 dark:text-zinc-500">Total Active Tasks</div>
                        <div class="text-2xl sm:text-3xl font-extrabold text-amber-400 mt-1" id="master-active-ops">0</div>
                        <div class="text-[11px] text-slate-400 dark:text-zinc-400 mt-0.5 font-medium">Pending approvals</div>
                    </div>
                    <div class="bg-slate-800/60 dark:bg-[#121216]/90 backdrop-blur border border-slate-700/60 dark:border-zinc-800/80 rounded-2xl p-4 shadow-xs">
                        <div class="text-[11px] font-bold uppercase tracking-wider text-slate-400 dark:text-zinc-500">Clearance Rate</div>
                        <div class="text-2xl sm:text-3xl font-extrabold text-emerald-400 mt-1" id="master-res-rate">100%</div>
                        <div class="text-[11px] text-slate-400 dark:text-zinc-400 mt-0.5 font-medium">Approved vs dispatched</div>
                    </div>
                    <div class="bg-slate-800/60 dark:bg-[#121216]/90 backdrop-blur border border-slate-700/60 dark:border-zinc-800/80 rounded-2xl p-4 shadow-xs">
                        <div class="text-[11px] font-bold uppercase tracking-wider text-slate-400 dark:text-zinc-500">Transport Billed</div>
                        <div class="text-2xl sm:text-3xl font-extrabold text-blue-400 mt-1" id="master-transport-revenue">$0.00</div>
                        <div class="text-[11px] text-slate-400 dark:text-zinc-400 mt-0.5 font-medium">Shortfall recovery charges</div>
                    </div>
                    <div class="bg-slate-800/60 dark:bg-[#121216]/90 backdrop-blur border border-slate-700/60 dark:border-zinc-800/80 rounded-2xl p-4 shadow-xs">
                        <div class="text-[11px] font-bold uppercase tracking-wider text-slate-400 dark:text-zinc-500">Salesperson Debt Backlog</div>
                        <div class="text-2xl sm:text-3xl font-extrabold text-rose-400 mt-1" id="master-financial-backlog">$0.00</div>
                        <div class="text-[11px] text-slate-400 dark:text-zinc-400 mt-0.5 font-medium">Pending shortfall recovery</div>
                    </div>
                </div>
            </div>

            <!-- Fleet Operational Sub-View Navigation Pills -->
            <div class="flex items-center gap-1.5 p-1.5 bg-slate-100 dark:bg-[#0c0c10] rounded-2xl border border-slate-200 dark:border-zinc-800 overflow-x-auto no-scrollbar scroll-smooth">
                <button onclick="switchFleetSubView('trips')" id="fleet-btn-trips" class="fleet-subview-btn px-3.5 py-2 rounded-xl text-xs font-bold transition flex items-center gap-1.5 whitespace-nowrap cursor-pointer bg-blue-600 text-white shadow-md">
                    <span>🛣️</span> 7-Stage Trips Pipeline
                </button>
                <button onclick="switchFleetSubView('salespersons')" id="fleet-btn-salespersons" class="fleet-subview-btn px-3.5 py-2 rounded-xl text-xs font-bold transition flex items-center gap-1.5 whitespace-nowrap cursor-pointer bg-white dark:bg-[#121216] text-slate-700 dark:text-zinc-300 hover:bg-slate-50 dark:hover:bg-zinc-800">
                    <span>👥</span> Sales Rep Debt Ledger
                </button>
                <button onclick="switchFleetSubView('payments')" id="fleet-btn-payments" class="fleet-subview-btn px-3.5 py-2 rounded-xl text-xs font-bold transition flex items-center gap-1.5 whitespace-nowrap cursor-pointer bg-white dark:bg-[#121216] text-slate-700 dark:text-zinc-300 hover:bg-slate-50 dark:hover:bg-zinc-800">
                    <span>💳</span> Cleared Payments History
                </button>
                <button onclick="switchFleetSubView('trucks')" id="fleet-btn-trucks" class="fleet-subview-btn px-3.5 py-2 rounded-xl text-xs font-bold transition flex items-center gap-1.5 whitespace-nowrap cursor-pointer bg-white dark:bg-[#121216] text-slate-700 dark:text-zinc-300 hover:bg-slate-50 dark:hover:bg-zinc-800">
                    <span>🚚</span> 39 Commercial Trucks
                </button>
                <button onclick="switchFleetSubView('drivers')" id="fleet-btn-drivers" class="fleet-subview-btn px-3.5 py-2 rounded-xl text-xs font-bold transition flex items-center gap-1.5 whitespace-nowrap cursor-pointer bg-white dark:bg-[#121216] text-slate-700 dark:text-zinc-300 hover:bg-slate-50 dark:hover:bg-zinc-800">
                    <span>👤</span> 21 Commercial Drivers
                </button>
                <button onclick="switchFleetSubView('approvals')" id="fleet-btn-approvals" class="fleet-subview-btn px-3.5 py-2 rounded-xl text-xs font-bold transition flex items-center gap-1.5 whitespace-nowrap cursor-pointer bg-white dark:bg-[#121216] text-slate-700 dark:text-zinc-300 hover:bg-slate-50 dark:hover:bg-zinc-800">
                    <span>📋</span> Shortfall Approvals
                </button>
                <button onclick="switchFleetSubView('ledger')" id="fleet-btn-ledger" class="fleet-subview-btn px-3.5 py-2 rounded-xl text-xs font-bold transition flex items-center gap-1.5 whitespace-nowrap cursor-pointer bg-white dark:bg-[#121216] text-slate-700 dark:text-zinc-300 hover:bg-slate-50 dark:hover:bg-zinc-800">
                    <span>📜</span> Financial Audit Ledger
                </button>
                <button onclick="switchFleetSubView('all')" id="fleet-btn-all" class="fleet-subview-btn px-3.5 py-2 rounded-xl text-xs font-bold transition flex items-center gap-1.5 whitespace-nowrap cursor-pointer bg-white dark:bg-[#121216] text-slate-700 dark:text-zinc-300 hover:bg-slate-50 dark:hover:bg-zinc-800">
                    <span>🌐</span> All Operations
                </button>
            </div>

            <!-- Fleet Approval Top Stats Cards -->
            <div class="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3 sm:gap-4">
                <div class="bg-white dark:bg-[#0a0a0d] border border-slate-200/80 dark:border-zinc-800/80 rounded-2xl p-4 sm:p-5 shadow-xs hover:shadow-md transition-all duration-200">
                    <div class="text-[11px] sm:text-xs font-bold uppercase tracking-wider text-slate-400 dark:text-zinc-500">Total Trips Verified</div>
                    <div class="text-2xl sm:text-3xl font-extrabold text-blue-600 dark:text-blue-400 mt-1.5" id="fleet-stat-trips">0</div>
                    <div class="text-[11px] sm:text-xs text-blue-600 dark:text-blue-400 font-semibold mt-1" id="fleet-stat-sales-val">$0.00 ERP Sales</div>
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
                <div class="bg-white dark:bg-[#0a0a0d] border border-slate-200/80 dark:border-zinc-800/80 rounded-2xl p-4 sm:p-5 shadow-xs hover:shadow-md transition-all duration-200 col-span-2 sm:col-span-1">
                    <div class="text-[11px] sm:text-xs font-bold uppercase tracking-wider text-slate-400 dark:text-zinc-500">Salesperson Debt</div>
                    <div class="text-2xl sm:text-3xl font-extrabold text-rose-500 dark:text-rose-400 mt-1.5" id="fleet-stat-backlog">$0.00</div>
                    <div class="text-[11px] sm:text-xs text-rose-600 dark:text-rose-400 font-semibold mt-1">Pending Shortfall Ledger</div>
                </div>
            </div>

            <!-- SUBVIEW 1: 7-STAGE TRIPS PIPELINE -->
            <div id="fleet-section-trips" class="fleet-subview-panel bg-white dark:bg-[#0a0a0d] border border-slate-200/80 dark:border-zinc-800/80 rounded-2xl shadow-xs overflow-hidden transition-all duration-200">
                <div class="p-4 sm:p-5 border-b border-slate-200 dark:border-zinc-850 flex flex-col md:flex-row items-stretch md:items-center justify-between gap-3 sm:gap-4 bg-slate-50/60 dark:bg-[#0e0e12]/80">
                    <div class="flex flex-col sm:flex-row flex-wrap items-stretch sm:items-center gap-2 sm:gap-3 w-full md:w-auto">
                        <input type="text" id="trips-search" placeholder="🔍 Search Trip #, Driver, Truck, City..." oninput="filterTripsTable(true)" class="bg-white dark:bg-[#121216] border border-slate-300 dark:border-zinc-750 rounded-xl px-4 py-2 text-xs font-medium text-slate-800 dark:text-zinc-100 placeholder-slate-400 dark:placeholder-zinc-500 focus:outline-none focus:ring-2 focus:ring-blue-500 w-full sm:w-64 transition">
                        
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
            <div id="fleet-section-salespersons" class="fleet-subview-panel bg-white dark:bg-[#0a0a0d] border border-slate-200/80 dark:border-zinc-800/80 rounded-2xl p-5 sm:p-6 shadow-xs">
                <div class="flex flex-col sm:flex-row sm:items-center justify-between mb-4 gap-2">
                    <div>
                        <h2 class="text-xs sm:text-sm font-extrabold uppercase tracking-wider text-slate-900 dark:text-zinc-100 flex items-center gap-2">
                            <span>👥</span> Salesperson Outstanding Balance & Recovery Audit
                        </h2>
                        <p class="text-[11px] text-slate-500 dark:text-zinc-400 mt-0.5">Real-time balances tracked per sales representative with instant clearance action</p>
                    </div>
                    <div class="flex items-center gap-3">
                        <button onclick="openClearPaymentModal()" class="bg-emerald-600 hover:bg-emerald-700 text-white font-bold px-3 py-1.5 rounded-xl text-xs transition flex items-center gap-1.5 shadow-xs cursor-pointer">
                            <span>💳</span> Clear Debt Payment
                        </button>
                        <div class="text-right">
                            <span class="text-xs font-bold text-slate-500 dark:text-zinc-400">Total Pending: </span>
                            <span class="text-sm font-extrabold text-rose-600 dark:text-rose-400 font-mono" id="fleet-total-pending-pill">$0.00</span>
                        </div>
                    </div>
                </div>
                <div class="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-3 sm:gap-4" id="fleet-salesperson-cards">
                    <!-- Populated dynamically -->
                </div>
            </div>

            <!-- SUBVIEW 3: CLEARED PAYMENTS HISTORY -->
            <div id="fleet-section-payments" class="fleet-subview-panel bg-white dark:bg-[#0a0a0d] border border-slate-200/80 dark:border-zinc-800/80 rounded-2xl shadow-xs overflow-hidden transition-all duration-200">
                <div class="p-4 sm:p-5 border-b border-slate-200 dark:border-zinc-850 flex flex-col md:flex-row items-stretch md:items-center justify-between gap-3 sm:gap-4 bg-slate-50/60 dark:bg-[#0e0e12]/80">
                    <div>
                        <h3 class="text-xs sm:text-sm font-extrabold uppercase tracking-wider text-slate-900 dark:text-zinc-100 flex items-center gap-2">
                            <span>💳</span> Cleared Sales Rep Debt Settlements
                        </h3>
                        <p class="text-[11px] text-slate-500 dark:text-zinc-400">Official accounting verification and payment offset audit history</p>
                    </div>
                    <button onclick="openClearPaymentModal()" class="bg-emerald-600 hover:bg-emerald-700 text-white font-bold px-3.5 py-1.5 rounded-xl text-xs transition flex items-center gap-1.5 shadow-xs cursor-pointer self-start sm:self-auto">
                        <span>+</span> Record New Clearance
                    </button>
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

            <!-- SUBVIEW 4: 39 COMMERCIAL TRUCKS FLEET -->
            <div id="fleet-section-trucks" class="fleet-subview-panel bg-white dark:bg-[#0a0a0d] border border-slate-200/80 dark:border-zinc-800/80 rounded-2xl shadow-xs overflow-hidden transition-all duration-200">
                <div class="p-4 sm:p-5 border-b border-slate-200 dark:border-zinc-850 flex flex-col md:flex-row items-stretch md:items-center justify-between gap-3 sm:gap-4 bg-slate-50/60 dark:bg-[#0e0e12]/80">
                    <div>
                        <h3 class="text-xs sm:text-sm font-extrabold uppercase tracking-wider text-slate-900 dark:text-zinc-100 flex items-center gap-2">
                            <span>🚚</span> 39 Commercial Trucks Fleet Master
                        </h3>
                        <p class="text-[11px] text-slate-500 dark:text-zinc-400">Verified commercial delivery vehicles registered in Tagoneswa database</p>
                    </div>
                    <input type="text" id="trucks-search" placeholder="🔍 Search Truck #, Plate, Model..." oninput="filterTrucksTable(true)" class="bg-white dark:bg-[#121216] border border-slate-300 dark:border-zinc-750 rounded-xl px-4 py-2 text-xs font-medium text-slate-800 dark:text-zinc-100 placeholder-slate-400 dark:placeholder-zinc-500 focus:outline-none focus:ring-2 focus:ring-blue-500 w-full sm:w-64 transition">
                </div>

                <div class="overflow-x-auto">
                    <table class="w-full text-left text-xs min-w-[760px]">
                        <thead class="bg-slate-100/75 dark:bg-[#0e0e12] text-slate-500 dark:text-zinc-400 font-bold uppercase tracking-wider border-b border-slate-200 dark:border-zinc-800">
                            <tr>
                                <th class="px-4 sm:px-5 py-3.5 whitespace-nowrap">Truck #</th>
                                <th class="px-4 sm:px-5 py-3.5 whitespace-nowrap">Plate Number</th>
                                <th class="px-4 sm:px-5 py-3.5 whitespace-nowrap">Model & Make</th>
                                <th class="px-4 sm:px-5 py-3.5 whitespace-nowrap">Body Type</th>
                                <th class="px-4 sm:px-5 py-3.5 whitespace-nowrap">Home Depot</th>
                                <th class="px-4 sm:px-5 py-3.5 whitespace-nowrap">Active Status</th>
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

            <!-- SUBVIEW 5: 21 COMMERCIAL DRIVERS -->
            <div id="fleet-section-drivers" class="fleet-subview-panel bg-white dark:bg-[#0a0a0d] border border-slate-200/80 dark:border-zinc-800/80 rounded-2xl shadow-xs overflow-hidden transition-all duration-200">
                <div class="p-4 sm:p-5 border-b border-slate-200 dark:border-zinc-850 flex flex-col md:flex-row items-stretch md:items-center justify-between gap-3 sm:gap-4 bg-slate-50/60 dark:bg-[#0e0e12]/80">
                    <div>
                        <h3 class="text-xs sm:text-sm font-extrabold uppercase tracking-wider text-slate-900 dark:text-zinc-100 flex items-center gap-2">
                            <span>👤</span> 21 Commercial Drivers Roster
                        </h3>
                        <p class="text-[11px] text-slate-500 dark:text-zinc-400">Verified commercial drivers registered in Tagoneswa database</p>
                    </div>
                    <input type="text" id="drivers-search" placeholder="🔍 Search Driver Name, Phone..." oninput="filterDriversTable(true)" class="bg-white dark:bg-[#121216] border border-slate-300 dark:border-zinc-750 rounded-xl px-4 py-2 text-xs font-medium text-slate-800 dark:text-zinc-100 placeholder-slate-400 dark:placeholder-zinc-500 focus:outline-none focus:ring-2 focus:ring-blue-500 w-full sm:w-64 transition">
                </div>

                <div class="overflow-x-auto">
                    <table class="w-full text-left text-xs min-w-[760px]">
                        <thead class="bg-slate-100/75 dark:bg-[#0e0e12] text-slate-500 dark:text-zinc-400 font-bold uppercase tracking-wider border-b border-slate-200 dark:border-zinc-800">
                            <tr>
                                <th class="px-4 sm:px-5 py-3.5 whitespace-nowrap">Staff ID</th>
                                <th class="px-4 sm:px-5 py-3.5 whitespace-nowrap">Full Name</th>
                                <th class="px-4 sm:px-5 py-3.5 whitespace-nowrap">WhatsApp Phone</th>
                                <th class="px-4 sm:px-5 py-3.5 whitespace-nowrap">Role Designation</th>
                                <th class="px-4 sm:px-5 py-3.5 whitespace-nowrap">Active Status</th>
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
            <div id="fleet-section-approvals" class="fleet-subview-panel bg-white dark:bg-[#0a0a0d] border border-slate-200/80 dark:border-zinc-800/80 rounded-2xl shadow-xs overflow-hidden transition-all duration-200">
                <div class="p-4 sm:p-5 border-b border-slate-200 dark:border-zinc-850 flex flex-col md:flex-row items-stretch md:items-center justify-between gap-3 sm:gap-4 bg-slate-50/60 dark:bg-[#0e0e12]/80">
                    <div class="flex flex-col sm:flex-row flex-wrap items-stretch sm:items-center gap-2 sm:gap-3 w-full md:w-auto">
                        <input type="text" id="fleet-search" placeholder="🔍 Search Trip ID, Salesperson, City..." oninput="filterFleetApprovalsTable(true)" class="bg-white dark:bg-[#121216] border border-slate-300 dark:border-zinc-750 rounded-xl px-4 py-2.5 sm:py-2 text-xs font-medium text-slate-800 dark:text-zinc-100 placeholder-slate-400 dark:placeholder-zinc-500 focus:outline-none focus:ring-2 focus:ring-blue-500 w-full sm:w-64 transition">
                        
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
                                <th class="px-4 sm:px-5 py-3.5 whitespace-nowrap">ERP Valuation</th>
                                <th class="px-4 sm:px-5 py-3.5 whitespace-nowrap">Shortfall / Transport</th>
                                <th class="px-4 sm:px-5 py-3.5 whitespace-nowrap">Settlement (Customer vs Debt)</th>
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

            <!-- SUBVIEW 7: FINANCIAL AUDIT & RECOVERY LEDGER -->
            <div id="fleet-section-ledger" class="fleet-subview-panel bg-white dark:bg-[#0a0a0d] border border-slate-200/80 dark:border-zinc-800/80 rounded-2xl shadow-xs overflow-hidden transition-all duration-200">
                <div class="p-4 sm:p-5 border-b border-slate-200 dark:border-zinc-850 bg-slate-50/75 dark:bg-[#0e0e12]/80">
                    <div class="flex flex-col md:flex-row md:items-center justify-between gap-4">
                        <div>
                            <div class="inline-flex items-center gap-1.5 bg-indigo-50 dark:bg-indigo-500/10 text-indigo-700 dark:text-indigo-300 border border-indigo-200 dark:border-indigo-500/30 px-2.5 py-0.5 rounded-full text-[10px] font-bold uppercase tracking-wider mb-1">
                                🛡️ Anti-Cheating & Parity Guard
                            </div>
                            <h3 class="text-xs sm:text-sm font-extrabold uppercase tracking-wider text-slate-900 dark:text-zinc-100">
                                Daily Recovery & Shortfall Audit Ledger
                            </h3>
                            <p class="text-[11px] text-slate-500 dark:text-zinc-400">Cross-verifies customer charges, debt records, and accounts clearances</p>
                        </div>

                        <!-- Date Filters -->
                        <div class="flex items-center gap-1 bg-white dark:bg-[#121216] p-1 rounded-xl border border-slate-300 dark:border-zinc-750 self-start md:self-auto">
                            <button onclick="setAuditTimeframe('ALL')" id="timeframe-btn-ALL" class="audit-tf-btn px-3 py-1 rounded-lg text-xs font-bold bg-blue-600 text-white transition cursor-pointer">All Dates</button>
                            <button onclick="setAuditTimeframe('TODAY')" id="timeframe-btn-TODAY" class="audit-tf-btn px-3 py-1 rounded-lg text-xs font-bold text-slate-600 dark:text-zinc-300 hover:text-slate-900 dark:hover:text-white transition cursor-pointer">Today</button>
                            <button onclick="setAuditTimeframe('YESTERDAY')" id="timeframe-btn-YESTERDAY" class="audit-tf-btn px-3 py-1 rounded-lg text-xs font-bold text-slate-600 dark:text-zinc-300 hover:text-slate-900 dark:hover:text-white transition cursor-pointer">Yesterday</button>
                            <button onclick="setAuditTimeframe('WEEK')" id="timeframe-btn-WEEK" class="audit-tf-btn px-3 py-1 rounded-lg text-xs font-bold text-slate-600 dark:text-zinc-300 hover:text-slate-900 dark:hover:text-white transition cursor-pointer">Last 7 Days</button>
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
                        <thead class="bg-slate-100/75 dark:bg-[#0e0e12] text-slate-500 dark:text-zinc-400 font-bold uppercase tracking-wider border-b border-slate-200 dark:border-zinc-800">
                            <tr>
                                <th class="px-4 sm:px-5 py-3 whitespace-nowrap">Date</th>
                                <th class="px-4 sm:px-5 py-3 whitespace-nowrap">Salesperson</th>
                                <th class="px-4 sm:px-5 py-3 whitespace-nowrap">Trip Ref</th>
                                <th class="px-4 sm:px-5 py-3 whitespace-nowrap">Transaction Type</th>
                                <th class="px-4 sm:px-5 py-3 whitespace-nowrap">Amount</th>
                                <th class="px-4 sm:px-5 py-3 whitespace-nowrap">Audit Details & Notes</th>
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
        </div>
    </main>

    <!-- Modal 1: Dynamic Fuel Price & 45 City Delivery Corridors Configuration -->
    <div id="cityMinimumsModal" class="fixed inset-0 z-50 hidden flex items-center justify-center p-3 sm:p-4 bg-slate-900/70 backdrop-blur-xs">
        <div class="bg-white dark:bg-[#0c0c10] border border-slate-200 dark:border-zinc-800 rounded-3xl w-full max-w-4xl max-h-[92vh] flex flex-col shadow-2xl overflow-hidden animate-in fade-in zoom-in-95 duration-150">
            <!-- Modal Header -->
            <div class="p-4 sm:p-5 border-b border-slate-200 dark:border-zinc-800 flex items-center justify-between bg-slate-50 dark:bg-[#121216]">
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
            <div class="p-4 sm:p-6 overflow-y-auto space-y-6 flex-1">
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

                <!-- 45 Cities Search & Table -->
                <div class="border border-slate-200 dark:border-zinc-800 rounded-2xl overflow-hidden">
                    <div class="p-3.5 bg-slate-50/75 dark:bg-[#121216] border-b border-slate-200 dark:border-zinc-800 flex flex-col sm:flex-row items-stretch sm:items-center justify-between gap-3">
                        <div class="flex items-center gap-2">
                            <input type="text" id="modal-city-search" placeholder="🔍 Search city or route..." oninput="filterCityRulesModal()" class="bg-white dark:bg-[#181820] border border-slate-300 dark:border-zinc-700 rounded-xl px-3.5 py-1.5 text-xs font-medium text-slate-800 dark:text-zinc-100 placeholder-slate-400 dark:placeholder-zinc-500 focus:outline-none focus:ring-2 focus:ring-blue-500 w-full sm:w-60 transition">
                            <span id="modal-city-count" class="text-xs text-slate-500 dark:text-zinc-400 font-bold whitespace-nowrap">45 Cities</span>
                        </div>
                        <span class="text-[11px] text-slate-400 dark:text-zinc-500 italic">Values saved dynamically into database without hardcoding</span>
                    </div>

                    <div class="max-h-[46vh] overflow-y-auto">
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
            <div class="p-3.5 sm:p-4 border-t border-slate-200 dark:border-zinc-800 bg-slate-50 dark:bg-[#121216] flex items-center justify-between">
                <span class="text-[11px] text-slate-500 dark:text-zinc-400">All trip pricing calculations update instantly in WhatsApp</span>
                <button onclick="closeCityConfigModal()" class="px-4 py-2 rounded-xl text-xs font-bold bg-slate-200 dark:bg-zinc-800 text-slate-700 dark:text-zinc-200 hover:bg-slate-300 dark:hover:bg-zinc-700 transition cursor-pointer">
                    Done / Close
                </button>
            </div>
        </div>
    </div>

    <!-- Modal 2: Financial Debt Settlement & Payment Clearance -->
    <div id="clearPaymentModal" class="fixed inset-0 z-50 hidden flex items-center justify-center p-3 sm:p-4 bg-slate-900/70 backdrop-blur-xs">
        <div class="bg-white dark:bg-[#0c0c10] border border-slate-200 dark:border-zinc-800 rounded-3xl w-full max-w-lg flex flex-col shadow-2xl overflow-hidden animate-in fade-in zoom-in-95 duration-150">
            <!-- Modal Header -->
            <div class="p-4 sm:p-5 border-b border-slate-200 dark:border-zinc-800 flex items-center justify-between bg-slate-50 dark:bg-[#121216]">
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
            <div class="p-4 sm:p-6 space-y-4">
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
            <div class="p-4 border-t border-slate-200 dark:border-zinc-800 bg-slate-50 dark:bg-[#121216] flex items-center justify-end gap-2.5">
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
    <div id="auditLogsModal" class="fixed inset-0 z-50 hidden flex items-center justify-center p-3 sm:p-4 bg-slate-900/70 backdrop-blur-xs">
        <div class="bg-white dark:bg-[#0c0c10] border border-slate-200 dark:border-zinc-800 rounded-3xl w-full max-w-4xl max-h-[90vh] flex flex-col shadow-2xl overflow-hidden animate-in fade-in zoom-in-95 duration-150">
            <!-- Modal Header -->
            <div class="p-4 sm:p-5 border-b border-slate-200 dark:border-zinc-800 flex items-center justify-between bg-slate-50 dark:bg-[#121216]">
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
            <div class="overflow-y-auto flex-1 p-4">
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
            <div class="p-3.5 border-t border-slate-200 dark:border-zinc-800 bg-slate-50 dark:bg-[#121216] flex items-center justify-between">
                <span class="text-[11px] text-slate-400 dark:text-zinc-500">Security & compliance logs cannot be purged or modified</span>
                <button onclick="closeAuditLogsModal()" class="px-4 py-2 rounded-xl text-xs font-bold bg-slate-200 dark:bg-zinc-800 text-slate-700 dark:text-zinc-200 hover:bg-slate-300 dark:hover:bg-zinc-700 transition cursor-pointer">
                    Close
                </button>
            </div>
        </div>
    </div>

    <script>
        let cachedData = null;
        let isRefreshing = false;
        const initialAllowedDomains = {allowed_domains_json};
        const initialDefaultTab = '{default_tab}';
        // Pagination state
        let itPage = 1, itPageSize = 15;
        let projPage = 1, projPageSize = 15;
        let wsPage = 1, wsPageSize = 15;
        let fleetPage = 1, fleetPageSize = 15;
        let ledgerPage = 1, ledgerPageSize = 15;
        let tripsPage = 1, tripsPageSize = 15;
        let trucksPage = 1, trucksPageSize = 15;
        let driversPage = 1, driversPageSize = 15;
        let paymentsPage = 1, paymentsPageSize = 15;

        function renderPaginationControls(infoId, controlsId, currentPage, totalCount, pageSize, changeFnName) {{
            const infoEl = document.getElementById(infoId);
            const controlsEl = document.getElementById(controlsId);
            if (!infoEl || !controlsEl) return;

            if (totalCount === 0) {{
                infoEl.textContent = 'Showing 0 of 0 entries';
                controlsEl.innerHTML = '';
                return;
            }}

            const totalPages = Math.max(1, Math.ceil(totalCount / pageSize));
            const startItem = (currentPage - 1) * pageSize + 1;
            const endItem = Math.min(currentPage * pageSize, totalCount);

            infoEl.innerHTML = `Showing <strong class="text-slate-900 dark:text-zinc-100">${{startItem}}–${{endItem}}</strong> of <strong class="text-slate-900 dark:text-zinc-100">${{totalCount}}</strong> entries`;

            if (totalPages <= 1) {{
                controlsEl.innerHTML = '';
                return;
            }}

            const isPrevDisabled = currentPage <= 1;
            const isNextDisabled = currentPage >= totalPages;

            const btnClass = "px-2.5 py-1 text-xs rounded-lg font-bold border transition cursor-pointer flex items-center gap-1 ";
            const activeBtnClass = btnClass + "bg-white dark:bg-[#16161c] text-slate-700 dark:text-zinc-200 border-slate-300 dark:border-zinc-700 hover:bg-slate-100 dark:hover:bg-[#202028]";
            const disabledBtnClass = btnClass + "bg-slate-100 dark:bg-[#0f0f13] text-slate-400 dark:text-zinc-600 border-slate-200 dark:border-zinc-800 cursor-not-allowed opacity-50";

            controlsEl.innerHTML = `
                <button onclick="${{changeFnName}}(${{currentPage - 1}})" ${{isPrevDisabled ? 'disabled' : ''}} class="${{isPrevDisabled ? disabledBtnClass : activeBtnClass}}">
                    ‹ Prev
                </button>
                <span class="text-xs font-semibold px-2 text-slate-600 dark:text-zinc-400">
                    Page <strong class="text-slate-900 dark:text-zinc-100 font-mono">${{currentPage}}</strong> of <strong class="text-slate-900 dark:text-zinc-100 font-mono">${{totalPages}}</strong>
                </span>
                <button onclick="${{changeFnName}}(${{currentPage + 1}})" ${{isNextDisabled ? 'disabled' : ''}} class="${{isNextDisabled ? disabledBtnClass : activeBtnClass}}">
                    Next ›
                </button>
            `;
        }}

        function changeITPage(p) {{ itPage = p; filterITTable(false); }}
        function changeProjPage(p) {{ projPage = p; filterProjectsTable(false); }}
        function changeWSPage(p) {{ wsPage = p; filterFleetTable(false); }}
        function changeFleetPage(p) {{ fleetPage = p; filterFleetApprovalsTable(false); }}
        function changeLedgerPage(p) {{ ledgerPage = p; filterLedgerTable(false); }}
        function changeTripsPage(p) {{ tripsPage = p; filterTripsTable(false); }}
        function changeTrucksPage(p) {{ trucksPage = p; filterTrucksTable(false); }}
        function changeDriversPage(p) {{ driversPage = p; filterDriversTable(false); }}
        function changePaymentsPage(p) {{ paymentsPage = p; filterPaymentsTable(false); }}

        // -------------------------------------------------------------
        // Sliding Sidebar Controller
        // -------------------------------------------------------------
        function toggleSidebar(open) {{
            const sidebar = document.getElementById('sliding-sidebar');
            const backdrop = document.getElementById('sidebar-backdrop');
            if (!sidebar || !backdrop) return;
            if (open) {{
                sidebar.classList.remove('-translate-x-full');
                backdrop.classList.remove('hidden');
            }} else {{
                sidebar.classList.add('-translate-x-full');
                backdrop.classList.add('hidden');
            }}
        }}

        // -------------------------------------------------------------
        // Fleet Operations Sub-View Switcher
        // -------------------------------------------------------------
        let currentFleetSubView = 'trips';
        function switchFleetSubView(viewId) {{
            currentFleetSubView = viewId;
            document.querySelectorAll('.fleet-subview-btn').forEach(btn => {{
                btn.classList.remove('bg-blue-600', 'text-white', 'shadow-md');
                btn.classList.add('bg-white', 'dark:bg-[#121216]', 'text-slate-700', 'dark:text-zinc-300');
            }});
            const activeBtn = document.getElementById('fleet-btn-' + viewId);
            if (activeBtn) {{
                activeBtn.classList.add('bg-blue-600', 'text-white', 'shadow-md');
                activeBtn.classList.remove('bg-white', 'dark:bg-[#121216]', 'text-slate-700', 'dark:text-zinc-300');
            }}

            const subviews = ['trips', 'salespersons', 'payments', 'trucks', 'drivers', 'approvals', 'ledger'];
            subviews.forEach(sv => {{
                const el = document.getElementById('fleet-section-' + sv);
                if (el) {{
                    if (viewId === 'all' || viewId === sv) {{
                        el.style.display = 'block';
                    }} else {{
                        el.style.display = 'none';
                    }}
                }}
            }});
        }}

        function filterByITAdmin(adminName) {{
            const adminFilter = document.getElementById('it-admin-filter');
            if (adminFilter) {{
                adminFilter.value = adminName;
            }}
            itPage = 1;
            filterITTable(false);
            const tableCard = document.getElementById('it-table-card');
            if (tableCard) {{
                tableCard.scrollIntoView({{ behavior: 'smooth', block: 'start' }});
            }}
            showToast(adminName === 'ALL' ? 'Showing all technician tickets' : `Filtered tickets for ${{adminName}}`);
        }}

        function toggleTheme() {{
            const isDark = document.documentElement.classList.toggle('dark');
            localStorage.setItem('tagoneswa_theme', isDark ? 'dark' : 'light');
            updateThemeUI(isDark);
        }}

        function updateThemeUI(isDark) {{
            document.querySelectorAll('.theme-toggle-icon').forEach(el => {{
                el.textContent = isDark ? '☀️' : '🌙';
            }});
            document.querySelectorAll('.theme-toggle-label').forEach(el => {{
                el.textContent = isDark ? 'Light' : 'Dark';
            }});
        }}

        // Sync initial theme UI state
        updateThemeUI(document.documentElement.classList.contains('dark'));

        function showToast(msg, icon = '✅') {{
            const toast = document.getElementById('toast');
            document.getElementById('toastMsg').textContent = msg;
            document.getElementById('toastIcon').textContent = icon;
            toast.classList.remove('translate-y-20', 'opacity-0');
            toast.classList.add('translate-y-0', 'opacity-100');
            setTimeout(() => {{
                toast.classList.remove('translate-y-0', 'opacity-100');
                toast.classList.add('translate-y-20', 'opacity-0');
            }}, 2500);
        }}

        function switchDomain(domain) {{
            const allowed = (cachedData && cachedData.user && cachedData.user.allowed_domains) || initialAllowedDomains;
            if (!allowed.includes(domain)) {{
                domain = allowed[0] || initialDefaultTab;
            }}

            document.querySelectorAll('.tab-btn').forEach(btn => btn.classList.remove('active'));
            document.querySelectorAll('.domain-view').forEach(view => {{
                view.classList.remove('active');
                view.style.display = 'none';
            }});

            const targetBtn = document.getElementById('btn-tab-' + domain);
            const targetView = document.getElementById('view-' + domain);
            if (targetBtn) targetBtn.classList.add('active');
            if (targetView) {{
                targetView.classList.add('active');
                targetView.style.display = 'block';
                window.location.hash = domain;
            }}
        }}

        async function manualRefresh() {{
            if (isRefreshing) return;
            isRefreshing = true;

            const mIcon = document.getElementById('mobileRefreshIcon');
            const dIcon = document.getElementById('desktopRefreshIcon');
            if (mIcon) mIcon.classList.add('spinning');
            if (dIcon) dIcon.classList.add('spinning');

            try {{
                await fetchDashboard();
                showToast('Live dashboard refreshed!');
            }} catch (err) {{
                showToast('Failed to refresh data', '⚠️');
            }} finally {{
                setTimeout(() => {{
                    if (mIcon) mIcon.classList.remove('spinning');
                    if (dIcon) dIcon.classList.remove('spinning');
                    isRefreshing = false;
                }}, 600);
            }}
        }}

        async function handleLogout() {{
            try {{
                await fetch('/api/logout', {{ method: 'POST' }});
            }} catch (e) {{}}
            window.location.href = '/login';
        }}

        async function fetchDashboard() {{
            try {{
                const res = await fetch('/api/dashboard/data');
                if (res.status === 401) {{
                    window.location.href = '/login';
                    return;
                }}
                const data = await res.json();
                cachedData = data;

                if (data.user) {{
                    const uName = document.getElementById('userDisplayName');
                    if (uName) uName.textContent = data.user.name;
                    const uRole = document.getElementById('userRoleBadge');
                    if (uRole) uRole.innerHTML = `<span class="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse"></span> ${{data.user.role.replace('_', ' ')}}`;
                }}

                if (data.master_kpis) renderMasterKPIs(data.master_kpis);
                if (data.it) renderIT(data.it);
                if (data.projects) renderProjects(data.projects);
                if (data.logistics) renderLogistics(data.logistics);
                if (data.fleet) renderFleet(data.fleet);

                const allowed = (data.user && data.user.allowed_domains) || initialAllowedDomains;
                let hash = window.location.hash.replace('#', '');
                if (!allowed.includes(hash)) {{
                    hash = allowed[0] || initialDefaultTab;
                }}
                switchDomain(hash);
            }} catch (err) {{
                console.error('Error loading dashboard:', err);
            }}
        }}

        function renderIT(it) {{
            if (!it) return;
            document.getElementById('it-stat-total').textContent = it.stats.total;
            document.getElementById('it-stat-active').textContent = it.stats.open + it.stats.in_progress;
            document.getElementById('it-stat-resolved').textContent = it.stats.resolved + it.stats.closed;
            document.getElementById('it-stat-avg-time').textContent = it.stats.avg_resolution;

            // Render IT Admin SLA Cards with click-to-filter
            const adminContainer = document.getElementById('it-admin-cards');
            if (adminContainer && it.admins) {{
                adminContainer.innerHTML = it.admins.map(a => `
                    <div onclick="filterByITAdmin('${{a.name}}')" class="bg-slate-50 dark:bg-[#0f0f13] border border-slate-200 dark:border-zinc-800 rounded-xl p-3.5 sm:p-4 flex items-center justify-between shadow-xs hover:border-blue-500 dark:hover:border-blue-500/60 transition cursor-pointer hover:shadow-md group">
                        <div>
                            <div class="font-extrabold text-slate-900 dark:text-zinc-100 text-xs sm:text-sm group-hover:text-blue-600 dark:group-hover:text-blue-400 transition flex items-center gap-1.5">
                                <span>${{a.name}}</span>
                                <span class="text-[10px] text-blue-500 opacity-0 group-hover:opacity-100 transition font-semibold">🔍 Filter</span>
                            </div>
                            <div class="text-[10px] sm:text-[11px] text-slate-500 dark:text-zinc-400 font-mono">+${{a.phone}}</div>
                            <div class="mt-2 flex items-center gap-1.5">
                                <span class="bg-amber-50 dark:bg-amber-500/10 text-amber-700 dark:text-amber-300 border border-amber-200 dark:border-amber-500/30 text-[10px] font-bold px-2 py-0.5 rounded">${{a.pending}} Pending</span>
                                <span class="bg-emerald-50 dark:bg-emerald-500/10 text-emerald-700 dark:text-emerald-300 border border-emerald-200 dark:border-emerald-500/30 text-[10px] font-bold px-2 py-0.5 rounded">${{a.resolved}} Solved</span>
                            </div>
                        </div>
                        <div class="text-right">
                            <div class="text-sm sm:text-base font-extrabold text-blue-600 dark:text-blue-400 font-mono">${{a.sla_pct}}% SLA</div>
                            <div class="text-[10px] sm:text-[11px] text-slate-500 dark:text-zinc-400 font-medium">Avg: ${{a.avg_time}}</div>
                        </div>
                    </div>
                `).join('');
            }}

            // Populate Admin Filter
            const adminFilter = document.getElementById('it-admin-filter');
            if (adminFilter && it.records) {{
                const currentSelected = adminFilter.value;
                const adminNames = [...new Set(it.records.map(r => r.assigned_admin))].filter(Boolean);
                adminFilter.innerHTML = '<option value="ALL">All Support Admins</option>' + adminNames.map(name => `
                    <option value="${{name}}" ${{currentSelected === name ? 'selected' : ''}}>${{name}}</option>
                `).join('');
            }}

            // Render Category Issue Tree
            const treeContainer = document.getElementById('it-category-tree');
            if (treeContainer) {{
                if (it.category_tree && it.category_tree.length > 0) {{
                    treeContainer.innerHTML = it.category_tree.map(cat => `
                        <div class="border border-slate-200 dark:border-slate-800 rounded-xl overflow-hidden bg-slate-50/50 dark:bg-[#11192e]/40">
                            <div class="p-3 sm:p-3.5 bg-slate-100/80 dark:bg-[#15203b] font-extrabold text-xs text-slate-900 dark:text-white flex items-center justify-between">
                                <span>📁 ${{cat.category_name}}</span>
                                <span class="bg-blue-100 dark:bg-blue-950/80 text-blue-800 dark:text-blue-300 px-2 py-0.5 rounded-full text-[10px] font-bold">${{cat.count}} tickets</span>
                            </div>
                            <div class="p-3 space-y-2 text-xs">
                                ${{cat.subcategories.map(sub => `
                                    <div class="pl-2.5 sm:pl-3 border-l-2 border-slate-300 dark:border-slate-700">
                                        <div class="font-bold text-slate-700 dark:text-slate-300 flex items-center justify-between text-xs">
                                            <span>↳ ${{sub.subcategory_name}}</span>
                                            <span class="text-slate-400 dark:text-slate-500 font-medium text-[11px]">${{sub.count}} logs</span>
                                        </div>
                                        <div class="pl-2.5 sm:pl-3 mt-1 space-y-0.5 text-[11px] text-slate-500 dark:text-slate-400">
                                            ${{sub.issues.map(iss => `
                                                <div class="flex items-center justify-between py-0.5">
                                                    <span>• ${{iss.issue_name}}</span>
                                                    <span class="font-mono text-slate-600 dark:text-slate-300 font-bold">${{iss.count}}</span>
                                                </div>
                                            `).join('')}}
                                        </div>
                                    </div>
                                `).join('')}}
                            </div>
                        </div>
                    `).join('');
                }} else {{
                    treeContainer.innerHTML = '<div class="text-xs text-slate-400 dark:text-slate-500 p-3">No category issues logged yet.</div>';
                }}
            }}

            filterITTable(false);
        }}

        function filterITTable(resetPage = false) {{
            if (!cachedData || !cachedData.it) return;
            if (resetPage) itPage = 1;

            const q = document.getElementById('it-search').value.toLowerCase().trim();
            const statusFilter = document.getElementById('it-status-filter').value;
            const adminFilter = document.getElementById('it-admin-filter').value;

            let records = cachedData.it.records.filter(r => {{
                const matchesQ = !q || r.ticket_number.toLowerCase().includes(q) ||
                                 r.employee_name.toLowerCase().includes(q) ||
                                 r.issue.toLowerCase().includes(q) ||
                                 r.description.toLowerCase().includes(q) ||
                                 r.category.toLowerCase().includes(q);
                const matchesStatus = statusFilter === 'ALL' || r.status === statusFilter;
                const matchesAdmin = adminFilter === 'ALL' || r.assigned_admin === adminFilter;
                return matchesQ && matchesStatus && matchesAdmin;
            }});

            // Enforce newest tickets first (descending order by ticket_id)
            records.sort((a, b) => (b.ticket_id || 0) - (a.ticket_id || 0));

            // Update Dynamic Count Badge
            document.getElementById('it-count-badge').textContent = `Showing ${{records.length}} of ${{cachedData.it.records.length}} tickets`;

            // Pagination Slicing (15 per page)
            const totalPages = Math.max(1, Math.ceil(records.length / itPageSize));
            if (itPage > totalPages) itPage = totalPages;
            const startIndex = (itPage - 1) * itPageSize;
            const pagedRecords = records.slice(startIndex, startIndex + itPageSize);

            const tbody = document.getElementById('it-table-body');
            if (tbody) {{
                if (records.length === 0) {{
                    tbody.innerHTML = '<tr><td colspan="8" class="px-4 py-6 text-center text-slate-400 dark:text-zinc-500 font-medium">No matching IT support tickets found.</td></tr>';
                }} else {{
                    tbody.innerHTML = pagedRecords.map(r => {{
                        let statusBadge = 'bg-amber-500/10 text-amber-700 dark:text-amber-300 border-amber-200 dark:border-amber-500/30';
                        let statusDot = 'bg-amber-500';
                        if (r.status === 'Resolved' || r.status === 'Closed') {{
                            statusBadge = 'bg-emerald-500/10 text-emerald-700 dark:text-emerald-300 border-emerald-200 dark:border-emerald-500/30';
                            statusDot = 'bg-emerald-500';
                        }} else if (r.status === 'In Progress') {{
                            statusBadge = 'bg-blue-500/10 text-blue-700 dark:text-blue-300 border-blue-200 dark:border-blue-500/30';
                            statusDot = 'bg-blue-500 animate-pulse';
                        }}

                        let pBadge = 'bg-slate-100 dark:bg-[#121216] text-slate-700 dark:text-zinc-300 border border-slate-200 dark:border-zinc-800';
                        if (r.priority === 'Urgent') pBadge = 'bg-rose-500/10 text-rose-700 dark:text-rose-400 border border-rose-200 dark:border-rose-500/30 font-bold';
                        else if (r.priority === 'High') pBadge = 'bg-amber-500/10 text-amber-700 dark:text-amber-400 border border-amber-200 dark:border-amber-500/30 font-bold';

                        return `
                            <tr class="hover:bg-slate-50/80 dark:hover:bg-[#121218] transition">
                                <td class="px-4 sm:px-5 py-3 sm:py-3.5 font-mono font-bold text-blue-600 dark:text-blue-400 whitespace-nowrap">${{r.ticket_number}}</td>
                                <td class="px-4 sm:px-5 py-3 sm:py-3.5 whitespace-nowrap"><strong class="text-slate-900 dark:text-zinc-100">${{r.employee_name}}</strong><br><small class="text-slate-400 dark:text-zinc-500 font-mono">+${{r.employee_phone}}</small></td>
                                <td class="px-4 sm:px-5 py-3 sm:py-3.5 text-slate-700 dark:text-zinc-300 whitespace-nowrap">${{r.department}}<br><small class="text-slate-500 dark:text-zinc-400 font-medium">📍 ${{r.location}}</small></td>
                                <td class="px-4 sm:px-5 py-3 sm:py-3.5"><strong class="text-slate-900 dark:text-zinc-100">${{r.category}}</strong> <span class="text-slate-400">➔</span> ${{r.subcategory}}<br><small class="text-slate-500 dark:text-zinc-400">${{r.issue}}</small></td>
                                <td class="px-4 sm:px-5 py-3 sm:py-3.5 whitespace-nowrap"><span class="px-2 py-0.5 rounded text-[10px] ${{pBadge}}">${{r.priority}}</span></td>
                                <td class="px-4 sm:px-5 py-3 sm:py-3.5 whitespace-nowrap">
                                    <span class="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md text-[10px] font-bold border ${{statusBadge}} whitespace-nowrap">
                                        <span class="w-1.5 h-1.5 rounded-full ${{statusDot}}"></span>
                                        ${{r.status}}
                                    </span>
                                </td>
                                <td class="px-4 sm:px-5 py-3 sm:py-3.5 font-medium text-slate-800 dark:text-zinc-200 whitespace-nowrap">${{r.assigned_admin}}</td>
                                <td class="px-4 sm:px-5 py-3 sm:py-3.5 font-mono font-bold text-slate-900 dark:text-zinc-100 whitespace-nowrap">${{r.resolution_time}}</td>
                            </tr>
                        `;
                    }}).join('');
                }}
            }}

            renderPaginationControls('it-pagination-info', 'it-pagination-controls', itPage, records.length, itPageSize, 'changeITPage');
        }}

        function renderProjects(proj) {{
            if (!proj) return;
            document.getElementById('proj-stat-total').textContent = proj.stats.total;
            document.getElementById('proj-stat-active').textContent = proj.stats.open + proj.stats.in_progress;
            document.getElementById('proj-stat-completed').textContent = proj.stats.resolved + proj.stats.closed;
            document.getElementById('proj-stat-locations').textContent = proj.stats.locations_count;

            // Populate Location & Admin Filter
            const locFilter = document.getElementById('proj-loc-filter');
            if (locFilter && proj.records) {{
                const currentLoc = locFilter.value;
                const locations = [...new Set(proj.records.map(r => r.location))].filter(Boolean);
                locFilter.innerHTML = '<option value="ALL">All Branches & Yards</option>' + locations.map(loc => `
                    <option value="${{loc}}" ${{currentLoc === loc ? 'selected' : ''}}>${{loc}}</option>
                `).join('');
            }}

            const adminFilter = document.getElementById('proj-admin-filter');
            if (adminFilter && proj.records) {{
                const currentAdmin = adminFilter.value;
                const admins = [...new Set(proj.records.map(r => r.assigned_admin))].filter(Boolean);
                adminFilter.innerHTML = '<option value="ALL">All Project Leads</option>' + admins.map(a => `
                    <option value="${{a}}" ${{currentAdmin === a ? 'selected' : ''}}>${{a}}</option>
                `).join('');
            }}

            filterProjectsTable(false);
        }}

        function filterProjectsTable(resetPage = false) {{
            if (!cachedData || !cachedData.projects) return;
            if (resetPage) projPage = 1;

            const q = document.getElementById('proj-search').value.toLowerCase().trim();
            const locFilter = document.getElementById('proj-loc-filter').value;
            const adminFilter = document.getElementById('proj-admin-filter').value;
            const statusFilter = document.getElementById('proj-status-filter').value;

            let records = cachedData.projects.records.filter(r => {{
                const matchesQ = !q || r.ticket_number.toLowerCase().includes(q) ||
                                 r.location.toLowerCase().includes(q) ||
                                 r.description.toLowerCase().includes(q) ||
                                 r.category.toLowerCase().includes(q);
                const matchesLoc = locFilter === 'ALL' || r.location === locFilter;
                const matchesAdmin = adminFilter === 'ALL' || r.assigned_admin === adminFilter;
                const matchesStatus = statusFilter === 'ALL' || r.status === statusFilter;
                return matchesQ && matchesLoc && matchesAdmin && matchesStatus;
            }});

            // Enforce newest tickets first (descending order by ticket_id)
            records.sort((a, b) => (b.ticket_id || 0) - (a.ticket_id || 0));

            document.getElementById('proj-count-badge').textContent = `Showing ${{records.length}} of ${{cachedData.projects.records.length}} tickets`;

            // Pagination Slicing (15 per page)
            const totalPages = Math.max(1, Math.ceil(records.length / projPageSize));
            if (projPage > totalPages) projPage = totalPages;
            const startIndex = (projPage - 1) * projPageSize;
            const pagedRecords = records.slice(startIndex, startIndex + projPageSize);

            const tbody = document.getElementById('proj-table-body');
            if (tbody) {{
                if (records.length === 0) {{
                    tbody.innerHTML = '<tr><td colspan="7" class="px-4 py-6 text-center text-slate-400 dark:text-zinc-500 font-medium">No matching project tickets found.</td></tr>';
                }} else {{
                    tbody.innerHTML = pagedRecords.map(r => {{
                        let statusBadge = 'bg-amber-500/10 text-amber-700 dark:text-amber-300 border-amber-200 dark:border-amber-500/30';
                        let statusDot = 'bg-amber-500';
                        if (r.status === 'Resolved' || r.status === 'Closed') {{
                            statusBadge = 'bg-emerald-500/10 text-emerald-700 dark:text-emerald-300 border-emerald-200 dark:border-emerald-500/30';
                            statusDot = 'bg-emerald-500';
                        }} else if (r.status === 'In Progress') {{
                            statusBadge = 'bg-blue-500/10 text-blue-700 dark:text-blue-300 border-blue-200 dark:border-blue-500/30';
                            statusDot = 'bg-blue-500 animate-pulse';
                        }}

                        return `
                            <tr class="hover:bg-slate-50/80 dark:hover:bg-[#121218] transition">
                                <td class="px-4 sm:px-5 py-3 sm:py-3.5 font-mono font-bold text-blue-600 dark:text-blue-400 whitespace-nowrap">${{r.ticket_number}}</td>
                                <td class="px-4 sm:px-5 py-3 sm:py-3.5 whitespace-nowrap"><strong class="text-slate-900 dark:text-zinc-100">${{r.employee_name}}</strong><br><small class="text-slate-400 dark:text-zinc-500 font-mono">+${{r.employee_phone}}</small></td>
                                <td class="px-4 sm:px-5 py-3 sm:py-3.5 font-bold text-slate-800 dark:text-zinc-200 whitespace-nowrap">📍 ${{r.location}}</td>
                                <td class="px-4 sm:px-5 py-3 sm:py-3.5"><strong class="text-slate-900 dark:text-zinc-100">${{r.category}}</strong><br><small class="text-slate-500 dark:text-zinc-400">${{r.description}}</small></td>
                                <td class="px-4 sm:px-5 py-3 sm:py-3.5 whitespace-nowrap">
                                    <span class="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md text-[10px] font-bold border ${{statusBadge}} whitespace-nowrap">
                                        <span class="w-1.5 h-1.5 rounded-full ${{statusDot}}"></span>
                                        ${{r.status}}
                                    </span>
                                </td>
                                <td class="px-4 sm:px-5 py-3 sm:py-3.5 font-medium text-slate-800 dark:text-zinc-200 whitespace-nowrap">${{r.assigned_admin}}</td>
                                <td class="px-4 sm:px-5 py-3 sm:py-3.5 text-slate-500 dark:text-zinc-400 font-mono text-[11px] whitespace-nowrap">${{r.created_at}}</td>
                            </tr>
                        `;
                    }}).join('');
                }}
            }}

            renderPaginationControls('proj-pagination-info', 'proj-pagination-controls', projPage, records.length, projPageSize, 'changeProjPage');
        }}

        function renderLogistics(log) {{
            if (!log) return;
            document.getElementById('ws-stat-fleet').textContent = log.fleet_count || 39;
            document.getElementById('ws-stat-review').textContent = log.stats.under_review;
            document.getElementById('ws-stat-floor').textContent = log.stats.in_workshop;
            document.getElementById('ws-stat-parts').textContent = log.stats.awaiting_parts;
            document.getElementById('ws-stat-qc').textContent = log.stats.awaiting_qc;

            // Populate Mechanics Filter
            const mechFilter = document.getElementById('ws-mech-filter');
            if (mechFilter && log.records) {{
                const currentMech = mechFilter.value;
                const mechs = [...new Set(log.records.map(r => r.assigned_mechanic))].filter(Boolean);
                mechFilter.innerHTML = '<option value="ALL">All Mechanics</option>' + mechs.map(m => `
                    <option value="${{m}}" ${{currentMech === m ? 'selected' : ''}}>${{m}}</option>
                `).join('');
            }}

            filterFleetTable(false);
        }}

        function filterFleetTable(resetPage = false) {{
            if (!cachedData || !cachedData.logistics) return;
            if (resetPage) wsPage = 1;

            const q = document.getElementById('ws-search').value.toLowerCase().trim();
            const statusFilter = document.getElementById('ws-status-filter').value;
            const mechFilter = document.getElementById('ws-mech-filter').value;

            let records = cachedData.logistics.records.filter(r => {{
                const matchesQ = !q || r.ticket_number.toLowerCase().includes(q) ||
                                 r.truck_number.toLowerCase().includes(q) ||
                                 r.plate_number.toLowerCase().includes(q) ||
                                 r.description.toLowerCase().includes(q) ||
                                 r.category.toLowerCase().includes(q);
                const matchesStatus = statusFilter === 'ALL' || r.status === statusFilter;
                const matchesMech = mechFilter === 'ALL' || r.assigned_mechanic === mechFilter;
                return matchesQ && matchesStatus && matchesMech;
            }});

            // Enforce newest tickets first (descending order by ticket_id)
            records.sort((a, b) => (b.ticket_id || 0) - (a.ticket_id || 0));

            document.getElementById('ws-count-badge').textContent = `Showing ${{records.length}} of ${{cachedData.logistics.records.length}} vehicles`;

            // Pagination Slicing (15 per page)
            const totalPages = Math.max(1, Math.ceil(records.length / wsPageSize));
            if (wsPage > totalPages) wsPage = totalPages;
            const startIndex = (wsPage - 1) * wsPageSize;
            const pagedRecords = records.slice(startIndex, startIndex + wsPageSize);

            const tbody = document.getElementById('ws-table-body');
            if (tbody) {{
                if (records.length === 0) {{
                    tbody.innerHTML = '<tr><td colspan="9" class="px-4 py-6 text-center text-slate-400 dark:text-zinc-500 font-medium">No matching workshop records found.</td></tr>';
                }} else {{
                    tbody.innerHTML = pagedRecords.map(r => {{
                        let statusBadge = 'bg-blue-500/10 text-blue-700 dark:text-blue-300 border-blue-200 dark:border-blue-500/30';
                        let statusDot = 'bg-blue-500';
                        const statusRaw = r.status || '';
                        const statusLabel = statusRaw.replace(/_/g, ' ');

                        if (statusRaw === 'UNDER_REVIEW') {{
                            statusBadge = 'bg-amber-500/10 text-amber-700 dark:text-amber-300 border-amber-200 dark:border-amber-500/30';
                            statusDot = 'bg-amber-500';
                        }} else if (statusRaw === 'CLOSED') {{
                            statusBadge = 'bg-zinc-500/10 text-zinc-700 dark:text-zinc-300 border-zinc-200 dark:border-zinc-700';
                            statusDot = 'bg-zinc-400';
                        }} else if (statusRaw === 'REWORK_REQUIRED') {{
                            statusBadge = 'bg-rose-500/10 text-rose-700 dark:text-rose-300 border-rose-200 dark:border-rose-500/30';
                            statusDot = 'bg-rose-500 animate-pulse';
                        }} else if (statusRaw === 'AWAITING_TEST') {{
                            statusBadge = 'bg-emerald-500/10 text-emerald-700 dark:text-emerald-300 border-emerald-200 dark:border-emerald-500/30';
                            statusDot = 'bg-emerald-500';
                        }}

                        let qcResult = r.qc_result || 'Pending QC';
                        let qcClass = 'text-zinc-500 dark:text-zinc-400';
                        if (qcResult.toUpperCase().includes('PASS')) {{
                            qcClass = 'text-emerald-600 dark:text-emerald-400 font-bold';
                        }} else if (qcResult.toUpperCase().includes('FAIL') || qcResult.toUpperCase().includes('REWORK')) {{
                            qcClass = 'text-rose-600 dark:text-rose-400 font-bold';
                        }} else if (qcResult.toUpperCase().includes('PEND')) {{
                            qcClass = 'text-amber-600 dark:text-amber-400 font-medium';
                        }}

                        return `
                            <tr class="hover:bg-slate-50/80 dark:hover:bg-[#121218] transition">
                                <td class="px-4 sm:px-5 py-3 sm:py-3.5 font-mono font-bold text-blue-600 dark:text-blue-400 whitespace-nowrap">${{r.ticket_number}}</td>
                                <td class="px-4 sm:px-5 py-3 sm:py-3.5 whitespace-nowrap"><strong class="text-slate-900 dark:text-zinc-100">Truck #${{r.truck_number}}</strong><br><small class="text-slate-400 dark:text-zinc-500 font-mono">${{r.plate_number}}</small></td>
                                <td class="px-4 sm:px-5 py-3 sm:py-3.5 font-medium text-slate-800 dark:text-zinc-200 whitespace-nowrap">${{r.truck_model}}</td>
                                <td class="px-4 sm:px-5 py-3 sm:py-3.5"><strong class="text-slate-900 dark:text-zinc-100">${{r.category}}</strong><br><small class="text-slate-500 dark:text-zinc-400">${{r.description.substring(0, 45)}}...</small></td>
                                <td class="px-4 sm:px-5 py-3 sm:py-3.5 text-slate-700 dark:text-zinc-300 whitespace-nowrap">${{r.logged_by}}</td>
                                <td class="px-4 sm:px-5 py-3 sm:py-3.5 whitespace-nowrap"><strong class="text-slate-900 dark:text-zinc-100">${{r.assigned_mechanic}}</strong><br><small class="text-blue-600 dark:text-blue-400 font-semibold">⏱️ ETA: ${{r.eta}}</small></td>
                                <td class="px-4 sm:px-5 py-3 sm:py-3.5 whitespace-nowrap"><small class="bg-amber-50 dark:bg-amber-500/10 text-amber-800 dark:text-amber-300 border border-amber-200 dark:border-amber-500/30 px-2 py-0.5 rounded font-medium">📦 ${{r.parts_status}}</small></td>
                                <td class="px-4 sm:px-5 py-3 sm:py-3.5 font-bold font-mono text-slate-900 dark:text-zinc-100 whitespace-nowrap">${{r.costing}}</td>
                                <td class="px-4 sm:px-5 py-3 sm:py-3.5 whitespace-nowrap">
                                    <div class="flex flex-col items-start gap-1">
                                        <span class="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md text-[10px] font-bold border ${{statusBadge}} whitespace-nowrap">
                                            <span class="w-1.5 h-1.5 rounded-full ${{statusDot}}"></span>
                                            ${{statusLabel}}
                                        </span>
                                        <span class="inline-flex items-center gap-1 text-[10px] font-mono text-zinc-500 dark:text-zinc-400 bg-slate-100 dark:bg-[#121216] px-2 py-0.5 rounded border border-slate-200 dark:border-zinc-800 whitespace-nowrap">
                                            QC: <strong class="${{qcClass}}">${{qcResult}}</strong>
                                        </span>
                                    </div>
                                </td>
                            </tr>
                        `;
                    }}).join('');
                }}
            }}

            renderPaginationControls('ws-pagination-info', 'ws-pagination-controls', wsPage, records.length, wsPageSize, 'changeWSPage');
        }}

        let currentAuditTimeframe = 'ALL';

        function renderMasterKPIs(kpis) {{
            if (!kpis) return;
            const elActive = document.getElementById('master-active-ops');
            if (elActive) elActive.textContent = kpis.active_operations;
            const elRate = document.getElementById('master-res-rate');
            if (elRate) elRate.textContent = kpis.resolution_rate_pct + '%';
            const elRev = document.getElementById('master-transport-revenue');
            if (elRev) elRev.textContent = '$' + Number(kpis.transport_revenue).toFixed(2);
            const elBacklog = document.getElementById('master-financial-backlog');
            if (elBacklog) elBacklog.textContent = '$' + Number(kpis.total_financial_backlog).toFixed(2);
        }}

        function setAuditTimeframe(tf) {{
            currentAuditTimeframe = tf;
            ledgerPage = 1;
            document.querySelectorAll('.audit-tf-btn').forEach(btn => {{
                btn.classList.remove('bg-blue-600', 'text-white');
                btn.classList.add('text-slate-600', 'dark:text-zinc-300', 'hover:text-slate-900', 'dark:hover:text-white');
            }});
            const activeBtn = document.getElementById('timeframe-btn-' + tf);
            if (activeBtn) {{
                activeBtn.classList.add('bg-blue-600', 'text-white');
                activeBtn.classList.remove('text-slate-600', 'dark:text-zinc-300', 'hover:text-slate-900', 'dark:hover:text-white');
            }}
            if (cachedData && cachedData.fleet) {{
                filterLedgerTable(true);
            }}
        }}

        function renderFleet(fleet) {{
            if (!fleet) return;
            // 1. Top Stats Cards
            document.getElementById('fleet-stat-trips').textContent = fleet.stats.total_trips;
            document.getElementById('fleet-stat-sales-val').textContent = '$' + Number(fleet.stats.total_sales_value).toLocaleString('en-US', {{minimumFractionDigits: 2, maximumFractionDigits: 2}}) + ' ERP Sales';
            document.getElementById('fleet-stat-approved').textContent = fleet.stats.approved_trips;
            document.getElementById('fleet-stat-shortfalls').textContent = fleet.stats.shortfall_trips;
            document.getElementById('fleet-stat-transport').textContent = '$' + Number(fleet.stats.total_transport_charges).toFixed(2);
            document.getElementById('fleet-stat-backlog').textContent = '$' + Number(fleet.stats.total_outstanding_backlog).toFixed(2);
            document.getElementById('fleet-total-pending-pill').textContent = '$' + Number(fleet.stats.total_outstanding_backlog).toFixed(2);

            // 2. Salesperson Pending Balance & Audit Cards
            const spCardsContainer = document.getElementById('fleet-salesperson-cards');
            if (spCardsContainer && fleet.salespersons) {{
                if (fleet.salespersons.length === 0) {{
                    spCardsContainer.innerHTML = '<div class="text-xs text-slate-400 dark:text-zinc-500 p-3 col-span-full">No salesperson ledger records yet.</div>';
                }} else {{
                    spCardsContainer.innerHTML = fleet.salespersons.map(sp => {{
                        let badgeClass = 'bg-emerald-500/10 text-emerald-700 dark:text-emerald-300 border-emerald-200 dark:border-emerald-500/30';
                        let badgeText = '🟢 Cleared / Healthy';
                        if (sp.risk_level === 'HIGH_ALERT') {{
                            badgeClass = 'bg-rose-500/10 text-rose-700 dark:text-rose-300 border-rose-200 dark:border-rose-500/30 font-bold';
                            badgeText = '🔴 High Debt Alert';
                        }} else if (sp.risk_level === 'ACTIVE_PENDING') {{
                            badgeClass = 'bg-amber-500/10 text-amber-700 dark:text-amber-300 border-amber-200 dark:border-amber-500/30 font-semibold';
                            badgeText = '🟡 Pending Recovery';
                        }}

                        return `
                            <div class="bg-slate-50 dark:bg-[#0f0f13] border border-slate-200 dark:border-zinc-800 rounded-xl p-4 flex flex-col justify-between hover:shadow-md transition">
                                <div>
                                    <div class="flex items-start justify-between gap-1">
                                        <div>
                                            <div class="font-extrabold text-slate-900 dark:text-zinc-100 text-sm">${{sp.name}}</div>
                                            <div class="text-[11px] text-slate-500 dark:text-zinc-400 font-mono">+${{sp.phone}}</div>
                                        </div>
                                        <span class="text-[10px] px-2 py-0.5 rounded-full border ${{badgeClass}} whitespace-nowrap">${{badgeText}}</span>
                                    </div>
                                    <div class="mt-3 bg-white dark:bg-[#121216] border border-slate-200 dark:border-zinc-800 rounded-lg p-2.5">
                                        <div class="text-[10px] uppercase font-bold text-slate-400 dark:text-zinc-500">Current Outstanding Debt</div>
                                        <div class="text-xl font-extrabold font-mono ${{sp.net_balance > 0 ? 'text-rose-600 dark:text-rose-400' : 'text-emerald-600 dark:text-emerald-400'}} mt-0.5">
                                            $${{sp.net_balance.toFixed(2)}}
                                        </div>
                                    </div>
                                </div>
                                <div class="mt-3 pt-2.5 border-t border-slate-200/80 dark:border-zinc-800/80 flex items-center justify-between text-[11px] text-slate-600 dark:text-zinc-400">
                                    <span>Accrued: <strong class="text-rose-600 dark:text-rose-400 font-mono">$${{sp.total_shortfalls.toFixed(2)}}</strong></span>
                                    <span>Recovered: <strong class="text-emerald-600 dark:text-emerald-400 font-mono">$${{sp.total_recovered.toFixed(2)}}</strong></span>
                                </div>
                                ${{sp.net_balance > 0 ? `
                                    <button onclick="openClearPaymentModal('${{sp.name}}', '${{sp.phone}}', ${{sp.net_balance}})" class="mt-3 w-full bg-emerald-600 hover:bg-emerald-700 text-white font-bold py-1.5 px-3 rounded-lg text-xs transition flex items-center justify-center gap-1 shadow-xs cursor-pointer">
                                        <span>💳</span> Clear Debt Settlement
                                    </button>
                                ` : ''}}
                            </div>
                        `;
                    }}).join('');
                }}
            }}

            // 3. Populate City Filter dropdown
            const cityFilter = document.getElementById('fleet-city-filter');
            if (cityFilter && fleet.cities) {{
                const curCity = cityFilter.value;
                cityFilter.innerHTML = '<option value="ALL">All Destination Cities</option>' + fleet.cities.map(c => `
                    <option value="${{c}}" ${{curCity === c ? 'selected' : ''}}>${{c}}</option>
                `).join('');
            }}

            // 4. Render all Subviews & Modals
            filterTripsTable(false);
            filterTrucksTable(false);
            filterDriversTable(false);
            filterPaymentsTable(false);
            filterLedgerTable(false);
            filterFleetApprovalsTable(false);
            populatePaySalespersonDropdown(fleet.salespersons);
            if (fleet.route_rules) renderModalCityRules(fleet.route_rules);
        }}

        function filterLedgerTable(resetPage = false) {{
            if (!cachedData || !cachedData.fleet || !cachedData.fleet.ledger) return;
            if (resetPage) ledgerPage = 1;

            const entries = cachedData.fleet.ledger;

            const todayStr = new Date().toISOString().substring(0, 10);
            const yesterdayObj = new Date();
            yesterdayObj.setDate(yesterdayObj.getDate() - 1);
            const yesterdayStr = yesterdayObj.toISOString().substring(0, 10);
            const sevenDaysAgo = new Date();
            sevenDaysAgo.setDate(sevenDaysAgo.getDate() - 7);

            let filtered = entries.filter(e => {{
                if (currentAuditTimeframe === 'TODAY') {{
                    return e.date_only === todayStr;
                }} else if (currentAuditTimeframe === 'YESTERDAY') {{
                    return e.date_only === yesterdayStr;
                }} else if (currentAuditTimeframe === 'WEEK') {{
                    return new Date(e.date_only) >= sevenDaysAgo;
                }}
                return true;
            }});

            // Calculate daily audit metrics
            let paidTotal = 0;
            let deferredTotal = 0;
            let recoveredTotal = 0;
            let alertCount = 0;

            filtered.forEach(e => {{
                if (e.is_recovery) {{
                    recoveredTotal += Math.abs(e.amount);
                }} else {{
                    deferredTotal += e.amount;
                }}
            }});

            // Count alerts across approvals matching current timeframe
            if (cachedData.fleet.records) {{
                cachedData.fleet.records.forEach(r => {{
                    let inTf = true;
                    if (currentAuditTimeframe === 'TODAY') inTf = (r.date_only === todayStr);
                    else if (currentAuditTimeframe === 'YESTERDAY') inTf = (r.date_only === yesterdayStr);
                    else if (currentAuditTimeframe === 'WEEK') inTf = (new Date(r.date_only) >= sevenDaysAgo);

                    if (inTf) {{
                        paidTotal += (r.amount_charged_to_customer || 0);
                        if (!r.is_clean) alertCount += r.audit_flags.length;
                    }}
                }});
            }}

            document.getElementById('audit-stat-customer-paid').textContent = '$' + paidTotal.toFixed(2);
            document.getElementById('audit-stat-deferred').textContent = '$' + deferredTotal.toFixed(2);
            document.getElementById('audit-stat-recovered').textContent = '$' + recoveredTotal.toFixed(2);
            const alertEl = document.getElementById('audit-stat-flags');
            const alertNote = document.getElementById('audit-stat-flags-note');
            alertEl.textContent = alertCount;
            if (alertCount > 0) {{
                alertEl.className = 'text-base sm:text-lg font-extrabold text-red-600 dark:text-red-400 font-mono mt-0.5';
                alertNote.innerHTML = '<span class="text-red-600 dark:text-red-400 font-bold">⚠️ Discrepancy Found</span>';
            }} else {{
                alertEl.className = 'text-base sm:text-lg font-extrabold text-emerald-600 dark:text-emerald-400 font-mono mt-0.5';
                alertNote.innerHTML = '<span class="text-emerald-600 dark:text-emerald-400 font-semibold">100% Math Match</span>';
            }}

            // Pagination Slicing (15 per page)
            const totalPages = Math.max(1, Math.ceil(filtered.length / ledgerPageSize));
            if (ledgerPage > totalPages) ledgerPage = totalPages;
            const startIndex = (ledgerPage - 1) * ledgerPageSize;
            const pagedRecords = filtered.slice(startIndex, startIndex + ledgerPageSize);

            const tbody = document.getElementById('fleet-ledger-table-body');
            if (tbody) {{
                if (filtered.length === 0) {{
                    tbody.innerHTML = '<tr><td colspan="6" class="px-4 py-6 text-center text-slate-400 dark:text-zinc-500 font-medium">No ledger transactions in this timeframe.</td></tr>';
                }} else {{
                    tbody.innerHTML = pagedRecords.map(e => {{
                        const isRec = e.is_recovery;
                        const amtClass = isRec ? 'text-emerald-600 dark:text-emerald-400 font-bold' : 'text-rose-600 dark:text-rose-400 font-bold';
                        const sign = isRec ? '-' : '+';
                        const typeBadge = isRec
                            ? '<span class="inline-flex items-center gap-1.5 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300 border border-emerald-200 dark:border-emerald-500/30 text-[10px] font-bold px-2 py-0.5 rounded whitespace-nowrap"><span class="w-1.5 h-1.5 rounded-full bg-emerald-500"></span>SURPLUS RECOVERY</span>'
                            : '<span class="inline-flex items-center gap-1.5 bg-amber-500/10 text-amber-700 dark:text-amber-300 border border-amber-200 dark:border-amber-500/30 text-[10px] font-bold px-2 py-0.5 rounded whitespace-nowrap"><span class="w-1.5 h-1.5 rounded-full bg-amber-500"></span>SHORTFALL DEFICIT</span>';

                        return `
                            <tr class="hover:bg-slate-50/80 dark:hover:bg-[#121218] transition">
                                <td class="px-4 sm:px-5 py-3 text-slate-500 dark:text-zinc-400 font-mono text-[11px] whitespace-nowrap">${{e.created_at}}</td>
                                <td class="px-4 sm:px-5 py-3 whitespace-nowrap"><strong class="text-slate-900 dark:text-zinc-100">${{e.salesperson_name}}</strong><br><small class="text-slate-400 dark:text-zinc-500 font-mono">+${{e.salesperson_phone}}</small></td>
                                <td class="px-4 sm:px-5 py-3 font-mono font-bold text-blue-600 dark:text-blue-400 whitespace-nowrap">${{e.trip_id}}</td>
                                <td class="px-4 sm:px-5 py-3 whitespace-nowrap">${{typeBadge}}</td>
                                <td class="px-4 sm:px-5 py-3 font-mono ${{amtClass}} whitespace-nowrap">${{sign}}$${{Math.abs(e.amount).toFixed(2)}}</td>
                                <td class="px-4 sm:px-5 py-3 text-slate-600 dark:text-zinc-300">${{e.notes || '--'}}</td>
                            </tr>
                        `;
                    }}).join('');
                }}
            }}

            renderPaginationControls('ledger-pagination-info', 'ledger-pagination-controls', ledgerPage, filtered.length, ledgerPageSize, 'changeLedgerPage');
        }}

        function filterFleetApprovalsTable(resetPage = false) {{
            if (!cachedData || !cachedData.fleet || !cachedData.fleet.records) return;
            if (resetPage) fleetPage = 1;

            const q = document.getElementById('fleet-search').value.toLowerCase().trim();
            const cityFilter = document.getElementById('fleet-city-filter').value;
            const statusFilter = document.getElementById('fleet-status-filter').value;

            let records = cachedData.fleet.records.filter(r => {{
                const matchesQ = !q || r.trip_id.toLowerCase().includes(q) ||
                                 r.salesperson_name.toLowerCase().includes(q) ||
                                 r.salesperson_phone.toLowerCase().includes(q) ||
                                 r.destination_city.toLowerCase().includes(q) ||
                                 r.route.toLowerCase().includes(q);
                const matchesCity = cityFilter === 'ALL' || r.destination_city === cityFilter;
                const matchesStatus = statusFilter === 'ALL' || r.status === statusFilter;
                return matchesQ && matchesCity && matchesStatus;
            }});

            // Enforce newest first
            records.sort((a, b) => (b.id || 0) - (a.id || 0));

            document.getElementById('fleet-count-badge').textContent = `Showing ${{records.length}} of ${{cachedData.fleet.records.length}} trips`;

            // Pagination Slicing (15 per page)
            const totalPages = Math.max(1, Math.ceil(records.length / fleetPageSize));
            if (fleetPage > totalPages) fleetPage = totalPages;
            const startIndex = (fleetPage - 1) * fleetPageSize;
            const pagedRecords = records.slice(startIndex, startIndex + fleetPageSize);

            const tbody = document.getElementById('fleet-approvals-table-body');
            if (tbody) {{
                if (records.length === 0) {{
                    tbody.innerHTML = '<tr><td colspan="9" class="px-4 py-6 text-center text-slate-400 dark:text-zinc-500 font-medium">No matching trip approvals found.</td></tr>';
                }} else {{
                    tbody.innerHTML = pagedRecords.map(r => {{
                        let statusBadge = 'bg-blue-500/10 text-blue-700 dark:text-blue-300 border-blue-200 dark:border-blue-500/30';
                        let statusDot = 'bg-blue-500';
                        if (r.status === 'APPROVED' || r.status === 'DISPATCHED') {{
                            statusBadge = 'bg-emerald-500/10 text-emerald-700 dark:text-emerald-300 border-emerald-200 dark:border-emerald-500/30';
                            statusDot = 'bg-emerald-500';
                        }} else if (r.status === 'SHORTFALL_RECORDED') {{
                            statusBadge = 'bg-amber-500/10 text-amber-700 dark:text-amber-300 border-amber-200 dark:border-amber-500/30';
                            statusDot = 'bg-amber-500';
                        }}

                        let auditBadge = '<span class="inline-flex items-center gap-1.5 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300 border border-emerald-200 dark:border-emerald-500/30 text-[10px] font-bold px-2 py-0.5 rounded whitespace-nowrap"><span class="w-1.5 h-1.5 rounded-full bg-emerald-500"></span>Verified Parity</span>';
                        if (!r.is_clean) {{
                            auditBadge = `<span class="inline-flex items-center gap-1.5 bg-red-500/10 text-red-700 dark:text-red-300 border border-red-200 dark:border-red-500/30 text-[10px] font-bold px-2 py-0.5 rounded whitespace-nowrap" title="${{r.audit_flags.join('; ')}}"><span class="w-1.5 h-1.5 rounded-full bg-rose-500 animate-pulse"></span>Audit Alert (${{r.audit_flags.length}})</span>`;
                        }}

                        return `
                            <tr class="hover:bg-slate-50/80 dark:hover:bg-[#121218] transition">
                                <td class="px-4 sm:px-5 py-3 sm:py-3.5 font-mono font-bold text-blue-600 dark:text-blue-400 whitespace-nowrap">${{r.trip_id}}</td>
                                <td class="px-4 sm:px-5 py-3 sm:py-3.5 whitespace-nowrap"><strong class="text-slate-900 dark:text-zinc-100">${{r.salesperson_name}}</strong><br><small class="text-slate-400 dark:text-zinc-500 font-mono">+${{r.salesperson_phone}}</small></td>
                                <td class="px-4 sm:px-5 py-3 sm:py-3.5 whitespace-nowrap"><span class="font-bold text-slate-800 dark:text-zinc-200">📍 ${{r.destination_city}}</span><br><small class="text-slate-500 dark:text-zinc-400">${{r.route}}</small></td>
                                <td class="px-4 sm:px-5 py-3 sm:py-3.5 font-mono whitespace-nowrap">
                                    <span class="font-bold ${{r.trip_sales_value >= r.required_minimum ? 'text-emerald-600 dark:text-emerald-400' : 'text-slate-900 dark:text-zinc-100'}}">$${{r.trip_sales_value.toFixed(2)}}</span>
                                    <br><small class="text-slate-400 dark:text-zinc-500">Min: $${{r.required_minimum.toFixed(2)}}</small>
                                </td>
                                <td class="px-4 sm:px-5 py-3 sm:py-3.5 font-mono whitespace-nowrap">
                                    ${{r.has_shortfall ? `<span class="text-rose-600 dark:text-rose-400 font-bold">-$${{r.shortfall.toFixed(2)}}</span><br><small class="text-indigo-600 dark:text-indigo-400 font-bold">Fee: $${{r.transport_charge.toFixed(2)}}</small>` : '<span class="text-emerald-600 dark:text-emerald-400 font-bold">Compliant (No Fee)</span>'}}
                                </td>
                                <td class="px-4 sm:px-5 py-3 sm:py-3.5 text-xs text-slate-700 dark:text-zinc-300 whitespace-nowrap">
                                    ${{r.has_shortfall ? `
                                        <span>Customer Paid: <strong class="text-emerald-700 dark:text-emerald-400 font-mono">$${{r.amount_charged_to_customer.toFixed(2)}}</strong></span><br>
                                        <span>Debt Added: <strong class="text-amber-700 dark:text-amber-400 font-mono">$${{r.pending_balance_recorded.toFixed(2)}}</strong></span>
                                    ` : '<span class="text-slate-400 dark:text-zinc-500">Direct Clearance</span>'}}
                                </td>
                                <td class="px-4 sm:px-5 py-3 sm:py-3.5 whitespace-nowrap">${{auditBadge}}</td>
                                <td class="px-4 sm:px-5 py-3 sm:py-3.5 whitespace-nowrap">
                                    <span class="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md text-[10px] font-bold border ${{statusBadge}} whitespace-nowrap">
                                        <span class="w-1.5 h-1.5 rounded-full ${{statusDot}}"></span>
                                        ${{r.status.replace(/_/g, ' ')}}
                                    </span>
                                </td>
                                <td class="px-4 sm:px-5 py-3 sm:py-3.5 text-slate-500 dark:text-zinc-400 text-[11px] font-mono whitespace-nowrap">${{r.created_at}}</td>
                            </tr>
                        `;
                    }}).join('');
                }}
            }}

            renderPaginationControls('fleet-pagination-info', 'fleet-pagination-controls', fleetPage, records.length, fleetPageSize, 'changeFleetPage');
        }}

        // =============================================================
        // SUBVIEW 1: 7-STAGE COMMERCIAL TRIPS PIPELINE
        // =============================================================
        function filterTripsTable(resetPage = false) {{
            if (!cachedData || !cachedData.fleet || !cachedData.fleet.trips) return;
            if (resetPage) tripsPage = 1;

            const q = (document.getElementById('trips-search')?.value || '').toLowerCase().trim();
            const stageFilter = document.getElementById('trips-stage-filter')?.value || 'ALL';

            let trips = cachedData.fleet.trips.filter(t => {{
                const matchesQ = !q || (t.trip_id && t.trip_id.toLowerCase().includes(q)) ||
                                 (t.salesperson_name && t.salesperson_name.toLowerCase().includes(q)) ||
                                 (t.salesperson_phone && t.salesperson_phone.toLowerCase().includes(q)) ||
                                 (t.destination_city && t.destination_city.toLowerCase().includes(q)) ||
                                 (t.truck_plate && t.truck_plate.toLowerCase().includes(q)) ||
                                 (t.driver_name && t.driver_name.toLowerCase().includes(q));
                
                let matchesStage = true;
                if (stageFilter !== 'ALL') {{
                    const st = (t.status || '').toUpperCase();
                    matchesStage = st.includes(stageFilter);
                }}
                return matchesQ && matchesStage;
            }});

            const badgeEl = document.getElementById('trips-count-badge');
            if (badgeEl) badgeEl.textContent = `Showing ${{trips.length}} of ${{cachedData.fleet.trips.length}} trips`;

            const totalPages = Math.max(1, Math.ceil(trips.length / tripsPageSize));
            if (tripsPage > totalPages) tripsPage = totalPages;
            const startIndex = (tripsPage - 1) * tripsPageSize;
            const pagedTrips = trips.slice(startIndex, startIndex + tripsPageSize);

            const tbody = document.getElementById('fleet-trips-table-body');
            if (tbody) {{
                if (trips.length === 0) {{
                    tbody.innerHTML = '<tr><td colspan="8" class="px-4 py-6 text-center text-slate-400 dark:text-zinc-500 font-medium">No matching trips found in pipeline.</td></tr>';
                }} else {{
                    tbody.innerHTML = pagedTrips.map(t => {{
                        const st = (t.status || '').toUpperCase();
                        let stageBadge = 'bg-blue-500/10 text-blue-700 dark:text-blue-300 border-blue-200 dark:border-blue-500/30';
                        let stageLabel = '📝 Stage 1: Quoted';

                        if (st.includes('APPROVED')) {{
                            stageBadge = 'bg-emerald-500/10 text-emerald-700 dark:text-emerald-300 border-emerald-200 dark:border-emerald-500/30';
                            stageLabel = '⚡ Stage 2: Approved';
                        }} else if (st.includes('VOUCHER') || st.includes('ALLOWANCE')) {{
                            stageBadge = 'bg-indigo-500/10 text-indigo-700 dark:text-indigo-300 border-indigo-200 dark:border-indigo-500/30';
                            stageLabel = '⛽ Stage 3: Voucher Issued';
                        }} else if (st.includes('LOADED') || st.includes('ODOMETER')) {{
                            stageBadge = 'bg-purple-500/10 text-purple-700 dark:text-purple-300 border-purple-200 dark:border-purple-500/30';
                            stageLabel = '📦 Stage 4: Loaded';
                        }} else if (st.includes('IN_TRANSIT') || st.includes('TRANSIT')) {{
                            stageBadge = 'bg-amber-500/10 text-amber-700 dark:text-amber-300 border-amber-200 dark:border-amber-500/30';
                            stageLabel = '🚛 Stage 5: In Transit';
                        }} else if (st.includes('OFFLOADED') || st.includes('POD')) {{
                            stageBadge = 'bg-teal-500/10 text-teal-700 dark:text-teal-300 border-teal-200 dark:border-teal-500/30';
                            stageLabel = '🏢 Stage 6: Offloaded';
                        }} else if (st.includes('SETTLED') || st.includes('CLOSED')) {{
                            stageBadge = 'bg-emerald-500/20 text-emerald-800 dark:text-emerald-200 border-emerald-300 dark:border-emerald-500/40';
                            stageLabel = '✅ Stage 7: Settled';
                        }}

                        return `
                            <tr class="hover:bg-slate-50/80 dark:hover:bg-[#121218] transition">
                                <td class="px-4 sm:px-5 py-3.5 font-mono font-bold text-blue-600 dark:text-blue-400 whitespace-nowrap">${{t.trip_id}}</td>
                                <td class="px-4 sm:px-5 py-3.5 whitespace-nowrap">
                                    <span class="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md text-[10px] font-bold border ${{stageBadge}} whitespace-nowrap">
                                        ${{stageLabel}}
                                    </span>
                                </td>
                                <td class="px-4 sm:px-5 py-3.5 whitespace-nowrap">
                                    <strong class="text-slate-900 dark:text-zinc-100">${{t.salesperson_name}}</strong><br>
                                    <small class="text-slate-400 dark:text-zinc-500 font-mono">+${{t.salesperson_phone}}</small>
                                </td>
                                <td class="px-4 sm:px-5 py-3.5 whitespace-nowrap">
                                    <span class="font-bold text-slate-800 dark:text-zinc-200">📍 ${{t.destination_city}}</span><br>
                                    <small class="text-slate-500 dark:text-zinc-400">${{t.route}}</small>
                                </td>
                                <td class="px-4 sm:px-5 py-3.5 whitespace-nowrap">
                                    <strong class="text-slate-900 dark:text-zinc-100">🚚 ${{t.truck_plate}}</strong><br>
                                    <small class="text-slate-500 dark:text-zinc-400">👤 ${{t.driver_name}}</small>
                                </td>
                                <td class="px-4 sm:px-5 py-3.5 whitespace-nowrap font-mono text-xs">
                                    <div>Allow: <strong class="text-slate-900 dark:text-zinc-100">$${{t.total_allowance.toFixed(2)}}</strong></div>
                                    <div>Transp: <strong class="text-indigo-600 dark:text-indigo-400">$${{t.transport_charge.toFixed(2)}}</strong></div>
                                </td>
                                <td class="px-4 sm:px-5 py-3.5 whitespace-nowrap text-[11px] text-slate-500 dark:text-zinc-400 font-mono">
                                    <div>Dep: ${{t.departed_at || '--'}}</div>
                                    <div>Ret: ${{t.returned_at || '--'}}</div>
                                </td>
                                <td class="px-4 sm:px-5 py-3.5 whitespace-nowrap font-mono text-xs">
                                    <span>${{t.start_odometer ? t.start_odometer + ' km' : '--'}} → ${{t.end_odometer ? t.end_odometer + ' km' : '--'}}</span>
                                    ${{t.discrepancy_amount > 0 ? `<br><small class="text-rose-600 dark:text-rose-400 font-bold">⚠️ Discrepancy: $${{t.discrepancy_amount.toFixed(2)}}</small>` : ''}}
                                </td>
                            </tr>
                        `;
                    }}).join('');
                }}
            }}

            renderPaginationControls('trips-pagination-info', 'trips-pagination-controls', tripsPage, trips.length, tripsPageSize, 'changeTripsPage');
        }}

        // =============================================================
        // SUBVIEW 4: 39 COMMERCIAL TRUCKS FLEET
        // =============================================================
        function filterTrucksTable(resetPage = false) {{
            if (!cachedData || !cachedData.fleet || !cachedData.fleet.trucks) return;
            if (resetPage) trucksPage = 1;

            const q = (document.getElementById('trucks-search')?.value || '').toLowerCase().trim();
            let trucks = cachedData.fleet.trucks.filter(t => {{
                return !q || (t.truck_number && t.truck_number.toLowerCase().includes(q)) ||
                             (t.plate_number && t.plate_number.toLowerCase().includes(q)) ||
                             (t.model_make && t.model_make.toLowerCase().includes(q)) ||
                             (t.body_type && t.body_type.toLowerCase().includes(q)) ||
                             (t.home_depot && t.home_depot.toLowerCase().includes(q));
            }});

            const totalPages = Math.max(1, Math.ceil(trucks.length / trucksPageSize));
            if (trucksPage > totalPages) trucksPage = totalPages;
            const startIndex = (trucksPage - 1) * trucksPageSize;
            const pagedTrucks = trucks.slice(startIndex, startIndex + trucksPageSize);

            const tbody = document.getElementById('fleet-trucks-table-body');
            if (tbody) {{
                if (trucks.length === 0) {{
                    tbody.innerHTML = '<tr><td colspan="6" class="px-4 py-6 text-center text-slate-400 dark:text-zinc-500 font-medium">No commercial trucks found.</td></tr>';
                }} else {{
                    tbody.innerHTML = pagedTrucks.map(t => `
                        <tr class="hover:bg-slate-50/80 dark:hover:bg-[#121218] transition">
                            <td class="px-4 sm:px-5 py-3.5 font-mono font-bold text-blue-600 dark:text-blue-400 whitespace-nowrap">#${{t.truck_number}}</td>
                            <td class="px-4 sm:px-5 py-3.5 font-extrabold text-slate-900 dark:text-zinc-100 whitespace-nowrap">${{t.plate_number}}</td>
                            <td class="px-4 sm:px-5 py-3.5 font-medium text-slate-800 dark:text-zinc-200 whitespace-nowrap">${{t.model_make}}</td>
                            <td class="px-4 sm:px-5 py-3.5 text-slate-600 dark:text-zinc-300 whitespace-nowrap">${{t.body_type}}</td>
                            <td class="px-4 sm:px-5 py-3.5 text-slate-500 dark:text-zinc-400 whitespace-nowrap">${{t.home_depot}}</td>
                            <td class="px-4 sm:px-5 py-3.5 whitespace-nowrap">
                                <span class="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-[10px] font-bold border ${{t.active ? 'bg-emerald-500/10 text-emerald-700 dark:text-emerald-300 border-emerald-200 dark:border-emerald-500/30' : 'bg-rose-500/10 text-rose-700 dark:text-rose-300 border-rose-200 dark:border-rose-500/30'}}">
                                    <span class="w-1.5 h-1.5 rounded-full ${{t.active ? 'bg-emerald-500' : 'bg-rose-500'}}"></span>
                                    ${{t.active ? 'Commercial Ready' : 'Maintenance'}}
                                </span>
                            </td>
                        </tr>
                    `).join('');
                }}
            }}

            renderPaginationControls('trucks-pagination-info', 'trucks-pagination-controls', trucksPage, trucks.length, trucksPageSize, 'changeTrucksPage');
        }}

        // =============================================================
        // SUBVIEW 5: 21 COMMERCIAL DRIVERS
        // =============================================================
        function filterDriversTable(resetPage = false) {{
            if (!cachedData || !cachedData.fleet || !cachedData.fleet.drivers) return;
            if (resetPage) driversPage = 1;

            const q = (document.getElementById('drivers-search')?.value || '').toLowerCase().trim();
            let drivers = cachedData.fleet.drivers.filter(d => {{
                return !q || (d.full_name && d.full_name.toLowerCase().includes(q)) ||
                             (d.phone && d.phone.toLowerCase().includes(q)) ||
                             (d.role && d.role.toLowerCase().includes(q));
            }});

            const totalPages = Math.max(1, Math.ceil(drivers.length / driversPageSize));
            if (driversPage > totalPages) driversPage = totalPages;
            const startIndex = (driversPage - 1) * driversPageSize;
            const pagedDrivers = drivers.slice(startIndex, startIndex + driversPageSize);

            const tbody = document.getElementById('fleet-drivers-table-body');
            if (tbody) {{
                if (drivers.length === 0) {{
                    tbody.innerHTML = '<tr><td colspan="5" class="px-4 py-6 text-center text-slate-400 dark:text-zinc-500 font-medium">No drivers found.</td></tr>';
                }} else {{
                    tbody.innerHTML = pagedDrivers.map(d => `
                        <tr class="hover:bg-slate-50/80 dark:hover:bg-[#121218] transition">
                            <td class="px-4 sm:px-5 py-3.5 font-mono text-xs text-slate-500 dark:text-zinc-400 whitespace-nowrap">#WD-${{d.staff_id}}</td>
                            <td class="px-4 sm:px-5 py-3.5 font-extrabold text-slate-900 dark:text-zinc-100 whitespace-nowrap">👤 ${{d.full_name}}</td>
                            <td class="px-4 sm:px-5 py-3.5 font-mono text-blue-600 dark:text-blue-400 whitespace-nowrap">+${{d.phone}}</td>
                            <td class="px-4 sm:px-5 py-3.5 text-xs font-semibold text-slate-700 dark:text-zinc-300 whitespace-nowrap">${{d.role}}</td>
                            <td class="px-4 sm:px-5 py-3.5 whitespace-nowrap">
                                <span class="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-[10px] font-bold border ${{d.active ? 'bg-emerald-500/10 text-emerald-700 dark:text-emerald-300 border-emerald-200 dark:border-emerald-500/30' : 'bg-zinc-500/10 text-zinc-700 dark:text-zinc-300 border-zinc-200'}}">
                                    <span class="w-1.5 h-1.5 rounded-full ${{d.active ? 'bg-emerald-500' : 'bg-zinc-400'}}"></span>
                                    ${{d.active ? 'On Roster' : 'Off Duty'}}
                                </span>
                            </td>
                        </tr>
                    `).join('');
                }}
            }}

            renderPaginationControls('drivers-pagination-info', 'drivers-pagination-controls', driversPage, drivers.length, driversPageSize, 'changeDriversPage');
        }}

        // =============================================================
        // SUBVIEW 3: CLEARED PAYMENTS HISTORY
        // =============================================================
        function filterPaymentsTable(resetPage = false) {{
            if (!cachedData || !cachedData.fleet || !cachedData.fleet.payments) return;
            if (resetPage) paymentsPage = 1;

            const q = (document.getElementById('payments-search')?.value || '').toLowerCase().trim();
            let payments = cachedData.fleet.payments.filter(p => {{
                return !q || (p.salesperson_name && p.salesperson_name.toLowerCase().includes(q)) ||
                             (p.salesperson_phone && p.salesperson_phone.toLowerCase().includes(q)) ||
                             (p.reference_number && p.reference_number.toLowerCase().includes(q)) ||
                             (p.payment_method && p.payment_method.toLowerCase().includes(q)) ||
                             (p.recorded_by && p.recorded_by.toLowerCase().includes(q));
            }});

            const totalPages = Math.max(1, Math.ceil(payments.length / paymentsPageSize));
            if (paymentsPage > totalPages) paymentsPage = totalPages;
            const startIndex = (paymentsPage - 1) * paymentsPageSize;
            const pagedPayments = payments.slice(startIndex, startIndex + paymentsPageSize);

            const tbody = document.getElementById('fleet-payments-table-body');
            if (tbody) {{
                if (payments.length === 0) {{
                    tbody.innerHTML = '<tr><td colspan="7" class="px-4 py-6 text-center text-slate-400 dark:text-zinc-500 font-medium">No payment clearances recorded yet.</td></tr>';
                }} else {{
                    tbody.innerHTML = pagedPayments.map(p => `
                        <tr class="hover:bg-slate-50/80 dark:hover:bg-[#121218] transition">
                            <td class="px-4 sm:px-5 py-3.5 font-mono text-[11px] text-slate-500 dark:text-zinc-400 whitespace-nowrap">${{p.payment_date}}</td>
                            <td class="px-4 sm:px-5 py-3.5 whitespace-nowrap">
                                <strong class="text-slate-900 dark:text-zinc-100">${{p.salesperson_name}}</strong><br>
                                <small class="text-slate-400 dark:text-zinc-500 font-mono">+${{p.salesperson_phone}}</small>
                            </td>
                            <td class="px-4 sm:px-5 py-3.5 font-mono font-bold text-emerald-600 dark:text-emerald-400 whitespace-nowrap">
                                +$${{p.cleared_amount.toFixed(2)}}
                            </td>
                            <td class="px-4 sm:px-5 py-3.5 whitespace-nowrap">
                                <span class="bg-blue-50 dark:bg-blue-500/10 text-blue-700 dark:text-blue-300 border border-blue-200 dark:border-blue-500/30 text-[10px] font-bold px-2 py-0.5 rounded">
                                    ${{p.payment_method}}
                                </span>
                                <div class="text-[11px] font-mono text-slate-500 dark:text-zinc-400 mt-0.5">Ref: ${{p.reference_number}}</div>
                            </td>
                            <td class="px-4 sm:px-5 py-3.5 font-mono text-xs whitespace-nowrap">
                                <span class="text-slate-400">$${{p.previous_balance.toFixed(2)}}</span> → <strong class="text-slate-900 dark:text-zinc-100">$${{p.remaining_balance.toFixed(2)}}</strong>
                            </td>
                            <td class="px-4 sm:px-5 py-3.5 text-xs text-slate-700 dark:text-zinc-300 whitespace-nowrap">👤 ${{p.recorded_by}}</td>
                            <td class="px-4 sm:px-5 py-3.5 text-xs text-slate-600 dark:text-zinc-300">${{p.remarks || '--'}}</td>
                        </tr>
                    `).join('');
                }}
            }}

            renderPaginationControls('payments-pagination-info', 'payments-pagination-controls', paymentsPage, payments.length, paymentsPageSize, 'changePaymentsPage');
        }}

        // =============================================================
        // MODAL 1: DELIVERY CORRIDORS & CITY MINIMUMS
        // =============================================================
        function openCityConfigModal() {{
            const modal = document.getElementById('cityMinimumsModal');
            if (!modal) return;
            if (cachedData && cachedData.fleet) {{
                const fpInput = document.getElementById('modal-fuel-price');
                if (fpInput && cachedData.fleet.fuel_price) {{
                    fpInput.value = Number(cachedData.fleet.fuel_price).toFixed(2);
                }}
                if (cachedData.fleet.route_rules) {{
                    renderModalCityRules(cachedData.fleet.route_rules);
                }}
            }}
            modal.classList.remove('hidden');
        }}

        function closeCityConfigModal() {{
            const modal = document.getElementById('cityMinimumsModal');
            if (modal) modal.classList.add('hidden');
        }}

        let modalCityRulesCache = [];
        function renderModalCityRules(rules) {{
            if (!rules) return;
            modalCityRulesCache = Object.keys(rules).map(k => {{
                return {{ key: k, ...rules[k] }};
            }});
            filterCityRulesModal();
        }}

        function filterCityRulesModal() {{
            const q = (document.getElementById('modal-city-search')?.value || '').toLowerCase().trim();
            const tbody = document.getElementById('modal-city-rules-tbody');
            if (!tbody) return;

            let filtered = modalCityRulesCache.filter(c => {{
                return !q || c.key.toLowerCase().includes(q) || (c.route && c.route.toLowerCase().includes(q));
            }});

            const countEl = document.getElementById('modal-city-count');
            if (countEl) countEl.textContent = `${{filtered.length}} Cities`;

            if (filtered.length === 0) {{
                tbody.innerHTML = '<tr><td colspan="6" class="px-4 py-4 text-center text-slate-400">No matching cities found.</td></tr>';
                return;
            }}

            tbody.innerHTML = filtered.map(c => `
                <tr class="hover:bg-slate-50 dark:hover:bg-[#16161e] transition">
                    <td class="px-4 py-2.5 font-bold text-slate-900 dark:text-zinc-100 capitalize">📍 ${{c.key}}</td>
                    <td class="px-4 py-2.5 text-[11px] text-slate-500 dark:text-zinc-400">${{c.route || '--'}}</td>
                    <td class="px-4 py-2.5 font-mono text-xs text-slate-700 dark:text-zinc-300">${{c.distance_km || 0}} km</td>
                    <td class="px-4 py-2.5">
                        <div class="relative w-28">
                            <span class="absolute left-2 top-1 text-slate-400 text-xs">$</span>
                            <input type="number" step="0.01" id="min-input-${{c.key}}" value="${{Number(c.min_sales || 0).toFixed(2)}}" class="w-full pl-5 pr-2 py-1 bg-white dark:bg-[#181820] border border-slate-300 dark:border-zinc-700 rounded-lg text-xs font-mono font-bold text-slate-800 dark:text-zinc-100 focus:outline-none focus:ring-1 focus:ring-blue-500">
                        </div>
                    </td>
                    <td class="px-4 py-2.5">
                        <div class="relative w-28">
                            <span class="absolute left-2 top-1 text-slate-400 text-xs">$</span>
                            <input type="number" step="0.01" id="van-input-${{c.key}}" value="${{Number(c.van_min || 0).toFixed(2)}}" class="w-full pl-5 pr-2 py-1 bg-white dark:bg-[#181820] border border-slate-300 dark:border-zinc-700 rounded-lg text-xs font-mono font-bold text-slate-800 dark:text-zinc-100 focus:outline-none focus:ring-1 focus:ring-blue-500">
                        </div>
                    </td>
                    <td class="px-4 py-2.5 text-right">
                        <button onclick="saveCityMin('${{c.key}}')" id="btn-save-${{c.key}}" class="bg-blue-600 hover:bg-blue-700 text-white font-bold px-3 py-1 rounded-lg text-[11px] transition shadow-xs cursor-pointer">
                            Save
                        </button>
                    </td>
                </tr>
            `).join('');
        }}

        async function saveFuelPrice() {{
            const fpInput = document.getElementById('modal-fuel-price');
            const btn = document.getElementById('modal-save-fuel-btn');
            const feedback = document.getElementById('fuel-update-feedback');
            if (!fpInput || !btn) return;

            const newPrice = parseFloat(fpInput.value);
            if (isNaN(newPrice) || newPrice <= 0) {{
                alert('Please enter a valid fuel price.');
                return;
            }}

            btn.disabled = true;
            btn.innerHTML = '⏳ Recalculating 45 Cities...';
            if (feedback) feedback.classList.add('hidden');

            try {{
                const res = await fetch('/api/v2/config/update-fuel', {{
                    method: 'POST',
                    headers: {{ 'Content-Type': 'application/json' }},
                    body: JSON.stringify({{ fuel_price: newPrice, recalculate_cities: true }})
                }});
                const data = await res.json();
                if (res.ok) {{
                    showToast(`Fuel price updated to $${{newPrice.toFixed(2)}}/L and 45 cities recalculated!`);
                    if (feedback) {{
                        feedback.textContent = `✅ Successfully recalculated all 45 cities based on $${{newPrice.toFixed(2)}}/L fuel rate`;
                        feedback.className = 'mt-2 text-xs font-semibold text-emerald-600 dark:text-emerald-400 block';
                    }}
                    await fetchDashboard();
                }} else {{
                    alert(data.detail || 'Failed to update fuel price');
                }}
            }} catch (err) {{
                alert('Network error while updating fuel price: ' + err.message);
            }} finally {{
                btn.disabled = false;
                btn.innerHTML = '<span>💾</span> Save & Recalculate 45 Cities';
            }}
        }}

        async function saveCityMin(cityKey) {{
            const minInput = document.getElementById('min-input-' + cityKey);
            const vanInput = document.getElementById('van-input-' + cityKey);
            const btn = document.getElementById('btn-save-' + cityKey);
            if (!minInput || !vanInput || !btn) return;

            const minSales = parseFloat(minInput.value);
            const vanMin = parseFloat(vanInput.value);
            btn.disabled = true;
            btn.textContent = '...';

            try {{
                const res = await fetch('/api/v2/config/update-city-minimum', {{
                    method: 'POST',
                    headers: {{ 'Content-Type': 'application/json' }},
                    body: JSON.stringify({{ city_key: cityKey, min_sales: minSales, van_min: vanMin }})
                }});
                if (res.ok) {{
                    btn.textContent = '✅ Saved';
                    btn.className = 'bg-emerald-600 text-white font-bold px-3 py-1 rounded-lg text-[11px] transition shadow-xs';
                    setTimeout(() => {{
                        btn.textContent = 'Save';
                        btn.className = 'bg-blue-600 hover:bg-blue-700 text-white font-bold px-3 py-1 rounded-lg text-[11px] transition shadow-xs cursor-pointer';
                        btn.disabled = false;
                    }}, 2000);
                    showToast(`Updated threshold for ${{cityKey.toUpperCase()}}!`);
                    await fetchDashboard();
                }} else {{
                    btn.disabled = false;
                    btn.textContent = 'Save';
                    alert('Failed to save city minimum threshold.');
                }}
            }} catch (err) {{
                btn.disabled = false;
                btn.textContent = 'Save';
                alert('Network error: ' + err.message);
            }}
        }}

        // =============================================================
        // MODAL 2: CLEAR SALES REP DEBT SETTLEMENT
        // =============================================================
        let activeSalespersonsForPay = [];
        function populatePaySalespersonDropdown(salespersons) {{
            if (!salespersons) return;
            activeSalespersonsForPay = salespersons;
            const selectEl = document.getElementById('modal-pay-salesperson');
            if (!selectEl) return;

            const currentVal = selectEl.value;
            selectEl.innerHTML = '<option value="">-- Choose Sales Rep --</option>' + salespersons.map(sp => `
                <option value="${{sp.phone}}" data-name="${{sp.name}}" data-balance="${{sp.net_balance}}">
                    ${{sp.name}} (+${{sp.phone}}) — Debt: $${{sp.net_balance.toFixed(2)}}
                </option>
            `).join('');

            if (currentVal) selectEl.value = currentVal;
        }}

        function openClearPaymentModal(repName = '', repPhone = '', balance = 0) {{
            const modal = document.getElementById('clearPaymentModal');
            if (!modal) return;
            const selectEl = document.getElementById('modal-pay-salesperson');
            const amountInput = document.getElementById('modal-pay-amount');
            const refInput = document.getElementById('modal-pay-ref');
            const remarksInput = document.getElementById('modal-pay-remarks');
            const feedback = document.getElementById('modal-pay-feedback');

            if (feedback) feedback.classList.add('hidden');
            if (refInput) refInput.value = '';
            if (remarksInput) remarksInput.value = '';

            if (repPhone && selectEl) {{
                selectEl.value = repPhone;
            }}
            onSelectPaySalesperson();

            if (balance > 0 && amountInput) {{
                amountInput.value = balance.toFixed(2);
            }}

            modal.classList.remove('hidden');
        }}

        function closeClearPaymentModal() {{
            const modal = document.getElementById('clearPaymentModal');
            if (modal) modal.classList.add('hidden');
        }}

        function onSelectPaySalesperson() {{
            const selectEl = document.getElementById('modal-pay-salesperson');
            const balanceEl = document.getElementById('modal-pay-current-balance');
            const amountInput = document.getElementById('modal-pay-amount');
            if (!selectEl || !balanceEl) return;

            const selectedOption = selectEl.options[selectEl.selectedIndex];
            if (selectedOption && selectedOption.dataset.balance) {{
                const bal = parseFloat(selectedOption.dataset.balance);
                balanceEl.textContent = '$' + bal.toFixed(2);
                if (amountInput && (!amountInput.value || parseFloat(amountInput.value) <= 0)) {{
                    amountInput.value = bal > 0 ? bal.toFixed(2) : '0.00';
                }}
            }} else {{
                balanceEl.textContent = '$0.00';
            }}
        }}

        function fillFullClearance() {{
            const selectEl = document.getElementById('modal-pay-salesperson');
            const amountInput = document.getElementById('modal-pay-amount');
            if (!selectEl || !amountInput) return;
            const selectedOption = selectEl.options[selectEl.selectedIndex];
            if (selectedOption && selectedOption.dataset.balance) {{
                amountInput.value = parseFloat(selectedOption.dataset.balance).toFixed(2);
            }}
        }}

        async function submitClearPayment() {{
            const selectEl = document.getElementById('modal-pay-salesperson');
            const amountInput = document.getElementById('modal-pay-amount');
            const methodSelect = document.getElementById('modal-pay-method');
            const refInput = document.getElementById('modal-pay-ref');
            const remarksInput = document.getElementById('modal-pay-remarks');
            const btn = document.getElementById('modal-submit-pay-btn');
            const feedback = document.getElementById('modal-pay-feedback');

            if (!selectEl.value) {{
                alert('Please select a sales representative.');
                return;
            }}
            const amt = parseFloat(amountInput.value);
            if (isNaN(amt) || amt <= 0) {{
                alert('Please enter a valid amount greater than $0.00');
                return;
            }}

            const selectedOption = selectEl.options[selectEl.selectedIndex];
            const repPhone = selectEl.value;
            const repName = selectedOption.dataset.name || 'Sales Rep';
            const method = methodSelect.value;
            const ref = (refInput.value || '').trim();
            const remarks = (remarksInput.value || '').trim();

            btn.disabled = true;
            btn.innerHTML = '⏳ Processing Clearance...';

            try {{
                const res = await fetch('/api/v2/finance/clear-sales-rep-payment', {{
                    method: 'POST',
                    headers: {{ 'Content-Type': 'application/json' }},
                    body: JSON.stringify({{
                        salesperson_phone: repPhone,
                        salesperson_name: repName,
                        cleared_amount: amt,
                        payment_method: method,
                        reference_number: ref,
                        remarks: remarks
                    }})
                }});
                const data = await res.json();
                if (res.ok) {{
                    showToast(`Successfully cleared $${{amt.toFixed(2)}} for ${{repName}}!`);
                    closeClearPaymentModal();
                    await fetchDashboard();
                }} else {{
                    if (feedback) {{
                        feedback.textContent = data.detail || 'Error clearing payment';
                        feedback.className = 'text-xs font-bold text-rose-600 block';
                    }} else {{
                        alert(data.detail || 'Error clearing payment');
                    }}
                }}
            }} catch (err) {{
                alert('Network error while recording payment: ' + err.message);
            }} finally {{
                btn.disabled = false;
                btn.innerHTML = '<span>✅</span> Confirm Debt Clearance';
            }}
        }}

        // =============================================================
        // MODAL 3: SYSTEM AUDIT LOGS TRAIL
        // =============================================================
        function openAuditLogsModal() {{
            const modal = document.getElementById('auditLogsModal');
            if (!modal) return;
            modal.classList.remove('hidden');
            loadAuditLogs();
        }}

        function closeAuditLogsModal() {{
            const modal = document.getElementById('auditLogsModal');
            if (modal) modal.classList.add('hidden');
        }}

        async function loadAuditLogs() {{
            const tbody = document.getElementById('modal-audit-tbody');
            if (!tbody) return;
            tbody.innerHTML = '<tr><td colspan="6" class="px-4 py-6 text-center text-slate-400">Loading audit records...</td></tr>';

            try {{
                const res = await fetch('/api/v2/audit/logs');
                const data = await res.json();
                if (res.ok && data.logs) {{
                    if (data.logs.length === 0) {{
                        tbody.innerHTML = '<tr><td colspan="6" class="px-4 py-6 text-center text-slate-400">No audit logs found yet.</td></tr>';
                    }} else {{
                        tbody.innerHTML = data.logs.map(l => {{
                            let actionColor = 'bg-blue-500/10 text-blue-700 dark:text-blue-300 border-blue-200 dark:border-blue-500/30';
                            if (l.action.includes('CLEAR')) actionColor = 'bg-emerald-500/10 text-emerald-700 dark:text-emerald-300 border-emerald-200 dark:border-emerald-500/30';
                            else if (l.action.includes('UPDATE')) actionColor = 'bg-purple-500/10 text-purple-700 dark:text-purple-300 border-purple-200 dark:border-purple-500/30';

                            return `
                                <tr class="hover:bg-slate-50 dark:hover:bg-[#16161e] transition">
                                    <td class="px-4 py-2.5 font-mono text-[11px] text-slate-500 dark:text-zinc-400 whitespace-nowrap">${{l.created_at}}</td>
                                    <td class="px-4 py-2.5 whitespace-nowrap">
                                        <strong class="text-slate-900 dark:text-zinc-100">${{l.username}}</strong><br>
                                        <small class="text-slate-400 dark:text-zinc-500">${{l.user_role}}</small>
                                    </td>
                                    <td class="px-4 py-2.5 whitespace-nowrap">
                                        <span class="inline-flex items-center px-2 py-0.5 rounded text-[10px] font-bold border ${{actionColor}} whitespace-nowrap">
                                            ${{l.action}}
                                        </span>
                                    </td>
                                    <td class="px-4 py-2.5 font-mono text-xs font-semibold text-slate-700 dark:text-zinc-300 whitespace-nowrap">${{l.module}}</td>
                                    <td class="px-4 py-2.5 font-mono text-xs text-slate-600 dark:text-zinc-400 whitespace-nowrap">${{l.entity_id}}</td>
                                    <td class="px-4 py-2.5 text-xs text-slate-700 dark:text-zinc-300">
                                        <div>${{l.remarks || '--'}}</div>
                                        ${{l.new_value ? `<small class="font-mono text-slate-400 dark:text-zinc-500 block truncate max-w-xs">${{JSON.stringify(l.new_value)}}</small>` : ''}}
                                    </td>
                                </tr>
                            `;
                        }}).join('');
                    }}
                }}
            }} catch (err) {{
                tbody.innerHTML = `<tr><td colspan="6" class="px-4 py-4 text-center text-rose-500">Failed to load audit logs: ${{err.message}}</td></tr>`;
            }}
        }}

        // Initialize dashboard
        switchDomain(initialDefaultTab);
        fetchDashboard();
        setInterval(() => {{
            if (!document.hidden) {{
                fetchDashboard();
            }}
        }}, 15000);
        document.addEventListener('visibilitychange', () => {{
            if (!document.hidden) {{
                fetchDashboard();
            }}
        }});
    </script>
</body>
</html>"""
    return HTMLResponse(content=html_content)
