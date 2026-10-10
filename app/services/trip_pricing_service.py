import re
from typing import Optional, Dict, Any, List


class CityNotFoundError(Exception):
    """Raised when a city or area cannot be mapped to the minimum sales rule."""
    pass


# Master Zimbabwe Delivery Corridors (from Harare hub)
# 45 delivery stops from the trips list, grouped into corridors out of Harare.
MASTER_CORRIDORS: Dict[str, Dict[str, Any]] = {
    "Corridor 1": {
        "id": "corridor_1",
        "name": "West to Bulawayo",
        "route_label": "Route 1 West to Bulawayo",
        "stop_count": 7,
        "stops": ["Norton", "Chegutu", "Kadoma", "Kwekwe", "Gweru", "Bulawayo", "Gokwe"],
    },
    "Corridor 2": {
        "id": "corridor_2",
        "name": "Northwest to Karoi",
        "route_label": "Route 2 Northwest to Karoi",
        "stop_count": 5,
        "stops": ["Murambedzi", "Banket", "Chinhoyi", "Karoi", "Magunje"],
    },
    "Corridor 3": {
        "id": "corridor_3",
        "name": "North to Guruve and Mt Darwin",
        "route_label": "Route 3 North to Guruve and Mt Darwin",
        "stop_count": 8,
        "stops": ["Domboshawa", "Glendale", "Bindura", "Madziva", "Mt Darwin", "Mazowe", "Mvurwi", "Guruve"],
    },
    "Corridor 4": {
        "id": "corridor_4",
        "name": "Northeast to Kotwa",
        "route_label": "Route 4 Northeast to Kotwa",
        "stop_count": 6,
        "stops": ["Juru", "Murewa", "Mutoko", "Kotwa", "Bhora", "Mutawatawa"],
    },
    "Corridor 5": {
        "id": "corridor_5",
        "name": "East to Mutare and Chipinge",
        "route_label": "Route 5 East to Mutare and Chipinge",
        "stop_count": 7,
        "stops": ["Ruwa", "Marondera", "Rusape", "Mutare", "Chipinge", "Wedza", "Murambinda"],
    },
    "Corridor 6": {
        "id": "corridor_6",
        "name": "South to Masvingo and beyond",
        "route_label": "Route 6 South to Masvingo and beyond",
        "stop_count": 11,
        "stops": [
            "Beatrice", "Chivhu", "Masvingo", "Rutenga", "Mvuma", "Gutu",
            "Nyika", "Zaka", "Chiredzi", "Zvishavane", "Mberengwa"
        ],
    },
    "Corridor 7": {
        "id": "corridor_7",
        "name": "Local / Harare Route",
        "route_label": "Route 7 Local / Harare Route",
        "stop_count": 7,
        "stops": ["Harare", "Workington", "Southerton", "Graniteside", "Msasa", "Chitungwiza", "Local"],
    }
}


