import datetime
from sqlalchemy import (
    Column, Integer, String, Text, Boolean, DateTime, ForeignKey
)
from sqlalchemy.orm import relationship
from app.database import Base

class WorkshopTruck(Base):
    __tablename__ = "workshop_trucks"
    truck_id = Column(Integer, primary_key=True, autoincrement=True)
    truck_number = Column(String(50), unique=True, nullable=False) # e.g. "1045"
    plate_number = Column(String(50), nullable=False)             # e.g. "ABZ 1045"
    model_make = Column(String(100), nullable=False)              # e.g. "Volvo FH16 540"
    body_type = Column(String(50), default="Horse")               # Horse, Tipper, Rigid, Tanker
    home_depot = Column(String(100), default="Harare Central")
    active = Column(Boolean, default=True)

class WorkshopStaff(Base):
    __tablename__ = "workshop_staff"
    staff_id = Column(Integer, primary_key=True, autoincrement=True)
    full_name = Column(String(100), nullable=False)
    phone = Column(String(20), unique=True, nullable=False)
    role = Column(String(50), nullable=False) # CLERK, SUPERVISOR, MECHANIC, PURCHASING, LEAD
    active = Column(Boolean, default=True)

class WorkshopCategory(Base):
    __tablename__ = "workshop_categories"
    category_id = Column(Integer, primary_key=True, autoincrement=True)
    category_name = Column(String(100), nullable=False)
    active = Column(Boolean, default=True)
    subcategories = relationship("WorkshopSubcategory", back_populates="category", cascade="all, delete-orphan")

class WorkshopSubcategory(Base):
    __tablename__ = "workshop_subcategories"
    subcategory_id = Column(Integer, primary_key=True, autoincrement=True)
    category_id = Column(Integer, ForeignKey("workshop_categories.category_id"), nullable=False)
    subcategory_name = Column(String(100), nullable=False)
    active = Column(Boolean, default=True)
    category = relationship("WorkshopCategory", back_populates="subcategories")

class WorkshopTicket(Base):
    __tablename__ = "workshop_tickets"
    ticket_id = Column(Integer, primary_key=True, autoincrement=True)
    ticket_number = Column(String(30), unique=True, nullable=False) # TKT-FLT-YYYYMMDD-XXXXX
    truck_id = Column(Integer, ForeignKey("workshop_trucks.truck_id"), nullable=True)
    logged_by_staff_id = Column(Integer, ForeignKey("workshop_staff.staff_id"), nullable=True)
    assigned_mechanic_id = Column(Integer, ForeignKey("workshop_staff.staff_id"), nullable=True)
    category_name = Column(String(100), nullable=True)
    subcategory_name = Column(String(100), nullable=True)
    description = Column(Text, nullable=False)
    image_id = Column(String(100), nullable=True)
    status = Column(String(50), default="OPEN") # OPEN, UNDER_REVIEW, WITH_MECHANIC, AWAITING_PARTS, INFO_REQUESTED, REPAIR_IN_PROGRESS, AWAITING_TEST, REWORK_REQUIRED, CLOSED
    
    # Gatekeeper Triage
    internal_outcome = Column(String(50), nullable=True) # RESOLVED_INTERNALLY, NO_VALID_FAULT
    internal_action_notes = Column(Text, nullable=True)
    
    # Mechanic & Timing
    expected_completion_time = Column(String(100), nullable=True) # e.g. "Tomorrow 11 AM"
    expected_completion_timestamp = Column(DateTime, nullable=True)
    repair_completed_at = Column(DateTime, nullable=True)
    sla_result = Column(String(20), nullable=True) # EARLY, ON_TIME, LATE
    
    # Notes & Costing
    resolution_notes = Column(Text, nullable=True)
    cost_parts = Column(String(50), nullable=True)
    cost_labour = Column(String(50), nullable=True)
    cost_total = Column(String(50), nullable=True)
    
    # QC Testing
    qc_passed = Column(Boolean, nullable=True)
    qc_failure_reason = Column(Text, nullable=True)
    qc_tested_at = Column(DateTime, nullable=True)
    return_to_fleet_at = Column(DateTime, nullable=True)
    
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)

    truck = relationship("WorkshopTruck")
    logged_by = relationship("WorkshopStaff", foreign_keys=[logged_by_staff_id])
    assigned_mechanic = relationship("WorkshopStaff", foreign_keys=[assigned_mechanic_id])
    parts_requests = relationship("WorkshopPartsRequest", back_populates="ticket", cascade="all, delete-orphan")

class WorkshopPartsRequest(Base):
    __tablename__ = "workshop_parts_requests"
    request_id = Column(Integer, primary_key=True, autoincrement=True)
    ticket_id = Column(Integer, ForeignKey("workshop_tickets.ticket_id"), nullable=False)
    part_name = Column(String(200), nullable=False)
    part_description = Column(Text, nullable=True)
    sample_image_id = Column(String(100), nullable=True)
    
    # Purchasing Clarification Loop
    clarification_requested = Column(Boolean, default=False)
    clarification_note = Column(Text, nullable=True)
    clarification_response = Column(Text, nullable=True)
    clarification_image_id = Column(String(100), nullable=True)
    
    status = Column(String(50), default="PENDING") # PENDING, INFO_REQUESTED, RECEIVED
    requested_at = Column(DateTime, default=datetime.datetime.utcnow)
    received_at = Column(DateTime, nullable=True)

    ticket = relationship("WorkshopTicket", back_populates="parts_requests")
