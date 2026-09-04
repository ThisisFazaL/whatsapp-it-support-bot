import logging
import datetime
from fastapi import APIRouter, Depends, Request, Response, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload

from app.database import (
    get_db, Ticket, MaintenanceTicket, TicketAssignment, MaintenanceTicketAssignment,
    SupportAdmin, Employee, Department, Location, Category, Subcategory, IssueType, Priority, TicketStatus
)
from app.workshop.models import (
    WorkshopTicket, WorkshopTruck, WorkshopStaff, WorkshopPartsRequest
)
from app.auth import (
    authenticate_user, create_session_token, get_current_user_from_request,
    COOKIE_NAME, SESSION_MAX_AGE, USERS_DB
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
# Authentication Routes (/login, /logout)
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
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&display=swap" rel="stylesheet">
    <style>
        body { font-family: 'Plus Jakarta Sans', sans-serif; }
    </style>
</head>
<body class="bg-slate-100 text-slate-800 min-h-screen flex items-center justify-center p-3 sm:p-6">
    <div class="bg-white border border-slate-200 rounded-3xl shadow-xl w-full max-w-md p-6 sm:p-10">
        <div class="text-center mb-6 sm:mb-8">
            <div class="inline-flex items-center gap-2 bg-blue-50 border border-blue-200 text-blue-700 px-3.5 py-1.5 rounded-full text-xs font-bold mb-3 sm:mb-4">
                🔒 Enterprise Security
            </div>
            <h1 class="text-2xl sm:text-3xl font-extrabold text-slate-900 tracking-tight">Tagoneswa Portal</h1>
            <p class="text-slate-500 text-xs sm:text-sm mt-1">IT Support • Building Projects • Fleet Workshop</p>
        </div>

        <div id="errorBox" class="hidden bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-xl text-xs sm:text-sm mb-5 font-medium"></div>

        <form id="loginForm" class="space-y-4 sm:space-y-5">
            <div>
                <label class="block text-xs font-bold text-slate-700 uppercase tracking-wider mb-1.5 sm:mb-2" for="username">Username</label>
                <input class="w-full bg-slate-50 border border-slate-300 rounded-xl px-4 py-3 text-slate-900 text-base sm:text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:bg-white transition" type="text" id="username" name="username" placeholder="e.g. admin, logistics" required autofocus autocomplete="username">
            </div>

            <div>
                <label class="block text-xs font-bold text-slate-700 uppercase tracking-wider mb-1.5 sm:mb-2" for="password">Password</label>
                <div class="relative">
                    <input class="w-full bg-slate-50 border border-slate-300 rounded-xl px-4 py-3 text-slate-900 text-base sm:text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:bg-white transition" type="password" id="password" name="password" placeholder="••••••••••••" required autocomplete="current-password">
                    <button type="button" class="absolute right-3.5 top-1/2 -translate-y-1/2 text-xs font-semibold text-slate-400 hover:text-slate-600 px-2 py-1" onclick="togglePassword()">Show</button>
                </div>
            </div>

            <button type="submit" class="w-full bg-blue-600 hover:bg-blue-700 active:bg-blue-800 text-white font-bold py-3.5 rounded-xl shadow-md transition duration-150 text-sm sm:text-base flex items-center justify-center gap-2 cursor-pointer" id="loginBtn">
                Sign In to Dashboard →
            </button>
        </form>

        <div class="mt-6 sm:mt-8 text-center text-[11px] sm:text-xs text-slate-400 border-t border-slate-100 pt-5 sm:pt-6">
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
    default_tab = "logistics" if user["role"] == "LOGISTICS_ADMIN" else ("projects" if user["role"] == "PROJECTS_ADMIN" else "it")
    
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
# Data API: Complete 3-Domain Partitioned Metrics & Records
# -------------------------------------------------------------
@router.get("/api/dashboard/data")
async def get_dashboard_data(request: Request, db: AsyncSession = Depends(get_db)):
    """
    Returns complete live operational metrics partitioned cleanly across:
    1. IT Support (with Admin SLA & Category Issue Tree)
    2. Building Projects & Maintenance
    3. Workshop & Fleet Logistics
    """
    user = get_current_user_from_request(request)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized session. Please log in.")

    # 1. Fetch IT Support Admins (Kevin, Ellias, Faisal)
    admins_stmt = select(SupportAdmin).where(
        SupportAdmin.active == True,
        SupportAdmin.phone.in_(IT_SUPPORT_ADMIN_PHONES)
    )
    support_admins = (await db.execute(admins_stmt)).scalars().all()

    # 2. Fetch IT Tickets
    it_stmt = select(Ticket).options(
        selectinload(Ticket.employee).selectinload(Employee.department),
        selectinload(Ticket.employee).selectinload(Employee.location),
        selectinload(Ticket.category),
        selectinload(Ticket.subcategory),
        selectinload(Ticket.issue_type),
        selectinload(Ticket.priority),
        selectinload(Ticket.status)
    )
    it_tickets = (await db.execute(it_stmt)).scalars().all()

    # 3. Fetch Maintenance (Projects) Tickets
    maint_stmt = select(MaintenanceTicket).options(
        selectinload(MaintenanceTicket.employee).selectinload(Employee.department),
        selectinload(MaintenanceTicket.employee).selectinload(Employee.location),
        selectinload(MaintenanceTicket.category),
        selectinload(MaintenanceTicket.subcategory),
        selectinload(MaintenanceTicket.issue_type),
        selectinload(MaintenanceTicket.priority),
        selectinload(MaintenanceTicket.status)
    )
    maint_tickets = (await db.execute(maint_stmt)).scalars().all()

    # 4. Fetch Assignments Map
    asg_stmt = select(TicketAssignment).options(selectinload(TicketAssignment.admin))
    asgs = (await db.execute(asg_stmt)).scalars().all()
    asg_map = {f"IT_{a.ticket_id}": a.admin for a in asgs if a.admin}

    m_asg_stmt = select(MaintenanceTicketAssignment).options(selectinload(MaintenanceTicketAssignment.admin))
    m_asgs = (await db.execute(m_asg_stmt)).scalars().all()
    for ma in m_asgs:
        if ma.admin:
            asg_map[f"MAINT_{ma.ticket_id}"] = ma.admin

    # 5. Fetch Workshop & Fleet Logistics Data
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

    # -----------------------------
    # Process IT Support Records & Category Tree Map
    # -----------------------------
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

    now_utc = datetime.datetime.utcnow()
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

    # Format Category Tree List
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

    # -----------------------------
    # Process Maintenance (Projects) Records
    # -----------------------------
    maint_records = []
    maint_stats = {"total": len(maint_tickets), "open": 0, "in_progress": 0, "resolved": 0, "closed": 0, "locations_count": 0}
    loc_set = set()

    for t in maint_tickets:
        s_id = t.status_id
        if s_id == 1: maint_stats["open"] += 1
        elif s_id == 2: maint_stats["in_progress"] += 1
        elif s_id == 3: maint_stats["resolved"] += 1
        elif s_id == 4: maint_stats["closed"] += 1

        admin = asg_map.get(f"MAINT_{t.ticket_id}")
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

    # -----------------------------
    # Process Workshop & Fleet Logistics Records
    # -----------------------------
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

    return {
        "user": {
            "username": user["username"],
            "name": user["name"],
            "role": user["role"],
            "allowed_domains": user["allowed_domains"]
        },
        "it": {
            "stats": it_stats,
            "records": it_records,
            "admins": it_admin_performance,
            "category_tree": category_tree_list
        },
        "projects": {
            "stats": maint_stats,
            "records": maint_records
        },
        "logistics": {
            "stats": ws_stats,
            "records": ws_records,
            "fleet_count": len(ws_trucks)
        }
    }

# -------------------------------------------------------------
# Main Secured Dashboard View (GET /dashboard)
# -------------------------------------------------------------
@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard_view(request: Request):
    """Renders the executive white-themed 3-Domain Operations Dashboard with full mobile support."""
    user = get_current_user_from_request(request)
    if not user:
        return RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)

    html_content = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <title>Tagoneswa Multi-Domain Operations Console</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&family=JetBrains+Mono:wght@500;700&display=swap" rel="stylesheet">
    <style>
        body { font-family: 'Plus Jakarta Sans', sans-serif; }
        .font-mono { font-family: 'JetBrains Mono', monospace; }
        .tab-btn.active {
            background-color: #2563eb;
            color: #ffffff;
            box-shadow: 0 4px 12px rgba(37, 99, 235, 0.25);
        }
        .domain-view { display: none; }
        .domain-view.active { display: block; }
        .no-scrollbar::-webkit-scrollbar { display: none; }
        .no-scrollbar { -ms-overflow-style: none; scrollbar-width: none; }
        @keyframes spinFast {
            0% { transform: rotate(0deg); }
            100% { transform: rotate(360deg); }
        }
        .spinning {
            animation: spinFast 0.6s linear infinite;
        }
    </style>
