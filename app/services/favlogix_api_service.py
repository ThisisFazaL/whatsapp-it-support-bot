import re
import time
import json
import base64
import logging
from typing import Dict, Any, Optional, List
import httpx

from app.config import settings

logger = logging.getLogger("favlogix_api")


class FavlogixAPIError(Exception):
    """Base error for Favlogix API operations."""
    pass


class FavlogixAuthError(FavlogixAPIError):
    """Raised when authentication against Favlogix fails."""
    pass


class FavlogixTripNotFoundError(FavlogixAPIError):
    """Raised when the specified trip cannot be located."""
    pass


class FavlogixCalculationPendingError(FavlogixAPIError):
    """Raised when a trip has no active sales orders or cannot be valued."""
    pass


class FavlogixAPIService:
    """
    Direct background HTTP client for Favlogix ERP (Option 1 - Headless).
    Communicates directly with Favlogix backend without requiring
    a local browser, Chrome window, or display server.

    Supports dual modes:
    1. Modern New Platform (fio.favlogix.com): Dedicated `/api/tenant/inventory/packaging-list/trip-totals`
    2. Legacy Platform (erp.favlogix.com): PocketBase `/api/pb/api/collections/sales_order/records`
    """

    def __init__(self):
        self.api_url: str = settings.favlogix_api_url.rstrip("/")
        self.org_name_or_id: str = settings.favlogix_organization
        self.email: str = settings.favlogix_email
        self.password: str = settings.favlogix_password
        self.auth_token: str = settings.favlogix_auth_token
        self.token_expiry: float = 0.0
        self.resolved_org_id: Optional[str] = None
        self.cookies: Dict[str, str] = {}

        if self.auth_token:
            self.token_expiry = self._decode_token_expiry(self.auth_token)

    @property
    def is_fio(self) -> bool:
        """Returns True if connected to the new fio.favlogix.com platform."""
        return "fio" in self.api_url or "/tenant" in self.api_url or "fio" in getattr(settings, "favlogix_url", "")

    @property
    def base_url(self) -> str:
        """Normalized base URL without trailing slash."""
        # Ensure base URL ends with /api if connecting to fio
        clean = self.api_url.rstrip("/")
        if self.is_fio and not clean.endswith("/api"):
            clean = f"{clean}/api"
        return clean

    def _decode_token_expiry(self, token: str) -> float:
        """Parses the JWT exp timestamp without verifying signature."""
        try:
            parts = token.split(".")
            if len(parts) >= 2:
                padded = parts[1] + "=" * ((4 - len(parts[1]) % 4) % 4)
                payload = json.loads(base64.b64decode(padded).decode("utf-8"))
                exp = float(payload.get("exp", 0.0))
                return exp
        except Exception as e:
            logger.warning(f"Could not decode token expiry from JWT: {e}")
        return 0.0

    async def _resolve_organization_id(self) -> str:
        """Resolves organization friendly name to ID for legacy erp.favlogix.com."""
        if self.resolved_org_id:
            return self.resolved_org_id

        target = self.org_name_or_id.strip()
        if len(target) == 15 and all(c in "0123456789abcdef" for c in target.lower()):
            self.resolved_org_id = target
            return target

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                res = await client.get(f"{self.base_url}/organizations")
                if res.status_code == 200:
                    orgs = res.json()
                    for org in orgs:
                        if org.get("name", "").lower() == target.lower():
                            self.resolved_org_id = org.get("id")
                            logger.info(f"Resolved Favlogix organization '{target}' to ID '{self.resolved_org_id}'")
                            return self.resolved_org_id
        except Exception as e:
            logger.error(f"Error fetching Favlogix organizations: {e}")

        self.resolved_org_id = target
        return target

    async def _login(self) -> str:
        """Authenticates against Favlogix auth API using password or session refresh."""
        # ----------------------------------------------------
        # Mode A: New Platform (fio.favlogix.com)
        # ----------------------------------------------------
        if self.is_fio:
            login_url = f"{self.base_url}/tenant/auth/login"
            # Format username: e.g. faizan@sandbox
            username = self.email.strip()
            if "@" in username:
                parts = username.split("@")
                # If username is an email like faizanpatel@favlogix.com, format as faizanpatel@sandbox
                if "." in parts[1] and self.org_name_or_id:
                    username = f"{parts[0]}@{self.org_name_or_id.strip()}"
            elif self.org_name_or_id:
                username = f"{username}@{self.org_name_or_id.strip()}"

            if not self.password:
                raise FavlogixAuthError(
                    f"Favlogix password is empty in .env. Please set FAVLOGIX_PASSWORD for '{username}'."
                )

            logger.info(f"Authenticating with fio.favlogix.com as '{username}'...")
            payload = {"username": username, "password": self.password}
            try:
                async with httpx.AsyncClient(timeout=15.0) as client:
                    res = await client.post(login_url, json=payload)
                    if res.status_code == 200:
                        # Extract cookies (session token)
                        self.cookies = dict(res.cookies)
                        data = res.json() if res.text.startswith("{") else {}
                        token = data.get("token") or res.cookies.get("session") or ""
                        if token:
                            self.auth_token = token
                            self.token_expiry = self._decode_token_expiry(token)
                        logger.info("Successfully authenticated with fio.favlogix.com.")
                        return self.auth_token or "cookie-authenticated"
                    elif res.status_code == 401 or res.status_code == 422:
                        raise FavlogixAuthError(f"fio.favlogix.com login failed ({res.status_code}): {res.text}")
                    else:
                        raise FavlogixAuthError(f"fio.favlogix.com login returned HTTP {res.status_code}: {res.text}")
            except Exception as e:
                if isinstance(e, FavlogixAuthError):
                    raise
                raise FavlogixAuthError(f"Network error logging in to fio.favlogix.com: {e}")

        # ----------------------------------------------------
        # Mode B: Legacy Platform (erp.favlogix.com)
        # ----------------------------------------------------
        org_id = await self._resolve_organization_id()
        if self.password:
            login_url = f"{self.base_url}/auth/login"
            payload = {
                "organizationId": org_id,
                "email": self.email,
                "password": self.password
            }
            logger.info(f"Attempting Favlogix auth login for '{self.email}' (Org ID: {org_id})...")
            try:
                async with httpx.AsyncClient(timeout=15.0) as client:
                    res = await client.post(login_url, json=payload)
                    if res.status_code == 200:
                        data = res.json()
                        token = data.get("token")
                        if token:
                            self.auth_token = token
                            self.token_expiry = self._decode_token_expiry(token)
                            logger.info("Successfully authenticated with Favlogix API via password.")
                            return self.auth_token
                        else:
                            raise FavlogixAuthError("Favlogix login succeeded but returned no token.")
                    else:
                        raise FavlogixAuthError(f"Favlogix login failed with status {res.status_code}: {res.text}")
            except Exception as e:
                if isinstance(e, FavlogixAuthError):
                    raise
                raise FavlogixAuthError(f"Network error during Favlogix login: {e}")

        # Refresh existing token if available
        if self.auth_token:
            refresh_url = f"{self.base_url}/auth/token"
            headers = {"Authorization": self.auth_token, "Accept": "application/json"}
            try:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    res = await client.post(refresh_url, headers=headers)
                    if res.status_code == 200:
                        data = res.json()
                        token = data.get("token")
                        if token:
                            self.auth_token = token
                            self.token_expiry = self._decode_token_expiry(token)
                            logger.info("Successfully refreshed Favlogix session token.")
                            return self.auth_token
            except Exception as e:
                logger.warning(f"Could not refresh Favlogix token: {e}")

            if self.token_expiry and time.time() < self.token_expiry - 60:
                return self.auth_token

        raise FavlogixAuthError(
            "Favlogix credentials not configured or expired. "
            "Please provide FAVLOGIX_PASSWORD in your .env file."
        )

    async def _ensure_valid_token(self) -> str:
        """Ensures an unexpired token or active session is ready."""
        now = time.time()
        if not self.auth_token and not self.cookies:
            return await self._login()
        if self.token_expiry and now > self.token_expiry - 120:
            return await self._login()
        return self.auth_token

    async def extract_trip_data(self, trip_id: str) -> Dict[str, Any]:
        """
        Extracts trip valuation and orders for a given trip ID.
        Automatically branches between fio.favlogix.com (trip-totals endpoint)
        and erp.favlogix.com (PocketBase sales_order query).
        """
        clean_trip = trip_id.strip()
        await self._ensure_valid_token()

        # Extract destination city (e.g. 17092026-byo -> Byo -> Bulawayo, 20042026-BINDURA -> Bindura)
        dest_city = ""
        city_match = re.search(r"[-_]([A-Za-z]+)", clean_trip)
        if city_match:
            dest_city = city_match.group(1).title()

        # ----------------------------------------------------
        # Mode A: New Platform (fio.favlogix.com)
        # ----------------------------------------------------
        if self.is_fio:
            clean_trip = trip_id.strip().upper().replace("TRIP-", "").strip()
            sales_trip_url = f"{self.base_url}/tenant/sales/trip"
            detail_url = f"{self.base_url}/tenant/sales/trip/detail"
            headers = {"Accept": "application/json"}
            if self.auth_token and not self.auth_token.startswith("cookie-"):
                headers["Authorization"] = f"Bearer {self.auth_token}"

            async with httpx.AsyncClient(timeout=15.0, cookies=self.cookies) as client:
                trip_data = None
                orders_data = []

                # 1. Try direct detail lookup (if full trip ID like 22092026-TEST2 was provided)
                res_detail = await client.get(detail_url, params={"tripId": clean_trip}, headers=headers)
                if res_detail.status_code == 401:
                    logger.warning("fio.favlogix.com session expired. Re-authenticating...")
                    await self._login()
                    res_detail = await client.get(detail_url, params={"tripId": clean_trip}, headers=headers, cookies=self.cookies)

                if res_detail.status_code == 200:
                    d_json = res_detail.json()
                    trip_data = d_json.get("trip")
                    orders_data = d_json.get("orders", [])
                elif res_detail.status_code == 404:
                    # 2. Try sales/trip search (e.g. user typed 'TEST2' or partial name)
                    search_params = {"trip": clean_trip, "search": clean_trip, "limit": 100}
                    res_search = await client.get(sales_trip_url, params=search_params, headers=headers)
                    if res_search.status_code == 401:
                        await self._login()
                        res_search = await client.get(sales_trip_url, params=search_params, headers=headers, cookies=self.cookies)

                    if res_search.status_code == 200:
                        s_json = res_search.json()
                        items = s_json.get("data", []) if isinstance(s_json, dict) else s_json
                        matching = [
                            it for it in items
                            if clean_trip.lower() in it.get("tripId", "").lower()
                            or it.get("tripId", "").lower().endswith(clean_trip.lower())
                        ]
                        if matching:
                            real_trip_id = matching[0].get("tripId")
                            res_real = await client.get(detail_url, params={"tripId": real_trip_id}, headers=headers, cookies=self.cookies)
                            if res_real.status_code == 200:
                                d_json = res_real.json()
                                trip_data = d_json.get("trip")
                                orders_data = d_json.get("orders", [])
                            else:
                                trip_data = matching[0]

                if not trip_data:
                    # 3. Final fallback: List recent trips and match locally
                    res_all = await client.get(sales_trip_url, params={"limit": 200}, headers=headers, cookies=self.cookies)
                    if res_all.status_code == 200:
                        s_json = res_all.json()
                        items = s_json.get("data", []) if isinstance(s_json, dict) else s_json
                        matching = [
                            it for it in items
                            if clean_trip.lower() in it.get("tripId", "").lower()
                            or it.get("tripId", "").lower().endswith(clean_trip.lower())
                        ]
                        if matching:
                            real_trip_id = matching[0].get("tripId")
                            res_real = await client.get(detail_url, params={"tripId": real_trip_id}, headers=headers, cookies=self.cookies)
                            if res_real.status_code == 200:
                                d_json = res_real.json()
                                trip_data = d_json.get("trip")
                                orders_data = d_json.get("orders", [])
                            else:
                                trip_data = matching[0]

                if not trip_data:
                    raise FavlogixCalculationPendingError(
                        f"Trip '{clean_trip}' was not found in Favlogix Sales Trips."
                    )

                actual_trip_id = trip_data.get("tripId") or clean_trip
                total_amount = float(trip_data.get("totalAmount") or 0.0)
                total_orders = int(trip_data.get("orderCount") or len(orders_data) or 1)
                order_ids = [o.get("orderId") or o.get("orderKey") for o in orders_data if o.get("orderId") or o.get("orderKey")]

                # Resolve destination city
                resolved_city = dest_city
                if not resolved_city:
                    for o in orders_data:
                        c_name = o.get("customerName", "").lower()
                        if "mufakose" in c_name or "harare" in c_name:
                            resolved_city = "Local"
                            break
                        for known in ["bindura", "bulawayo", "mutare", "gweru", "kwekwe", "chinhoyi", "masvingo", "marondera", "rusape"]:
                            if known in c_name:
                                resolved_city = known.title()
                                break

                if not resolved_city:
                    resolved_city = "Local"

                logger.info(
                    f"fio.favlogix.com: Trip '{actual_trip_id}' found with {total_orders} orders, "
                    f"total amount: ${total_amount:,.2f}, destination: {resolved_city} (Orders: {order_ids})"
                )

                return {
                    "trip_id": actual_trip_id,
                    "total_amount": round(total_amount, 2),
                    "destination_city": resolved_city,
                    "route": "",
                    "status": "CALCULATED",
                    "order_count": total_orders,
                    "orders": order_ids
                }

        # ----------------------------------------------------
        # Mode B: Legacy Platform (erp.favlogix.com)
        # ----------------------------------------------------
        records_url = f"{self.base_url}/pb/api/collections/sales_order/records"
        headers = {
            "Authorization": self.auth_token,
            "Accept": "application/json"
        }

        params = {
            "filter": f'trip_id = "{clean_trip}" && is_deleted = false',
            "perPage": 100
        }

        async with httpx.AsyncClient(timeout=15.0) as client:
            res = await client.get(records_url, params=params, headers=headers)

            if res.status_code == 401:
                logger.warning("Favlogix returned HTTP 401. Re-authenticating token...")
                await self._login()
                headers["Authorization"] = self.auth_token
                res = await client.get(records_url, params=params, headers=headers)

            if res.status_code != 200:
                raise FavlogixAPIError(f"Favlogix sales_order query failed with HTTP {res.status_code}: {res.text}")

            data = res.json()
            inner = data.get("data", {})
            items = inner.get("items", []) if isinstance(inner, dict) else data.get("items", [])

            if not items:
                p_like = {
                    "filter": f'trip_id ~ "{clean_trip}" && is_deleted = false',
                    "perPage": 100
                }
                res_like = await client.get(records_url, params=p_like, headers=headers)
                if res_like.status_code == 200:
                    data_like = res_like.json()
                    inner_like = data_like.get("data", {})
                    items = inner_like.get("items", []) if isinstance(inner_like, dict) else data_like.get("items", [])

            if not items:
                raise FavlogixCalculationPendingError(
                    f"Trip '{clean_trip}' currently has 0 active sales orders in Favlogix."
                )

            total_amount = sum(float(item.get("total", 0.0)) for item in items)
            order_ids = [it.get("sales_order_id") for it in items if it.get("sales_order_id")]

            return {
                "trip_id": clean_trip,
                "total_amount": round(total_amount, 2),
                "destination_city": dest_city or "Bulawayo",
                "route": "",
                "status": "CALCULATED",
                "order_count": len(items),
                "orders": order_ids
            }

    async def list_active_trips(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Lists active delivery trips from either fio.favlogix.com or erp.favlogix.com."""
        await self._ensure_valid_token()

        if self.is_fio:
            sales_trip_url = f"{self.base_url}/tenant/sales/trip"
            headers = {"Accept": "application/json"}
            if self.auth_token and not self.auth_token.startswith("cookie-"):
                headers["Authorization"] = f"Bearer {self.auth_token}"

            async with httpx.AsyncClient(timeout=15.0, cookies=self.cookies) as client:
                res = await client.get(sales_trip_url, headers=headers)
                if res.status_code == 401:
                    await self._login()
                    res = await client.get(sales_trip_url, headers=headers, cookies=self.cookies)
                if res.status_code != 200:
                    return []
                s_json = res.json()
                items = s_json.get("data", []) if isinstance(s_json, dict) else s_json

                return [
                    {
                        "trip_id": it.get("tripId"),
                        "order_count": int(it.get("orderCount") or 1),
                        "total_amount": float(it.get("totalAmount") or 0.0),
                        "currency": it.get("currencyCode", "USD"),
                        "status": "Open" if it.get("isOpen") else "Closed"
                    }
                    for it in items[:limit]
                ]

        # Legacy
        records_url = f"{self.base_url}/pb/api/collections/sales_order/records"
        headers = {"Authorization": self.auth_token, "Accept": "application/json"}
        params = {
            "filter": 'trip_id != "" && is_deleted = false',
            "fields": "trip_id,total,status",
            "perPage": 500
        }

        async with httpx.AsyncClient(timeout=15.0) as client:
            res = await client.get(records_url, params=params, headers=headers)
            if res.status_code != 200:
                return []

            data = res.json()
            inner = data.get("data", {})
            items = inner.get("items", []) if isinstance(inner, dict) else data.get("items", [])

            trips: Dict[str, Dict[str, Any]] = {}
            for it in items:
                tid = it.get("trip_id")
                if not tid:
                    continue
                if tid not in trips:
                    trips[tid] = {"trip_id": tid, "order_count": 0, "total_amount": 0.0}
                trips[tid]["order_count"] += 1
                trips[tid]["total_amount"] += float(it.get("total", 0.0))

            return [
                {
                    "trip_id": t["trip_id"],
                    "order_count": t["order_count"],
                    "total_amount": round(t["total_amount"], 2)
                }
                for t in trips.values()
            ][:limit]


favlogix_api_service = FavlogixAPIService()
