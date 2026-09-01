import datetime
import re
import random
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.meta_api import meta_api
from app.state_manager import set_user_state, clear_user_state, get_user_state
from app.workshop.models import (
    WorkshopTruck, WorkshopStaff, WorkshopCategory, WorkshopSubcategory,
    WorkshopTicket, WorkshopPartsRequest
)

GLOBAL_RESET_KEYWORDS = {"hi", "hello", "menu", "reset", "cancel", "start"}

def extract_numeric_choice(text: str) -> str:
    match = re.search(r"\d+", text.strip()) if text else None
    return match.group(0) if match else text.strip().lower()

async def generate_workshop_ticket_number(session: AsyncSession) -> str:
    today_str = datetime.datetime.utcnow().strftime("%Y%m%d")
    stmt = select(func.count(WorkshopTicket.ticket_id))
    total_count = (await session.execute(stmt)).scalar() or 0
    ticket_num = f"TKT-FLT-{today_str}-{str(total_count + 1).zfill(5)}"
    
    check_stmt = select(WorkshopTicket).where(WorkshopTicket.ticket_number == ticket_num)
    existing = (await session.execute(check_stmt)).scalars().first()
    if existing:
        random_suffix = str(random.randint(100, 999))
        ticket_num = f"TKT-FLT-{today_str}-{str(total_count + 1).zfill(5)}{random_suffix}"
    return ticket_num

async def start_workshop_flow(session: AsyncSession, staff: WorkshopStaff):
    phone = staff.phone
    role = staff.role.upper()
    
    if role in {"DRIVER", "CLERK"}:
        await set_user_state(session, phone, "ws_truck_search", {})
        role_label = "Driver" if role == "DRIVER" else "Clerk"
        msg = (
            f"👋 *Welcome {staff.full_name}* ({role_label})\\n"
            f"🚚 *Tagoneswa Logistics & Fleet Portal*\\n\\n"
            f"Please enter the *Truck Number* (e.g. for plate `ABZ 1045`, type `1045`):"
        )
        await meta_api.send_text_message(phone, msg)
    
    elif role in {"MECHANIC", "LEAD"}:
        stmt = select(WorkshopTicket).where(
            WorkshopTicket.status.in_(["WITH_MECHANIC", "AWAITING_PARTS", "INFO_REQUESTED", "REPAIR_IN_PROGRESS", "REWORK_REQUIRED"])
        ).order_by(WorkshopTicket.created_at.desc()).limit(5)
        active_tickets = (await session.execute(stmt)).scalars().all()
        
        if not active_tickets:
            msg = (
                f"👋 *Hello {staff.full_name}* (Workshop Team)\n\n"
                f"✅ No pending workshop tickets currently assigned to you."
            )
            await meta_api.send_text_message(phone, msg)
        else:
            lines = [f"🔧 *Active Workshop Tickets ({staff.full_name}):*\n"]
            for t in active_tickets:
                lines.append(f"• 🎫 *{t.ticket_number}* | Status: `{t.status}`\n  📌 Fault: {t.category_name} - {t.subcategory_name}")
            lines.append("\n💡 Reply with ticket commands or wait for new job assignments.")
            await meta_api.send_text_message(phone, "\n".join(lines))
            
    elif role == "SUPERVISOR":
        msg = (
            f"👋 *Welcome {staff.full_name}* (Logistics Supervisor)\n\n"
            f"You will automatically receive alerts when:\n"
            f"• 1. New faults are reported for Gatekeeper Review\n"
            f"• 2. Repaired vehicles are ready for Road-Test QC\n\n"
            f"💡 Type `status` to view active workshop jobs."
        )
        await meta_api.send_text_message(phone, msg)
        
    elif role == "PURCHASING":
        stmt = select(WorkshopPartsRequest).where(WorkshopPartsRequest.status.in_(["PENDING", "INFO_REQUESTED"]))
        pending = (await session.execute(stmt)).scalars().all()
        msg = (
            f"👋 *Welcome Purchasing & Procurement Team*\n\n"
            f"📦 Pending Parts Requisitions: *{len(pending)}*\n"
            f"You will receive instant alerts with photos when workshop mechanics request spares."
        )
        await meta_api.send_text_message(phone, msg)

