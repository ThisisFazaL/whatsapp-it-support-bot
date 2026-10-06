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


class CompanyTenantSession:
    """Encapsulates authentication state and credentials for a single company tenant."""

    def __init__(
        self,
        company_key: str,
        display_name: str,
        org_name_or_id: str,
        email: str,
        password: str,
        auth_token: str = "",
        api_url: str = ""
    ):
        self.company_key = company_key.upper()  # 'LG', 'TG', 'KRECKLE', 'DEFAULT'
        self.display_name = display_name
        self.org_name_or_id = (org_name_or_id or "").strip()
        self.email = (email or "").strip()
        self.password = (password or "").strip()
        self.auth_token = (auth_token or "").strip()
        self.api_url = (api_url or "").rstrip("/")
        self.token_expiry: float = 0.0
        self.resolved_org_id: Optional[str] = None
        self.cookies: Dict[str, str] = {}

    @property
    def is_configured(self) -> bool:
        """Returns True if minimum credentials exist to authenticate this tenant."""
        return bool(self.auth_token or (self.email and self.password))

    def __repr__(self) -> str:
        return f"<CompanyTenantSession key={self.company_key} name='{self.display_name}' org='{self.org_name_or_id}' email='{self.email}'>"


class FavlogixAPIService:
    """
    Direct background HTTP client for Favlogix ERP (Option 1 - Headless).
    Communicates directly with Favlogix backend without requiring
    a local browser, Chrome window, or display server.

    Supports:
    1. Multi-Company Tenants (LG Plast, Tagoneswa Hardware, Kreckle Foods)
    2. Modern Platform (fio.favlogix.com): Dedicated `/api/tenant/sales/trip` endpoints
    3. Legacy Platform (erp.favlogix.com): PocketBase `/api/pb/api/collections/sales_order/records`
    """

    def __init__(self):
        self.default_api_url: str = settings.favlogix_api_url.rstrip("/")
        self.tenants: Dict[str, CompanyTenantSession] = {}
        self._init_tenants()

    def _init_tenants(self):
        """Initializes tenant configurations for the 3 operating companies and a fallback default."""
        self.tenants = {
            "LG": CompanyTenantSession(
                company_key="LG",
                display_name="LG Plast",
                org_name_or_id=getattr(settings, "favlogix_lg_org", "") or "lgplast",
                email=getattr(settings, "favlogix_lg_email", ""),
                password=getattr(settings, "favlogix_lg_password", ""),
                auth_token=getattr(settings, "favlogix_lg_auth_token", ""),
                api_url=getattr(settings, "favlogix_lg_api_url", "") or self.default_api_url
            ),
            "TG": CompanyTenantSession(
                company_key="TG",
                display_name="Tagoneswa Hardware",
                org_name_or_id=getattr(settings, "favlogix_tg_org", "") or "tagoneswa",
                email=getattr(settings, "favlogix_tg_email", ""),
                password=getattr(settings, "favlogix_tg_password", ""),
                auth_token=getattr(settings, "favlogix_tg_auth_token", ""),
                api_url=getattr(settings, "favlogix_tg_api_url", "") or self.default_api_url
            ),
            "KRECKLE": CompanyTenantSession(
                company_key="KRECKLE",
                display_name="Kreckle Foods",
                org_name_or_id=getattr(settings, "favlogix_kreckle_org", "") or "kreckle",
                email=getattr(settings, "favlogix_kreckle_email", ""),
                password=getattr(settings, "favlogix_kreckle_password", ""),
                auth_token=getattr(settings, "favlogix_kreckle_auth_token", ""),
                api_url=getattr(settings, "favlogix_kreckle_api_url", "") or self.default_api_url
            ),
            "DEFAULT": CompanyTenantSession(
                company_key="DEFAULT",
                display_name="Default Tenant",
                org_name_or_id=settings.favlogix_organization,
                email=settings.favlogix_email,
                password=settings.favlogix_password,
                auth_token=settings.favlogix_auth_token,
                api_url=self.default_api_url
            )
        }

        # Pre-decode token expiries if tokens were pre-supplied
        for t in self.tenants.values():
            if t.auth_token:
                t.token_expiry = self._decode_token_expiry(t.auth_token)

    # ----------------------------------------------------
    # Backwards-compatible properties
    # ----------------------------------------------------
    @property
    def api_url(self) -> str:
        return self.default_api_url

    @property
    def org_name_or_id(self) -> str:
        return self.tenants["DEFAULT"].org_name_or_id

    @property
    def email(self) -> str:
        return self.tenants["DEFAULT"].email

    @property
    def password(self) -> str:
        return self.tenants["DEFAULT"].password

    @property
    def auth_token(self) -> str:
        return self.tenants["DEFAULT"].auth_token

    @property
    def cookies(self) -> Dict[str, str]:
        return self.tenants["DEFAULT"].cookies

    @property
    def token_expiry(self) -> float:
        return self.tenants["DEFAULT"].token_expiry

    @property
    def is_fio(self) -> bool:
        """Returns True if default connected URL is fio.favlogix.com."""
        return self._is_fio(self.tenants["DEFAULT"])

    @property
    def base_url(self) -> str:
        """Normalized base URL without trailing slash for default tenant."""
        return self._base_url(self.tenants["DEFAULT"])

    def _is_fio(self, tenant: CompanyTenantSession) -> bool:
        url = tenant.api_url or self.default_api_url
        return "fio" in url or "/tenant" in url or "fio" in getattr(settings, "favlogix_url", "")

    def _base_url(self, tenant: CompanyTenantSession) -> str:
        clean = (tenant.api_url or self.default_api_url).rstrip("/")
        if self._is_fio(tenant) and not clean.endswith("/api"):
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

    def get_tenant(self, company_name: Optional[str] = None, trip_id: Optional[str] = None) -> CompanyTenantSession:
        """
        Resolves the appropriate CompanyTenantSession based on:
        1. Explicit company_name (e.g. 'LG Plast', 'B. LG Plast', 'Tagoneswa Hardware', 'A. TG Hardware', 'Kreckle Foods').
        2. Prefix of trip_id (e.g. 'LG-2026-001', 'TG-20042026', 'KR-01').
        3. Fallback to DEFAULT tenant.
        """
        c_str = (company_name or "").strip().lower()
        key = None

        if "lg" in c_str or "plast" in c_str:
            key = "LG"
        elif "tg" in c_str or "tagoneswa" in c_str or "hardware" in c_str:
            key = "TG"
        elif "kreckle" in c_str or "food" in c_str or "kr" in c_str:
            key = "KRECKLE"

        # Check trip_id prefix if key not resolved from company_name
        if not key and trip_id:
            t_upper = trip_id.strip().upper()
            if t_upper.startswith(("LG-", "LG_", "LGP-")):
                key = "LG"
            elif t_upper.startswith(("TG-", "TG_", "TGH-")):
                key = "TG"
            elif t_upper.startswith(("KR-", "KF-", "KRECKLE-")):
                key = "KRECKLE"

        if key and key in self.tenants:
            tenant = self.tenants[key]
            if tenant.is_configured:
                return tenant
            logger.info(f"Tenant '{key}' matched for '{company_name or trip_id}', but specific credentials not set. Falling back to DEFAULT tenant.")

        return self.tenants["DEFAULT"]

    async def _resolve_organization_id(self, tenant: Optional[CompanyTenantSession] = None) -> str:
        """Resolves organization friendly name to ID for legacy erp.favlogix.com."""
        tenant = tenant or self.tenants["DEFAULT"]
        if tenant.resolved_org_id:
            return tenant.resolved_org_id

        target = tenant.org_name_or_id.strip()
        if len(target) == 15 and all(c in "0123456789abcdef" for c in target.lower()):
            tenant.resolved_org_id = target
            return target

        base = self._base_url(tenant)
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                res = await client.get(f"{base}/organizations")
                if res.status_code == 200:
                    orgs = res.json()
                    for org in orgs:
                        if org.get("name", "").lower() == target.lower():
                            tenant.resolved_org_id = org.get("id")
                            logger.info(f"Resolved Favlogix organization '{target}' to ID '{tenant.resolved_org_id}'")
                            return tenant.resolved_org_id
        except Exception as e:
            logger.error(f"Error fetching Favlogix organizations for tenant {tenant.company_key}: {e}")

        tenant.resolved_org_id = target
        return target

    async def _login(self, tenant: Optional[CompanyTenantSession] = None) -> str:
        """Authenticates against Favlogix auth API for a specific tenant session."""
        tenant = tenant or self.tenants["DEFAULT"]
        base = self._base_url(tenant)
        is_fio = self._is_fio(tenant)

        # ----------------------------------------------------
        # Mode A: New Platform (fio.favlogix.com)
        # ----------------------------------------------------
        if is_fio:
            login_url = f"{base}/tenant/auth/login"
            username = tenant.email.strip()
            if "@" in username:
                parts = username.split("@")
                if "." in parts[1] and tenant.org_name_or_id:
                    username = f"{parts[0]}@{tenant.org_name_or_id.strip()}"
            elif tenant.org_name_or_id:
                username = f"{username}@{tenant.org_name_or_id.strip()}"

            if not tenant.password:
                raise FavlogixAuthError(
                    f"Favlogix password is empty for tenant '{tenant.display_name}'. Please set password in environment."
                )

            logger.info(f"Authenticating with fio.favlogix.com for tenant '{tenant.display_name}' as '{username}'...")
            payload = {"username": username, "password": tenant.password}
            try:
                async with httpx.AsyncClient(timeout=15.0) as client:
                    res = await client.post(login_url, json=payload)
                    if res.status_code == 200:
                        tenant.cookies = dict(res.cookies)
                        data = res.json() if res.text.startswith("{") else {}
                        token = data.get("token") or res.cookies.get("session") or ""
                        if token:
                            tenant.auth_token = token
                            tenant.token_expiry = self._decode_token_expiry(token)
                        logger.info(f"Successfully authenticated tenant '{tenant.display_name}' with fio.favlogix.com.")
                        return tenant.auth_token or "cookie-authenticated"
                    elif res.status_code in (401, 422):
                        raise FavlogixAuthError(f"fio.favlogix.com login failed for tenant '{tenant.display_name}' ({res.status_code}): {res.text}")
                    else:
                        raise FavlogixAuthError(f"fio.favlogix.com login returned HTTP {res.status_code} for tenant '{tenant.display_name}': {res.text}")
            except Exception as e:
                if isinstance(e, FavlogixAuthError):
                    raise
                raise FavlogixAuthError(f"Network error logging in to fio.favlogix.com for tenant '{tenant.display_name}': {e}")

        # ----------------------------------------------------
        # Mode B: Legacy Platform (erp.favlogix.com)
        # ----------------------------------------------------
        org_id = await self._resolve_organization_id(tenant)
        if tenant.password:
            login_url = f"{base}/auth/login"
            payload = {
                "organizationId": org_id,
                "email": tenant.email,
                "password": tenant.password
            }
            logger.info(f"Attempting Favlogix auth login for '{tenant.email}' (Tenant: {tenant.display_name}, Org ID: {org_id})...")
            try:
                async with httpx.AsyncClient(timeout=15.0) as client:
                    res = await client.post(login_url, json=payload)
                    if res.status_code == 200:
                        data = res.json()
                        token = data.get("token")
                        if token:
                            tenant.auth_token = token
                            tenant.token_expiry = self._decode_token_expiry(token)
                            logger.info(f"Successfully authenticated tenant '{tenant.display_name}' via password.")
                            return tenant.auth_token
                        else:
                            raise FavlogixAuthError(f"Favlogix login succeeded for '{tenant.display_name}' but returned no token.")
                    else:
                        raise FavlogixAuthError(f"Favlogix login failed for '{tenant.display_name}' with status {res.status_code}: {res.text}")
            except Exception as e:
                if isinstance(e, FavlogixAuthError):
                    raise
                raise FavlogixAuthError(f"Network error during Favlogix login for '{tenant.display_name}': {e}")

        # Refresh existing token if available
        if tenant.auth_token:
            refresh_url = f"{base}/auth/token"
            headers = {"Authorization": tenant.auth_token, "Accept": "application/json"}
            try:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    res = await client.post(refresh_url, headers=headers)
                    if res.status_code == 200:
                        data = res.json()
                        token = data.get("token")
                        if token:
                            tenant.auth_token = token
                            tenant.token_expiry = self._decode_token_expiry(token)
                            logger.info(f"Successfully refreshed Favlogix session token for '{tenant.display_name}'.")
                            return tenant.auth_token
            except Exception as e:
                logger.warning(f"Could not refresh Favlogix token for '{tenant.display_name}': {e}")

            if tenant.token_expiry and time.time() < tenant.token_expiry - 60:
                return tenant.auth_token

        raise FavlogixAuthError(
            f"Favlogix credentials not configured or expired for tenant '{tenant.display_name}'. "
            "Please provide credentials in environment variables."
        )

    async def _ensure_valid_token(self, tenant: Optional[CompanyTenantSession] = None) -> str:
        """Ensures an unexpired token or active session is ready for a given tenant."""
        tenant = tenant or self.tenants["DEFAULT"]
        now = time.time()
        if not tenant.auth_token and not tenant.cookies:
            return await self._login(tenant)
        if tenant.token_expiry and now > tenant.token_expiry - 120:
            return await self._login(tenant)
        return tenant.auth_token

    async def _extract_from_tenant(self, tenant: CompanyTenantSession, trip_id: str) -> Dict[str, Any]:
        """Performs raw trip extraction against a specific company tenant."""
        clean_trip = trip_id.strip()
        await self._ensure_valid_token(tenant)
        base = self._base_url(tenant)
        is_fio = self._is_fio(tenant)

        # Extract destination city heuristic from trip name (e.g. 17092026-byo -> Bulawayo)
        dest_city = ""
        city_match = re.search(r"[-_]([A-Za-z]+)", clean_trip)
        if city_match:
            dest_city = city_match.group(1).title()

        # ----------------------------------------------------
        # Mode A: New Platform (fio.favlogix.com)
        # ----------------------------------------------------
        if is_fio:
            clean_trip = trip_id.strip().upper().replace("TRIP-", "").strip()
            sales_trip_url = f"{base}/tenant/sales/trip"
            detail_url = f"{base}/tenant/sales/trip/detail"
            headers = {"Accept": "application/json"}
            if tenant.auth_token and not tenant.auth_token.startswith("cookie-"):
                headers["Authorization"] = f"Bearer {tenant.auth_token}"

            async with httpx.AsyncClient(timeout=15.0, cookies=tenant.cookies) as client:
                trip_data = None
                orders_data = []

                # 1. Direct detail lookup
                res_detail = await client.get(detail_url, params={"tripId": clean_trip}, headers=headers)
                if res_detail.status_code == 401:
                    logger.warning(f"fio.favlogix.com session expired for '{tenant.display_name}'. Re-authenticating...")
                    await self._login(tenant)
                    if tenant.auth_token and not tenant.auth_token.startswith("cookie-"):
                        headers["Authorization"] = f"Bearer {tenant.auth_token}"
                    res_detail = await client.get(detail_url, params={"tripId": clean_trip}, headers=headers, cookies=tenant.cookies)

                if res_detail.status_code == 200:
                    d_json = res_detail.json()
                    trip_data = d_json.get("trip")
                    orders_data = d_json.get("orders", [])
                elif res_detail.status_code == 404:
                    # 2. Search sales/trip
                    search_params = {"trip": clean_trip, "search": clean_trip, "limit": 100}
                    res_search = await client.get(sales_trip_url, params=search_params, headers=headers)
                    if res_search.status_code == 401:
                        await self._login(tenant)
                        if tenant.auth_token and not tenant.auth_token.startswith("cookie-"):
                            headers["Authorization"] = f"Bearer {tenant.auth_token}"
                        res_search = await client.get(sales_trip_url, params=search_params, headers=headers, cookies=tenant.cookies)

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
                            res_real = await client.get(detail_url, params={"tripId": real_trip_id}, headers=headers, cookies=tenant.cookies)
                            if res_real.status_code == 200:
                                d_json = res_real.json()
                                trip_data = d_json.get("trip")
                                orders_data = d_json.get("orders", [])
                            else:
                                trip_data = matching[0]

                if not trip_data:
                    # 3. List recent trips and match locally
                    res_all = await client.get(sales_trip_url, params={"limit": 200}, headers=headers, cookies=tenant.cookies)
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
                            res_real = await client.get(detail_url, params={"tripId": real_trip_id}, headers=headers, cookies=tenant.cookies)
                            if res_real.status_code == 200:
                                d_json = res_real.json()
                                trip_data = d_json.get("trip")
                                orders_data = d_json.get("orders", [])
                            else:
                                trip_data = matching[0]

                if not trip_data:
                    raise FavlogixCalculationPendingError(
                        f"Trip '{clean_trip}' was not found in Favlogix ({tenant.display_name})."
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

                customers_list = []
                for idx, o in enumerate(orders_data, start=1):
                    c_name = o.get("customerName") or o.get("customer") or o.get("name") or f"Customer {idx}"
                    c_id = o.get("orderId") or o.get("orderKey") or f"CUST-{idx}"
                    o_val = float(o.get("totalAmount") or o.get("total") or o.get("amount") or 0.0)
                    order_key = o.get("orderId") or o.get("orderKey") or o.get("orderNumber") or ""
                    customers_list.append({
                        "customer_name": c_name,
                        "customer_id": c_id,
                        "order_id": order_key,
                        "order_total": round(o_val, 2),
                        "to_collect": 0.0
                    })

                logger.info(
                    f"fio.favlogix.com [{tenant.display_name}]: Trip '{actual_trip_id}' found with {total_orders} orders, "
                    f"total: ${total_amount:,.2f}, destination: {resolved_city}"
                )

                return {
                    "trip_id": actual_trip_id,
                    "company_name": tenant.display_name,
                    "company_key": tenant.company_key,
                    "total_amount": round(total_amount, 2),
                    "destination_city": resolved_city,
                    "route": "",
                    "status": "CALCULATED",
                    "order_count": total_orders,
                    "orders": order_ids,
                    "customers": customers_list
                }

        # ----------------------------------------------------
        # Mode B: Legacy Platform (erp.favlogix.com)
        # ----------------------------------------------------
        records_url = f"{base}/pb/api/collections/sales_order/records"
        headers = {
            "Authorization": tenant.auth_token,
            "Accept": "application/json"
        }

        params = {
            "filter": f'trip_id = "{clean_trip}" && is_deleted = false',
            "perPage": 100
        }

        async with httpx.AsyncClient(timeout=15.0) as client:
            res = await client.get(records_url, params=params, headers=headers)

            if res.status_code == 401:
                logger.warning(f"Favlogix returned HTTP 401 for '{tenant.display_name}'. Re-authenticating token...")
                await self._login(tenant)
                headers["Authorization"] = tenant.auth_token
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
                    f"Trip '{clean_trip}' currently has 0 active sales orders in Favlogix ({tenant.display_name})."
                )

            total_amount = sum(float(item.get("total", 0.0)) for item in items)
            order_ids = [it.get("sales_order_id") for it in items if it.get("sales_order_id")]

            customers_list = []
            for idx, it in enumerate(items, start=1):
                c_name = it.get("customer_name") or it.get("customer") or it.get("name") or f"Customer {idx}"
                c_id = it.get("sales_order_id") or it.get("id") or f"CUST-{idx}"
                o_val = float(it.get("total", 0.0))
                customers_list.append({
                    "customer_name": c_name,
                    "customer_id": c_id,
                    "order_id": it.get("sales_order_id") or "",
                    "order_total": round(o_val, 2),
                    "to_collect": 0.0
                })

            return {
                "trip_id": clean_trip,
                "company_name": tenant.display_name,
                "company_key": tenant.company_key,
                "total_amount": round(total_amount, 2),
                "destination_city": dest_city or "Bulawayo",
                "route": "",
                "status": "CALCULATED",
                "order_count": len(items),
                "orders": order_ids,
                "customers": customers_list
            }

    async def extract_trip_data(self, trip_id: str, company_name: Optional[str] = None) -> Dict[str, Any]:
        """
        Extracts trip valuation and orders for a given trip ID.
        Uses company_name or trip_id to route to the correct company tenant (LG, TG, Kreckle).
        If the primary tenant does not find the trip, gracefully falls back across other configured tenants.
        """
        primary_tenant = self.get_tenant(company_name, trip_id)
        last_error: Optional[Exception] = None

        try:
            return await self._extract_from_tenant(primary_tenant, trip_id)
        except (FavlogixCalculationPendingError, FavlogixTripNotFoundError, FavlogixAuthError) as err:
            last_error = err
            logger.info(f"Trip '{trip_id}' not resolved on primary tenant '{primary_tenant.display_name}' ({err}). Checking other tenants...")

        # Multi-company fallback search across other configured tenants
        for key in ["LG", "TG", "KRECKLE", "DEFAULT"]:
            tenant = self.tenants.get(key)
            if tenant and tenant != primary_tenant and tenant.is_configured:
                try:
                    alt_result = await self._extract_from_tenant(tenant, trip_id)
                    if alt_result and alt_result.get("status") == "CALCULATED":
                        logger.info(f"Trip '{trip_id}' successfully discovered under '{tenant.display_name}' tenant!")
                        return alt_result
                except Exception as alt_err:
                    logger.debug(f"Search for '{trip_id}' under alternative tenant '{tenant.display_name}' failed: {alt_err}")

        # If all failed, re-raise the original primary error
        if last_error:
            raise last_error
        raise FavlogixCalculationPendingError(f"Trip '{trip_id}' was not found in Favlogix.")

    async def list_active_trips(self, company_name: Optional[str] = None, limit: int = 100) -> List[Dict[str, Any]]:
        """Lists active delivery trips for a specific company tenant or default."""
        tenant = self.get_tenant(company_name)
        await self._ensure_valid_token(tenant)
        base = self._base_url(tenant)
        is_fio = self._is_fio(tenant)

        if is_fio:
            sales_trip_url = f"{base}/tenant/sales/trip"
            headers = {"Accept": "application/json"}
            if tenant.auth_token and not tenant.auth_token.startswith("cookie-"):
                headers["Authorization"] = f"Bearer {tenant.auth_token}"

            async with httpx.AsyncClient(timeout=15.0, cookies=tenant.cookies) as client:
                res = await client.get(sales_trip_url, headers=headers)
                if res.status_code == 401:
                    await self._login(tenant)
                    if tenant.auth_token and not tenant.auth_token.startswith("cookie-"):
                        headers["Authorization"] = f"Bearer {tenant.auth_token}"
                    res = await client.get(sales_trip_url, headers=headers, cookies=tenant.cookies)
                if res.status_code != 200:
                    return []
                s_json = res.json()
                items = s_json.get("data", []) if isinstance(s_json, dict) else s_json

                return [
                    {
                        "trip_id": it.get("tripId"),
                        "company": tenant.display_name,
                        "order_count": int(it.get("orderCount") or 1),
                        "total_amount": float(it.get("totalAmount") or 0.0),
                        "currency": it.get("currencyCode", "USD"),
                        "status": "Open" if it.get("isOpen") else "Closed"
                    }
                    for it in items[:limit]
                ]

        # Legacy PocketBase
        records_url = f"{base}/pb/api/collections/sales_order/records"
        headers = {"Authorization": tenant.auth_token, "Accept": "application/json"}
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
                    trips[tid] = {"trip_id": tid, "company": tenant.display_name, "order_count": 0, "total_amount": 0.0}
                trips[tid]["order_count"] += 1
                trips[tid]["total_amount"] += float(it.get("total", 0.0))

            return [
                {
                    "trip_id": t["trip_id"],
                    "company": t.get("company", tenant.display_name),
                    "order_count": t["order_count"],
                    "total_amount": round(t["total_amount"], 2)
                }
                for t in trips.values()
            ][:limit]


favlogix_api_service = FavlogixAPIService()
