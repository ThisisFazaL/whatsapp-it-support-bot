import asyncio
import logging
from sqlalchemy import text
from app.database import engine

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("fix_seq")

async def fix_sequences():
    logger.info("Fixing PostgreSQL primary key sequence counters...")
    tables = [
        ("tickets", "ticket_id", "tickets_ticket_id_seq"),
        ("employees", "employee_id", "employees_employee_id_seq"),
        ("support_admins", "admin_id", "support_admins_admin_id_seq"),
        ("categories", "category_id", "categories_category_id_seq"),
        ("subcategories", "subcategory_id", "subcategories_subcategory_id_seq"),
        ("issue_types", "issue_type_id", "issue_types_issue_type_id_seq"),
        ("locations", "location_id", "locations_location_id_seq"),
        ("departments", "department_id", "departments_department_id_seq"),
    ]

    async with engine.begin() as conn:
        for tbl, pk, seq in tables:
            try:
                sql = f"SELECT setval('{seq}', COALESCE((SELECT MAX({pk}) FROM {tbl}), 0) + 1, false);"
                await conn.execute(text(sql))
                logger.info(f"Fixed sequence {seq} for table {tbl}.")
            except Exception as e:
                logger.warning(f"Could not reset sequence {seq}: {e}")
    logger.info("✅ All PostgreSQL sequences fixed!")

if __name__ == "__main__":
    asyncio.run(fix_sequences())
