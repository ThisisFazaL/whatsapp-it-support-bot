import asyncio
import logging
from sqlalchemy import text
from app.database import Base, engine

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("migrate")

async def migrate():
    logger.info("Migrating PostgreSQL schema for Maintenance fields and dedicated maintenance_tickets table...")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.execute(text("ALTER TABLE admin_category_mapping ADD COLUMN IF NOT EXISTS subcategory_id INT REFERENCES subcategories(subcategory_id) ON DELETE CASCADE;"))
        await conn.execute(text("ALTER TABLE admin_category_mapping ALTER COLUMN category_id DROP NOT NULL;"))
        await conn.execute(text("ALTER TABLE tickets ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP;"))
        await conn.execute(text("ALTER TABLE tickets ADD COLUMN IF NOT EXISTS image_id VARCHAR(100);"))
        await conn.execute(text("ALTER TABLE support_admins ADD COLUMN IF NOT EXISTS is_master_admin BOOLEAN DEFAULT FALSE;"))
        await conn.execute(text("ALTER TABLE support_admins ADD COLUMN IF NOT EXISTS is_maintenance_admin BOOLEAN DEFAULT FALSE;"))
        await conn.execute(text("ALTER TABLE employees ADD COLUMN IF NOT EXISTS is_maintenance_reporter BOOLEAN DEFAULT FALSE;"))
        await conn.execute(text("ALTER TABLE categories ADD COLUMN IF NOT EXISTS domain VARCHAR(20) DEFAULT 'IT';"))
    logger.info("✅ Schema migration completed successfully!")

if __name__ == "__main__":
    asyncio.run(migrate())
