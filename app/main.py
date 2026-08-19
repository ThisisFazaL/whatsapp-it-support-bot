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
from app.state_manager import is_employee_registered, get_user_state
from app.handlers.admin_handler import handle_admin_command
from app.handlers.resolution_handler import handle_resolution_confirmation
from app.handlers.flow_handler import handle_flow
from app.handlers.my_tickets_handler import handle_my_tickets
from app.reports import send_daily_report_to_master
from app.meta_api import meta_api

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

@app.get("/")
async def root():
    return {
        "service": "WhatsApp IT Support Chatbot API",
        "status": "running",
        "webhook_endpoint": "/webhook/meta-whatsapp",
        "docs": "/docs"
    }

@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "whatsapp_it_support_bot"}

@app.get("/daily-report.pdf")
async def download_daily_report_pdf():
    """Serves the latest Daily Master Executive Report PDF directly for Meta WhatsApp API."""
    pdf_path = "Daily_IT_Support_Master_Report_Sample.pdf"
    if not os.path.exists(pdf_path):
        from generate_daily_report_pdf import create_daily_report_pdf
        create_daily_report_pdf(pdf_path)
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
            else:
                logger.info(f"Unsupported message type '{msg_type}' received from {sender_phone}.")
                await meta_api.send_text_message(sender_phone, "ℹ️ Please send text messages, numbers, photo attachments, or tap interactive buttons.")
                return

            # Step 1: Employee Registration Check
            employee = await is_employee_registered(db, sender_phone)
            if not employee:
                logger.warning(f"Unregistered phone number attempted access: {sender_phone}")
                warning_msg = (
                    f"🚫 *Access Restricted*\n\n"
                    f"Your phone number (`+{sender_phone}`) is not registered as an active employee in our IT Support database.\n\n"
                    f"Please contact your IT System Administrator to register your account."
                )
                await meta_api.send_text_message(sender_phone, warning_msg)
                return

            # Step 2: "My Tickets" Command Check
            isMyTickets = await handle_my_tickets(db, employee, message_text)
            if isMyTickets:
                return

            # Step 3: Admin Command Check (e.g. 'resolve TKT-...')
            isAdminCmd = await handle_admin_command(db, sender_phone, message_text)
            if isAdminCmd:
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
                image_id=image_id
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
