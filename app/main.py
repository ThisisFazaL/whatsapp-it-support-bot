import logging
import asyncio
import datetime
import os
from typing import Set
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, Response, Query, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.config import settings
from app.database import get_db, init_db_models, Ticket, async_session_factory
from app.state_manager import is_employee_registered, is_admin, get_user_state
from app.handlers.admin_handler import handle_admin_command
from app.handlers.resolution_handler import handle_resolution_confirmation
from app.handlers.flow_handler import handle_flow
from app.handlers.my_tickets_handler import handle_my_tickets
from app.reports import send_daily_report_to_master
from app.meta_api import meta_api
from app.dashboard import router as dashboard_router

logger = logging.getLogger("main")
logging.basicConfig(level=logging.INFO)

PROCESSED_WAMIDS: Set[str] = set()

async def scheduled_daily_report_loop():
    """Background task loop to deliver Daily Master Executive Report at 8:00 PM IST (14:30 UTC) daily."""
    last_sent_date = None
    while True:
        try:
            now_utc = datetime.datetime.utcnow()
            today_date_str = now_utc.strftime("%Y-%m-%d")
            
            # Check if current time is past 14:30 UTC (8:00 PM IST) and hasn't sent today
            target_utc = now_utc.replace(hour=14, minute=30, second=0, microsecond=0)
            
            if now_utc >= target_utc and last_sent_date != today_date_str:
                logger.info("8:00 PM IST trigger window reached. Executing Daily Master Report delivery...")
                async with async_session_factory() as session:
                    await send_daily_report_to_master(session)
                last_sent_date = today_date_str
                logger.info("Daily Master Report delivered successfully!")

            # Calculate next target (tomorrow 14:30 UTC if sent, or check again in 60s)
            now_utc = datetime.datetime.utcnow()
            next_target = now_utc.replace(hour=14, minute=30, second=0, microsecond=0)
            if now_utc >= next_target:
                next_target += datetime.timedelta(days=1)

            sleep_seconds = (next_target - now_utc).total_seconds()
            logger.info(f"Next Daily Master Report scheduled in {sleep_seconds/3600:.2f} hours (at 8:00 PM IST / {next_target.isoformat()}).")
            await asyncio.sleep(min(sleep_seconds, 3600))

        except asyncio.CancelledError:
            logger.info("Scheduled report loop cancelled.")
            break
        except Exception as e:
            logger.error(f"Error in scheduled daily report loop: {e}", exc_info=True)
            await asyncio.sleep(300)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifecycle startup and shutdown hooks."""
    logger.info("Initializing database models and seed data...")
    await init_db_models()
    logger.info("Database initialized successfully.")

    # Start 8 PM IST EOD report background task loop
    report_task = asyncio.create_task(scheduled_daily_report_loop())
    yield
    report_task.cancel()
    logger.info("Shutting down application...")

app = FastAPI(
    title="WhatsApp IT Support Chatbot Service",
    description="Automated IT support ticketing chatbot via Meta WhatsApp Cloud API",
    version="2.0.0",
    lifespan=lifespan
)

from fastapi.responses import FileResponse, RedirectResponse

app.include_router(dashboard_router)

@app.get("/")
async def root():
    return RedirectResponse(url="/dashboard")

@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "whatsapp_it_support_bot"}

@app.get("/trigger-ticket-cleanup")
async def trigger_ticket_cleanup_endpoint():
    """Removes test maintenance tickets 1-4, renumbers ticket 5 as TKT-MNT-20260827-00001 and sends alert to admins."""
    from process_ticket_cleanup_and_notify import cleanup_and_renumber
    await cleanup_and_renumber()
    return {"status": "success", "message": "Test tickets deleted, ticket 5 renumbered to TKT-MNT-20260827-00001, and alerts sent to admins."}

@app.get("/trigger-create-zayn-ticket")
async def trigger_create_zayn_ticket_endpoint():
    """Creates Zayn's Building Projects ticket TKT-MNT-20260831-00001 and notifies Projects Admins."""
    from create_zayn_ticket_1_and_notify import create_zayn_ticket_and_notify
    await create_zayn_ticket_and_notify()
    return {"status": "success", "message": "Ticket TKT-MNT-20260831-00001 created and alerts sent to Projects Admins (Stanclea, Omar, Master Admin)."}

