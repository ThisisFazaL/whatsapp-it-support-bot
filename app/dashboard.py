import logging
import datetime
from fastapi import APIRouter, Depends, Response
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload

from app.database import (
    get_db, Ticket, MaintenanceTicket, TicketAssignment, MaintenanceTicketAssignment,
    SupportAdmin, Employee, Department, Location, Category, Subcategory, IssueType, Priority, TicketStatus
)

logger = logging.getLogger("dashboard")

router = APIRouter()

SUPPORT_ADMIN_PHONES = {"263718627526", "263788843579", "263780100503", "263780099291", "26377133602"}

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

@router.get("/api/dashboard/data")
async def get_dashboard_data(db: AsyncSession = Depends(get_db)):
    """
    Returns complete live executive metrics, support admin SLA breakdown,
    resolution times, and 100% full historical ticket records across IT & Maintenance tables.
    """
    # Fetch active support admins
    admins_stmt = select(SupportAdmin).where(
        SupportAdmin.active == True,
        SupportAdmin.phone.in_(SUPPORT_ADMIN_PHONES)
    )
    admins_res = await db.execute(admins_stmt)
    support_admins = admins_res.scalars().all()

    # Fetch all IT tickets
    it_stmt = (
        select(Ticket)
        .options(
            selectinload(Ticket.employee).selectinload(Employee.department),
            selectinload(Ticket.employee).selectinload(Employee.location),
            selectinload(Ticket.category),
            selectinload(Ticket.subcategory),
            selectinload(Ticket.issue_type),
            selectinload(Ticket.priority),
            selectinload(Ticket.status)
        )
    )
    it_tickets = (await db.execute(it_stmt)).scalars().all()

    # Fetch all Maintenance tickets
    maint_stmt = (
        select(MaintenanceTicket)
        .options(
            selectinload(MaintenanceTicket.employee).selectinload(Employee.department),
            selectinload(MaintenanceTicket.employee).selectinload(Employee.location),
            selectinload(MaintenanceTicket.category),
            selectinload(MaintenanceTicket.subcategory),
            selectinload(MaintenanceTicket.issue_type),
            selectinload(MaintenanceTicket.priority),
            selectinload(MaintenanceTicket.status)
        )
    )
    maint_tickets = (await db.execute(maint_stmt)).scalars().all()

    # Fetch all IT ticket assignments
    asg_stmt = (
        select(TicketAssignment)
        .options(selectinload(TicketAssignment.admin))
    )
    asgs = (await db.execute(asg_stmt)).scalars().all()
    asg_map = {f"IT_{a.ticket_id}": a.admin for a in asgs if a.admin}

    # Fetch all Maintenance ticket assignments
    m_asg_stmt = (
        select(MaintenanceTicketAssignment)
        .options(selectinload(MaintenanceTicketAssignment.admin))
    )
    m_asgs = (await db.execute(m_asg_stmt)).scalars().all()
    for ma in m_asgs:
        if ma.admin:
            asg_map[f"MAINT_{ma.ticket_id}"] = ma.admin

    tickets = list(it_tickets) + list(maint_tickets)
    tickets.sort(key=lambda t: t.created_at or datetime.datetime.min, reverse=True)

    now_utc = datetime.datetime.utcnow()
    today_str = now_utc.strftime("%Y-%m-%d")

    records = []
    total_count = len(tickets)
    open_count = 0
    in_progress_count = 0
    resolved_count = 0
    closed_count = 0
    today_count = 0

    all_resolution_times = []
    category_tree_map = {}

    # Initialize Admin Performance Map ONLY for Kevin, Ellias, Faisal
    admin_stats_map = {}
    for sa in support_admins:
        admin_stats_map[sa.admin_id] = {
            "admin_id": sa.admin_id,
            "full_name": sa.full_name,
            "phone": sa.phone,
            "pending_count": 0,
            "resolved_count": 0,
            "total_assigned": 0,
            "resolution_seconds_list": []
        }

    for t in tickets:
        status_name = t.status.status_name if t.status else "Open"
        if t.status_id == 1:
            open_count += 1
        elif t.status_id == 2:
            in_progress_count += 1
        elif t.status_id == 3:
            resolved_count += 1
        elif t.status_id == 4:
            closed_count += 1

        c_date_str = t.created_at.strftime("%Y-%m-%d") if t.created_at else ""
        if c_date_str == today_str:
            today_count += 1

        # Hierarchical Category -> Subcategory -> Issue Tree Data
        cat_name = t.category.category_name if t.category else "Other / Custom Request"
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

        # Resolution Time Calculation
        res_seconds = None
        per_ticket_solving_time_str = "Active"
        if t.status_id in (3, 4) and t.created_at:
            end_time = t.closed_at or t.updated_at
            if end_time and end_time > t.created_at:
                res_seconds = (end_time - t.created_at).total_seconds()
                all_resolution_times.append(res_seconds)
                per_ticket_solving_time_str = format_duration(res_seconds)
            else:
                per_ticket_solving_time_str = "< 1m"
        elif t.created_at:
            active_sec = (now_utc - t.created_at).total_seconds()
            per_ticket_solving_time_str = f"Open ({format_duration(active_sec)})"

        # Track Admin Metrics
        is_maint = getattr(t, "domain", "") == "MAINTENANCE" or "TKT-MNT" in t.ticket_number
        asg_key = f"MAINT_{t.ticket_id}" if is_maint else f"IT_{t.ticket_id}"
        admin = asg_map.get(asg_key)
        if admin and admin.admin_id in admin_stats_map:
            astat = admin_stats_map[admin.admin_id]
            astat["total_assigned"] += 1
            if t.status_id in (1, 2):
                astat["pending_count"] += 1
            elif t.status_id in (3, 4):
                astat["resolved_count"] += 1
                if res_seconds is not None:
                    astat["resolution_seconds_list"].append(res_seconds)

        emp = t.employee
        emp_name = emp.full_name if emp else "Unknown"
        emp_phone = emp.phone if emp else ""
        dept_name = emp.department.department_name if emp and emp.department else "General"
        loc_name = emp.location.location_name if emp and emp.location else "Headquarters"

        p_name = t.priority.priority_name if t.priority else "Medium"
        admin_name = admin.full_name if admin else "Unassigned"
        admin_phone = admin.phone if admin else ""

        records.append({
            "ticket_id": t.ticket_id,
            "ticket_number": t.ticket_number,
            "domain": "MAINTENANCE" if is_maint else "IT",
            "employee_name": emp_name,
            "employee_phone": emp_phone,
            "department": dept_name,
            "location": loc_name,
            "category": cat_name,
            "subcategory": sub_name,
            "issue": issue_name,
            "priority": p_name,
            "status": status_name,
            "status_id": t.status_id,
            "description": t.description,
            "image_id": t.image_id,
            "assigned_admin": admin_name,
            "admin_phone": admin_phone,
            "created_at": t.created_at.strftime("%Y-%m-%d %H:%M:%S") if t.created_at else "",
            "updated_at": t.updated_at.strftime("%Y-%m-%d %H:%M:%S") if t.updated_at else "",
            "closed_at": t.closed_at.strftime("%Y-%m-%d %H:%M:%S") if t.closed_at else "",
            "resolution_time_formatted": per_ticket_solving_time_str
        })

    # Compile Admin Performance List (ONLY Kevin, Ellias, Faisal)
    admin_performance = []
    for a_id, astat in admin_stats_map.items():
        sec_list = astat["resolution_seconds_list"]
        avg_sec = sum(sec_list) / len(sec_list) if sec_list else 0
        admin_performance.append({
            "admin_id": astat["admin_id"],
            "full_name": astat["full_name"],
            "phone": astat["phone"],
            "pending_count": astat["pending_count"],
            "resolved_count": astat["resolved_count"],
            "total_assigned": astat["total_assigned"],
            "avg_resolution_seconds": avg_sec,
            "avg_resolution_formatted": format_duration(avg_sec) if avg_sec > 0 else "N/A"
        })

    # Convert Category Tree Map to list
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

    overall_avg_sec = sum(all_resolution_times) / len(all_resolution_times) if all_resolution_times else 0

    return {
        "summary": {
            "total_tickets": total_count,
            "open_tickets": open_count,
            "in_progress_tickets": in_progress_count,
            "pending_total": open_count + in_progress_count,
            "resolved_tickets": resolved_count,
            "closed_tickets": closed_count,
            "completed_total": resolved_count + closed_count,
            "today_tickets": today_count,
            "overall_avg_resolution_time": format_duration(overall_avg_sec)
        },
        "admin_performance": admin_performance,
        "category_tree": category_tree_list,
        "records": records,
        "server_time": datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
    }