# Normalized minimum sales extracted directly from CITY SALES MINIMUMS.xlsx & TRANSPORT COSTING FORMULA.xlsx
# Required minimums follow the formula: Total Expense / 0.04 (Expense budgeted at 4% of sales)
CITY_MINIMUMS: Dict[str, Dict[str, Any]] = {
    # Corridor 1: West to Bulawayo (7 stops)
    "norton": {"min_sales": 2327.34, "van_min": 3827.34, "distance_km": 42.0, "route": "Route 1 West to Bulawayo", "corridor": "Corridor 1"},
    "chegutu": {"min_sales": 4761.72, "van_min": 6261.72, "distance_km": 108.0, "route": "Route 1 West to Bulawayo", "corridor": "Corridor 1"},
    "kadoma": {"min_sales": 5498.44, "van_min": 6998.44, "distance_km": 144.0, "route": "Route 1 West to Bulawayo", "corridor": "Corridor 1"},
    "kwekwe": {"min_sales": 7996.88, "van_min": 9496.88, "distance_km": 216.0, "route": "Route 1 West to Bulawayo", "corridor": "Corridor 1"},
    "gweru": {"min_sales": 9822.66, "van_min": 11322.66, "distance_km": 278.0, "route": "Route 1 West to Bulawayo", "corridor": "Corridor 1"},
    "bulawayo": {"min_sales": 16211.72, "van_min": 16961.72, "distance_km": 442.0, "route": "Route 1 West to Bulawayo", "corridor": "Corridor 1"},
    "gokwe": {"min_sales": 13200.78, "van_min": 13950.78, "distance_km": 342.0, "route": "Route 1 West to Bulawayo", "corridor": "Corridor 1"},

    # Corridor 2: Northwest to Karoi (5 stops)
    "murambedzi": {"min_sales": 3672.66, "van_min": 5172.66, "distance_km": 112.0, "route": "Route 2 Northwest to Karoi", "corridor": "Corridor 2"},
    "banket": {"min_sales": 3928.91, "van_min": 5428.91, "distance_km": 95.0, "route": "Route 2 Northwest to Karoi", "corridor": "Corridor 2"},
    "chinhoyi": {"min_sales": 4665.63, "van_min": 6165.63, "distance_km": 118.0, "route": "Route 2 Northwest to Karoi", "corridor": "Corridor 2"},
    "karoi": {"min_sales": 8684.38, "van_min": 9434.38, "distance_km": 204.0, "route": "Route 2 Northwest to Karoi", "corridor": "Corridor 2"},
    "magunje": {"min_sales": 9278.12, "van_min": 10778.12, "distance_km": 236.0, "route": "Route 2 Northwest to Karoi", "corridor": "Corridor 2"},

    # Corridor 3: North to Guruve and Mt Darwin (8 stops)
    "domboshawa": {"min_sales": 1910.94, "van_min": 3410.94, "distance_km": 34.0, "route": "Route 3 North to Guruve and Mt Darwin", "corridor": "Corridor 3"},
    "mazowe": {"min_sales": 2295.31, "van_min": 3795.31, "distance_km": 40.0, "route": "Route 3 North to Guruve and Mt Darwin", "corridor": "Corridor 3"},
    "glendale": {"min_sales": 3352.34, "van_min": 4852.34, "distance_km": 66.0, "route": "Route 3 North to Guruve and Mt Darwin", "corridor": "Corridor 3"},
    "bindura": {"min_sales": 3704.69, "van_min": 5204.69, "distance_km": 88.0, "route": "Route 3 North to Guruve and Mt Darwin", "corridor": "Corridor 3"},
    "madziva": {"min_sales": 4729.69, "van_min": 6229.69, "distance_km": 138.0, "route": "Route 3 North to Guruve and Mt Darwin", "corridor": "Corridor 3"},
    "mt darwin": {"min_sales": 5946.88, "van_min": 7446.88, "distance_km": 162.0, "route": "Route 3 North to Guruve and Mt Darwin", "corridor": "Corridor 3"},
    "mvurwi": {"min_sales": 4025.00, "van_min": 5525.00, "distance_km": 102.0, "route": "Route 3 North to Guruve and Mt Darwin", "corridor": "Corridor 3"},
    "guruve": {"min_sales": 5306.25, "van_min": 6806.25, "distance_km": 152.0, "route": "Route 3 North to Guruve and Mt Darwin", "corridor": "Corridor 3"},

    # Corridor 4: Northeast to Kotwa (6 stops)
    "juru": {"min_sales": 2551.56, "van_min": 4051.56, "distance_km": 54.0, "route": "Route 4 Northeast to Kotwa", "corridor": "Corridor 4"},
    "bhora": {"min_sales": 4633.59, "van_min": 6133.59, "distance_km": 48.0, "route": "Route 4 Northeast to Kotwa", "corridor": "Corridor 4"},
    "murewa": {"min_sales": 3832.81, "van_min": 5332.81, "distance_km": 88.0, "route": "Route 4 Northeast to Kotwa", "corridor": "Corridor 4"},
    "mutoko": {"min_sales": 5498.44, "van_min": 6998.44, "distance_km": 142.0, "route": "Route 4 Northeast to Kotwa", "corridor": "Corridor 4"},
    "kotwa": {"min_sales": 8060.94, "van_min": 9560.94, "distance_km": 218.0, "route": "Route 4 Northeast to Kotwa", "corridor": "Corridor 4"},
    "mutawatawa": {"min_sales": 5754.69, "van_min": 7254.69, "distance_km": 165.0, "route": "Route 4 Northeast to Kotwa", "corridor": "Corridor 4"},

    # Corridor 5: East to Mutare and Chipinge (7 stops)
    "ruwa": {"min_sales": 1686.72, "van_min": 3186.72, "distance_km": 24.0, "route": "Route 5 East to Mutare and Chipinge", "corridor": "Corridor 5"},
    "marondera": {"min_sales": 3320.31, "van_min": 4820.31, "distance_km": 74.0, "route": "Route 5 East to Mutare and Chipinge", "corridor": "Corridor 5"},
    "wedza": {"min_sales": 5754.69, "van_min": 7254.69, "distance_km": 132.0, "route": "Route 5 East to Mutare and Chipinge", "corridor": "Corridor 5"},
    "hwedza": {"min_sales": 5754.69, "van_min": 7254.69, "distance_km": 132.0, "route": "Route 5 East to Mutare and Chipinge", "corridor": "Corridor 5"},
    "rusape": {"min_sales": 6459.38, "van_min": 7959.38, "distance_km": 172.0, "route": "Route 5 East to Mutare and Chipinge", "corridor": "Corridor 5"},
    "mutare": {"min_sales": 10542.19, "van_min": 11292.19, "distance_km": 265.0, "route": "Route 5 East to Mutare and Chipinge", "corridor": "Corridor 5"},
    "chipinge": {"min_sales": 18806.25, "van_min": 19556.25, "distance_km": 448.0, "route": "Route 5 East to Mutare and Chipinge", "corridor": "Corridor 5"},
    "murambinda": {"min_sales": 10239.06, "van_min": 11739.06, "distance_km": 210.0, "route": "Route 5 East to Mutare and Chipinge", "corridor": "Corridor 5"},

    # Corridor 6: South to Masvingo and beyond (11 stops)
    "beatrice": {"min_sales": 2711.72, "van_min": 4211.72, "distance_km": 54.0, "route": "Route 6 South to Masvingo and beyond", "corridor": "Corridor 6"},
    "chivhu": {"min_sales": 5466.41, "van_min": 6966.41, "distance_km": 142.0, "route": "Route 6 South to Masvingo and beyond", "corridor": "Corridor 6"},
    "mvuma": {"min_sales": 7100.00, "van_min": 8600.00, "distance_km": 194.0, "route": "Route 6 South to Masvingo and beyond", "corridor": "Corridor 6"},
    "gutu": {"min_sales": 9453.12, "van_min": 10203.12, "distance_km": 234.0, "route": "Route 6 South to Masvingo and beyond", "corridor": "Corridor 6"},
    "masvingo": {"min_sales": 11535.16, "van_min": 12285.16, "distance_km": 296.0, "route": "Route 6 South to Masvingo and beyond", "corridor": "Corridor 6"},
    "nyika": {"min_sales": 14161.72, "van_min": 14911.72, "distance_km": 378.0, "route": "Route 6 South to Masvingo and beyond", "corridor": "Corridor 6"},
    "zaka": {"min_sales": 14321.88, "van_min": 15071.88, "distance_km": 382.0, "route": "Route 6 South to Masvingo and beyond", "corridor": "Corridor 6"},
    "zvishavane": {"min_sales": 12720.31, "van_min": 13470.31, "distance_km": 394.0, "route": "Route 6 South to Masvingo and beyond", "corridor": "Corridor 6"},
    "chiredzi": {"min_sales": 16243.75, "van_min": 16993.75, "distance_km": 438.0, "route": "Route 6 South to Masvingo and beyond", "corridor": "Corridor 6"},
    "mberengwa": {"min_sales": 15122.66, "van_min": 15872.66, "distance_km": 432.0, "route": "Route 6 South to Masvingo and beyond", "corridor": "Corridor 6"},
    "rutenga": {"min_sales": 15763.28, "van_min": 16513.28, "distance_km": 446.0, "route": "Route 6 South to Masvingo and beyond", "corridor": "Corridor 6"},

    # Corridor 7: Local / Harare Route (7 stops)
    "local": {"min_sales": 2201.56, "van_min": 3701.56, "distance_km": 15.0, "route": "Route 7 Local / Harare Route", "corridor": "Corridor 7"},
    "harare": {"min_sales": 2201.56, "van_min": 3701.56, "distance_km": 6.0, "route": "Route 7 Local / Harare Route", "corridor": "Corridor 7"},
    "workington": {"min_sales": 2201.56, "van_min": 3701.56, "distance_km": 5.0, "route": "Route 7 Local / Harare Route", "corridor": "Corridor 7"},
    "southerton": {"min_sales": 2201.56, "van_min": 3701.56, "distance_km": 4.0, "route": "Route 7 Local / Harare Route", "corridor": "Corridor 7"},
    "graniteside": {"min_sales": 2201.56, "van_min": 3701.56, "distance_km": 8.0, "route": "Route 7 Local / Harare Route", "corridor": "Corridor 7"},
    "msasa": {"min_sales": 2201.56, "van_min": 3701.56, "distance_km": 16.0, "route": "Route 7 Local / Harare Route", "corridor": "Corridor 7"},
    "chitungwiza": {"min_sales": 2201.56, "van_min": 3701.56, "distance_km": 28.0, "route": "Route 7 Local / Harare Route", "corridor": "Corridor 7"},

    # Remote / Outlier routes preserved
    "binga": {"min_sales": 12448.05, "van_min": 13198.05, "distance_km": 874.0, "route": "Binga", "corridor": "Outlier"},
    "sanyati": {"min_sales": 9485.16, "van_min": 10235.16, "distance_km": 228.0, "route": "Sanyati", "corridor": "Outlier"},
    "birchenough": {"min_sales": 14289.84, "van_min": 15039.84, "distance_km": 382.0, "route": "Birchenough", "corridor": "Outlier"},
    "shurugwi": {"min_sales": 9587.50, "van_min": 10337.50, "distance_km": 314.0, "route": "Shurugwi", "corridor": "Outlier"},
    "nyanga": {"min_sales": 11139.06, "van_min": 11889.06, "distance_km": 274.0, "route": "Nyanga", "corridor": "Outlier"},
    "ruwangwe": {"min_sales": 10990.62, "van_min": 11740.62, "distance_km": 364.0, "route": "Ruwangwe", "corridor": "Outlier"}
}

