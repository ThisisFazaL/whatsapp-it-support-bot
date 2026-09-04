import logging
import datetime
from fastapi import APIRouter, Depends, Request, Response, Form, HTTPException, status
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

SUPPORT_ADMIN_PHONES = {"263718627526", "263788843579", "263780100503", "263780099291", "263771333602"}

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
    """Renders sleek glassmorphic login page with Tagoneswa branding."""
    user = get_current_user_from_request(request)
    if user:
        return RedirectResponse(url="/dashboard", status_code=status.HTTP_302_FOUND)

    html_content = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Tagoneswa Enterprise Portal — Secure Login</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&display=swap" rel="stylesheet">
    <style>
        :root {
            --primary: #2563eb;
            --primary-dark: #1d4ed8;
            --bg-dark: #090d16;
            --card-bg: rgba(17, 24, 39, 0.85);
            --border-color: rgba(255, 255, 255, 0.1);
            --text-main: #f3f4f6;
            --text-muted: #9ca3af;
        }
        * { box-sizing: border-box; margin: 0; padding: 0; font-family: 'Plus Jakarta Sans', sans-serif; }
        body {
            background: radial-gradient(circle at 50% 20%, #1e1b4b 0%, #090d16 80%);
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 20px;
            color: var(--text-main);
        }
        .login-card {
            background: var(--card-bg);
            backdrop-filter: blur(20px);
            border: 1px solid var(--border-color);
            border-radius: 24px;
            padding: 40px;
            width: 100%;
            max-width: 440px;
            box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.6);
            animation: fadeIn 0.5s ease-out;
        }
        @keyframes fadeIn {
            from { opacity: 0; transform: translateY(20px); }
            to { opacity: 1; transform: translateY(0); }
        }
        .brand-header {
            text-align: center;
            margin-bottom: 32px;
        }
        .brand-badge {
            display: inline-flex;
            align-items: center;
            gap: 8px;
            background: rgba(37, 99, 235, 0.15);
            border: 1px solid rgba(37, 99, 235, 0.3);
            color: #60a5fa;
            padding: 6px 14px;
            border-radius: 9999px;
            font-size: 0.82rem;
            font-weight: 600;
            margin-bottom: 16px;
        }
        .brand-title {
            font-size: 1.65rem;
            font-weight: 800;
            letter-spacing: -0.02em;
            background: linear-gradient(135deg, #ffffff 0%, #94a3b8 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            margin-bottom: 6px;
        }
        .brand-desc {
            color: var(--text-muted);
            font-size: 0.88rem;
        }
        .form-group {
            margin-bottom: 20px;
        }
        .form-label {
            display: block;
            font-size: 0.84rem;
            font-weight: 600;
            color: #e2e8f0;
            margin-bottom: 8px;
        }
        .input-wrapper {
            position: relative;
        }
        .form-input {
            width: 100%;
            background: rgba(15, 23, 42, 0.7);
            border: 1px solid rgba(255, 255, 255, 0.12);
            border-radius: 12px;
            padding: 13px 16px;
            color: #ffffff;
            font-size: 0.95rem;
            transition: all 0.2s;
        }
        .form-input:focus {
            outline: none;
            border-color: #3b82f6;
            box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.25);
            background: rgba(15, 23, 42, 0.95);
        }
        .toggle-pw {
            position: absolute;
            right: 14px;
            top: 50%;
            transform: translateY(-50%);
            background: none;
            border: none;
            color: var(--text-muted);
            cursor: pointer;
            font-size: 0.85rem;
        }
        .submit-btn {
            width: 100%;
            background: linear-gradient(135deg, #2563eb 0%, #1d4ed8 100%);
            color: #ffffff;
            border: none;
            border-radius: 12px;
            padding: 14px;
            font-size: 0.98rem;
            font-weight: 700;
            cursor: pointer;
            transition: all 0.2s;
            box-shadow: 0 10px 15px -3px rgba(37, 99, 235, 0.4);
            margin-top: 8px;
        }
        .submit-btn:hover {
            transform: translateY(-1px);
            box-shadow: 0 14px 20px -3px rgba(37, 99, 235, 0.5);
        }
        .submit-btn:active { transform: translateY(0); }
        .alert-error {
            background: rgba(239, 68, 68, 0.15);
            border: 1px solid rgba(239, 68, 68, 0.3);
            color: #f87171;
            padding: 12px 16px;
            border-radius: 12px;
            font-size: 0.85rem;
            margin-bottom: 20px;
            display: none;
        }
        .card-footer {
            margin-top: 28px;
            text-align: center;
            font-size: 0.78rem;
            color: #64748b;
        }
    </style>
</head>
<body>
    <div class="login-card">
        <div class="brand-header">
            <div class="brand-badge">🔒 Tagoneswa Security</div>
            <h1 class="brand-title">Enterprise Console</h1>
            <p class="brand-desc">IT Support • Building Projects • Fleet Workshop</p>
        </div>

        <div id="errorBox" class="alert-error"></div>

        <form id="loginForm">
            <div class="form-group">
                <label class="form-label" for="username">Username</label>
                <input class="form-input" type="text" id="username" name="username" placeholder="e.g. admin, logistics" required autofocus autocomplete="username">
            </div>

            <div class="form-group">
                <label class="form-label" for="password">Password</label>
                <div class="input-wrapper">
                    <input class="form-input" type="password" id="password" name="password" placeholder="••••••••••••" required autocomplete="current-password">
                    <button type="button" class="toggle-pw" onclick="togglePassword()">Show</button>
                </div>
            </div>

            <button type="submit" class="submit-btn" id="loginBtn">Authenticate & Enter →</button>
        </form>

        <div class="card-footer">
            Tagoneswa Holdings • Internal Management System
        </div>
    </div>

    <script>
        function togglePassword() {
            const pw = document.getElementById('password');
            const btn = document.querySelector('.toggle-pw');
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
            errBox.style.display = 'none';
            btn.disabled = true;
            btn.textContent = 'Verifying...';

            const username = document.getElementById('username').value.trim();
            const password = document.getElementById('password').value.trim();

            try {
                const res = await fetch('/login', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
                    body: new URLSearchParams({ username, password })
                });

                const data = await res.json();
                if (res.ok && data.status === 'success') {
                    window.location.href = data.redirect || '/dashboard';
                } else {
                    errBox.textContent = data.detail || 'Invalid username or password. Please try again.';
                    errBox.style.display = 'block';
                    btn.disabled = false;
                    btn.textContent = 'Authenticate & Enter →';
                }
            } catch (err) {
                errBox.textContent = 'Connection error. Please check your network.';
                errBox.style.display = 'block';
                btn.disabled = false;
                btn.textContent = 'Authenticate & Enter →';
            }
        });
    </script>
