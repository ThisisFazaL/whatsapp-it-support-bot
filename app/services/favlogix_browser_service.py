import re
import time
import logging
from typing import Dict, Any, Optional
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import WebDriverException, TimeoutException

from app.config import settings

logger = logging.getLogger("favlogix_browser")


class FavlogixError(Exception):
    """Base exception for Favlogix browser automation."""
    pass


class BrowserNotConnectedError(FavlogixError):
    """Raised when Chrome remote debugging port is not reachable."""
    pass


class FavlogixSessionExpiredError(FavlogixError):
    """Raised when Favlogix displays a login or session expired screen."""
    pass


class TripNotFoundError(FavlogixError):
    """Raised when the Trip ID does not exist in Favlogix."""
    pass


class FavlogixCalculationPendingError(FavlogixError):
    """Raised when the trip calculation did not finish in time."""
    pass


class FavlogixBrowserService:
    """Controls the persistent Chrome session connected via remote debugging port."""

    def __init__(self, port: int = None, base_url: str = None, timeout: int = None):
        self.port = port or getattr(settings, "favlogix_remote_debug_port", 9222)
        self.base_url = base_url or getattr(settings, "favlogix_url", "https://erp.favlogix.com")
        self.timeout = timeout or getattr(settings, "favlogix_timeout_seconds", 30)
        self._driver: Optional[webdriver.Chrome] = None

    def get_driver(self) -> webdriver.Chrome:
        """Connects to the already running Chrome session."""
        if self._driver is not None:
            try:
                # Ping driver to verify connection is alive
                _ = self._driver.title
                return self._driver
            except Exception:
                self._driver = None

        # Pre-check port connectivity with a fast socket check to avoid ChromeDriver's 60-second hang
        import socket
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(0.5)
                res = s.connect_ex(("127.0.0.1", self.port))
                if res != 0:
                    raise BrowserNotConnectedError(
                        f"Cannot connect to Chrome on port {self.port}. "
                        "Ensure Chrome is started with: chrome.exe --remote-debugging-port=9222 --user-data-dir=..."
                    )
        except BrowserNotConnectedError:
            raise
        except Exception as e:
            raise BrowserNotConnectedError(f"Error checking Chrome port {self.port}: {e}") from e

        options = Options()
        options.add_experimental_option("debuggerAddress", f"127.0.0.1:{self.port}")

        try:
            self._driver = webdriver.Chrome(options=options)
            return self._driver
        except WebDriverException as e:
            raise BrowserNotConnectedError(
                f"Cannot connect to Chrome on port {self.port}. "
                "Ensure Chrome is started with: chrome.exe --remote-debugging-port=9222 --user-data-dir=..."
            ) from e

    def is_session_authenticated(self, driver: webdriver.Chrome) -> bool:
        """Checks if current page is showing a login or auth barrier."""
        try:
            url = driver.current_url.lower()
            if any(term in url for term in ["login", "signin", "auth", "session-expired"]):
                return False

            login_elements = driver.find_elements(By.CSS_SELECTOR, "input[type='password'], button[type='submit'], form[action*='login']")
            if login_elements and any(el.is_displayed() for el in login_elements):
                return False

            return True
        except Exception:
            return True

    def _close_modal(self, driver: webdriver.Chrome):
        """Cleanly dismisses the modal without saving or creating a packaging list."""
        try:
            close_buttons = driver.find_elements(By.XPATH, "//button[contains(text(), 'Close') or @data-slot='dialog-close']")
            for cb in close_buttons:
                if cb.is_displayed():
                    ActionChains(driver).move_to_element(cb).click().perform()
                    time.sleep(0.5)
                    break
        except Exception:
            pass

    def extract_trip_data(self, trip_id: str) -> Dict[str, Any]:
        """
        Navigates to Packaging Lists, opens the creation modal,
        selects Trip-based delivery and the target Trip ID,
        extracts the Total Amount and destination city, and closes the modal cleanly.
        """
        driver = self.get_driver()

        # Step 1: Check session health
        if not self.is_session_authenticated(driver):
            raise FavlogixSessionExpiredError(
                "Favlogix session has expired. Please log into Favlogix in the automation browser window."
            )

        # Step 2: Ensure on packaging-lists page
        target_url = "https://erp.favlogix.com/inventory/packaging-lists"
        if "inventory/packaging-lists" not in driver.current_url:
            driver.get(target_url)
            time.sleep(1.5)

        # Step 3: Check if modal is already open
        modal_open = False
        close_btns = driver.find_elements(By.XPATH, "//button[contains(text(), 'Close') or @data-slot='dialog-close']")
        for cb in close_btns:
            if cb.is_displayed():
                modal_open = True
                break

        if not modal_open:
            create_btn = WebDriverWait(driver, self.timeout).until(
                EC.element_to_be_clickable((By.XPATH, "//button[contains(., 'Create Packaging List')]"))
            )
            create_btn.click()
            time.sleep(1.0)

        # Step 4: Ensure Delivery Type is 'Trip-based'
        delivery_triggers = driver.find_elements(By.XPATH, "//div[contains(., 'Delivery Type')]//button[@data-slot='select-trigger']")
        if delivery_triggers:
            dt_trig = delivery_triggers[-1]
            if "trip-based" not in dt_trig.text.lower():
                dt_trig.click()
                time.sleep(0.5)
                trip_based_opts = driver.find_elements(By.XPATH, "//*[@role='option' and contains(., 'Trip-based')] | //*[@data-slot='select-item' and contains(., 'Trip-based')]")
                if trip_based_opts:
                    trip_based_opts[0].click()
                    time.sleep(0.8)

        # Step 5: Locate Trip Trigger
        trip_triggers = driver.find_elements(
            By.XPATH,
            "//*[contains(text(), 'Trip Orders') or contains(text(), 'Sales Orders')]/ancestor::div[contains(@class, 'rounded') or contains(@class, 'space-y')][1]//button[@data-slot='select-trigger']"
        )
        if not trip_triggers:
            all_triggers = driver.find_elements(By.CSS_SELECTOR, "[data-slot='select-trigger']")
            if len(all_triggers) >= 4:
                trip_triggers = [all_triggers[3]]

        if not trip_triggers:
            self._close_modal(driver)
            raise TripNotFoundError(f"Trip dropdown not found in Favlogix packaging list modal.")

        trip_trigger = trip_triggers[0]
        cleaned_search = trip_id.strip().upper().replace("TRIP-", "")

        # Open dropdown if closed
        if trip_trigger.get_attribute("data-state") != "open":
            trip_trigger.click()
            time.sleep(0.6)

        # Step 6: Find matching trip in options
        options = driver.find_elements(By.XPATH, "//*[@role='option'] | //*[@data-slot='select-item']")
        target_option = None
        matched_trip_name = ""

        # Substring match
        for opt in options:
            opt_text = opt.text.strip().upper()
            if cleaned_search in opt_text:
                target_option = opt
                matched_trip_name = opt.text.strip()
                break

        # Fuzzy match across tokens
        if not target_option:
            tokens = [t for t in re.split(r"[-_\s]+", cleaned_search) if len(t) >= 3]
            for opt in options:
                opt_text = opt.text.strip().upper()
                if any(t in opt_text for t in tokens):
                    target_option = opt
                    matched_trip_name = opt.text.strip()
                    break

        if not target_option:
            ActionChains(driver).send_keys(Keys.ESCAPE).perform()
            time.sleep(0.3)
            self._close_modal(driver)
            avail = [o.text.strip().splitlines()[0] for o in options if o.text.strip()]
            avail_str = ", ".join(avail[:6]) if avail else "None"
            raise TripNotFoundError(
                f"Trip ID '{trip_id}' not found in active Favlogix trips.\nAvailable trips include: {avail_str}"
            )

        # Click the target trip option
        target_option.click()
        time.sleep(1.2)

        # Step 7: Ensure orders are selected in the trip
        orders = driver.find_elements(
            By.XPATH,
            "//*[contains(text(), 'Trip Orders') or contains(text(), 'Sales Orders')]/ancestor::div[contains(@class, 'rounded') or contains(@class, 'space-y')][1]//div[@role='button']"
        )
        for ord_elem in orders:
            cls = ord_elem.get_attribute("class") or ""
            if "border-primary" not in cls:
                ord_elem.click()
                time.sleep(0.5)

        if orders:
            time.sleep(0.8)

        # Step 8: Extract Total Amount
        total_spans = driver.find_elements(
            By.XPATH,
            "//div[contains(., 'Total Amount')]//span[contains(@class, 'tabular-nums') or contains(text(), '$')]"
        )
        total_amount = None
        if total_spans:
            raw_text = total_spans[0].text.strip()
            clean_num = re.sub(r"[^\d.]", "", raw_text)
            if clean_num:
                total_amount = float(clean_num)

        # Step 9: Extract Destination City
        dest_city = ""
        city_match = re.search(r"[-_]([A-Za-z]+)", matched_trip_name)
        if city_match:
            dest_city = city_match.group(1)
        else:
            deliv_loc = driver.find_elements(
                By.XPATH,
                "//*[contains(text(), 'DELIVERY LOCATION') or contains(text(), 'Delivery Location')]/following::*[1]"
            )
            if deliv_loc:
                dest_city = deliv_loc[0].text.strip()

        # Step 10: Cleanly Close Modal
        self._close_modal(driver)

        if total_amount is None:
            if not orders:
                raise FavlogixCalculationPendingError(
                    f"Trip '{matched_trip_name.splitlines()[0]}' currently has 0 active sales orders in Favlogix."
                )
            raise FavlogixCalculationPendingError(
                f"Could not read Total Amount for '{matched_trip_name.splitlines()[0]}'. Favlogix calculation may still be pending."
            )

        clean_trip_id = matched_trip_name.splitlines()[0]
        return {
            "trip_id": clean_trip_id,
            "total_amount": total_amount,
            "destination_city": dest_city or "Bulawayo",
            "route": "",
            "status": "CALCULATED"
        }
