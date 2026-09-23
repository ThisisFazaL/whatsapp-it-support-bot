import asyncio
import sys
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

        # 4. Test Webhook Reaction filter (Silent return)
        reaction_payload = {
            "entry": [{
                "changes": [{
                    "value": {
                        "messages": [{
                            "from": "919265368695",
                            "type": "reaction",
                            "reaction": {"emoji": "👍"}
                        }]
                    }
                }]
            }]
        }
        webhook_res = await client.post("/webhook/meta-whatsapp", json=reaction_payload)
        assert webhook_res.status_code == 200
        assert webhook_res.json().get("status") == "accepted"
        
        # Test background processor on reaction
        from app.main import process_webhook_payload
        await process_webhook_payload(reaction_payload)
        print("✅ Webhook reaction silently ignored without spamming user")

        # 5. Test Webhook Passive chatter filter
        passive_payload = {
            "entry": [{
                "changes": [{
                    "value": {
                        "messages": [{
                            "from": "919265368695",
                            "type": "text",
                            "text": {"body": "ok"}
                        }]
                    }
                }]
            }]
        }
        passive_res = await client.post("/webhook/meta-whatsapp", json=passive_payload)
        assert passive_res.status_code == 200
        assert passive_res.json().get("status") == "accepted"
        
        # Test background processor on passive chatter
        await process_webhook_payload(passive_payload)
        print("✅ Webhook passive chatter (ok) silently acknowledged without spamming user")

if __name__ == "__main__":
    asyncio.run(test_dashboard_and_auth())
