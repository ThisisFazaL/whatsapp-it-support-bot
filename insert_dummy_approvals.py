import asyncio
import datetime
from sqlalchemy import select, delete
from app.database import (
    async_session_factory,
    FleetTripRequest,
    FleetEmergencyExpense,
    FleetTripApproval
)

async def seed_dummy_approvals():
    async with async_session_factory() as session:
        demo_trip_ids = [
            "TRIP-DEMO-ALW-01",
            "TRIP-DEMO-FUEL-02",
            "TRIP-DEMO-EMG-03",
            "TRIP-DEMO-SF-04"
        ]

        print("--- Cleaning up previous demo records (if any) ---")
        await session.execute(delete(FleetEmergencyExpense).where(FleetEmergencyExpense.trip_id.in_(demo_trip_ids)))
        await session.execute(delete(FleetTripApproval).where(FleetTripApproval.trip_id.in_(demo_trip_ids)))
        await session.execute(delete(FleetTripRequest).where(FleetTripRequest.trip_id.in_(demo_trip_ids)))
        await session.commit()

        print("--- Inserting fresh pending dummy approval records ---")

        # 1. Driver Extra Allowance (Pending)
        tr1 = FleetTripRequest(
            trip_id="TRIP-DEMO-ALW-01",
            company_name="Tagoneswa Hardware",
            destination_city="Mutare",
            route="Route 5 East",
            salesperson_name="Stuart Chaleka",
            salesperson_phone="263718643451",
            driver_name="Tonderai Matongo",
            driver_phone="263712024095",
            truck_plate="AGZ 7331",
            trip_sales_value=4250.00,
            transport_charge=195.00,
            status="ACTIVE",
            created_at=datetime.datetime.utcnow(),
            updated_at=datetime.datetime.utcnow()
        )
        exp1 = FleetEmergencyExpense(
            trip_id="TRIP-DEMO-ALW-01",
            driver_phone="263712024095",
            charge_type="EXTRA_ALLOWANCE",
            amount=55.00,
            description="Accommodation: $35.00; Food: $20.00 | Breakdown: Night stop in Mutare due to late customer offloading",
            status="PENDING",
            approved_by=None,
            rejection_note=None,
            created_at=datetime.datetime.utcnow()
        )
        session.add(tr1)
        session.add(exp1)

        # 2. Driver Emergency Fuel (Pending)
        tr2 = FleetTripRequest(
            trip_id="TRIP-DEMO-FUEL-02",
            company_name="LG Plast",
            destination_city="Bulawayo",
            route="Route 1 South",
            salesperson_name="Ashraf Nedziwe",
            salesperson_phone="263779214825",
            driver_name="Godknows Kadungure",
            driver_phone="263712024201",
            truck_plate="AES 8922",
            trip_sales_value=5890.00,
            transport_charge=260.00,
            status="ACTIVE",
            created_at=datetime.datetime.utcnow(),
            updated_at=datetime.datetime.utcnow()
        )
        exp2 = FleetEmergencyExpense(
            trip_id="TRIP-DEMO-FUEL-02",
            driver_phone="263712024201",
            charge_type="EMERGENCY_FUEL",
            amount=35.00,
            description="Corridor emergency fuel top-up at Kadoma due to detour on Highway",
            status="PENDING",
            approved_by=None,
            rejection_note=None,
            created_at=datetime.datetime.utcnow()
        )
        session.add(tr2)
        session.add(exp2)

        # 3. Driver Other Emergency Expense (Pending)
        tr3 = FleetTripRequest(
            trip_id="TRIP-DEMO-EMG-03",
            company_name="Kreckle Foods",
            destination_city="Gweru",
            route="Route 2 Midlands",
            salesperson_name="David Mungadzi",
            salesperson_phone="263780543771",
            driver_name="Kelvin Chitsamba",
            driver_phone="263712035327",
            truck_plate="AFK 4109",
            trip_sales_value=3400.00,
            transport_charge=150.00,
            status="ACTIVE",
            created_at=datetime.datetime.utcnow(),
            updated_at=datetime.datetime.utcnow()
        )
        exp3 = FleetEmergencyExpense(
            trip_id="TRIP-DEMO-EMG-03",
            driver_phone="263712035327",
            charge_type="OTHER_EMERGENCY",
            amount=25.00,
            description="Emergency tire valve & puncture repair at Kwekwe service centre",
            status="PENDING",
            approved_by=None,
            rejection_note=None,
            created_at=datetime.datetime.utcnow()
        )
        session.add(tr3)
        session.add(exp3)

        # 4. Commercial Trip Shortfall (Pending)
        tr4 = FleetTripRequest(
            trip_id="TRIP-DEMO-SF-04",
            company_name="Tagoneswa Hardware",
            destination_city="Masvingo",
            route="Route 4 South-East",
            salesperson_name="Tafadzwa Sungiso",
            salesperson_phone="263717905914",
            trip_sales_value=1850.00,
            transport_charge=180.00,
            status="SHORTFALL_RECORDED",
            created_at=datetime.datetime.utcnow(),
            updated_at=datetime.datetime.utcnow()
        )
        appr4 = FleetTripApproval(
            trip_id="TRIP-DEMO-SF-04",
            salesperson_phone="263717905914",
            salesperson_name="Tafadzwa Sungiso",
            destination_city="Masvingo",
            route="Route 4 South-East",
            trip_sales_value=1850.00,
            required_minimum=2500.00,
            shortfall=650.00,
            transport_charge=180.00,
            has_shortfall=True,
            status="SHORTFALL_RECORDED",
            raw_data={"company_name": "Tagoneswa Hardware"},
            created_at=datetime.datetime.utcnow()
        )
        session.add(tr4)
        session.add(appr4)

        await session.commit()
        print("[SUCCESS] Successfully inserted 3 pending driver expenses and 1 pending trip shortfall!")

        # Print inserted records
        res_exp = (await session.execute(select(FleetEmergencyExpense).where(FleetEmergencyExpense.trip_id.in_(demo_trip_ids)))).scalars().all()
        for e in res_exp:
            print(f"  Expense #{e.id}: Trip {e.trip_id} | Type: {e.charge_type} | Amount: ${e.amount:.2f} | Status: {e.status}")

        res_sf = (await session.execute(select(FleetTripApproval).where(FleetTripApproval.trip_id == "TRIP-DEMO-SF-04"))).scalars().all()
        for s in res_sf:
            print(f"  Shortfall Approval #{s.id}: Trip {s.trip_id} | Shortfall: ${s.shortfall:.2f} | Status: {s.status}")

if __name__ == "__main__":
    asyncio.run(seed_dummy_approvals())
