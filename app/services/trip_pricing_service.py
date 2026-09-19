import re
from typing import Optional, Dict, Any


class CityNotFoundError(Exception):
    """Raised when a city or area cannot be mapped to the minimum sales rule."""
    pass


# Normalized minimum sales extracted directly from CITY SALES MINIMUMS.xlsx & TRANSPORT COSTING FORMULA.xlsx
# Required minimums follow the formula: Total Expense / 0.04 (Expense budgeted at 4% of sales)
CITY_MINIMUMS: Dict[str, Dict[str, Any]] = {
    "norton": {"min_sales": 2327.34, "van_min": 3827.34, "route": "Route 1 Byo"},
    "chegutu": {"min_sales": 4761.72, "van_min": 6261.72, "route": "Route 1 Byo"},
    "kadoma": {"min_sales": 5498.44, "van_min": 6998.44, "route": "Route 1 Byo"},
    "kwekwe": {"min_sales": 7996.88, "van_min": 9496.88, "route": "Route 1 Byo"},
    "gweru": {"min_sales": 9822.66, "van_min": 11322.66, "route": "Route 1 Byo"},
    "bulawayo": {"min_sales": 16211.72, "van_min": 16961.72, "route": "Route 1 Byo"},
    "gokwe": {"min_sales": 13200.78, "van_min": 13950.78, "route": "Route 1 Byo"},
    "murambedzi": {"min_sales": 3672.66, "van_min": 5172.66, "route": "Route 2 Karoi"},
    "banket": {"min_sales": 3928.91, "van_min": 5428.91, "route": "Route 2 Karoi"},
    "chinhoyi": {"min_sales": 4665.63, "van_min": 6165.63, "route": "Route 2 Karoi"},
    "karoi": {"min_sales": 8684.38, "van_min": 9434.38, "route": "Route 2 Karoi"},
    "magunje": {"min_sales": 9278.12, "van_min": 10778.12, "route": "Route 2 Karoi"},
    "ruwa": {"min_sales": 1686.72, "van_min": 3186.72, "route": "Route 3 Mtr"},
    "marondera": {"min_sales": 3320.31, "van_min": 4820.31, "route": "Route 3 Mtr"},
    "hwedza": {"min_sales": 5754.69, "van_min": 7254.69, "route": "Route 3 Mtr"},
    "rusape": {"min_sales": 6459.38, "van_min": 7959.38, "route": "Route 3 Mtr"},
    "mutare": {"min_sales": 10542.19, "van_min": 11292.19, "route": "Route 3 Mtr"},
    "chipinge": {"min_sales": 18806.25, "van_min": 19556.25, "route": "Route 3 Mtr"},
    "bhora": {"min_sales": 4633.59, "van_min": 6133.59, "route": "Route 4 Mutoko"},
    "juru": {"min_sales": 2551.56, "van_min": 4051.56, "route": "Route 4 Mutoko"},
    "murewa": {"min_sales": 3832.81, "van_min": 5332.81, "route": "Route 4 Mutoko"},
    "mutoko": {"min_sales": 5498.44, "van_min": 6998.44, "route": "Route 4 Mutoko"},
    "kotwa": {"min_sales": 8060.94, "van_min": 9560.94, "route": "Route 4 Mutoko"},
    "mutawatawa": {"min_sales": 5754.69, "van_min": 7254.69, "route": "Route 4 Mutoko"},
    "domboshawa": {"min_sales": 1910.94, "van_min": 3410.94, "route": "Route 5 Bindura"},
    "mazowe": {"min_sales": 2295.31, "van_min": 3795.31, "route": "Route 5 Bindura"},
    "glendale": {"min_sales": 3352.34, "van_min": 4852.34, "route": "Route 5 Bindura"},
    "bindura": {"min_sales": 3704.69, "van_min": 5204.69, "route": "Route 5 Bindura"},
    "madziva": {"min_sales": 4729.69, "van_min": 6229.69, "route": "Route 5 Bindura"},
    "mt darwin": {"min_sales": 5946.88, "van_min": 7446.88, "route": "Route 5 Bindura"},
    "mvurwi": {"min_sales": 4025.00, "van_min": 5525.00, "route": "Route 5 Bindura"},
    "guruve": {"min_sales": 5306.25, "van_min": 6806.25, "route": "Route 5 Bindura"},
    "beatrice": {"min_sales": 2711.72, "van_min": 4211.72, "route": "Route 7 Masvingo"},
    "chivhu": {"min_sales": 5466.41, "van_min": 6966.41, "route": "Route 7 Masvingo"},
    "mvuma": {"min_sales": 7100.00, "van_min": 8600.00, "route": "Route 7 Masvingo"},
    "murambinda": {"min_sales": 10239.06, "van_min": 11739.06, "route": "Route 7 Masvingo"},
    "masvingo": {"min_sales": 11535.16, "van_min": 12285.16, "route": "Route 7 Masvingo"},
    "gutu": {"min_sales": 9453.12, "van_min": 10203.12, "route": "Route 7 Masvingo"},
    "nyika": {"min_sales": 14161.72, "van_min": 14911.72, "route": "Route 7 Masvingo"},
    "zaka": {"min_sales": 14321.88, "van_min": 15071.88, "route": "Route 7 Masvingo"},
    "zvishavane": {"min_sales": 12720.31, "van_min": 13470.31, "route": "Route 7 Masvingo"},
    "chiredzi": {"min_sales": 16243.75, "van_min": 16993.75, "route": "Route 7 Masvingo"},
    "mberengwa": {"min_sales": 15122.66, "van_min": 15872.66, "route": "Route 7 Masvingo"},
    "rutenga": {"min_sales": 15763.28, "van_min": 16513.28, "route": "Route 7 Masvingo"},
    "local": {"min_sales": 2201.56, "van_min": 3701.56, "route": "Local"},
    "binga": {"min_sales": 12448.05, "van_min": 13198.05, "route": "Binga"},
    "sanyati": {"min_sales": 9485.16, "van_min": 10235.16, "route": "Sanyati"},
    "birchenough": {"min_sales": 14289.84, "van_min": 15039.84, "route": "Birchenough"},
    "shurugwi": {"min_sales": 9587.50, "van_min": 10337.50, "route": "Shurugwi"},
    "nyanga": {"min_sales": 11139.06, "van_min": 11889.06, "route": "Nyanga"},
    "ruwangwe": {"min_sales": 10990.62, "van_min": 11740.62, "route": "Ruwangwe"}
}