@app.get("/debug-check-stanclea-admin")
async def debug_check_stanclea_admin_endpoint(db: AsyncSession = Depends(get_db)):
    from app.database import SupportAdmin, Employee
    from sqlalchemy import select
    from app.state_manager import is_admin, is_employee_registered
    
    admins_res = await db.execute(select(SupportAdmin))
    admins = admins_res.scalars().all()
    admin_list = [{"id": a.admin_id, "name": a.full_name, "phone": a.phone, "is_maint": a.is_maintenance_admin, "active": a.active} for a in admins]
    
    stanclea_admin = await is_admin(db, "263780099291")
    stanclea_emp = await is_employee_registered(db, "263780099291")
    
    return {
        "all_admins": admin_list,
        "stanclea_is_admin": bool(stanclea_admin),
        "stanclea_admin_name": stanclea_admin.full_name if stanclea_admin else None,
        "stanclea_is_emp": bool(stanclea_emp)
    }

@app.get("/inspect-zayn-tickets")
async def inspect_zayn_tickets_endpoint(db: AsyncSession = Depends(get_db)):
    """Inspects all Building Projects and IT Support tickets created by Zayn or anyone."""
    try:
        from app.database import MaintenanceTicket, Ticket, Employee
        from sqlalchemy import select

        # Map employees
        emp_res = await db.execute(select(Employee))
        emps = emp_res.scalars().all()
        emp_map = {e.employee_id: (e.full_name, e.phone) for e in emps}

        # 1. Fetch Maintenance / Building Projects tickets
        m_res = await db.execute(select(MaintenanceTicket).order_by(MaintenanceTicket.ticket_id.desc()))
        m_tickets = m_res.scalars().all()

        maint_list = []
        all_maint_list = []
        for t in m_tickets:
            emp_info = emp_map.get(t.employee_id, ("Unknown", ""))
            emp_name, emp_phone = emp_info[0] or "Unknown", emp_info[1] or ""
            item = {
                "ticket_id": t.ticket_id,
                "ticket_number": str(t.ticket_number),
                "reporter": f"{emp_name} (+{emp_phone})",
                "created_at": t.created_at.isoformat() if t.created_at else None,
                "room_area": str(t.room_area or "N/A"),
                "description": str(t.description or ""),
                "status_id": t.status_id
            }
            all_maint_list.append(item)
            if "zayn" in emp_name.lower() or "713866223" in emp_phone:
                maint_list.append(item)

        # 2. Fetch IT Support tickets
        it_res = await db.execute(select(Ticket).order_by(Ticket.ticket_id.desc()))
        it_tickets = it_res.scalars().all()

        it_list = []
        all_it_list = []
        for t in it_tickets:
            emp_info = emp_map.get(t.employee_id, ("Unknown", ""))
            emp_name, emp_phone = emp_info[0] or "Unknown", emp_info[1] or ""
            item = {
                "ticket_id": t.ticket_id,
                "ticket_number": str(t.ticket_number),
                "reporter": f"{emp_name} (+{emp_phone})",
                "created_at": t.created_at.isoformat() if t.created_at else None,
                "description": str(t.description or ""),
                "status_id": t.status_id
            }
            all_it_list.append(item)
            if "zayn" in emp_name.lower() or "713866223" in emp_phone:
                it_list.append(item)

        return {
            "status": "success",
            "zayn_projects_tickets": maint_list,
            "zayn_it_tickets": it_list,
            "all_projects_tickets": all_maint_list,
            "all_it_tickets": all_it_list
        }
    except Exception as e:
        return {"status": "error", "error_message": str(e)}

@app.get("/daily-report.pdf")
async def download_daily_report_pdf(db: AsyncSession = Depends(get_db)):
    """Serves the latest Daily Master Executive Report PDF directly generated from live database."""
    pdf_path = "Daily_IT_Support_Master_Report_Sample.pdf"
    from app.reports import generate_daily_master_report_data
    from generate_daily_report_pdf import create_daily_report_pdf
    text_summary, today_tickets, asg_map = await generate_daily_master_report_data(db)
    create_daily_report_pdf(pdf_path, today_tickets=today_tickets, asg_map=asg_map)
    return FileResponse(
        pdf_path,
        media_type="application/pdf",
        filename=f"Daily_IT_Support_Master_Report_{datetime.datetime.now().strftime('%d%b%Y')}.pdf"
    )

