import re
import datetime
from typing import Optional, Dict, Any
from sqlalchemy import select, delete
from sqlalchemy.orm.attributes import flag_modified
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import ConversationState, Employee, SupportAdmin

def clean_phone_number(phone: str) -> str:
    """Removes all non-digit characters (+, spaces, hyphens) from phone string."""
    if not phone:
        return ""
    digits = re.sub(r"[^\d]", "", str(phone))
    return digits

async def is_employee_registered(session: AsyncSession, phone: str) -> Optional[Employee]:
    """Returns Employee if clean phone digits match and active == True with relationships eagerly loaded."""
    from sqlalchemy.orm import selectinload
    clean_phone = clean_phone_number(phone)
    # Match exact or last 10 digits fallback
    stmt = (
        select(Employee)
        .options(selectinload(Employee.department), selectinload(Employee.location))
        .where(Employee.active == True)
    )
    res = await session.execute(stmt)
    employees = res.scalars().all()
    
    for emp in employees:
        emp_clean = clean_phone_number(emp.phone)
        if emp_clean == clean_phone or (len(clean_phone) >= 10 and clean_phone[-10:] == emp_clean[-10:]):
            return emp
    return None

async def is_admin(session: AsyncSession, phone: str) -> Optional[SupportAdmin]:
    """Returns SupportAdmin if clean phone digits match and active == True."""
    clean_phone = clean_phone_number(phone)
    stmt = select(SupportAdmin).where(SupportAdmin.active == True)
    res = await session.execute(stmt)
    admins = res.scalars().all()

    for admin in admins:
        admin_clean = clean_phone_number(admin.phone)
        if admin_clean == clean_phone or (len(clean_phone) >= 10 and clean_phone[-10:] == admin_clean[-10:]):
            return admin
    return None

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