async def handle_truck_search(session: AsyncSession, staff: WorkshopStaff, text: str, data: dict):
    phone = staff.phone
    search_query = text.strip()
    
    stmt = select(WorkshopTruck).where(
        (WorkshopTruck.truck_number.ilike(f"%{search_query}%")) |
        (WorkshopTruck.plate_number.ilike(f"%{search_query}%"))
    ).where(WorkshopTruck.active == True)
    
    res = await session.execute(stmt)
    matching_trucks = res.scalars().all()
    
    if not matching_trucks:
        await meta_api.send_text_message(
            phone,
            f"⚠️ No truck found matching '*{search_query}*'.\n\nPlease check the truck number painted on the door or enter registration plate:"
        )
        return
        
    if len(matching_trucks) == 1:
        truck = matching_trucks[0]
        data["truck_id"] = truck.truck_id
        data["truck_info"] = f"{truck.model_make} ({truck.plate_number})"
        data["truck_number"] = truck.truck_number
        
        await set_user_state(session, phone, "ws_confirm_truck", data)
        body = (
            f"🚚 Truck Found:\n\n"
            f"• *Number:* #{truck.truck_number}\n"
            f"• *Model:* {truck.model_make}\n"
            f"• *Plate:* `{truck.plate_number}`\n"
            f"• *Depot:* {truck.home_depot}\n\n"
            f"Please confirm this vehicle:"
        )
        buttons = [
            {"id": "btn_ws_confirm_truck", "title": "✅ Confirm Truck"},
            {"id": "btn_ws_reenter_truck", "title": "🔄 Re-enter Number"}
        ]
        await meta_api.send_button_message(phone, body, buttons, header_text="VEHICLE CONFIRMATION")
    else:
        lines = [f"🔍 Multiple vehicles found matching '*{search_query}*':\n"]
        for idx, t in enumerate(matching_trucks[:5], start=1):
            lines.append(f"*{idx}.* Truck #{t.truck_number} — {t.model_make} (`{t.plate_number}`)")
        lines.append("\nPlease reply with the number (e.g. `1`, `2`) to select:")
        
        data["multi_truck_ids"] = [t.truck_id for t in matching_trucks[:5]]
        await set_user_state(session, phone, "ws_select_multi_truck", data)
        await meta_api.send_text_message(phone, "\n".join(lines))

async def handle_truck_confirmation(session: AsyncSession, staff: WorkshopStaff, text: str, data: dict):
    phone = staff.phone
    if "reenter" in text.lower() or text == "2":
        await set_user_state(session, phone, "ws_truck_search", {})
        await meta_api.send_text_message(phone, "Please enter the Truck Number (e.g. `9999` or `1045`):")
        return
        
    stmt = select(WorkshopCategory).where(WorkshopCategory.active == True).order_by(WorkshopCategory.category_id)
    categories = (await session.execute(stmt)).scalars().all()
    
    cat_list = []
    cat_map = {}
    for idx, c in enumerate(categories, start=1):
        cat_list.append(f"*{idx}.* {c.category_name}")
        cat_map[str(idx)] = c.category_id
        
    data["category_map"] = cat_map
    await set_user_state(session, phone, "ws_select_category", data)
    
    msg = (
        f"📋 *Select Fault Category for Truck #{data.get('truck_number')}*:\n\n"
        f"{'\n'.join(cat_list)}\n\n"
        f"Reply with category number (e.g. `1`, `2`):"
    )
    await meta_api.send_text_message(phone, msg)

async def handle_category_selection(session: AsyncSession, staff: WorkshopStaff, text: str, data: dict):
    phone = staff.phone
    choice = extract_numeric_choice(text)
    cat_map = data.get("category_map", {})
    
    if choice not in cat_map:
        await meta_api.send_text_message(phone, "⚠️ Invalid selection. Please reply with a valid number from the list.")
        return
        
    category_id = cat_map[choice]
    cat_obj = await session.get(WorkshopCategory, category_id)
    data["category_id"] = category_id
    data["category_name"] = cat_obj.category_name
    
    stmt = select(WorkshopSubcategory).where(
        WorkshopSubcategory.category_id == category_id,
        WorkshopSubcategory.active == True
    ).order_by(WorkshopSubcategory.subcategory_id)
    subcats = (await session.execute(stmt)).scalars().all()
    
    sub_list = []
    sub_map = {}
    for idx, sc in enumerate(subcats, start=1):
        sub_list.append(f"*{idx}.* {sc.subcategory_name}")
        sub_map[str(idx)] = sc.subcategory_name
        
    data["sub_map"] = sub_map
    await set_user_state(session, phone, "ws_select_subcategory", data)
    
    msg = (
        f"📌 *{cat_obj.category_name}* ➔ Select Specific Fault:\n\n"
        f"{'\n'.join(sub_list)}\n\n"
        f"Reply with issue number (e.g. `1`, `2`):"
    )
    await meta_api.send_text_message(phone, msg)