</head>
<body class="bg-slate-50 text-slate-800 min-h-screen pb-12">
    <!-- Toast Notification -->
    <div id="toast" class="fixed bottom-5 right-5 z-50 transform translate-y-20 opacity-0 transition-all duration-300 pointer-events-none bg-slate-900 text-white px-4 py-3 rounded-2xl shadow-2xl border border-slate-700 text-xs font-semibold flex items-center gap-2">
        <span id="toastIcon">✅</span>
        <span id="toastMsg">Live data updated</span>
    </div>

    <!-- Top Sticky Header -->
    <header class="bg-white border-b border-slate-200 sticky top-0 z-30 shadow-xs">
        <div class="max-w-7xl mx-auto px-3 sm:px-6 lg:px-8 py-2.5 sm:py-3.5">
            <div class="flex flex-col md:flex-row items-center justify-between gap-3">
                <!-- Top Row: Brand & Mobile Actions -->
                <div class="flex items-center justify-between w-full md:w-auto gap-3">
                    <div class="flex items-center gap-2.5">
                        <div class="w-9 h-9 sm:w-10 sm:h-10 bg-blue-600 rounded-xl flex items-center justify-center text-white text-lg sm:text-xl font-bold shadow-md shadow-blue-500/20 shrink-0">
                            🚚
                        </div>
                        <div>
                            <h1 class="text-base sm:text-lg font-extrabold text-slate-900 tracking-tight leading-none">Tagoneswa</h1>
                            <p class="text-[10px] sm:text-xs text-slate-500 font-medium mt-0.5">Operations Portal</p>
                        </div>
                    </div>

                    <!-- Right Controls for Mobile -->
                    <div class="flex items-center gap-2 md:hidden">
                        <button onclick="manualRefresh()" id="mobileRefreshBtn" class="bg-slate-100 hover:bg-slate-200 active:bg-slate-300 text-slate-700 p-2 rounded-xl text-xs font-bold transition flex items-center gap-1 border border-slate-200" title="Refresh Live Data">
                            <span id="mobileRefreshIcon" class="inline-block">🔄</span>
                        </button>
                        <button onclick="handleLogout()" class="bg-red-50 hover:bg-red-100 text-red-600 border border-red-200 text-xs font-bold px-3 py-1.5 rounded-xl transition cursor-pointer">
                            Log Out
                        </button>
                    </div>
                </div>

                <!-- 3 Domain Switcher (Scrollable on Mobile) -->
                <nav class="flex bg-slate-100 p-1 rounded-xl border border-slate-200 gap-1 w-full md:w-auto overflow-x-auto justify-start sm:justify-center no-scrollbar">
                    <button id="btn-tab-it" onclick="switchDomain('it')" class="tab-btn active px-3.5 sm:px-4 py-2 rounded-lg text-xs font-bold text-slate-600 hover:text-slate-900 transition flex items-center gap-1.5 whitespace-nowrap shrink-0 cursor-pointer">
                        <span>💻</span> IT Support
                    </button>
                    <button id="btn-tab-projects" onclick="switchDomain('projects')" class="tab-btn px-3.5 sm:px-4 py-2 rounded-lg text-xs font-bold text-slate-600 hover:text-slate-900 transition flex items-center gap-1.5 whitespace-nowrap shrink-0 cursor-pointer">
                        <span>🏗️</span> Building Projects
                    </button>
                    <button id="btn-tab-logistics" onclick="switchDomain('logistics')" class="tab-btn px-3.5 sm:px-4 py-2 rounded-lg text-xs font-bold text-slate-600 hover:text-slate-900 transition flex items-center gap-1.5 whitespace-nowrap shrink-0 cursor-pointer">
                        <span>🚚</span> Workshop & Fleet
                    </button>
                </nav>

                <!-- User Pill, Desktop Refresh & Logout -->
                <div class="hidden md:flex items-center gap-3">
                    <button onclick="manualRefresh()" id="desktopRefreshBtn" class="bg-slate-100 hover:bg-slate-200 active:bg-slate-300 text-slate-700 px-3 py-2 rounded-xl text-xs font-bold transition flex items-center gap-1.5 border border-slate-200 cursor-pointer shadow-xs" title="Refresh Live Data">
                        <span id="desktopRefreshIcon" class="inline-block">🔄</span>
                        <span>Refresh</span>
                    </button>
                    <div class="text-right">
                        <div class="text-xs font-bold text-slate-900" id="userDisplayName">Administrator</div>
                        <div class="text-[10px] font-semibold text-emerald-600 flex items-center justify-end gap-1" id="userRoleBadge">
                            <span class="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse"></span> Online
                        </div>
                    </div>
                    <button onclick="handleLogout()" class="bg-red-50 hover:bg-red-100 text-red-600 border border-red-200 text-xs font-bold px-3.5 py-2 rounded-xl transition cursor-pointer">
                        Log Out
                    </button>
                </div>
            </div>
        </div>
    </header>

    <!-- Main Content Container -->
    <main class="max-w-7xl mx-auto px-3 sm:px-6 lg:px-8 py-4 sm:py-8 space-y-6 sm:space-y-8">

        <!-- ========================================================= -->
        <!-- TAB 1: IT SUPPORT -->
        <!-- ========================================================= -->
        <div id="view-it" class="domain-view active space-y-6 sm:space-y-8">
            <!-- IT Stats -->
            <div class="grid grid-cols-2 lg:grid-cols-4 gap-3 sm:gap-4">
                <div class="bg-white border border-slate-200 rounded-2xl p-4 sm:p-5 shadow-xs">
                    <div class="text-[11px] sm:text-xs font-bold uppercase tracking-wider text-slate-400">Total IT Tickets</div>
                    <div class="text-2xl sm:text-3xl font-extrabold text-slate-900 mt-1.5" id="it-stat-total">0</div>
                    <div class="text-[11px] sm:text-xs text-blue-600 font-semibold mt-1">All IT Logs</div>
                </div>
                <div class="bg-white border border-slate-200 rounded-2xl p-4 sm:p-5 shadow-xs">
                    <div class="text-[11px] sm:text-xs font-bold uppercase tracking-wider text-slate-400">Open & Active</div>
                    <div class="text-2xl sm:text-3xl font-extrabold text-amber-500 mt-1.5" id="it-stat-active">0</div>
                    <div class="text-[11px] sm:text-xs text-amber-600 font-semibold mt-1">Action Required</div>
                </div>
                <div class="bg-white border border-slate-200 rounded-2xl p-4 sm:p-5 shadow-xs">
                    <div class="text-[11px] sm:text-xs font-bold uppercase tracking-wider text-slate-400">Resolved / Closed</div>
                    <div class="text-2xl sm:text-3xl font-extrabold text-emerald-500 mt-1.5" id="it-stat-resolved">0</div>
                    <div class="text-[11px] sm:text-xs text-emerald-600 font-semibold mt-1">Completed Solved</div>
                </div>
                <div class="bg-white border border-slate-200 rounded-2xl p-4 sm:p-5 shadow-xs">
                    <div class="text-[11px] sm:text-xs font-bold uppercase tracking-wider text-slate-400">Avg Resolution</div>
                    <div class="text-2xl sm:text-3xl font-extrabold text-purple-600 mt-1.5" id="it-stat-avg-time">--</div>
                    <div class="text-[11px] sm:text-xs text-purple-600 font-semibold mt-1">SLA Speed Benchmark</div>
                </div>
            </div>

            <!-- IT Table Section (Main tickets info first) -->
            <div class="bg-white border border-slate-200 rounded-2xl shadow-xs overflow-hidden">
                <!-- Controls & Filters -->
                <div class="p-4 sm:p-5 border-b border-slate-200 flex flex-col md:flex-row items-stretch md:items-center justify-between gap-3 sm:gap-4 bg-slate-50/50">
                    <div class="flex flex-col sm:flex-row flex-wrap items-stretch sm:items-center gap-2 sm:gap-3 w-full md:w-auto">
                        <input type="text" id="it-search" placeholder="🔍 Search employee, ticket #, issue..." oninput="filterITTable()" class="bg-white border border-slate-300 rounded-xl px-4 py-2.5 sm:py-2 text-xs font-medium text-slate-800 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-blue-500 w-full sm:w-64">
                        
                        <!-- Admin Filter -->
                        <select id="it-admin-filter" onchange="filterITTable()" class="bg-white border border-slate-300 rounded-xl px-3 py-2.5 sm:py-2 text-xs font-medium text-slate-700 focus:outline-none focus:ring-2 focus:ring-blue-500 w-full sm:w-auto">
                            <option value="ALL">All Support Admins</option>
                        </select>

                        <!-- Status Filter -->
                        <select id="it-status-filter" onchange="filterITTable()" class="bg-white border border-slate-300 rounded-xl px-3 py-2.5 sm:py-2 text-xs font-medium text-slate-700 focus:outline-none focus:ring-2 focus:ring-blue-500 w-full sm:w-auto">
                            <option value="ALL">All Statuses</option>
                            <option value="Open">Open</option>
                            <option value="In Progress">In Progress</option>
                            <option value="Resolved">Resolved</option>
                            <option value="Closed">Closed</option>
                        </select>
                    </div>

                    <!-- Dynamic Count Badge & Mobile Refresh Indicator -->
                    <div class="flex items-center justify-between sm:justify-end gap-2">
                        <span id="it-count-badge" class="bg-blue-50 text-blue-700 border border-blue-200 text-xs font-bold px-3 py-1.5 rounded-full">
                            Showing 0 tickets
                        </span>
                    </div>
                </div>

                <!-- Swipe hint on mobile -->
                <div class="block md:hidden text-[11px] text-slate-400 px-4 py-1.5 bg-slate-50 border-b border-slate-100 flex items-center justify-between">
                    <span>👉 Swipe horizontally for full table</span>
                    <span class="font-mono text-slate-400">⇄</span>
                </div>

                <!-- Table -->
                <div class="overflow-x-auto">
                    <table class="w-full text-left text-xs min-w-[760px]">
                        <thead class="bg-slate-100/75 text-slate-500 font-bold uppercase tracking-wider border-b border-slate-200">
                            <tr>
                                <th class="px-4 sm:px-5 py-3.5">Ticket #</th>
                                <th class="px-4 sm:px-5 py-3.5">Employee</th>
                                <th class="px-4 sm:px-5 py-3.5">Department & Location</th>
                                <th class="px-4 sm:px-5 py-3.5">Category & Issue</th>
                                <th class="px-4 sm:px-5 py-3.5">Priority</th>
                                <th class="px-4 sm:px-5 py-3.5">Status</th>
                                <th class="px-4 sm:px-5 py-3.5">Assigned Admin</th>
                                <th class="px-4 sm:px-5 py-3.5">Solving Time</th>
                            </tr>
                        </thead>
                        <tbody id="it-table-body" class="divide-y divide-slate-200 text-slate-700"></tbody>
                    </table>
                </div>
            </div>

            <!-- IT Admin SLA Cards (Kevin Chikati, Ellias Chigwida, Faisal) -->
            <div class="bg-white border border-slate-200 rounded-2xl p-5 sm:p-6 shadow-xs">
                <div class="flex flex-col sm:flex-row sm:items-center justify-between mb-4 gap-1">
                    <h2 class="text-xs sm:text-sm font-extrabold uppercase tracking-wider text-slate-900 flex items-center gap-2">
                        <span>👨‍💻</span> IT Support Technicians Performance & SLA
                    </h2>
                    <span class="text-[11px] font-semibold text-slate-400">Real-Time Resolution Metrics</span>
                </div>
                <div class="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-3 sm:gap-4" id="it-admin-cards"></div>
            </div>

            <!-- Category & Issue Breakdown Tree -->
            <div class="bg-white border border-slate-200 rounded-2xl p-5 sm:p-6 shadow-xs">
                <div class="flex flex-col sm:flex-row sm:items-center justify-between mb-4 gap-1">
                    <h2 class="text-xs sm:text-sm font-extrabold uppercase tracking-wider text-slate-900 flex items-center gap-2">
                        <span>🌳</span> Category, Subcategory & Specific Issue Breakdown
                    </h2>
                    <span class="text-[11px] font-semibold text-slate-400">Hierarchical Fault Occurrences</span>
                </div>
                <div id="it-category-tree" class="space-y-3"></div>
            </div>
        </div>

        <!-- ========================================================= -->
        <!-- TAB 2: BUILDING PROJECTS -->
        <!-- ========================================================= -->
        <div id="view-projects" class="domain-view space-y-6 sm:space-y-8">
            <!-- Projects Stats -->
            <div class="grid grid-cols-2 lg:grid-cols-4 gap-3 sm:gap-4">
                <div class="bg-white border border-slate-200 rounded-2xl p-4 sm:p-5 shadow-xs">
                    <div class="text-[11px] sm:text-xs font-bold uppercase tracking-wider text-slate-400">Total Project Tickets</div>
                    <div class="text-2xl sm:text-3xl font-extrabold text-slate-900 mt-1.5" id="proj-stat-total">0</div>
                    <div class="text-[11px] sm:text-xs text-blue-600 font-semibold mt-1">Building & Facilities</div>
                </div>
                <div class="bg-white border border-slate-200 rounded-2xl p-4 sm:p-5 shadow-xs">
                    <div class="text-[11px] sm:text-xs font-bold uppercase tracking-wider text-slate-400">Active Work Orders</div>
                    <div class="text-2xl sm:text-3xl font-extrabold text-amber-500 mt-1.5" id="proj-stat-active">0</div>
                    <div class="text-[11px] sm:text-xs text-amber-600 font-semibold mt-1">On-Site in Progress</div>
                </div>
                <div class="bg-white border border-slate-200 rounded-2xl p-4 sm:p-5 shadow-xs">
                    <div class="text-[11px] sm:text-xs font-bold uppercase tracking-wider text-slate-400">Completed Facilities</div>
                    <div class="text-2xl sm:text-3xl font-extrabold text-emerald-500 mt-1.5" id="proj-stat-completed">0</div>
                    <div class="text-[11px] sm:text-xs text-emerald-600 font-semibold mt-1">Inspected & Closed</div>
                </div>
                <div class="bg-white border border-slate-200 rounded-2xl p-4 sm:p-5 shadow-xs">
                    <div class="text-[11px] sm:text-xs font-bold uppercase tracking-wider text-slate-400">Active Branches / Yards</div>
                    <div class="text-2xl sm:text-3xl font-extrabold text-purple-600 mt-1.5" id="proj-stat-locations">0</div>
                    <div class="text-[11px] sm:text-xs text-purple-600 font-semibold mt-1">Locations Serviced</div>
                </div>
            </div>

            <!-- Projects Table Section -->
            <div class="bg-white border border-slate-200 rounded-2xl shadow-xs overflow-hidden">
                <div class="p-4 sm:p-5 border-b border-slate-200 flex flex-col md:flex-row items-stretch md:items-center justify-between gap-3 sm:gap-4 bg-slate-50/50">
                    <div class="flex flex-col sm:flex-row flex-wrap items-stretch sm:items-center gap-2 sm:gap-3 w-full md:w-auto">
                        <input type="text" id="proj-search" placeholder="🔍 Search site, ticket #, repair..." oninput="filterProjectsTable()" class="bg-white border border-slate-300 rounded-xl px-4 py-2.5 sm:py-2 text-xs font-medium text-slate-800 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-blue-500 w-full sm:w-64">
                        
                        <!-- Location Filter -->
                        <select id="proj-loc-filter" onchange="filterProjectsTable()" class="bg-white border border-slate-300 rounded-xl px-3 py-2.5 sm:py-2 text-xs font-medium text-slate-700 focus:outline-none focus:ring-2 focus:ring-blue-500 w-full sm:w-auto">
                            <option value="ALL">All Branches & Yards</option>
                        </select>

                        <!-- Admin Filter -->
                        <select id="proj-admin-filter" onchange="filterProjectsTable()" class="bg-white border border-slate-300 rounded-xl px-3 py-2.5 sm:py-2 text-xs font-medium text-slate-700 focus:outline-none focus:ring-2 focus:ring-blue-500 w-full sm:w-auto">
                            <option value="ALL">All Project Leads</option>
                        </select>

                        <!-- Status Filter -->
                        <select id="proj-status-filter" onchange="filterProjectsTable()" class="bg-white border border-slate-300 rounded-xl px-3 py-2.5 sm:py-2 text-xs font-medium text-slate-700 focus:outline-none focus:ring-2 focus:ring-blue-500 w-full sm:w-auto">
                            <option value="ALL">All Statuses</option>
                            <option value="Open">Open</option>
                            <option value="In Progress">In Progress</option>
                            <option value="Closed">Closed</option>
                        </select>
                    </div>

                    <div class="flex items-center justify-between sm:justify-end gap-2">
                        <span id="proj-count-badge" class="bg-blue-50 text-blue-700 border border-blue-200 text-xs font-bold px-3 py-1.5 rounded-full">
                            Showing 0 tickets
                        </span>
                    </div>
                </div>

                <!-- Swipe hint on mobile -->
                <div class="block md:hidden text-[11px] text-slate-400 px-4 py-1.5 bg-slate-50 border-b border-slate-100 flex items-center justify-between">
                    <span>👉 Swipe horizontally for full table</span>
                    <span class="font-mono text-slate-400">⇄</span>
                </div>

                <div class="overflow-x-auto">
                    <table class="w-full text-left text-xs min-w-[760px]">
                        <thead class="bg-slate-100/75 text-slate-500 font-bold uppercase tracking-wider border-b border-slate-200">
                            <tr>
                                <th class="px-4 sm:px-5 py-3.5">Ticket #</th>
                                <th class="px-4 sm:px-5 py-3.5">Reporter</th>
                                <th class="px-4 sm:px-5 py-3.5">Site / Branch Location</th>
                                <th class="px-4 sm:px-5 py-3.5">Category & Description</th>
                                <th class="px-4 sm:px-5 py-3.5">Status</th>
                                <th class="px-4 sm:px-5 py-3.5">Assigned Lead</th>
                                <th class="px-4 sm:px-5 py-3.5">Date Created</th>
                            </tr>
                        </thead>
                        <tbody id="proj-table-body" class="divide-y divide-slate-200 text-slate-700"></tbody>
                    </table>
                </div>
            </div>
        </div>

        <!-- ========================================================= -->
        <!-- TAB 3: WORKSHOP & FLEET LOGISTICS -->
        <!-- ========================================================= -->
        <div id="view-logistics" class="domain-view space-y-6 sm:space-y-8">
            <!-- Fleet Stats -->
            <div class="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3 sm:gap-4">
                <div class="bg-white border border-slate-200 rounded-2xl p-4 sm:p-5 shadow-xs">
                    <div class="text-[11px] sm:text-xs font-bold uppercase tracking-wider text-slate-400">Active Fleet</div>
                    <div class="text-2xl sm:text-3xl font-extrabold text-blue-600 mt-1.5" id="ws-stat-fleet">39</div>
                    <div class="text-[11px] sm:text-xs text-blue-600 font-semibold mt-1">Trucks Registered</div>
                </div>
                <div class="bg-white border border-slate-200 rounded-2xl p-4 sm:p-5 shadow-xs">
                    <div class="text-[11px] sm:text-xs font-bold uppercase tracking-wider text-slate-400">Supervisor Review</div>
                    <div class="text-2xl sm:text-3xl font-extrabold text-amber-500 mt-1.5" id="ws-stat-review">0</div>
                    <div class="text-[11px] sm:text-xs text-amber-600 font-semibold mt-1">Gatekeeper Triage</div>
                </div>
                <div class="bg-white border border-slate-200 rounded-2xl p-4 sm:p-5 shadow-xs">
                    <div class="text-[11px] sm:text-xs font-bold uppercase tracking-wider text-slate-400">In Workshop</div>
                    <div class="text-2xl sm:text-3xl font-extrabold text-indigo-600 mt-1.5" id="ws-stat-floor">0</div>
                    <div class="text-[11px] sm:text-xs text-indigo-600 font-semibold mt-1">Floor Wrenching</div>
                </div>
                <div class="bg-white border border-slate-200 rounded-2xl p-4 sm:p-5 shadow-xs">
                    <div class="text-[11px] sm:text-xs font-bold uppercase tracking-wider text-slate-400">Awaiting Spares</div>
                    <div class="text-2xl sm:text-3xl font-extrabold text-rose-500 mt-1.5" id="ws-stat-parts">0</div>
                    <div class="text-[11px] sm:text-xs text-rose-600 font-semibold mt-1">Purchasing Queue</div>
                </div>
                <div class="bg-white border border-slate-200 rounded-2xl p-4 sm:p-5 shadow-xs col-span-2 sm:col-span-1">
                    <div class="text-[11px] sm:text-xs font-bold uppercase tracking-wider text-slate-400">QC Road-Test</div>
                    <div class="text-2xl sm:text-3xl font-extrabold text-emerald-500 mt-1.5" id="ws-stat-qc">0</div>
                    <div class="text-[11px] sm:text-xs text-emerald-600 font-semibold mt-1">Awaiting Sign-off</div>
                </div>
            </div>

            <!-- Fleet Table Section -->
            <div class="bg-white border border-slate-200 rounded-2xl shadow-xs overflow-hidden">
                <div class="p-4 sm:p-5 border-b border-slate-200 flex flex-col md:flex-row items-stretch md:items-center justify-between gap-3 sm:gap-4 bg-slate-50/50">
                    <div class="flex flex-col sm:flex-row flex-wrap items-stretch sm:items-center gap-2 sm:gap-3 w-full md:w-auto">
                        <input type="text" id="ws-search" placeholder="🔍 Search truck #, plate, fault notes..." oninput="filterFleetTable()" class="bg-white border border-slate-300 rounded-xl px-4 py-2.5 sm:py-2 text-xs font-medium text-slate-800 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-blue-500 w-full sm:w-64">
                        
                        <!-- Mechanic Filter -->
                        <select id="ws-mech-filter" onchange="filterFleetTable()" class="bg-white border border-slate-300 rounded-xl px-3 py-2.5 sm:py-2 text-xs font-medium text-slate-700 focus:outline-none focus:ring-2 focus:ring-blue-500 w-full sm:w-auto">
                            <option value="ALL">All Mechanics</option>
                        </select>

                        <!-- Status Filter -->
                        <select id="ws-status-filter" onchange="filterFleetTable()" class="bg-white border border-slate-300 rounded-xl px-3 py-2.5 sm:py-2 text-xs font-medium text-slate-700 focus:outline-none focus:ring-2 focus:ring-blue-500 w-full sm:w-auto">
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
                        <span id="ws-count-badge" class="bg-blue-50 text-blue-700 border border-blue-200 text-xs font-bold px-3 py-1.5 rounded-full">
                            Showing 0 vehicles
                        </span>
                    </div>
                </div>

                <!-- Swipe hint on mobile -->
                <div class="block md:hidden text-[11px] text-slate-400 px-4 py-1.5 bg-slate-50 border-b border-slate-100 flex items-center justify-between">
                    <span>👉 Swipe horizontally for full table</span>
                    <span class="font-mono text-slate-400">⇄</span>
                </div>

                <div class="overflow-x-auto">
                    <table class="w-full text-left text-xs min-w-[760px]">
                        <thead class="bg-slate-100/75 text-slate-500 font-bold uppercase tracking-wider border-b border-slate-200">
                            <tr>
                                <th class="px-4 sm:px-5 py-3.5">Ticket #</th>
                                <th class="px-4 sm:px-5 py-3.5">Truck & Plate</th>
                                <th class="px-4 sm:px-5 py-3.5">Vehicle Model</th>
                                <th class="px-4 sm:px-5 py-3.5">Fault Category & Description</th>
                                <th class="px-4 sm:px-5 py-3.5">Logged By</th>
                                <th class="px-4 sm:px-5 py-3.5">Mechanic & ETA</th>
                                <th class="px-4 sm:px-5 py-3.5">Parts Requisition</th>
                                <th class="px-4 sm:px-5 py-3.5">Costing</th>
                                <th class="px-4 sm:px-5 py-3.5">Status & QC</th>
                            </tr>
                        </thead>
                        <tbody id="ws-table-body" class="divide-y divide-slate-200 text-slate-700"></tbody>
                    </table>
                </div>
            </div>
        </div>
    </main>

    <script>
        let cachedData = null;
        let isRefreshing = false;

        function showToast(msg, icon = '✅') {
            const toast = document.getElementById('toast');
            document.getElementById('toastMsg').textContent = msg;
            document.getElementById('toastIcon').textContent = icon;
            toast.classList.remove('translate-y-20', 'opacity-0');
            toast.classList.add('translate-y-0', 'opacity-100');
            setTimeout(() => {
                toast.classList.remove('translate-y-0', 'opacity-100');
                toast.classList.add('translate-y-20', 'opacity-0');
            }, 2500);
        }

        function switchDomain(domain) {
            document.querySelectorAll('.tab-btn').forEach(btn => btn.classList.remove('active'));
            document.querySelectorAll('.domain-view').forEach(view => view.classList.remove('active'));

            const targetBtn = document.getElementById('btn-tab-' + domain);
            const targetView = document.getElementById('view-' + domain);
            if (targetBtn && targetView) {
                targetBtn.classList.add('active');
                targetView.classList.add('active');
                window.location.hash = domain;
            }
        }

        async function manualRefresh() {
            if (isRefreshing) return;
            isRefreshing = true;

            const mIcon = document.getElementById('mobileRefreshIcon');
            const dIcon = document.getElementById('desktopRefreshIcon');
            if (mIcon) mIcon.classList.add('spinning');
            if (dIcon) dIcon.classList.add('spinning');

            try {
                await fetchDashboard();
                showToast('Live dashboard refreshed!');
            } catch (err) {
                showToast('Failed to refresh data', '⚠️');
            } finally {
                setTimeout(() => {
                    if (mIcon) mIcon.classList.remove('spinning');
                    if (dIcon) dIcon.classList.remove('spinning');
                    isRefreshing = false;
                }, 600);
            }
        }

        async function handleLogout() {
            try {
                await fetch('/api/logout', { method: 'POST' });
            } catch (e) {}
            window.location.href = '/login';
        }

        async function fetchDashboard() {
            try {
                const res = await fetch('/api/dashboard/data');
                if (res.status === 401) {
                    window.location.href = '/login';
                    return;
                }
                const data = await res.json();
                cachedData = data;

                if (data.user) {
                    const uName = document.getElementById('userDisplayName');
                    if (uName) uName.textContent = data.user.name;
                    const uRole = document.getElementById('userRoleBadge');
                    if (uRole) uRole.innerHTML = `<span class="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse"></span> ${data.user.role.replace('_', ' ')}`;
                }

                renderIT(data.it);
                renderProjects(data.projects);
                renderLogistics(data.logistics);

                const hash = window.location.hash.replace('#', '');
                if (['it', 'projects', 'logistics'].includes(hash)) {
                    switchDomain(hash);
                }
            } catch (err) {
                console.error('Error loading dashboard:', err);
            }
        }

        function renderIT(it) {
            if (!it) return;
            document.getElementById('it-stat-total').textContent = it.stats.total;
            document.getElementById('it-stat-active').textContent = it.stats.open + it.stats.in_progress;
            document.getElementById('it-stat-resolved').textContent = it.stats.resolved + it.stats.closed;
            document.getElementById('it-stat-avg-time').textContent = it.stats.avg_resolution;

            // Render IT Admin SLA Cards
            const adminContainer = document.getElementById('it-admin-cards');
            adminContainer.innerHTML = it.admins.map(a => `
                <div class="bg-slate-50 border border-slate-200 rounded-xl p-3.5 sm:p-4 flex items-center justify-between">
                    <div>
                        <div class="font-extrabold text-slate-900 text-xs sm:text-sm">${a.name}</div>
                        <div class="text-[10px] sm:text-[11px] text-slate-500 font-mono">+${a.phone}</div>
                        <div class="mt-2 flex items-center gap-1.5">
                            <span class="bg-amber-100 text-amber-800 text-[10px] font-bold px-2 py-0.5 rounded">${a.pending} Pending</span>
                            <span class="bg-emerald-100 text-emerald-800 text-[10px] font-bold px-2 py-0.5 rounded">${a.resolved} Solved</span>
                        </div>
                    </div>
                    <div class="text-right">
                        <div class="text-sm sm:text-base font-extrabold text-blue-600">${a.sla_pct}% SLA</div>
                        <div class="text-[10px] sm:text-[11px] text-slate-500 font-medium">Avg: ${a.avg_time}</div>
                    </div>
                </div>
            `).join('');

            // Populate Admin Filter
            const adminFilter = document.getElementById('it-admin-filter');
            const currentSelected = adminFilter.value;
            const adminNames = [...new Set(it.records.map(r => r.assigned_admin))].filter(Boolean);
            adminFilter.innerHTML = '<option value="ALL">All Support Admins</option>' + adminNames.map(name => `
                <option value="${name}" ${currentSelected === name ? 'selected' : ''}>${name}</option>
            `).join('');

            // Render Category Issue Tree
            const treeContainer = document.getElementById('it-category-tree');
            if (it.category_tree && it.category_tree.length > 0) {
                treeContainer.innerHTML = it.category_tree.map(cat => `
                    <div class="border border-slate-200 rounded-xl overflow-hidden bg-slate-50/50">
                        <div class="p-3 sm:p-3.5 bg-slate-100/80 font-extrabold text-xs text-slate-900 flex items-center justify-between">
                            <span>📁 ${cat.category_name}</span>
                            <span class="bg-blue-100 text-blue-800 px-2 py-0.5 rounded-full text-[10px] font-bold">${cat.count} tickets</span>
                        </div>
                        <div class="p-3 space-y-2 text-xs">
                            ${cat.subcategories.map(sub => `
                                <div class="pl-2.5 sm:pl-3 border-l-2 border-slate-300">
                                    <div class="font-bold text-slate-700 flex items-center justify-between text-xs">
                                        <span>↳ ${sub.subcategory_name}</span>
                                        <span class="text-slate-400 font-medium text-[11px]">${sub.count} logs</span>
                                    </div>
                                    <div class="pl-2.5 sm:pl-3 mt-1 space-y-0.5 text-[11px] text-slate-500">
                                        ${sub.issues.map(iss => `
                                            <div class="flex items-center justify-between py-0.5">
                                                <span>• ${iss.issue_name}</span>
                                                <span class="font-mono text-slate-600 font-bold">${iss.count}</span>
                                            </div>
                                        `).join('')}
                                    </div>
                                </div>
                            `).join('')}
                        </div>
                    </div>
                `).join('');
            } else {
                treeContainer.innerHTML = '<div class="text-xs text-slate-400 p-3">No category issues logged yet.</div>';
            }

            filterITTable();
        }

        function filterITTable() {
            if (!cachedData || !cachedData.it) return;
            const q = document.getElementById('it-search').value.toLowerCase().trim();
            const statusFilter = document.getElementById('it-status-filter').value;
            const adminFilter = document.getElementById('it-admin-filter').value;

            const records = cachedData.it.records.filter(r => {
                const matchesQ = !q || r.ticket_number.toLowerCase().includes(q) ||
                                 r.employee_name.toLowerCase().includes(q) ||
                                 r.issue.toLowerCase().includes(q) ||
                                 r.description.toLowerCase().includes(q) ||
                                 r.category.toLowerCase().includes(q);
                const matchesStatus = statusFilter === 'ALL' || r.status === statusFilter;
                const matchesAdmin = adminFilter === 'ALL' || r.assigned_admin === adminFilter;
                return matchesQ && matchesStatus && matchesAdmin;
            });

            // Update Dynamic Count Badge
            document.getElementById('it-count-badge').textContent = `Showing ${records.length} of ${cachedData.it.records.length} tickets`;

            const tbody = document.getElementById('it-table-body');
            tbody.innerHTML = records.map(r => {
                let statusBadge = 'bg-amber-100 text-amber-800 border-amber-200';
                if (r.status === 'Resolved' || r.status === 'Closed') statusBadge = 'bg-emerald-100 text-emerald-800 border-emerald-200';
                else if (r.status === 'In Progress') statusBadge = 'bg-blue-100 text-blue-800 border-blue-200';

                let pBadge = 'bg-slate-100 text-slate-700';
                if (r.priority === 'Urgent') pBadge = 'bg-red-100 text-red-700 font-bold';
                else if (r.priority === 'High') pBadge = 'bg-amber-100 text-amber-800 font-bold';

                return `
                    <tr class="hover:bg-slate-50/80 transition">
                        <td class="px-4 sm:px-5 py-3 sm:py-3.5 font-mono font-bold text-blue-600">${r.ticket_number}</td>
                        <td class="px-4 sm:px-5 py-3 sm:py-3.5"><strong>${r.employee_name}</strong><br><small class="text-slate-400 font-mono">+${r.employee_phone}</small></td>
                        <td class="px-4 sm:px-5 py-3 sm:py-3.5">${r.department}<br><small class="text-slate-500 font-medium">📍 ${r.location}</small></td>
                        <td class="px-4 sm:px-5 py-3 sm:py-3.5"><strong>${r.category}</strong> ➔ ${r.subcategory}<br><small class="text-slate-500">${r.issue}</small></td>
                        <td class="px-4 sm:px-5 py-3 sm:py-3.5"><span class="px-2 py-0.5 rounded text-[10px] ${pBadge}">${r.priority}</span></td>
                        <td class="px-4 sm:px-5 py-3 sm:py-3.5"><span class="px-2.5 py-1 rounded-full text-[11px] font-bold border ${statusBadge}">${r.status}</span></td>
                        <td class="px-4 sm:px-5 py-3 sm:py-3.5 font-medium">${r.assigned_admin}</td>
                        <td class="px-4 sm:px-5 py-3 sm:py-3.5 font-mono font-bold">${r.resolution_time}</td>
                    </tr>
                `;
            }).join('');
        }

        function renderProjects(proj) {
            if (!proj) return;
            document.getElementById('proj-stat-total').textContent = proj.stats.total;
            document.getElementById('proj-stat-active').textContent = proj.stats.open + proj.stats.in_progress;
            document.getElementById('proj-stat-completed').textContent = proj.stats.resolved + proj.stats.closed;
            document.getElementById('proj-stat-locations').textContent = proj.stats.locations_count;

            // Populate Location & Admin Filter
            const locFilter = document.getElementById('proj-loc-filter');
            const currentLoc = locFilter.value;
            const locations = [...new Set(proj.records.map(r => r.location))].filter(Boolean);
            locFilter.innerHTML = '<option value="ALL">All Branches & Yards</option>' + locations.map(loc => `
                <option value="${loc}" ${currentLoc === loc ? 'selected' : ''}>${loc}</option>
            `).join('');

            const adminFilter = document.getElementById('proj-admin-filter');
            const currentAdmin = adminFilter.value;
            const admins = [...new Set(proj.records.map(r => r.assigned_admin))].filter(Boolean);
            adminFilter.innerHTML = '<option value="ALL">All Project Leads</option>' + admins.map(a => `
                <option value="${a}" ${currentAdmin === a ? 'selected' : ''}>${a}</option>
            `).join('');

            filterProjectsTable();
        }

        function filterProjectsTable() {
            if (!cachedData || !cachedData.projects) return;
            const q = document.getElementById('proj-search').value.toLowerCase().trim();
            const locFilter = document.getElementById('proj-loc-filter').value;
            const adminFilter = document.getElementById('proj-admin-filter').value;
            const statusFilter = document.getElementById('proj-status-filter').value;

            const records = cachedData.projects.records.filter(r => {
                const matchesQ = !q || r.ticket_number.toLowerCase().includes(q) ||
                                 r.location.toLowerCase().includes(q) ||
                                 r.description.toLowerCase().includes(q) ||
                                 r.category.toLowerCase().includes(q);
                const matchesLoc = locFilter === 'ALL' || r.location === locFilter;
                const matchesAdmin = adminFilter === 'ALL' || r.assigned_admin === adminFilter;
                const matchesStatus = statusFilter === 'ALL' || r.status === statusFilter;
                return matchesQ && matchesLoc && matchesAdmin && matchesStatus;
            });

            document.getElementById('proj-count-badge').textContent = `Showing ${records.length} of ${cachedData.projects.records.length} tickets`;

            const tbody = document.getElementById('proj-table-body');
            tbody.innerHTML = records.map(r => {
                let statusBadge = 'bg-amber-100 text-amber-800 border-amber-200';
                if (r.status === 'Resolved' || r.status === 'Closed') statusBadge = 'bg-emerald-100 text-emerald-800 border-emerald-200';
                else if (r.status === 'In Progress') statusBadge = 'bg-blue-100 text-blue-800 border-blue-200';

                return `
                    <tr class="hover:bg-slate-50/80 transition">
                        <td class="px-4 sm:px-5 py-3 sm:py-3.5 font-mono font-bold text-blue-600">${r.ticket_number}</td>
                        <td class="px-4 sm:px-5 py-3 sm:py-3.5"><strong>${r.employee_name}</strong><br><small class="text-slate-400 font-mono">+${r.employee_phone}</small></td>
                        <td class="px-4 sm:px-5 py-3 sm:py-3.5 font-bold text-slate-800">📍 ${r.location}</td>
                        <td class="px-4 sm:px-5 py-3 sm:py-3.5"><strong>${r.category}</strong><br><small class="text-slate-500">${r.description}</small></td>
                        <td class="px-4 sm:px-5 py-3 sm:py-3.5"><span class="px-2.5 py-1 rounded-full text-[11px] font-bold border ${statusBadge}">${r.status}</span></td>
                        <td class="px-4 sm:px-5 py-3 sm:py-3.5 font-medium">${r.assigned_admin}</td>
                        <td class="px-4 sm:px-5 py-3 sm:py-3.5 text-slate-500">${r.created_at}</td>
                    </tr>
                `;
            }).join('');
        }

        function renderLogistics(log) {
            if (!log) return;
            document.getElementById('ws-stat-fleet').textContent = log.fleet_count || 39;
            document.getElementById('ws-stat-review').textContent = log.stats.under_review;
            document.getElementById('ws-stat-floor').textContent = log.stats.in_workshop;
            document.getElementById('ws-stat-parts').textContent = log.stats.awaiting_parts;
            document.getElementById('ws-stat-qc').textContent = log.stats.awaiting_qc;

            // Populate Mechanics Filter
            const mechFilter = document.getElementById('ws-mech-filter');
            const currentMech = mechFilter.value;
            const mechs = [...new Set(log.records.map(r => r.assigned_mechanic))].filter(Boolean);
            mechFilter.innerHTML = '<option value="ALL">All Mechanics</option>' + mechs.map(m => `
                <option value="${m}" ${currentMech === m ? 'selected' : ''}>${m}</option>
            `).join('');

            filterFleetTable();
        }

        function filterFleetTable() {
            if (!cachedData || !cachedData.logistics) return;
            const q = document.getElementById('ws-search').value.toLowerCase().trim();
            const statusFilter = document.getElementById('ws-status-filter').value;
            const mechFilter = document.getElementById('ws-mech-filter').value;

            const records = cachedData.logistics.records.filter(r => {
                const matchesQ = !q || r.ticket_number.toLowerCase().includes(q) ||
                                 r.truck_number.toLowerCase().includes(q) ||
                                 r.plate_number.toLowerCase().includes(q) ||
                                 r.description.toLowerCase().includes(q) ||
                                 r.category.toLowerCase().includes(q);
                const matchesStatus = statusFilter === 'ALL' || r.status === statusFilter;
                const matchesMech = mechFilter === 'ALL' || r.assigned_mechanic === mechFilter;
                return matchesQ && matchesStatus && matchesMech;
            });

            document.getElementById('ws-count-badge').textContent = `Showing ${records.length} of ${cachedData.logistics.records.length} vehicles`;

            const tbody = document.getElementById('ws-table-body');
            tbody.innerHTML = records.map(r => {
                let statusBadge = 'bg-blue-100 text-blue-800 border-blue-200';
                if (r.status === 'UNDER_REVIEW') statusBadge = 'bg-amber-100 text-amber-800 border-amber-200';
                else if (r.status === 'CLOSED') statusBadge = 'bg-slate-100 text-slate-700 border-slate-300';
                else if (r.status === 'REWORK_REQUIRED') statusBadge = 'bg-red-100 text-red-700 border-red-200';
                else if (r.status === 'AWAITING_TEST') statusBadge = 'bg-emerald-100 text-emerald-800 border-emerald-200';

                return `
                    <tr class="hover:bg-slate-50/80 transition">
                        <td class="px-4 sm:px-5 py-3 sm:py-3.5 font-mono font-bold text-blue-600">${r.ticket_number}</td>
                        <td class="px-4 sm:px-5 py-3 sm:py-3.5"><strong>Truck #${r.truck_number}</strong><br><small class="text-slate-400 font-mono">${r.plate_number}</small></td>
                        <td class="px-4 sm:px-5 py-3 sm:py-3.5 font-medium text-slate-800">${r.truck_model}</td>
                        <td class="px-4 sm:px-5 py-3 sm:py-3.5"><strong>${r.category}</strong><br><small class="text-slate-500">${r.description.substring(0, 45)}...</small></td>
                        <td class="px-4 sm:px-5 py-3 sm:py-3.5">${r.logged_by}</td>
                        <td class="px-4 sm:px-5 py-3 sm:py-3.5"><strong>${r.assigned_mechanic}</strong><br><small class="text-blue-600 font-semibold">⏱️ ETA: ${r.eta}</small></td>
                        <td class="px-4 sm:px-5 py-3 sm:py-3.5"><small class="bg-amber-50 text-amber-800 border border-amber-200 px-2 py-0.5 rounded font-medium">📦 ${r.parts_status}</small></td>
                        <td class="px-4 sm:px-5 py-3 sm:py-3.5 font-bold font-mono text-slate-900">${r.costing}</td>
                        <td class="px-4 sm:px-5 py-3 sm:py-3.5">
                            <span class="px-2.5 py-1 rounded-full text-[10px] font-bold border ${statusBadge}">${r.status.replace('_', ' ')}</span><br>
                            <small class="text-slate-400 mt-1 block">QC: ${r.qc_result}</small>
                        </td>
                    </tr>
                `;
            }).join('');
        }

        fetchDashboard();
        setInterval(fetchDashboard, 15000);
    </script>
</body>
</html>"""
    return HTMLResponse(content=html_content)