# Aliases for flexible matching
CITY_ALIASES: Dict[str, str] = {
    "wedza": "wedza",
    "hwedza": "wedza",
    "byo": "bulawayo",
    "jerera": "zaka",
    "zaka / jerera": "zaka",
    "zaka/jerera": "zaka",
    "nyika (bikita)": "nyika",
    "bikita": "nyika",
    "darwin": "mt darwin",
    "mount darwin": "mt darwin",
    "hre": "harare",
    "wlk": "workington",
    "walk": "workington",
    "chit": "chitungwiza",
    "chitung": "chitungwiza",
}


def normalize_city_name(raw_name: str) -> str:
    """Cleans and maps raw city text to normalized canonical name."""
    if not raw_name:
        return ""
    clean = re.sub(r"[^\w\s\(\)/]", "", raw_name.lower()).strip()
    clean = re.sub(r"\s+", " ", clean)

    # 1. Direct exact match in CITY_MINIMUMS
    if clean in CITY_MINIMUMS:
        return clean

    # 2. Direct exact match in CITY_ALIASES
    if clean in CITY_ALIASES:
        return CITY_ALIASES[clean]

    # 3. Alias word-boundary match (e.g., "zaka / jerera", "harare cbd")
    for alias, canonical in CITY_ALIASES.items():
        pattern = r"\b" + re.escape(alias) + r"\b"
        if re.search(pattern, clean):
            return canonical

    # 4. Canonical word-boundary match within text (e.g. "deliver to gweru depot")
    for canonical in CITY_MINIMUMS:
        pattern = r"\b" + re.escape(canonical) + r"\b"
        if re.search(pattern, clean):
            return canonical

    return clean


