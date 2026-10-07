# -*- coding: utf-8 -*-
"""
Centralized Configuration & Route Rules Service for Tagoneswa Operations.
Manages database-backed system settings (fuel price, allowance rates, etc.)
and city minimum sales rules with in-memory caching for zero latency.
"""
import logging
import datetime
from typing import Dict, Any, Optional, List, Tuple
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update

from app.database import (
    SystemSetting, SystemSettingHistory, FleetRouteRule, WebUser, AuditLog, UserCustomPermission, RevokedUser
)

logger = logging.getLogger("config_service")

# In-memory synchronized caches
SETTINGS_CACHE: Dict[str, Any] = {
    "fuel_price_usd": 1.55,
    "expense_budget_pct": 0.04,
    "meal_rate_usd": 2.00,
    "accommodation_rate_usd": 15.00,
    "van_minimum_surcharge": 1500.00
}

ROUTE_RULES_CACHE: Dict[str, Dict[str, Any]] = {}

DEFAULT_SYSTEM_SETTINGS = [
    {
        "key": "fuel_price_usd",
        "category": "PRICING",
        "value": "1.55",
        "data_type": "float",
        "label": "Diesel Fuel Price ($ / Liter)",
        "description": "Standard diesel fuel price used for fleet trip costing and corridor minimum calculations."
    },
    {
        "key": "expense_budget_pct",
        "category": "PRICING",
        "value": "0.04",
        "data_type": "float",
        "label": "Expense Budget Allocation (%)",
        "description": "Expense percentage budgeted against total sales revenue (default 0.04 for 4%)."
    },
    {
        "key": "meal_rate_usd",
        "category": "ALLOWANCES",
        "value": "2.00",
        "data_type": "float",
        "label": "Meal Allowance per Person ($)",
        "description": "Automated meal allowance rate per person per qualifying meal."
    },
    {
        "key": "accommodation_rate_usd",
        "category": "ALLOWANCES",
        "value": "15.00",
        "data_type": "float",
        "label": "Accommodation Allowance ($ / Night)",
        "description": "Nightly accommodation rate per crew member on overnight corridors."
    },
    {
        "key": "van_minimum_surcharge",
        "category": "PRICING",
        "value": "1500.00",
        "data_type": "float",
        "label": "Van Sales Minimum Surcharge ($)",
        "description": "Standard minimum sales surcharge added for van sales."
    }
]


def get_cached_setting(key: str, default: Any = None) -> Any:
    """Returns cached system setting value synchronously."""
    return SETTINGS_CACHE.get(key, default)


def get_fuel_price() -> float:
    """Returns active fuel price per liter in USD."""
    return float(SETTINGS_CACHE.get("fuel_price_usd", 1.55))


def get_meal_rate() -> float:
    """Returns active meal allowance per person in USD."""
    return float(SETTINGS_CACHE.get("meal_rate_usd", 2.00))


def get_accommodation_rate() -> float:
    """Returns active accommodation rate per night in USD."""
    return float(SETTINGS_CACHE.get("accommodation_rate_usd", 15.00))


def get_expense_budget_pct() -> float:
    """Returns active expense budget percentage (default 0.04)."""
    return float(SETTINGS_CACHE.get("expense_budget_pct", 0.04))


def get_van_minimum_surcharge() -> float:
    """Returns active van minimum surcharge in USD."""
    return float(SETTINGS_CACHE.get("van_minimum_surcharge", 1500.00))


def get_cached_city_rule(city_key: str) -> Optional[Dict[str, Any]]:
    """Returns cached route rule for a city key."""
    clean = (city_key or "").strip().lower()
    return ROUTE_RULES_CACHE.get(clean)


def get_all_cached_city_rules() -> List[Dict[str, Any]]:
    """Returns all cached route rules as a list."""
    return list(ROUTE_RULES_CACHE.values())


