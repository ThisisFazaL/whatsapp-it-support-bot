# Dedicated Laptop 24/7 Setup Guide for Real ERP Automation

This guide explains how to set up a dedicated laptop (or office PC) to run the Favlogix Chrome automation in the background 24/7.

---

## 1. Laptop System & Power Settings (Crucial)

Since this laptop will run 24/7 in the background without a user sitting in front of it:
1. **Prevent Sleep on AC Power**:
   - Open Windows **Settings** -> **System** -> **Power & battery**.
   - Under **Screen and sleep**:
     - *When plugged in, put my device to sleep after*: Set to **Never**.
     - *When plugged in, turn off my screen after*: Set to **Never** (or 30 mins, screen off is fine but sleep must be Never).
2. **Close Lid Action (Laptops only)**:
   - Open **Control Panel** -> **Power Options** -> **Choose what closing the lid does**.
   - Under *When I close the lid (Plugged in)*: Select **Do nothing**.
   - This allows you to close the laptop lid and tuck it away while Chrome keeps running!

---

## 2. Setting Your Real ERP Website URL

When moving from the test site (`https://erp.favlogix.com`) to your **real production ERP**:
1. Open the project's `.env` file on the laptop:
   ```env
   # Real Production ERP URL
   FAVLOGIX_URL=https://your-real-erp-domain.com
   FAVLOGIX_PACKAGING_LISTS_PATH=/inventory/packaging-lists
   ```
2. The automation will automatically navigate to your real ERP packaging lists URL without modifying any Python code.

---

## 3. First-Time Setup on the Laptop

1. **Install Prerequisites**:
   - [Google Chrome](https://www.google.com/chrome/)
   - [Python 3.11 or 3.12](https://www.python.org/downloads/) (Check *Add Python to PATH* during installation)
   - [Ngrok](https://ngrok.com/) (Run `ngrok config add-authtoken <YOUR_TOKEN>`)
2. **Install Python Dependencies**:
   Open Command Prompt in the repository folder:
   ```cmd
   python -m venv venv
   .\venv\Scripts\activate
   pip install -r requirements.txt
   ```

---

## 4. Launching the 24/7 Automation

Run the one-click launcher:
👉 **Double-click `worker\start_all_24x7.bat`**

This script automatically:
1. Launches Chrome with `--remote-debugging-port=9222` using a dedicated profile folder at `C:\FavlogixWorkerProfile`.
2. Adds anti-throttling flags (`--disable-background-timer-throttling`, `--disable-backgrounding-occluded-windows`, `--disable-renderer-backgrounding`) so Windows never suspends Chrome even when minimized.
3. Launches the Ngrok tunnel connecting your laptop to Render.
4. Starts the local FastAPI bridge worker on port 8000.

### One-Time Login:
In the Chrome window that opens:
- Navigate to your ERP and **log in once** with your credentials.
- Check **Remember Me** / Keep me signed in.
- Your session cookies are stored permanently in `C:\FavlogixWorkerProfile` and will survive computer restarts.

---

## 5. Auto-Start on Windows Boot (Optional but Recommended)

To make the laptop automatically resume all services if the computer restarts or recovers from a power outage:
1. Press `Win + R`, type:
   ```cmd
   shell:startup
   ```
   and press Enter.
2. Create a shortcut to `worker\start_all_24x7.bat` and paste it inside this Startup folder.
3. Now whenever the laptop boots up, the entire background automation stack starts automatically!
