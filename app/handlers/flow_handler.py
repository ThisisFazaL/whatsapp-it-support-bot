import datetime
import random
import re
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import (
    Category, Subcategory, IssueType, Priority, TicketStatus, Location,
    Ticket, TicketAssignment, MaintenanceTicket, MaintenanceTicketAssignment,
    SupportAdmin, AdminCategoryMapping, Employee, ConversationState
)
from app.state_manager import set_user_state, clear_user_state
from app.meta_api import meta_api

GLOBAL_RESET_KEYWORDS = {"hi", "hello", "menu", "reset", "cancel", "start"}
SKIP_KEYWORDS = {"skip", "no", "none", "pass", "next", "btn_skip_photo"}

def extract_numeric_choice(text: str) -> str:
    """Extracts first sequence of digits from text string (e.g. '1.', 'option 2' -> '1', '2')."""
    match = re.search(r"\d+", text.strip()) if text else None
    return match.group(0) if match else text.strip().lower()

async def generate_ticket_number(session: AsyncSession, domain: str = "IT") -> str:
    """Generates a unique ticket number in format: TKT-YYYYMMDD-XXXXX or TKT-MNT-YYYYMMDD-XXXXX"""
    prefix = "TKT-MNT" if domain == "MAINTENANCE" else "TKT"
    today_str = datetime.datetime.utcnow().strftime("%Y%m%d")
    
    if domain == "MAINTENANCE":
        stmt = select(func.count(MaintenanceTicket.ticket_id))
        res = await session.execute(stmt)
        total_count = res.scalar() or 0
        ticket_num = f"{prefix}-{today_str}-{str(total_count + 1).zfill(5)}"
        check_stmt = select(MaintenanceTicket).where(MaintenanceTicket.ticket_number == ticket_num)
        existing = (await session.execute(check_stmt)).scalars().first()
    else:
        stmt = select(func.count(Ticket.ticket_id))
        res = await session.execute(stmt)
        total_count = res.scalar() or 0
        ticket_num = f"{prefix}-{today_str}-{str(total_count + 1).zfill(5)}"
        check_stmt = select(Ticket).where(Ticket.ticket_number == ticket_num)
        existing = (await session.execute(check_stmt)).scalars().first()

    if existing:
        random_suffix = str(random.randint(100, 999))
        ticket_num = f"{prefix}-{today_str}-{str(total_count + 1).zfill(5)}{random_suffix}"

    return ticket_num

async def start_ticket_creation_flow(session: AsyncSession, phone: str, employee: Employee = None):
    """
    Starts ticket creation flow.
    Checks if employee or admin is authorized for Maintenance. If dual-role, presents 2 Interactive Buttons.
    """
    is_maint_reporter = employee.is_maintenance_reporter if employee else False
    is_master = False
    is_maint_admin = False

    # Check phone directly in Employee table
    if not is_maint_reporter and phone:
        e_res = await session.execute(select(Employee).where(Employee.phone == phone))
        emp_obj = e_res.scalars().first()
        if emp_obj:
            is_maint_reporter = emp_obj.is_maintenance_reporter

    # Check SupportAdmin table
    if phone:
        a_res = await session.execute(select(SupportAdmin).where(SupportAdmin.phone == phone))
        adm_obj = a_res.scalars().first()
        if adm_obj:
            is_master = adm_obj.is_master_admin
            is_maint_admin = adm_obj.is_maintenance_admin

    if is_maint_reporter or is_maint_admin or is_master or phone == settings.master_admin_phone:
        # All Authorized Projects Reporters (Paida, Fazal, Arif, Zayn, Faizan) are Dual-Role Users
        body = "👋 *Welcome to Support Portal*\n\nPlease select the type of ticket you would like to create:"
        buttons = [
            {"id": "btn_domain_it", "title": "💻 IT Support"},
            {"id": "btn_domain_maint", "title": "🏗️ Projects"}
        ]
        await set_user_state(session, phone, "select_domain", {})
        await meta_api.send_button_message(
            to_phone=phone,
            body_text=body,
            buttons=buttons,
            header_text="⚙️ SELECT SUPPORT DOMAIN"
        )
    else:
        # Standard IT Employee -> Go DIRECTLY to IT Categories Menu (NEVER ask location for IT!)
        await send_categories_menu(session, phone, domain="IT", data={"domain": "IT"})

