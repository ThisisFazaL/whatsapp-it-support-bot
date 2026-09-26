import re
import datetime
from typing import Dict, Any, Tuple


MEAL_RATE_PER_PERSON = 2.00  # $2.00 per person per meal as requested by user
ACCOMMODATION_RATE_PER_PERSON = 15.00  # $15.00 per person per night


def parse_time_to_minutes(time_str: str) -> int:
    """
    Parses a time string like '06:30 AM', '2:00 PM', '14:00', '2pm' into minutes from midnight (0 - 1439).
    Returns -1 if parsing fails.
    """
    if not time_str:
        return -1
    clean = time_str.strip().lower()

    # Match format like '02:30 pm', '2:30pm', '2pm', '14:00', '6:30 am'
    m = re.search(r"(\d{1,2})(?::(\d{2}))?\s*(am|pm)?", clean)
    if not m:
        return -1

    hour = int(m.group(1))
    minute = int(m.group(2)) if m.group(2) else 0
    ampm = m.group(3)

    if ampm == "pm" and hour < 12:
        hour += 12
    elif ampm == "am" and hour == 12:
        hour = 0

    return hour * 60 + minute


def parse_trip_schedule(departure_str: str, return_str: str) -> Tuple[int, int, int]:
    """
    Parses departure and return string descriptions to determine:
    1. Departure time in minutes (0 - 1439)
    2. Return time in minutes (0 - 1439)
    3. Number of nights spent on trip (0 if same-day, 1+ if overnight)
    """
    dep_mins = parse_time_to_minutes(departure_str)
    ret_mins = parse_time_to_minutes(return_str)

    if dep_mins == -1:
        dep_mins = 6 * 60 + 30  # default 06:30 AM
    if ret_mins == -1:
        ret_mins = 20 * 60  # default 08:00 PM

    dep_lower = (departure_str or "").lower()
    ret_lower = (return_str or "").lower()

    # Determine nights count
    nights = 0
    # Explicit nights check e.g. '2 nights', '1 night', 'overnight'
    m_night = re.search(r"(\d+)\s*night", ret_lower + " " + dep_lower)
    if m_night:
        nights = int(m_night.group(1))
    elif "tomorrow" in ret_lower or "next day" in ret_lower or "+1" in ret_lower:
        nights = 1
    elif any(d in ret_lower for d in ["2 days", "two days"]):
        nights = 1
    elif any(d in ret_lower for d in ["3 days", "three days"]):
        nights = 2
    else:
        # Check if dates specified (e.g. 26/09 vs 27/09)
        date_pattern = r"(\d{1,2})[/\.-](\d{1,2})"
        dep_dates = re.findall(date_pattern, dep_lower)
        ret_dates = re.findall(date_pattern, ret_lower)
        if dep_dates and ret_dates:
            try:
                d1 = int(dep_dates[0][0])
                d2 = int(ret_dates[0][0])
                if d2 > d1:
                    nights = d2 - d1
            except Exception:
                pass

    return dep_mins, ret_mins, max(0, nights)


