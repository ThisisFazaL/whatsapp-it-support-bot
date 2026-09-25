import asyncio
import logging
from app.meta_api import meta_api

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("send_flow")

async def send_az_flow_to_fazal():
    fazal_phone = "919265368695"
    logger.info(f"Sending complete A-Z flow messages to Fazal ({fazal_phone})...")

    # Part 1: Architecture & Stage 1 - 2
    msg_part1 = (
        "🚛 *TAGONESWA SALES & FLEET BOT — COMPLETE A-Z FLOW*\n"
        "════════════════════════════\n"
        "Welcome Fazal! Here is the authoritative operational guide for the newly deployed Sales & Fleet subsystem.\n\n"
        "🏢 *COMPANY SELECTION (Stage 1):*\n"
        "• Interactive Buttons (< 20 chars, NO emojis):\n"
        "  1. `A. TG Hardware`\n"
        "  2. `B. LG Plast`\n"
        "  3. `C. Kreckle`\n"
        "• Tags the trip immediately so return balancing routes to that company's specific Sales Admin.\n\n"
        "📊 *CLEAN SHORTFALL DISPLAY:*\n"
        "• Sales Rep **NEVER** sees Route Minimum, Shortfall Amount, or 4% formula.\n"
        "• Display shows strictly:\n"
        "  - Trip ID: `TRIP-2026-00456`\n"
        "  - Destination: `Gweru`\n"
        "  - Sales Total: `$14,200.00`\n"
        "  - Transport Fee to Take: `*$152.00*`\n\n"
        "⚡ *SHORTFALL RESOLUTION:*\n"
        "• `[Full Charge]`: Customer paid full fee. Clears directly without asking redundant amount.\n"
        "• `[Partial Charge]`: Rep enters amount paid; deficit added to rep's pending ledger.\n"
        "• `[Add to Pending]`: Entire fee added to rep's pending ledger directly.\n\n"
        "📋 *FAVLOGIX CHARGES & MANIFEST (Stage 2):*\n"
        "• Rep selects `[YES]` or `[NO]` for Favlogix charges.\n"
        "• On YES, registers customer fee schedule:\n"
        "  `CUST-101: 45, CUST-102: 60` (or `SKIP`).\n"
        "• Enables autonomous matching during driver transit!"
    )

    # Part 2: Allocation, Zayn Approval & Driver Transit (Stage 3 - 5)
    msg_part2 = (
        "⚙️ *STAGE 3: EDWARD LOGISTICS ALLOCATION*\n"
        "────────────────────────────\n"
        "• Multi-trip FIFO queue with `[Trip Queue]` and `[Allocate Trip]`.\n"
        "• Truck plate (`ZW 123 ABC`) and Driver (`John Banda`) are **typed** directly (NO buttons).\n"
        "• Prompts for crew members & meals contain **NO brackets**.\n"
        "• Review card features `[Confirm]` and `[Change]`.\n"
        "• 🔒 *Edward CANNOT see Sales Total!*\n\n"
        "💰 *STAGE 4: ZAYN ALLOWANCES & ACCOUNTS*\n"
        "────────────────────────────\n"
        "• Zayn receives automated allowance approval card: Tolls + Food (`$46.50`).\n"
        "• Zayn taps `[Approve]` or `[Recalculate]`.\n"
        "• On approval, Accounts alerted -> taps `[Transfer Done]`.\n"
        "• Driver is prompted for departure time.\n\n"
        "🚚 *STAGE 5: DRIVER IN-TRANSIT WORKFLOW*\n"
        "────────────────────────────\n"
        "• Driver taps `[Trip Started]` -> Live location alert sent to Sales Rep.\n"
        "• In-transit Menu has 3 buttons:\n"
        "  1. `[Delivery Charges]`\n"
        "  2. `[Emergency Charges]`\n"
        "  3. `[I am Returning]`\n"
        "• Delivery fee entry autonomously matches Stage 2 manifest:\n"
        "  Driver enters Customer ID -> selects payment: `[Cash]`, `[Bank/EcoCash]`, `[Unpaid]`.\n"
        "• Emergency options: `[Emergency Fuel]` (video pump audit instruction) & `[Other]` (issue description + cost).\n"
        "• Driver taps `[I am Returning]` -> Live location deactivated -> Switches to `[Emergency Charges]` and `[I Have Returned]`."
    )

    # Part 3: Balancing, Closure, Confidentiality & Live Testing
    msg_part3 = (
        "⚖️ *STAGE 6 & 7: BALANCING, AUDIT & CLOSURE*\n"
        "────────────────────────────\n"
        "• Driver arrival summons assigned company Sales Admin (`TG`, `LG`, or `Kreckle`).\n"
        "• Sales Admin receives reconciliation card (Expected vs Collected vs Expenses).\n"
        "• Sales Admin taps `[Balanced]` or `[Not Balancing]` (logs discrepancy amount & note).\n"
        "• Logistics Manager adjudicates: `[Approve]` (reimbursement payout) or `[Reject]` (charged to driver pending ledger).\n\n"
        "🔒 *CRITICAL CONFIDENTIALITY RULE:*\n"
        "• `Sales Total` is **STRICTLY HIDDEN** from Driver, Sales Rep, Sales Admin, and Edward in all operational messages and the final **TRIP CLOSED** broadcast!\n"
        "• Only Executive Management (Zayn & Accounts) receives the confidential sales total.\n\n"
        "🛡️ *SUBSYSTEM ISOLATION:*\n"
        "• IT Support ticketing, Projects Maintenance, and Truck Maintenance continue running 100% independently without collision.\n\n"
        "🧪 *HOW YOU CAN TEST LIVE RIGHT NOW:*\n"
        "1. Reply `role sales` to switch this chat to Sales testing mode.\n"
        "2. Tap `[Fleet Trip Approval]` and test the whole flow!\n"
        "3. Reply `role admin` at any time to return to Master Admin."
    )

    r1 = await meta_api.send_text_message(fazal_phone, msg_part1)
    logger.info(f"Part 1 sent: {r1}")
    await asyncio.sleep(1.0)

    r2 = await meta_api.send_text_message(fazal_phone, msg_part2)
    logger.info(f"Part 2 sent: {r2}")
    await asyncio.sleep(1.0)

    r3 = await meta_api.send_text_message(fazal_phone, msg_part3)
    logger.info(f"Part 3 sent: {r3}")

    print("All 3 messages sent successfully to Fazal's WhatsApp!")

if __name__ == "__main__":
    asyncio.run(send_az_flow_to_fazal())