def sync_legacy_services():
    """Syncs cached settings into legacy service globals to guarantee backward compatibility."""
    try:
        from app.services import allowance_calculator
        allowance_calculator.MEAL_RATE_PER_PERSON = get_meal_rate()
        allowance_calculator.ACCOMMODATION_RATE_PER_PERSON = get_accommodation_rate()
    except Exception as e:
        logger.warning(f"Error syncing allowance_calculator: {e}")

    try:
        from app.services import trip_pricing_service
        for k, v in ROUTE_RULES_CACHE.items():
            if k in trip_pricing_service.CITY_MINIMUMS:
                trip_pricing_service.CITY_MINIMUMS[k]["min_sales"] = v["min_sales"]
                trip_pricing_service.CITY_MINIMUMS[k]["van_min"] = v["van_min"]
                if v.get("route"):
                    trip_pricing_service.CITY_MINIMUMS[k]["route"] = v["route"]
                if v.get("corridor"):
                    trip_pricing_service.CITY_MINIMUMS[k]["corridor"] = v["corridor"]
    except Exception as e:
        logger.warning(f"Error syncing trip_pricing_service: {e}")


async def load_settings_into_cache(session: AsyncSession):
    """Loads all system settings and route rules from the database into in-memory cache."""
    try:
        stmt_settings = select(SystemSetting)
        res_settings = await session.execute(stmt_settings)
        settings = res_settings.scalars().all()
        for s in settings:
            val = s.value
            if s.data_type == "float":
                val = float(val)
            elif s.data_type == "integer":
                val = int(val)
            elif s.data_type == "boolean":
                val = val.lower() in ("true", "1", "yes")
            SETTINGS_CACHE[s.key] = val

        stmt_rules = select(FleetRouteRule).where(FleetRouteRule.is_active == True)
        res_rules = await session.execute(stmt_rules)
        rules = res_rules.scalars().all()
        for r in rules:
            ROUTE_RULES_CACHE[r.city_key.lower()] = {
                "id": r.id,
                "city_key": r.city_key.lower(),
                "city_name": r.city_name,
                "corridor": r.corridor_name,
                "route": r.route_label or r.corridor_name,
                "distance_km": r.distance_km,
                "min_sales": r.min_sales,
                "van_min": r.van_min,
                "is_active": r.is_active,
                "updated_at": r.updated_at.strftime("%Y-%m-%d %H:%M") if r.updated_at else ""
            }

        sync_legacy_services()
        logger.info(f"Loaded {len(settings)} system settings and {len(rules)} route rules into memory cache.")

        # Synchronize roles, active sessions, and revocation blacklists from database into auth memory cache
        try:
            from app.auth import (
                load_all_user_custom_permissions, sync_db_roles_to_users_db,
                load_revocation_and_sessions, register_user_in_memory, USERS_DB
            )

            # 1. Fetch all revoked/blacklisted usernames
            res_rev = await session.execute(select(RevokedUser.username))
            revoked_list = [r[0].strip().lower() for r in res_rev.all() if r[0]]

            # 2. Fetch all WebUser records
            res_users = await session.execute(select(WebUser))
            all_web_users = res_users.scalars().all()

            roles_map = {}
            sessions_map = {}
            status_map = {}

            for wu in all_web_users:
                uname = wu.username.strip().lower()
                status_map[uname] = bool(wu.is_active)
                if wu.is_active:
                    roles_map[uname] = wu.role
                if wu.current_session_token:
                    sessions_map[uname] = wu.current_session_token

                # Register any database-persisted user into runtime USERS_DB
                if uname not in USERS_DB:
                    register_user_in_memory(uname, {
                        "password_hash": wu.password_hash,
                        "role": wu.role,
                        "name": wu.full_name,
                        "company": wu.company,
                        "phone": wu.phone,
                        "is_active": wu.is_active
                    })

            # Load into auth security engine
            load_revocation_and_sessions(revoked_list, sessions_map, status_map)
            if roles_map:
                sync_db_roles_to_users_db(roles_map)

            logger.info(f"Loaded {len(all_web_users)} web user(s), {len(sessions_map)} active session(s), and {len(revoked_list)} revoked account(s).")

            # 3. Sync user custom permissions from database into auth memory cache
            stmt_perms = select(WebUser.username, UserCustomPermission.permission_key, UserCustomPermission.is_granted).join(
                UserCustomPermission, WebUser.id == UserCustomPermission.user_id
            )
            res_perms = await session.execute(stmt_perms)
            perms_map = {}
            for uname, pkey, is_g in res_perms.all():
                u = uname.strip().lower()
                if u not in perms_map:
                    perms_map[u] = {}
                perms_map[u][pkey] = is_g
            load_all_user_custom_permissions(perms_map)
            logger.info(f"Loaded delegated permissions for {len(perms_map)} user(s) into memory cache.")
        except Exception as perm_err:
            logger.warning(f"Note on user custom permissions/roles load: {perm_err}")
    except Exception as e:
        logger.warning(f"Failed to load settings into cache: {e}")


