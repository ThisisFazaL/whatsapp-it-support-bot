import datetime
import random
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import (
    Category, Subcategory, IssueType, Priority, TicketStatus,
    Ticket, TicketAssignment, SupportAdmin, AdminCategoryMapping, Employee, ConversationState
)
from app.state_manager import set_user_state, clear_user_state
from app.meta_api import meta_api

GLOBAL_RESET_KEYWORDS = {"hi", "hello", "menu", "reset", "cancel", "start"}
SKIP_KEYWORDS = {"skip", "no", "none", "pass", "next"}

def extract_numeric_choice(text: str) -> str:
    """Extracts first sequence of digits from text string (e.g. '1.', 'option 2' -> '1', '2')."""
    match = re.search(r"\d+", text.strip()) if text else None
    return match.group(0) if match else text.strip().lower()

import re

async def generate_ticket_number(session: AsyncSession) -> str:
    """Generates a unique ticket number in format: TKT-YYYYMMDD-XXXXX"""
    today_str = datetime.datetime.utcnow().strftime("%Y%m%d")
    stmt = select(func.count(Ticket.ticket_id))
    res = await session.execute(stmt)
    total_count = res.scalar() or 0
    
    seq_num = total_count + 1
    ticket_num = f"TKT-{today_str}-{str(seq_num).zfill(5)}"
    
    check_stmt = select(Ticket).where(Ticket.ticket_number == ticket_num)
    existing = (await session.execute(check_stmt)).scalars().first()
    if existing:
        random_suffix = str(random.randint(100, 999))
        ticket_num = f"TKT-{today_str}-{str(seq_num).zfill(5)}{random_suffix}"

    return ticket_num

async def send_categories_menu(session: AsyncSession, phone: str):
    """Fetches categories and sends menu to user, updating state to awaiting_category."""
    stmt = select(Category).where(Category.active == True).order_by(Category.category_id)
    res = await session.execute(stmt)
    categories = res.scalars().all()

    if not categories:
        await meta_api.send_text_message(phone, "No active IT support categories found. Please contact IT directly.")
        return

    cat_list_str = "\n".join([f"{idx+1}️⃣ *{cat.category_name}*" for idx, cat in enumerate(categories)])
    msg = (
        f"👋 *Welcome to IT Support Ticket Bot*\n\n"
        f"Please select a category by replying with the corresponding number:\n\n"
        f"{cat_list_str}\n\n"
        f"💡 _Reply 'my tickets' to view your active tickets, or 'reset' to start over._"
    )

    cat_map = {str(idx + 1): cat.category_id for idx, cat in enumerate(categories)}
    await set_user_state(session, phone, "awaiting_category", {"categories_map": cat_map})
    await meta_api.send_text_message(phone, msg)

