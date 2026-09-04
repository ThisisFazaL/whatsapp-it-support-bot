import datetime
import json
from typing import AsyncGenerator
from sqlalchemy import (
    Column, Integer, String, Text, Boolean, DateTime, ForeignKey, JSON
)
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base, relationship, selectinload
from sqlalchemy import select, func, delete

from app.config import settings

Base = declarative_base()

# Register Workshop models with Base
import app.workshop.models

class Location(Base):
    __tablename__ = "locations"
    location_id = Column(Integer, primary_key=True, autoincrement=True)
    location_name = Column(String(100), nullable=False)

class Department(Base):
    __tablename__ = "departments"
    department_id = Column(Integer, primary_key=True, autoincrement=True)
    department_name = Column(String(100), nullable=False)

class Employee(Base):
    __tablename__ = "employees"
    employee_id = Column(Integer, primary_key=True, autoincrement=True)
    employee_code = Column(String(50), nullable=True)
    full_name = Column(String(100), nullable=False)
    phone = Column(String(20), unique=True, nullable=False)
    email = Column(String(100), nullable=True)
    department_id = Column(Integer, ForeignKey("departments.department_id"), nullable=True)
    location_id = Column(Integer, ForeignKey("locations.location_id"), nullable=True)
    is_maintenance_reporter = Column(Boolean, default=False)
    active = Column(Boolean, default=True)

    department = relationship("Department")
    location = relationship("Location")

class SupportAdmin(Base):
    __tablename__ = "support_admins"
    admin_id = Column(Integer, primary_key=True, autoincrement=True)
    full_name = Column(String(100), nullable=False)
    phone = Column(String(20), unique=True, nullable=False)
    is_master_admin = Column(Boolean, default=False)
    is_maintenance_admin = Column(Boolean, default=False)
    active = Column(Boolean, default=True)

    category_mappings = relationship("AdminCategoryMapping", back_populates="admin", cascade="all, delete-orphan")

class AdminCategoryMapping(Base):
    __tablename__ = "admin_category_mapping"
    mapping_id = Column(Integer, primary_key=True, autoincrement=True)
    admin_id = Column(Integer, ForeignKey("support_admins.admin_id"), nullable=False)
    category_id = Column(Integer, ForeignKey("categories.category_id"), nullable=True)
    subcategory_id = Column(Integer, ForeignKey("subcategories.subcategory_id"), nullable=True)

    admin = relationship("SupportAdmin", back_populates="category_mappings")
    category = relationship("Category")
    subcategory = relationship("Subcategory")

class Category(Base):
    __tablename__ = "categories"
    category_id = Column(Integer, primary_key=True, autoincrement=True)
    category_name = Column(String(100), nullable=False)
    domain = Column(String(20), default="IT") # "IT" or "MAINTENANCE"
    active = Column(Boolean, default=True)
    
    subcategories = relationship("Subcategory", back_populates="category", cascade="all, delete-orphan")

class Subcategory(Base):
    __tablename__ = "subcategories"
    subcategory_id = Column(Integer, primary_key=True, autoincrement=True)
    category_id = Column(Integer, ForeignKey("categories.category_id"), nullable=False)
    subcategory_name = Column(String(100), nullable=False)
    active = Column(Boolean, default=True)

    category = relationship("Category", back_populates="subcategories")
    issue_types = relationship("IssueType", back_populates="subcategory", cascade="all, delete-orphan")

class IssueType(Base):
    __tablename__ = "issue_types"
    issue_type_id = Column(Integer, primary_key=True, autoincrement=True)
    subcategory_id = Column(Integer, ForeignKey("subcategories.subcategory_id"), nullable=False)
    issue_name = Column(String(150), nullable=False)
    active = Column(Boolean, default=True)

    subcategory = relationship("Subcategory", back_populates="issue_types")

class Priority(Base):
    __tablename__ = "priorities"
    priority_id = Column(Integer, primary_key=True)
    priority_name = Column(String(50), nullable=False)

class TicketStatus(Base):
    __tablename__ = "ticket_status"
    status_id = Column(Integer, primary_key=True)
    status_name = Column(String(50), nullable=False)