async def start_location_selection(session: AsyncSession, phone: str, domain: str = "MAINTENANCE"):
    """Presents project site location selection numbered text list for Building Projects."""
    stmt = select(Location).order_by(Location.location_id)
    res = await session.execute(stmt)
    locations = res.scalars().all()

    loc_list = []
    loc_map = {}
    for idx, loc in enumerate(locations):
        num_str = str(idx + 1)
        loc_list.append(f"{num_str}. *{loc.location_name}*")
        loc_map[num_str] = loc.location_id

    # Add 'Other' option
    other_idx = str(len(locations) + 1)
    loc_list.append(f"{other_idx}. *Other (Type location)*")
    loc_map[other_idx] = "OTHER"

    loc_text = "\n".join(loc_list)
    msg = (
        f"🏢 *Select Project Location*\n\n"
        f"Please select the project location by replying with the corresponding number:\n\n"
        f"{loc_text}"
    )

    data = {"domain": domain, "locations_map": loc_map}
    await set_user_state(session, phone, "select_location", data)
    await meta_api.send_text_message(phone, msg)

async def send_categories_menu(session: AsyncSession, phone: str, domain: str = "IT", data: dict = None):
    """Fetches categories by domain and sends menu to user, updating state to awaiting_category."""
    norm_domain = (domain or "IT").upper()
    stmt = select(Category).where(Category.domain.ilike(norm_domain), Category.active == True).order_by(Category.category_id)
    res = await session.execute(stmt)
    categories = res.scalars().all()

    if not categories:
        # Fallback to IT domain if not found
        stmt = select(Category).where(Category.domain.ilike("IT"), Category.active == True).order_by(Category.category_id)
        categories = (await session.execute(stmt)).scalars().all()

    cat_list_str = "\n".join([f"{idx+1}. *{cat.category_name}*" for idx, cat in enumerate(categories)])
    domain_title = "🏗️ Building Projects" if norm_domain == "MAINTENANCE" else "💻 IT Support"
    msg = (
        f"📌 *Select {domain_title} Category*\n\n"
        f"Please select a category by replying with the corresponding number:\n\n"
        f"{cat_list_str}\n\n"
        f"💡 _Reply 'reset' to start over._"
    )

    cat_map = {str(idx + 1): cat.category_id for idx, cat in enumerate(categories)}
    current_data = data or {}
    current_data["domain"] = domain
    current_data["categories_map"] = cat_map

    await set_user_state(session, phone, "awaiting_category", current_data)
    await meta_api.send_text_message(phone, msg)

