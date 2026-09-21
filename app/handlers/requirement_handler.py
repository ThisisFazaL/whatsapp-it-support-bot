import re
import datetime
import logging
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import (
    Product, ProductRequirement, Employee, ConversationState
)
from app.state_manager import set_user_state, clear_user_state, get_user_state
from app.meta_api import meta_api
from app.services.product_service import find_matching_products, get_product_by_id
from app.services.ai_extractor import extract_requirement_entities, get_missing_fields

logger = logging.getLogger("requirement_handler")

SKIP_KEYWORDS = {"skip", "no", "none", "pass", "next", "btn_req_skip_photo", "na", "n/a", "-"}
GLOBAL_RESET_KEYWORDS = {"hi", "hello", "menu", "reset", "cancel", "start"}

def extract_numeric_choice(text: str) -> str:
    """Extracts first sequence of digits from text string."""
    match = re.search(r"\d+", text.strip()) if text else None
    return match.group(0) if match else text.strip().lower()

async def generate_requirement_number(session: AsyncSession) -> str:
    """Generates unique requirement reference code: REQ-YYYYMMDD-XXXXX."""
    today_str = datetime.datetime.utcnow().strftime("%Y%m%d")
    stmt = select(func.coalesce(func.max(ProductRequirement.requirement_id), 0))
    res = await session.execute(stmt)
    max_id = res.scalar() or 0
    next_num = max_id + 1

    while True:
        req_num = f"REQ-{today_str}-{str(next_num).zfill(5)}"
        chk = await session.execute(select(ProductRequirement).where(ProductRequirement.requirement_number == req_num))
        if not chk.scalars().first():
            return req_num
        next_num += 1

async def start_product_requirement_flow(session: AsyncSession, phone: str, employee: Employee = None, initial_text: str = None):
    """
    Entry point to start the Product Requirement reporting flow.
    Supports either:
    1. Direct guided interactive buttons (default)
    2. Fast natural-language entity extraction if salesperson sent a compound sentence.
    """
    data = {}

    # If salesperson provided a compound message initially, run entity extraction
    if initial_text and len(initial_text.split()) >= 4:
        extracted = await extract_requirement_entities(initial_text)
        data.update({k: v for k, v in extracted.items() if v is not None})

        # If compound text already gave us customer, product, and quantity
        missing = get_missing_fields(data)
        if not missing:
            # Everything needed was in the message! Jump straight to summary confirmation
            await show_requirement_summary(session, phone, employee, data)
            return
        elif len(missing) == 1 and missing[0] == "quantity":
            # Only quantity missing
            await set_user_state(session, phone, "awaiting_current_qty", data, flow_name="product_requirement")
            await meta_api.send_text_message(
                phone,
                f"📝 *Product Requirement for {data.get('customer_name', 'Customer')}*\n\n"
                f"Product: *{data.get('product_name')}*\n\n"
                f"What quantity does the customer require currently in pieces?\n(e.g., *500*, *200*)"
            )
            return

    # Standard conversational guided entry
    msg = (
        "📦 *Report Product Requirement*\n\n"
        "Please select the type of requirement you would like to report:\n\n"
        "1️⃣ *Existing Product — Currently Unavailable*\n"
        "_(Customer wants our existing product, but we are out of stock)_\n\n"
        "2️⃣ *New Product — Market Opportunity*\n"
        "_(Customer wants a product we do not currently manufacture)_"
    )
    buttons = [
        {"id": "btn_req_type_unavail", "title": "1️⃣ Unavailable Stock"},
        {"id": "btn_req_type_new", "title": "2️⃣ New Opportunity"}
    ]
    await set_user_state(session, phone, "select_req_type", data, flow_name="product_requirement")
    await meta_api.send_button_message(
        to_phone=phone,
        body_text=msg,
        buttons=buttons,
        header_text="📦 PRODUCT REQUIREMENT"
    )

