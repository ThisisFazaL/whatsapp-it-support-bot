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
    Communicates directly with the Favlogix PocketBase API without requiring
    a local browser, Chrome window, or display server.
    """

    def __init__(self):
        self.api_url: str = settings.favlogix_api_url.rstrip("/")
        self.org_name_or_id: str = settings.favlogix_organization
        self.email: str = settings.favlogix_email
        self.password: str = settings.favlogix_password
        self.auth_token: str = settings.favlogix_auth_token
        self.token_expiry: float = 0.0
        self.resolved_org_id: Optional[str] = None

        if self.auth_token:
            self.token_expiry = self._decode_token_expiry(self.auth_token)

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
        """
        Resolves an organization name (e.g. 'sandbox') to its internal Favlogix organization ID.
        If already provided as a 15-character hex ID, returns it directly.
        """
        if self.resolved_org_id:
            return self.resolved_org_id

        target = self.org_name_or_id.strip()
        # If target looks like a 15-character hex ID (e.g. '019bdf9df302700')
        if len(target) == 15 and all(c in "0123456789abcdef" for c in target.lower()):
            self.resolved_org_id = target
            return target

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                res = await client.get(f"{self.api_url}/organizations")
                if res.status_code == 200:
                    orgs = res.json()
                    for org in orgs:
                        if org.get("name", "").lower() == target.lower():
                            self.resolved_org_id = org.get("id")
                            logger.info(f"Resolved Favlogix organization '{target}' to ID '{self.resolved_org_id}'")
                            return self.resolved_org_id
        except Exception as e:
            logger.error(f"Error fetching Favlogix organizations: {e}")

        # Fallback to current target if resolution failed
        self.resolved_org_id = target
        return target

    async def _login(self) -> str:
        """
        Authenticates against Favlogix auth API using password or refreshes active token.
        """
        org_id = await self._resolve_organization_id()

        # 1. If password is provided, perform full login
        if self.password:
            login_url = f"{self.api_url}/auth/login"
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

        # 2. If no password but we have an auth token, attempt refresh
        if self.auth_token:
            refresh_url = f"{self.api_url}/auth/token"
            headers = {"Authorization": self.auth_token, "Accept": "application/json"}
            logger.info("Attempting to refresh existing Favlogix session token...")
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

            # If token is still unexpired according to payload, reuse it
            if self.token_expiry and time.time() < self.token_expiry - 60:
                logger.info("Reusing unexpired Favlogix JWT token.")
                return self.auth_token

        raise FavlogixAuthError(
            "Favlogix credentials not configured or expired. "
            "Please provide FAVLOGIX_PASSWORD or an active FAVLOGIX_AUTH_TOKEN in environment variables."
        )

    async def _ensure_valid_token(self) -> str:
        """Ensures an unexpired token is ready for API calls."""
        now = time.time()
        # If token is missing, or expired / expiring in less than 2 minutes
        if not self.auth_token or (self.token_expiry and now > self.token_expiry - 120):
            return await self._login()
        return self.auth_token

    async def extract_trip_data(self, trip_id: str) -> Dict[str, Any]:
        """
        Extracts sales order records for a specific trip directly from PocketBase.
        Calculates the aggregated total sales amount and destination city.
        """
        clean_trip = trip_id.strip()
        token = await self._ensure_valid_token()

        # Extract destination city from trip ID pattern (e.g. 20042026-BINDURA -> Bindura)
        dest_city = ""
        city_match = re.search(r"[-_]([A-Za-z]+)", clean_trip)
        if city_match:
            dest_city = city_match.group(1).title()

        records_url = f"{self.api_url}/pb/api/collections/sales_order/records"
        headers = {
            "Authorization": token,
            "Accept": "application/json"
        }

        # Query 1: Exact trip_id match
        params = {
            "filter": f'trip_id = "{clean_trip}" && is_deleted = false',
            "perPage": 100
        }

        async with httpx.AsyncClient(timeout=15.0) as client:
            res = await client.get(records_url, params=params, headers=headers)

            # Handle automatic 401 token renewal
            if res.status_code == 401:
                logger.warning("Favlogix returned HTTP 401. Re-authenticating token...")
                token = await self._login()
                headers["Authorization"] = token
                res = await client.get(records_url, params=params, headers=headers)

            if res.status_code != 200:
                raise FavlogixAPIError(f"Favlogix sales_order query failed with HTTP {res.status_code}: {res.text}")

            data = res.json()
            inner = data.get("data", {})
            items = inner.get("items", []) if isinstance(inner, dict) else data.get("items", [])

            # If exact match found 0 items, attempt case-insensitive partial match
            if not items:
                logger.info(f"Exact match yielded 0 orders for '{clean_trip}'. Trying case-insensitive partial match...")
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

            # Sum line totals
            total_amount = 0.0
            order_ids = []
            for item in items:
                total_amount += float(item.get("total", 0.0))
                so_id = item.get("sales_order_id")
                if so_id:
                    order_ids.append(so_id)

            logger.info(
                f"Favlogix API: Trip '{clean_trip}' has {len(items)} sales orders, "
                f"total amount: ${total_amount:,.2f} (Orders: {order_ids})"
            )

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
        """
        Lists all active trips and their aggregated valuations from sales orders.
        """
        token = await self._ensure_valid_token()
        records_url = f"{self.api_url}/pb/api/collections/sales_order/records"
        headers = {"Authorization": token, "Accept": "application/json"}
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

            res_list = [
                {
                    "trip_id": t["trip_id"],
                    "order_count": t["order_count"],
                    "total_amount": round(t["total_amount"], 2)
                }
                for t in trips.values()
            ]
            return res_list[:limit]


favlogix_api_service = FavlogixAPIService()
