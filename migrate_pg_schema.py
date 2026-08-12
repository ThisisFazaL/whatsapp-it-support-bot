import asyncio
import logging
from sqlalchemy import text
from app.database import engine

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("migrate")

async def migrate():
    logger.info("Migrating PostgreSQL schema for updated_at column...")
    async with engine.begin() as conn:
        # Add updated_at to tickets if missing
        await conn.execute(text("ALTER TABLE tickets ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP;"))
        # Add image_id to tickets if missing
        await conn.execute(text("ALTER TABLE tickets ADD COLUMN IF NOT EXISTS image_id VARCHAR(100);"))
        # Add is_master_admin to support_admins if missing
        await conn.execute(text("ALTER TABLE support_admins ADD COLUMN IF NOT EXISTS is_master_admin BOOLEAN DEFAULT FALSE;"))
    logger.info("✅ Schema migration completed successfully!")

if __name__ == "__main__":
    asyncio.run(migrate())
