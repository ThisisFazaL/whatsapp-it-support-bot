import datetime
import json
from typing import AsyncGenerator
from sqlalchemy import (
    Column, Integer, String, Text, Boolean, DateTime, ForeignKey, JSON
)
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base, relationship, selectinload
from sqlalchemy import select, func

from app.config import settings

Base = declarative_base()

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
    active = Column(Boolean, default=True)

    department = relationship("Department")
    location = relationship("Location")

class SupportAdmin(Base):
    __tablename__ = "support_admins"
    admin_id = Column(Integer, primary_key=True, autoincrement=True)
    full_name = Column(String(100), nullable=False)
    phone = Column(String(20), unique=True, nullable=False)
    is_master_admin = Column(Boolean, default=False)
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
    category_id = Column(Integer, ForeignKey("categories.category_id"), nullable=True)
    subcategory_id = Column(Integer, ForeignKey("subcategories.subcategory_id"), nullable=True)
    issue_type_id = Column(Integer, ForeignKey("issue_types.issue_type_id"), nullable=True)
    description = Column(Text, nullable=False)
    image_id = Column(String(100), nullable=True) # Optional Meta image attachment ID
    priority_id = Column(Integer, ForeignKey("priorities.priority_id"), default=2)
    status_id = Column(Integer, ForeignKey("ticket_status.status_id"), default=1)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)
    closed_at = Column(DateTime, nullable=True)

    employee = relationship("Employee")
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
        
        res = await session.execute(select(Location))
        if not res.scalars().all():
            session.add_all([Location(location_id=1, location_name="Headquarters - Floor 3"), Location(location_id=2, location_name="Branch Office")])

        # Check Support Admins
        res = await session.execute(select(SupportAdmin))
        if not res.scalars().all():
            master_admin = SupportAdmin(admin_id=1, full_name="Fazal (Master Admin)", phone="919265368695", is_master_admin=True, active=True)
            hw_admin = SupportAdmin(admin_id=2, full_name="Alex Rivera (Hardware Admin)", phone="919876543210", is_master_admin=False, active=True)
            sw_admin = SupportAdmin(admin_id=3, full_name="Sarah Jenkins (Software Admin)", phone="15556729057", is_master_admin=False, active=True)
            session.add_all([master_admin, hw_admin, sw_admin])
            await session.flush()

            # Mappings: Alex -> Hardware (1), Sarah -> Software (2)
            session.add_all([
                AdminCategoryMapping(admin_id=2, category_id=1),
                AdminCategoryMapping(admin_id=3, category_id=2),
                AdminCategoryMapping(admin_id=1, category_id=1),
                AdminCategoryMapping(admin_id=1, category_id=2),
                AdminCategoryMapping(admin_id=1, category_id=3),
                AdminCategoryMapping(admin_id=1, category_id=4),
            ])

        # Check Employees
        res = await session.execute(select(Employee))
        if not res.scalars().all():
            emps = [
                Employee(employee_id=1, employee_code="EMP1001", full_name="John Doe", phone="919876543210", email="john.doe@company.com", department_id=2, location_id=1, active=True),
                Employee(employee_id=2, employee_code="EMP1002", full_name="Jane Smith", phone="15556729057", email="jane.smith@company.com", department_id=1, location_id=1, active=True),
                Employee(employee_id=3, employee_code="EMP1003", full_name="Robert Johnson", phone="919876543211", email="robert.j@company.com", department_id=2, location_id=2, active=True),
                Employee(employee_id=4, employee_code="EMP1004", full_name="Fazal Saiyed", phone="919265368695", email="fazal@company.com", department_id=1, location_id=1, active=True),
            ]
            session.add_all(emps)

        await session.commit()