async def handle_requirement_flow(
    session: AsyncSession,
    employee: Employee,
    message_text: str,
    state: ConversationState,
    image_id: str = None,
    sender_phone: str = None
):
    """
    Main state machine dispatcher for flow_name = "product_requirement".
    """
    phone = employee.phone if employee else sender_phone
    if not phone:
        return

    text_raw = (message_text or "").strip()
    text_clean = text_raw.lower()
    choice_num = extract_numeric_choice(text_raw)

    step = state.current_step if state else ""
    data = dict(state.current_data or {}) if state else {}

    # -------------------------------------------------------------
    # STEP 1: Select Requirement Type
    # -------------------------------------------------------------
    if step == "select_req_type":
        if "new" in text_clean or "btn_req_type_new" in text_clean or choice_num == "2":
            data["requirement_type"] = "NEW_PRODUCT"
            type_label = "New Product / Market Opportunity"
        else:
            data["requirement_type"] = "EXISTING_UNAVAILABLE"
            type_label = "Existing Product (Unavailable)"

        data["type_label"] = type_label
        await set_user_state(session, phone, "awaiting_customer_name", data, flow_name="product_requirement")
        await meta_api.send_text_message(
            phone,
            f"🏢 *Customer / Shop Name*\n\n"
            f"Requirement: *{type_label}*\n\n"
            f"Please type the name of the shop, hardware store, or customer:\n"
            f"_(e.g., *ABC Hardware*, *Buildland Wholesale*)_"
        )
        return

    # -------------------------------------------------------------
    # STEP 2: Customer / Shop Name
    # -------------------------------------------------------------
    elif step == "awaiting_customer_name":
        if len(text_raw) < 2:
            await meta_api.send_text_message(phone, "⚠️ Please enter a valid customer or shop name:")
            return

        data["customer_name"] = text_raw
        req_type = data.get("requirement_type", "EXISTING_UNAVAILABLE")

        await set_user_state(session, phone, "awaiting_product", data, flow_name="product_requirement")

        if req_type == "NEW_PRODUCT":
            msg = (
                f"💡 *New Product Description*\n\n"
                f"What product does *{text_raw}* need that we don't currently manufacture?\n"
                f"_(e.g., *32mm conduit bend*, *40mm adapter*, *heavy duty junction box*)_"
            )
        else:
            msg = (
                f"📦 *Select Existing Product*\n\n"
                f"Which product does *{text_raw}* need?\n"
                f"_(e.g., *25mm conduit*, *20mm elbow*, *25mm coupling*)_"
            )
        await meta_api.send_text_message(phone, msg)
        return

    # -------------------------------------------------------------
    # STEP 3: Product Name & Catalog Matching
    # -------------------------------------------------------------
    elif step == "awaiting_product":
        if len(text_raw) < 2:
            await meta_api.send_text_message(phone, "⚠️ Please specify the product name or size:")
            return

        data["raw_product_name"] = text_raw

        # Catalog lookup
        matches = await find_matching_products(session, text_raw, limit=1)
        if matches:
            matched_prod = matches[0]
            data["suggested_product_id"] = matched_prod.product_id
            data["suggested_product_name"] = matched_prod.product_name
            data["suggested_category"] = matched_prod.category

            msg = (
                f"🔍 *Product Master Match*\n\n"
                f"Did the customer mean:\n"
                f"👉 *{matched_prod.product_name}*?\n\n"
                f"1️⃣ Yes, use this product\n"
                f"2️⃣ No, keep as '{text_raw}'"
            )
            buttons = [
                {"id": "btn_req_cat_match_yes", "title": "1️⃣ Yes, Match"},
                {"id": "btn_req_cat_match_no", "title": f"2️⃣ No, Custom"}
            ]
            await set_user_state(session, phone, "confirm_catalog_match", data, flow_name="product_requirement")
            await meta_api.send_button_message(
                to_phone=phone,
                body_text=msg,
                buttons=buttons,
                header_text="🔍 PRODUCT VERIFICATION"
            )
            return

        # No match found -> accept user's product name directly
        data["product_id"] = None
        data["product_name"] = text_raw.title()
        await ask_required_quantity(session, phone, data)
        return

    # -------------------------------------------------------------
    # STEP 3.5: Confirm Catalog Match
    # -------------------------------------------------------------
    elif step == "confirm_catalog_match":
        if "yes" in text_clean or "btn_req_cat_match_yes" in text_clean or choice_num == "1":
            data["product_id"] = data.get("suggested_product_id")
            data["product_name"] = data.get("suggested_product_name")
            data["product_category"] = data.get("suggested_category")
        else:
            data["product_id"] = None
            data["product_name"] = data.get("raw_product_name", "Custom Product").title()

        await ask_required_quantity(session, phone, data)
        return

    # -------------------------------------------------------------
    # STEP 4: Current Required Quantity
    # -------------------------------------------------------------
    elif step == "awaiting_current_qty":
        qty_num = None
        if choice_num and choice_num.isdigit():
            qty_num = int(choice_num)
        elif text_clean in SKIP_KEYWORDS:
            qty_num = 0

        if qty_num is None:
            await meta_api.send_text_message(phone, "⚠️ Please reply with a quantity number (e.g. *500*, *200*, or *0*):")
            return

        data["required_quantity"] = qty_num

        await set_user_state(session, phone, "awaiting_monthly_demand", data, flow_name="product_requirement")
        await meta_api.send_text_message(
            phone,
            f"🔄 *Monthly Recurring Demand*\n\n"
            f"What is the customer's estimated recurring demand **per month**?\n"
            f"_(e.g., *500*, *1000*, or reply *'0'* if one-time need)_"
        )
        return

    # -------------------------------------------------------------
    # STEP 5: Monthly Demand
    # -------------------------------------------------------------
    elif step == "awaiting_monthly_demand":
        m_num = None
        if choice_num and choice_num.isdigit():
            m_num = int(choice_num)
        elif text_clean in SKIP_KEYWORDS:
            m_num = 0

        if m_num is None:
            await meta_api.send_text_message(phone, "⚠️ Please enter estimated monthly demand as a number (e.g. *500* or *0*):")
            return

        data["monthly_demand"] = m_num

        # Ask Urgency via interactive buttons
        msg = (
            f"⚡ *Customer Urgency & Interest*\n\n"
            f"How willing and ready is *{data.get('customer_name')}* to purchase?"
        )
        buttons = [
            {"id": "btn_req_urg_ready", "title": "🟢 Ready to Buy"},
            {"id": "btn_req_urg_exploring", "title": "🟡 Exploring"},
            {"id": "btn_req_urg_immediate", "title": "🔴 Urgent Need"}
        ]
        await set_user_state(session, phone, "select_urgency", data, flow_name="product_requirement")
        await meta_api.send_button_message(
            to_phone=phone,
            body_text=msg,
            buttons=buttons,
            header_text="⚡ CUSTOMER INTEREST"
        )
        return

    # -------------------------------------------------------------
    # STEP 6: Customer Urgency
    # -------------------------------------------------------------
    elif step == "select_urgency":
        urg = "Ready to purchase"
        if "explor" in text_clean or "btn_req_urg_exploring" in text_clean or choice_num == "2":
            urg = "Exploring options"
        elif "urgent" in text_clean or "btn_req_urg_immediate" in text_clean or choice_num == "3":
            urg = "Immediate need"
        elif "ready" in text_clean or "btn_req_urg_ready" in text_clean or choice_num == "1":
            urg = "Ready to purchase"

        data["customer_urgency"] = urg
        req_type = data.get("requirement_type", "EXISTING_UNAVAILABLE")

        if req_type == "NEW_PRODUCT":
            # For new product, ask about competitor / supplier
            await set_user_state(session, phone, "awaiting_competitor", data, flow_name="product_requirement")
            await meta_api.send_text_message(
                phone,
                "🏢 *Competitor / Existing Supplier (Optional)*\n\n"
                "Who currently supplies this item to the shop, if known?\n"
                "_(e.g., *Plastix Ltd*, *Proflo*, or type *'skip'*)_"
            )
            return
        else:
            # Skip competitor/price for existing unavailable product -> go to comments
            await ask_optional_comments(session, phone, data)
            return

    # -------------------------------------------------------------
    # STEP 7: Competitor / Existing Supplier (New Products Only)
    # -------------------------------------------------------------
    elif step == "awaiting_competitor":
        if text_clean not in SKIP_KEYWORDS and len(text_clean) > 1:
            data["competitor_supplier"] = text_raw
        else:
            data["competitor_supplier"] = None

        await set_user_state(session, phone, "awaiting_market_price", data, flow_name="product_requirement")
        await meta_api.send_text_message(
            phone,
            "💵 *Current Market Price (Optional)*\n\n"
            "What price per piece is the customer currently paying or expecting?\n"
            "_(e.g., *$1.80*, *2.50*, or type *'skip'*)_"
        )
        return

    # -------------------------------------------------------------
    # STEP 8: Current Market Price (New Products Only)
    # -------------------------------------------------------------
    elif step == "awaiting_market_price":
        if text_clean not in SKIP_KEYWORDS:
            price_match = re.search(r"(\d+(?:\.\d{1,2})?)", text_raw)
            if price_match:
                try:
                    data["current_market_price"] = float(price_match.group(1))
                except ValueError:
                    data["current_market_price"] = None
        else:
            data["current_market_price"] = None

        await ask_optional_comments(session, phone, data)
        return

    # -------------------------------------------------------------
    # STEP 9: Additional Comments
    # -------------------------------------------------------------
    elif step == "awaiting_comments":
        if text_clean not in SKIP_KEYWORDS and len(text_clean) > 1:
            data["comments"] = text_raw
        else:
            data["comments"] = None

        # Prompt for optional photo attachment
        msg = (
            "📸 *Product Photo (Optional)*\n\n"
            "You can attach a photo of the sample, existing stock, or specification right now, or tap 'Skip Photo':"
        )
        buttons = [
            {"id": "btn_req_skip_photo", "title": "⏩ Skip Photo"}
        ]
        await set_user_state(session, phone, "awaiting_photo", data, flow_name="product_requirement")
        await meta_api.send_button_message(
            to_phone=phone,
            body_text=msg,
            buttons=buttons,
            header_text="📸 PRODUCT PHOTO"
        )
        return

    # -------------------------------------------------------------
    # STEP 10: Product Photo Attachment / Skip
    # -------------------------------------------------------------
    elif step == "awaiting_photo":
        if image_id:
            data["image_id"] = image_id
        elif text_clean not in SKIP_KEYWORDS and len(text_clean) > 2:
            # If user sent additional notes text instead of photo
            data["comments"] = (data.get("comments") or "") + " | " + text_raw

        await show_requirement_summary(session, phone, employee, data)
        return

    # -------------------------------------------------------------
    # STEP 11: Final Confirmation / Edit
    # -------------------------------------------------------------
    elif step == "confirm_summary":
        if "submit" in text_clean or "yes" in text_clean or "btn_req_confirm_submit" in text_clean or choice_num == "1":
            await finalize_requirement_submission(session, phone, employee, data)
            return
        elif "edit" in text_clean or "btn_req_edit" in text_clean or choice_num == "2":
            # Restart flow with clean state
            await meta_api.send_text_message(phone, "🔄 Restarting requirement entry...")
            await start_product_requirement_flow(session, phone, employee)
            return
        else:
            await meta_api.send_text_message(
                phone,
                "⚠️ Please confirm by replying with *1* (Yes, Submit) or *2* (Edit):"
            )
            return

