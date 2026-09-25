import re
import datetime
from typing import Optional, Dict, Any
from sqlalchemy import select, delete
from sqlalchemy.orm.attributes import flag_modified
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import ConversationState, Employee, SupportAdmin

import time

_EMPLOYEE_CACHE: Dict[str, tuple[float, Optional[Employee]]] = {}
_ADMIN_CACHE: Dict[str, tuple[float, Optional[SupportAdmin]]] = {}
CACHE_TTL_SECONDS = 300.0  # 5 minutes

def clean_phone_number(phone: str) -> str:
    """Removes all non-digit characters (+, spaces, hyphens) from phone string."""
    if not phone:
        return ""
    digits = re.sub(r"[^\d]", "", str(phone))
    return digits


def normalize_phone_number(phone: str) -> str:
    """
    Cleans and normalizes phone numbers into E.164 digits without leading '+'.
    Specifically auto-resolves Zimbabwean local numbers:
    - 07XXXXXXXX (10 digits starting with 0) -> 2637XXXXXXXX
    - 7XXXXXXXX (9 digits starting with 7) -> 2637XXXXXXXX
    Leaves international numbers (e.g. 91..., 1..., 27...) untouched.
    """
    if not phone:
        return ""
    digits = re.sub(r"[^\d]", "", str(phone))
    if len(digits) == 10 and digits.startswith("0"):
        digits = "263" + digits[1:]
    elif len(digits) == 9 and digits.startswith("7"):
        digits = "263" + digits
    return digits


def invalidate_user_cache(phone: str):
    """Evicts phone from in-memory employee and admin caches."""
    if not phone:
        return
    clean_p = clean_phone_number(phone)
    _EMPLOYEE_CACHE.pop(clean_p, None)
    _ADMIN_CACHE.pop(clean_p, None)


async def is_employee_registered(session: AsyncSession, phone: str) -> Optional[Employee]:
    """Returns Employee if clean phone digits match and active == True with relationships eagerly loaded."""
    if not phone:
        return None
    clean_phone = clean_phone_number(phone)
    now = time.time()

    # Check fast in-memory cache
    if clean_phone in _EMPLOYEE_CACHE:
        cached_time, cached_emp = _EMPLOYEE_CACHE[clean_phone]
        if now - cached_time < CACHE_TTL_SECONDS:
            return cached_emp

    from sqlalchemy.orm import selectinload
    last_9 = clean_phone[-9:] if len(clean_phone) >= 9 else clean_phone
    stmt = (
        select(Employee)
        .options(selectinload(Employee.department), selectinload(Employee.location))
        .where(
            (Employee.phone == phone) |
            (Employee.phone == clean_phone) |
            (Employee.phone.endswith(last_9)),
            Employee.active == True
        )
        .limit(1)
    )
    res = await session.execute(stmt)
    emp = res.scalars().first()

    _EMPLOYEE_CACHE[clean_phone] = (now, emp)
    return emp

async def is_admin(session: AsyncSession, phone: str) -> Optional[SupportAdmin]:
    """Returns SupportAdmin if clean phone digits match and active == True."""
    if not phone:
        return None
    clean_phone = clean_phone_number(phone)
    now = time.time()

    # Check fast in-memory cache
    if clean_phone in _ADMIN_CACHE:
        cached_time, cached_adm = _ADMIN_CACHE[clean_phone]
        if now - cached_time < CACHE_TTL_SECONDS:
            return cached_adm

    last_9 = clean_phone[-9:] if len(clean_phone) >= 9 else clean_phone
    stmt = select(SupportAdmin).where(
        (SupportAdmin.phone == phone) |
        (SupportAdmin.phone == clean_phone) |
        (SupportAdmin.phone.endswith(last_9)),
        SupportAdmin.active == True
    ).limit(1)
    res = await session.execute(stmt)
    admin = res.scalars().first()

    _ADMIN_CACHE[clean_phone] = (now, admin)
    return admin

async def get_user_state(session: AsyncSession, phone: str) -> Optional[ConversationState]:
    """Retrieves current conversation state for a phone number."""
    clean_phone = clean_phone_number(phone)
    stmt = select(ConversationState).where(ConversationState.phone == clean_phone)
    res = await session.execute(stmt)
    return res.scalars().first()

async def set_user_state(
    session: AsyncSession, 
    phone: str, 
    current_step: str, 
    current_data: Optional[Dict[str, Any]] = None,
    flow_name: str = "raise_ticket"
) -> ConversationState:
    """Updates or inserts the conversation state for a phone number."""
    clean_phone = clean_phone_number(phone)
    new_data = dict(current_data) if current_data is not None else {}
    
    state = await get_user_state(session, clean_phone)
    if state:
        state.current_step = current_step
        state.current_data = new_data
        state.flow_name = flow_name
        state.updated_at = datetime.datetime.utcnow()
        flag_modified(state, "current_data")
    else:
        state = ConversationState(
            phone=clean_phone,
            flow_name=flow_name,
            current_step=current_step,
            current_data=new_data,
            updated_at=datetime.datetime.utcnow()
        )
        session.add(state)
    
    await session.commit()
    return state

async def clear_user_state(session: AsyncSession, phone: str):
    """Deletes conversation state for a phone number."""
    clean_phone = clean_phone_number(phone)
    stmt = delete(ConversationState).where(ConversationState.phone == clean_phone)
    await session.execute(stmt)
    await session.commit()