async def update_system_setting(
    session: AsyncSession,
    key: str,
    new_value: Any,
    changed_by: str = "Admin",
    reason: str = "Manual configuration update"
) -> bool:
    """Updates a system setting with history and audit logging."""
    str_val = str(new_value).strip()
    stmt = select(SystemSetting).where(SystemSetting.key == key)
    res = await session.execute(stmt)
    setting = res.scalars().first()

    old_val = setting.value if setting else None
    if setting:
        setting.value = str_val
        setting.updated_by = changed_by
        setting.updated_at = datetime.datetime.utcnow()
    else:
        setting = SystemSetting(
            key=key,
            value=str_val,
            label=key.replace("_", " ").title(),
            updated_by=changed_by,
            updated_at=datetime.datetime.utcnow()
        )
        session.add(setting)

    # Add history entry
    hist = SystemSettingHistory(
        setting_key=key,
        previous_value=old_val,
        new_value=str_val,
        changed_by=changed_by,
        change_reason=reason,
        effective_from=datetime.datetime.utcnow(),
        created_at=datetime.datetime.utcnow()
    )
    session.add(hist)

    # Add audit log
    audit = AuditLog(
        username=changed_by,
        action="UPDATE_SETTING",
        module="CONFIG",
        entity_id=key,
        previous_value={"value": old_val},
        new_value={"value": str_val},
        remarks=reason,
        created_at=datetime.datetime.utcnow()
    )
    session.add(audit)
    await session.commit()

    # Update in-memory cache
    if setting.data_type == "float":
        SETTINGS_CACHE[key] = float(str_val)
    elif setting.data_type == "integer":
        SETTINGS_CACHE[key] = int(str_val)
    else:
        SETTINGS_CACHE[key] = str_val

    sync_legacy_services()
    return True


async def update_city_rule(
    session: AsyncSession,
    city_key: str,
    min_sales: float,
    van_min: float,
    distance_km: Optional[float] = None,
    updated_by: str = "Admin",
    reason: str = "City minimum updated"
) -> bool:
    """Updates minimum sales thresholds for a specific city."""
    clean_key = city_key.strip().lower()
    stmt = select(FleetRouteRule).where(FleetRouteRule.city_key == clean_key)
    res = await session.execute(stmt)
    rule = res.scalars().first()

    if not rule:
        return False

    old_vals = {"min_sales": rule.min_sales, "van_min": rule.van_min}
    rule.min_sales = round(float(min_sales), 2)
    rule.van_min = round(float(van_min), 2)
    if distance_km is not None:
        rule.distance_km = round(float(distance_km), 2)
    rule.updated_by = updated_by
    rule.updated_at = datetime.datetime.utcnow()

    new_vals = {"min_sales": rule.min_sales, "van_min": rule.van_min}

    audit = AuditLog(
        username=updated_by,
        action="UPDATE_ROUTE_MINIMUM",
        module="CONFIG",
        entity_id=clean_key,
        previous_value=old_vals,
        new_value=new_vals,
        remarks=reason,
        created_at=datetime.datetime.utcnow()
    )
    session.add(audit)
    await session.commit()

    # Update cache
    if clean_key in ROUTE_RULES_CACHE:
        ROUTE_RULES_CACHE[clean_key]["min_sales"] = rule.min_sales
        ROUTE_RULES_CACHE[clean_key]["van_min"] = rule.van_min
        if distance_km is not None:
            ROUTE_RULES_CACHE[clean_key]["distance_km"] = rule.distance_km

    sync_legacy_services()
    return True