@app.get("/trigger-daily-report")
async def trigger_daily_report(db: AsyncSession = Depends(get_db)):
    """API endpoint to manually trigger 8 PM IST Daily Master Report on demand."""
    await send_daily_report_to_master(db)
    return {"status": "report_delivered", "message": "Daily Master Report sent to Master Admin!"}

@app.get("/webhook/meta-whatsapp")
async def verify_webhook(
    mode: str = Query(None, alias="hub.mode"),
    token: str = Query(None, alias="hub.verify_token"),
    challenge: str = Query(None, alias="hub.challenge")
):
    """Meta WhatsApp Cloud API Webhook Verification."""
    logger.info(f"Received Webhook Verification request: mode={mode}, token={token}, challenge={challenge}")
    if mode == "subscribe" and token == settings.verify_token:
        logger.info("Webhook verification SUCCESS.")
        return Response(content=challenge, media_type="text/plain", status_code=200)
    
    logger.warning("Webhook verification FAILED.")
    return Response(content="Verification token mismatch", status_code=403)

async def process_webhook_payload(body: dict):
    """Processes incoming Meta WhatsApp Webhook payload safely in background task."""
    async with async_session_factory() as db:
        try:
            entry = body.get("entry", [])
            if not entry:
                return
            changes = entry[0].get("changes", [])
            if not changes:
                return
            value = changes[0].get("value", {})
            messages = value.get("messages", [])
            if not messages:
                return

            msg_obj = messages[0]
            wamid = msg_obj.get("id")
            sender_phone = msg_obj.get("from")
            msg_type = msg_obj.get("type")

            # Deduplication check
            if wamid and wamid in PROCESSED_WAMIDS:
                logger.info(f"Duplicate wamid '{wamid}' skipped.")
                return

            if wamid:
                PROCESSED_WAMIDS.add(wamid)
                if len(PROCESSED_WAMIDS) > 5000:
                    PROCESSED_WAMIDS.clear()

            image_id = None
            message_text = ""

            if msg_type == "text":
                message_text = msg_obj.get("text", {}).get("body", "").strip()
            elif msg_type == "image":
                image_obj = msg_obj.get("image", {})
                image_id = image_obj.get("id")
                message_text = image_obj.get("caption", "Photo attachment").strip()
                logger.info(f"Received Image attachment ID '{image_id}' from {sender_phone}.")
            elif msg_type == "interactive":
                interactive_obj = msg_obj.get("interactive", {})
                btn_reply = interactive_obj.get("button_reply", {})
                btn_id = btn_reply.get("id", "")
                btn_title = btn_reply.get("title", "")
                # Keep btn_id intact if present (e.g. "cmd_my_assigned_tickets" or "resolve_TKT-...")
                message_text = btn_id if btn_id else btn_title
                logger.info(f"Received Interactive Button click from {sender_phone}: id='{btn_id}', title='{btn_title}' -> text='{message_text}'")
            elif msg_type == "button":
                btn_obj = msg_obj.get("button", {})
                payload = btn_obj.get("payload", "")
                text_val = btn_obj.get("text", "")
                message_text = payload if payload else text_val
                logger.info(f"Received Template Quick Reply button click from {sender_phone}: payload='{payload}', text='{text_val}' -> text='{message_text}'")
            else:
                logger.info(f"Unsupported message type '{msg_type}' received from {sender_phone}.")
                await meta_api.send_text_message(sender_phone, "ℹ️ Please send text messages, numbers, photo attachments, or tap interactive buttons.")
                return

            # Step 0: Workshop Subsystem Routing (Isolated Subsystem)
            from app.workshop.router import get_workshop_staff, handle_workshop_message
            workshop_user = await get_workshop_staff(db, sender_phone)
            if workshop_user:
                logger.info(f"Routing to Workshop Subsystem for staff '{workshop_user.full_name}' ({workshop_user.role}).")
                await handle_workshop_message(db, workshop_user, message_text, image_id)
                return

            # Check if user is an active SupportAdmin or ExecutiveObserver
            admin = await is_admin(db, sender_phone)
            from app.config import settings
            is_observer = sender_phone in settings.executive_observer_phones

            # Step 1: Employee Registration Check (Support Admins & Observers bypass restriction)
            employee = await is_employee_registered(db, sender_phone)
            if not employee and not admin and not is_observer:
                logger.warning(f"Unregistered phone number attempted access: {sender_phone}")
                warning_msg = (
                    f"🚫 *Access Restricted*\n\n"
                    f"Your phone number (`+{sender_phone}`) is not registered as an active employee in our IT Support database.\n\n"
                    f"Please contact your IT System Administrator to register your account."
                )
                await meta_api.send_text_message(sender_phone, warning_msg)
                return

            # Step 2: Admin Command Check (Process Admin Commands FIRST for active Support Admins!)
            if admin:
                isAdminCmd = await handle_admin_command(db, sender_phone, message_text)
                if isAdminCmd:
                    return

            # Step 3: "My Tickets" Command Check (if employee record exists)
            if employee:
                isMyTickets = await handle_my_tickets(db, employee, message_text)
                if isMyTickets:
                    return

            # Step 4: Check Current Conversation State
            state = await get_user_state(db, sender_phone)

            # Step 5: Check Resolution Confirmation Loop
            if state and state.current_step == "awaiting_resolution_confirmation":
                await handle_resolution_confirmation(
                    session=db,
                    sender_phone=sender_phone,
                    message_text=message_text,
                    current_data=state.current_data or {}
                )
                return

            # Step 6: Multi-Step Ticket Flow Execution (with optional image)
            await handle_flow(
                session=db,
                employee=employee,
                message_text=message_text,
                state=state,
                image_id=image_id,
                sender_phone=sender_phone
            )

        except Exception as e:
            logger.error(f"Error processing webhook payload: {e}", exc_info=True)

