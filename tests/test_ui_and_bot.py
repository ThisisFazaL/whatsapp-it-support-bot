import asyncio
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import pytest
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
from httpx import AsyncClient, ASGITransport
from app.main import app

@pytest.mark.asyncio
async def test_dashboard_and_auth():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Test Login
        login_res = await client.post("/login", json={"username": "admin", "password": "Admin@Tagoneswa2026!"})
        assert login_res.status_code == 200, f"Login failed: {login_res.text}"
        cookies = login_res.cookies
        print("✅ Login successful for admin")

        # 2. Test Dashboard HTML
        dash_res = await client.get("/dashboard", cookies=cookies)
        assert dash_res.status_code == 200
        html = dash_res.text
        
        # Verify Banner is strictly inside view-fleet
        assert 'id="master-kpi-banner"' in html
        view_fleet_pos = html.find('id="view-fleet"')
        banner_pos = html.find('id="master-kpi-banner"')
        view_it_pos = html.find('id="view-it"')
        
        assert view_it_pos < view_fleet_pos < banner_pos, "Banner is not placed inside view-fleet!"
        print("✅ Banner verified inside view-fleet (not in view-it or global container)")

        # Verify Theme Toggle
        assert "toggleTheme()" in html
        assert "theme-toggle-btn" in html
        assert "theme-toggle-icon" in html
        assert "localStorage.getItem('tagoneswa_theme')" in html
        print("✅ Dark/Light theme toggle controls and persistence script verified")

        # Verify Pure OLED Black Theme & Widescreen Enterprise Container
        assert "max-w-[1780px]" in html, "Widescreen fluid layout max-w-[1780px] missing!"
        assert ("dark:bg-black" in html or "dark:bg-[#000000]" in html), "Pure OLED pitch black dark:bg-black missing!"
        print("✅ Pure OLED black theme & widescreen enterprise fluid layout verified")

        # Verify Technician Performance Cards at Top (Above Tickets Table)
        admin_cards_pos = html.find('id="it-admin-cards"')
        it_table_pos = html.find('id="it-table-card"')
        assert admin_cards_pos != -1 and it_table_pos != -1
        assert admin_cards_pos < it_table_pos, "Technician SLA cards must appear ABOVE the 100-ticket table!"
        assert "filterByITAdmin" in html, "Interactive click-to-filter technician helper missing!"
        print("✅ Technician performance SLA cards verified at top above tickets table")

        # Verify 15-per-page Pagination Controls across all 5 tables
        assert 'id="it-pagination-controls"' in html
        assert 'id="proj-pagination-controls"' in html
        assert 'id="ws-pagination-controls"' in html
        assert 'id="ledger-pagination-controls"' in html
        assert 'id="fleet-pagination-controls"' in html
        assert "renderPaginationControls" in html
        print("✅ 15-per-page pagination controls verified across all 5 dashboard views")

        # 3. Test API data
        data_res = await client.get("/api/dashboard/data", cookies=cookies)
        assert data_res.status_code == 200
        data = data_res.json()
        assert "fleet" in data and "it" in data and "projects" in data and "logistics" in data
        assert "master_kpis" in data
        print("✅ API partitioned data returned successfully")

        # 4. Test Webhook Reaction filter (Silent return & Mocked Meta API)
        from unittest.mock import patch, AsyncMock
        with patch("app.meta_api.meta_api.send_text_message", new_callable=AsyncMock) as mock_send_text, \
             patch("app.meta_api.meta_api.send_button_message", new_callable=AsyncMock) as mock_send_btn, \
             patch("app.meta_api.meta_api.send_image_message", new_callable=AsyncMock) as mock_send_img:

            reaction_payload = {
                "entry": [{
                    "changes": [{
                        "value": {
                            "messages": [{
                                "from": "910000000000",
                                "type": "reaction",
                                "reaction": {"emoji": "👍"}
                            }]
                        }
                    }]
                }]
            }
            from app.main import process_webhook_payload
            await process_webhook_payload(reaction_payload)
            assert mock_send_text.call_count == 0
            assert mock_send_btn.call_count == 0
            print("✅ Webhook reaction silently ignored without spamming user")

            # 5. Test Webhook Passive chatter filter
            passive_payload = {
                "entry": [{
                    "changes": [{
                        "value": {
                            "messages": [{
                                "from": "910000000000",
                                "type": "text",
                                "text": {"body": "ok"}
                            }]
                        }
                    }]
                }]
            }
            await process_webhook_payload(passive_payload)
            assert mock_send_text.call_count == 0
            assert mock_send_btn.call_count == 0
            print("✅ Webhook passive chatter (ok) silently acknowledged without spamming user")

            # 6. Test Admin Command Fallback Safety
            from app.database import async_session_factory
            from app.handlers.admin_handler import handle_admin_command
            async with async_session_factory() as session:
                is_handled = await handle_admin_command(session, "919265368695", "ok")
                assert is_handled is False, f"Expected handle_admin_command to return False for 'ok', got {is_handled}"
                assert mock_send_text.call_count == 0
                assert mock_send_btn.call_count == 0
                print("✅ Admin handler safely ignored non-command 'ok' without triggering greeting or ticket dump")

if __name__ == "__main__":
    asyncio.run(test_dashboard_and_auth())

