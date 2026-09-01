import asyncio
import csv
import os
import sys
import re
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

from app.config import settings
from app.database import Base
from app.workshop.models import WorkshopTruck, WorkshopStaff

def clean_phone(phone_str: str) -> str:
    """Strips all non-digit characters and ensures country code format."""
    digits = re.sub(r"\D", "", str(phone_str or ""))
    return digits

def extract_truck_number_from_plate(plate: str, provided_num: str = None) -> str:
    """Extracts numeric truck number from plate (e.g. 'ABZ 1045' -> '1045') if not explicitly given."""
    if provided_num and str(provided_num).strip():
        return str(provided_num).strip()
    match = re.search(r"\d+", str(plate or ""))
    return match.group(0) if match else str(plate).strip()

async def import_data(trucks_csv_path: str = "Tagoneswa_Fleet_Trucks_Template.csv", staff_csv_path: str = "Tagoneswa_Workshop_Staff_Template.csv"):
    db_urls = [settings.database_url, "sqlite+aiosqlite:///./itsupport.db"]
    engine = None

    for url in db_urls:
        try:
            kw = {"echo": False}
            if "postgresql" in url:
                kw["connect_args"] = {"ssl": "require", "statement_cache_size": 0, "prepared_statement_cache_size": 0}
            test_engine = create_async_engine(url, **kw)
            async with test_engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
            engine = test_engine
            break
        except Exception:
            continue

    if not engine:
        raise RuntimeError("Could not connect to database.")

    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    
    async with session_factory() as session:
        # 1. Import Trucks
        if os.path.exists(trucks_csv_path):
            with open(trucks_csv_path, mode="r", encoding="utf-8-sig") as f:
                reader = csv.DictReader(f)
                truck_count = 0
                for row in reader:
                    plate = str(row.get("Registration Plate Number (e.g. ABZ 1045)", "") or row.get("Registration Plate", "") or row.get("Plate", "")).strip()
                    raw_num = str(row.get("Truck Number (Auto-extracted from Plate: e.g. 1045)", "") or row.get("Truck Number", "")).strip()
                    truck_num = extract_truck_number_from_plate(plate, raw_num)
                    
                    model = str(row.get("Vehicle Make & Model (e.g. Volvo FH16 540)", "") or row.get("Vehicle Make & Model", "") or row.get("Make & Model", "")).strip()
                    body = str(row.get("Body Type / Configuration (e.g. Horse 6x4, Tipper, Tanker)", "") or row.get("Body Type / Configuration", "")).strip()
                    depot = str(row.get("Home Depot / Base Yard (e.g. Harare Central Yard)", "") or row.get("Home Depot / Yard", "")).strip()
                    active_str = str(row.get("Status (Active / Inactive)", "") or row.get("Status", "Active")).strip().lower()
                    is_active = active_str in ["active", "yes", "true", "1"]

                    if not truck_num:
                        continue

                    stmt = select(WorkshopTruck).where(WorkshopTruck.truck_number == truck_num)
                    truck = (await session.execute(stmt)).scalars().first()
                    if not truck:
                        truck = WorkshopTruck(
                            truck_number=truck_num,
                            plate_number=plate or f"TRK {truck_num}",
                            model_make=model or "Heavy Vehicle",
                            body_type=body or "Horse (6x4)",
                            home_depot=depot or "Harare Central Yard",
                            active=is_active
                        )
                        session.add(truck)
                    else:
                        truck.plate_number = plate or truck.plate_number
                        truck.model_make = model or truck.model_make
                        truck.body_type = body or truck.body_type
                        truck.home_depot = depot or truck.home_depot
                        truck.active = is_active
                    truck_count += 1
                await session.commit()
                print(f"[SUCCESS] Imported / Updated {truck_count} Fleet Trucks!")

        # 2. Import Staff
        if os.path.exists(staff_csv_path):
            with open(staff_csv_path, mode="r", encoding="utf-8-sig") as f:
                reader = csv.DictReader(f)
                staff_count = 0
                for row in reader:
                    name = str(row.get("Full Name", "")).strip()
                    raw_phone = str(row.get("WhatsApp Phone Number (with Country Code e.g. +263...)", "") or row.get("WhatsApp Phone Number", "") or row.get("Phone", "")).strip()
                    role = str(row.get("System Role (DRIVER / SUPERVISOR / MECHANIC / LEAD / PURCHASING / CLERK)", "") or row.get("System Role", "") or row.get("Role", "DRIVER")).strip().upper()
                    active_str = str(row.get("Status (Active / Inactive)", "") or row.get("Status", "Active")).strip().lower()
                    is_active = active_str in ["active", "yes", "true", "1"]

                    phone = clean_phone(raw_phone)
                    if not phone or not name:
                        continue

                    stmt = select(WorkshopStaff).where(WorkshopStaff.phone == phone)
                    staff = (await session.execute(stmt)).scalars().first()
                    if not staff:
                        staff = WorkshopStaff(
                            full_name=name,
                            phone=phone,
                            role=role,
                            active=is_active
                        )
                        session.add(staff)
                    else:
                        staff.full_name = name
                        staff.role = role
                        staff.active = is_active
                    staff_count += 1
                await session.commit()
                print(f"[SUCCESS] Imported / Updated {staff_count} Workshop Staff / Drivers!")

if __name__ == "__main__":
    trucks_file = sys.argv[1] if len(sys.argv) > 1 else "Tagoneswa_Fleet_Trucks_Template.csv"
    staff_file = sys.argv[2] if len(sys.argv) > 2 else "Tagoneswa_Workshop_Staff_Template.csv"
    asyncio.run(import_data(trucks_file, staff_file))
