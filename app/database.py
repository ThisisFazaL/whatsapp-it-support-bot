import datetime
import json
from typing import AsyncGenerator, Optional, List, Dict, Any
from sqlalchemy import (
    Column, Integer, String, Text, Boolean, DateTime, ForeignKey, JSON, Float
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

class FleetTripApproval(Base):
    __tablename__ = "fleet_trip_approvals"
    id = Column(Integer, primary_key=True, autoincrement=True)
    trip_id = Column(String(100), nullable=False, index=True)
    salesperson_phone = Column(String(30), nullable=False, index=True)
    salesperson_name = Column(String(100), nullable=True)
    destination_city = Column(String(100), nullable=False)
    route = Column(String(100), nullable=True)
    trip_sales_value = Column(Float, nullable=False, default=0.0)
    required_minimum = Column(Float, nullable=False, default=0.0)
    shortfall = Column(Float, nullable=False, default=0.0)
    transport_charge = Column(Float, nullable=False, default=0.0)
    amount_charged_to_customer = Column(Float, nullable=False, default=0.0)
    pending_balance_recorded = Column(Float, nullable=False, default=0.0)
    dispatch_option = Column(String(50), nullable=True)
    has_shortfall = Column(Boolean, default=False)
    status = Column(String(50), default="SHORTFALL_RECORDED")  # "SHORTFALL_RECORDED", "APPROVED", "DISPATCHED"
    raw_data = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

class FleetPendingLedger(Base):
    __tablename__ = "fleet_pending_ledger"
    id = Column(Integer, primary_key=True, autoincrement=True)
    salesperson_phone = Column(String(30), nullable=False, index=True)
    salesperson_name = Column(String(100), nullable=True)
    trip_id = Column(String(100), nullable=True, index=True)
    entry_type = Column(String(50), nullable=False)  # "SHORTFALL_PARTIAL_BALANCE", "SHORTFALL_FULL_UNCHARGED", "RECOVERY_SURPLUS"
    amount = Column(Float, nullable=False, default=0.0)  # Positive = pending deficit, Negative = surplus recovered
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

class FleetTripRequest(Base):
    __tablename__ = "fleet_trip_requests"
    id = Column(Integer, primary_key=True, autoincrement=True)
    trip_id = Column(String(100), unique=True, nullable=False, index=True)
    company_name = Column(String(100), nullable=False)  # "A. TG Hardware", "B. LG Plast", "C. Kreckle"
    sales_admin_phone = Column(String(30), nullable=True, index=True)
    salesperson_phone = Column(String(30), nullable=False, index=True)
    salesperson_name = Column(String(100), nullable=True)
    destination_city = Column(String(100), nullable=False)
    route = Column(String(100), nullable=True)
    trip_sales_value = Column(Float, nullable=False, default=0.0)  # Confidential from operational staff
    transport_charge = Column(Float, nullable=False, default=0.0)
    
    # Edward Assignment
    truck_plate = Column(String(50), nullable=True, index=True)
    driver_name = Column(String(100), nullable=True)
    driver_phone = Column(String(30), nullable=True, index=True)
    crew_count = Column(Integer, nullable=False, default=2)
    meal_count = Column(Integer, nullable=False, default=3)
    toll_gates_count = Column(Integer, nullable=False, default=0)
    toll_cost = Column(Float, nullable=False, default=0.0)
    food_allowance = Column(Float, nullable=False, default=0.0)
    total_allowance = Column(Float, nullable=False, default=0.0)
    
    # Zayn & Accounts
    allowance_status = Column(String(50), default="PENDING_APPROVAL")  # PENDING_APPROVAL, APPROVED, TRANSFERRED
    allowance_approved_by = Column(String(100), nullable=True)
    departure_time = Column(String(20), nullable=True)
    return_time = Column(String(20), nullable=True)
    night_count = Column(Integer, nullable=False, default=0)
    accommodation_allowance = Column(Float, nullable=False, default=0.0)
    recalculate_note = Column(Text, nullable=True)
    
    # Driver Transit & Return
    status = Column(String(50), default="CREATED", index=True)
    # CREATED -> PENDING_ASSIGNMENT -> ASSIGNED -> ALLOWANCE_APPROVED -> TRANSFERRED -> ACTIVE -> RETURNING -> RETURNED -> BALANCED -> CLOSED
    is_live_location_active = Column(Boolean, default=False)
    last_latitude = Column(Float, nullable=True)
    last_longitude = Column(Float, nullable=True)
    last_location_time = Column(DateTime, nullable=True)
    start_odometer = Column(Float, nullable=True)
    end_odometer = Column(Float, nullable=True)
    distance_km = Column(Float, nullable=True)
    departed_at = Column(DateTime, nullable=True)
    returning_at = Column(DateTime, nullable=True)
    returned_at = Column(DateTime, nullable=True)
    closed_at = Column(DateTime, nullable=True)
    
    # Balancing & Adjudication
    discrepancy_amount = Column(Float, nullable=False, default=0.0)
    discrepancy_reason = Column(Text, nullable=True)
    reimbursement_status = Column(String(50), default="NONE")  # NONE, PENDING, APPROVED, REJECTED
    
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)

