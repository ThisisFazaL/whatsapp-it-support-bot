import asyncio
import logging
from app.meta_api import meta_api

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("buttons_showcase")

async def send_showcase():
    phone = "919265368695"
    logger.info(f"Starting Sales & Fleet live button showcase for Fazal ({phone})...")

    # Banner Intro
    await meta_api.send_text_message(
        phone,
        "🎬 *TAGONESWA SALES & FLEET — LIVE BUTTON SHOWCASE*\n"
        "════════════════════════════\n"
        "Here are the exact interactive button cards as they appear to each team member in live production.\n\n"
        "Sending each message in exact operational sequence across all 7 stages..."
    )
    await asyncio.sleep(1.5)

    # 1. Sales Portal Menu
    await meta_api.send_button_message(
        to_phone=phone,
        header_text="TAGONESWA SALES PORTAL",
        body_text=(
            "👋 *STAGE 1: SALES PORTAL ENTRY*\n"
            "────────────────────\n"
            "Welcome Tinashe (Sales Rep)!\n"
            "Please select an option below:"
        ),
        buttons=[
            {"id": "demo_btn_fleet", "title": "Fleet Trip Approval"},
            {"id": "demo_btn_pending", "title": "Pending Balance"},
            {"id": "demo_btn_it", "title": "IT Support"}
        ]
    )
    await asyncio.sleep(1.5)

    # 2. Company Selection
    await meta_api.send_button_message(
        to_phone=phone,
        header_text="SELECT COMPANY",
        body_text=(
            "🏢 *STAGE 1: COMPANY SELECTION*\n"
            "────────────────────\n"
            "Which operating company is this trip for?\n\n"
            "• Auto-routes return balancing to this company's assigned Sales Admin."
        ),
        buttons=[
            {"id": "demo_co_tg", "title": "A. TG Hardware"},
            {"id": "demo_co_lg", "title": "B. LG Plast"},
            {"id": "demo_co_kr", "title": "C. Kreckle"}
        ]
    )
    await asyncio.sleep(1.5)

    # 3. Clean Shortfall Card
    await meta_api.send_button_message(
        to_phone=phone,
        header_text="FLEET TRIP DETAILS",
        body_text=(
            "📋 *STAGE 1: CLEAN SHORTFALL VIEW*\n"
            "────────────────────\n"
            "🏢 Company: A. TG Hardware\n"
            "🚛 Trip: `TRIP-2026-00456`\n"
            "📍 Destination: Gweru\n"
            "💰 Sales Total: $14,200.00\n"
            "💸 Transport Fee to Take: *$152.00*\n"
            "────────────────────\n"
            "*(Route Minimum and 4% formula strictly hidden)*\n\n"
            "Please select how transport fee will be handled:"
        ),
        buttons=[
            {"id": "demo_sf_full", "title": "Full Charge"},
            {"id": "demo_sf_part", "title": "Partial Charge"},
            {"id": "demo_sf_pend", "title": "Add to Pending"}
        ]
    )
    await asyncio.sleep(1.5)

    # 4. Favlogix Charge Confirmation
    await meta_api.send_button_message(
        to_phone=phone,
        header_text="FAVLOGIX CHARGES",
        body_text=(
            "📋 *STAGE 2: FAVLOGIX CHARGE CHECK*\n"
            "────────────────────\n"
            "Full transport charge of $152.00 selected.\n\n"
            "Please charge all customers in Favlogix and select YES when done:"
        ),
        buttons=[
            {"id": "demo_chg_yes", "title": "YES"},
            {"id": "demo_chg_no", "title": "NO"}
        ]
    )
    await asyncio.sleep(1.5)

    # 5. Edward Queue / Allocation
    await meta_api.send_button_message(
        to_phone=phone,
        header_text="LOGISTICS QUEUE",
        body_text=(
            "🚛 *STAGE 3: EDWARD TRIP ALLOCATION*\n"
            "────────────────────\n"
            "Company: A. TG Hardware\n"
            "Trip: `TRIP-2026-00456`\n"
            "Route: Gweru\n"
            "Rep: Tinashe\n"
            "Registered Customers: 3\n"
            "────────────────────\n"
            "🔒 *(Sales Total strictly hidden from Edward)*\n\n"
            "Please select an action:"
        ),
        buttons=[
            {"id": "demo_edw_alloc", "title": "Allocate Trip"},
            {"id": "demo_edw_queue", "title": "Trip Queue"}
        ]
    )
    await asyncio.sleep(1.5)

    # 6. Edward Review Card
    await meta_api.send_button_message(
        to_phone=phone,
        header_text="CONFIRM ALLOCATION",
        body_text=(
            "📋 *STAGE 3: EDWARD REVIEW SUMMARY*\n"
            "────────────────────\n"
            "Trip: `TRIP-2026-00456` | Route: Gweru\n"
            "Truck: ZW 123 ABC | Driver: John Banda\n"
            "Crew: 2 people | Meals: 3 | Tolls: 4\n"
            "────────────────────\n"
            "Toll cost: $34.50\n"
            "Food ($2 x 2 x 3): $12.00\n"
            "Total allowance: $46.50\n"
            "────────────────────\n"
            "Please review and confirm:"
        ),
        buttons=[
            {"id": "demo_edw_conf", "title": "Confirm"},
            {"id": "demo_edw_chg", "title": "Change"}
        ]
    )
    await asyncio.sleep(1.5)

    # 7. Zayn Allowance Approval
    await meta_api.send_button_message(
        to_phone=phone,
        header_text="ALLOWANCE APPROVAL",
        body_text=(
            "💰 *STAGE 4: ZAYN ALLOWANCE APPROVAL*\n"
            "────────────────────\n"
            "Company: A. TG Hardware\n"
            "Trip: `TRIP-2026-00456` | Route: Gweru\n"
            "Driver: John Banda | Truck: ZW 123 ABC\n"
            "Crew: 2 people | Meals: 3 | Tolls: 4\n"
            "────────────────────\n"
            "Toll cost: $34.50\n"
            "Food ($2 x 2 x 3): $12.00\n"
            "────────────────────\n"
            "Total allowance: *$46.50*\n\n"
            "Please approve or recalculate:"
        ),
        buttons=[
            {"id": "demo_zayn_appr", "title": "Approve"},
            {"id": "demo_zayn_recalc", "title": "Recalculate"}
        ]
    )
    await asyncio.sleep(1.5)

    # 8. Accounts Transfer Done
    await meta_api.send_button_message(
        to_phone=phone,
        header_text="ACCOUNTS TRANSFER",
        body_text=(
            "💸 *STAGE 4: ACCOUNTS DISBURSEMENT*\n"
            "────────────────────\n"
            "Trip: `TRIP-2026-00456`\n"
            "Driver: John Banda (+263779888777)\n"
            "Total Allowance: $46.50\n"
            "────────────────────\n"
            "Approved by Zayn. Please release cash/transfer and tap below when done:"
        ),
        buttons=[
            {"id": "demo_acc_done", "title": "Transfer Done"}
        ]
    )
    await asyncio.sleep(1.5)

    # 9. Driver Trip Started
    await meta_api.send_button_message(
        to_phone=phone,
        header_text="DRIVER DISPATCH",
        body_text=(
            "🚚 *STAGE 5: DRIVER TRIP COMMENCEMENT*\n"
            "────────────────────\n"
            "Trip: `TRIP-2026-00456`\n"
            "Truck: ZW 123 ABC | Route: Gweru\n"
            "Allowance Received: $46.50\n"
            "Departure Time: 06:30 AM\n"
            "────────────────────\n"
            "Tap below when starting the engine:"
        ),
        buttons=[
            {"id": "demo_drv_start", "title": "Trip Started"}
        ]
    )
    await asyncio.sleep(1.5)

    # 10. Driver In-Transit Menu
    await meta_api.send_button_message(
        to_phone=phone,
        header_text="DRIVER IN-TRANSIT",
        body_text=(
            "🚚 *STAGE 5: DRIVER IN-TRANSIT MENU*\n"
            "────────────────────\n"
            "Trip: `TRIP-2026-00456`\n"
            "📍 Live location stream: ACTIVE (Sales Rep viewing)\n"
            "────────────────────\n"
            "Select an action during transit:"
        ),
        buttons=[
            {"id": "demo_drv_deliv", "title": "Delivery Charges"},
            {"id": "demo_drv_emerg", "title": "Emergency Charges"},
            {"id": "demo_drv_ret", "title": "I am Returning"}
        ]
    )
    await asyncio.sleep(1.5)

    # 11. Customer Payment Method
    await meta_api.send_button_message(
        to_phone=phone,
        header_text="DELIVERY PAYMENT",
        body_text=(
            "💵 *STAGE 5: CUSTOMER DELIVERY PAYMENT*\n"
            "────────────────────\n"
            "Matched Customer: `CUST-101`\n"
            "Scheduled Transport Fee: $45.00\n"
            "────────────────────\n"
            "Please select how the customer paid:"
        ),
        buttons=[
            {"id": "demo_pay_cash", "title": "Cash"},
            {"id": "demo_pay_bank", "title": "Bank/EcoCash"},
            {"id": "demo_pay_unpaid", "title": "Unpaid"}
        ]
    )
    await asyncio.sleep(1.5)

    # 12. Driver Return to Base Menu
    await meta_api.send_button_message(
        to_phone=phone,
        header_text="RETURN TO BASE",
        body_text=(
            "🚚 *STAGE 5: DRIVER RETURN PHASE*\n"
            "────────────────────\n"
            "📍 Live location stream: DEACTIVATED\n"
            "Driver returning to Harare Depot.\n"
            "────────────────────\n"
            "Tap below when arrived at base:"
        ),
        buttons=[
            {"id": "demo_drv_emerg2", "title": "Emergency Charges"},
            {"id": "demo_drv_returned", "title": "I Have Returned"}
        ]
    )
    await asyncio.sleep(1.5)

    # 13. Sales Admin Balancing
    await meta_api.send_button_message(
        to_phone=phone,
        header_text="SALES ADMIN BALANCING",
        body_text=(
            "⚖️ *STAGE 6: SALES ADMIN BALANCING SESSION*\n"
            "────────────────────\n"
            "Company: A. TG Hardware\n"
            "Trip: `TRIP-2026-00456`\n"
            "Driver: John Banda | Truck: ZW 123 ABC\n"
            "────────────────────\n"
            "Expected Delivery Fees: $152.00\n"
            "Collected Fees (Audited): $152.00\n"
            "Allowances Given: $46.50\n"
            "Emergency Fuel: $35.00 (verify pump video)\n"
            "────────────────────\n"
            "Please conduct physical audit and select outcome:"
        ),
        buttons=[
            {"id": "demo_adm_bal", "title": "Balanced"},
            {"id": "demo_adm_notbal", "title": "Not Balancing"}
        ]
    )
    await asyncio.sleep(1.5)

    # 14. Logistics Manager Adjudication
    await meta_api.send_button_message(
        to_phone=phone,
        header_text="MANAGER ADJUDICATION",
        body_text=(
            "⚖️ *STAGE 7: DISCREPANCY ADJUDICATION*\n"
            "────────────────────\n"
            "Trip: `TRIP-2026-00456`\n"
            "Driver: John Banda\n"
            "Discrepancy: $12.50 variance\n"
            "Audit Note: Pump video showed $47.50, driver reported $35.00\n"
            "────────────────────\n"
            "Please select manager adjudication outcome:"
        ),
        buttons=[
            {"id": "demo_mgr_appr", "title": "Approve"},
            {"id": "demo_mgr_rej", "title": "Reject"}
        ]
    )
    await asyncio.sleep(1.5)

    # Final summary text
    await meta_api.send_text_message(
        phone,
        "🏁 *SHOWCASE COMPLETE!*\n"
        "════════════════════════════\n"
        "All 14 interactive button cards above reflect the exact production messages delivered across WhatsApp.\n\n"
        "• Strict standard: Zero emojis on buttons, all <= 20 chars.\n"
        "• Strict confidentiality: Sales Total completely hidden from operational staff.\n\n"
        "💡 To test the live functional bot right now in this chat, reply: `role sales`"
    )

    print("Showcase completed successfully!")

if __name__ == "__main__":
    asyncio.run(send_showcase())