async def ask_required_quantity(session: AsyncSession, phone: str, data: dict):
    """Helper to transition to quantity input."""
    await set_user_state(session, phone, "awaiting_current_qty", data, flow_name="product_requirement")
    await meta_api.send_text_message(
        phone,
        f"🔢 *Current Quantity Required*\n\n"
        f"Product: *{data.get('product_name')}*\n\n"
        f"How many pieces does *{data.get('customer_name')}* currently need?\n"
        f"_(e.g., *500*, *200*, or *0* if no immediate order)_"
    )

async def ask_optional_comments(session: AsyncSession, phone: str, data: dict):
    """Helper to transition to comments prompt."""
    await set_user_state(session, phone, "awaiting_comments", data, flow_name="product_requirement")
    await meta_api.send_text_message(
        phone,
        "📝 *Additional Comments (Optional)*\n\n"
        "Any specific customer requirements, delivery date expectations, or notes?\n"
        "_(Type your comments or reply *'skip'*)_"
    )

async def show_requirement_summary(session: AsyncSession, phone: str, employee: Employee, data: dict):
    """Formats and displays structured summary card for salesperson verification."""
    sales_name = employee.full_name if employee else "Sales Representative"
    cust_name = data.get("customer_name", "N/A")
    prod_name = data.get("product_name", "N/A")
    req_type = data.get("requirement_type", "EXISTING_UNAVAILABLE")
    type_label = "Existing Product (Unavailable Stock)" if req_type == "EXISTING_UNAVAILABLE" else "New Product / Market Opportunity"

    curr_qty = data.get("required_quantity", 0)
    monthly = data.get("monthly_demand", 0)
    urgency = data.get("customer_urgency", "Ready to purchase")
    competitor = data.get("competitor_supplier")
    price = data.get("current_market_price")
    comments = data.get("comments")
    has_photo = "🖼️ Yes" if data.get("image_id") else "None"

    extra_lines = []
    if competitor:
        extra_lines.append(f"🏢 *Existing Supplier:* {competitor}")
    if price:
        extra_lines.append(f"💵 *Market Price:* ${price:.2f}")
    if comments:
        extra_lines.append(f"📝 *Notes:* {comments}")
    extra_lines.append(f"📸 *Photo:* {has_photo}")
    extra_str = "\n".join(extra_lines)

    summary_text = (
        f"📋 *PRODUCT REQUIREMENT SUMMARY*\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"👤 *Salesperson:* {sales_name}\n"
        f"🏢 *Customer/Shop:* {cust_name}\n"
        f"🏷️ *Type:* {type_label}\n"
        f"📦 *Product:* {prod_name}\n"
        f"🔢 *Current Requirement:* {curr_qty} pcs\n"
        f"🔄 *Monthly Demand:* {monthly} pcs/month\n"
        f"⚡ *Customer Interest:* {urgency}\n"
        f"{extra_str}\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"Is this information correct?"
    )

    buttons = [
        {"id": "btn_req_confirm_submit", "title": "1️⃣ Yes, Submit"},
        {"id": "btn_req_edit", "title": "2️⃣ Edit"}
    ]

    await set_user_state(session, phone, "confirm_summary", data, flow_name="product_requirement")
    await meta_api.send_button_message(
        to_phone=phone,
        body_text=summary_text,
        buttons=buttons,
        header_text="📋 VERIFY REQUIREMENT"
    )

