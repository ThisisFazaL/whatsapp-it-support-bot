import asyncio
import os
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from app.config import settings
from app.database import Base
from app.workshop.models import (
    WorkshopTruck, WorkshopStaff, WorkshopCategory, WorkshopSubcategory,
    WorkshopTicket, WorkshopPartsRequest
)

# Permanent Production Fleet of Tagoneswa Logistics (39 unique vehicles)
PRODUCTION_FLEET = [
    {"truck_number": "7331", "plate_number": "AGZ 7331", "model_make": "IVECO STRALIS 330", "body_type": "Horse (6x4)", "home_depot": "Harare Yard"},
    {"truck_number": "5771", "plate_number": "AGV 5771", "model_make": "IVECO 180e25 (Rigid)", "body_type": "Rigid", "home_depot": "Harare Yard"},
    {"truck_number": "0234", "plate_number": "AHF 0234", "model_make": "IVECO 74e18", "body_type": "Rigid", "home_depot": "Harare Yard"},
    {"truck_number": "8440", "plate_number": "AHF 8440", "model_make": "IVECO Box VA 75 E18", "body_type": "Box Rigid", "home_depot": "Harare Yard"},
    {"truck_number": "0233", "plate_number": "AHF 0233", "model_make": "IVECO Eurocargo", "body_type": "Rigid", "home_depot": "Harare Yard"},
    {"truck_number": "2070", "plate_number": "AGT 2070", "model_make": "SINO TRUCK ZZ1168G", "body_type": "Horse (6x4)", "home_depot": "Harare Yard"},
    {"truck_number": "1928", "plate_number": "AGV 1928", "model_make": "Fox Rigid Truck", "body_type": "Rigid", "home_depot": "Harare Yard"},
    {"truck_number": "1926", "plate_number": "AGV 1926", "model_make": "DAF LF250", "body_type": "Rigid", "home_depot": "Harare Yard"},
    {"truck_number": "5978", "plate_number": "AEK 5978", "model_make": "IVECO Eurocargo", "body_type": "Rigid", "home_depot": "Harare Yard"},
    {"truck_number": "6854", "plate_number": "AFE 6854", "model_make": "ToyoAce", "body_type": "Rigid", "home_depot": "Harare Yard"},
    {"truck_number": "0346", "plate_number": "AFG 0346", "model_make": "IVECO 75E16 Eurocargo", "body_type": "Rigid", "home_depot": "Harare Yard"},
    {"truck_number": "9709", "plate_number": "AFM 9709", "model_make": "Toyota Prius", "body_type": "Light Vehicle", "home_depot": "Harare Yard"},
    {"truck_number": "5056", "plate_number": "AFN 5056", "model_make": "IVECO Eurocargo Box 180e25", "body_type": "Box Rigid", "home_depot": "Harare Yard"},
    {"truck_number": "5057", "plate_number": "AFN 5057", "model_make": "IVECO Eurocargo Box 180e25", "body_type": "Box Rigid", "home_depot": "Harare Yard"},
    {"truck_number": "4351", "plate_number": "AFO 4351", "model_make": "Hino Dutro", "body_type": "Rigid", "home_depot": "Harare Yard"},
    {"truck_number": "2545", "plate_number": "AFS 2545", "model_make": "Toyota Dyna", "body_type": "Rigid", "home_depot": "Harare Yard"},
    {"truck_number": "2732", "plate_number": "AFV 2732", "model_make": "Nissan AD Van", "body_type": "Van", "home_depot": "Harare Yard"},
    {"truck_number": "4929", "plate_number": "AGA 4929", "model_make": "Mazda Titan", "body_type": "Rigid", "home_depot": "Harare Yard"},
    {"truck_number": "5878", "plate_number": "AGH 5878", "model_make": "IVECO", "body_type": "Rigid", "home_depot": "Harare Yard"},
    {"truck_number": "5879", "plate_number": "AGH 5879", "model_make": "Eurocargo 180e24", "body_type": "Rigid", "home_depot": "Harare Yard"},
    {"truck_number": "6858", "plate_number": "AGN 6858", "model_make": "Toyota Probox", "body_type": "Light Vehicle", "home_depot": "Harare Yard"},
    {"truck_number": "8435", "plate_number": "AHF 8435", "model_make": "Isuzu", "body_type": "Rigid", "home_depot": "Harare Yard"},
    {"truck_number": "0232", "plate_number": "AHF 0232", "model_make": "IVECO Eurocargo", "body_type": "Rigid", "home_depot": "Harare Yard"},
    {"truck_number": "9313", "plate_number": "AHC 9313", "model_make": "SINO TRUCK", "body_type": "Horse (6x4)", "home_depot": "Harare Yard"},
    {"truck_number": "9312", "plate_number": "AHC 9312", "model_make": "Nissan AD Van", "body_type": "Van", "home_depot": "Harare Yard"},
    {"truck_number": "0030", "plate_number": "AHC 0030", "model_make": "Hino Ranger", "body_type": "Rigid", "home_depot": "Harare Yard"},
    {"truck_number": "1742", "plate_number": "AGY 1742", "model_make": "Nissan AD Van", "body_type": "Van", "home_depot": "Harare Yard"},
    {"truck_number": "6234", "plate_number": "AGX 6234", "model_make": "Nissan Condor UD Truck", "body_type": "UD Truck", "home_depot": "Harare Yard"},
    {"truck_number": "5770", "plate_number": "AGV 5770", "model_make": "MAN TGL 7150", "body_type": "Rigid", "home_depot": "Harare Yard"},
    {"truck_number": "5769", "plate_number": "AGV 5769", "model_make": "IVECO 180E25", "body_type": "Rigid", "home_depot": "Harare Yard"},
    {"truck_number": "5768", "plate_number": "AGV 5768", "model_make": "Mitsubishi Fuso", "body_type": "Rigid", "home_depot": "Harare Yard"},
    {"truck_number": "6917", "plate_number": "AGT 6917", "model_make": "Nissan AD Van", "body_type": "Van", "home_depot": "Harare Yard"},
    {"truck_number": "2920", "plate_number": "AGQ 2920", "model_make": "Mazda Titan", "body_type": "Rigid", "home_depot": "Harare Yard"},
    {"truck_number": "0727", "plate_number": "AGO 0727", "model_make": "Nissan Caravan NV350", "body_type": "Van", "home_depot": "Harare Yard"},
    {"truck_number": "0714", "plate_number": "AGO 0714", "model_make": "Nissan NV200", "body_type": "Van", "home_depot": "Harare Yard"},
    {"truck_number": "6605", "plate_number": "AGI 6605", "model_make": "Toyota Probox", "body_type": "Light Vehicle", "home_depot": "Harare Yard"},
    {"truck_number": "4715", "plate_number": "ACW 4715", "model_make": "Hino 30SC (Rigid)", "body_type": "Rigid", "home_depot": "Harare Yard"},
    {"truck_number": "8434", "plate_number": "AHF 8434", "model_make": "IVECO 150e19", "body_type": "Rigid", "home_depot": "Harare Yard"},
    {"truck_number": "8436", "plate_number": "AHF 8436", "model_make": "IVECO 180e28", "body_type": "Rigid", "home_depot": "Harare Yard"},
]

