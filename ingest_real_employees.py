import asyncio
import logging
import csv
import io
from sqlalchemy import select, delete, text
from app.database import (
    async_session_factory, Location, Department, Employee,
    SupportAdmin, AdminCategoryMapping, Category, Ticket, TicketAssignment, ConversationState, engine
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ingest_real")

RAW_CSV_DATA = """Full Name,Phone Number,Department,Company Name,Company Location
Chaleka Stuart,263775502914,Sales,TAGONESWA,110 Coventry Road Workington
Faisal Kassim,263780100503,Repairs Maintenance,Tagoneswa,110 Coventry Road Workington
Sujit Patel,263718352518,Admin,"Lg,TG,Kreckle",110 Coventry Road Workington
Arshford Mariga,263776477481,Hr,Tagoneswa | LG | Kreckle Foods,6 Austin Road Workington
David Nyandare,263783041705,Shop Manager,Tagoneswa Hardware,110 Coventry Road Workington
Esmatullah Wais,263784171527,Warehouse,Tagoneswa,110 Coventry Road Workington
Nayan Desai,263715071114,Shop Manager,Tagoneswa Hardware,110 Coventry Road Workington
Faizan Patel,263778405964,,LG,110 Coventry Road Workington
Paidamoyo Mapeka,263712127593,Procurement,Projects,110 Coventry Road Workington
Primrose Mutamba,263787061699,Projects,Bridgerton Investment,110 Coventry Road Workington
Gladys,263788500190,Projects,Bridgerton/Cloudglow,110 Coventry Road Workington
Talent Ruziwe,263717905915,Sales And Marketing,Tg,110 Coventry Road Workington
Primrose Mutamba,263717741469,Projects,Tagoneswa Investments Pvt Ltd,110 Coventry Road Workington
Simbarashe Chaunoita,263785571584,Production,LG Plast,110 Coventry Road Workington
Tariro Kanhichire,263788146329,Cashier,Tagoneswa investment,110 Coventry Road Workington
Vanessa Chido Zimbiti,263782723251,Sales And Marketing,Tagoneswa,110 Coventry Road Workington
Takudzwa Ryan Zamani,263776502926,Stores,Lightgroove investments,110 Coventry Road Workington
Batsirai Muradzikwa,263711421202,Production,Kreckle Foods,6 Austin Road Workington
Soyab Patel,263784077420,Production,Kreckle Foods,6 Austin Road Workington
Amin Mudhala,263781343668,Admin,Kreckle Foods,6 Austin Road Workington
Brenda Kwangare,263714282265,Production,Kreckle Foods,6 Austin Road Workington
Mehluli Sibanda,263774522586,Production,Kreckle Foods,6 Austin Road Workington
Tafadzwa Dube,263774308083,Production,Kreckle Foods,6 Austin Road Workington
Hujefa Patel,263778861934,Admin,Kreckle Foods,6 Austin Road Workington
Stansy,263780099291,Projects,Bridgerton/Cloudglow,110 Coventry Road Workington
Sajjad Kazi,263788500565,Sales,Kreckle Foods,6 Austin Road Workington
Omprakash,263780099335,Maintenance,Kreckle foods,6 Austin Road Workington
Tafadzwa Sungiso,263717905914,Tg Sales And Marketing,Tagoneswa,110 Coventry Road Workington
Rumbidzai,263787380916,Hr,TG,110 Coventry Road Workington
Ellias Murenga,263788843579,It,Tagoneswa Investments,110 Coventry Road Workington
Faruk Patel,263780515663,Lg Factory,COVENTRY,110 Coventry Road Workington
Decide Munengwa,263719532552,Tg Sales,Tagoneswa investments,110 Coventry Road Workington
Lydon Kandikire,263718295309,Logistics,Lightgroove investments,110 Coventry Road Workington
Panashe Mtamangira,263785322640,Logistics,Krecklefoods,6 Austin Road Workington
Faizan Shk,263714282264,Finance,All,110 Coventry Road Workington
Memory Kwenda,263719532553,Procurement,Tagoneswa investments,110 Coventry Road Workington
Melander Sumani,263787984319,Procurement,Tagoneswa investments,110 Coventry Road Workington
Everjoy Tias,263780216289,Sales Admin,Krecklefoods,6 Austin Road Workington
Ruvimbo Rumhungwe,263788071001,Sales And Marketing,Krecklefoods,6 Austin Road Workington
Christine Chiweshe,263783498457,Sales Admin,Tagoneswa investments,110 Coventry Road Workington
Onelly Madziro,263787381215,Sales Admin,Lightgroove investments,110 Coventry Road Workington
Mazviita Sibongile Ruzvidzo,263786673351,Sales Admin,Lightgroove investments,110 Coventry Road Workington
Rudo Chikarakara,263788311514,Lg Sales,LIGHTGROOVE,110 Coventry Road Workington
Sharon Mushawa,263712498581,Sales,LIGHTGROOVE,110 Coventry Road Workington
Raiyaan Afridi,263783125328,"Accounts, Logistics",LG Plast,110 Coventry Road Workington
Primrose Makumbe,263787891815,Lg Sales,Lightgroove investments,110 Coventry Road Workington
Mercy Mungoriwo,263780480274,Lg Sales,Lightgroove investments,110 Coventry Road Workington
Ashraf Nedziwe,263779214825,Sales And Marketing,LIGHTGROOVE,110 Coventry Road Workington
Rosa Ndimande Samihembo,263780573092,Sales & Marketing,KRECKLE FOODS,6 Austin Road Workington
Tanaka Mupfumi,263780435477,Tg Sales And Marketing,Tagoneswa,110 Coventry Road Workington
David Mungadzi,263780543771,Sales,Kreckle Foods,6 Austin Road Workington
Chiedza Chinopfukutwa,263780100545,Expenses Department,Krecklefoods,6 Austin Road Workington
Stuart Chaleka,263718643451,Marketing,Tagoneswa,110 Coventry Road Workington
Gabriel Jore,263783876347,Expense Department,Lightgroove investments,110 Coventry Road Workington
Sharon Shara,263719659503,Accounts,Lightgroove investments,110 Coventry Road Workington
Milcah Munashe Chidemo,263788068560,Accounts,Tagoneswa investments,110 Coventry Road Workington
Millcent Mkhwananzi,263718793307,Accounts,Tagoneswa Investments,110 Coventry Road Workington
Vigilance Bangezhano,263780100288,Accounts,Kreckle Foods,6 Austin Road Workington
Munashe Mangirandi,263787348969,Accounts,Krecklefoods,6 Austin Road Workington
Imraan Jooma,263781207175,Sales,"Krecklefoods,Lightgroove and Tagoneswa investments",110 Coventry Road Workington
Zayn,263713866223,General,"Tagoneswa Investments, Kreckle",110 Coventry Road Workington"""

async def ingest_real_company_directory():
    logger.info("Starting complete database reset and real employee ingestion...")
    async with async_session_factory() as session:
        # 1. Reset all test tickets, assignments, and conversation states
        await session.execute(delete(TicketAssignment))
        await session.execute(delete(Ticket))
        await session.execute(delete(ConversationState))
        logger.info("Cleared test tickets, assignments, and conversation states.")

        # 2. Parse CSV Data
        reader = csv.DictReader(io.StringIO(RAW_CSV_DATA))
        rows = list(reader)

        # 3. Collect & Ingest Unique Locations
        loc_map = {}
        for row in rows:
            loc_str = row["Company Location"].strip() if row.get("Company Location") else "Headquarters"
            if loc_str not in loc_map:
                stmt_loc = select(Location).where(Location.location_name == loc_str)
                loc = (await session.execute(stmt_loc)).scalars().first()
                if not loc:
                    loc = Location(location_name=loc_str)
                    session.add(loc)
                    await session.flush()
                loc_map[loc_str] = loc.location_id

        # 4. Collect & Ingest Unique Departments
        dept_map = {}
        # Make sure CEO, IT Support exist
        for d_str in ["IT Support", "CEO"]:
            stmt_d = select(Department).where(Department.department_name == d_str)
            d_obj = (await session.execute(stmt_d)).scalars().first()
            if not d_obj:
                d_obj = Department(department_name=d_str)
                session.add(d_obj)
                await session.flush()
            dept_map[d_str] = d_obj.department_id

        for row in rows:
            dept_str = row["Department"].strip() if row.get("Department") and row["Department"].strip() else "General"
            if dept_str not in dept_map:
                stmt_dept = select(Department).where(Department.department_name == dept_str)
                dept = (await session.execute(stmt_dept)).scalars().first()
                if not dept:
                    dept = Department(department_name=dept_str)
                    session.add(dept)
                    await session.flush()
                dept_map[dept_str] = dept.department_id

        # 5. Clear Dummy Employees (except Fazal 919265368695 and Arif 263732786786)
        preserved_phones = {"919265368695", "263732786786"}
        stmt_emp_del = select(Employee).where(Employee.phone.not_in(preserved_phones))
        old_dummy_emps = (await session.execute(stmt_emp_del)).scalars().all()
        for old_e in old_dummy_emps:
            await session.delete(old_e)
        await session.flush()
        logger.info("Removed old dummy employee records.")

        # 6. Ingest All 60 Real Employees
        ingested_count = 0
        for idx, row in enumerate(rows, start=1001):
            name = row["Full Name"].strip()
            phone = str(row["Phone Number"]).replace("+", "").replace(" ", "").strip()
            dept_str = row["Department"].strip() if row.get("Department") and row["Department"].strip() else "General"
            loc_str = row["Company Location"].strip() if row.get("Company Location") else "Headquarters"
            
            dept_id = dept_map.get(dept_str)
            loc_id = loc_map.get(loc_str)

            stmt_chk = select(Employee).where(Employee.phone == phone)
            emp = (await session.execute(stmt_chk)).scalars().first()
            if not emp:
                emp = Employee(
                    employee_code=f"EMP{idx}",
                    full_name=name,
                    phone=phone,
                    email=f"{name.lower().replace(' ', '.')}@company.com",
                    department_id=dept_id,
                    location_id=loc_id,
                    active=True
                )
                session.add(emp)
                ingested_count += 1
            else:
                emp.full_name = name
                emp.department_id = dept_id
                emp.location_id = loc_id
                emp.active = True

        # Ensure Fazal 919265368695 & Arif 263732786786 exist
        fazal_phone = "919265368695"
        stmt_fazal = select(Employee).where(Employee.phone == fazal_phone)
        fazal_emp = (await session.execute(stmt_fazal)).scalars().first()
        if not fazal_emp:
            session.add(Employee(
                employee_code="EMP1000",
                full_name="Fazal Saiyed",
                phone=fazal_phone,
                email="fazal@company.com",
                department_id=dept_map.get("IT Support", 1),
                location_id=loc_map.get("110 Coventry Road Workington", 1),
                active=True
            ))

        arif_phone = "263732786786"
        stmt_arif = select(Employee).where(Employee.phone == arif_phone)
        arif_emp = (await session.execute(stmt_arif)).scalars().first()
        if not arif_emp:
            session.add(Employee(
                employee_code="EMP1005",
                full_name="Arif",
                phone=arif_phone,
                email="arif@company.com",
                department_id=dept_map.get("CEO", 1),
                location_id=loc_map.get("110 Coventry Road Workington", 1),
                active=True
            ))

        # 7. Ensure Fazal is active Master Support Admin mapped to ALL categories
        stmt_adm = select(SupportAdmin).where(SupportAdmin.phone == fazal_phone)
        fazal_admin = (await session.execute(stmt_adm)).scalars().first()
        if not fazal_admin:
            fazal_admin = SupportAdmin(
                full_name="Fazal Saiyed (Primary Support Admin)",
                phone=fazal_phone,
                is_master_admin=True,
                active=True
            )
            session.add(fazal_admin)
            await session.flush()

        cat_stmt = select(Category).where(Category.active == True)
        all_categories = (await session.execute(cat_stmt)).scalars().all()
        
        await session.execute(delete(AdminCategoryMapping))
        await session.flush()

        for cat in all_categories:
            session.add(AdminCategoryMapping(admin_id=fazal_admin.admin_id, category_id=cat.category_id))

        await session.commit()
        logger.info(f"✅ Ingested {ingested_count} new real employees!")

    # 8. Reset sequences
    async with engine.begin() as conn:
        for tbl, pk, seq in [
            ("tickets", "ticket_id", "tickets_ticket_id_seq"),
            ("employees", "employee_id", "employees_employee_id_seq"),
            ("locations", "location_id", "locations_location_id_seq"),
            ("departments", "department_id", "departments_department_id_seq"),
        ]:
            try:
                await conn.execute(text(f"SELECT setval('{seq}', COALESCE((SELECT MAX({pk}) FROM {tbl}), 0) + 1, false);"))
            except Exception:
                pass

    logger.info("✅ Full real company employee directory ingested & tickets reset successfully!")

if __name__ == "__main__":
    asyncio.run(ingest_real_company_directory())