class Ticket(Base):
    __tablename__ = "tickets"
    ticket_id = Column(Integer, primary_key=True, autoincrement=True)
    ticket_number = Column(String(30), unique=True, nullable=False)
    employee_id = Column(Integer, ForeignKey("employees.employee_id"), nullable=False)
    location_id = Column(Integer, ForeignKey("locations.location_id"), nullable=True)
    domain = Column(String(20), default="IT") # "IT" or "MAINTENANCE"
    category_id = Column(Integer, ForeignKey("categories.category_id"), nullable=True)
    subcategory_id = Column(Integer, ForeignKey("subcategories.subcategory_id"), nullable=True)
    issue_type_id = Column(Integer, ForeignKey("issue_types.issue_type_id"), nullable=True)
    room_area = Column(String(150), nullable=True)
    is_safety_hazard = Column(Boolean, default=False)
    description = Column(Text, nullable=False)
    resolution_note = Column(Text, nullable=True)
    image_id = Column(String(100), nullable=True) # Optional Meta image attachment ID
    priority_id = Column(Integer, ForeignKey("priorities.priority_id"), default=2)
    status_id = Column(Integer, ForeignKey("ticket_status.status_id"), default=1)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)
    closed_at = Column(DateTime, nullable=True)

    employee = relationship("Employee")
    location = relationship("Location")
    category = relationship("Category")
    subcategory = relationship("Subcategory")
    issue_type = relationship("IssueType")
    priority = relationship("Priority")
    status = relationship("TicketStatus")

class TicketAssignment(Base):
    __tablename__ = "ticket_assignments"
    assignment_id = Column(Integer, primary_key=True, autoincrement=True)
    ticket_id = Column(Integer, ForeignKey("tickets.ticket_id"), nullable=False)
    admin_id = Column(Integer, ForeignKey("support_admins.admin_id"), nullable=False)
    assigned_at = Column(DateTime, default=datetime.datetime.utcnow)

    admin = relationship("SupportAdmin")
    ticket = relationship("Ticket")

class MaintenanceTicket(Base):
    __tablename__ = "maintenance_tickets"
    ticket_id = Column(Integer, primary_key=True, autoincrement=True)
    ticket_number = Column(String(30), unique=True, nullable=False)
    employee_id = Column(Integer, ForeignKey("employees.employee_id"), nullable=False)
    location_id = Column(Integer, ForeignKey("locations.location_id"), nullable=True)
    domain = Column(String(20), default="MAINTENANCE")
    category_id = Column(Integer, ForeignKey("categories.category_id"), nullable=True)
    subcategory_id = Column(Integer, ForeignKey("subcategories.subcategory_id"), nullable=True)
    issue_type_id = Column(Integer, ForeignKey("issue_types.issue_type_id"), nullable=True)
    room_area = Column(String(150), nullable=True)
    is_safety_hazard = Column(Boolean, default=False)
    description = Column(Text, nullable=False)
    resolution_note = Column(Text, nullable=True)
    image_id = Column(String(100), nullable=True)
    priority_id = Column(Integer, ForeignKey("priorities.priority_id"), default=2)
    status_id = Column(Integer, ForeignKey("ticket_status.status_id"), default=1)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)
    closed_at = Column(DateTime, nullable=True)

    employee = relationship("Employee")
    location = relationship("Location")
    category = relationship("Category")
    subcategory = relationship("Subcategory")
    issue_type = relationship("IssueType")
    priority = relationship("Priority")
    status = relationship("TicketStatus")

class MaintenanceTicketAssignment(Base):
    __tablename__ = "maintenance_ticket_assignments"
    assignment_id = Column(Integer, primary_key=True, autoincrement=True)
    ticket_id = Column(Integer, ForeignKey("maintenance_tickets.ticket_id"), nullable=False)
    admin_id = Column(Integer, ForeignKey("support_admins.admin_id"), nullable=False)
    assigned_at = Column(DateTime, default=datetime.datetime.utcnow)

    admin = relationship("SupportAdmin")
    ticket = relationship("MaintenanceTicket")

class ConversationState(Base):
    __tablename__ = "conversation_state"
    phone = Column(String(20), primary_key=True)
    flow_name = Column(String(50), default="raise_ticket")
    current_step = Column(String(50), nullable=False)
    current_data = Column(JSON, default=dict)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)

engine_kwargs = {"echo": False}
if "postgresql" in settings.database_url:
    engine_kwargs["connect_args"] = {
        "ssl": "require",
        "statement_cache_size": 0,
        "prepared_statement_cache_size": 0
    }

engine = create_async_engine(settings.database_url, **engine_kwargs)
async_session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with async_session_factory() as session:
        yield session