async def handle_flow(
    session: AsyncSession,
    employee: Employee,
    message_text: str,
    state: ConversationState,
    image_id: str = None,
    sender_phone: str = None
):
    phone = employee.phone if employee else sender_phone
    if not phone:
        return
    text_clean = message_text.strip().lower()
    choice_num = extract_numeric_choice(message_text)

    # Global Reset Check
    if text_clean in GLOBAL_RESET_KEYWORDS or not state or not state.current_step:
        await start_ticket_creation_flow(session, phone, employee)
        return

    step = state.current_step
    data = state.current_data or {}
    domain = data.get("domain", "IT")

    # STEP 0: Select Domain (Dual-Role Buttons)
    if step == "select_domain":
        if "maint" in text_clean or "btn_domain_maint" in text_clean or "project" in text_clean or choice_num == "2":
            await start_location_selection(session, phone, domain="MAINTENANCE")
        else:
            # IT Support -> Skip Location Prompt completely! Pull from DB profile directly!
            await send_categories_menu(session, phone, domain="IT", data={"domain": "IT"})
        return

    # STEP 1: Select Location (Numbered Text List - ONLY for Projects domain)
    elif step == "select_location":
        loc_map = data.get("locations_map", {})
        selected_loc_id = loc_map.get(choice_num) or loc_map.get(text_clean)

        if not selected_loc_id:
            await meta_api.send_text_message(
                phone,
                "⚠️ *Invalid Option*: Please reply with a valid location number from the list (e.g. *1*, *2*)."
            )
            return

        if selected_loc_id == "OTHER":
            await set_user_state(session, phone, "awaiting_other_location", data)
            await meta_api.send_text_message(
                phone,
                "🏢 *Type Custom Project Location*\n\nPlease type the location name or site address:"
            )
            return
        else:
            loc_obj = await session.get(Location, int(selected_loc_id))
            data["location_id"] = int(selected_loc_id)
            data["location_name"] = loc_obj.location_name if loc_obj else "On-Site"

            # Ask for Specific Room / Area for Projects
            await set_user_state(session, phone, "awaiting_room_area", data)
            await meta_api.send_text_message(
                phone,
                "📍 *Specify Room / Area*\n\nPlease type the specific room, floor, or area:\n(e.g., *Executive Kitchen*, *2nd Floor Restroom*, *Warehouse Bay 3*, *Reception*)"
            )
            return

    # STEP 1.2: Awaiting Custom Project Location Text
    elif step == "awaiting_other_location":
        custom_loc = message_text.strip()
        if len(custom_loc) < 2:
            await meta_api.send_text_message(phone, "⚠️ Please type a valid location name:")
            return

        data["location_name"] = custom_loc
        data["location_id"] = None

        await set_user_state(session, phone, "awaiting_room_area", data)
        await meta_api.send_text_message(
            phone,
            "📍 *Specify Room / Area*\n\nPlease type the specific room, floor, or area:\n(e.g., *Executive Kitchen*, *2nd Floor Restroom*, *Warehouse Bay 3*, *Reception*)"
        )
        return

    # STEP 1.5: Awaiting Room / Area Text
    elif step == "awaiting_room_area":
        room_text = message_text.strip()
        if len(room_text) < 2:
            await meta_api.send_text_message(phone, "⚠️ Please type a valid room or area description:")
            return

        data["room_area"] = room_text
        await send_categories_menu(session, phone, domain="MAINTENANCE", data=data)
        return

    # STEP 2: Awaiting Category
    elif step == "awaiting_category":
        cat_map = data.get("categories_map", {})
        selected_cat_id = cat_map.get(choice_num) or cat_map.get(text_clean)
        
        if not selected_cat_id:
            await meta_api.send_text_message(
                phone,
                "⚠️ *Invalid Option*: Please reply with a valid category number from the menu."
            )
            return

        sub_stmt = (
            select(Subcategory)
            .where(Subcategory.category_id == selected_cat_id, Subcategory.active == True)
            .order_by(Subcategory.subcategory_id)
        )
        sub_res = await session.execute(sub_stmt)
        subcategories = sub_res.scalars().all()

        if not subcategories:
            data["category_id"] = selected_cat_id
            data["subcategory_id"] = None
            data["issue_type_id"] = None
            await set_user_state(session, phone, "awaiting_description", data)
            await meta_api.send_text_message(
                phone,
                "📝 *Describe Your Issue*\n\nPlease type a brief description of the problem:"
            )
            return

        sub_list_str = "\n".join([f"{idx+1}. *{sub.subcategory_name}*" for idx, sub in enumerate(subcategories)])
        msg = (
            f"📁 *Select Subcategory*\n\n"
            f"Please choose a subcategory by replying with the number:\n\n"
            f"{sub_list_str}"
        )

        sub_map = {str(idx + 1): sub.subcategory_id for idx, sub in enumerate(subcategories)}
        data["category_id"] = selected_cat_id
        data["subcategories_map"] = sub_map
        
        await set_user_state(session, phone, "awaiting_subcategory", data)
        await meta_api.send_text_message(phone, msg)
        return

    # STEP 3: Awaiting Subcategory
    elif step == "awaiting_subcategory":
        sub_map = data.get("subcategories_map", {})
        selected_sub_id = sub_map.get(choice_num) or sub_map.get(text_clean)

        if not selected_sub_id:
            await meta_api.send_text_message(
                phone,
                "⚠️ *Invalid Option*: Please reply with a valid number from the subcategory list."
            )
            return

        issue_stmt = (
            select(IssueType)
            .where(IssueType.subcategory_id == selected_sub_id, IssueType.active == True)
            .order_by(IssueType.issue_type_id)
        )
        issue_res = await session.execute(issue_stmt)
        issues = issue_res.scalars().all()

        if not issues:
            data["subcategory_id"] = selected_sub_id
            data["issue_type_id"] = None
            await set_user_state(session, phone, "awaiting_description", data)
            await meta_api.send_text_message(
                phone,
                "📝 *Describe Your Issue*\n\nPlease type a brief description of the problem:"
            )
            return

        issue_list_str = "\n".join([f"{idx+1}. *{issue.issue_name}*" for idx, issue in enumerate(issues)])
        msg = (
            f"🛠️ *Select Specific Issue*\n\n"
            f"Please select the issue matching your problem:\n\n"
            f"{issue_list_str}"
        )

        issue_map = {str(idx + 1): issue.issue_type_id for idx, issue in enumerate(issues)}
        data["subcategory_id"] = selected_sub_id
        data["issues_map"] = issue_map

        await set_user_state(session, phone, "awaiting_issue", data)
        await meta_api.send_text_message(phone, msg)
        return

    # STEP 4: Awaiting Issue Type
    elif step == "awaiting_issue":
        issue_map = data.get("issues_map", {})
        selected_issue_id = issue_map.get(choice_num) or issue_map.get(text_clean)

        if not selected_issue_id:
            await meta_api.send_text_message(
                phone,
                "⚠️ *Invalid Option*: Please reply with a valid number from the issue list."
            )
            return

        data["issue_type_id"] = selected_issue_id
        await set_user_state(session, phone, "awaiting_description", data)
        await meta_api.send_text_message(
            phone,
            "📝 *Describe Your Issue*\n\nPlease reply with a brief description of the problem:"
        )
        return

    # STEP 5: Awaiting Description -> Send 3 Interactive Priority Buttons
    elif step == "awaiting_description":
        description = message_text.strip()
        if len(description) < 3 and not image_id:
            await meta_api.send_text_message(phone, "⚠️ Description is too short. Please provide a brief description:")
            return

        data["description"] = description
        if image_id:
            data["image_id"] = image_id

        # Send 3 Interactive Priority Buttons
        body = "🚨 *Select Priority Level*\n\nHow urgent is this issue?"
        buttons = [
            {"id": "btn_prio_low", "title": "🟢 Low"},
            {"id": "btn_prio_med", "title": "🟡 Medium"},
            {"id": "btn_prio_crit", "title": "🔴 Critical"}
        ]
        await set_user_state(session, phone, "select_priority", data)
        await meta_api.send_button_message(
            to_phone=phone,
            body_text=body,
            buttons=buttons,
            header_text="🚨 TICKET PRIORITY"
        )
        return

    # STEP 6: Select Priority (Buttons)
    elif step == "select_priority":
        p_id = 2 # Default Medium
        if "low" in text_clean or "btn_prio_low" in text_clean or choice_num == "1":
            p_id = 1
        elif "crit" in text_clean or "btn_prio_crit" in text_clean or choice_num == "3":
            p_id = 3
        elif "med" in text_clean or "btn_prio_med" in text_clean or choice_num == "2":
            p_id = 2

        data["priority_id"] = p_id

        # If MAINTENANCE domain, ask Safety Hazard Flag via 2 Interactive Buttons
        if domain == "MAINTENANCE":
            body = "⚠️ *Safety Hazard Check*\n\nIs this issue an URGENT SAFETY HAZARD?\n(e.g., exposed live electrical wire, active roof flooding, structural risk)"
            buttons = [
                {"id": "btn_hazard_yes", "title": "⚠️ Yes - Safety Hazard"},
                {"id": "btn_hazard_no", "title": "🟢 No - Standard Issue"}
            ]
            await set_user_state(session, phone, "select_safety_hazard", data)
            await meta_api.send_button_message(
                to_phone=phone,
                body_text=body,
                buttons=buttons,
                header_text="⚠️ SAFETY HAZARD FLAG"
            )
            return

        # Otherwise go directly to photo step
        await send_photo_attachment_prompt(session, phone, data)
        return

    # STEP 6.5: Select Safety Hazard (2 Buttons for Maintenance)
    elif step == "select_safety_hazard":
        is_hazard = "yes" in text_clean or "btn_hazard_yes" in text_clean or choice_num == "1"
        data["is_safety_hazard"] = is_hazard

        await send_photo_attachment_prompt(session, phone, data)
        return

    # STEP 7: Awaiting Image / Skip Button
    elif step == "awaiting_image":
        if image_id:
            data["image_id"] = image_id
        elif text_clean not in SKIP_KEYWORDS and len(text_clean) > 2:
            data["description"] = data.get("description", "") + " | " + message_text.strip()

        # Generate Final Ticket!
        await finalize_ticket_creation(session, phone, employee, data)
        return