</body>
</html>"""
    return HTMLResponse(content=html_content)

@router.post("/login")
async def process_login(request: Request, response: Response):
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
    
    # Set HttpOnly, Secure cookie
    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        max_age=SESSION_MAX_AGE,
        httponly=True,
        samesite="lax",
        secure=False # Set to True if strictly HTTPS
    )

    # Determine default redirect tab
    default_tab = "logistics" if user["role"] == "LOGISTICS_ADMIN" else ("projects" if user["role"] == "PROJECTS_ADMIN" else "it")
    return {"status": "success", "redirect": f"/dashboard#{default_tab}", "user": user["name"], "role": user["role"]}

@router.get("/logout")
async def logout(response: Response):
    """Invalidates session and redirects to login."""
    response.delete_cookie(COOKIE_NAME)
    return RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)

# -------------------------------------------------------------
# Data API: Complete 3-Domain Partitioned Metrics & Records
# -------------------------------------------------------------
@router.get("/api/dashboard/data")
async def get_dashboard_data(request: Request, db: AsyncSession = Depends(get_db)):
    """
    Returns complete live operational metrics partitioned cleanly across:
    1. IT Support
    2. Building Projects & Maintenance
    3. Workshop & Fleet Logistics
    """
    user = get_current_user_from_request(request)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized session. Please log in.")

    # 1. Fetch IT Support Admins
    admins_stmt = select(SupportAdmin).where(
        SupportAdmin.active == True,
        SupportAdmin.phone.in_(SUPPORT_ADMIN_PHONES)
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
    # Process IT Support Records
    # -----------------------------
    it_records = []
    it_stats = {"total": len(it_tickets), "open": 0, "in_progress": 0, "resolved": 0, "closed": 0, "avg_resolution": "--"}
    it_res_times = []
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
            "category": t.category.category_name if t.category else "Hardware",
            "subcategory": t.subcategory.subcategory_name if t.subcategory else "General",
            "issue": t.issue_type.issue_name if t.issue_type else "Custom Issue",
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
        it_admin_performance.append({
            "name": ast["full_name"], "phone": ast["phone"],
            "pending": ast["pending_count"], "resolved": ast["resolved_count"],
            "total": ast["total_assigned"], "avg_time": format_duration(avg_s) if avg_s > 0 else "--"
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
            "admins": it_admin_performance
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
    """Renders the high-end 3-Domain Operations Dashboard."""
    user = get_current_user_from_request(request)
    if not user:
        return RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)

    html_content = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Tagoneswa Operations Console</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&family=JetBrains+Mono:wght@500;700&display=swap" rel="stylesheet">
    <style>
        :root {
            --bg-body: #0a0e1a;
            --bg-card: rgba(17, 24, 39, 0.75);
            --bg-card-hover: rgba(30, 41, 59, 0.85);
            --border: rgba(255, 255, 255, 0.08);
            --border-highlight: rgba(59, 130, 246, 0.4);
            --text-main: #f8fafc;
            --text-muted: #94a3b8;
            --primary: #3b82f6;
            --accent-green: #10b981;
            --accent-amber: #f59e0b;
            --accent-purple: #8b5cf6;
            --accent-rose: #f43f5e;
        }
        * { box-sizing: border-box; margin: 0; padding: 0; font-family: 'Plus Jakarta Sans', sans-serif; }
        body {
            background-color: var(--bg-body);
            background-image: 
                radial-gradient(at 10% 10%, rgba(37, 99, 235, 0.12) 0px, transparent 50%),
                radial-gradient(at 90% 90%, rgba(139, 92, 246, 0.1) 0px, transparent 50%);
            color: var(--text-main);
            min-height: 100vh;
            padding: 24px;
        }
        .container {
            max-width: 1600px;
            margin: 0 auto;
        }
        /* Top Navigation & Domain Switcher */
        .header {
            display: flex;
            align-items: center;
            justify-content: space-between;
            background: var(--bg-card);
            backdrop-filter: blur(16px);
            border: 1px solid var(--border);
            border-radius: 20px;
            padding: 16px 24px;
            margin-bottom: 24px;
            box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.3);
        }
        .brand-group {
            display: flex;
            align-items: center;
            gap: 14px;
        }
        .brand-logo {
            width: 44px;
            height: 44px;
            background: linear-gradient(135deg, #2563eb, #7c3aed);
            border-radius: 12px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 1.4rem;
            box-shadow: 0 8px 16px -4px rgba(37, 99, 235, 0.5);
        }
        .brand-text h1 {
            font-size: 1.25rem;
            font-weight: 800;
            letter-spacing: -0.02em;
        }
        .brand-text p {
            font-size: 0.8rem;
            color: var(--text-muted);
        }

        /* 3-Domain Switcher */
        .domain-switcher {
            display: flex;
            background: rgba(15, 23, 42, 0.8);
            border: 1px solid var(--border);
            padding: 5px;
            border-radius: 14px;
            gap: 4px;
        }
        .domain-btn {
            background: transparent;
            border: none;
            color: var(--text-muted);
            padding: 10px 20px;
            border-radius: 10px;
            font-size: 0.88rem;
            font-weight: 700;
            cursor: pointer;
            transition: all 0.2s;
            display: flex;
            align-items: center;
            gap: 8px;
        }
        .domain-btn:hover {
            color: #ffffff;
            background: rgba(255, 255, 255, 0.05);
        }
        .domain-btn.active {
            background: linear-gradient(135deg, #2563eb, #1d4ed8);
            color: #ffffff;
            box-shadow: 0 4px 12px rgba(37, 99, 235, 0.4);
        }

        .user-nav {
            display: flex;
            align-items: center;
            gap: 16px;
        }
        .user-pill {
            text-align: right;
        }
        .user-name {
            font-size: 0.88rem;
            font-weight: 700;
            color: #ffffff;
        }
        .user-role {
            font-size: 0.75rem;
            color: var(--accent-green);
        }
        .logout-btn {
            background: rgba(239, 68, 68, 0.15);
            border: 1px solid rgba(239, 68, 68, 0.3);
            color: #f87171;
            padding: 8px 16px;
            border-radius: 10px;
            font-size: 0.82rem;
            font-weight: 600;
            cursor: pointer;
            text-decoration: none;
            transition: all 0.2s;
        }
        .logout-btn:hover {
            background: rgba(239, 68, 68, 0.25);
            color: #ffffff;
        }

        /* Stats Grid */
        .stats-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
            gap: 20px;
            margin-bottom: 24px;
        }
        .stat-card {
            background: var(--bg-card);
            backdrop-filter: blur(12px);
            border: 1px solid var(--border);
            border-radius: 18px;
            padding: 20px 24px;
            position: relative;
            overflow: hidden;
            transition: transform 0.2s;
        }
        .stat-card:hover {
            transform: translateY(-2px);
            border-color: rgba(255, 255, 255, 0.15);
        }
        .stat-card::before {
            content: '';
            position: absolute;
            top: 0; left: 0; right: 0; height: 3px;
        }
        .stat-card.blue::before { background: #3b82f6; }
        .stat-card.amber::before { background: #f59e0b; }
        .stat-card.purple::before { background: #8b5cf6; }
        .stat-card.green::before { background: #10b981; }
        .stat-card.rose::before { background: #f43f5e; }

        .stat-label {
            font-size: 0.82rem;
            font-weight: 600;
            color: var(--text-muted);
            margin-bottom: 8px;
            text-transform: uppercase;
            letter-spacing: 0.04em;
        }
        .stat-value {
            font-size: 2rem;
            font-weight: 800;
            letter-spacing: -0.02em;
            color: #ffffff;
        }

        /* Team Performance Section */
        .section-title {
            font-size: 1.1rem;
            font-weight: 800;
            margin-bottom: 14px;
            display: flex;
            align-items: center;
            gap: 8px;
        }
        .team-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
            gap: 16px;
            margin-bottom: 24px;
        }
        .team-card {
            background: var(--bg-card);
            border: 1px solid var(--border);
            border-radius: 14px;
            padding: 16px 20px;
            display: flex;
            align-items: center;
            justify-content: space-between;
        }
        .team-info h4 {
            font-size: 0.95rem;
            font-weight: 700;
        }
        .team-info p {
            font-size: 0.78rem;
            color: var(--text-muted);
        }
        .team-metrics {
            text-align: right;
        }
        .team-badge {
            display: inline-block;
            padding: 3px 8px;
            border-radius: 6px;
            font-size: 0.75rem;
            font-weight: 700;
            background: rgba(16, 185, 129, 0.15);
            color: #34d399;
        }

        /* Filter Controls */
        .controls-bar {
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 16px;
            background: var(--bg-card);
            border: 1px solid var(--border);
            border-radius: 16px;
            padding: 14px 20px;
            margin-bottom: 20px;
        }
        .search-input {
            background: rgba(15, 23, 42, 0.8);
            border: 1px solid var(--border);
            border-radius: 10px;
            padding: 10px 16px;
            color: #ffffff;
            font-size: 0.88rem;
            width: 320px;
        }
        .search-input:focus {
            outline: none;
            border-color: #3b82f6;
        }
        .filter-select {
            background: rgba(15, 23, 42, 0.8);
            border: 1px solid var(--border);
            border-radius: 10px;
            padding: 10px 16px;
            color: #ffffff;
            font-size: 0.88rem;
            cursor: pointer;
        }

        /* Data Tables */
        .table-container {
            background: var(--bg-card);
            border: 1px solid var(--border);
            border-radius: 20px;
            overflow: hidden;
            box-shadow: 0 10px 30px -10px rgba(0, 0, 0, 0.4);
        }
        table {
            width: 100%;
            border-collapse: collapse;
            text-align: left;
        }
        th {
            background: rgba(15, 23, 42, 0.9);
            padding: 14px 18px;
            font-size: 0.78rem;
            font-weight: 700;
            color: var(--text-muted);
            text-transform: uppercase;
            letter-spacing: 0.05em;
            border-bottom: 1px solid var(--border);
        }
        td {
            padding: 16px 18px;
            font-size: 0.88rem;
            border-bottom: 1px solid rgba(255, 255, 255, 0.04);
            color: #cbd5e1;
        }
        tr:hover td {
            background: rgba(255, 255, 255, 0.02);
            color: #ffffff;
        }
        .ticket-badge {
            font-family: 'JetBrains Mono', monospace;
            font-size: 0.82rem;
            font-weight: 700;
            color: #60a5fa;
            background: rgba(37, 99, 235, 0.15);
            padding: 4px 8px;
            border-radius: 6px;
            border: 1px solid rgba(37, 99, 235, 0.3);
        }
        .status-pill {
            display: inline-flex;
            align-items: center;
            gap: 6px;
            padding: 4px 10px;
            border-radius: 9999px;
            font-size: 0.78rem;
            font-weight: 700;
        }
        .status-open { background: rgba(245, 158, 11, 0.15); color: #fbbf24; border: 1px solid rgba(245, 158, 11, 0.3); }
        .status-progress { background: rgba(59, 130, 246, 0.15); color: #60a5fa; border: 1px solid rgba(59, 130, 246, 0.3); }
        .status-resolved { background: rgba(16, 185, 129, 0.15); color: #34d399; border: 1px solid rgba(16, 185, 129, 0.3); }
        .status-closed { background: rgba(148, 163, 184, 0.15); color: #94a3b8; border: 1px solid rgba(148, 163, 184, 0.3); }
        .status-rework { background: rgba(239, 68, 68, 0.15); color: #f87171; border: 1px solid rgba(239, 68, 68, 0.3); }

        .domain-view { display: none; }
        .domain-view.active { display: block; animation: fadeIn 0.3s ease-out; }
    </style>
</head>
<body>
    <div class="container">
        <!-- Header -->
        <header class="header">
            <div class="brand-group">
                <div class="brand-logo">🚚</div>
                <div class="brand-text">
                    <h1>Tagoneswa Console</h1>
                    <p>Enterprise Multi-Domain Operations</p>
                </div>
            </div>

            <!-- 3 Domain Switcher -->
            <nav class="domain-switcher">
                <button class="domain-btn active" id="btn-tab-it" onclick="switchDomain('it')">
                    💻 IT Support
                </button>
                <button class="domain-btn" id="btn-tab-projects" onclick="switchDomain('projects')">
                    🏗️ Building Projects
                </button>
                <button class="domain-btn" id="btn-tab-logistics" onclick="switchDomain('logistics')">
                    🚚 Workshop & Fleet
                </button>
            </nav>

            <div class="user-nav">
                <div class="user-pill">
                    <div class="user-name" id="userDisplayName">Authorized User</div>
                    <div class="user-role" id="userRoleBadge">Online</div>
                </div>
                <a href="/logout" class="logout-btn">Log Out</a>
            </div>
        </header>

        <!-- ========================================================= -->
        <!-- TAB 1: IT SUPPORT -->
        <!-- ========================================================= -->
        <div id="view-it" class="domain-view active">
            <div class="stats-grid">
                <div class="stat-card blue">
                    <div class="stat-label">Total IT Tickets</div>
                    <div class="stat-value" id="it-stat-total">0</div>
                </div>
                <div class="stat-card amber">
                    <div class="stat-label">Open / In Progress</div>
                    <div class="stat-value" id="it-stat-active">0</div>
                </div>
                <div class="stat-card green">
                    <div class="stat-label">Resolved / Closed</div>
                    <div class="stat-value" id="it-stat-resolved">0</div>
                </div>
                <div class="stat-card purple">
                    <div class="stat-label">Avg Resolution Time</div>
                    <div class="stat-value" id="it-stat-avg-time">--</div>
                </div>
            </div>

            <div class="section-title">👨‍💻 IT Support Admins Performance</div>
            <div class="team-grid" id="it-admin-cards"></div>

            <div class="controls-bar">
                <input type="text" class="search-input" id="it-search" placeholder="🔍 Search employee, ticket #, issue..." oninput="filterITTable()">
                <select class="filter-select" id="it-status-filter" onchange="filterITTable()">
                    <option value="ALL">All Statuses</option>
                    <option value="Open">Open</option>
                    <option value="In Progress">In Progress</option>
                    <option value="Resolved">Resolved</option>
                    <option value="Closed">Closed</option>
                </select>
            </div>

            <div class="table-container">
                <table>
                    <thead>
                        <tr>
                            <th>Ticket #</th>
                            <th>Employee</th>
                            <th>Department & Location</th>
                            <th>Category & Issue</th>
                            <th>Status</th>
                            <th>Assigned Admin</th>
                            <th>Created</th>
                            <th>Solving Time</th>
                        </tr>
                    </thead>
                    <tbody id="it-table-body"></tbody>
                </table>
            </div>
        </div>

        <!-- ========================================================= -->
        <!-- TAB 2: BUILDING PROJECTS -->
        <!-- ========================================================= -->
        <div id="view-projects" class="domain-view">
            <div class="stats-grid">
                <div class="stat-card blue">
                    <div class="stat-label">Total Projects Tickets</div>
                    <div class="stat-value" id="proj-stat-total">0</div>
                </div>
                <div class="stat-card amber">
                    <div class="stat-label">Active Work Orders</div>
                    <div class="stat-value" id="proj-stat-active">0</div>
                </div>
                <div class="stat-card green">
                    <div class="stat-label">Completed Facilities</div>
                    <div class="stat-value" id="proj-stat-completed">0</div>
                </div>
                <div class="stat-card purple">
                    <div class="stat-label">Active Yards & Locations</div>
                    <div class="stat-value" id="proj-stat-locations">0</div>
                </div>
            </div>

            <div class="controls-bar">
                <input type="text" class="search-input" id="proj-search" placeholder="🔍 Search site, ticket #, repair..." oninput="filterProjectsTable()">
                <select class="filter-select" id="proj-status-filter" onchange="filterProjectsTable()">
                    <option value="ALL">All Statuses</option>
                    <option value="Open">Open</option>
                    <option value="In Progress">In Progress</option>
                    <option value="Closed">Closed</option>
                </select>
            </div>

            <div class="table-container">
                <table>
                    <thead>
                        <tr>
                            <th>Ticket #</th>
                            <th>Reporter</th>
                            <th>Site / Branch Location</th>
                            <th>Facility Category</th>
                            <th>Status</th>
                            <th>Assigned Lead</th>
                            <th>Created Date</th>
                        </tr>
                    </thead>
                    <tbody id="proj-table-body"></tbody>
                </table>
            </div>
        </div>

        <!-- ========================================================= -->
        <!-- TAB 3: WORKSHOP & FLEET LOGISTICS -->
        <!-- ========================================================= -->
        <div id="view-logistics" class="domain-view">
            <div class="stats-grid">
                <div class="stat-card purple">
                    <div class="stat-label">Active Fleet Fleet Vehicles</div>
                    <div class="stat-value" id="ws-stat-fleet">39</div>
                </div>
                <div class="stat-card amber">
                    <div class="stat-label">Under Supervisor Review</div>
                    <div class="stat-value" id="ws-stat-review">0</div>
                </div>
                <div class="stat-card blue">
                    <div class="stat-label">In Workshop Floor</div>
                    <div class="stat-value" id="ws-stat-floor">0</div>
                </div>
                <div class="stat-card rose">
                    <div class="stat-label">Awaiting Spares / Parts</div>
                    <div class="stat-value" id="ws-stat-parts">0</div>
                </div>
                <div class="stat-card green">
                    <div class="stat-label">Awaiting QC Road-Test</div>
                    <div class="stat-value" id="ws-stat-qc">0</div>
                </div>
            </div>

            <div class="controls-bar">
                <input type="text" class="search-input" id="ws-search" placeholder="🔍 Search truck #, plate, fault notes..." oninput="filterFleetTable()">
                <select class="filter-select" id="ws-status-filter" onchange="filterFleetTable()">
                    <option value="ALL">All Workshop Stages</option>
                    <option value="UNDER_REVIEW">Under Review</option>
                    <option value="WITH_MECHANIC">With Mechanic</option>
                    <option value="AWAITING_PARTS">Awaiting Parts</option>
                    <option value="AWAITING_TEST">Awaiting QC Test</option>
                    <option value="REWORK_REQUIRED">Rework Required</option>
                    <option value="CLOSED">Closed / Returned to Fleet</option>
                </select>
            </div>

            <div class="table-container">
                <table>
                    <thead>
                        <tr>
                            <th>Ticket #</th>
                            <th>Truck & Plate</th>
                            <th>Vehicle Model</th>
                            <th>Fault Category</th>
                            <th>Logged By</th>
                            <th>Mechanic & ETA</th>
                            <th>Parts Requisition</th>
                            <th>Costing</th>
                            <th>Status & QC</th>
                        </tr>
                    </thead>
                    <tbody id="ws-table-body"></tbody>
                </table>
            </div>
        </div>
    </div>

    <script>
        let cachedData = null;

        function switchDomain(domain) {
            document.querySelectorAll('.domain-btn').forEach(btn => btn.classList.remove('active'));
            document.querySelectorAll('.domain-view').forEach(view => view.classList.remove('active'));

            const targetBtn = document.getElementById('btn-tab-' + domain);
            const targetView = document.getElementById('view-' + domain);
            if (targetBtn && targetView) {
                targetBtn.classList.add('active');
                targetView.classList.add('active');
                window.location.hash = domain;
            }
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

                // Update User Info
                if (data.user) {
                    document.getElementById('userDisplayName').textContent = data.user.name;
                    document.getElementById('userRoleBadge').textContent = data.user.role.replace('_', ' ');
                }

                renderIT(data.it);
                renderProjects(data.projects);
                renderLogistics(data.logistics);

                // Check URL hash for initial tab
                const hash = window.location.hash.replace('#', '');
                if (['it', 'projects', 'logistics'].includes(hash)) {
                    switchDomain(hash);
                }
            } catch (err) {
                console.error('Error loading dashboard data:', err);
            }
        }

        function renderIT(it) {
            if (!it) return;
            document.getElementById('it-stat-total').textContent = it.stats.total;
            document.getElementById('it-stat-active').textContent = it.stats.open + it.stats.in_progress;
            document.getElementById('it-stat-resolved').textContent = it.stats.resolved + it.stats.closed;
            document.getElementById('it-stat-avg-time').textContent = it.stats.avg_resolution;

            // Render IT Admins
            const adminContainer = document.getElementById('it-admin-cards');
            adminContainer.innerHTML = it.admins.map(a => `
                <div class="team-card">
                    <div class="team-info">
                        <h4>${a.name}</h4>
                        <p>+${a.phone}</p>
                    </div>
                    <div class="team-metrics">
                        <span class="team-badge">${a.resolved} Resolved</span>
                        <p style="font-size:0.75rem; color:var(--text-muted); margin-top:4px;">Avg: ${a.avg_time}</p>
                    </div>
                </div>
            `).join('');

            filterITTable();
        }

        function filterITTable() {
            if (!cachedData || !cachedData.it) return;
            const q = document.getElementById('it-search').value.toLowerCase();
            const statusFilter = document.getElementById('it-status-filter').value;
            const records = cachedData.it.records.filter(r => {
                const matchesQ = r.ticket_number.toLowerCase().includes(q) ||
                                 r.employee_name.toLowerCase().includes(q) ||
                                 r.issue.toLowerCase().includes(q) ||
                                 r.description.toLowerCase().includes(q);
                const matchesStatus = statusFilter === 'ALL' || r.status === statusFilter;
                return matchesQ && matchesStatus;
            });

            const tbody = document.getElementById('it-table-body');
            tbody.innerHTML = records.map(r => `
                <tr>
                    <td><span class="ticket-badge">${r.ticket_number}</span></td>
                    <td><strong>${r.employee_name}</strong><br><small style="color:var(--text-muted)">+${r.employee_phone}</small></td>
                    <td>${r.department}<br><small style="color:var(--text-muted)">📍 ${r.location}</small></td>
                    <td>${r.category}<br><small style="color:var(--text-muted)">${r.issue}</small></td>
                    <td><span class="status-pill status-${r.status.toLowerCase().replace(' ', '')}">${r.status}</span></td>
                    <td>${r.assigned_admin}</td>
                    <td>${r.created_at}</td>
                    <td><strong>${r.resolution_time}</strong></td>
                </tr>
            `).join('');
        }

        function renderProjects(proj) {
            if (!proj) return;
            document.getElementById('proj-stat-total').textContent = proj.stats.total;
            document.getElementById('proj-stat-active').textContent = proj.stats.open + proj.stats.in_progress;
            document.getElementById('proj-stat-completed').textContent = proj.stats.resolved + proj.stats.closed;
            document.getElementById('proj-stat-locations').textContent = proj.stats.locations_count;
            filterProjectsTable();
        }

        function filterProjectsTable() {
            if (!cachedData || !cachedData.projects) return;
            const q = document.getElementById('proj-search').value.toLowerCase();
            const statusFilter = document.getElementById('proj-status-filter').value;
            const records = cachedData.projects.records.filter(r => {
                const matchesQ = r.ticket_number.toLowerCase().includes(q) ||
                                 r.location.toLowerCase().includes(q) ||
                                 r.category.toLowerCase().includes(q) ||
                                 r.description.toLowerCase().includes(q);
                const matchesStatus = statusFilter === 'ALL' || r.status === statusFilter;
                return matchesQ && matchesStatus;
            });

            const tbody = document.getElementById('proj-table-body');
            tbody.innerHTML = records.map(r => `
                <tr>
                    <td><span class="ticket-badge">${r.ticket_number}</span></td>
                    <td><strong>${r.employee_name}</strong><br><small style="color:var(--text-muted)">+${r.employee_phone}</small></td>
                    <td>📍 <strong>${r.location}</strong></td>
                    <td>${r.category}<br><small style="color:var(--text-muted)">${r.subcategory}</small></td>
                    <td><span class="status-pill status-${r.status.toLowerCase().replace(' ', '')}">${r.status}</span></td>
                    <td>${r.assigned_admin}</td>
                    <td>${r.created_at}</td>
                </tr>
            `).join('');
        }

        function renderLogistics(log) {
            if (!log) return;
            document.getElementById('ws-stat-fleet').textContent = log.fleet_count || 39;
            document.getElementById('ws-stat-review').textContent = log.stats.under_review;
            document.getElementById('ws-stat-floor').textContent = log.stats.in_workshop;
            document.getElementById('ws-stat-parts').textContent = log.stats.awaiting_parts;
            document.getElementById('ws-stat-qc').textContent = log.stats.awaiting_qc;
            filterFleetTable();
        }

        function filterFleetTable() {
            if (!cachedData || !cachedData.logistics) return;
            const q = document.getElementById('ws-search').value.toLowerCase();
            const statusFilter = document.getElementById('ws-status-filter').value;
            const records = cachedData.logistics.records.filter(r => {
                const matchesQ = r.ticket_number.toLowerCase().includes(q) ||
                                 r.truck_number.toLowerCase().includes(q) ||
                                 r.plate_number.toLowerCase().includes(q) ||
                                 r.description.toLowerCase().includes(q) ||
                                 r.category.toLowerCase().includes(q);
                const matchesStatus = statusFilter === 'ALL' || r.status === statusFilter;
                return matchesQ && matchesStatus;
            });

            const tbody = document.getElementById('ws-table-body');
            tbody.innerHTML = records.map(r => {
                let statusClass = 'status-progress';
                if (r.status === 'UNDER_REVIEW') statusClass = 'status-open';
                else if (r.status === 'CLOSED') statusClass = 'status-closed';
                else if (r.status === 'REWORK_REQUIRED') statusClass = 'status-rework';
                else if (r.status === 'AWAITING_TEST') statusClass = 'status-resolved';

                return `
                    <tr>
                        <td><span class="ticket-badge">${r.ticket_number}</span></td>
                        <td><strong>Truck #${r.truck_number}</strong><br><small style="color:var(--text-muted)">${r.plate_number}</small></td>
                        <td>${r.truck_model}</td>
                        <td><strong>${r.category}</strong><br><small style="color:var(--text-muted)">${r.description.substring(0, 40)}...</small></td>
                        <td>${r.logged_by}</td>
                        <td><strong>${r.assigned_mechanic}</strong><br><small style="color:#60a5fa">⏱️ ETA: ${r.eta}</small></td>
                        <td><small style="color:#f59e0b">📦 ${r.parts_status}</small></td>
                        <td><strong>${r.costing}</strong></td>
                        <td>
                            <span class="status-pill ${statusClass}">${r.status.replace('_', ' ')}</span><br>
                            <small style="color:var(--text-muted)">QC: ${r.qc_result}</small>
                        </td>
                    </tr>
                `;
            }).join('');
        }

        // Initialize on load and poll every 10 seconds
        fetchDashboard();
        setInterval(fetchDashboard, 10000);
    </script>
</body>
</html>"""
    return HTMLResponse(content=html_content)