async def init_db_models():
    """Create all tables and insert seed data if empty."""
    global engine, async_session_factory
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
    except Exception as e:
        print(f"Failed to connect to primary DB ({e}). Falling back to local SQLite 'sqlite+aiosqlite:///./itsupport.db'...")
        engine = create_async_engine("sqlite+aiosqlite:///./itsupport.db", echo=False)
        async_session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            
    async with async_session_factory() as session:
        # Check Priorities
        res = await session.execute(select(Priority))
        if not res.scalars().all():
            priorities = [
                Priority(priority_id=1, priority_name="Low"),
                Priority(priority_id=2, priority_name="Medium"),
                Priority(priority_id=3, priority_name="High"),
                Priority(priority_id=4, priority_name="Urgent"),
            ]
            session.add_all(priorities)
        
        # Check Statuses
        res = await session.execute(select(TicketStatus))
        if not res.scalars().all():
            statuses = [
                TicketStatus(status_id=1, status_name="Open"),
                TicketStatus(status_id=2, status_name="In Progress"),
                TicketStatus(status_id=3, status_name="Resolved"),
                TicketStatus(status_id=4, status_name="Closed"),
            ]
            session.add_all(statuses)

        # Check Categories
        res = await session.execute(select(Category))
        if not res.scalars().all():
            cat1 = Category(category_id=1, category_name="Hardware & Devices")
            cat2 = Category(category_id=2, category_name="Software & Applications")
            cat3 = Category(category_id=3, category_name="Network & Connectivity")
            cat4 = Category(category_id=4, category_name="Account & Access Management")
            session.add_all([cat1, cat2, cat3, cat4])
            await session.flush()

            sub1 = Subcategory(subcategory_id=1, category_id=1, subcategory_name="Laptop / Desktop PC")
            sub2 = Subcategory(subcategory_id=2, category_id=1, subcategory_name="Printers & Scanners")
            sub3 = Subcategory(subcategory_id=3, category_id=1, subcategory_name="Peripherals (Monitor, Keyboard, Mouse)")
            
            sub4 = Subcategory(subcategory_id=4, category_id=2, subcategory_name="Email & Outlook")
            sub5 = Subcategory(subcategory_id=5, category_id=2, subcategory_name="Office Productivity Apps")
            sub6 = Subcategory(subcategory_id=6, category_id=2, subcategory_name="VPN & Security Software")
            
            sub7 = Subcategory(subcategory_id=7, category_id=3, subcategory_name="Wi-Fi & Wireless Network")
            sub8 = Subcategory(subcategory_id=8, category_id=3, subcategory_name="LAN / Internet Connection")
            
            sub9 = Subcategory(subcategory_id=9, category_id=4, subcategory_name="Password Reset")
            sub10 = Subcategory(subcategory_id=10, category_id=4, subcategory_name="Software Permission / Access")
            session.add_all([sub1, sub2, sub3, sub4, sub5, sub6, sub7, sub8, sub9, sub10])
            await session.flush()

            issues = [
                IssueType(subcategory_id=1, issue_name="Display / Screen damage or flickering"),
                IssueType(subcategory_id=1, issue_name="Battery charging / Power failure"),
                IssueType(subcategory_id=1, issue_name="System slow / BSOD crash"),
                IssueType(subcategory_id=2, issue_name="Printer offline or unreachable"),
                IssueType(subcategory_id=2, issue_name="Paper jam / Toner replacement"),
                IssueType(subcategory_id=3, issue_name="External monitor not displaying"),
                IssueType(subcategory_id=3, issue_name="Keyboard or Mouse non-responsive"),
                IssueType(subcategory_id=4, issue_name="Outlook unable to sync emails"),
                IssueType(subcategory_id=4, issue_name="Email send/receive error"),
                IssueType(subcategory_id=5, issue_name="MS Office license activation issue"),
                IssueType(subcategory_id=5, issue_name="Application freezing on launch"),
                IssueType(subcategory_id=6, issue_name="VPN connection drops constantly"),
                IssueType(subcategory_id=6, issue_name="Antivirus alert / blocking file"),
                IssueType(subcategory_id=7, issue_name="Cannot connect to Office Wi-Fi"),
                IssueType(subcategory_id=7, issue_name="Wi-Fi password prompt looping"),
                IssueType(subcategory_id=8, issue_name="Ethernet cable disconnected / No IP"),
                IssueType(subcategory_id=8, issue_name="Extremely slow web browsing"),
                IssueType(subcategory_id=9, issue_name="Active Directory Domain Password Reset"),
                IssueType(subcategory_id=9, issue_name="Corporate Email Password Reset"),
                IssueType(subcategory_id=10, issue_name="Request access to Shared Folder / Drive"),
                IssueType(subcategory_id=10, issue_name="Request access to ERP / CRM System"),
            ]
            session.add_all(issues)

        # Check Departments / Locations
        res = await session.execute(select(Department))
        if not res.scalars().all():
            session.add_all([Department(department_id=1, department_name="IT Support"), Department(department_id=2, department_name="Finance")])
        
        # Guarantee 7 Official Building Projects Site Locations are synced
        desired_locations = [
            "Tagoneswa Hardware",
            "LG Plast",
            "Shop 5",
            "Shop 6",
            "Kreckle Foods",
            "19 Mcloughlin Kensington",
            "12 Divine Milton Park"
        ]
        res = await session.execute(select(Location).order_by(Location.location_id))
        existing_locs = res.scalars().all()
        for idx, name in enumerate(desired_locations):
            if idx < len(existing_locs):
                existing_locs[idx].location_name = name
            else:
                session.add(Location(location_name=name))
        await session.flush()

        # Guarantee 4 Support Admins are synced in PostgreSQL database on startup
        admin_data = [
            {"name": "Fazal Saiyed (Master Admin)", "phone": "919265368695", "is_master": True},
            {"name": "Kevin Chikati", "phone": "263718627526", "is_master": False},
            {"name": "Ellias Murenga", "phone": "263788843579", "is_master": False},
            {"name": "Faisal Kassim", "phone": "263780100503", "is_master": False},
        ]

        for ad in admin_data:
            a_res = await session.execute(select(SupportAdmin).where(SupportAdmin.phone == ad["phone"]))
            existing_admin = a_res.scalars().first()
            if existing_admin:
                existing_admin.full_name = ad["name"]
                existing_admin.active = True
                existing_admin.is_master_admin = ad["is_master"]
            else:
                first_name = ad["name"].split()[0]
                a_name_res = await session.execute(select(SupportAdmin).where(SupportAdmin.full_name.ilike(f"%{first_name}%")))
                existing_by_name = a_name_res.scalars().first()
                if existing_by_name:
                    existing_by_name.phone = ad["phone"]
                    existing_by_name.active = True
                    existing_by_name.full_name = ad["name"]
                else:
                    session.add(SupportAdmin(
                        full_name=ad["name"],
                        phone=ad["phone"],
                        is_master_admin=ad["is_master"],
                        active=True
                    ))
        await session.commit()

        # Ensure Department "Sales" and Location "6 Austin Road Workington" exist
        dept_res = await session.execute(select(Department).where(Department.department_name.ilike("%Sales%")))
        sales_dept = dept_res.scalars().first()
        if not sales_dept:
            sales_dept = Department(department_name="Sales")
            session.add(sales_dept)
            await session.flush()

        loc_coventry_res = await session.execute(select(Location).where(Location.location_name.ilike("%110 Coventry Road%")))
        coventry_loc = loc_coventry_res.scalars().first()

        loc_austin_res = await session.execute(select(Location).where(Location.location_name.ilike("%6 Austin Road%")))
        austin_loc = loc_austin_res.scalars().first()

        # Update or Insert Patience Ndlovu
        p_res = await session.execute(select(Employee).where(Employee.phone == "263780806954"))
        patience = p_res.scalars().first()
        if patience:
            patience.full_name = "Patience Ndlovu"
            patience.department_id = sales_dept.department_id
            if austin_loc: patience.location_id = austin_loc.location_id
            patience.active = True
        else:
            session.add(Employee(
                employee_code="EMP_PATIENCE",
                full_name="Patience Ndlovu",
                phone="263780806954",
                department_id=sales_dept.department_id,
                location_id=austin_loc.location_id if austin_loc else None,
                active=True
            ))

        # Sync location mappings for registered Austin Road employees
        austin_phones = {
            "263776477481", "263711421202", "263784077420", "263781343668", "263714282265",
            "263774522586", "263774308083", "263778861934", "263788500565", "263780099335",
            "263785322640", "263780216289", "263788071001", "263780573092", "263780543771",
            "263780100545", "263780100288", "263787348969", "263780806954"
        }
        if austin_loc:
            for p_num in austin_phones:
                emp_obj = (await session.execute(select(Employee).where(Employee.phone == p_num))).scalars().first()
                if emp_obj:
                    emp_obj.location_id = austin_loc.location_id

        if coventry_loc:
            # Map remaining employees to Coventry Road
            all_emps = (await session.execute(select(Employee))).scalars().all()
            for emp in all_emps:
                if emp.phone not in austin_phones and (emp.location_id is None or emp.location_id in [1, 2, 3]):
                    emp.location_id = coventry_loc.location_id

        # Guarantee Projects Support Admins (Stanclea & Omar Arizai) are synced with correct phone numbers
        maint_admins_data = [
            {"name": "Stanclea", "phone": "263780099291"},
            {"name": "Omar Arizai", "phone": "263771333602"}
        ]
        for ma in maint_admins_data:
            m_res = await session.execute(select(SupportAdmin).where((SupportAdmin.phone == ma["phone"]) | (SupportAdmin.full_name.ilike(f"%{ma['name']}%"))))
            m_adm = m_res.scalars().first()
            if m_adm:
                m_adm.full_name = ma["name"]
                m_adm.phone = ma["phone"]
                m_adm.is_maintenance_admin = True
                m_adm.active = True
            else:
                session.add(SupportAdmin(
                    full_name=ma["name"],
                    phone=ma["phone"],
                    is_master_admin=False,
                    is_maintenance_admin=True,
                    active=True
                ))

        # Guarantee Authorized Building Projects Reporters are synced
        maint_reporters_data = [
            {"name": "Fazal Saiyed", "phone": "919265368695"},
            {"name": "Arif", "phone": "263732786786"},
            {"name": "Zayn", "phone": "263713866223"},
            {"name": "Faizan Patel", "phone": "263778405964"},
            {"name": "Paidamoyo Mapeka", "phone": "263712127593"},
            {"name": "Soyab Patel", "phone": "263784077420"},
            {"name": "Batsirai Muradzikwa", "phone": "263711421202"},
            {"name": "Simbarashe Chaunoita", "phone": "263785571584"},
            {"name": "Stanclea", "phone": "263780099291"},
            {"name": "Omar Arizai", "phone": "263771333602"},
        ]
        for rep in maint_reporters_data:
            r_phone = rep["phone"]
            r_name = rep["name"]
            e_res = await session.execute(select(Employee).where(Employee.phone == r_phone))
            emp = e_res.scalars().first()
            if emp:
                emp.is_maintenance_reporter = True
                emp.active = True
            else:
                session.add(Employee(
                    employee_code=f"EMP_MNT_{r_phone[-4:]}",
                    full_name=r_name,
                    phone=r_phone,
                    is_maintenance_reporter=True,
                    active=True
                ))

        # Explicitly remove Kevin Chikati from maintenance reporters
        k_res = await session.execute(select(Employee).where(Employee.phone == "263718627526"))
        kevin = k_res.scalars().first()
        if kevin:
            kevin.is_maintenance_reporter = False

        await session.commit()

        # Clean up legacy / incorrect AdminCategoryMapping rows
        await session.execute(delete(AdminCategoryMapping))
        await session.commit()

        # Sync Maintenance / Building Projects Categories (including Renovation & Expansion) on startup
        try:
            from seed_maintenance_data import seed_maintenance_data_in_session
            await seed_maintenance_data_in_session(session)
        except Exception as m_err:
            import logging
            logging.getLogger("database").warning(f"Maintenance categories init note: {m_err}")

        # Sync Workshop Taxonomy and Real Tagoneswa Fleet on startup
        try:
            from seed_workshop_data import seed_workshop_data_in_session
            await seed_workshop_data_in_session(session)
        except Exception as ws_err:
            import logging
            logging.getLogger("database").warning(f"Workshop tables init note: {ws_err}")

    # Sync all PostgreSQL sequences and ensure columns exist to prevent runtime errors
    async with engine.begin() as conn:
        from sqlalchemy import text
        col_queries = [
            "ALTER TABLE tickets ADD COLUMN IF NOT EXISTS location_id INTEGER REFERENCES locations(location_id);",
            "ALTER TABLE maintenance_tickets ADD COLUMN IF NOT EXISTS location_id INTEGER REFERENCES locations(location_id);"
        ]
        for cq in col_queries:
            try:
                await conn.execute(text(cq))
            except Exception:
                pass

        seq_queries = [
            "SELECT setval('maintenance_ticket_assignments_assignment_id_seq', COALESCE((SELECT MAX(assignment_id) FROM maintenance_ticket_assignments), 0) + 1, false);",
            "SELECT setval('maintenance_tickets_ticket_id_seq', COALESCE((SELECT MAX(ticket_id) FROM maintenance_tickets), 0) + 1, false);",
            "SELECT setval('ticket_assignments_assignment_id_seq', COALESCE((SELECT MAX(assignment_id) FROM ticket_assignments), 0) + 1, false);",
            "SELECT setval('tickets_ticket_id_seq', COALESCE((SELECT MAX(ticket_id) FROM tickets), 0) + 1, false);",
            "SELECT setval('support_admins_admin_id_seq', COALESCE((SELECT MAX(admin_id) FROM support_admins), 0) + 1, false);",
            "SELECT setval('employees_employee_id_seq', COALESCE((SELECT MAX(employee_id) FROM employees), 0) + 1, false);"
        ]
        for q in seq_queries:
            try:
                await conn.execute(text(q))
            except Exception:
                pass
