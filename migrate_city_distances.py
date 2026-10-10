import asyncio
from app.database import async_session_factory, FleetRouteRule
from app.services.trip_pricing_service import CITY_MINIMUMS
from sqlalchemy import select

async def main():
    async with async_session_factory() as session:
        stmt = select(FleetRouteRule)
        rules = (await session.execute(stmt)).scalars().all()
        updated_count = 0
        for r in rules:
            city_key = r.city_key.lower().strip()
            if city_key in CITY_MINIMUMS:
                exact_dist = float(CITY_MINIMUMS[city_key].get("distance_km", 0.0))
                r.distance_km = exact_dist
                updated_count += 1
                print(f"Updated {r.city_name:18} ({r.city_key:15}) -> {r.distance_km} km")
            else:
                print(f"WARNING: {r.city_key} not in CITY_MINIMUMS!")

        await session.commit()
        print(f"\nSuccessfully committed {updated_count} city distances to database fleet_route_rules table.")

        # Verify
        stmt_check = select(FleetRouteRule)
        verified_rules = (await session.execute(stmt_check)).scalars().all()
        zero_count = sum(1 for vr in verified_rules if not vr.distance_km or vr.distance_km <= 0)
        print(f"Verification: {len(verified_rules)} rules in DB, {zero_count} with distance <= 0.")
        assert zero_count == 0, f"Found {zero_count} rules with distance <= 0!"

if __name__ == "__main__":
    asyncio.run(main())
