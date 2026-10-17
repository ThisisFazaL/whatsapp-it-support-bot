import asyncio
from app.database import engine
from sqlalchemy import text

DRIVERS_UPDATE = [
    {"first_name": "Kelvin", "full_name": "Kelvin Chitsamba", "phone": "263712035327"},
    {"first_name": "Godknows", "full_name": "Godknows Kadungure", "phone": "263712024201"},
    {"first_name": "Garikai", "full_name": "Garikai Madubeko", "phone": "263712035390"},
    {"first_name": "Tonderai", "full_name": "Tonderai Matongo", "phone": "263712024095"},
    {"first_name": "Wilbert", "full_name": "Wilbert Makoma", "phone": "263712035303"},
    {"first_name": "Tatenda", "full_name": "Tatenda Bhunu", "phone": "26371204128"},
    {"first_name": "Takudzwa", "full_name": "Takudzwa Bafana", "phone": "263712035305"},
    {"first_name": "Brian", "full_name": "Brian", "phone": "26371204166"},
    {"first_name": "Ashley", "full_name": "Ashley Zirota", "phone": "263712035780"},
    {"first_name": "Langton", "full_name": "Langton Mariga", "phone": "26371204106"},
    {"first_name": "Shepard", "full_name": "Shepherd Matowanyika", "phone": "26371204109"},
    {"first_name": "Nathan", "full_name": "Nathan", "phone": "26372035559"},
    {"first_name": "Peter", "full_name": "Peter Ncube", "phone": "26371204156"},
    {"first_name": "Lastern", "full_name": "Lastern Sabola", "phone": "26371204145"},
    {"first_name": "Fortune", "full_name": "Fortune Samukange", "phone": "263712035301"},
    {"first_name": "Michael", "full_name": "Michael Kamudyariwa", "phone": "263712035418"},
    {"first_name": "Last", "full_name": "Last Kanyandura", "phone": "263712035813"},
    {"first_name": "Nyasha", "full_name": "Nyasha Isaiah", "phone": "263712035527"},
    {"first_name": "Praymore", "full_name": "Praymore Madondo", "phone": "263712035440"},
    {"first_name": "Owen", "full_name": "Owen Sibanda", "phone": "263712035457"},
    {"first_name": "Terrence", "full_name": "Terrence Mupfumi", "phone": "263712035503"},
]

async def update_all_drivers():
    async with engine.connect() as conn:
        conn = await conn.execution_options(isolation_level="AUTOCOMMIT")

        print("=== UPDATING WORKSHOP STAFF ===", flush=True)
        for drv in DRIVERS_UPDATE:
            # Check existing workshop_staff
            check_q = text("SELECT staff_id, full_name, phone FROM workshop_staff WHERE full_name ILIKE :pat;")
            res = await conn.execute(check_q, {"pat": f"%{drv['first_name']}%"})
            existing = res.fetchall()

            if existing:
                for row in existing:
                    staff_id = row[0]
                    old_phone = row[2]
                    update_q = text("UPDATE workshop_staff SET phone = :phone, active = true WHERE staff_id = :sid;")
                    await conn.execute(update_q, {"phone": drv["phone"], "sid": staff_id})
                    print(f"  [UPDATED] WorkshopStaff: {row[1]} (id={staff_id}) {old_phone} -> {drv['phone']}", flush=True)
            else:
                # Insert new
                ins_q = text("INSERT INTO workshop_staff (full_name, phone, role, active) VALUES (:name, :phone, 'DRIVER', true);")
                await conn.execute(ins_q, {"name": drv["full_name"], "phone": drv["phone"]})
                print(f"  [INSERTED] WorkshopStaff: {drv['full_name']} -> {drv['phone']}", flush=True)

        print("\n=== UPDATING EMPLOYEES (FLEET) ===", flush=True)
        # Find drivers department
        dept_res = await conn.execute(text("SELECT department_id FROM departments WHERE department_name ILIKE '%driver%' OR department_name ILIKE '%fleet%' LIMIT 1;"))
        dept_row = dept_res.fetchone()
        dept_id = dept_row[0] if dept_row else 22

        for drv in DRIVERS_UPDATE:
            check_emp = text("SELECT employee_id, full_name, phone FROM employees WHERE full_name ILIKE :pat;")
            res = await conn.execute(check_emp, {"pat": f"%{drv['first_name']}%"})
            existing_emp = res.fetchall()

            if existing_emp:
                for row in existing_emp:
                    emp_id = row[0]
                    old_phone = row[2]
                    update_emp_q = text("UPDATE employees SET phone = :phone, active = true WHERE employee_id = :eid;")
                    await conn.execute(update_emp_q, {"phone": drv["phone"], "eid": emp_id})
                    print(f"  [UPDATED] Employee: {row[1]} (id={emp_id}) {old_phone} -> {drv['phone']}", flush=True)
            else:
                # Insert new employee
                ins_emp_q = text("""
                    INSERT INTO employees (full_name, phone, department_id, active, is_maintenance_reporter)
                    VALUES (:name, :phone, :dept_id, true, false);
                """)
                await conn.execute(ins_emp_q, {"name": drv["full_name"], "phone": drv["phone"], "dept_id": dept_id})
                print(f"  [INSERTED] Employee: {drv['full_name']} -> {drv['phone']}", flush=True)

        print("\n=== VERIFICATION OF ALL 21 DRIVERS ===", flush=True)
        for drv in DRIVERS_UPDATE:
            ws_check = await conn.execute(text("SELECT full_name, phone, active FROM workshop_staff WHERE phone = :ph;"), {"ph": drv["phone"]})
            ws_row = ws_check.fetchone()
            emp_check = await conn.execute(text("SELECT full_name, phone, active FROM employees WHERE phone = :ph;"), {"ph": drv["phone"]})
            emp_row = emp_check.fetchone()
            print(f"Driver {drv['first_name']:<10} | WS: {bool(ws_row)} ({ws_row[0] if ws_row else '--'}) | EMP: {bool(emp_row)} ({emp_row[0] if emp_row else '--'}) | Phone: {drv['phone']}", flush=True)

    await engine.dispose()

if __name__ == "__main__":
    asyncio.run(update_all_drivers())
