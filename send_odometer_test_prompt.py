import asyncio
import logging
from sqlalchemy import select
from app.database import async_session_factory, FleetTripRequest
from app.state_manager import set_user_state
from app.meta_api import meta_api

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("odometer_test")

async def send_odometer_prompt():
    phone = "919265368695"
    trip_id = "TEST-ODO-001"
    
    async with async_session_factory() as session:
        # 1. Ensure test trip exists
        res = await session.execute(
            select(FleetTripRequest).where(FleetTripRequest.trip_id == trip_id)
        )
        trip = res.scalars().first()
        if not trip:
            trip = FleetTripRequest(
                trip_id=trip_id,
                company_name="A. TG Hardware",
                salesperson_name="Fazal Saiyed",
                salesperson_phone=phone,
                destination_city="Harare",
                route="Harare Central",
                driver_phone=phone,
                driver_name="Fazal Saiyed",
                truck_plate="TEST-9999",
                status="ASSIGNED",
                departure_time="10:00 AM",
                trip_sales_value=500.0,
                transport_charge=50.0
            )
            session.add(trip)
            logger.info(f"Created new test trip {trip_id}")
        else:
            trip.driver_phone = phone
            trip.driver_name = "Fazal Saiyed"
            trip.truck_plate = "TEST-9999"
            trip.status = "ASSIGNED"
            trip.departure_time = "10:00 AM"
            logger.info(f"Updated existing test trip {trip_id}")
            
        await session.commit()
        
        # 2. Set conversation state to awaiting_start_odometer
        await set_user_state(
            session,
            phone,
            current_step="awaiting_start_odometer",
            current_data={"trip_id": trip_id},
            flow_name="fleet_driver"
        )
        logger.info(f"Set state for {phone} to awaiting_start_odometer with trip {trip_id}")
        
    # 3. Send the exact trip departure odometer prompt to Fazal
    prompt = (
        f"🚚 *TRIP DEPARTURE: {trip_id}*\n"
        "────────────────────\n"
        "Please enter the vehicle's *Starting Odometer* reading (in KM), or send a 📸 *photo* of the dashboard cluster:\n"
        "_(e.g. 145200 or take a photo)_"
    )
    api_res = await meta_api.send_text_message(phone, prompt)
    logger.info(f"WhatsApp message response: {api_res}")
    return api_res

if __name__ == "__main__":
    asyncio.run(send_odometer_prompt())