async def handle_subcategory_selection(session: AsyncSession, staff: WorkshopStaff, text: str, data: dict):
    phone = staff.phone
    choice = extract_numeric_choice(text)
    sub_map = data.get("sub_map", {})
    
    if choice not in sub_map:
        await meta_api.send_text_message(phone, "⚠️ Invalid selection. Please reply with a valid number from the list.")
        return
        
    data["subcategory_name"] = sub_map[choice]
    await set_user_state(session, phone, "ws_enter_description", data)
    
    msg = (
        f"📝 *Please describe the problem in detail:*\n\n"
        f"📌 *Issue:* {data.get('category_name')} ➔ {data.get('subcategory_name')}\n"
        f"Type your fault notes below:"
    )
    await meta_api.send_text_message(phone, msg)

async def handle_description_entry(session: AsyncSession, staff: WorkshopStaff, text: str, image_id: str, data: dict):
    phone = staff.phone
    data["description"] = text.strip() if text else "Fault reported via WhatsApp"
    
    if image_id:
        data["image_id"] = image_id
        return await finalize_ticket_logging(session, staff, data)
        
    # Prompt for optional photo
    await set_user_state(session, phone, "ws_attach_clerk_photo", data)
    photo_prompt = (
        f"📸 *Attach Photo (Optional)*\n\n"
        f"Please send a photo of the defect/damage right now, or tap below to skip:"
    )
    buttons = [{"id": "btn_ws_skip_clerk_photo", "title": "Skip Photo"}]
    await meta_api.send_button_message(phone, photo_prompt, buttons, header_text="PHOTO ATTACHMENT")

async def handle_photo_step(session: AsyncSession, staff: WorkshopStaff, text: str, image_id: str, data: dict):
    if image_id:
        data["image_id"] = image_id
    elif text and text.startswith("btn_ws_skip_clerk_photo"):
        data["image_id"] = None
    elif text and text.lower() in {"skip", "skip photo"}:
        data["image_id"] = None
        
    await finalize_ticket_logging(session, staff, data)

async def finalize_ticket_logging(session: AsyncSession, staff: WorkshopStaff, data: dict):
    phone = staff.phone
    description = data.get("description", "Fault reported via WhatsApp")
    image_id = data.get("image_id")
    
    ticket_num = await generate_workshop_ticket_number(session)
    
    ticket = WorkshopTicket(
        ticket_number=ticket_num,
        truck_id=data.get("truck_id"),
        logged_by_staff_id=staff.staff_id,
        category_name=data.get("category_name"),
        subcategory_name=data.get("subcategory_name"),
        description=description,
        image_id=image_id,
        status="UNDER_REVIEW"
    )
    session.add(ticket)
    await session.commit()
    await session.refresh(ticket)
    
    await clear_user_state(session, phone)
    
    # 1. Confirm to Clerk
    clerk_msg = (
        f"✅ *Workshop Fault Ticket Created!*\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"🎫 *Ticket Number:* `{ticket.ticket_number}`\n"
        f"🚚 *Vehicle:* {data.get('truck_info')}\n"
        f"📌 *Category:* {ticket.category_name} ➔ {ticket.subcategory_name}\n"
        f"📝 *Description:* {ticket.description}\n"
        f"📸 *Photo:* {'Attached' if image_id else 'None'}\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"⏳ *Status: UNDER REVIEW* (Forwarded to Supervisor for Gatekeeper Review)."
    )
    await meta_api.send_text_message(phone, clerk_msg)
    
    # 2. Alert Supervisor
    stmt = select(WorkshopStaff).where(WorkshopStaff.role == "SUPERVISOR", WorkshopStaff.active == True)
    supervisors = (await session.execute(stmt)).scalars().all()
    
    for sup in supervisors:
        sup_msg = (
            f"🔍 *NEW WORKSHOP FAULT UNDER REVIEW*\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n"
            f"🎫 *Ticket ID:* `{ticket.ticket_number}`\n"
            f"🚚 *Vehicle:* {data.get('truck_info')}\n"
            f"👤 *Logged By:* {staff.full_name}\n"
            f"📌 *Fault:* {ticket.category_name} ➔ {ticket.subcategory_name}\n"
            f"📝 *Notes:* {ticket.description}\n"
            f"📸 *Photo:* {'Attached' if image_id else 'None'}\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n"
            f"Please select routing action:"
        )
        buttons = [
            {"id": f"btn_ws_route_intern_{ticket.ticket_id}", "title": "🛠️ Handle Internally"},
            {"id": f"btn_ws_route_work_{ticket.ticket_id}", "title": "🏭 Send to Workshop"}
        ]
        await meta_api.send_button_message(sup.phone, sup_msg, buttons, header_text="SUPERVISOR REVIEW")