class FleetCustomerSchedule(Base):
    __tablename__ = "fleet_customer_schedules"
    id = Column(Integer, primary_key=True, autoincrement=True)
    trip_id = Column(String(100), nullable=False, index=True)
    customer_id = Column(String(100), nullable=False, index=True)
    expected_charge = Column(Float, nullable=False, default=0.0)
    collected_charge = Column(Float, nullable=False, default=0.0)
    payment_method = Column(String(50), default="CASH")  # CASH, BANK_ECOCASH, UNPAID
    reference_note = Column(String(255), nullable=True)
    status = Column(String(50), default="PENDING")  # PENDING, MATCHED, VARIANCE
    variance = Column(Float, nullable=False, default=0.0)
    recorded_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

class FleetEmergencyExpense(Base):
    __tablename__ = "fleet_emergency_expenses"
    id = Column(Integer, primary_key=True, autoincrement=True)
    trip_id = Column(String(100), nullable=False, index=True)
    driver_phone = Column(String(30), nullable=False, index=True)
    charge_type = Column(String(50), nullable=False)  # EMERGENCY_FUEL, OTHER
    amount = Column(Float, nullable=False, default=0.0)
    description = Column(Text, nullable=True)
    has_video_evidence = Column(Boolean, default=False)
    status = Column(String(50), default="PENDING")  # PENDING, APPROVED, REJECTED
    approved_by = Column(String(100), nullable=True)
    verified_in_balancing = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

class DriverPendingLedger(Base):
    __tablename__ = "driver_pending_ledger"
    id = Column(Integer, primary_key=True, autoincrement=True)
    driver_phone = Column(String(30), nullable=False, index=True)
    driver_name = Column(String(100), nullable=True)
    trip_id = Column(String(100), nullable=True, index=True)
    amount = Column(Float, nullable=False, default=0.0)
    reason = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

class IncomingWebhookLog(Base):
    __tablename__ = "incoming_webhook_logs"
    id = Column(Integer, primary_key=True, autoincrement=True)
    sender_phone = Column(String(50), nullable=True, index=True)
    message_type = Column(String(50), nullable=True)
    message_text = Column(Text, nullable=True)
    raw_payload = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

class Product(Base):
    __tablename__ = "products"
    product_id = Column(Integer, primary_key=True, autoincrement=True)
    product_code = Column(String(50), unique=True, nullable=True)
    product_name = Column(String(150), nullable=False, index=True)
    category = Column(String(100), nullable=False) # "Conduit Pipes", "Conduit Fittings", etc.
    size_spec = Column(String(50), nullable=True)  # "20mm", "25mm", "32mm"
    unit_of_measure = Column(String(20), default="pcs")
    standard_price = Column(Float, nullable=True)
    active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

class ProductRequirement(Base):
    __tablename__ = "product_requirements"
    requirement_id = Column(Integer, primary_key=True, autoincrement=True)
    requirement_number = Column(String(30), unique=True, nullable=False) # REQ-YYYYMMDD-XXXXX
    salesperson_id = Column(Integer, ForeignKey("employees.employee_id"), nullable=False)
    customer_name = Column(String(150), nullable=False) # Customer / Shop Name
    customer_phone = Column(String(50), nullable=True)
    requirement_type = Column(String(30), nullable=False) # "EXISTING_UNAVAILABLE" or "NEW_PRODUCT"
    
    product_id = Column(Integer, ForeignKey("products.product_id"), nullable=True)
    product_name = Column(String(150), nullable=False)
    product_category = Column(String(100), nullable=True)
    
    required_quantity = Column(Integer, nullable=True)
    monthly_demand = Column(Integer, nullable=True)
    customer_urgency = Column(String(50), nullable=True) # "Ready to purchase", "Exploring options", etc.
    
    competitor_supplier = Column(String(150), nullable=True)
    current_market_price = Column(Float, nullable=True)
    comments = Column(Text, nullable=True)
    
    image_id = Column(String(100), nullable=True)
    status = Column(String(50), default="Pending Review") # Pending Review, Under Evaluation, Approved, Rejected, Production Planning, Available, Closed
    management_notes = Column(Text, nullable=True)
    
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)

    salesperson = relationship("Employee")
    product = relationship("Product")

class AdminNotificationLog(Base):
    __tablename__ = "admin_notification_logs"
    id = Column(Integer, primary_key=True, autoincrement=True)
    admin_phone = Column(String(30), index=True, nullable=False)
    ticket_number = Column(String(50), index=True, nullable=False)
    delivered_at = Column(DateTime, default=datetime.datetime.utcnow)