# Aliases for flexible matching
CITY_ALIASES: Dict[str, str] = {
    "wedza": "hwedza",
    "byo": "bulawayo",
    "jerera": "zaka",
    "zaka / jerera": "zaka",
    "zaka/jerera": "zaka",
    "nyika (bikita)": "nyika",
    "bikita": "nyika",
    "darwin": "mt darwin",
    "mount darwin": "mt darwin",
    "harare": "local"
}


def normalize_city_name(raw_name: str) -> str:
    """Cleans and maps raw city text to normalized canonical name."""
    if not raw_name:
        return ""
    clean = re.sub(r"[^\w\s\(\)/]", "", raw_name.lower()).strip()
    clean = re.sub(r"\s+", " ", clean)

    if clean in CITY_ALIASES:
        return CITY_ALIASES[clean]

    for alias, canonical in CITY_ALIASES.items():
        if alias in clean:
            return canonical

    for canonical in CITY_MINIMUMS:
        if canonical in clean or clean in canonical:
            return canonical

    return clean


def get_city_minimum(city_name: str, is_van_sales: bool = False) -> Dict[str, Any]:
    """Retrieves required minimum sales and route info for a given destination."""
    canonical = normalize_city_name(city_name)
    if canonical not in CITY_MINIMUMS:
        raise CityNotFoundError(f"Destination area '{city_name}' is not configured in minimum sales rules.")

    entry = CITY_MINIMUMS[canonical]
    required_min = entry["van_min"] if is_van_sales else entry["min_sales"]
    return {
        "canonical_city": canonical.title(),
        "route": entry["route"],
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
            "trip_value": round(actual, 2),
            "required_minimum": round(required_min, 2),
            "shortfall": shortfall,
            "transport_charge": charge
        }
