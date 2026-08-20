import logging
import datetime
from fastapi import APIRouter, Depends, Response
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload

from app.database import get_db, Ticket, TicketAssignment, SupportAdmin, Employee, Department, Location, Category, Subcategory, IssueType, Priority, TicketStatus

logger = logging.getLogger("dashboard")

router = APIRouter()

@router.get("/api/dashboard/data")
async def get_dashboard_data(db: AsyncSession = Depends(get_db)):
    """
    Returns complete live database ticket metrics and 100% full records of all historical tickets.
    """
    # Fetch all tickets ordered by newest first
    stmt = (
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
        .order_by(Ticket.ticket_id.desc())
    )
    res = await db.execute(stmt)
    tickets = res.scalars().all()

    # Fetch all assignments
    asg_stmt = (
        select(TicketAssignment)
        .options(selectinload(TicketAssignment.admin))
    )
    asg_res = await db.execute(asg_stmt)
    assignments = asg_res.scalars().all()
    asg_map = {a.ticket_id: a.admin for a in assignments if a.admin}

    today_str = datetime.datetime.utcnow().strftime("%Y-%m-%d")

    records = []
    total_count = len(tickets)
    open_count = 0
    in_progress_count = 0
    resolved_count = 0
    closed_count = 0
    today_count = 0

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

        emp = t.employee
        emp_name = emp.full_name if emp else "Unknown"
        emp_phone = emp.phone if emp else ""
        dept_name = emp.department.department_name if emp and emp.department else "General"
        loc_name = emp.location.location_name if emp and emp.location else "Headquarters"

        cat_name = t.category.category_name if t.category else "N/A"
        sub_name = t.subcategory.subcategory_name if t.subcategory else "N/A"
        issue_name = t.issue_type.issue_name if t.issue_type else "Custom Issue"
        p_name = t.priority.priority_name if t.priority else "Medium"
        admin = asg_map.get(t.ticket_id)
        admin_name = admin.full_name if admin else "Unassigned"
        admin_phone = admin.phone if admin else ""

        records.append({
            "ticket_id": t.ticket_id,
            "ticket_number": t.ticket_number,
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
            "closed_at": t.closed_at.strftime("%Y-%m-%d %H:%M:%S") if t.closed_at else ""
        })

    return {
        "summary": {
            "total_tickets": total_count,
            "open_tickets": open_count,
            "in_progress_tickets": in_progress_count,
            "pending_total": open_count + in_progress_count,
            "resolved_tickets": resolved_count,
            "closed_tickets": closed_count,
            "completed_total": resolved_count + closed_count,
            "today_tickets": today_count
        },
        "records": records,
        "server_time": datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
    }