async def recalculate_all_city_minimums(
    session: AsyncSession,
    new_fuel_price: float,
    updated_by: str = "Admin",
    reason: str = "Batch recalculation from fuel price adjustment"
) -> Dict[str, Any]:
    """
    Recalculates minimum sales for all 45 cities based on a new fuel price.
    Formula: Total Expense / 0.04 (Expense = Fuel Cost + Fixed Road / Allowance Allocations).
    Reflects the ratio of new_fuel_price / old_fuel_price proportionally on the fuel component.
    """
    old_fuel_price = get_fuel_price()
    if old_fuel_price <= 0:
        old_fuel_price = 1.55

    fuel_ratio = new_fuel_price / old_fuel_price

    # 1. Update fuel price setting
    await update_system_setting(
        session, "fuel_price_usd", new_fuel_price,
        changed_by=updated_by, reason=f"Fuel price adjusted to ${new_fuel_price:.2f}/L"
    )

    # 2. Adjust city minimums proportionally (fuel contributes ~65% of trip expense)
    stmt = select(FleetRouteRule).where(FleetRouteRule.is_active == True)
    res = await session.execute(stmt)
    rules = res.scalars().all()

    updated_cities = []
    for r in rules:
        # Weighted fuel adjustment: 65% fuel, 35% fixed overheads
        adjustment_factor = 0.35 + (0.65 * fuel_ratio)
        new_min = round(r.min_sales * adjustment_factor, 2)
        diff = round(r.van_min - r.min_sales, 2)
        new_van = round(new_min + diff, 2)

        r.min_sales = new_min
        r.van_min = new_van
        r.updated_by = updated_by
        r.updated_at = datetime.datetime.utcnow()

        updated_cities.append({
            "city_key": r.city_key,
            "city_name": r.city_name,
            "corridor": r.corridor_name,
            "new_min_sales": new_min,
            "new_van_min": new_van
        })

    audit = AuditLog(
        username=updated_by,
        action="BATCH_RECALCULATE_MINIMUMS",
        module="CONFIG",
        entity_id="ALL_CITIES",
        previous_value={"fuel_price": old_fuel_price},
        new_value={"fuel_price": new_fuel_price, "cities_count": len(updated_cities)},
        remarks=reason,
        created_at=datetime.datetime.utcnow()
    )
    session.add(audit)
    await session.commit()

    # Refresh cache
    await load_settings_into_cache(session)

    return {
        "status": "success",
        "fuel_price": new_fuel_price,
        "updated_cities_count": len(updated_cities),
        "cities": updated_cities
    }