# Permanent Production Staff & Drivers Directory (24 members + Admin)
PRODUCTION_STAFF = [
    {"full_name": "Terrence Mupfumi", "phone": "263788112771", "role": "DRIVER"},
    {"full_name": "Godknows Kadungure", "phone": "263772678948", "role": "DRIVER"},
    {"full_name": "Peter Ncube", "phone": "263774364811", "role": "DRIVER"},
    {"full_name": "Ashley Zirota", "phone": "263787760064", "role": "DRIVER"},
    {"full_name": "Wilbert Makoma", "phone": "263775959241", "role": "DRIVER"},
    {"full_name": "Langton Mariga", "phone": "263779618688", "role": "DRIVER"},
    {"full_name": "Takudzwa Bafana", "phone": "263775316554", "role": "DRIVER"},
    {"full_name": "Tatenda Bhunu", "phone": "263771345594", "role": "DRIVER"},
    {"full_name": "Tonderai Matongo", "phone": "263777758430", "role": "DRIVER"},
    {"full_name": "Lastern Sabola", "phone": "263733493338", "role": "DRIVER"},
    {"full_name": "Owen Sibanda", "phone": "263783175517", "role": "DRIVER"},
    {"full_name": "Praymore Madondo", "phone": "263781603472", "role": "DRIVER"},
    {"full_name": "Michael Kamudyariwa", "phone": "263774842059", "role": "DRIVER"},
    {"full_name": "Thabani Chinamora", "phone": "263772961453", "role": "DRIVER"},
    {"full_name": "Last Kanyandura", "phone": "263775738870", "role": "DRIVER"},
    {"full_name": "Nyasha Isaiah", "phone": "263777724900", "role": "DRIVER"},
    {"full_name": "Garikai Madubeko", "phone": "263777669972", "role": "DRIVER"},
    {"full_name": "Shepherd Matowanyika", "phone": "263776093473", "role": "DRIVER"},
    {"full_name": "Kelvin Chitsamba", "phone": "263779841935", "role": "DRIVER"},
    {"full_name": "Fortune Samukange", "phone": "263775189811", "role": "DRIVER"},
    {"full_name": "Panashe Mutamangira", "phone": "263777261203", "role": "LOGISTICS_ASSISTANT"},
    {"full_name": "Edward Chemhere", "phone": "263715025982", "role": "SUPERVISOR"},
    {"full_name": "Lydon Kandikire", "phone": "263718295309", "role": "PURCHASING"},
    {"full_name": "Sajid", "phone": "263718093498", "role": "MECHANIC"},
    {"full_name": "Fazal Saiyed (Supervisor)", "phone": "919265368695", "role": "SUPERVISOR"}
]

