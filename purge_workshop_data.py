import asyncio
import os
import sys
from sqlalchemy import select, delete, text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

from app.config import settings
from app.database import Base, ConversationState
from app.workshop.models import (
    WorkshopTruck, WorkshopStaff, WorkshopCategory, WorkshopSubcategory,
    WorkshopTicket, WorkshopPartsRequest
)

async def purge_all_workshop_data():
    """Performs a complete, clean, one-time deletion of all workshop trucks, staff, tickets, parts requests, and states."""
    db_urls = [settings.database_url, "sqlite+aiosqlite:///./itsupport.db"]
    
    for url in db_urls:
        try:
            kw = {"echo": False}
            if "postgresql" in url:
                kw["connect_args"] = {"ssl": "require", "statement_cache_size": 0, "prepared_statement_cache_size": 0}
            engine = create_async_engine(url, **kw)
            
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
                
            session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
            async with session_factory() as session:
                # 1. Delete all parts requests & tickets
                await session.execute(delete(WorkshopPartsRequest))
                await session.execute(delete(WorkshopTicket))
                
                # 2. Delete all trucks & staff
                await session.execute(delete(WorkshopTruck))
                await session.execute(delete(WorkshopStaff))
                
                # 3. Clean up workshop-related user states
                ws_steps = [
                    "ws_truck_search", "ws_confirm_truck", "ws_select_multi_truck",
                    "ws_select_category", "ws_select_subcategory", "ws_enter_description",
                    "ws_attach_clerk_photo", "ws_enter_eta", "ws_parts_check",
                    "ws_enter_part_details", "ws_parts_attach_photo", "ws_parts_clarification_reply",
                    "ws_enter_resolution_notes", "ws_enter_costing", "ws_reject_reason",
                    "ws_internal_fix_notes", "ws_qc_fail_reason", "ws_purchasing_inquiry"
                ]
                await session.execute(delete(ConversationState).where(ConversationState.current_step.in_(ws_steps)))
                
                await session.commit()
                print(f"[OK] Purged all workshop data successfully on: {url}")
                
        except Exception as e:
            print(f"[NOTE] Purge on {url} encountered: {e}")

if __name__ == "__main__":
    asyncio.run(purge_all_workshop_data())