def get_corridor_by_city(city_name: str) -> Optional[Dict[str, Any]]:
    """
    Finds the master delivery corridor corresponding to a given city/stop name.
    Returns the corridor dict containing 'id', 'name', 'route_label', 'stops',
    or None if the city is not part of any recognized corridor.
    """
    canonical = normalize_city_name(city_name)
    if canonical in CITY_MINIMUMS:
        corridor_key = CITY_MINIMUMS[canonical].get("corridor")
        if corridor_key and corridor_key in MASTER_CORRIDORS:
            return MASTER_CORRIDORS[corridor_key]

    clean = (city_name or "").strip().lower()
    for corridor_key, info in MASTER_CORRIDORS.items():
        if any(clean == s.lower() or s.lower() in clean for s in info.get("stops", [])):
            return info
    return None


def get_corridor(corridor_id_or_number: str) -> Optional[Dict[str, Any]]:
    """
    Retrieves corridor details by key (e.g. 'Corridor 1'), id (e.g. 'corridor_1'),
    number (e.g. '1', 1), or partial name.
    """
    query = str(corridor_id_or_number).strip().lower()
    for key, data in MASTER_CORRIDORS.items():
        if (
            key.lower() == query
            or data["id"].lower() == query
            or query == str(key.replace("Corridor ", "")).strip().lower()
            or query in key.lower()
            or query in data["name"].lower()
            or query in data["route_label"].lower()
        ):
            return data
    return None


