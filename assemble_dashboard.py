# assemble_dashboard.py
import ast

with open('app/dashboard.py.bak', 'r', encoding='utf-8') as f:
    orig_text = f.read()

dash_pos = orig_text.find('async def dashboard_view(request: Request):')
if dash_pos == -1:
    raise ValueError("dashboard_view not found in app/dashboard.py.bak")

base_code = orig_text[:dash_pos]

# Modernize login page button to shadcn style
base_code = base_code.replace(
    'bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-700 hover:to-indigo-700 active:scale-[0.99] text-white font-bold py-3.5 rounded-xl shadow-lg shadow-blue-500/25 transition duration-150',
    'bg-zinc-900 hover:bg-zinc-800 dark:bg-zinc-50 dark:hover:bg-zinc-200 text-white dark:text-zinc-900 font-semibold py-3 rounded-lg shadow-xs transition duration-150'
)
base_code = base_code.replace(" ⚠️ {discrepancy_trips}", " - {discrepancy_trips}")
base_code = base_code.replace(" ➔ ", " / ")

# Now we craft dashboard_view function code
new_dashboard_view = '''async def dashboard_view(request: Request):
    """Renders the executive shadcn/ui-styled Operations Dashboard with role-based domain access."""
    user = get_current_user_from_request(request)
    if not user:
        return RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)

    allowed = user.get("allowed_domains", ["it", "projects", "logistics", "fleet", "accounts", "admin"])
    default_tab = "fleet" if user["role"] in ("MASTER_ADMIN", "EXECUTIVE_OBSERVER", "FLEET_ADMIN", "SALES_ADMIN", "ACCOUNTS_USER", "LOGISTICS_MANAGER") else ("logistics" if user["role"] == "LOGISTICS_ADMIN" else ("projects" if user["role"] == "PROJECTS_ADMIN" else "it"))

    # Generate navigation tab buttons based on allowed domains
    tabs_html = []
    if "fleet" in allowed:
        tabs_html.append('<button id="btn-tab-fleet" onclick="switchDomain(\\'fleet\\')" class="tab-btn px-3.5 py-1.5 rounded-md text-xs font-medium text-zinc-600 dark:text-zinc-400 hover:text-zinc-900 dark:hover:text-zinc-100 transition-colors whitespace-nowrap cursor-pointer">Sales to Fleet</button>')
    if "it" in allowed:
        tabs_html.append('<button id="btn-tab-it" onclick="switchDomain(\\'it\\')" class="tab-btn px-3.5 py-1.5 rounded-md text-xs font-medium text-zinc-600 dark:text-zinc-400 hover:text-zinc-900 dark:hover:text-zinc-100 transition-colors whitespace-nowrap cursor-pointer">IT Support</button>')
    if "projects" in allowed:
        tabs_html.append('<button id="btn-tab-projects" onclick="switchDomain(\\'projects\\')" class="tab-btn px-3.5 py-1.5 rounded-md text-xs font-medium text-zinc-600 dark:text-zinc-400 hover:text-zinc-900 dark:hover:text-zinc-100 transition-colors whitespace-nowrap cursor-pointer">Building Projects</button>')
    if "logistics" in allowed:
        tabs_html.append('<button id="btn-tab-logistics" onclick="switchDomain(\\'logistics\\')" class="tab-btn px-3.5 py-1.5 rounded-md text-xs font-medium text-zinc-600 dark:text-zinc-400 hover:text-zinc-900 dark:hover:text-zinc-100 transition-colors whitespace-nowrap cursor-pointer">Workshop Fleet</button>')

    nav_tabs_markup = "\\n".join(tabs_html)
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
        sidebar_links.append('<button onclick="switchDomain(\\'fleet\\'); toggleSidebar(false);" class="w-full text-left px-3 py-2 rounded-lg text-xs font-medium text-zinc-700 dark:text-zinc-300 hover:bg-zinc-100 dark:hover:bg-zinc-800 hover:text-zinc-950 dark:hover:text-zinc-50 transition flex items-center gap-2">Sales to Fleet</button>')
    if "it" in allowed:
        sidebar_links.append('<button onclick="switchDomain(\\'it\\'); toggleSidebar(false);" class="w-full text-left px-3 py-2 rounded-lg text-xs font-medium text-zinc-700 dark:text-zinc-300 hover:bg-zinc-100 dark:hover:bg-zinc-800 hover:text-zinc-950 dark:hover:text-zinc-50 transition flex items-center gap-2">IT Support</button>')
    if "projects" in allowed:
        sidebar_links.append('<button onclick="switchDomain(\\'projects\\'); toggleSidebar(false);" class="w-full text-left px-3 py-2 rounded-lg text-xs font-medium text-zinc-700 dark:text-zinc-300 hover:bg-zinc-100 dark:hover:bg-zinc-800 hover:text-zinc-950 dark:hover:text-zinc-50 transition flex items-center gap-2">Building Projects</button>')
    if "logistics" in allowed:
        sidebar_links.append('<button onclick="switchDomain(\\'logistics\\'); toggleSidebar(false);" class="w-full text-left px-3 py-2 rounded-lg text-xs font-medium text-zinc-700 dark:text-zinc-300 hover:bg-zinc-100 dark:hover:bg-zinc-800 hover:text-zinc-950 dark:hover:text-zinc-50 transition flex items-center gap-2">Workshop Fleet</button>')

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

    sidebar_markup = "\\n".join(sidebar_links)

    nav_salespersons_opt = '<option value="salespersons">Sales Rep Balances</option>' if can_view_balances else ''
    nav_payments_opt = '<option value="payments">Payment History</option>' if can_view_balances else ''
    nav_ledger_opt = '<option value="ledger">Financial Audit Log</option>' if can_view_balances else ''
    nav_analytics_opt = '<option value="analytics">Data Analytics</option>' if is_master_admin else ''

    nav_salespersons_btn = '<button onclick="switchFleetSubView(\\'salespersons\\')" id="fleet-btn-salespersons" data-view="salespersons" class="fleet-quick-pill px-3 py-1.5 rounded-md text-xs font-medium bg-white/60 dark:bg-zinc-900/60 backdrop-blur-sm border border-zinc-200/80 dark:border-zinc-800/80 text-zinc-700 dark:text-zinc-300 hover:bg-zinc-100 dark:hover:bg-zinc-800 hover:text-zinc-950 dark:hover:text-zinc-50 transition cursor-pointer whitespace-nowrap">Sales Reps</button>' if can_view_balances else ''
    nav_payments_btn = '<button onclick="switchFleetSubView(\\'payments\\')" id="fleet-btn-payments" data-view="payments" class="fleet-quick-pill px-3 py-1.5 rounded-md text-xs font-medium bg-white/60 dark:bg-zinc-900/60 backdrop-blur-sm border border-zinc-200/80 dark:border-zinc-800/80 text-zinc-700 dark:text-zinc-300 hover:bg-zinc-100 dark:hover:bg-zinc-800 hover:text-zinc-950 dark:hover:text-zinc-50 transition cursor-pointer whitespace-nowrap">Payments</button>' if can_view_balances else ''
    nav_ledger_btn = '<button onclick="switchFleetSubView(\\'ledger\\')" id="fleet-btn-ledger" data-view="ledger" class="fleet-quick-pill px-3 py-1.5 rounded-md text-xs font-medium bg-white/60 dark:bg-zinc-900/60 backdrop-blur-sm border border-zinc-200/80 dark:border-zinc-800/80 text-zinc-700 dark:text-zinc-300 hover:bg-zinc-100 dark:hover:bg-zinc-800 hover:text-zinc-950 dark:hover:text-zinc-50 transition cursor-pointer whitespace-nowrap">Audit Log</button>' if can_view_balances else ''
    nav_analytics_btn = '<button onclick="switchFleetSubView(\\'analytics\\')" id="fleet-btn-analytics" data-view="analytics" class="fleet-quick-pill px-3 py-1.5 rounded-md text-xs font-medium bg-white/60 dark:bg-zinc-900/60 backdrop-blur-sm border border-zinc-200/80 dark:border-zinc-800/80 text-zinc-700 dark:text-zinc-300 hover:bg-zinc-100 dark:hover:bg-zinc-800 hover:text-zinc-950 dark:hover:text-zinc-50 transition cursor-pointer whitespace-nowrap">Analytics</button>' if is_master_admin else ''

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
    <script src="/static/js/dashboard.js?v=2.5.0"></script>
</body>
</html>"""
    return HTMLResponse(content=html_content)
'''

full_code = base_code + new_dashboard_view

print("Validating python syntax with ast.parse...")
ast.parse(full_code)

with open('app/dashboard.py', 'w', encoding='utf-8') as f:
    f.write(full_code)

print("Successfully written to app/dashboard.py!")
