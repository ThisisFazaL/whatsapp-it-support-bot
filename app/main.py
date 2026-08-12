import logging
from typing import Set
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, Response, Query, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.config import settings
from app.database import get_db, init_db_models, Ticket
from app.state_manager import is_employee_registered, get_user_state
from app.handlers.admin_handler import handle_admin_command
from app.handlers.resolution_handler import handle_resolution_confirmation
from app.handlers.flow_handler import handle_flow
from app.handlers.my_tickets_handler import handle_my_tickets
from app.meta_api import meta_api

logger = logging.getLogger("main")
logging.basicConfig(level=logging.INFO)

PROCESSED_WAMIDS: Set[str] = set()

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifecycle startup and shutdown hooks."""
    logger.info("Initializing database models and seed data...")
    await init_db_models()
    logger.info("Database initialized successfully.")
    yield
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

@app.post("/webhook/meta-whatsapp")
async def handle_incoming_webhook(request: Request, db: AsyncSession = Depends(get_db)):
    """Meta WhatsApp Cloud API Webhook Handler for incoming text & image messages."""
    try:
        body = await request.json()
        logger.info(f"Incoming Webhook Payload: {body}")

        entry = body.get("entry", [])
        if not entry:
            return {"status": "ignored", "reason": "No entry"}

        changes = entry[0].get("changes", [])
        if not changes:
            return {"status": "ignored", "reason": "No changes"}

        value = changes[0].get("value", {})
        messages = value.get("messages", [])

        if not messages:
            return {"status": "ignored", "reason": "Status event / non-message event"}

        msg_obj = messages[0]
        wamid = msg_obj.get("id")
        sender_phone = msg_obj.get("from")
        msg_type = msg_obj.get("type")

        # Deduplication check
        if wamid and wamid in PROCESSED_WAMIDS:
            logger.info(f"Duplicate wamid '{wamid}' skipped.")
            return {"status": "duplicate_skipped"}

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
        else:
            logger.info(f"Unsupported message type '{msg_type}' received from {sender_phone}.")
            await meta_api.send_text_message(sender_phone, "ℹ️ Please send text messages, numbers, or photo attachments.")
            return {"status": "ok"}

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
            return {"status": "access_denied"}

        # Step 2: "My Tickets" Command Check
        isMyTickets = await handle_my_tickets(db, employee, message_text)
        if isMyTickets:
            return {"status": "my_tickets_handled"}

        # Step 3: Admin Command Check (e.g. 'resolve TKT-...')
        isAdminCmd = await handle_admin_command(db, sender_phone, message_text)
        if isAdminCmd:
            return {"status": "admin_command_handled"}

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
            return {"status": "resolution_confirmation_handled"}

        # Step 6: Multi-Step Ticket Flow Execution (with optional image)
        await handle_flow(
            session=db,
            employee=employee,
            message_text=message_text,
            state=state,
            image_id=image_id
        )

        return {"status": "ok"}

    except Exception as e:
        logger.error(f"Error handling incoming Meta WhatsApp webhook: {e}", exc_info=True)
        return {"status": "error", "detail": str(e)}

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
