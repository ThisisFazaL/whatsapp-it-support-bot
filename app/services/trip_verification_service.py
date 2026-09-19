import logging
import httpx
from typing import Dict, Any, Optional

from app.config import settings
from app.services.trip_pricing_service import calculate_trip_approval, CityNotFoundError
from app.services.favlogix_browser_service import (
    FavlogixBrowserService,
    BrowserNotConnectedError,
    FavlogixSessionExpiredError,
    TripNotFoundError,
    FavlogixCalculationPendingError
)

logger = logging.getLogger("trip_verification")


class TripVerificationService:
    """Unified service that coordinates Favlogix data extraction and Zimbabwe pricing calculations."""

    def __init__(self):
        self.browser_service = FavlogixBrowserService()

    async def verify_trip(self, trip_id: str) -> Dict[str, Any]:
        """
        Extracts trip valuation and executes pricing verification.
        Supports both local direct Chrome automation and remote bridge tunneling (e.g. Render -> ngrok -> local).
        """
        raw_trip_data = None
        error_reason = None

        # 1. Attempt local Chrome browser automation (fast socket pre-check prevents hangs)
        try:
            raw_trip_data = self.browser_service.extract_trip_data(trip_id)
            logger.info(f"Successfully extracted trip data locally for '{trip_id}': {raw_trip_data}")
        except BrowserNotConnectedError:
            logger.info("Local Chrome port 9222 not reachable. Checking remote Favlogix bridge URL...")
            # 2. If running on Render or remote, check if bridge URL is configured
            bridge_url = getattr(settings, "favlogix_bridge_url", None)
            if bridge_url:
                try:
                    async with httpx.AsyncClient(timeout=20.0) as client:
                        clean_bridge = bridge_url.rstrip("/")
                        res = await client.get(f"{clean_bridge}/api/favlogix/verify-trip", params={"trip_id": trip_id})
                        if res.status_code == 200:
                            data = res.json()
                            if data.get("success"):
                                raw_trip_data = {
                                    "trip_id": data.get("trip_id", trip_id),
                                    "total_amount": float(data.get("total_amount", 0)),
                                    "destination_city": data.get("destination_city", "Bulawayo"),
                                    "status": "CALCULATED"
                                }
                            else:
                                error_reason = data.get("error", "Unknown error from Favlogix bridge.")
                        else:
                            error_reason = f"Favlogix bridge returned HTTP {res.status_code}."
                except Exception as bridge_err:
                    logger.error(f"Error calling Favlogix bridge: {bridge_err}")
                    error_reason = f"Could not reach Favlogix bridge: {bridge_err}"
            else:
                error_reason = "Favlogix automation browser is not connected (Chrome port 9222 closed)."
        except (TripNotFoundError, FavlogixSessionExpiredError, FavlogixCalculationPendingError) as specific_err:
            error_reason = str(specific_err)
        except Exception as generic_err:
            logger.error(f"Unexpected error extracting trip '{trip_id}': {generic_err}", exc_info=True)
            error_reason = f"Favlogix extraction failed: {generic_err}"

        if not raw_trip_data:
            return {
                "success": False,
                "trip_id": trip_id,
                "error": error_reason or "Failed to retrieve trip data from Favlogix."
            }

        # 3. Calculate minimum sales and 4% transport charge
        amount = raw_trip_data.get("total_amount", 0.0)
        destination = raw_trip_data.get("destination_city", "Bulawayo")

        try:
            pricing = calculate_trip_approval(actual_sales=amount, destination=destination)
            return {
                "success": True,
                "trip_id": raw_trip_data.get("trip_id", trip_id),
                "total_amount": pricing["trip_value"],
                "destination_city": pricing["city"],
                "route": pricing["route"],
                "required_minimum": pricing["required_minimum"],
                "shortfall": pricing["shortfall"],
                "transport_charge": pricing["transport_charge"],
                "approved": pricing["approved"]
            }
        except CityNotFoundError:
            # Fallback to general city rule
            fallback_pricing = calculate_trip_approval(actual_sales=amount, destination="Bulawayo")
            return {
                "success": True,
                "trip_id": raw_trip_data.get("trip_id", trip_id),
                "total_amount": amount,
                "destination_city": destination,
                "route": "Custom Destination",
                "required_minimum": fallback_pricing["required_minimum"],
                "shortfall": fallback_pricing["shortfall"],
                "transport_charge": fallback_pricing["transport_charge"],
                "approved": fallback_pricing["approved"]
            }


trip_verification_service = TripVerificationService()
