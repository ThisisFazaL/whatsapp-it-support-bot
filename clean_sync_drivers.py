import asyncio
from app.database import engine
from sqlalchemy import text

# The definitive 21 drivers from user's PDF
DRIVERS_MAP = [
    {"name": "Kelvin Chitsamba", "phone": "263712035327"},
    {"name": "Godknows Kadungure", "phone": "263712024201"},
    {"name": "Garikai Madubeko", "phone": "263712035390"},
    {"name": "Tonderai Matongo", "phone": "263712024095"},
    {"name": "Wilbert Makoma", "phone": "263712035303"},
    {"name": "Tatenda Bhunu", "phone": "26371204128"},
    {"name": "Takudzwa Bafana", "phone": "263712035305"},
    {"name": "Brian", "phone": "26371204166"},
    {"name": "Ashley Zirota", "phone": "263712035780"},
    {"name": "Langton Mariga", "phone": "26371204106"},
    {"name": "Shepherd Matowanyika", "phone": "26371204109"},
    {"name": "Nathan", "phone": "26372035559"},
    {"name": "Peter Ncube", "phone": "26371204156"},
    {"name": "Lastern Sabola", "phone": "26371204145"},
    {"name": "Fortune Samukange", "phone": "263712035301"},
    {"name": "Michael Kamudyariwa", "phone": "263712035418"},
    {"name": "Last Kanyandura", "phone": "263712035813"},
    {"name": "Nyasha Isaiah", "phone": "263712035527"},
    {"name": "Praymore Madondo", "phone": "263712035440"},
    {"name": "Owen Sibanda", "phone": "263712035457"},
    {"name": "Terrence Mupfumi", "phone": "263712035503"},
]

async def sync():
    async with engine.connect() as conn:
        conn = await conn.execution_options(isolation_level="AUTOCOMMIT")

        # 1. Clean up duplicate id 40 if present in workshop_staff
        await conn.execute(text("DELETE FROM workshop_staff WHERE staff_id = 40;"))

        print("=== UPDATING WORKSHOP_STAFF ===", flush=True)
        for drv in DRIVERS_MAP:
            # Check by exact name or first name if unique
            first_name = drv["name"].split()[0]
            if first_name == "Last":
                q = text("SELECT staff_id, full_name, phone FROM workshop_staff WHERE full_name ILIKE 'Last %';")
            elif first_name == "Lastern":
                q = text("SELECT staff_id, full_name, phone FROM workshop_staff WHERE full_name ILIKE 'Lastern %';")
            elif first_name == "Shepherd":
                q = text("SELECT staff_id, full_name, phone FROM workshop_staff WHERE full_name ILIKE '%Matowanyika%';")
            else:
                q = text("SELECT staff_id, full_name, phone FROM workshop_staff WHERE full_name ILIKE :pat;")
            
            res = await conn.execute(q, {"pat": f"%{first_name}%"})
            rows = res.fetchall()

            if rows:
                sid = rows[0][0]
                await conn.execute(text("UPDATE workshop_staff SET phone = :phone, active = true WHERE staff_id = :sid;"), {"phone": drv["phone"], "sid": sid})
                print(f"  [OK] WS: {rows[0][1]} -> {drv['phone']}", flush=True)
            else:
                await conn.execute(text("INSERT INTO workshop_staff (full_name, phone, role, active) VALUES (:name, :phone, 'DRIVER', true);"), {"name": drv["name"], "phone": drv["phone"]})
                print(f"  [NEW] WS: {drv['name']} -> {drv['phone']}", flush=True)

        print("\n=== UPDATING EMPLOYEES ===", flush=True)
        dept_row = (await conn.execute(text("SELECT department_id FROM departments WHERE department_name ILIKE '%driver%' OR department_name ILIKE '%fleet%' LIMIT 1;"))).fetchone()
        dept_id = dept_row[0] if dept_row else 22

        for drv in DRIVERS_MAP:
            first_name = drv["name"].split()[0]
            if first_name == "Last":
                q = text("SELECT employee_id, full_name, phone FROM employees WHERE full_name ILIKE 'Last %';")
            elif first_name == "Lastern":
                q = text("SELECT employee_id, full_name, phone FROM employees WHERE full_name ILIKE 'Lastern %';")
            elif first_name == "Shepherd":
                q = text("SELECT employee_id, full_name, phone FROM employees WHERE full_name ILIKE '%Matowanyika%';")
            else:
                q = text("SELECT employee_id, full_name, phone FROM employees WHERE full_name ILIKE :pat;")
            
            res = await conn.execute(q, {"pat": f"%{first_name}%"})
            rows = res.fetchall()

            if rows:
                eid = rows[0][0]
                await conn.execute(text("UPDATE employees SET phone = :phone, active = true WHERE employee_id = :eid;"), {"phone": drv["phone"], "eid": eid})
                print(f"  [OK] EMP: {rows[0][1]} -> {drv['phone']}", flush=True)
            else:
                await conn.execute(text("""
                    INSERT INTO employees (full_name, phone, department_id, active, is_maintenance_reporter)
                    VALUES (:name, :phone, :dept_id, true, false);
                """), {"name": drv["name"], "phone": drv["phone"], "dept_id": dept_id})
                print(f"  [NEW] EMP: {drv['name']} -> {drv['phone']}", flush=True)

        print("\n=== FINAL VERIFICATION (ALL 21 DRIVERS) ===", flush=True)
        for drv in DRIVERS_MAP:
            ws_r = (await conn.execute(text("SELECT full_name, phone, active FROM workshop_staff WHERE phone = :ph;"), {"ph": drv["phone"]})).fetchone()
            emp_r = (await conn.execute(text("SELECT full_name, phone, active FROM employees WHERE phone = :ph;"), {"ph": drv["phone"]})).fetchone()
            print(f"Driver {drv['name']:<25} | WS: {ws_r[1] if ws_r else 'MISSING'} | EMP: {emp_r[1] if emp_r else 'MISSING'}")

    await engine.dispose()

if __name__ == "__main__":
    asyncio.run(sync())