@router.get("/dashboard", response_class=HTMLResponse)
async def render_dashboard_page():
    """
    Renders an ultra-clean, professional white-themed Live Web Dashboard UI for Executive Ticket Tracking.
    """
    html_content = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Tagoneswa IT Support - Executive Analytics Dashboard</title>
    <!-- Tailwind CSS CDN -->
    <script src="https://cdn.tailwindcss.com"></script>
    <!-- FontAwesome CDN -->
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@300;400;500;600;700;800&display=swap');
        body { font-family: 'Plus Jakarta Sans', sans-serif; background-color: #F8FAFC; color: #0F172A; }
        
        .badge-open { background-color: #FFFBEB; color: #B45309; border: 1px solid #FDE68A; }
        .badge-progress { background-color: #EFF6FF; color: #1D4ED8; border: 1px solid #BFDBFE; }
        .badge-resolved { background-color: #ECFDF5; color: #047857; border: 1px solid #A7F3D0; }
        .badge-closed { background-color: #F1F5F9; color: #475569; border: 1px solid #E2E8F0; }
        
        .badge-urgent { background-color: #FEF2F2; color: #B91C1C; border: 1px solid #FECACA; font-weight: 700; }
        .badge-high { background-color: #FFEDD5; color: #C2410C; border: 1px solid #FDBA74; }
        .badge-medium { background-color: #FEF9C3; color: #A16207; border: 1px solid #FDE047; }
        .badge-low { background-color: #EEF2FF; color: #4338CA; border: 1px solid #C7D2FE; }

        .tab-btn.active { border-bottom: 2px solid #2563EB; color: #2563EB; font-weight: 700; }
    </style>
</head>
<body class="bg-slate-50 text-slate-900 min-h-screen">

    <!-- Header Navbar -->
    <header class="bg-white border-b border-slate-200 sticky top-0 z-40 shadow-xs">
        <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-3.5 flex flex-col md:flex-row md:items-center md:justify-between gap-4">
            <div class="flex items-center space-x-3">
                <div class="bg-blue-600 text-white p-2.5 rounded-xl shadow-md shadow-blue-500/20">
                    <i class="fa-solid fa-headset text-xl"></i>
                </div>
                <div>
                    <h1 class="text-xl font-bold tracking-tight text-slate-900 flex items-center gap-2">
                        TAGONESWA IT SUPPORT
                        <span class="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-emerald-50 text-emerald-700 border border-emerald-200">
                            <span class="w-2 h-2 rounded-full bg-emerald-500 animate-pulse"></span>
                            Live System Operational
                        </span>
                    </h1>
                    <p class="text-xs text-slate-500">Executive Real-Time Ticket Tracking & Support Engineering Dashboard</p>
                </div>
            </div>
            
            <div class="flex items-center space-x-3">
                <button onclick="exportToCSV()" class="inline-flex items-center gap-2 px-3.5 py-2 rounded-xl text-xs font-semibold bg-slate-100 hover:bg-slate-200 text-slate-700 border border-slate-300 transition">
                    <i class="fa-solid fa-file-csv text-emerald-600 text-sm"></i>
                    <span>Export CSV</span>
                </button>
                <button onclick="fetchDashboardData()" class="inline-flex items-center gap-2 px-4 py-2 rounded-xl text-sm font-semibold bg-white hover:bg-slate-50 text-slate-700 border border-slate-300 shadow-xs transition">
                    <i class="fa-solid fa-arrows-rotate text-blue-600" id="refresh-icon"></i>
                    <span>Refresh Data</span>
                </button>
                <div class="text-xs text-slate-500 hidden sm:block text-right border-l border-slate-200 pl-4">
                    <div>Last Updated: <span id="last-updated-time" class="font-mono font-semibold text-slate-800">--:--:--</span></div>
                    <div class="text-slate-400">Auto-refreshes every 15s</div>
                </div>
            </div>
        </div>
    </header>

    <!-- Main Container -->
    <main class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 space-y-8">

        <!-- Executive Summary KPI Cards -->
        <div class="grid grid-cols-2 sm:grid-cols-2 lg:grid-cols-5 gap-4 sm:gap-6">
            <!-- Total All-Time -->
            <div class="bg-white border border-slate-200 rounded-2xl p-5 shadow-xs hover:shadow-md transition">
                <div class="flex items-center justify-between">
                    <span class="text-xs font-bold uppercase tracking-wider text-slate-500">Total Tickets</span>
                    <div class="p-2 bg-blue-50 text-blue-600 rounded-lg"><i class="fa-solid fa-ticket text-lg"></i></div>
                </div>
                <div class="mt-3 flex items-baseline">
                    <span class="text-3xl font-black text-slate-900" id="stat-total">0</span>
                    <span class="ml-2 text-xs text-slate-500">all-time</span>
                </div>
                <div class="mt-2 text-xs text-slate-400">Complete database records</div>
            </div>

            <!-- Pending Action -->
            <div class="bg-white border border-slate-200 rounded-2xl p-5 shadow-xs hover:shadow-md transition">
                <div class="flex items-center justify-between">
                    <span class="text-xs font-bold uppercase tracking-wider text-amber-600">Pending Action</span>
                    <div class="p-2 bg-amber-50 text-amber-600 rounded-lg"><i class="fa-solid fa-clock-rotate-left text-lg"></i></div>
                </div>
                <div class="mt-3 flex items-baseline">
                    <span class="text-3xl font-black text-amber-600" id="stat-pending">0</span>
                    <span class="ml-2 text-xs text-slate-500">unresolved</span>
                </div>
                <div class="mt-2 text-xs text-slate-500 flex items-center justify-between border-t border-slate-100 pt-2">
                    <span>Open: <strong id="stat-open" class="text-slate-800">0</strong></span>
                    <span>In Progress: <strong id="stat-progress" class="text-slate-800">0</strong></span>
                </div>
            </div>

            <!-- Resolved / Completed -->
            <div class="bg-white border border-slate-200 rounded-2xl p-5 shadow-xs hover:shadow-md transition">
                <div class="flex items-center justify-between">
                    <span class="text-xs font-bold uppercase tracking-wider text-emerald-600">Resolved / Closed</span>
                    <div class="p-2 bg-emerald-50 text-emerald-600 rounded-lg"><i class="fa-solid fa-circle-check text-lg"></i></div>
                </div>
                <div class="mt-3 flex items-baseline">
                    <span class="text-3xl font-black text-emerald-600" id="stat-completed">0</span>
                    <span class="ml-2 text-xs text-slate-500">fixed</span>
                </div>
                <div class="mt-2 text-xs text-slate-500 flex items-center justify-between border-t border-slate-100 pt-2">
                    <span>Resolved: <strong id="stat-resolved" class="text-slate-800">0</strong></span>
                    <span>Closed: <strong id="stat-closed" class="text-slate-800">0</strong></span>
                </div>
            </div>

            <!-- Today's New -->
            <div class="bg-white border border-slate-200 rounded-2xl p-5 shadow-xs hover:shadow-md transition">
                <div class="flex items-center justify-between">
                    <span class="text-xs font-bold uppercase tracking-wider text-purple-600">Today's New</span>
                    <div class="p-2 bg-purple-50 text-purple-600 rounded-lg"><i class="fa-solid fa-calendar-day text-lg"></i></div>
                </div>
                <div class="mt-3 flex items-baseline">
                    <span class="text-3xl font-black text-purple-600" id="stat-today">0</span>
                    <span class="ml-2 text-xs text-slate-500">today</span>
                </div>
                <div class="mt-2 text-xs text-slate-400">Created in last 24h</div>
            </div>

            <!-- Avg Resolution Speed -->
            <div class="bg-white border border-slate-200 rounded-2xl p-5 shadow-xs hover:shadow-md transition">
                <div class="flex items-center justify-between">
                    <span class="text-xs font-bold uppercase tracking-wider text-blue-600">Avg Resolution Speed</span>
                    <div class="p-2 bg-blue-50 text-blue-600 rounded-lg"><i class="fa-solid fa-stopwatch text-lg"></i></div>
                </div>
                <div class="mt-3 flex items-baseline">
                    <span class="text-2xl font-black text-blue-700" id="stat-avg-time">--</span>
                </div>
                <div class="mt-2 text-xs text-slate-500">Mean duration to resolve</div>
            </div>
        </div>

        <!-- Professional Executive Navigation Tabs -->
        <div class="border-b border-slate-200 flex space-x-8 text-sm font-semibold">
            <button onclick="switchTab('directory')" id="tab-btn-directory" class="tab-btn active pb-3 transition flex items-center gap-2">
                <i class="fa-solid fa-list-check"></i> Ticket Directory
            </button>
            <button onclick="switchTab('admins')" id="tab-btn-admins" class="tab-btn pb-3 text-slate-500 hover:text-slate-900 transition flex items-center gap-2">
                <i class="fa-solid fa-user-shield"></i> Admin SLA & Workload
            </button>
            <button onclick="switchTab('insights')" id="tab-btn-insights" class="tab-btn pb-3 text-slate-500 hover:text-slate-900 transition flex items-center gap-2">
                <i class="fa-solid fa-chart-pie"></i> Category Analytics
            </button>
        </div>

        <!-- TAB 1: TICKET DIRECTORY -->
        <div id="tab-directory" class="space-y-6">
            <!-- Search & Filter Controls -->
            <div class="bg-white border border-slate-200 rounded-2xl p-4 sm:p-5 shadow-xs space-y-4">
                <div class="flex flex-col md:flex-row md:items-center md:justify-between gap-4">
                    <!-- Search Input -->
                    <div class="relative flex-1">
                        <i class="fa-solid fa-magnifying-glass absolute left-3.5 top-1/2 -translate-y-1/2 text-slate-400"></i>
                        <input type="text" id="search-input" onkeyup="filterTickets()" placeholder="Search by Ticket #, Employee Name, Phone, Category, Issue description, Admin..." 
                               class="w-full pl-10 pr-4 py-2.5 rounded-xl bg-slate-50 border border-slate-300 text-sm text-slate-900 placeholder-slate-400 focus:outline-none focus:bg-white focus:border-blue-600 focus:ring-1 focus:ring-blue-600 transition">
                    </div>

                    <!-- Filters -->
                    <div class="flex flex-wrap items-center gap-3">
                        <select id="filter-domain" onchange="filterTickets()" class="bg-slate-50 border border-slate-300 text-slate-800 text-sm rounded-xl px-3.5 py-2.5 focus:outline-none focus:bg-white focus:border-blue-600 font-medium">
                            <option value="ALL">All Support Domains</option>
                            <option value="IT">💻 IT Support</option>
                            <option value="MAINTENANCE">🏗️ Building Projects</option>
                        </select>

                        <select id="filter-status" onchange="filterTickets()" class="bg-slate-50 border border-slate-300 text-slate-800 text-sm rounded-xl px-3.5 py-2.5 focus:outline-none focus:bg-white focus:border-blue-600 font-medium">
                            <option value="ALL">All Statuses</option>
                            <option value="Open">🟡 Open</option>
                            <option value="In Progress">🔵 In Progress</option>
                            <option value="Resolved">🟢 Resolved</option>
                            <option value="Closed">⚪ Closed</option>
                        </select>

                        <select id="filter-priority" onchange="filterTickets()" class="bg-slate-50 border border-slate-300 text-slate-800 text-sm rounded-xl px-3.5 py-2.5 focus:outline-none focus:bg-white focus:border-blue-600 font-medium">
                            <option value="ALL">All Priorities</option>
                            <option value="Urgent">🔥 Urgent</option>
                            <option value="High">🚨 High</option>
                            <option value="Medium">⚡ Medium</option>
                            <option value="Low">🔹 Low</option>
                        </select>
                    </div>
                </div>
            </div>

            <!-- Historical Ticket Table -->
            <div class="bg-white border border-slate-200 rounded-2xl shadow-xs overflow-hidden">
                <div class="px-6 py-4 border-b border-slate-200 flex items-center justify-between bg-slate-50/50">
                    <h3 class="text-sm font-bold text-slate-800 uppercase tracking-wider flex items-center gap-2">
                        <i class="fa-solid fa-database text-blue-600"></i>
                        Historical Ticket Records
                        <span class="text-xs text-slate-500 font-normal capitalize">(Showing <span id="visible-count" class="font-bold text-slate-800">0</span> records)</span>
                    </h3>
                </div>

                <div class="overflow-x-auto">
                    <table class="w-full text-left text-sm text-slate-700">
                        <thead class="text-xs uppercase bg-slate-100/80 text-slate-500 border-b border-slate-200 font-bold">
                            <tr>
                                <th class="px-6 py-3.5">Ticket #</th>
                                <th class="px-6 py-3.5">Employee & Contact</th>
                                <th class="px-6 py-3.5">Location / Dept</th>
                                <th class="px-6 py-3.5">Category & Issue</th>
                                <th class="px-6 py-3.5">Priority</th>
                                <th class="px-6 py-3.5">Status</th>
                                <th class="px-6 py-3.5">Assigned Admin</th>
                                <th class="px-6 py-3.5">Resolution Time</th>
                                <th class="px-6 py-3.5 text-right">Action</th>
                            </tr>
                        </thead>
                        <tbody id="tickets-table-body" class="divide-y divide-slate-100">
                            <tr>
                                <td colspan="9" class="text-center py-12 text-slate-400">
                                    <i class="fa-solid fa-spinner fa-spin text-2xl mb-2 text-blue-600"></i>
                                    <div>Loading live ticket database...</div>
                                </td>
                            </tr>
                        </tbody>
                    </table>
                </div>
            </div>
        </div>

        <!-- TAB 2: ADMIN SLA & WORKLOAD -->
        <div id="tab-admins" class="hidden space-y-6">
            <div class="bg-white border border-slate-200 rounded-2xl shadow-xs overflow-hidden">
                <div class="px-6 py-4 border-b border-slate-200 bg-slate-50/50 flex items-center justify-between">
                    <div>
                        <h3 class="text-sm font-bold text-slate-800 uppercase tracking-wider">IT Support Engineers SLA & Workload</h3>
                        <p class="text-xs text-slate-500 mt-0.5">Tracking performance for assigned Support Engineers: Kevin Chikati, Ellias Murenga, and Faisal Kassim</p>
                    </div>
                </div>
                <div class="overflow-x-auto">
                    <table class="w-full text-left text-sm text-slate-700">
                        <thead class="text-xs uppercase bg-slate-100/80 text-slate-500 border-b border-slate-200 font-bold">
                            <tr>
                                <th class="px-6 py-3.5">Support Admin Name</th>
                                <th class="px-6 py-3.5">WhatsApp Contact</th>
                                <th class="px-6 py-3.5 text-center">🟡 Pending Tickets</th>
                                <th class="px-6 py-3.5 text-center">🟢 Resolved Tickets</th>
                                <th class="px-6 py-3.5 text-center">Total Assigned</th>
                                <th class="px-6 py-3.5 text-right">Avg Resolution Speed</th>
                            </tr>
                        </thead>
                        <tbody id="admins-table-body" class="divide-y divide-slate-100">
                            <!-- Dynamic Admin Rows -->
                        </tbody>
                    </table>
                </div>
            </div>
        </div>

        <!-- TAB 3: CATEGORY ANALYTICS -->
        <div id="tab-insights" class="hidden space-y-6">
            <div class="bg-white border border-slate-200 rounded-2xl p-6 shadow-xs space-y-6">
                <div>
                    <h3 class="text-sm font-bold text-slate-800 uppercase tracking-wider">Category, Subcategory & Issue Breakdown</h3>
                    <p class="text-xs text-slate-500 mt-0.5">Click any Category header to expand its Subcategories and specific Issue types</p>
                </div>
                <div id="category-tree-container" class="space-y-4">
                    <!-- Dynamic Accordions -->
                </div>
            </div>
        </div>

    </main>

    <!-- Ticket Detail Modal -->
    <div id="detail-modal" class="fixed inset-0 z-50 hidden bg-slate-900/60 backdrop-blur-xs flex items-center justify-center p-4">
        <div class="bg-white border border-slate-200 rounded-2xl max-w-2xl w-full p-6 space-y-6 shadow-2xl relative">
            <button onclick="closeModal()" class="absolute top-4 right-4 text-slate-400 hover:text-slate-700 p-2 text-xl transition">
                <i class="fa-solid fa-xmark"></i>
            </button>

            <div class="flex items-center space-x-3 border-b border-slate-100 pb-4">
                <div class="p-3 bg-blue-50 text-blue-600 rounded-xl">
                    <i class="fa-solid fa-receipt text-2xl"></i>
                </div>
                <div>
                    <h2 class="text-lg font-bold text-slate-900 flex items-center gap-2" id="m-ticket-num">TKT-XXXXXX</h2>
                    <p class="text-xs text-slate-500" id="m-created-at">Created at: --</p>
                </div>
            </div>

            <div class="grid grid-cols-2 gap-4 text-xs bg-slate-50 p-4 rounded-xl border border-slate-200">
                <div>
                    <span class="text-slate-500 block font-medium">Employee Name:</span>
                    <strong class="text-slate-900 text-sm font-bold" id="m-emp-name">--</strong>
                    <div class="text-slate-500 font-mono mt-0.5" id="m-emp-phone">--</div>
                </div>
                <div>
                    <span class="text-slate-500 block font-medium">Location & Dept:</span>
                    <strong class="text-slate-900 text-sm font-bold" id="m-location">--</strong>
                    <div class="text-slate-600 mt-0.5" id="m-dept">--</div>
                </div>
            </div>

            <div class="space-y-3">
                <div>
                    <span class="text-xs font-semibold text-slate-500 block">Category ➡️ Subcategory:</span>
                    <div class="text-sm font-bold text-slate-800" id="m-category">--</div>
                </div>
                <div>
                    <span class="text-xs font-semibold text-slate-500 block">Specific Issue:</span>
                    <div class="text-sm text-slate-700" id="m-issue">--</div>
                </div>
                <div>
                    <span class="text-xs font-semibold text-slate-500 block">Full Issue Description:</span>
                    <div class="text-xs bg-slate-50 p-3.5 rounded-xl border border-slate-200 text-slate-800 leading-relaxed font-mono whitespace-pre-wrap" id="m-desc">--</div>
                </div>
            </div>

            <div class="grid grid-cols-3 gap-4 text-xs border-t border-slate-100 pt-4">
                <div>
                    <span class="text-slate-500 block font-medium">Assigned Support Admin:</span>
                    <strong class="text-blue-700 text-sm font-bold" id="m-admin">--</strong>
                </div>
                <div>
                    <span class="text-slate-500 block font-medium">Current Status:</span>
                    <span id="m-status-badge">--</span>
                </div>
                <div>
                    <span class="text-slate-500 block font-medium">Resolution Time:</span>
                    <strong class="text-emerald-700 text-sm font-bold font-mono" id="m-res-time">--</strong>
                </div>
            </div>

            <div id="m-photo-container" class="hidden border-t border-slate-100 pt-4">
                <span class="text-xs font-semibold text-slate-500 block mb-2">WhatsApp Photo Attachment:</span>
                <div class="text-xs font-mono bg-amber-50 p-3 rounded-xl border border-amber-200 text-amber-900 flex items-center justify-between">
                    <span>Meta Image ID: <strong id="m-photo-id" class="text-amber-700">--</strong></span>
                    <span class="text-xs bg-amber-200 text-amber-900 px-2 py-0.5 rounded font-sans font-semibold">Attached in Chat</span>
                </div>
            </div>
        </div>
    </div>

    <!-- JavaScript Data Handler -->
    <script>
        let allRecords = [];
        let adminStats = [];
        let categoryTree = [];
        let openCategoryNames = new Set(); // Track expanded category accordions across auto-refreshes!

        async function fetchDashboardData() {
            const refreshIcon = document.getElementById('refresh-icon');
            if (refreshIcon) refreshIcon.classList.add('fa-spin');

            try {
                const res = await fetch('/api/dashboard/data');
                const data = await res.json();
                
                allRecords = data.records || [];
                adminStats = data.admin_performance || [];
                categoryTree = data.category_tree || [];

                updateStats(data.summary || {});
                renderAdminTable(adminStats);
                renderCategoryTree(categoryTree, data.summary.total_tickets || 1);

                // Preserve search input & filter selections across auto-refreshes!
                filterTickets();
                
                document.getElementById('last-updated-time').innerText = new Date().toLocaleTimeString();
            } catch (err) {
                console.error("Error fetching dashboard data:", err);
            } finally {
                if (refreshIcon) refreshIcon.classList.remove('fa-spin');
            }
        }

        function updateStats(summary) {
            document.getElementById('stat-total').innerText = summary.total_tickets || 0;
            document.getElementById('stat-pending').innerText = summary.pending_total || 0;
            document.getElementById('stat-open').innerText = summary.open_tickets || 0;
            document.getElementById('stat-progress').innerText = summary.in_progress_tickets || 0;
            
            document.getElementById('stat-completed').innerText = summary.completed_total || 0;
            document.getElementById('stat-resolved').innerText = summary.resolved_tickets || 0;
            document.getElementById('stat-closed').innerText = summary.closed_tickets || 0;

            document.getElementById('stat-today').innerText = summary.today_tickets || 0;
            document.getElementById('stat-avg-time').innerText = summary.overall_avg_resolution_time || '--';
        }

        function renderAdminTable(admins) {
            const tbody = document.getElementById('admins-table-body');
            if (!admins || admins.length === 0) {
                tbody.innerHTML = `<tr><td colspan="6" class="text-center py-8 text-slate-400">No active support admin stats found.</td></tr>`;
                return;
            }

            let html = '';
            admins.forEach(a => {
                const pendingBadge = a.pending_count > 0 
                    ? `<span class="px-3 py-1 rounded-full text-xs font-bold bg-amber-100 text-amber-800 border border-amber-300">${a.pending_count} Active</span>`
                    : `<span class="px-3 py-1 rounded-full text-xs font-semibold bg-slate-100 text-slate-500">0 Pending</span>`;

                html += `
                <tr class="hover:bg-slate-50 transition">
                    <td class="px-6 py-4 font-bold text-slate-900 flex items-center gap-2">
                        <i class="fa-solid fa-user-gear text-blue-600"></i> ${escapeHtml(a.full_name)}
                    </td>
                    <td class="px-6 py-4 font-mono text-slate-600">+${a.phone}</td>
                    <td class="px-6 py-4 text-center font-bold">${pendingBadge}</td>
                    <td class="px-6 py-4 text-center font-bold text-emerald-600">${a.resolved_count}</td>
                    <td class="px-6 py-4 text-center font-semibold text-slate-700">${a.total_assigned}</td>
                    <td class="px-6 py-4 text-right font-mono font-bold text-blue-700">${a.avg_resolution_formatted}</td>
                </tr>
                `;
            });
            tbody.innerHTML = html;
        }

        function renderCategoryTree(tree, totalTickets) {
            const container = document.getElementById('category-tree-container');
            if (!tree || tree.length === 0) {
                container.innerHTML = `<div class="text-slate-400 text-sm">No category tree stats recorded yet.</div>`;
                return;
            }

            // Save currently open details element names before re-render
            document.querySelectorAll('#category-tree-container details').forEach(d => {
                const catTitle = d.getAttribute('data-cat-name');
                if (catTitle) {
                    if (d.open) openCategoryNames.add(catTitle);
                    else openCategoryNames.delete(catTitle);
                }
            });

            let html = '';
            tree.sort((a, b) => b.count - a.count).forEach((cat, idx) => {
                const catPct = Math.round((cat.count / totalTickets) * 100);
                
                // Keep open if previously opened by user OR first category by default
                const isInitiallyOpen = (openCategoryNames.size === 0 && idx === 0) || openCategoryNames.has(cat.category_name);
                const openAttr = isInitiallyOpen ? 'open' : '';

                let subHtml = '';
                cat.subcategories.sort((a, b) => b.count - a.count).forEach(sub => {
                    let issHtml = '';
                    sub.issues.forEach(iss => {
                        issHtml += `
                        <div class="flex items-center justify-between text-xs text-slate-600 pl-4 py-1 border-l-2 border-slate-200">
                            <span>📌 ${escapeHtml(iss.issue_name)}</span>
                            <span class="font-bold text-slate-800 bg-slate-100 px-2 py-0.5 rounded">${iss.count} tickets</span>
                        </div>
                        `;
                    });

                    subHtml += `
                    <div class="bg-slate-50 p-4 rounded-xl border border-slate-200 space-y-2">
                        <div class="flex items-center justify-between text-sm font-bold text-slate-800">
                            <span>📂 Subcategory: ${escapeHtml(sub.subcategory_name)}</span>
                            <span class="text-xs bg-blue-100 text-blue-800 px-2.5 py-0.5 rounded-full font-semibold">${sub.count} tickets</span>
                        </div>
                        <div class="space-y-1 pt-1">
                            ${issHtml}
                        </div>
                    </div>
                    `;
                });

                html += `
                <details data-cat-name="${escapeHtml(cat.category_name)}" class="group bg-white border border-slate-200 rounded-2xl p-4 shadow-xs" ${openAttr} ontoggle="onAccordionToggle(this, '${escapeHtml(cat.category_name)}')">
                    <summary class="flex items-center justify-between font-bold text-slate-900 cursor-pointer list-none">
                        <div class="flex items-center space-x-3">
                            <span class="p-2 bg-blue-50 text-blue-600 rounded-lg"><i class="fa-solid fa-folder-open"></i></span>
                            <span class="text-base">${escapeHtml(cat.category_name)}</span>
                        </div>
                        <div class="flex items-center space-x-4">
                            <span class="text-xs font-bold text-slate-500 bg-slate-100 px-3 py-1 rounded-full">${cat.count} total tickets (${catPct}%)</span>
                            <i class="fa-solid fa-chevron-down text-slate-400 group-open:rotate-180 transition-transform"></i>
                        </div>
                    </summary>
                    <div class="mt-4 pt-4 border-t border-slate-100 space-y-3">
                        ${subHtml}
                    </div>
                </details>
                `;
            });
            container.innerHTML = html;
        }

        function onAccordionToggle(el, catName) {
            if (el.open) {
                openCategoryNames.add(catName);
            } else {
                openCategoryNames.delete(catName);
            }
        }

        function getStatusBadgeHtml(status) {
            if (status === 'Open') return '<span class="px-3 py-1 rounded-full text-xs font-bold badge-open"><i class="fa-solid fa-circle-dot mr-1 text-amber-600"></i>Open</span>';
            if (status === 'In Progress') return '<span class="px-3 py-1 rounded-full text-xs font-bold badge-progress"><i class="fa-solid fa-spinner fa-spin mr-1 text-blue-600"></i>In Progress</span>';
            if (status === 'Resolved') return '<span class="px-3 py-1 rounded-full text-xs font-bold badge-resolved"><i class="fa-solid fa-check-double mr-1 text-emerald-600"></i>Resolved</span>';
            if (status === 'Closed') return '<span class="px-3 py-1 rounded-full text-xs font-bold badge-closed"><i class="fa-solid fa-lock mr-1 text-slate-500"></i>Closed</span>';
            return `<span class="px-3 py-1 rounded-full text-xs font-bold bg-slate-100 text-slate-700">${status}</span>`;
        }

        function getPriorityBadgeHtml(p) {
            if (p === 'Urgent') return '<span class="px-2.5 py-0.5 rounded-md text-xs badge-urgent"><i class="fa-solid fa-fire mr-1"></i>Urgent</span>';
            if (p === 'High') return '<span class="px-2.5 py-0.5 rounded-md text-xs badge-high">High</span>';
            if (p === 'Medium') return '<span class="px-2.5 py-0.5 rounded-md text-xs badge-medium">Medium</span>';
            return '<span class="px-2.5 py-0.5 rounded-md text-xs badge-low">Low</span>';
        }

        function renderTable(records) {
            const tbody = document.getElementById('tickets-table-body');
            document.getElementById('visible-count').innerText = records.length;

            if (records.length === 0) {
                tbody.innerHTML = `<tr><td colspan="9" class="text-center py-12 text-slate-400">No ticket records found matching criteria.</td></tr>`;
                return;
            }

            let html = '';
            records.forEach(r => {
                const photoIcon = r.image_id ? `<span class="text-amber-500 ml-1.5" title="Photo Attachment Present"><i class="fa-solid fa-image"></i></span>` : '';
                const domainBadge = r.domain === 'MAINTENANCE' 
                    ? `<span class="px-2 py-0.5 rounded text-[10px] font-bold bg-amber-100 text-amber-800 border border-amber-300 ml-1">🏗️ Projects</span>`
                    : `<span class="px-2 py-0.5 rounded text-[10px] font-bold bg-blue-100 text-blue-800 border border-blue-300 ml-1">💻 IT</span>`;

                html += `
                <tr class="hover:bg-slate-50 transition cursor-pointer" onclick='openModal(${JSON.stringify(r).replace(/'/g, "&apos;")})'>
                    <td class="px-6 py-4 font-mono font-bold text-blue-600 whitespace-nowrap">
                        ${r.ticket_number}${domainBadge}${photoIcon}
                    </td>
                    <td class="px-6 py-4">
                        <div class="font-bold text-slate-900">${escapeHtml(r.employee_name)}</div>
                        <div class="text-xs text-slate-500 font-mono">+${r.employee_phone}</div>
                    </td>
                    <td class="px-6 py-4">
                        <div class="text-slate-800 font-medium">${escapeHtml(r.location)}</div>
                        <div class="text-xs text-slate-500">${escapeHtml(r.department)}</div>
                    </td>
                    <td class="px-6 py-4 max-w-xs">
                        <div class="text-xs font-bold text-slate-800 truncate">${escapeHtml(r.category)} ➡️ ${escapeHtml(r.subcategory)}</div>
                        <div class="text-xs text-slate-500 truncate mt-0.5">${escapeHtml(r.issue)}</div>
                    </td>
                    <td class="px-6 py-4 whitespace-nowrap">
                        ${getPriorityBadgeHtml(r.priority)}
                    </td>
                    <td class="px-6 py-4 whitespace-nowrap">
                        ${getStatusBadgeHtml(r.status)}
                    </td>
                    <td class="px-6 py-4 whitespace-nowrap">
                        <div class="text-sm text-slate-800 font-semibold">${escapeHtml(r.assigned_admin)}</div>
                    </td>
                    <td class="px-6 py-4 whitespace-nowrap font-mono font-bold text-xs text-slate-800">
                        ${r.resolution_time_formatted}
                    </td>
                    <td class="px-6 py-4 text-right whitespace-nowrap">
                        <button onclick='event.stopPropagation(); openModal(${JSON.stringify(r).replace(/'/g, "&apos;")})' class="text-xs bg-white hover:bg-slate-100 text-blue-600 px-3.5 py-1.5 rounded-lg border border-slate-300 font-semibold shadow-xs transition">
                            View Details
                        </button>
                    </td>
                </tr>
                `;
            });
            tbody.innerHTML = html;
        }

        function filterTickets() {
            const queryInput = document.getElementById('search-input');
            const domainSelect = document.getElementById('filter-domain');
            const statusSelect = document.getElementById('filter-status');
            const prioritySelect = document.getElementById('filter-priority');

            const query = queryInput ? queryInput.value.toLowerCase().trim() : '';
            const domainFilter = domainSelect ? domainSelect.value : 'ALL';
            const statusFilter = statusSelect ? statusSelect.value : 'ALL';
            const priorityFilter = prioritySelect ? prioritySelect.value : 'ALL';

            const filtered = allRecords.filter(r => {
                const matchesQuery = !query || 
                    r.ticket_number.toLowerCase().includes(query) ||
                    r.employee_name.toLowerCase().includes(query) ||
                    r.employee_phone.includes(query) ||
                    r.category.toLowerCase().includes(query) ||
                    r.issue.toLowerCase().includes(query) ||
                    r.description.toLowerCase().includes(query) ||
                    (r.domain && r.domain.toLowerCase().includes(query)) ||
                    r.assigned_admin.toLowerCase().includes(query);

                const matchesDomain = domainFilter === 'ALL' || r.domain === domainFilter;
                const matchesStatus = statusFilter === 'ALL' || r.status === statusFilter;
                const matchesPriority = priorityFilter === 'ALL' || r.priority === priorityFilter;

                return matchesQuery && matchesDomain && matchesStatus && matchesPriority;
            });

            renderTable(filtered);
        }

        function switchTab(tabName) {
            document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active', 'text-blue-600'));
            document.getElementById('tab-directory').classList.add('hidden');
            document.getElementById('tab-admins').classList.add('hidden');
            document.getElementById('tab-insights').classList.add('hidden');

            document.getElementById('tab-btn-' + tabName).classList.add('active');
            document.getElementById('tab-' + tabName).classList.remove('hidden');
        }

        function openModal(r) {
            document.getElementById('m-ticket-num').innerText = r.ticket_number;
            document.getElementById('m-created-at').innerText = 'Created At: ' + r.created_at;
            document.getElementById('m-emp-name').innerText = r.employee_name;
            document.getElementById('m-emp-phone').innerText = '+' + r.employee_phone;
            document.getElementById('m-location').innerText = r.location;
            document.getElementById('m-dept').innerText = r.department;
            document.getElementById('m-category').innerText = r.category + ' ➡️ ' + r.subcategory;
            document.getElementById('m-issue').innerText = r.issue;
            document.getElementById('m-desc').innerText = r.description;
            document.getElementById('m-admin').innerText = r.assigned_admin + (r.admin_phone ? ' (+' + r.admin_phone + ')' : '');
            document.getElementById('m-status-badge').innerHTML = getStatusBadgeHtml(r.status);
            document.getElementById('m-res-time').innerText = r.resolution_time_formatted || '--';

            const photoContainer = document.getElementById('m-photo-container');
            if (r.image_id) {
                document.getElementById('m-photo-id').innerText = r.image_id;
                photoContainer.classList.remove('hidden');
            } else {
                photoContainer.classList.add('hidden');
            }

            document.getElementById('detail-modal').classList.remove('hidden');
        }

        function closeModal() {
            document.getElementById('detail-modal').classList.add('hidden');
        }

        function exportToCSV() {
            if (!allRecords || allRecords.length === 0) return alert("No records available to export.");
            
            let csv = "Ticket #,Employee Name,Phone,Department,Location,Category,Subcategory,Issue,Priority,Status,Assigned Admin,Created At,Resolution Time,Description\\n";
            allRecords.forEach(r => {
                csv += `"${r.ticket_number}","${r.employee_name}","+${r.employee_phone}","${r.department}","${r.location}","${r.category}","${r.subcategory}","${r.issue}","${r.priority}","${r.status}","${r.assigned_admin}","${r.created_at}","${r.resolution_time_formatted}","${r.description.replace(/"/g, '""')}"\\n`;
            });

            const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" });
            const link = document.createElement("a");
            link.href = URL.createObjectURL(blob);
            link.setAttribute("download", `Tagoneswa_IT_Support_Tickets_${new Date().toISOString().slice(0,10)}.csv`);
            document.body.appendChild(link);
            link.click();
            document.body.removeChild(link);
        }

        function escapeHtml(str) {
            if (!str) return '';
            return str.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&#039;");
        }

        // Initial Fetch & Auto Refresh every 15s
        fetchDashboardData();
        setInterval(fetchDashboardData, 15000);
    </script>
</body>
</html>
"""
    return HTMLResponse(content=html_content)