def calculate_meal_count(departure_str: str, return_str: str) -> int:
    """
    Calculates number of meals per person based on departure and return times.
    Rule:
    - Breakfast: 07:00 - 08:30 AM (Included if departing <= 08:30 AM)
    - Lunch: 12:00 - 02:00 PM (Included if departing <= 01:00 PM and returning >= 01:30 PM.
             If departure is 02:00 PM / 14:00, lunch is strictly EXCLUDED)
    - Dinner: 06:30 - 08:30 PM (Included if returning >= 07:00 PM / 19:00)
    - Overnight trips: 3 meals for each full intermediate day.
    """
    dep_mins, ret_mins, nights = parse_trip_schedule(departure_str, return_str)

    # 1. Same-day trip (nights == 0)
    if nights == 0:
        meals = 0
        # Breakfast: included if departed early (<= 08:30 AM) and returning after 09:00 AM
        if dep_mins <= (8 * 60 + 30) and ret_mins >= (9 * 60):
            meals += 1

        # Lunch: included if departed before 01:00 PM (780 mins) and returning after 01:30 PM (810 mins)
        # Note: If departure is 02:00 PM (840 mins), lunch is NOT included!
        if dep_mins <= (13 * 60) and ret_mins >= (13 * 60 + 30):
            meals += 1

        # Dinner: included if returning at or after 07:00 PM (19:00 / 1140 mins)
        if ret_mins >= (19 * 60):
            meals += 1

        return max(1, meals)  # At least 1 meal if on a transit trip

    # 2. Multi-day / Overnight trip (nights >= 1)
    # Day 1 meals:
    day1_meals = 0
    if dep_mins <= (8 * 60 + 30):
        day1_meals += 1  # Breakfast
    if dep_mins <= (13 * 60):
        day1_meals += 1  # Lunch
    day1_meals += 1      # Dinner (on road overnight)

    # Full intermediate days (nights - 1):
    full_day_meals = max(0, nights - 1) * 3

    # Final return day meals:
    return_day_meals = 1  # Breakfast included
    if ret_mins >= (13 * 60 + 30):
        return_day_meals += 1  # Lunch included
    if ret_mins >= (19 * 60):
        return_day_meals += 1  # Dinner included

    total_meals = day1_meals + full_day_meals + return_day_meals
    return max(1, total_meals)


def is_masvingo_route(route_or_city: str) -> bool:
    """Checks whether the destination or route includes Masvingo (Tagoneswa Warehouse)."""
    if not route_or_city:
        return False
    norm = route_or_city.strip().lower()
    return any(name in norm for name in ["masvingo", "maswingo", "msv", "mucheke"])


def calculate_accommodation(route_or_city: str, nights: int, crew_count: int) -> Dict[str, Any]:
    """
    Calculates accommodation allowance.
    Rule:
    - If route includes Masvingo: $0.00 (Tagoneswa Masvingo Warehouse available for driver lodging).
    - Other routes: $15.00 per night per person.
    """
    if nights <= 0:
        return {
            "nights": 0,
            "cost": 0.0,
            "has_warehouse_stay": False,
            "note": "Same-day return (No accommodation needed)"
        }

    if is_masvingo_route(route_or_city):
        return {
            "nights": nights,
            "cost": 0.0,
            "has_warehouse_stay": True,
            "note": "🏠 *Accommodation: $0.00* (Tagoneswa Masvingo Warehouse available — free driver lodging)"
        }

    total_cost = nights * crew_count * ACCOMMODATION_RATE_PER_PERSON
    return {
        "nights": nights,
        "cost": total_cost,
        "has_warehouse_stay": False,
        "note": f"🏠 *Accommodation ({nights} night(s) @ ${ACCOMMODATION_RATE_PER_PERSON:,.2f}/person):* ${total_cost:,.2f}"
    }


def calculate_total_allowance(
    crew_count: int,
    departure_str: str,
    return_str: str,
    route_or_city: str,
    toll_cost: float = 0.0
) -> Dict[str, Any]:
    """
    Coordinates meal calculation, accommodation, and tolls into full allowance breakdown.
    """
    crew = max(1, crew_count)
    meal_count = calculate_meal_count(departure_str, return_str)
    dep_mins, ret_mins, nights = parse_trip_schedule(departure_str, return_str)

    food_allowance = meal_count * crew * MEAL_RATE_PER_PERSON
    accom_info = calculate_accommodation(route_or_city, nights, crew)
    accommodation_cost = accom_info["cost"]
    tolls = max(0.0, float(toll_cost or 0.0))

    total = food_allowance + accommodation_cost + tolls

    return {
        "crew_count": crew,
        "departure_time": departure_str,
        "return_time": return_str,
        "meal_count_per_person": meal_count,
        "meal_rate": MEAL_RATE_PER_PERSON,
        "food_allowance": round(food_allowance, 2),
        "nights": nights,
        "accommodation_cost": round(accommodation_cost, 2),
        "has_warehouse_stay": accom_info["has_warehouse_stay"],
        "accommodation_note": accom_info["note"],
        "toll_cost": round(tolls, 2),
        "total_allowance": round(total, 2)
    }