@app.post("/webhook/meta-whatsapp")
async def handle_incoming_webhook(request: Request):
    """Meta WhatsApp Cloud API Webhook Handler - Responds HTTP 200 immediately & processes in background."""
    try:
        body = await request.json()
        asyncio.create_task(process_webhook_payload(body))
        return {"status": "accepted"}
    except Exception as e:
        logger.error(f"Error receiving webhook payload: {e}")
        return {"status": "error"}

@app.get("/tickets")
async def list_recent_tickets(db: AsyncSession = Depends(get_db)):
    """API Endpoint to list recent tickets for monitoring."""
    stmt = (
        select(Ticket)
        .options(
            selectinload(Ticket.employee),
            selectinload(Ticket.category),
            selectinload(Ticket.subcategory),
            selectinload(Ticket.issue_type),
            selectinload(Ticket.priority),
            selectinload(Ticket.status)
        )
        .order_by(Ticket.ticket_id.desc())
        .limit(20)
    )
    res = await db.execute(stmt)
    tickets = res.scalars().all()

    output = []
    for t in tickets:
        output.append({
            "ticket_id": t.ticket_id,
            "ticket_number": t.ticket_number,
            "employee": t.employee.full_name if t.employee else "Unknown",
            "employee_phone": t.employee.phone if t.employee else "",
            "category": t.category.category_name if t.category else "",
            "subcategory": t.subcategory.subcategory_name if t.subcategory else "",
            "issue": t.issue_type.issue_name if t.issue_type else "Custom",
            "priority": t.priority.priority_name if t.priority else "",
            "status": t.status.status_name if t.status else "",
            "description": t.description,
            "image_id": t.image_id,
            "created_at": t.created_at.isoformat() if t.created_at else None
        })
    return {"tickets": output, "count": len(output)}