async def send_photo_attachment_prompt(session: AsyncSession, phone: str, data: dict):
    """Sends optional photo prompt with 1 Interactive 'Skip' Button."""
    body = "🖼️ *Attach Photo (Optional)*\n\nYou can send a photo of the problem right now, or tap 'Skip' to submit:"
    buttons = [
        {"id": "btn_skip_photo", "title": "⏩ Skip Photo"}
    ]
    await set_user_state(session, phone, "awaiting_image", data)
    await meta_api.send_button_message(
        to_phone=phone,
        body_text=body,
        buttons=buttons,
        header_text="📸 PHOTO ATTACHMENT"
    )

async def finalize_ticket_creation(session: AsyncSession, phone: str, employee: Employee, data: dict):
    """Creates ticket in database and routes alert to designated Support Admins."""
    domain = data.get("domain", "IT")
    category_id = data.get("category_id")
    subcategory_id = data.get("subcategory_id")
    issue_type_id = data.get("issue_type_id")
    is_safety_hazard = data.get("is_safety_hazard", False)
    description = data.get("description", "No description provided")
    ticket_image_id = data.get("image_id")
    priority_id = data.get("priority_id", 2)

    emp_id = employee.employee_id if employee else None
    if not emp_id and phone:
        e_res = await session.execute(select(Employee).where(Employee.phone == phone))
        emp_obj = e_res.scalars().first()
        if emp_obj:
            employee = emp_obj
            emp_id = emp_obj.employee_id

    if not emp_id:
        emp_obj = Employee(full_name="Staff User", phone=phone, active=True)
        session.add(emp_obj)
        await session.flush()
        employee = emp_obj
        emp_id = emp_obj.employee_id

    if domain == "IT":
        # Extract location directly from employee's registered profile in database!
        emp_loc_id = employee.location_id if employee else None
        emp_loc_name = employee.location.location_name if employee and employee.location else None
        if not emp_loc_name and emp_loc_id:
            loc_obj = await session.get(Location, emp_loc_id)
            emp_loc_name = loc_obj.location_name if loc_obj else None
        loc_name = emp_loc_name or "On-Site"
        location_id = emp_loc_id
        room_area = None
    else:
        # Projects domain -> Use location & room selected by user
        location_id = data.get("location_id")
        loc_name = data.get("location_name", "On-Site")
        room_area = data.get("room_area", "N/A")

    ticket_number = await generate_ticket_number(session, domain=domain)

    if domain == "MAINTENANCE":
        new_ticket = MaintenanceTicket(
            ticket_number=ticket_number,
            employee_id=emp_id,
            domain=domain,
            category_id=category_id,
            subcategory_id=subcategory_id,
            issue_type_id=issue_type_id,
            room_area=room_area,
            is_safety_hazard=is_safety_hazard,
            description=description,
            image_id=ticket_image_id,
            priority_id=priority_id,
            status_id=1 # Open
        )
    else:
        new_ticket = Ticket(
            ticket_number=ticket_number,
            employee_id=emp_id,
            location_id=location_id,
            domain=domain,
            category_id=category_id,
            subcategory_id=subcategory_id,
            issue_type_id=issue_type_id,
            room_area=room_area,
            is_safety_hazard=is_safety_hazard,
            description=description,
            image_id=ticket_image_id,
            priority_id=priority_id,
            status_id=1 # Open
        )
    session.add(new_ticket)
    await session.flush()

    # Load details for routing & notifications
    cat_obj = await session.get(Category, category_id) if category_id else None
    sub_obj = await session.get(Subcategory, subcategory_id) if subcategory_id else None
    issue_obj = await session.get(IssueType, issue_type_id) if issue_type_id else None
    p_obj = await session.get(Priority, priority_id) if priority_id else None

    # Route Maintenance Tickets vs IT Tickets
    assigned_admin = None
    target_admins = []
    buttons = []
    footer = ""

    if domain == "MAINTENANCE":
        maint_admins_stmt = select(SupportAdmin).where(SupportAdmin.is_maintenance_admin == True, SupportAdmin.active == True)
        target_admins = list((await session.execute(maint_admins_stmt)).scalars().all())
        assigned_admin = None
        buttons = [
            {"id": f"claim_{ticket_number}", "title": "🔵 Claim Ticket"}
        ]
        footer = "Tap button below to claim ticket"
    else:
        # IT Ticket Routing:
        cat_name_str = (cat_obj.category_name if cat_obj else "").lower()
        sub_name_str = (sub_obj.subcategory_name if sub_obj else "").lower()

        # Faisal Kassim handles:
        # 1. Security & Access Control (CCTV, Cameras, Access Control, Automatic Gates, Turnstiles, Biometrics)
        # 2. Electrical & Power Systems (Fittings, Wiring, Electronics, Power Supplies, Lights, Generator, UPS)
        # 3. Other / Custom Support -> General Maintenance & Facilities (Desk/Chair repair, Drawers, Furniture, Office Facilities)
        is_faisal_cat = (
            any(k in cat_name_str for k in ["security", "access control", "electrical", "power", "custom support", "other / custom", "facilities"]) or
            any(k in sub_name_str for k in [
                "cctv", "camera", "surveillance", "access control", "gate", "turnstile", "biometric",
                "electrical", "wiring", "fitting", "light", "electronics", "power supply", "generator", "ups",
                "general maintenance", "facilities", "desk", "chair", "drawer", "furniture"
            ])
        ) and not any(it_k in cat_name_str for it_k in ["computing", "hardware", "software", "network", "connectivity", "account"])

        if is_faisal_cat:
            # Route exclusively to Faisal Kassim (+263 780 100 503)
            faisal_stmt = select(SupportAdmin).where(
                (SupportAdmin.phone == "263780100503") | (SupportAdmin.phone.like("%780100503%")),
                SupportAdmin.active == True
            )
            faisal_admin = (await session.execute(faisal_stmt)).scalars().first()
            assigned_admin = faisal_admin
            target_admins = [faisal_admin] if faisal_admin else []
            buttons = [
                {"id": f"resolve_{ticket_number}", "title": "🟢 Resolve Ticket"}
            ]
            footer = "Tap button below to resolve"
        else:
            # Core IT Support (Computers, Laptops, Printers, Scanners, Peripherals, Wi-Fi, Internet, LAN, Outlook, Software, Passwords):
            # Route to Combined Kevin Chikati (+263 718 627 526) & Ellias Murenga (+263 788 843 579) with Claim button!
            kevin_ellias_stmt = select(SupportAdmin).where(
                SupportAdmin.phone.in_(["263718627526", "263788843579", "+263718627526", "+263788843579"]),
                SupportAdmin.active == True
            )
            target_admins = list((await session.execute(kevin_ellias_stmt)).scalars().all())
            
            # Fallback if phone format differs: query by first name
            if len(target_admins) < 2:
                name_stmt = select(SupportAdmin).where(
                    (SupportAdmin.full_name.ilike("%Kevin%")) | (SupportAdmin.full_name.ilike("%Ellias%")),
                    SupportAdmin.active == True
                )
                target_admins = list((await session.execute(name_stmt)).scalars().all())

            # Ticket remains unassigned until claimed
            assigned_admin = None
            buttons = [
                {"id": f"claim_{ticket_number}", "title": "✋ Claim Ticket"},
                {"id": f"resolve_{ticket_number}", "title": "🟢 Resolve Ticket"}
            ]
            footer = "Tap 'Claim Ticket' to assign to yourself"

    # Add initial assignment in DB if an admin is pre-assigned (e.g. Faisal or Maintenance)
    if assigned_admin:
        if domain == "MAINTENANCE":
            assignment = MaintenanceTicketAssignment(
                ticket_id=new_ticket.ticket_id,
                admin_id=assigned_admin.admin_id
            )
        else:
            assignment = TicketAssignment(
                ticket_id=new_ticket.ticket_id,
                admin_id=assigned_admin.admin_id
            )
        session.add(assignment)

    await session.commit()

    await clear_user_state(session, phone)

    hazard_notice = "\n⚠️ *SAFETY HAZARD:* 🚨 URGENT SAFETY HAZARD FLAG!" if is_safety_hazard else ""
    domain_label = "🏗️ PROJECTS" if domain == "MAINTENANCE" else "💻 IT SUPPORT"
    location_line = f"🏢 *Location:* {loc_name}" + (f" ({room_area})" if room_area else "") + "\n" if loc_name else ""

    # Send Confirmation to Reporter
    emp_confirmation = (
        f"✅ *{domain_label} TICKET CREATED!*\n\n"
        f"🎫 *Ticket ID:* `{ticket_number}`\n"
        f"{location_line}"
        f"📌 *Category:* {cat_obj.category_name if cat_obj else 'N/A'}\n"
        f"⚙️ *Issue:* {issue_obj.issue_name if issue_obj else 'Custom Issue'}\n"
        f"🚨 *Priority:* {p_obj.priority_name if p_obj else 'Medium'}{hazard_notice}\n"
        f"📝 *Description:* {description}\n\n"
        f"Our support team has been notified on WhatsApp and will assist shortly!"
    )
    await meta_api.send_text_message(phone, emp_confirmation)

    # Send Alert with Claim / Resolve Buttons to target Support Admins
    emp_name = employee.full_name if employee else "Staff Reporter"
    emp_phone = employee.phone if employee else phone
    dept_name = employee.department.department_name if employee and employee.department else ""
    dept_str = f" ({dept_name})" if dept_name else ""

    header = f"🚨 NEW {domain_label} TICKET"
    loc_body = f"🏢 *Location:* {loc_name}\n" + (f"📍 *Room / Area:* {room_area}\n" if room_area else "") if loc_name else ""
    body = (
        f"🎫 *Ticket ID:* `{ticket_number}`\n"
        f"👤 *Reporter:* {emp_name}{dept_str} (`+{emp_phone}`)\n"
        f"{loc_body}"
        f"📌 *Category:* {cat_obj.category_name if cat_obj else 'N/A'} ➡️ {sub_obj.subcategory_name if sub_obj else 'N/A'}\n"
        f"⚙️ *Issue:* {issue_obj.issue_name if issue_obj else 'Custom'}\n"
        f"🚨 *Priority:* {p_obj.priority_name if p_obj else 'Medium'}{hazard_notice}\n"
        f"📝 *Description:* {description}"
    )

    # Broadcast to all target admins (both Kevin & Ellias receive it!)
    for t_adm in target_admins:
        await meta_api.send_button_message(
            to_phone=t_adm.phone,
            body_text=body,
            buttons=buttons,
            header_text=header,
            footer_text=footer,
            image_id=ticket_image_id
        )

    # Send Alert to Master Admin Fazal
    if settings.master_admin_phone:
        master_body = f"ℹ️ *[MASTER ALERT]* New {domain_label} Ticket `{ticket_number}`.\n\n" + body
        master_buttons = [
            {"id": f"resolve_{ticket_number}", "title": "🟢 Resolve Ticket"}
        ]
        await meta_api.send_button_message(
            to_phone=settings.master_admin_phone,
            body_text=master_body,
            buttons=master_buttons,
            header_text=f"🚨 MASTER ALERT ({domain_label})",
            footer_text="Master Admin: Tap button to resolve anytime",
            image_id=ticket_image_id
        )