engine_kwargs = {
    "echo": False,
    "pool_pre_ping": True,
    "pool_recycle": 1800,
}
if "postgresql" in settings.database_url:
    engine_kwargs["pool_size"] = 10
    engine_kwargs["max_overflow"] = 10
    engine_kwargs["pool_timeout"] = 30
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
    if "sqlite" in settings.database_url:
        try:
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
        except Exception as e:
            print(f"Schema verification note: {e}")
    else:
        try:
            from sqlalchemy import text
            async with engine.begin() as conn:
                await conn.execute(text("""
                    CREATE TABLE IF NOT EXISTS fleet_trip_approvals (
                        id SERIAL PRIMARY KEY,
                        trip_id VARCHAR(100) NOT NULL,
                        salesperson_phone VARCHAR(30) NOT NULL,
                        salesperson_name VARCHAR(100),
                        destination_city VARCHAR(100) NOT NULL,
                        route VARCHAR(100),
                        trip_sales_value DOUBLE PRECISION DEFAULT 0.0,
                        required_minimum DOUBLE PRECISION DEFAULT 0.0,
                        shortfall DOUBLE PRECISION DEFAULT 0.0,
                        transport_charge DOUBLE PRECISION DEFAULT 0.0,
                        amount_charged_to_customer DOUBLE PRECISION DEFAULT 0.0,
                        pending_balance_recorded DOUBLE PRECISION DEFAULT 0.0,
                        dispatch_option VARCHAR(50),
                        has_shortfall BOOLEAN DEFAULT FALSE,
                        status VARCHAR(50) DEFAULT 'SHORTFALL_RECORDED',
                        raw_data JSONB,
                        created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT (NOW() AT TIME ZONE 'utc')
                    )
                """))
                await conn.execute(text("CREATE INDEX IF NOT EXISTS idx_fleet_trip_id ON fleet_trip_approvals(trip_id)"))
                await conn.execute(text("CREATE INDEX IF NOT EXISTS idx_fleet_sales_phone ON fleet_trip_approvals(salesperson_phone)"))
                await conn.execute(text("ALTER TABLE fleet_trip_approvals ADD COLUMN IF NOT EXISTS amount_charged_to_customer DOUBLE PRECISION DEFAULT 0.0"))
                await conn.execute(text("ALTER TABLE fleet_trip_approvals ADD COLUMN IF NOT EXISTS pending_balance_recorded DOUBLE PRECISION DEFAULT 0.0"))
                await conn.execute(text("ALTER TABLE fleet_trip_approvals ADD COLUMN IF NOT EXISTS dispatch_option VARCHAR(50)"))

                await conn.execute(text("""
                    CREATE TABLE IF NOT EXISTS fleet_pending_ledger (
                        id SERIAL PRIMARY KEY,
                        salesperson_phone VARCHAR(30) NOT NULL,
                        salesperson_name VARCHAR(100),
                        trip_id VARCHAR(100),
                        entry_type VARCHAR(50) NOT NULL,
                        amount DOUBLE PRECISION NOT NULL DEFAULT 0.0,
                        notes TEXT,
                        created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT (NOW() AT TIME ZONE 'utc')
                    )
                """))
                await conn.execute(text("CREATE INDEX IF NOT EXISTS idx_fpl_sales_phone ON fleet_pending_ledger(salesperson_phone)"))
                await conn.execute(text("CREATE INDEX IF NOT EXISTS idx_fpl_trip_id ON fleet_pending_ledger(trip_id)"))

                await conn.execute(text("""
                    CREATE TABLE IF NOT EXISTS admin_notification_logs (
                        id SERIAL PRIMARY KEY,
                        admin_phone VARCHAR(30) NOT NULL,
                        ticket_number VARCHAR(50) NOT NULL,
                        delivered_at TIMESTAMP WITHOUT TIME ZONE DEFAULT (NOW() AT TIME ZONE 'utc')
                    )
                """))
                await conn.execute(text("CREATE INDEX IF NOT EXISTS idx_anl_phone ON admin_notification_logs(admin_phone)"))
                await conn.execute(text("CREATE INDEX IF NOT EXISTS idx_anl_ticket ON admin_notification_logs(ticket_number)"))

                await conn.execute(text("""
                    CREATE TABLE IF NOT EXISTS incoming_webhook_logs (
                        id SERIAL PRIMARY KEY,
                        sender_phone VARCHAR(50),
                        message_type VARCHAR(50),
                        message_text TEXT,
                        raw_payload JSONB,
                        created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT (NOW() AT TIME ZONE 'utc')
                    )
                """))
                await conn.execute(text("CREATE INDEX IF NOT EXISTS idx_iwl_phone ON incoming_webhook_logs(sender_phone)"))

                await conn.execute(text("""
                    CREATE TABLE IF NOT EXISTS products (
                        product_id SERIAL PRIMARY KEY,
                        product_code VARCHAR(50) UNIQUE,
                        product_name VARCHAR(150) NOT NULL,
                        category VARCHAR(100) NOT NULL,
                        size_spec VARCHAR(50),
                        unit_of_measure VARCHAR(20) DEFAULT 'pcs',
                        standard_price DOUBLE PRECISION,
                        active BOOLEAN DEFAULT TRUE,
                        created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT (NOW() AT TIME ZONE 'utc')
                    )
                """))
                await conn.execute(text("CREATE INDEX IF NOT EXISTS idx_prod_name ON products(product_name)"))

                await conn.execute(text("""
                    CREATE TABLE IF NOT EXISTS product_requirements (
                        requirement_id SERIAL PRIMARY KEY,
                        requirement_number VARCHAR(30) UNIQUE NOT NULL,
                        salesperson_id INTEGER REFERENCES employees(employee_id),
                        customer_name VARCHAR(150) NOT NULL,
                        customer_phone VARCHAR(50),
                        requirement_type VARCHAR(30) NOT NULL,
                        product_id INTEGER REFERENCES products(product_id),
                        product_name VARCHAR(150) NOT NULL,
                        product_category VARCHAR(100),
                        required_quantity INTEGER,
                        monthly_demand INTEGER,
                        customer_urgency VARCHAR(50),
                        competitor_supplier VARCHAR(150),
                        current_market_price DOUBLE PRECISION,
                        comments TEXT,
                        image_id VARCHAR(100),
                        status VARCHAR(50) DEFAULT 'Pending Review',
                        management_notes TEXT,
                        created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT (NOW() AT TIME ZONE 'utc'),
                        updated_at TIMESTAMP WITHOUT TIME ZONE DEFAULT (NOW() AT TIME ZONE 'utc')
                    )
                """))

                await conn.execute(text("""
                    CREATE TABLE IF NOT EXISTS fleet_trip_requests (
                        id SERIAL PRIMARY KEY,
                        trip_id VARCHAR(100) UNIQUE NOT NULL,
                        company_name VARCHAR(100) NOT NULL,
                        sales_admin_phone VARCHAR(30),
                        salesperson_phone VARCHAR(30) NOT NULL,
                        salesperson_name VARCHAR(100),
                        destination_city VARCHAR(100) NOT NULL,
                        route VARCHAR(100),
                        trip_sales_value DOUBLE PRECISION DEFAULT 0.0,
                        transport_charge DOUBLE PRECISION DEFAULT 0.0,
                        truck_plate VARCHAR(50),
                        driver_name VARCHAR(100),
                        driver_phone VARCHAR(30),
                        crew_count INTEGER DEFAULT 2,
                        meal_count INTEGER DEFAULT 3,
                        toll_gates_count INTEGER DEFAULT 0,
                        toll_cost DOUBLE PRECISION DEFAULT 0.0,
                        food_allowance DOUBLE PRECISION DEFAULT 0.0,
                        total_allowance DOUBLE PRECISION DEFAULT 0.0,
                        allowance_status VARCHAR(50) DEFAULT 'PENDING_APPROVAL',
                        allowance_approved_by VARCHAR(100),
                        departure_time VARCHAR(20),
                        status VARCHAR(50) DEFAULT 'CREATED',
                        is_live_location_active BOOLEAN DEFAULT FALSE,
                        departed_at TIMESTAMP WITHOUT TIME ZONE,
                        returning_at TIMESTAMP WITHOUT TIME ZONE,
                        returned_at TIMESTAMP WITHOUT TIME ZONE,
                        closed_at TIMESTAMP WITHOUT TIME ZONE,
                        discrepancy_amount DOUBLE PRECISION DEFAULT 0.0,
                        discrepancy_reason TEXT,
                        reimbursement_status VARCHAR(50) DEFAULT 'NONE',
                        created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT (NOW() AT TIME ZONE 'utc'),
                        updated_at TIMESTAMP WITHOUT TIME ZONE DEFAULT (NOW() AT TIME ZONE 'utc')
                    )
                """))
                await conn.execute(text("CREATE INDEX IF NOT EXISTS idx_ftr_trip_id ON fleet_trip_requests(trip_id)"))
                await conn.execute(text("CREATE INDEX IF NOT EXISTS idx_ftr_driver_phone ON fleet_trip_requests(driver_phone)"))
                await conn.execute(text("CREATE INDEX IF NOT EXISTS idx_ftr_status ON fleet_trip_requests(status)"))

                await conn.execute(text("""
                    CREATE TABLE IF NOT EXISTS fleet_customer_schedules (
                        id SERIAL PRIMARY KEY,
                        trip_id VARCHAR(100) NOT NULL,
                        customer_id VARCHAR(100) NOT NULL,
                        expected_charge DOUBLE PRECISION DEFAULT 0.0,
                        collected_charge DOUBLE PRECISION DEFAULT 0.0,
                        payment_method VARCHAR(50) DEFAULT 'CASH',
                        reference_note VARCHAR(255),
                        status VARCHAR(50) DEFAULT 'PENDING',
                        variance DOUBLE PRECISION DEFAULT 0.0,
                        recorded_at TIMESTAMP WITHOUT TIME ZONE,
                        created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT (NOW() AT TIME ZONE 'utc')
                    )
                """))
                await conn.execute(text("CREATE INDEX IF NOT EXISTS idx_fcs_trip_id ON fleet_customer_schedules(trip_id)"))
                await conn.execute(text("CREATE INDEX IF NOT EXISTS idx_fcs_cust_id ON fleet_customer_schedules(customer_id)"))

                await conn.execute(text("""
                    CREATE TABLE IF NOT EXISTS fleet_emergency_expenses (
                        id SERIAL PRIMARY KEY,
                        trip_id VARCHAR(100) NOT NULL,
                        driver_phone VARCHAR(30) NOT NULL,
                        charge_type VARCHAR(50) NOT NULL,
                        amount DOUBLE PRECISION DEFAULT 0.0,
                        description TEXT,
                        has_video_evidence BOOLEAN DEFAULT FALSE,
                        verified_in_balancing BOOLEAN DEFAULT FALSE,
                        created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT (NOW() AT TIME ZONE 'utc')
                    )
                """))
                await conn.execute(text("CREATE INDEX IF NOT EXISTS idx_fee_trip_id ON fleet_emergency_expenses(trip_id)"))
                await conn.execute(text("CREATE INDEX IF NOT EXISTS idx_fee_driver_phone ON fleet_emergency_expenses(driver_phone)"))

                await conn.execute(text("""
                    CREATE TABLE IF NOT EXISTS driver_pending_ledger (
                        id SERIAL PRIMARY KEY,
                        driver_phone VARCHAR(30) NOT NULL,
                        driver_name VARCHAR(100),
                        trip_id VARCHAR(100),
                        amount DOUBLE PRECISION DEFAULT 0.0,
                        reason TEXT,
                        created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT (NOW() AT TIME ZONE 'utc')
                    )
                """))
                await conn.execute(text("CREATE INDEX IF NOT EXISTS idx_dpl_driver_phone ON driver_pending_ledger(driver_phone)"))
        except Exception as e:
            print(f"Database table init note: {e}")
            
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

        # Guarantee Support Admins are synced in PostgreSQL database on startup
        admin_data = [
            {"name": "Fazal Saiyed (Master Admin)", "phone": "919265368695", "is_master": True},
            {"name": "Sujit Patel (Admin)", "phone": "263718352518", "is_master": True},
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

        # Sync location mappings for registered Austin Road employees (batched)
        austin_phones = [
            "263776477481", "263711421202", "263784077420", "263781343668", "263714282265",
            "263774522586", "263774308083", "263778861934", "263788500565", "263780099335",
            "263785322640", "263780216289", "263788071001", "263780573092", "263780543771",
            "263780100545", "263780100288", "263787348969", "263780806954"
        ]
        if austin_loc:
            austin_emps = (await session.execute(
                select(Employee).where(Employee.phone.in_(austin_phones), Employee.location_id != austin_loc.location_id)
            )).scalars().all()
            for emp in austin_emps:
                emp.location_id = austin_loc.location_id

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

        # Guarantee Authorized Building Projects Reporters are synced in single batch
        maint_reporters_data = [
            {"name": "Fazal Saiyed", "phone": "919265368695"},
            {"name": "Arif", "phone": "263732786786"},
            {"name": "Zayn", "phone": "263713866223"},
            {"name": "Faizan Patel", "phone": "263778405964"},
            {"name": "Paidamoyo Mapeka", "phone": "263712127593"},
            {"name": "Soyab Patel", "phone": "263784077420"},
            {"name": "Batsirai Muradzikwa", "phone": "263711421202"},
            {"name": "Simbarashe Chaunoita", "phone": "263785571584"},
            {"name": "Faruk Patel", "phone": "263780515663"},
            {"name": "Stanclea", "phone": "263780099291"},
            {"name": "Omar Arizai", "phone": "263771333602"},
        ]
        reps_by_phone = {rep["phone"]: rep["name"] for rep in maint_reporters_data}
        existing_reps = (await session.execute(
            select(Employee).where(Employee.phone.in_(list(reps_by_phone.keys())))
        )).scalars().all()
        found_phones = set()
        for emp in existing_reps:
            found_phones.add(emp.phone)
            emp.is_maintenance_reporter = True
            emp.active = True
        for r_phone, r_name in reps_by_phone.items():
            if r_phone not in found_phones:
                session.add(Employee(
                    employee_code=f"EMP_MNT_{r_phone[-4:]}",
                    full_name=r_name,
                    phone=r_phone,
                    is_maintenance_reporter=True,
                    active=True
                ))

        # Explicitly remove Kevin Chikati from maintenance reporters
        kevin = (await session.execute(select(Employee).where(Employee.phone == "263718627526"))).scalars().first()
        if kevin:
            kevin.is_maintenance_reporter = False

        await session.commit()

        # Clean up legacy / incorrect AdminCategoryMapping rows if any exist
        has_mappings = (await session.execute(select(AdminCategoryMapping.mapping_id).limit(1))).scalars().first()
        if has_mappings:
            await session.execute(delete(AdminCategoryMapping))
            await session.commit()

        # Sync Maintenance / Building Projects Categories (only if not seeded)
        try:
            from seed_maintenance_data import seed_maintenance_data_in_session
            m_chk = await session.execute(select(Category).where(Category.domain.ilike("MAINTENANCE")))
            if not m_chk.scalars().first():
                await seed_maintenance_data_in_session(session)
        except Exception as m_err:
            import logging
            logging.getLogger("database").warning(f"Maintenance categories init note: {m_err}")

        # Sync Workshop Taxonomy and Real Tagoneswa Fleet on startup (only if empty)
        try:
            from app.workshop.models import WorkshopTruck
            from seed_workshop_data import seed_workshop_data_in_session
            wt_chk = await session.execute(select(WorkshopTruck))
            if not wt_chk.scalars().first():
                await seed_workshop_data_in_session(session)
        except Exception as ws_err:
            import logging
            logging.getLogger("database").warning(f"Workshop tables init note: {ws_err}")

        # Seed Products catalog if empty
        try:
            prod_chk = await session.execute(select(Product))
            if not prod_chk.scalars().first():
                default_products = [
                    Product(product_code="CND-20L", product_name="20mm PVC Conduit Pipe (Light Duty)", category="Conduit Pipes", size_spec="20mm", unit_of_measure="pcs"),
                    Product(product_code="CND-20H", product_name="20mm PVC Conduit Pipe (Heavy Duty)", category="Conduit Pipes", size_spec="20mm", unit_of_measure="pcs"),
                    Product(product_code="CND-25L", product_name="25mm PVC Conduit Pipe (Light Duty)", category="Conduit Pipes", size_spec="25mm", unit_of_measure="pcs"),
                    Product(product_code="CND-25H", product_name="25mm PVC Conduit Pipe (Heavy Duty)", category="Conduit Pipes", size_spec="25mm", unit_of_measure="pcs"),
                    Product(product_code="CND-32H", product_name="32mm PVC Conduit Pipe (Heavy Duty)", category="Conduit Pipes", size_spec="32mm", unit_of_measure="pcs"),
                    Product(product_code="FIT-ELB-20", product_name="20mm PVC Conduit Elbow", category="Conduit Fittings", size_spec="20mm", unit_of_measure="pcs"),
                    Product(product_code="FIT-ELB-25", product_name="25mm PVC Conduit Elbow", category="Conduit Fittings", size_spec="25mm", unit_of_measure="pcs"),
                    Product(product_code="FIT-ELB-32", product_name="32mm PVC Conduit Elbow", category="Conduit Fittings", size_spec="32mm", unit_of_measure="pcs"),
                    Product(product_code="FIT-BND-20", product_name="20mm PVC Conduit Bend", category="Conduit Fittings", size_spec="20mm", unit_of_measure="pcs"),
                    Product(product_code="FIT-BND-25", product_name="25mm PVC Conduit Bend", category="Conduit Fittings", size_spec="25mm", unit_of_measure="pcs"),
                    Product(product_code="FIT-BND-32", product_name="32mm PVC Conduit Bend", category="Conduit Fittings", size_spec="32mm", unit_of_measure="pcs"),
                    Product(product_code="FIT-CPL-20", product_name="20mm PVC Conduit Coupling", category="Conduit Fittings", size_spec="20mm", unit_of_measure="pcs"),
                    Product(product_code="FIT-CPL-25", product_name="25mm PVC Conduit Coupling", category="Conduit Fittings", size_spec="25mm", unit_of_measure="pcs"),
                    Product(product_code="FIT-CPL-32", product_name="32mm PVC Conduit Coupling", category="Conduit Fittings", size_spec="32mm", unit_of_measure="pcs"),
                    Product(product_code="FIT-TEE-20", product_name="20mm PVC Inspection Tee", category="Conduit Fittings", size_spec="20mm", unit_of_measure="pcs"),
                    Product(product_code="FIT-TEE-25", product_name="25mm PVC Inspection Tee", category="Conduit Fittings", size_spec="25mm", unit_of_measure="pcs"),
                    Product(product_code="FIT-JNC-20", product_name="20mm PVC Circular Junction Box", category="Conduit Fittings", size_spec="20mm", unit_of_measure="pcs"),
                    Product(product_code="FIT-JNC-25", product_name="25mm PVC Circular Junction Box", category="Conduit Fittings", size_spec="25mm", unit_of_measure="pcs"),
                    Product(product_code="ACC-SDL-20", product_name="20mm PVC Conduit Saddle", category="Conduit Accessories", size_spec="20mm", unit_of_measure="pcs"),
                    Product(product_code="ACC-SDL-25", product_name="25mm PVC Conduit Saddle", category="Conduit Accessories", size_spec="25mm", unit_of_measure="pcs"),
                ]
                session.add_all(default_products)
                await session.commit()
        except Exception as p_err:
            import logging
            logging.getLogger("database").warning(f"Products seed note: {p_err}")



async def get_sales_rep_pending_balance(session: AsyncSession, phone: str) -> float:
    """
    Computes net pending balance for a salesperson from fleet_pending_ledger.
    Positive amounts represent deficit to recover.
    Negative amounts represent surplus recovered from trips.
    Net balance = SUM(amount).
    """
    clean_phone = phone.replace("+", "").strip() if phone else ""
    stmt = (
        select(func.coalesce(func.sum(FleetPendingLedger.amount), 0.0))
        .where(FleetPendingLedger.salesperson_phone == clean_phone)
    )
    result = await session.execute(stmt)
    val = result.scalar()
    return round(float(val or 0.0), 2)


async def get_sales_rep_ledger_entries(session: AsyncSession, phone: str, limit: int = 5):
    """Fetches recent ledger entries for a salesperson."""
    clean_phone = phone.replace("+", "").strip() if phone else ""
    stmt = (
        select(FleetPendingLedger)
        .where(FleetPendingLedger.salesperson_phone == clean_phone)
        .order_by(FleetPendingLedger.id.desc())
        .limit(limit)
    )
    res = await session.execute(stmt)
    return res.scalars().all()


async def record_pending_ledger_entry(
    session: AsyncSession,
    phone: str,
    name: Optional[str],
    trip_id: Optional[str],
    entry_type: str,
    amount: float,
    notes: Optional[str] = None
) -> FleetPendingLedger:
    """Records an entry in fleet_pending_ledger and commits."""
    clean_phone = phone.replace("+", "").strip() if phone else ""
    entry = FleetPendingLedger(
        salesperson_phone=clean_phone,
        salesperson_name=name,
        trip_id=trip_id,
        entry_type=entry_type,
        amount=round(float(amount), 2),
        notes=notes,
        created_at=datetime.datetime.utcnow()
    )
    session.add(entry)
    await session.commit()
    await session.refresh(entry)
    return entry


async def create_or_update_fleet_trip_request(
    session: AsyncSession,
    trip_id: str,
    company_name: str,
    salesperson_phone: str,
    destination_city: str,
    salesperson_name: Optional[str] = None,
    sales_admin_phone: Optional[str] = None,
    route: Optional[str] = None,
    trip_sales_value: float = 0.0,
    transport_charge: float = 0.0
) -> FleetTripRequest:
    """Creates or updates a FleetTripRequest for a sales rep."""
    clean_sales_phone = salesperson_phone.replace("+", "").strip() if salesperson_phone else ""
    clean_admin_phone = sales_admin_phone.replace("+", "").strip() if sales_admin_phone else ""
    trip_id_clean = trip_id.strip()

    stmt = select(FleetTripRequest).where(FleetTripRequest.trip_id == trip_id_clean)
    res = await session.execute(stmt)
    req = res.scalars().first()

    if not req:
        req = FleetTripRequest(
            trip_id=trip_id_clean,
            company_name=company_name,
            sales_admin_phone=clean_admin_phone,
            salesperson_phone=clean_sales_phone,
            salesperson_name=salesperson_name,
            destination_city=destination_city,
            route=route or destination_city,
            trip_sales_value=round(float(trip_sales_value), 2),
            transport_charge=round(float(transport_charge), 2),
            status="PENDING_ASSIGNMENT",
            created_at=datetime.datetime.utcnow()
        )
        session.add(req)
    else:
        req.company_name = company_name
        req.salesperson_phone = clean_sales_phone
        if salesperson_name:
            req.salesperson_name = salesperson_name
        if clean_admin_phone:
            req.sales_admin_phone = clean_admin_phone
        req.destination_city = destination_city
        req.route = route or destination_city
        req.trip_sales_value = round(float(trip_sales_value), 2)
        req.transport_charge = round(float(transport_charge), 2)
        req.status = "PENDING_ASSIGNMENT"
        req.updated_at = datetime.datetime.utcnow()

    await session.commit()
    await session.refresh(req)
    return req


async def get_fleet_trip_request_by_id(session: AsyncSession, trip_id: str) -> Optional[FleetTripRequest]:
    """Retrieves FleetTripRequest by trip_id."""
    clean_id = trip_id.strip()
    stmt = select(FleetTripRequest).where(FleetTripRequest.trip_id == clean_id)
    res = await session.execute(stmt)
    return res.scalars().first()


async def get_pending_trips_for_edward(session: AsyncSession) -> List[FleetTripRequest]:
    """Retrieves all trip requests awaiting Edward's allocation in FIFO order."""
    stmt = (
        select(FleetTripRequest)
        .where(FleetTripRequest.status.in_(["CREATED", "PENDING_ASSIGNMENT"]))
        .order_by(FleetTripRequest.id.asc())
    )
    res = await session.execute(stmt)
    return list(res.scalars().all())


async def get_active_trip_for_driver(session: AsyncSession, driver_phone: str) -> Optional[FleetTripRequest]:
    """Retrieves currently active or in-transit trip for a driver."""
    clean_p = driver_phone.replace("+", "").strip() if driver_phone else ""
    last_9 = clean_p[-9:] if len(clean_p) >= 9 else clean_p
    stmt = (
        select(FleetTripRequest)
        .where(
            (FleetTripRequest.driver_phone == clean_p) | (FleetTripRequest.driver_phone.endswith(last_9)),
            FleetTripRequest.status.in_(["ALLOWANCE_APPROVED", "TRANSFERRED", "ACTIVE", "RETURNING"])
        )
        .order_by(FleetTripRequest.id.desc())
    )
    res = await session.execute(stmt)
    return res.scalars().first()


async def save_customer_schedules_batch(
    session: AsyncSession,
    trip_id: str,
    schedules: List[Dict[str, Any]]
) -> List[FleetCustomerSchedule]:
    """Saves a batch of customer schedules for autonomous driver matching."""
    clean_id = trip_id.strip()
    # Remove existing pending schedules for this trip
    stmt_del = delete(FleetCustomerSchedule).where(FleetCustomerSchedule.trip_id == clean_id)
    await session.execute(stmt_del)

    created_schedules = []
    for item in schedules:
        c_id = str(item.get("customer_id", "")).strip().upper()
        if not c_id:
            continue
        exp_charge = round(float(item.get("expected_charge", 0.0)), 2)
        sched = FleetCustomerSchedule(
            trip_id=clean_id,
            customer_id=c_id,
            expected_charge=exp_charge,
            collected_charge=0.0,
            payment_method="CASH",
            reference_note=item.get("reference_note"),
            status="PENDING",
            variance=0.0,
            created_at=datetime.datetime.utcnow()
        )
        session.add(sched)
        created_schedules.append(sched)

    await session.commit()
    return created_schedules


async def get_customer_schedules_for_trip(session: AsyncSession, trip_id: str) -> List[FleetCustomerSchedule]:
    """Returns all customer schedule records for a trip."""
    clean_id = trip_id.strip()
    stmt = (
        select(FleetCustomerSchedule)
        .where(FleetCustomerSchedule.trip_id == clean_id)
        .order_by(FleetCustomerSchedule.id.asc())
    )
    res = await session.execute(stmt)
    return list(res.scalars().all())


async def record_driver_delivery_payment(
    session: AsyncSession,
    trip_id: str,
    customer_id: str,
    collected_amount: float,
    payment_method: str = "CASH",
    reference_note: Optional[str] = None
) -> FleetCustomerSchedule:
    """Updates or creates a customer schedule entry with the collected amount from driver."""
    clean_id = trip_id.strip()
    cust_clean = customer_id.strip().upper()
    col_amt = round(float(collected_amount), 2)

    stmt = select(FleetCustomerSchedule).where(
        FleetCustomerSchedule.trip_id == clean_id,
        FleetCustomerSchedule.customer_id == cust_clean
    )
    res = await session.execute(stmt)
    sched = res.scalars().first()

    if not sched:
        sched = FleetCustomerSchedule(
            trip_id=clean_id,
            customer_id=cust_clean,
            expected_charge=col_amt,
            collected_charge=col_amt,
            payment_method=payment_method.upper(),
            reference_note=reference_note,
            status="MATCHED",
            variance=0.0,
            recorded_at=datetime.datetime.utcnow(),
            created_at=datetime.datetime.utcnow()
        )
        session.add(sched)
    else:
        sched.collected_charge = col_amt
        sched.payment_method = payment_method.upper()
        sched.reference_note = reference_note
        sched.recorded_at = datetime.datetime.utcnow()
        sched.variance = round(col_amt - sched.expected_charge, 2)
        sched.status = "MATCHED" if abs(sched.variance) < 0.01 else "VARIANCE"

    await session.commit()
    await session.refresh(sched)
    return sched


async def record_emergency_expense(
    session: AsyncSession,
    trip_id: str,
    driver_phone: str,
    charge_type: str,
    amount: float,
    description: Optional[str] = None,
    has_video: bool = False,
    status: str = "PENDING",
    approved_by: Optional[str] = None
) -> FleetEmergencyExpense:
    """Logs an emergency expense spent by a driver during transit."""
    clean_p = driver_phone.replace("+", "").strip() if driver_phone else ""
    exp = FleetEmergencyExpense(
        trip_id=trip_id.strip(),
        driver_phone=clean_p,
        charge_type=charge_type.upper(),
        amount=round(float(amount), 2),
        description=description,
        has_video_evidence=has_video,
        status=status,
        approved_by=approved_by,
        verified_in_balancing=False,
        created_at=datetime.datetime.utcnow()
    )
    session.add(exp)
    await session.commit()
    await session.refresh(exp)
    return exp


async def get_emergency_expense_by_id(session: AsyncSession, exp_id: int) -> Optional[FleetEmergencyExpense]:
    """Retrieves an emergency expense record by ID."""
    stmt = select(FleetEmergencyExpense).where(FleetEmergencyExpense.id == exp_id)
    res = await session.execute(stmt)
    return res.scalars().first()


async def set_emergency_expense_status(
    session: AsyncSession,
    exp_id: int,
    status: str,
    approved_by: str
) -> Optional[FleetEmergencyExpense]:
    """Updates approval status for an emergency expense."""
    exp = await get_emergency_expense_by_id(session, exp_id)
    if exp:
        exp.status = status
        exp.approved_by = approved_by
        await session.commit()
        await session.refresh(exp)
    return exp


async def get_emergency_expenses_for_trip(session: AsyncSession, trip_id: str) -> List[FleetEmergencyExpense]:
    """Retrieves all emergency expenses logged for a trip."""
    clean_id = trip_id.strip()
    stmt = (
        select(FleetEmergencyExpense)
        .where(FleetEmergencyExpense.trip_id == clean_id)
        .order_by(FleetEmergencyExpense.id.asc())
    )
    res = await session.execute(stmt)
    return list(res.scalars().all())


async def record_driver_pending_entry(
    session: AsyncSession,
    driver_phone: str,
    driver_name: Optional[str],
    trip_id: Optional[str],
    amount: float,
    reason: Optional[str] = None
) -> DriverPendingLedger:
    """Records an outstanding deficit in driver pending ledger."""
    clean_p = driver_phone.replace("+", "").strip() if driver_phone else ""
    entry = DriverPendingLedger(
        driver_phone=clean_p,
        driver_name=driver_name,
        trip_id=trip_id.strip() if trip_id else None,
        amount=round(float(amount), 2),
        reason=reason,
        created_at=datetime.datetime.utcnow()
    )
    session.add(entry)
    await session.commit()
    await session.refresh(entry)
    return entry


async def get_trip_reconciliation_summary(session: AsyncSession, trip_id: str) -> Dict[str, Any]:
    """Calculates complete reconciliation metrics for Sales Admin physical balancing session."""
    clean_id = trip_id.strip()
    trip = await get_fleet_trip_request_by_id(session, clean_id)
    schedules = await get_customer_schedules_for_trip(session, clean_id)
    emergencies = await get_emergency_expenses_for_trip(session, clean_id)

    total_expected = sum(s.expected_charge for s in schedules)
    total_collected = sum(s.collected_charge for s in schedules)
    cash_collected = sum(s.collected_charge for s in schedules if s.payment_method == "CASH")
    bank_collected = sum(s.collected_charge for s in schedules if s.payment_method in {"BANK_ECOCASH", "BANK", "ECOCASH"})
    unpaid_amount = sum(s.expected_charge for s in schedules if s.payment_method == "UNPAID" or (s.expected_charge > 0 and s.collected_charge == 0))
    total_emergencies = sum(e.amount for e in emergencies)
    total_allowance = trip.total_allowance if trip else 0.0

    return {
        "trip": trip,
        "schedules": schedules,
        "emergencies": emergencies,
        "total_expected": round(total_expected, 2),
        "total_collected": round(total_collected, 2),
        "cash_collected": round(cash_collected, 2),
        "bank_collected": round(bank_collected, 2),
        "unpaid_amount": round(unpaid_amount, 2),
        "total_emergencies": round(total_emergencies, 2),
        "total_allowance": round(total_allowance, 2),
        "net_cash_due_to_admin": round(cash_collected, 2)
    }


