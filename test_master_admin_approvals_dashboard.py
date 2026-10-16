# test_master_admin_approvals_dashboard.py
import os
import asyncio
import datetime
import httpx
from sqlalchemy import select, delete

os.environ["ENVIRONMENT"] = "development"

from app.main import app
from app.database import (
    async_session_factory,
    init_db_models,
    FleetEmergencyExpense,
    FleetTripApproval,
    AuditLog
)
from app.dashboard import create_session_token, COOKIE_NAME

async def run_tests():
    print("=== Running Master Admin Approvals & Dashboard Integration Tests ===", flush=True)

    # 1. Setup test records
    async with async_session_factory() as session:
        # Clean previous test records if any
        await session.execute(delete(FleetEmergencyExpense).where(FleetEmergencyExpense.trip_id.in_(["TRIP-TEST-ALLOWANCE-01", "TRIP-TEST-FUEL-02"])))
        await session.execute(delete(FleetTripApproval).where(FleetTripApproval.trip_id == "TRIP-TEST-SHORTFALL-01"))
        await session.commit()

        exp1 = FleetEmergencyExpense(
            trip_id="TRIP-TEST-ALLOWANCE-01",
            driver_phone="263771112233",
            charge_type="EXTRA_ALLOWANCE",
            amount=45.00,
            description="Accommodation: $30.00; Food: $15.00 | Breakdown: Night stop in Masvingo due to vehicle puncture",
            status="PENDING",
            receipt_image_id=None,
            created_at=datetime.datetime.utcnow()
        )
        session.add(exp1)

        exp2 = FleetEmergencyExpense(
            trip_id="TRIP-TEST-FUEL-02",
            driver_phone="263771112233",
            charge_type="EMERGENCY_FUEL",
            amount=25.00,
            description="Emergency Fuel: 15 Litres top up near Beitbridge",
            status="PENDING",
            receipt_image_id=None,
            created_at=datetime.datetime.utcnow()
        )
        session.add(exp2)

        shortfall_appr = FleetTripApproval(
            trip_id="TRIP-TEST-SHORTFALL-01",
            salesperson_phone="263772223344",
            salesperson_name="Farai Test Rep",
            destination_city="Bulawayo",
            route="Direct Route",
            trip_sales_value=1200.0,
            required_minimum=2000.0,
            shortfall=800.0,
            transport_charge=75.0,
            has_shortfall=True,
            status="SHORTFALL_RECORDED",
            created_at=datetime.datetime.utcnow()
        )
        session.add(shortfall_appr)

        await session.commit()
        await session.refresh(exp1)
        await session.refresh(exp2)
        exp1_id = exp1.id
        exp2_id = exp2.id
        shortfall_trip_id = shortfall_appr.trip_id

    print(f"Created test records: Expense 1 ID={exp1_id}, Expense 2 ID={exp2_id}, Shortfall Trip={shortfall_trip_id}", flush=True)

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # 3. Test Dashboard HTML includes the new UI components
        token_admin = create_session_token("faizan", "MASTER_ADMIN")
        client.cookies.set(COOKIE_NAME, token_admin)

        res_dash = await client.get("/dashboard")
        assert res_dash.status_code == 200, f"Expected 200, got {res_dash.status_code}"
        html = res_dash.text

        assert "driver-approvals-tbody" in html, "Missing driver-approvals-tbody in dashboard HTML"
        assert "driver-approvals-mobile-list" in html, "Missing driver-approvals-mobile-list in dashboard HTML"
        assert "driverApprovalDetailModal" in html, "Missing driverApprovalDetailModal in dashboard HTML"
        assert "rejectExpenseModal" in html, "Missing rejectExpenseModal in dashboard HTML"
        assert "Approver" in html, "Missing Approver column header in dashboard HTML"
        print("[PASS] Dashboard HTML contains all driver approvals tables, mobile containers, and modals.", flush=True)

        # 4. Test /api/dashboard/data returns enriched driver_approvals
        res_data = await client.get("/api/dashboard/data")
        assert res_data.status_code == 200
        data = res_data.json()
        assert "driver_approvals" in data.get("fleet", {}), "Missing driver_approvals in fleet payload"

        driver_apprs = data["fleet"]["driver_approvals"]
        matched_exp1 = next((e for e in driver_apprs if e["id"] == exp1_id), None)
        assert matched_exp1 is not None, f"Expense {exp1_id} not found in driver_approvals list"
        assert matched_exp1["charge_type"] == "EXTRA_ALLOWANCE"
        assert matched_exp1["amount"] == 45.00
        assert matched_exp1["status"] == "PENDING"
        print("[PASS] /api/dashboard/data correctly returns enriched driver approval records.", flush=True)

        # 5. Test RBAC: Regular observer or user without permissions cannot decide approvals (403)
        token_observer = create_session_token("executive", "EXECUTIVE_OBSERVER")
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client_obs:
            client_obs.cookies.set(COOKIE_NAME, token_observer)
            res_forbidden = await client_obs.post(
                "/api/v2/fleet/approvals/decide",
                json={"expense_id": exp1_id, "action": "APPROVE"}
            )
            assert res_forbidden.status_code == 403, f"Expected 403 Forbidden for observer, got {res_forbidden.status_code}"
            print("[PASS] Non-admin user correctly blocked with 403 Forbidden.", flush=True)

        # 6. Master Admin approves Expense 1 (Extra Allowance)
        res_approve = await client.post(
            "/api/v2/fleet/approvals/decide",
            json={"expense_id": exp1_id, "action": "APPROVE"}
        )
        assert res_approve.status_code == 200, f"Approval failed: {res_approve.text}"
        appr_json = res_approve.json()
        assert appr_json.get("status") == "success"
        assert appr_json.get("decision") == "APPROVE"
        approver_name = appr_json.get("approved_by")
        assert approver_name, "Approver name must be recorded in response"
        print(f"[PASS] Master Admin successfully approved Expense #{exp1_id} (Approver recorded: {approver_name}).", flush=True)

        # 7. Master Admin rejects Expense 2 with reason
        rejection_reason = "Corridor fuel rate exceeded; fuel at Masvingo depot instead."
        res_reject = await client.post(
            "/api/v2/fleet/approvals/decide",
            json={"expense_id": exp2_id, "action": "REJECT", "rejection_note": rejection_reason}
        )
        assert res_reject.status_code == 200, f"Rejection failed: {res_reject.text}"
        rej_json = res_reject.json()
        assert rej_json.get("status") == "success"
        assert rej_json.get("decision") == "REJECT"
        print(f"[PASS] Master Admin successfully rejected Expense #{exp2_id} with note.", flush=True)

        # 8. Verify in /api/dashboard/data that both decisions reflect with approver attribution
        res_data_after = await client.get("/api/dashboard/data")
        assert res_data_after.status_code == 200
        data_after = res_data_after.json()
        driver_apprs_after = data_after["fleet"]["driver_approvals"]

        e1_after = next((e for e in driver_apprs_after if e["id"] == exp1_id), None)
        assert e1_after is not None
        assert e1_after["status"] == "APPROVED"
        assert e1_after["approved_by"] == approver_name, f"Expected {approver_name}, got {e1_after['approved_by']}"

        e2_after = next((e for e in driver_apprs_after if e["id"] == exp2_id), None)
        assert e2_after is not None
        assert e2_after["status"] == "REJECTED"
        assert e2_after["approved_by"] == approver_name
        assert e2_after["rejection_note"] == rejection_reason
        print("[PASS] /api/dashboard/data reflects updated APPROVED and REJECTED statuses with approver name and rejection note.", flush=True)

        # 9. Test Trip Shortfall approval
        res_shortfall = await client.post(
            "/api/v2/fleet/trip-approvals/decide",
            json={"trip_id": shortfall_trip_id, "action": "APPROVE"}
        )
        assert res_shortfall.status_code == 200, f"Shortfall approval failed: {res_shortfall.text}"
        sf_json = res_shortfall.json()
        assert sf_json.get("status") == "success"
        print(f"[PASS] Master Admin successfully approved trip shortfall for {shortfall_trip_id}.", flush=True)

        # 10. Verify shortfall approval in dashboard data
        res_data_sf = await client.get("/api/dashboard/data")
        data_sf = res_data_sf.json()
        records_sf = data_sf["fleet"]["records"]
        sf_rec = next((r for r in records_sf if r["trip_id"] == shortfall_trip_id), None)
        assert sf_rec is not None
        assert sf_rec["status"] == "APPROVED"
        assert sf_rec["approved_by"] == approver_name
        print(f"[PASS] Shortfall approval verified: status=APPROVED, approved_by={sf_rec['approved_by']}.", flush=True)

    print("\n[SUCCESS] ALL MASTER ADMIN APPROVAL TESTS PASSED SUCCESSFULLY!", flush=True)

if __name__ == "__main__":
    asyncio.run(run_tests())