def get_city_minimum(city_name: str, is_van_sales: bool = False) -> Dict[str, Any]:
    """Retrieves required minimum sales, corridor, and route info for a given destination."""
    canonical = normalize_city_name(city_name)

    # 1. Check dynamic database-backed config cache first
    try:
        from app.services.config_service import get_cached_city_rule
        cached_rule = get_cached_city_rule(canonical)
        if cached_rule:
            required_min = cached_rule["van_min"] if is_van_sales else cached_rule["min_sales"]
            corridor_key = cached_rule.get("corridor")
            corridor_data = MASTER_CORRIDORS.get(corridor_key) if corridor_key else None
            return {
                "canonical_city": cached_rule.get("city_name", canonical.title()),
                "route": cached_rule.get("route", ""),
                "corridor": corridor_key,
                "corridor_name": corridor_data["name"] if corridor_data else None,
                "required_minimum": float(required_min),
                "is_van_sales": is_van_sales
            }
    except Exception:
        pass

    if canonical not in CITY_MINIMUMS:
        raise CityNotFoundError(f"Destination area '{city_name}' is not configured in minimum sales rules.")

    entry = CITY_MINIMUMS[canonical]
    required_min = entry["van_min"] if is_van_sales else entry["min_sales"]
    corridor_key = entry.get("corridor")
    corridor_data = MASTER_CORRIDORS.get(corridor_key) if corridor_key else None
    return {
        "canonical_city": canonical.title(),
        "route": entry["route"],
        "corridor": corridor_key,
        "corridor_name": corridor_data["name"] if corridor_data else None,
        "required_minimum": required_min,
        "is_van_sales": is_van_sales
    }


def calculate_trip_approval(actual_sales: float, destination: str, is_van_sales: bool = False) -> Dict[str, Any]:
    """
    Evaluates whether a trip meets the required minimum sales.
    If trip value >= required minimum: Approved, transport charge = $0.
    If trip value < required minimum: Shortfall = Required - Actual, Transport charge = Shortfall * 0.04 (4%).
    """
    city_info = get_city_minimum(destination, is_van_sales)
    required_min = float(city_info["required_minimum"])
    actual = float(actual_sales)

    if actual >= required_min:
        return {
            "approved": True,
            "city": city_info["canonical_city"],
            "route": city_info["route"],
            "corridor": city_info.get("corridor"),
            "corridor_name": city_info.get("corridor_name"),
            "trip_value": round(actual, 2),
            "required_minimum": round(required_min, 2),
            "shortfall": 0.00,
            "transport_charge": 0.00
        }
    else:
        shortfall = round(required_min - actual, 2)
        charge = round(shortfall * 0.04, 2)
        return {
            "approved": False,
            "city": city_info["canonical_city"],
            "route": city_info["route"],
            "corridor": city_info.get("corridor"),
            "corridor_name": city_info.get("corridor_name"),
            "trip_value": round(actual, 2),
            "required_minimum": round(required_min, 2),
            "shortfall": shortfall,
            "transport_charge": charge
        }
