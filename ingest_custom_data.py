import sys
import json
import asyncio
import argparse
from sqlalchemy import select, delete
from app.database import (
    async_session_factory, Location, Department, Category, Subcategory, IssueType,
    SupportAdmin, AdminCategoryMapping, Employee
)

SAMPLE_CUSTOM_DATA = {
    "locations": ["Headquarters - Floor 3", "Branch Office - Surat", "Plant - Ahmedabad"],
    "departments": ["IT Support", "Maintenance & Facilities", "Finance & HR", "Production"],
    "categories": [
        {
            "id": 1,
            "name": "Hardware & Devices",
            "subcategories": [
                {
                    "name": "Laptop / Desktop PC",
                    "issues": ["Display / Screen damage", "Battery / Power failure", "BSOD System crash"]
                },
                {
                    "name": "Printers & Scanners",
                    "issues": ["Printer offline", "Paper jam / Toner issue"]
                }
            ]
        },
        {
            "id": 2,
            "name": "Maintenance & Facilities",
            "subcategories": [
                {
                    "name": "AC & Electrical",
                    "issues": ["AC cooling issue", "Power socket non-functional"]
                },
                {
                    "name": "Plumbing & Office Setup",
                    "issues": ["Water leak in restroom", "Chair / Desk repair"]
                }
            ]
        }
    ],
    "admins": [
        {
            "name": "Fazal Saiyed (Master)",
            "phone": "919265368695",
            "is_master": True,
            "category_ids": [1, 2]
        },
        {
            "name": "Maintenance Manager",
            "phone": "919876543212",
            "is_master": False,
            "category_ids": [2]
        }
    ],
    "employees": [
        {
            "code": "EMP1004",
            "name": "Fazal Saiyed",
            "phone": "919265368695",
            "email": "fazal@company.com",
            "department": "IT Support",
            "location": "Headquarters - Floor 3"
        }
    ]
}

async def ingest_json_data(data: dict):
    print("Beginning custom data ingestion...")
    async with async_session_factory() as session:
        # 1. Locations
        loc_map = {}
        for idx, loc_name in enumerate(data.get("locations", []), start=1):
            stmt = select(Location).where(Location.location_name == loc_name)
            loc = (await session.execute(stmt)).scalars().first()
            if not loc:
                loc = Location(location_name=loc_name)
                session.add(loc)
                await session.flush()
            loc_map[loc_name] = loc.location_id

        # 2. Departments
        dept_map = {}
        for dept_name in data.get("departments", []):
            stmt = select(Department).where(Department.department_name == dept_name)
            dept = (await session.execute(stmt)).scalars().first()
            if not dept:
                dept = Department(department_name=dept_name)
                session.add(dept)
                await session.flush()
            dept_map[dept_name] = dept.department_id

        # 3. Categories, Subcategories, Issues
        for cat_item in data.get("categories", []):
            cat_name = cat_item["name"]
            stmt = select(Category).where(Category.category_name == cat_name)
            cat = (await session.execute(stmt)).scalars().first()
            if not cat:
                cat = Category(category_name=cat_name, active=True)
                session.add(cat)
                await session.flush()
            
            for sub_item in cat_item.get("subcategories", []):
                sub_name = sub_item["name"]
                stmt_sub = select(Subcategory).where(
                    Subcategory.category_id == cat.category_id,
                    Subcategory.subcategory_name == sub_name
                )
                sub = (await session.execute(stmt_sub)).scalars().first()
                if not sub:
                    sub = Subcategory(category_id=cat.category_id, subcategory_name=sub_name, active=True)
                    session.add(sub)
                    await session.flush()

                for issue_name in sub_item.get("issues", []):
                    stmt_iss = select(IssueType).where(
                        IssueType.subcategory_id == sub.subcategory_id,
                        IssueType.issue_name == issue_name
                    )
                    iss = (await session.execute(stmt_iss)).scalars().first()
                    if not iss:
                        iss = IssueType(subcategory_id=sub.subcategory_id, issue_name=issue_name, active=True)
                        session.add(iss)

        # 4. Admins & Category Mappings
        for adm in data.get("admins", []):
            phone = str(adm["phone"]).replace("+", "").replace(" ", "").strip()
            stmt_adm = select(SupportAdmin).where(SupportAdmin.phone == phone)
            admin_obj = (await session.execute(stmt_adm)).scalars().first()
            if not admin_obj:
                admin_obj = SupportAdmin(
                    full_name=adm["name"],
                    phone=phone,
                    is_master_admin=adm.get("is_master", False),
                    active=True
                )
                session.add(admin_obj)
                await session.flush()
            else:
                admin_obj.full_name = adm["name"]
                admin_obj.is_master_admin = adm.get("is_master", False)

            # Category mappings
            for cid in adm.get("category_ids", []):
                stmt_map = select(AdminCategoryMapping).where(
                    AdminCategoryMapping.admin_id == admin_obj.admin_id,
                    AdminCategoryMapping.category_id == cid
                )
                m = (await session.execute(stmt_map)).scalars().first()
                if not m:
                    m = AdminCategoryMapping(admin_id=admin_obj.admin_id, category_id=cid)
                    session.add(m)

        # 5. Employees
        for emp_item in data.get("employees", []):
            phone = str(emp_item["phone"]).replace("+", "").replace(" ", "").strip()
            stmt_emp = select(Employee).where(Employee.phone == phone)
            emp = (await session.execute(stmt_emp)).scalars().first()
            
            dept_id = dept_map.get(emp_item.get("department"))
            loc_id = loc_map.get(emp_item.get("location"))

            if not emp:
                emp = Employee(
                    employee_code=emp_item.get("code", "EMP1000"),
                    full_name=emp_item["name"],
                    phone=phone,
                    email=emp_item.get("email"),
                    department_id=dept_id,
                    location_id=loc_id,
                    active=True
                )
                session.add(emp)
            else:
                emp.full_name = emp_item["name"]
                emp.email = emp_item.get("email")
                emp.department_id = dept_id
                emp.location_id = loc_id

        await session.commit()
        print("✅ Custom data ingested successfully!")

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1].endswith(".json"):
        with open(sys.argv[1], "r", encoding="utf-8") as f:
            data = json.load(f)
        asyncio.run(ingest_json_data(data))
    else:
        print("Running ingestion with default sample schema...")
        asyncio.run(ingest_json_data(SAMPLE_CUSTOM_DATA))