async def seed_config_and_routes(session: AsyncSession):
    """Seeds initial SystemSetting, FleetRouteRule, and WebUser records if empty."""
    # 1. Seed System Settings
    res_s = await session.execute(select(SystemSetting.key).limit(1))
    if not res_s.scalars().first():
        for s_data in DEFAULT_SYSTEM_SETTINGS:
            s_obj = SystemSetting(
                key=s_data["key"],
                category=s_data["category"],
                value=s_data["value"],
                data_type=s_data["data_type"],
                label=s_data["label"],
                description=s_data["description"],
                updated_by="System Initializer",
                updated_at=datetime.datetime.utcnow()
            )
            session.add(s_obj)
        await session.commit()
        logger.info("Seeded initial default system settings.")

    # 2. Seed Fleet Route Rules from CITY_MINIMUMS & MASTER_CORRIDORS
    res_r = await session.execute(select(FleetRouteRule.id).limit(1))
    if not res_r.scalars().first():
        from app.services.trip_pricing_service import CITY_MINIMUMS
        for city_key, data in CITY_MINIMUMS.items():
            rule = FleetRouteRule(
                city_key=city_key.lower(),
                city_name=city_key.title(),
                corridor_name=data.get("corridor", "General"),
                route_label=data.get("route", ""),
                distance_km=0.0,
                min_sales=float(data.get("min_sales", 0.0)),
                van_min=float(data.get("van_min", 0.0)),
                is_active=True,
                updated_by="System Initializer",
                updated_at=datetime.datetime.utcnow()
            )
            session.add(rule)
        await session.commit()
        logger.info(f"Seeded {len(CITY_MINIMUMS)} city route rules into fleet_route_rules table.")

    # 3. Seed Web Users from USERS_DB
    res_u = await session.execute(select(WebUser.id).limit(1))
    if not res_u.scalars().first():
        from app.auth import USERS_DB
        for uname, udata in USERS_DB.items():
            w_user = WebUser(
                username=uname,
                password_hash=udata["password"],  # Store plaintext or hash compatible
                full_name=udata["name"],
                role=udata["role"],
                is_active=True,
                created_at=datetime.datetime.utcnow(),
                updated_at=datetime.datetime.utcnow()
            )
            session.add(w_user)

        # Also add Accounts Manager and Logistics User explicitly if not present
        if "accounts" not in USERS_DB:
            session.add(WebUser(
                username="accounts",
                password_hash="Accounts@Tagoneswa2026!",
                full_name="Accounts & Finance Officer",
                role="ACCOUNTS_USER",
                is_active=True,
                created_at=datetime.datetime.utcnow(),
                updated_at=datetime.datetime.utcnow()
            ))

        await session.commit()
        logger.info("Seeded initial web users from USERS_DB.")

    # Load cache (generic settings, rules, active web user roles, and all user custom permissions)
    await load_settings_into_cache(session)


async def update_meal_rate(
    session: AsyncSession,
    new_meal_rate: float,
    updated_by: str = "Admin",
    reason: str = "Meal allowance rate updated"
) -> bool:
    """Updates meal rate allowance with history and audit logging."""
    val = round(float(new_meal_rate), 2)
    old_rate = get_meal_rate()
    await update_system_setting(
        session, "meal_rate_usd", val, changed_by=updated_by, reason=reason
    )
    audit = AuditLog(
        username=updated_by,
        action="UPDATE_MEAL_RATE",
        module="CONFIG",
        permission_used="manage_meal_rate",
        entity_id="meal_rate_usd",
        previous_value={"meal_rate_usd": old_rate},
        new_value={"meal_rate_usd": val},
        remarks=reason,
        created_at=datetime.datetime.utcnow()
    )
    session.add(audit)
    await session.commit()
    return True


async def update_accommodation_rate(
    session: AsyncSession,
    new_accom_rate: float,
    updated_by: str = "Admin",
    reason: str = "Accommodation allowance rate updated"
) -> bool:
    """Updates accommodation allowance rate with history and audit logging."""
    val = round(float(new_accom_rate), 2)
    old_rate = get_accommodation_rate()
    await update_system_setting(
        session, "accommodation_rate_usd", val, changed_by=updated_by, reason=reason
    )
    audit = AuditLog(
        username=updated_by,
        action="UPDATE_ACCOMMODATION_RATE",
        module="CONFIG",
        permission_used="manage_accommodation_rate",
        entity_id="accommodation_rate_usd",
        previous_value={"accommodation_rate_usd": old_rate},
        new_value={"accommodation_rate_usd": val},
        remarks=reason,
        created_at=datetime.datetime.utcnow()
    )
    session.add(audit)
    await session.commit()
    return True