@app.get("/api/admin/recover-stuck-tickets")
async def recover_stuck_tickets(db: AsyncSession = Depends(get_db)):
    """Recovers any pending ticket states stuck at photo skip / awaiting_image step and creates them."""
    import traceback
    try:
        from app.database import ConversationState
        from app.state_manager import is_employee_registered, clear_user_state
        from app.handlers.flow_handler import finalize_ticket_creation
        
        stmt = select(ConversationState).where(
            ConversationState.flow_name == "raise_ticket",
            ConversationState.current_step.in_(["awaiting_image", "select_priority", "awaiting_description"])
        )
        res = await db.execute(stmt)
        stuck_states = res.scalars().all()
        
        recovered = []
        for s in stuck_states:
            try:
                data = s.current_data or {}
                if data.get("description") or data.get("category_id") or data.get("subcategory_id"):
                    emp = await is_employee_registered(db, s.phone)
                    await finalize_ticket_creation(
                        session=db,
                        phone=s.phone,
                        employee=emp,
                        data=data
                    )
                    recovered.append({
                        "phone": s.phone,
                        "step": s.current_step,
                        "description": data.get("description"),
                        "employee": emp.full_name if emp else "Staff User",
                        "status": "CREATED_AND_SENT"
                    })
                else:
                    await clear_user_state(db, s.phone)
            except Exception as single_err:
                logger.error(f"Error recovering state for {s.phone}: {single_err}", exc_info=True)
                recovered.append({
                    "phone": s.phone,
                    "error": str(single_err)
                })

        return {"recovered_count": len(recovered), "tickets": recovered}
    except Exception as e:
        logger.error(f"Error in recover_stuck_tickets: {e}", exc_info=True)
        return {"error": str(e), "traceback": traceback.format_exc()}

@app.get("/api/admin/reinitiate-claim-ticket-2")
async def reinitiate_claim_ticket_2(db: AsyncSession = Depends(get_db)):
    """Ensures TKT-MNT-20260903-00002 is assigned to Stanclea and set to In Progress in the DB."""
    try:
        from app.database import MaintenanceTicket, MaintenanceTicketAssignment, SupportAdmin
        stmt = select(MaintenanceTicket).where(MaintenanceTicket.ticket_number == "TKT-MNT-20260903-00002")
        t = (await db.execute(stmt)).scalars().first()
        if not t:
            return {"error": "Ticket TKT-MNT-20260903-00002 not found"}

        stanclea_phone = "263780099291"
        adm_stmt = select(SupportAdmin).where(SupportAdmin.phone == stanclea_phone)
        admin = (await db.execute(adm_stmt)).scalars().first()
        if not admin:
            return {"error": "Stanclea admin record not found"}

        asg_chk = select(MaintenanceTicketAssignment).where(MaintenanceTicketAssignment.ticket_id == t.ticket_id)
        current_asg = (await db.execute(asg_chk)).scalars().first()

        if not current_asg:
            db.add(MaintenanceTicketAssignment(ticket_id=t.ticket_id, admin_id=admin.admin_id))
        else:
            current_asg.admin_id = admin.admin_id

        t.status_id = 2  # In Progress
        await db.commit()
        return {"status": "SUCCESS", "ticket": t.ticket_number, "status_id": t.status_id, "assigned_to": admin.full_name}
    except Exception as e:
        return {"error": str(e)}

