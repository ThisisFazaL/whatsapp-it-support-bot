import os
import re
import time
import json
import base64
import logging
from typing import Dict, Any, Optional, List
import httpx

from app.config import settings

logger = logging.getLogger("favlogix_api")

try:
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature
    HAS_CRYPTO = True
except ImportError:
    ec = None
    hashes = None
    serialization = None
    decode_dss_signature = None
    HAS_CRYPTO = False


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
    """Encapsulates authentication state, ECDSA keypair, and credentials for a single company tenant."""

    def __init__(
        self,
        company_key: str,
        display_name: str,
        org_name_or_id: str,
        email: str,
        password: str,
        auth_token: str = "",
        api_url: str = "",
        reg_code: str = ""
    ):
        self.company_key = company_key.upper()  # 'LG', 'TG', 'KRECKLE', 'DEFAULT'
        self.display_name = display_name
        self.org_name_or_id = (org_name_or_id or "").strip()
        self.email = (email or "").strip()
        self.password = (password or "").strip()
        self.auth_token = (auth_token or "").strip()
        self.api_url = (api_url or "").rstrip("/")
        self.reg_code = (reg_code or "").strip()
        self.token_expiry: float = 0.0
        self.resolved_org_id: Optional[str] = None
        self.cookies: Dict[str, str] = {}
        self.device_key: Optional[str] = None
        self.private_key: Optional[Any] = None
        self.last_enroll_error: Optional[str] = None
        # Parse cookie string in auth_token if provided
        if self.auth_token and ("=" in self.auth_token or ";" in self.auth_token):
            for part in self.auth_token.split(";"):
                if "=" in part:
                    k, v = part.strip().split("=", 1)
                    self.cookies[k.strip()] = v.strip()
                    if k.strip() == "device_id":
                        self.device_key = v.strip()
        self._load_vault()

    @property
    def is_configured(self) -> bool:
        """Returns True if minimum credentials exist to authenticate this tenant."""
        return bool(self.auth_token or (self.email and self.password) or self.reg_code or self.cookies.get("session"))

    def _vault_path(self) -> str:
        vault_dir = os.path.join(os.path.dirname(__file__), "..", "..", ".device_vault")
        os.makedirs(vault_dir, exist_ok=True)
        return os.path.join(vault_dir, f"{self.company_key}.json")

    def _load_vault(self):
        """Loads cached enrolled device key, private key, and session cookies from local vault file."""
        try:
            p = self._vault_path()
            if os.path.exists(p):
                with open(p, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.device_key = data.get("device_key") or self.device_key
                    saved_cookies = data.get("cookies", {})
                    if saved_cookies:
                        self.cookies.update(saved_cookies)
                    pem = data.get("private_key_pem")
                    if pem and HAS_CRYPTO:
                        self.private_key = serialization.load_pem_private_key(pem.encode("utf-8"), password=None)
                    if self.device_key:
                        self.cookies["device_id"] = self.device_key
                    logger.info(f"Loaded vault device key for {self.company_key}: {self.device_key}")
        except Exception as e:
            logger.debug(f"Vault load note for {self.company_key}: {e}")

    def _save_vault(self):
        """Saves enrolled device key, private key, and session cookies to vault file."""
        try:
            vault_dict = {"device_key": self.device_key, "cookies": self.cookies}
            if self.private_key and HAS_CRYPTO:
                pem = self.private_key.private_bytes(
                    encoding=serialization.Encoding.PEM,
                    format=serialization.PrivateFormat.PKCS8,
                    encryption_algorithm=serialization.NoEncryption()
                ).decode("utf-8")
                vault_dict["private_key_pem"] = pem
            p = self._vault_path()
            with open(p, "w", encoding="utf-8") as f:
                json.dump(vault_dict, f)
        except Exception as e:
            logger.warning(f"Vault save note for {self.company_key}: {e}")

    async def load_from_db(self, session):
        """Loads enrolled credentials from PostgreSQL database if not present locally."""
        try:
            from app.database import get_system_vault_entry
            raw = await get_system_vault_entry(session, f"DEVICE_VAULT_{self.company_key}")
            if raw:
                data = json.loads(raw)
                self.device_key = data.get("device_key") or self.device_key
                saved_cookies = data.get("cookies", {})
                if saved_cookies:
                    self.cookies.update(saved_cookies)
                pem = data.get("private_key_pem")
                if pem and HAS_CRYPTO:
                    self.private_key = serialization.load_pem_private_key(pem.encode("utf-8"), password=None)
                if self.device_key:
                    self.cookies["device_id"] = self.device_key
                self._save_vault()
                logger.info(f"Restored vault device key & cookies for {self.company_key} from database.")
        except Exception as e:
            logger.debug(f"Vault DB load note for {self.company_key}: {e}")

    async def save_to_db(self, session):
        """Saves enrolled credentials and session cookies to PostgreSQL database."""
        try:
            vault_dict = {"device_key": self.device_key, "cookies": self.cookies}
            if self.private_key and HAS_CRYPTO:
                pem = self.private_key.private_bytes(
                    encoding=serialization.Encoding.PEM,
                    format=serialization.PrivateFormat.PKCS8,
                    encryption_algorithm=serialization.NoEncryption()
                ).decode("utf-8")
                vault_dict["private_key_pem"] = pem
            from app.database import save_system_vault_entry
            await save_system_vault_entry(session, f"DEVICE_VAULT_{self.company_key}", json.dumps(vault_dict))
            logger.info(f"Persisted vault credentials for {self.company_key} into database.")
        except Exception as e:
            logger.warning(f"Vault DB save note for {self.company_key}: {e}")

    def __repr__(self) -> str:
        return f"<CompanyTenantSession key={self.company_key} name='{self.display_name}' org='{self.org_name_or_id}' email='{self.email}' device_key={self.device_key}>"


class FavlogixAPIService:
    """
    Direct background HTTP client for Favlogix ERP (Option 1 - Headless).
    Communicates directly with Favlogix backend without requiring
    a local browser, Chrome window, or display server.

    Supports:
    1. Multi-Company Tenants (LG Plast, Tagoneswa Hardware, Kreckle Foods)
    2. Virtual Device Enrollment (ECDSA P-256 Keypair generation & verification)
    3. Modern Platform (fio.favlogix.com): Dedicated `/api/tenant/sales/trip` endpoints
    4. Legacy Platform (erp.favlogix.com): PocketBase `/api/pb/api/collections/sales_order/records`
    """

    def __init__(self):
        self.default_api_url: str = settings.favlogix_api_url.rstrip("/")
        self.tenants: Dict[str, CompanyTenantSession] = {}
        self._init_tenants()

    def _init_tenants(self):
        """Initializes tenant configurations for the 3 operating companies and a fallback default."""
        lg_email = (getattr(settings, "lgplast_email", "") or getattr(settings, "favlogix_lg_email", "") or os.getenv("LGPLAST_EMAIL", "") or os.getenv("FAVLOGIX_LG_EMAIL", "")).strip()
        lg_pass = (getattr(settings, "lgplast_password", "") or getattr(settings, "favlogix_lg_password", "") or os.getenv("LGPLAST_PASSWORD", "") or os.getenv("FAVLOGIX_LG_PASSWORD", "")).strip()
        lg_org = (getattr(settings, "lgplast_org", "") or getattr(settings, "favlogix_lg_org", "") or os.getenv("LGPLAST_ORG", "") or os.getenv("FAVLOGIX_LG_ORG", "") or "lgplast").strip()
        lg_reg = (getattr(settings, "lgplast_reg_code", "") or getattr(settings, "favlogix_lg_reg_code", "") or os.getenv("LGPLAST_REG_CODE", "") or os.getenv("FAVLOGIX_LG_REG_CODE", "")).strip()

        tg_email = (getattr(settings, "tagoneswa_email", "") or getattr(settings, "favlogix_tg_email", "") or os.getenv("TAGONESWA_EMAIL", "") or os.getenv("FAVLOGIX_TG_EMAIL", "")).strip()
        tg_pass = (getattr(settings, "tagoneswa_password", "") or getattr(settings, "favlogix_tg_password", "") or os.getenv("TAGONESWA_PASSWORD", "") or os.getenv("FAVLOGIX_TG_PASSWORD", "")).strip()
        tg_org = (getattr(settings, "tagoneswa_org", "") or getattr(settings, "favlogix_tg_org", "") or os.getenv("TAGONESWA_ORG", "") or os.getenv("FAVLOGIX_TG_ORG", "") or "tagoneswa").strip()
        tg_reg = (getattr(settings, "tagoneswa_reg_code", "") or getattr(settings, "favlogix_tg_reg_code", "") or os.getenv("TAGONESWA_REG_CODE", "") or os.getenv("FAVLOGIX_TG_REG_CODE", "")).strip()

        kr_email = (getattr(settings, "kreckle_email", "") or getattr(settings, "favlogix_kreckle_email", "") or os.getenv("KRECKLE_EMAIL", "") or os.getenv("FAVLOGIX_KRECKLE_EMAIL", "")).strip()
        kr_pass = (getattr(settings, "kreckle_password", "") or getattr(settings, "favlogix_kreckle_password", "") or os.getenv("KRECKLE_PASSWORD", "") or os.getenv("FAVLOGIX_KRECKLE_PASSWORD", "")).strip()
        kr_org = (getattr(settings, "kreckle_org", "") or getattr(settings, "favlogix_kreckle_org", "") or os.getenv("KRECKLE_ORG", "") or os.getenv("FAVLOGIX_KRECKLE_ORG", "") or "kreckle").strip()
        kr_reg = (getattr(settings, "kreckle_reg_code", "") or getattr(settings, "favlogix_kreckle_reg_code", "") or os.getenv("KRECKLE_REG_CODE", "") or os.getenv("FAVLOGIX_KRECKLE_REG_CODE", "")).strip()

        self.tenants = {
            "LG": CompanyTenantSession(
                company_key="LG",
                display_name="LG Plast",
                org_name_or_id=lg_org,
                email=lg_email,
                password=lg_pass,
                auth_token=getattr(settings, "lgplast_auth_token", "") or getattr(settings, "favlogix_lg_auth_token", "") or os.getenv("LGPLAST_AUTH_TOKEN", ""),
                api_url=getattr(settings, "favlogix_lg_api_url", "") or self.default_api_url,
                reg_code=lg_reg
            ),
            "TG": CompanyTenantSession(
                company_key="TG",
                display_name="Tagoneswa Hardware",
                org_name_or_id=tg_org,
                email=tg_email,
                password=tg_pass,
                auth_token=getattr(settings, "tagoneswa_auth_token", "") or getattr(settings, "favlogix_tg_auth_token", "") or os.getenv("TAGONESWA_AUTH_TOKEN", ""),
                api_url=getattr(settings, "favlogix_tg_api_url", "") or self.default_api_url,
                reg_code=tg_reg
            ),
            "KRECKLE": CompanyTenantSession(
                company_key="KRECKLE",
                display_name="Kreckle Foods",
                org_name_or_id=kr_org,
                email=kr_email,
                password=kr_pass,
                auth_token=getattr(settings, "kreckle_auth_token", "") or getattr(settings, "favlogix_kreckle_auth_token", "") or os.getenv("KRECKLE_AUTH_TOKEN", ""),
                api_url=getattr(settings, "favlogix_kreckle_api_url", "") or self.default_api_url,
                reg_code=kr_reg
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

        # Pre-seed verified Tagoneswa session cookies if not already configured
        if not self.tenants["TG"].cookies.get("session"):
            self.tenants["TG"].cookies.update({
                "device_id": "01a11041-9f57-770c-ad86-795b1169d6dc",
                "session": "1453d8df-eb60-4e45-bd8c-ab0717164a6c",
                "tenant": "tagoneswa",
                "csrf_token": "6c0ca903eb1dc4182bcbe84df98a234d79ea6a005677b942ccb7dff7526b6e04"
            })
            self.tenants["TG"].device_key = "01a11041-9f57-770c-ad86-795b1169d6dc"

    async def sync_vaults_from_db(self):
        """Restores any enrolled device vaults from database into tenant sessions."""
        try:
            from app.database import async_session_factory
            async with async_session_factory() as session:
                for tenant in self.tenants.values():
                    await tenant.load_from_db(session)
        except Exception as e:
            logger.warning(f"Could not sync device vaults from DB: {e}")

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

    async def enroll_device(self, tenant: CompanyTenantSession, reg_code: str) -> bool:
        """
        Enrolls a virtual device with Favlogix fio platform using an 8-character registration code.
        Generates ECDSA P-256 keypair, exports JWK, and calls /tenant/device/enroll.
        """
        if not HAS_CRYPTO:
            raise FavlogixAuthError("cryptography library is required for device enrollment.")

        base = self._base_url(tenant)
        enroll_url = f"{base}/tenant/device/enroll"

        if not tenant.private_key:
            tenant.private_key = ec.generate_private_key(ec.SECP256R1())

        pn = tenant.private_key.public_key().public_numbers()

        def b64url(n: int) -> str:
            b = n.to_bytes(32, "big")
            return base64.urlsafe_b64encode(b).decode("ascii").rstrip("=")

        jwk = {
            "kty": "EC",
            "crv": "P-256",
            "x": b64url(pn.x),
            "y": b64url(pn.y),
            "ext": True,
            "key_ops": ["verify"]
        }

        slug = (tenant.org_name_or_id or "").strip().lower()
        if not slug:
            if tenant.company_key == "LG":
                slug = "lgplast"
            elif tenant.company_key == "TG":
                slug = "tagoneswa"
            elif tenant.company_key == "KRECKLE":
                slug = "kreckle"

        raw_code = reg_code.strip().strip("'\"").strip()
        candidate_codes = [raw_code]
        if raw_code.upper() not in candidate_codes:
            candidate_codes.append(raw_code.upper())
        if raw_code.lower() not in candidate_codes:
            candidate_codes.append(raw_code.lower())

        last_res = None
        for code_attempt in candidate_codes:
            payload = {
                "slug": slug,
                "code": code_attempt,
                "publicKey": json.dumps(jwk)
            }
            logger.info(f"Enrolling device for tenant '{tenant.display_name}' with slug '{slug}' and code '{code_attempt}'...")
            async with httpx.AsyncClient(timeout=15.0) as client:
                res = await client.post(enroll_url, json=payload)
                last_res = res
                if res.status_code == 200:
                    res_data = res.json().get("data", {})
                    device_key = res_data.get("device", {}).get("key")
                    if not device_key:
                        raise FavlogixAuthError(f"Enrollment succeeded but returned no device key: {res.text}")
                    tenant.device_key = device_key
                    tenant.reg_code = code_attempt
                    tenant.cookies["device_id"] = device_key
                    tenant._save_vault()
                    try:
                        from app.database import async_session_factory
                        async with async_session_factory() as db_session:
                            await tenant.save_to_db(db_session)
                    except Exception as dbe:
                        logger.warning(f"Could not persist vault to DB for '{tenant.display_name}': {dbe}")
                    logger.info(f"Device successfully enrolled for '{tenant.display_name}'! Device Key: {device_key}")
                    return True
                elif res.status_code == 422 and "InvalidRegistrationCode" in res.text:
                    continue
                else:
                    break

        raise FavlogixAuthError(f"Device enrollment failed for '{tenant.display_name}' (HTTP {last_res.status_code if last_res else 'unknown'}): {last_res.text if last_res else 'no response'}")

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

            # Auto-enroll if reg_code is set but device not yet enrolled
            if not tenant.device_key and tenant.reg_code:
                try:
                    await self.enroll_device(tenant, tenant.reg_code)
                except Exception as enroll_err:
                    tenant.last_enroll_error = str(enroll_err)
                    logger.warning(f"Auto-enrollment attempt failed for '{tenant.display_name}': {enroll_err}")

            login_cookies = dict(tenant.cookies)
            if tenant.device_key:
                login_cookies["device_id"] = tenant.device_key

            logger.info(f"Authenticating with fio.favlogix.com for tenant '{tenant.display_name}' as '{username}' (device_id: {tenant.device_key})...")
            payload = {"username": username, "password": tenant.password}
            try:
                async with httpx.AsyncClient(timeout=15.0) as client:
                    res = await client.post(login_url, json=payload, cookies=login_cookies)
                    if res.status_code == 200:
                        tenant.cookies.update(res.cookies)
                        data = res.json() if res.text.startswith("{") else {}
                        inner_data = data.get("data", {}) if isinstance(data, dict) else {}

                        # Handle ECDSA Challenge if device authentication verification is requested
                        if "challenge" in inner_data:
                            challenge = inner_data["challenge"]
                            if not tenant.private_key or not HAS_CRYPTO:
                                raise FavlogixAuthError(f"Challenge received for '{tenant.display_name}' but private key not found in vault.")
                            der_sig = tenant.private_key.sign(challenge.encode("utf-8"), ec.ECDSA(hashes.SHA256()))
                            r_val, s_val = decode_dss_signature(der_sig)
                            raw_sig = r_val.to_bytes(32, "big") + s_val.to_bytes(32, "big")
                            sig_b64 = base64.b64encode(raw_sig).decode("ascii")

                            verify_url = f"{base}/tenant/auth/login/verify"
                            verify_payload = {
                                "signature": sig_b64,
                                "slug": inner_data.get("slug") or tenant.org_name_or_id,
                                "deviceKey": inner_data.get("deviceKey") or tenant.device_key,
                                "employeeConfigKey": inner_data.get("employeeConfigKey")
                            }
                            verify_cookies = dict(tenant.cookies)
                            verify_cookies.update(res.cookies)
                            if tenant.device_key:
                                verify_cookies["device_id"] = tenant.device_key
                            res_verify = await client.post(verify_url, json=verify_payload, cookies=verify_cookies)
                            if res_verify.status_code == 200:
                                tenant.cookies.update(res_verify.cookies)
                                v_data = res_verify.json().get("data", {}) if res_verify.text.startswith("{") else {}
                                token = v_data.get("token") or res_verify.cookies.get("session") or ""
                                if token:
                                    tenant.auth_token = token
                                    tenant.token_expiry = self._decode_token_expiry(token)
                                logger.info(f"Challenge successfully verified for '{tenant.display_name}'!")
                                return tenant.auth_token or "cookie-authenticated"
                            else:
                                raise FavlogixAuthError(f"Challenge verification failed for '{tenant.display_name}' ({res_verify.status_code}): {res_verify.text}")

                        token = data.get("token") or inner_data.get("token") or res.cookies.get("session") or ""
                        if token:
                            tenant.auth_token = token
                            tenant.token_expiry = self._decode_token_expiry(token)
                        logger.info(f"Successfully authenticated tenant '{tenant.display_name}' with fio.favlogix.com.")
                        return tenant.auth_token or "cookie-authenticated"
                    elif res.status_code in (401, 422):
                        raise FavlogixAuthError(f"fio.favlogix.com login failed for tenant '{tenant.display_name}' ({res.status_code}): {res.text}")
                    elif res.status_code == 403:
                        raise FavlogixAuthError(f"fio.favlogix.com device enrollment required for tenant '{tenant.display_name}' (HTTP 403): {res.text}")
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
        return tenant.auth_token or ("cookie-authenticated" if tenant.cookies else "")

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
            headers = {
                "Accept": "*/*",
                "Content-Type": "application/json",
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/153.0.0.0 Safari/537.36",
                "Referer": "https://fio.favlogix.com/sales/trips",
                "Origin": "https://fio.favlogix.com"
            }
            if "csrf_token" in tenant.cookies:
                headers["x-csrf-token"] = tenant.cookies["csrf_token"]
            if tenant.auth_token and not ("=" in tenant.auth_token or ";" in tenant.auth_token) and not tenant.auth_token.startswith("cookie-"):
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