async def finalize_requirement_submission(session: AsyncSession, phone: str, employee: Employee, data: dict):
    """Commits requirement to database, notifies salesperson with confirmation, and alerts management."""
    sales_id = employee.employee_id if employee else None
    if not sales_id and phone:
        e_chk = await session.execute(select(Employee).where(Employee.phone == phone))
        emp_obj = e_chk.scalars().first()
        if emp_obj:
            sales_id = emp_obj.employee_id
            employee = emp_obj

    req_number = await generate_requirement_number(session)

    new_req = ProductRequirement(
        requirement_number=req_number,
        salesperson_id=sales_id,
        customer_name=data.get("customer_name", "Shop Customer"),
        customer_phone=data.get("customer_phone"),
        requirement_type=data.get("requirement_type", "EXISTING_UNAVAILABLE"),
        product_id=data.get("product_id"),
        product_name=data.get("product_name", "Custom Product"),
        product_category=data.get("product_category"),
        required_quantity=data.get("required_quantity", 0),
        monthly_demand=data.get("monthly_demand", 0),
        customer_urgency=data.get("customer_urgency"),
        competitor_supplier=data.get("competitor_supplier"),
        current_market_price=data.get("current_market_price"),
        comments=data.get("comments"),
        image_id=data.get("image_id"),
        status="Pending Review"
    )
    session.add(new_req)
    await session.commit()

    # Clear state so user is ready for new interactions
    await clear_user_state(session, phone)

    type_str = "Unavailable Stock" if data.get("requirement_type") == "EXISTING_UNAVAILABLE" else "New Product Opportunity"
    receipt_msg = (
        f"✅ *PRODUCT REQUIREMENT SUBMITTED!*\n\n"
        f"🎫 *Reference ID:* `{req_number}`\n"
        f"🏢 *Customer:* {data.get('customer_name')}\n"
        f"📦 *Product:* {data.get('product_name')}\n"
        f"🏷️ *Type:* {type_str}\n"
        f"🔢 *Quantity:* {data.get('required_quantity', 0)} pcs (Monthly: {data.get('monthly_demand', 0)} pcs)\n\n"
        f"Management has been notified. Thank you for reporting this market demand!"
    )
    await meta_api.send_text_message(phone, receipt_msg)

    # Broadcast notification to Master Admin if configured
    from app.config import settings
    if settings.master_admin_phone:
        sales_name = employee.full_name if employee else "Sales Rep"
        admin_alert = (
            f"📢 *NEW MARKET DEMAND REPORT ({req_number})*\n\n"
            f"👤 *Salesperson:* {sales_name} (`+{phone}`)\n"
            f"🏢 *Customer:* {data.get('customer_name')}\n"
            f"📦 *Product:* {data.get('product_name')}\n"
            f"🏷️ *Type:* {type_str}\n"
            f"🔢 *Immediate Demand:* {data.get('required_quantity', 0)} pcs\n"
            f"🔄 *Monthly Demand:* {data.get('monthly_demand', 0)} pcs/month\n"
            f"⚡ *Urgency:* {data.get('customer_urgency', 'N/A')}\n"
            f"📊 *Status:* 🟡 Pending Review"
        )
        try:
            if data.get("image_id"):
                await meta_api.send_image_message(settings.master_admin_phone, data.get("image_id"), caption=admin_alert)
            else:
                await meta_api.send_text_message(settings.master_admin_phone, admin_alert)
        except Exception as alert_err:
            logger.error(f"Error alerting master admin: {alert_err}")
