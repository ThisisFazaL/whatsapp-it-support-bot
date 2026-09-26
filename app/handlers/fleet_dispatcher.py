import logging
import re
from typing import Optional, Any
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.handlers.logistics_handler import handle_edward_interaction, is_edward
from app.handlers.zayn_accounts_handler import handle_zayn_accounts_interaction
from app.handlers.driver_handler import handle_driver_interaction
from app.handlers.sales_admin_handler import handle_sales_admin_interaction
from app.handlers.logistics_manager_handler import handle_logistics_manager_interaction

from app.state_manager import normalize_phone_number

logger = logging.getLogger("fleet_dispatcher")


def clean_phone(phone: Optional[str]) -> str:
    return normalize_phone_number(str(phone or ""))


def is_fleet_interaction(phone: str, message_text: str, state: Optional[Any]) -> bool:
    """Fast check whether an incoming message belongs to the fleet operations subsystem."""
    txt = (message_text or "").strip().lower()

    if txt.startswith(("flt_", "location_pin_")):
        return True

    if state and state.flow_name:
        fn = state.flow_name.lower()
        if fn.startswith("fleet_") and fn not in {"fleet_approval", "fleet_pending"}:
            return True

    clean_p = clean_phone(phone)
    if is_edward(clean_p) and txt in {"trip queue", "queue", "allocate trip"}:
        return True

    # Support manual balance/settle command for Sales Admin
    if txt.startswith(("balance ", "settle ", "reconcile ")):
        return True

    return False



async def dispatch_fleet_message(
    session: AsyncSession,
    phone: str,
    message_text: str,
    state: Optional[Any],
    image_id: Optional[str] = None
) -> bool:
    """
    Modular dispatcher for all Fleet Operations Subsystem actions.
    Routes cleanly to dedicated handlers for Edward, Zayn, Accounts, Driver, Sales Admin, and Logistics Manager.
    Returns True if handled, False otherwise.
    """
    clean_p = clean_phone(phone)
    txt = (message_text or "").strip().lower()
    fn = state.flow_name.lower() if state and state.flow_name else ""

    # 1. Edward & Logistics Allocations
    if txt.startswith("flt_edw_") or fn == "fleet_edward" or (is_edward(clean_p) and txt in {"trip queue", "queue"}):
        handled = await handle_edward_interaction(session, clean_p, message_text, state)
        if handled:
            return True

    # 1.5 Sales Rep Allowance Configuration
    if txt.startswith("flt_rep_") or fn == "fleet_rep_allowance":
        from app.handlers.fleet_approval_handler import handle_sales_rep_allowance_interaction
        handled = await handle_sales_rep_allowance_interaction(session, clean_p, message_text, state)
        if handled:
            return True

    # 2. Zayn & Accounts
    if txt.startswith(("flt_zayn_", "flt_acc_")) or fn in {"fleet_zayn", "fleet_accounts"}:
        handled = await handle_zayn_accounts_interaction(session, clean_p, message_text, state)
        if handled:
            return True

    # 3. Driver Transit Actions
    if txt.startswith(("flt_drv_", "flt_pay_", "flt_emg_", "flt_odo_", "location_pin_")) or fn == "fleet_driver":
        handled = await handle_driver_interaction(session, clean_p, message_text, state, image_id=image_id)
        if handled:
            return True

    # 4. Sales Admin Balancing Actions
    if txt.startswith("flt_adm_") or fn == "fleet_sales_admin":
        handled = await handle_sales_admin_interaction(session, clean_p, message_text, state)
        if handled:
            return True

    # 5. Logistics Manager Adjudication Actions
    if txt.startswith("flt_mgr_") or fn == "fleet_logistics_mgr":
        handled = await handle_logistics_manager_interaction(session, clean_p, message_text, state)
        if handled:
            return True

    return False