@router.get("/dashboard", response_class=HTMLResponse)
async def render_dashboard_page():
    """
    Renders a modern, real-time Live Web Dashboard UI for Executive Ticket Tracking.
    """
    html_content = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Tagoneswa IT Support - Live Executive Tracking Dashboard</title>
    <!-- Tailwind CSS CDN -->
    <script src="https://cdn.tailwindcss.com"></script>
    <!-- FontAwesome CDN -->
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap');
        body { font-family: 'Inter', sans-serif; }
        .glass-header { background: rgba(15, 23, 42, 0.95); backdrop-filter: blur(12px); }
        .badge-open { background-color: #FEF3C7; color: #D97706; border: 1px solid #FCD34D; }
        .badge-progress { background-color: #DBEAFE; color: #2563EB; border: 1px solid #93C5FD; }
        .badge-resolved { background-color: #D1FAE5; color: #059669; border: 1px solid #6EE7B7; }
        .badge-closed { background-color: #F3F4F6; color: #4B5563; border: 1px solid #E5E7EB; }
        .badge-urgent { background-color: #FEE2E2; color: #DC2626; border: 1px solid #FCA5A5; font-weight: 700; }
        .badge-high { background-color: #FFEDD5; color: #EA580C; border: 1px solid #FDBA74; }
        .badge-medium { background-color: #FEF08A; color: #CA8A04; border: 1px solid #FDE047; }
        .badge-low { background-color: #E0E7FF; color: #4338CA; border: 1px solid #A5B4FC; }
    </style>
</head>
<body class="bg-slate-950 text-slate-100 min-h-screen">

    <!-- Top Navigation Header -->
    <header class="sticky top-0 z-40 glass-header border-b border-slate-800">
        <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-4 flex flex-col md:flex-row md:items-center md:justify-between gap-4">
            <div class="flex items-center space-x-3">
                <div class="bg-blue-600 text-white p-2.5 rounded-xl shadow-lg shadow-blue-500/30">
                    <i class="fa-solid fa-headset text-xl"></i>
                </div>
                <div>
                    <h1 class="text-xl font-bold tracking-tight text-white flex items-center gap-2">
                        TAGONESWA IT SUPPORT
                        <span class="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-medium bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                            <span class="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse"></span>
                            Live System Operational
                        </span>
                    </h1>
                    <p class="text-xs text-slate-400">Real-Time Ticket Tracking & Executive Analytics Portal</p>
                </div>
            </div>
            
            <div class="flex items-center space-x-3">
                <button onclick="fetchDashboardData()" class="inline-flex items-center gap-2 px-3.5 py-2 rounded-lg text-sm font-medium bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700 transition">
                    <i class="fa-solid fa-arrows-rotate" id="refresh-icon"></i>
                    <span>Refresh Now</span>
                </button>
                <div class="text-xs text-slate-400 hidden sm:block text-right">
                    <div>Last Updated: <span id="last-updated-time" class="font-mono text-slate-200">--:--:--</span></div>
                    <div class="text-slate-500">Auto-Refreshes every 15s</div>
                </div>
            </div>
        </div>
    </header>

    <!-- Main Container -->
    <main class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 space-y-8">

        <!-- Executive KPI Metrics Grid -->
        <div class="grid grid-cols-2 sm:grid-cols-2 lg:grid-cols-5 gap-4 sm:gap-6">
            <!-- Total Tickets -->
            <div class="bg-slate-900/80 border border-slate-800 rounded-2xl p-5 shadow-xl relative overflow-hidden group hover:border-slate-700 transition">
                <div class="flex items-center justify-between">
                    <span class="text-xs font-semibold uppercase tracking-wider text-slate-400">Total All-Time</span>
                    <div class="p-2 bg-blue-500/10 text-blue-400 rounded-lg"><i class="fa-solid fa-ticket"></i></div>
                </div>
                <div class="mt-4 flex items-baseline">
                    <span class="text-3xl font-extrabold text-white" id="stat-total">0</span>
                    <span class="ml-2 text-xs text-slate-400">tickets</span>
                </div>
                <div class="mt-2 text-xs text-slate-500">Complete system records</div>
            </div>

            <!-- Pending Action -->
            <div class="bg-slate-900/80 border border-slate-800 rounded-2xl p-5 shadow-xl relative overflow-hidden group hover:border-amber-500/40 transition">
                <div class="flex items-center justify-between">
                    <span class="text-xs font-semibold uppercase tracking-wider text-amber-400">Pending Action</span>
                    <div class="p-2 bg-amber-500/10 text-amber-400 rounded-lg"><i class="fa-solid fa-clock-rotate-left"></i></div>
                </div>
                <div class="mt-4 flex items-baseline">
                    <span class="text-3xl font-extrabold text-amber-400" id="stat-pending">0</span>
                    <span class="ml-2 text-xs text-slate-400">active</span>
                </div>
                <div class="mt-2 text-xs text-slate-400 flex items-center justify-between">
                    <span>Open: <strong id="stat-open" class="text-slate-200">0</strong></span>
                    <span>In Progress: <strong id="stat-progress" class="text-slate-200">0</strong></span>
                </div>
            </div>

            <!-- Resolved / Completed -->
            <div class="bg-slate-900/80 border border-slate-800 rounded-2xl p-5 shadow-xl relative overflow-hidden group hover:border-emerald-500/40 transition">
                <div class="flex items-center justify-between">
                    <span class="text-xs font-semibold uppercase tracking-wider text-emerald-400">Resolved / Closed</span>
                    <div class="p-2 bg-emerald-500/10 text-emerald-400 rounded-lg"><i class="fa-solid fa-circle-check"></i></div>
                </div>
                <div class="mt-4 flex items-baseline">
                    <span class="text-3xl font-extrabold text-emerald-400" id="stat-completed">0</span>
                    <span class="ml-2 text-xs text-slate-400">fixed</span>
                </div>
                <div class="mt-2 text-xs text-slate-400 flex items-center justify-between">
                    <span>Resolved: <strong id="stat-resolved" class="text-slate-200">0</strong></span>
                    <span>Closed: <strong id="stat-closed" class="text-slate-200">0</strong></span>
                </div>
            </div>

            <!-- Today's New -->
            <div class="bg-slate-900/80 border border-slate-800 rounded-2xl p-5 shadow-xl relative overflow-hidden group hover:border-purple-500/40 transition">
                <div class="flex items-center justify-between">
                    <span class="text-xs font-semibold uppercase tracking-wider text-purple-400">Today's New</span>
                    <div class="p-2 bg-purple-500/10 text-purple-400 rounded-lg"><i class="fa-solid fa-calendar-day"></i></div>
                </div>
                <div class="mt-4 flex items-baseline">
                    <span class="text-3xl font-extrabold text-purple-400" id="stat-today">0</span>
                    <span class="ml-2 text-xs text-slate-400">today</span>
                </div>
                <div class="mt-2 text-xs text-slate-500">Created in last 24h</div>
            </div>

            <!-- Resolution Rate -->
            <div class="bg-slate-900/80 border border-slate-800 rounded-2xl p-5 shadow-xl relative overflow-hidden group hover:border-blue-500/40 transition col-span-2 sm:col-span-1">
                <div class="flex items-center justify-between">
                    <span class="text-xs font-semibold uppercase tracking-wider text-blue-400">Resolution Rate</span>
                    <div class="p-2 bg-blue-500/10 text-blue-400 rounded-lg"><i class="fa-solid fa-chart-pie"></i></div>
                </div>
                <div class="mt-4 flex items-baseline">
                    <span class="text-3xl font-extrabold text-blue-400" id="stat-rate">0%</span>
                </div>
                <div class="w-full bg-slate-800 h-2 rounded-full mt-3 overflow-hidden">
                    <div id="rate-bar" class="bg-blue-500 h-full transition-all duration-500" style="width: 0%"></div>
                </div>
            </div>
        </div>

        <!-- Controls, Filters & Search Header -->
        <div class="bg-slate-900/80 border border-slate-800 rounded-2xl p-4 sm:p-6 shadow-xl space-y-4">
            <div class="flex flex-col md:flex-row md:items-center md:justify-between gap-4">
                <!-- Search Input -->
                <div class="relative flex-1">
                    <i class="fa-solid fa-magnifying-glass absolute left-3.5 top-1/2 -translate-y-1/2 text-slate-500"></i>
                    <input type="text" id="search-input" onkeyup="filterTickets()" placeholder="Search by Ticket #, Employee Name, Phone, Category, Issue description..." 
                           class="w-full pl-10 pr-4 py-2.5 rounded-xl bg-slate-950 border border-slate-800 text-sm text-white placeholder-slate-500 focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500 transition">
                </div>

                <!-- Filter Controls -->
                <div class="flex flex-wrap items-center gap-3">
                    <!-- Status Filter -->
                    <select id="filter-status" onchange="filterTickets()" class="bg-slate-950 border border-slate-800 text-slate-200 text-sm rounded-xl px-3 py-2.5 focus:outline-none focus:border-blue-500">
                        <option value="ALL">All Statuses</option>
                        <option value="Open">🟡 Open</option>
                        <option value="In Progress">🔵 In Progress</option>
                        <option value="Resolved">🟢 Resolved</option>
                        <option value="Closed">⚪ Closed</option>
                    </select>

                    <!-- Priority Filter -->
                    <select id="filter-priority" onchange="filterTickets()" class="bg-slate-950 border border-slate-800 text-slate-200 text-sm rounded-xl px-3 py-2.5 focus:outline-none focus:border-blue-500">
                        <option value="ALL">All Priorities</option>
                        <option value="Urgent">🔥 Urgent</option>
                        <option value="High">🚨 High</option>
                        <option value="Medium">⚡ Medium</option>
                        <option value="Low">🔹 Low</option>
                    </select>
                </div>
            </div>
        </div>

        <!-- Historical Ticket Records Table Card -->
        <div class="bg-slate-900/80 border border-slate-800 rounded-2xl shadow-xl overflow-hidden">
            <div class="px-6 py-4 border-b border-slate-800 flex items-center justify-between bg-slate-900">
                <h3 class="text-base font-semibold text-white flex items-center gap-2">
                    <i class="fa-solid fa-list-check text-blue-400"></i>
                    All Historical Ticket Records
                    <span class="text-xs text-slate-400 font-normal">(Showing <span id="visible-count">0</span> records)</span>
                </h3>
            </div>

            <div class="overflow-x-auto">
                <table class="w-full text-left text-sm text-slate-300">
                    <thead class="text-xs uppercase bg-slate-950/80 text-slate-400 border-b border-slate-800">
                        <tr>
                            <th class="px-6 py-3.5 font-semibold">Ticket #</th>
                            <th class="px-6 py-3.5 font-semibold">Employee</th>
                            <th class="px-6 py-3.5 font-semibold">Location / Dept</th>
                            <th class="px-6 py-3.5 font-semibold">Category & Issue</th>
                            <th class="px-6 py-3.5 font-semibold">Priority</th>
                            <th class="px-6 py-3.5 font-semibold">Status</th>
                            <th class="px-6 py-3.5 font-semibold">Assigned Admin</th>
                            <th class="px-6 py-3.5 font-semibold text-right">Action</th>
                        </tr>
                    </thead>
                    <tbody id="tickets-table-body" class="divide-y divide-slate-800/60 font-normal">
                        <!-- Dynamic Ticket Rows -->
                        <tr>
                            <td colspan="8" class="text-center py-12 text-slate-500">
                                <i class="fa-solid fa-spinner fa-spin text-2xl mb-2"></i>
                                <div>Loading live ticket records from database...</div>
                            </td>
                        </tr>
                    </tbody>
                </table>
            </div>
        </div>

    </main>

    <!-- Ticket Detail Modal -->
    <div id="detail-modal" class="fixed inset-0 z-50 hidden bg-slate-950/80 backdrop-blur-sm flex items-center justify-center p-4">
        <div class="bg-slate-900 border border-slate-800 rounded-2xl max-w-2xl w-full p-6 space-y-6 shadow-2xl relative">
            <button onclick="closeModal()" class="absolute top-4 right-4 text-slate-400 hover:text-white p-2 text-xl">
                <i class="fa-solid fa-xmark"></i>
            </button>

            <div class="flex items-center space-x-3 border-b border-slate-800 pb-4">
                <div class="p-3 bg-blue-600/10 text-blue-400 rounded-xl">
                    <i class="fa-solid fa-receipt text-2xl"></i>
                </div>
                <div>
                    <h2 class="text-lg font-bold text-white flex items-center gap-2" id="m-ticket-num">TKT-XXXXXX</h2>
                    <p class="text-xs text-slate-400" id="m-created-at">Created at: --</p>
                </div>
            </div>

            <div class="grid grid-cols-2 gap-4 text-xs bg-slate-950 p-4 rounded-xl border border-slate-800/80">
                <div>
                    <span class="text-slate-500 block">Employee:</span>
                    <strong class="text-slate-200 text-sm" id="m-emp-name">--</strong>
                    <div class="text-slate-400 font-mono mt-0.5" id="m-emp-phone">--</div>
                </div>
                <div>
                    <span class="text-slate-500 block">Location & Dept:</span>
                    <strong class="text-slate-200 text-sm" id="m-location">--</strong>
                    <div class="text-slate-400 mt-0.5" id="m-dept">--</div>
                </div>
            </div>

            <div class="space-y-3">
                <div>
                    <span class="text-xs text-slate-500 block">Category ➡️ Subcategory:</span>
                    <div class="text-sm font-semibold text-slate-200" id="m-category">--</div>
                </div>
                <div>
                    <span class="text-xs text-slate-500 block">Specific Issue:</span>
                    <div class="text-sm text-slate-300" id="m-issue">--</div>
                </div>
                <div>
                    <span class="text-xs text-slate-500 block">Full Description:</span>
                    <div class="text-xs bg-slate-950 p-3 rounded-lg border border-slate-800 text-slate-200 leading-relaxed font-mono whitespace-pre-wrap" id="m-desc">--</div>
                </div>
            </div>

            <div class="grid grid-cols-2 gap-4 text-xs border-t border-slate-800 pt-4">
                <div>
                    <span class="text-slate-500 block">Assigned Support Admin:</span>
                    <strong class="text-blue-400 text-sm" id="m-admin">--</strong>
                </div>
                <div>
                    <span class="text-slate-500 block">Current Status:</span>
                    <span id="m-status-badge">--</span>
                </div>
            </div>

            <div id="m-photo-container" class="hidden border-t border-slate-800 pt-4">
                <span class="text-xs text-slate-500 block mb-2">Attached Photo Media ID:</span>
                <div class="text-xs font-mono bg-slate-950 p-2.5 rounded-lg border border-slate-800 text-amber-400 flex items-center justify-between">
                    <span>Meta Photo ID: <strong id="m-photo-id">--</strong></span>
                    <span class="text-slate-400">Attached in WhatsApp</span>
                </div>
            </div>
        </div>
    </div>

    <!-- JavaScript Data Handler -->
    <script>
        let allRecords = [];

        async function fetchDashboardData() {
            const refreshIcon = document.getElementById('refresh-icon');
            if (refreshIcon) refreshIcon.classList.add('fa-spin');

            try {
                const res = await fetch('/api/dashboard/data');
                const data = await res.json();
                
                allRecords = data.records || [];
                updateStats(data.summary || {});
                renderTable(allRecords);
                
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

            const total = summary.total_tickets || 0;
            const completed = summary.completed_total || 0;
            const rate = total > 0 ? Math.round((completed / total) * 100) : 0;
            
            document.getElementById('stat-rate').innerText = rate + '%';
            document.getElementById('rate-bar').style.width = rate + '%';
        }

        function getStatusBadgeHtml(status) {
            if (status === 'Open') return '<span class="px-2.5 py-1 rounded-full text-xs font-semibold badge-open"><i class="fa-solid fa-circle-dot mr-1"></i>Open</span>';
            if (status === 'In Progress') return '<span class="px-2.5 py-1 rounded-full text-xs font-semibold badge-progress"><i class="fa-solid fa-spinner fa-spin mr-1"></i>In Progress</span>';
            if (status === 'Resolved') return '<span class="px-2.5 py-1 rounded-full text-xs font-semibold badge-resolved"><i class="fa-solid fa-check-double mr-1"></i>Resolved</span>';
            if (status === 'Closed') return '<span class="px-2.5 py-1 rounded-full text-xs font-semibold badge-closed"><i class="fa-solid fa-lock mr-1"></i>Closed</span>';
            return `<span class="px-2.5 py-1 rounded-full text-xs font-semibold bg-slate-800 text-slate-300">${status}</span>`;
        }

        function getPriorityBadgeHtml(p) {
            if (p === 'Urgent') return '<span class="px-2 py-0.5 rounded text-xs badge-urgent"><i class="fa-solid fa-fire mr-1"></i>Urgent</span>';
            if (p === 'High') return '<span class="px-2 py-0.5 rounded text-xs badge-high">High</span>';
            if (p === 'Medium') return '<span class="px-2 py-0.5 rounded text-xs badge-medium">Medium</span>';
            return '<span class="px-2 py-0.5 rounded text-xs badge-low">Low</span>';
        }

        function renderTable(records) {
            const tbody = document.getElementById('tickets-table-body');
            document.getElementById('visible-count').innerText = records.length;

            if (records.length === 0) {
                tbody.innerHTML = `<tr><td colspan="8" class="text-center py-12 text-slate-500">No ticket records found matching criteria.</td></tr>`;
                return;
            }

            let html = '';
            records.forEach(r => {
                const photoIcon = r.image_id ? `<span class="text-amber-400 ml-1" title="Photo Attachment Present"><i class="fa-solid fa-image"></i></span>` : '';

                html += `
                <tr class="hover:bg-slate-800/40 transition border-b border-slate-800/50 cursor-pointer" onclick='openModal(${JSON.stringify(r).replace(/'/g, "&apos;")})'>
                    <td class="px-6 py-4 font-mono font-bold text-blue-400 whitespace-nowrap">
                        ${r.ticket_number}${photoIcon}
                    </td>
                    <td class="px-6 py-4">
                        <div class="font-semibold text-slate-200">${escapeHtml(r.employee_name)}</div>
                        <div class="text-xs text-slate-400 font-mono">+${r.employee_phone}</div>
                    </td>
                    <td class="px-6 py-4">
                        <div class="text-slate-300">${escapeHtml(r.location)}</div>
                        <div class="text-xs text-slate-500">${escapeHtml(r.department)}</div>
                    </td>
                    <td class="px-6 py-4 max-w-xs">
                        <div class="text-xs font-semibold text-slate-300 truncate">${escapeHtml(r.category)} ➡️ ${escapeHtml(r.subcategory)}</div>
                        <div class="text-xs text-slate-400 truncate mt-0.5">${escapeHtml(r.issue)}</div>
                    </td>
                    <td class="px-6 py-4 whitespace-nowrap">
                        ${getPriorityBadgeHtml(r.priority)}
                    </td>
                    <td class="px-6 py-4 whitespace-nowrap">
                        ${getStatusBadgeHtml(r.status)}
                    </td>
                    <td class="px-6 py-4 whitespace-nowrap">
                        <div class="text-sm text-slate-200 font-medium">${escapeHtml(r.assigned_admin)}</div>
                    </td>
                    <td class="px-6 py-4 text-right whitespace-nowrap">
                        <button onclick='event.stopPropagation(); openModal(${JSON.stringify(r).replace(/'/g, "&apos;")})' class="text-xs bg-slate-800 hover:bg-slate-700 text-blue-400 px-3 py-1.5 rounded-lg border border-slate-700 font-medium transition">
                            View Details
                        </button>
                    </td>
                </tr>
                `;
            });
            tbody.innerHTML = html;
        }

        function filterTickets() {
            const query = document.getElementById('search-input').value.toLowerCase().strip();
            const statusFilter = document.getElementById('filter-status').value;
            const priorityFilter = document.getElementById('filter-priority').value;

            const filtered = allRecords.filter(r => {
                const matchesQuery = !query || 
                    r.ticket_number.toLowerCase().includes(query) ||
                    r.employee_name.toLowerCase().includes(query) ||
                    r.employee_phone.includes(query) ||
                    r.category.toLowerCase().includes(query) ||
                    r.issue.toLowerCase().includes(query) ||
                    r.description.toLowerCase().includes(query) ||
                    r.assigned_admin.toLowerCase().includes(query);

                const matchesStatus = statusFilter === 'ALL' || r.status === statusFilter;
                const matchesPriority = priorityFilter === 'ALL' || r.priority === priorityFilter;

                return matchesQuery && matchesStatus && matchesPriority;
            });

            renderTable(filtered);
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