async def handle_flow(
    session: AsyncSession,
    employee: Employee,
    message_text: str,
    state: ConversationState,
    image_id: str = None
):
    phone = employee.phone
    text_clean = message_text.strip().lower()
    choice_num = extract_numeric_choice(message_text)

    # Global Reset Check
    if text_clean in GLOBAL_RESET_KEYWORDS or not state or not state.current_step:
        await send_categories_menu(session, phone)
        return

    step = state.current_step
    data = state.current_data or {}

    # STEP 1: Awaiting Category
    if step == "awaiting_category":
        cat_map = data.get("categories_map", {})
        selected_cat_id = cat_map.get(choice_num) or cat_map.get(text_clean)
        
        if not selected_cat_id:
            await meta_api.send_text_message(
                phone,
                "⚠️ *Invalid Option*: Please reply with a valid category number from the menu (e.g. *1*, *2*)."
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
            await meta_api.send_text_message(phone, "No subcategories found for this category. Resetting state.")
            await send_categories_menu(session, phone)
            return

        sub_list_str = "\n".join([f"{idx+1}️⃣ *{sub.subcategory_name}*" for idx, sub in enumerate(subcategories)])
        msg = (
            f"📁 *Select Subcategory*\n\n"
            f"Please choose a subcategory:\n\n"
            f"{sub_list_str}"
        )

        sub_map = {str(idx + 1): sub.subcategory_id for idx, sub in enumerate(subcategories)}
        data["category_id"] = selected_cat_id
        data["subcategories_map"] = sub_map
        
        await set_user_state(session, phone, "awaiting_subcategory", data)
        await meta_api.send_text_message(phone, msg)
        return

    # STEP 2: Awaiting Subcategory
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
                "📝 *Describe Your Issue*\n\nPlease type a brief description of the problem you are experiencing:"
            )
            return

        issue_list_str = "\n".join([f"{idx+1}️⃣ *{issue.issue_name}*" for idx, issue in enumerate(issues)])
        msg = (
            f"🛠️ *Select Specific Issue*\n\n"
            f"Please select the issue that best matches your problem:\n\n"
            f"{issue_list_str}"
        )

        issue_map = {str(idx + 1): issue.issue_type_id for idx, issue in enumerate(issues)}
        data["subcategory_id"] = selected_sub_id
        data["issues_map"] = issue_map

        await set_user_state(session, phone, "awaiting_issue", data)
        await meta_api.send_text_message(phone, msg)
        return

    # STEP 3: Awaiting Issue Type
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
            "📝 *Describe Your Issue*\n\nPlease reply with a brief description of your issue (e.g. error message, computer model, physical damage):"
        )
        return

    # STEP 4: Awaiting Description -> Ask for Optional Image
    elif step == "awaiting_description":
        description = message_text.strip()
        if len(description) < 3 and not image_id:
            await meta_api.send_text_message(phone, "⚠️ Description is too short. Please provide a brief description:")
            return

        data["description"] = description
        if image_id:
            data["image_id"] = image_id

        await set_user_state(session, phone, "awaiting_image", data)
        await meta_api.send_text_message(
            phone,
            "🖼️ *Attach Photo of Issue (Optional)*\n\n"
            "You can send a photo/image of the problem right now, or reply *'skip'* to proceed to priority selection:"
        )
        return

    # STEP 4.5: Awaiting Image
    elif step == "awaiting_image":
        if image_id:
            data["image_id"] = image_id
        elif text_clean not in SKIP_KEYWORDS and len(text_clean) > 2:
            data["description"] = data.get("description", "") + " | " + message_text.strip()

        p_stmt = select(Priority).order_by(Priority.priority_id)
        p_res = await session.execute(p_stmt)
        priorities = p_res.scalars().all()

        p_list_str = "\n".join([f"{p.priority_id}️⃣ *{p.priority_name}*" for p in priorities])
        msg = (
            f"🚨 *Select Ticket Priority*\n\n"
            f"How urgent is this issue?\n\n"
            f"{p_list_str}"
        )

        p_map = {str(p.priority_id): p.priority_id for p in priorities}
        data["priorities_map"] = p_map

        await set_user_state(session, phone, "awaiting_priority", data)
        await meta_api.send_text_message(phone, msg)
        return

    # STEP 5: Awaiting Priority -> Generate Ticket with Category-Based Admin Routing
    elif step == "awaiting_priority":
        p_map = data.get("priorities_map", {})
        selected_priority_id = p_map.get(choice_num) or p_map.get(text_clean)

        if not selected_priority_id:
            await meta_api.send_text_message(
                phone,
                "⚠️ *Invalid Option*: Please reply with a priority number (1 = Low, 2 = Medium, 3 = High, 4 = Urgent)."
            )
            return

        priority_id = int(selected_priority_id)
        category_id = data.get("category_id")
        subcategory_id = data.get("subcategory_id")
        issue_type_id = data.get("issue_type_id")
        description = data.get("description", "No description provided")
        ticket_image_id = data.get("image_id")

        ticket_number = await generate_ticket_number(session)

        new_ticket = Ticket(
            ticket_number=ticket_number,
            employee_id=employee.employee_id,
            category_id=category_id,
            subcategory_id=subcategory_id,
            issue_type_id=issue_type_id,
            description=description,
            image_id=ticket_image_id,
            priority_id=priority_id,
            status_id=1 # Open
        )
        session.add(new_ticket)
        await session.flush()

        # Subcategory-Level 1:1 Admin Routing Matrix
        assigned_admin = None
        if subcategory_id:
            sub_map_stmt = (
                select(AdminCategoryMapping)
                .options(selectinload(AdminCategoryMapping.admin))
                .where(AdminCategoryMapping.subcategory_id == subcategory_id)
            )
            sub_mappings = (await session.execute(sub_map_stmt)).scalars().all()
            active_sub_admins = [m.admin for m in sub_mappings if m.admin and m.admin.active]
            if active_sub_admins:
                assigned_admin = active_sub_admins[0]

        # Category-Level Fallback
        if not assigned_admin and category_id:
            cat_map_stmt = (
                select(AdminCategoryMapping)
                .options(selectinload(AdminCategoryMapping.admin))
                .where(AdminCategoryMapping.category_id == category_id)
            )
            cat_mappings = (await session.execute(cat_map_stmt)).scalars().all()
            active_cat_admins = [m.admin for m in cat_mappings if m.admin and m.admin.active]
            if active_cat_admins:
                assigned_admin = active_cat_admins[0]

        # Master Admin Fallback
        if not assigned_admin:
            master_stmt = select(SupportAdmin).where(SupportAdmin.is_master_admin == True, SupportAdmin.active == True)
            assigned_admin = (await session.execute(master_stmt)).scalars().first()

        # Fallback to any active admin
        if not assigned_admin:
            any_admin_stmt = select(SupportAdmin).where(SupportAdmin.active == True)
            assigned_admin = (await session.execute(any_admin_stmt)).scalars().first()

        if assigned_admin:
            assignment = TicketAssignment(
                ticket_id=new_ticket.ticket_id,
                admin_id=assigned_admin.admin_id
            )
            session.add(assignment)

        await session.commit()

        # Load entity details for context
        cat_obj = await session.get(Category, category_id) if category_id else None
        sub_obj = await session.get(Subcategory, subcategory_id) if subcategory_id else None
        issue_obj = await session.get(IssueType, issue_type_id) if issue_type_id else None
        p_obj = await session.get(Priority, priority_id) if priority_id else None

        # Load employee location and department
        emp_stmt = (
            select(Employee)
            .options(selectinload(Employee.department), selectinload(Employee.location))
            .where(Employee.employee_id == employee.employee_id)
        )
        emp_detailed = (await session.execute(emp_stmt)).scalars().first()
        dept_name = emp_detailed.department.department_name if emp_detailed and emp_detailed.department else "General"
        loc_name = emp_detailed.location.location_name if emp_detailed and emp_detailed.location else "Headquarters"

        await clear_user_state(session, phone)

        # Send Confirmation to Employee
        img_notice = "\n🖼️ *Photo:* Attachment Included" if ticket_image_id else ""
        emp_confirmation = (
            f"✅ *Ticket Created Successfully!*\n\n"
            f"🎫 *Ticket ID:* `{ticket_number}`\n"
            f"📌 *Category:* {cat_obj.category_name if cat_obj else 'N/A'}\n"
            f"📁 *Subcategory:* {sub_obj.subcategory_name if sub_obj else 'N/A'}\n"
            f"⚙️ *Issue:* {issue_obj.issue_name if issue_obj else 'Custom'}\n"
            f"🚨 *Priority:* {p_obj.priority_name if p_obj else 'Medium'}\n"
            f"📝 *Description:* {description}{img_notice}\n\n"
            f"Our IT Support team has been notified on WhatsApp and will assist you shortly!"
        )
        await meta_api.send_text_message(phone, emp_confirmation)

        # Broadcast Ticket Alert with Interactive Quick Reply Button to ALL Active Support Admins
        img_admin_line = f"\n🖼️ *Photo Attachment ID:* `{ticket_image_id}`" if ticket_image_id else ""
        header = "🚨 NEW IT SUPPORT REQUEST 🚨"
        body = (
            f"🎫 *Ticket ID:* `{ticket_number}`\n"
            f"👤 *Employee:* {employee.full_name}\n"
            f"📞 *Phone:* +{employee.phone}\n"
            f"🏢 *Location:* {loc_name}\n"
            f"🏬 *Department:* {dept_name}\n\n"
            f"📌 *Category:* {cat_obj.category_name if cat_obj else 'N/A'} ➡️ {sub_obj.subcategory_name if sub_obj else 'N/A'}\n"
            f"⚙️ *Issue:* {issue_obj.issue_name if issue_obj else 'Custom'}\n"
            f"🚨 *Priority:* {p_obj.priority_name if p_obj else 'Medium'}\n"
            f"📝 *Description:* {description}{img_admin_line}"
        )
        footer = "Tap button below to claim this ticket"
        buttons = [
            {
                "id": f"claim_{ticket_number}",
                "title": "⚡ Accept Ticket"
            }
        ]

        all_admins_stmt = select(SupportAdmin).where(SupportAdmin.active == True)
        all_admins = (await session.execute(all_admins_stmt)).scalars().all()
        for adm in all_admins:
            await meta_api.send_button_message(
                to_phone=adm.phone,
                body_text=body,
                buttons=buttons,
                header_text=header,
                footer_text=footer
            )

        return
