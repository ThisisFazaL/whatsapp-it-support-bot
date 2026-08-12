import asyncio
import logging
from sqlalchemy import text, delete
from app.database import (
    async_session_factory, TicketAssignment, Ticket, ConversationState, engine
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("reset_data")

async def reset_test_tickets():
    logger.info("Cleaning up all test tickets and resetting conversation states...")
    async with async_session_factory() as session:
        # 1. Delete all ticket assignments
        await session.execute(delete(TicketAssignment))
        logger.info("Deleted test ticket assignments.")

        # 2. Delete all test tickets
        await session.execute(delete(Ticket))
        logger.info("Deleted test tickets.")

        # 3. Clear conversation states
        await session.execute(delete(ConversationState))
        logger.info("Cleared conversation states.")

        await session.commit()

    # 4. Reset ticket primary key sequence counter back to 1
    async with engine.begin() as conn:
        try:
            await conn.execute(text("SELECT setval('tickets_ticket_id_seq', 1, false);"))
            logger.info("Reset tickets_ticket_id_seq sequence back to 1.")
        except Exception as e:
            logger.warning(f"Sequence reset notice: {e}")

    logger.info("✅ Database cleaned! All test tickets and temporary states removed while keeping Employees, Admins, and Categories intact.")

if __name__ == "__main__":
    asyncio.run(reset_test_tickets())