@app.get("/send-zayn-project-ticket-2-to-stanclea")
@app.get("/trigger-send-zayn-ticket-to-stanclea")
async def trigger_send_zayn_ticket_to_stanclea(db: AsyncSession = Depends(get_db)):
    """Sends Zayn's Projects Ticket 2 (TKT-MNT-20260903-00002) alert to Stanclea directly on WhatsApp."""
    try:
        from app.database import MaintenanceTicket
        stmt = (
            select(MaintenanceTicket)
            .options(
                selectinload(MaintenanceTicket.category),
                selectinload(MaintenanceTicket.subcategory),
                selectinload(MaintenanceTicket.issue_type),
                selectinload(MaintenanceTicket.priority),
                selectinload(MaintenanceTicket.location),
                selectinload(MaintenanceTicket.employee)
            )
            .where(MaintenanceTicket.ticket_number == "TKT-MNT-20260903-00002")
        )
        res = await db.execute(stmt)
        t = res.scalars().first()
        if not t:
            # Fallback to latest MaintenanceTicket
            stmt_latest = (
                select(MaintenanceTicket)
                .options(
                    selectinload(MaintenanceTicket.category),
                    selectinload(MaintenanceTicket.subcategory),
                    selectinload(MaintenanceTicket.issue_type),
                    selectinload(MaintenanceTicket.priority),
                    selectinload(MaintenanceTicket.location),
                    selectinload(MaintenanceTicket.employee)
                )
                .order_by(MaintenanceTicket.ticket_id.desc())
            )
            res2 = await db.execute(stmt_latest)
            t = res2.scalars().first()

        stanclea_phone = "263780099291"

        from app.state_manager import clear_user_state
        # Clear any stale conversation state for Stanclea
        await clear_user_state(db, stanclea_phone)

        cat_name = t.category.category_name if t and t.category else "Renovation & Expansion"
        sub_name = t.subcategory.subcategory_name if t and t.subcategory else "Structural & Partitioning"
        issue_name = t.issue_type.issue_name if t and t.issue_type else "Room extension / expansion work"
        priority_name = t.priority.priority_name if t and t.priority else "Medium"
        desc = t.description if t and t.description else "We would like to close the back area and make a double story,also move the showroom back"
        ticket_num = t.ticket_number if t else "TKT-MNT-20260903-00002"
        loc_name = t.location.location_name if t and t.location else "Shop 5"
        room_area = t.room_area or "Warehouse"
        image_id = t.image_id if t else None

        header = "🚨 NEW 🏗️ PROJECTS TICKET"
        body = (
            f"🎫 *Ticket ID:* `{ticket_num}`\n"
            f"👤 *Reporter:* Zayn (General) (`+263713866223`)\n"
            f"🏢 *Location:* {loc_name}\n"
            f"📍 *Room / Area:* {room_area}\n"
            f"📌 *Category:* {cat_name} ➡️ {sub_name}\n"
            f"⚙️ *Issue:* {issue_name}\n"
            f"🚨 *Priority:* {priority_name}\n"
            f"📝 *Description:* {desc}"
        )
        footer = "Tap button below to claim ticket"
        buttons = [
            {"id": f"claim_{ticket_num}", "title": "🔵 Claim Ticket"}
        ]
        try:
            resp = await meta_api.send_button_message(
                to_phone=stanclea_phone,
                body_text=body,
                buttons=buttons,
                header_text=header,
                footer_text=footer,
                image_id=image_id
            )
        except Exception as send_err:
            resp = {"meta_error": str(send_err)}
        return {"status": "SUCCESS", "meta_response": resp, "ticket": ticket_num, "sent_to": stanclea_phone}
    except Exception as e:
        import traceback
        logger.error(f"Error sending zayn ticket to stanclea: {e}", exc_info=True)
        return {"error": str(e), "traceback": traceback.format_exc()}

@app.get("/debug-stanclea-admin-check")
async def debug_stanclea_admin_check(db: AsyncSession = Depends(get_db)):
    """Inspects Stanclea's exact admin, employee, and conversation state records."""
    try:
        from app.database import SupportAdmin, Employee, ConversationState
        stanclea_phone = "263780099291"
        adm = await is_admin(db, stanclea_phone)
        emp = await is_employee_registered(db, stanclea_phone)
        state = await get_user_state(db, stanclea_phone)

        all_admins = (await db.execute(select(SupportAdmin))).scalars().all()
        all_emps = (await db.execute(select(Employee).where(Employee.phone.like("%780099291%")))).scalars().all()

        return {
            "is_admin_result": {"id": adm.admin_id, "name": adm.full_name, "phone": adm.phone, "active": adm.active, "is_maint": adm.is_maintenance_admin} if adm else None,
            "is_employee_result": {"id": emp.employee_id, "name": emp.full_name, "phone": emp.phone, "is_maint_reporter": emp.is_maintenance_reporter} if emp else None,
            "current_state": {"flow": state.flow_name, "step": state.current_step, "data": state.current_data} if state else None,
            "all_admins_list": [{"id": a.admin_id, "name": a.full_name, "phone": a.phone, "active": a.active} for a in all_admins],
            "matching_employees": [{"id": e.employee_id, "name": e.full_name, "phone": e.phone} for e in all_emps]
        }
    except Exception as e:
        return {"error": str(e), "traceback": traceback.format_exc()}