async def seed_workshop_data_in_session(session: AsyncSession):
    """Idempotently seeds standard fault taxonomies, fleet trucks, and registered staff."""
    
    # 1. Seed Real Fleet Trucks
    for t in PRODUCTION_FLEET:
        stmt = select(WorkshopTruck).where(WorkshopTruck.truck_number == t["truck_number"])
        existing = (await session.execute(stmt)).scalars().first()
        if not existing:
            session.add(WorkshopTruck(**t, active=True))
        else:
            existing.plate_number = t["plate_number"]
            existing.model_make = t["model_make"]
            existing.body_type = t["body_type"]
            existing.home_depot = t["home_depot"]
            existing.active = True

    # 2. Seed Real Staff & Drivers
    for s in PRODUCTION_STAFF:
        clean_p = s["phone"]
        last_9 = clean_p[-9:] if len(clean_p) >= 9 else clean_p
        stmt = select(WorkshopStaff).where(
            (WorkshopStaff.phone == clean_p) |
            (WorkshopStaff.phone.endswith(last_9))
        )
        existing = (await session.execute(stmt)).scalars().first()
        if not existing:
            session.add(WorkshopStaff(
                full_name=s["full_name"],
                phone=clean_p,
                role=s["role"],
                active=True
            ))
        else:
            existing.full_name = s["full_name"]
            existing.phone = clean_p
            existing.role = s["role"]
            existing.active = True

    # 3. Seed Categories & Subcategories
    taxonomy = [
        ("Brakes & Air Pressure", ["Air Pressure Leak", "Foot Brake Spongy / Low Air", "Handbrake / Maxie Stuck", "Air Compressor / Dryer Issue"]),
        ("Engine, Fuel & Cooling", ["Engine Overheating", "Low Oil Pressure Warning", "Diesel Starvation / Fuel Leak", "Loss of Power / Turbo Noise"]),
        ("Electrical, Lights & Battery", ["Battery Dead / No Crank", "Alternator Warning Light", "Headlights / Tail Lights Failed", "Starter Motor Click"]),
        ("Transmission & Clutch", ["Gearbox Grinding / Stiff", "Clutch Slipping", "Propshaft Vibration", "Differential Noise"]),
        ("Suspension, Steering & Axles", ["Air Bag Deflated / Leak", "Kingpin Play / Steering Stiff", "Leaf Spring Broken / Shifted", "Wheel Alignment / Pulling"]),
        ("Tires, Wheels & Rims", ["Flat / Blown Tire", "Wheel Nut Loose / Stud Broken", "Rim Crack / Flange Damage", "Wheel Bearing Noise / Heat"]),
        ("Trailer & Cargo Body", ["Trailer Brake Lockup", "Fifth Wheel / Turntable Play", "Landing Gear Jammed / Bent", "Curtain / Door Lock Mechanism"]),
        ("Refrigeration Unit (Reefer)", ["Reefer Engine Failure", "Temperature Warning / Gas Leak", "Electric Standby Trip", "Drive Belt Snapped"])
    ]

    for cat_name, subcats in taxonomy:
        stmt = select(WorkshopCategory).where(WorkshopCategory.category_name == cat_name)
        cat_obj = (await session.execute(stmt)).scalars().first()
        if not cat_obj:
            cat_obj = WorkshopCategory(category_name=cat_name, active=True)
            session.add(cat_obj)
            await session.flush()
            
        for sc_name in subcats:
            sc_stmt = select(WorkshopSubcategory).where(
                WorkshopSubcategory.category_id == cat_obj.category_id,
                WorkshopSubcategory.subcategory_name == sc_name
            )
            sc_obj = (await session.execute(sc_stmt)).scalars().first()
            if not sc_obj:
                session.add(WorkshopSubcategory(
                    category_id=cat_obj.category_id,
                    subcategory_name=sc_name,
                    active=True
                ))

    await session.commit()
