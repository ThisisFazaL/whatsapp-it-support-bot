import asyncio
import logging
import sys
from sqlalchemy import select
from app.database import async_session_factory, Employee
from app.meta_api import meta_api

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("broadcast_template")

async def send_template_broadcast(template_name: str, lang_code: str = "en"):
    logger.info(f"Starting template broadcast '{template_name}' (lang: {lang_code}) to all registered employees...")
    async with async_session_factory() as session:
        stmt = select(Employee).where(Employee.active == True)
        res = await session.execute(stmt)
        employees = res.scalars().all()

        total = len(employees)
        logger.info(f"Found {total} active employees for broadcast.")

        success_count = 0
        fail_count = 0

        for idx, emp in enumerate(employees, start=1):
            phone = emp.phone
            logger.info(f"[{idx}/{total}] Sending template '{template_name}' to {emp.full_name} ({phone})...")
            
            res_meta = await meta_api.send_template_message(phone, template_name, lang_code)
            if "messages" in res_meta:
                success_count += 1
            else:
                fail_count += 1
                logger.warning(f"Failed to send template to {emp.full_name} ({phone}): {res_meta}")

            await asyncio.sleep(0.5)

        logger.info(f"✅ Template Broadcast Finished! Successfully delivered to {success_count}/{total} employees.")

if __name__ == "__main__":
    t_name = sys.argv[1] if len(sys.argv) > 1 else "tagoneswa_launch_announcement"
    asyncio.run(send_template_broadcast(t_name))
