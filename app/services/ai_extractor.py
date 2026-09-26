import re
import os
import json
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger("ai_extractor")

def rule_based_extract(text: str) -> Dict[str, Any]:
    """
    Fast, reliable deterministic regex and NLP entity extractor.
    Extracts customer, product, quantity, monthly demand, type, and urgency.
    Does NOT hallucinate or assume missing fields.
    """
    result = {
        "customer_name": None,
        "product_name": None,
        "requirement_type": None,
        "required_quantity": None,
        "monthly_demand": None,
        "customer_urgency": None,
        "competitor_supplier": None,
        "current_market_price": None,
        "comments": None
    }

    t_clean = text.strip()
    t_lower = t_clean.lower()

    # 1. Requirement Type Detection
    new_prod_triggers = [
        "don't make", "dont make", "do not make", "don't currently make", "dont currently make",
        "don't manufacture", "dont manufacture", "new product", "market opportunity",
        "if you start", "if we start", "start manufacturing", "start supplying"
    ]
    unavail_triggers = [
        "out of stock", "no stock", "unavailable", "currently don't have", "dont have stock",
        "no stock currently", "running low", "shortage", "finished"
    ]

    if any(k in t_lower for k in new_prod_triggers):
        result["requirement_type"] = "NEW_PRODUCT"
    elif any(k in t_lower for k in unavail_triggers):
        result["requirement_type"] = "EXISTING_UNAVAILABLE"

    # 2. Customer / Shop Name Extraction
    # Pattern e.g. "ABC Hardware wants...", "At Metro Electricals...", "Customer Buildland needs..."
    cust_match = re.search(
        r"(?:at\s+|customer\s+|shop\s+)?([A-Z][A-Za-z0-9\s&'-]+?(?:Hardware|Electricals|Wholesalers|Trading|Enterprises|Wholesale|Store|Shop|Supplies|Distributors|Plastics|Construction|Builders))\b",
        t_clean
    )
    if cust_match:
        result["customer_name"] = cust_match.group(1).strip()
    else:
        # Fallback: check text before "wants", "needs", "requested", "ordered"
        lead_match = re.search(r"^([A-Z][A-Za-z0-9\s&'-]{2,35})\s+(?:wants|needs|is looking for|asked for|requested)", t_clean)
        if lead_match:
            candidate = lead_match.group(1).strip()
            if candidate.lower() not in {"the", "a", "our", "my", "this", "they", "we"}:
                result["customer_name"] = candidate

    # 3. Monthly Demand Extraction
    # Handles:
    # "500 pieces every month", "500 pcs/month", "around 1000 a month", "500 per month"
    # "500 pieces of 25mm conduit every month", "every month 500", "monthly demand: 500"
    monthly_match = re.search(
        r"(?:around|approx|about)?\s*(\d+[\d,]*)\s*(?:pieces|pcs|pc|units|pipes|lengths)?(?:\s+(?:of|for)\s+[^.,]+?)?\s*(?:every\s+month|per\s+month|a\s+month|\/month|monthly)",
        t_lower
    )
    if not monthly_match:
        monthly_match = re.search(
            r"(?:monthly|per\s+month|every\s+month)\s*(?:demand|requirement|consumption|order|need)?\s*(?:of|around|approx|is|:)?\s*(\d+[\d,]*)",
            t_lower
        )
    if monthly_match:
        qty_str = monthly_match.group(1).replace(",", "")
        try:
            result["monthly_demand"] = int(qty_str)
        except ValueError:
            pass

    # 4. Current / Immediate Quantity Extraction
    # e.g. "needs 200 pieces currently", "immediate requirement of 300 pcs", "take 500 pcs"
    # Make sure we don't accidentally take the number that was already assigned to monthly_demand
    curr_match = re.search(
        r"(?:need|needs|wants|want|order of|require|requires|take|take around|current(?:ly)?\s+need|immediate)?\s*(\d+[\d,]*)\s*(?:pieces|pcs|pc|units|pipes|lengths)\b(?!\s*(?:of\s+[^.,]+?\s+)?(?:every|per|a\s+month|\/month|monthly))",
        t_lower
    )
    if curr_match:
        qty_str = curr_match.group(1).replace(",", "")
        try:
            val = int(qty_str)
            if result["monthly_demand"] != val:
                result["required_quantity"] = val
            elif not result["required_quantity"]:
                # If it's the only quantity mentioned, it can be both or initial
                pass
        except ValueError:
            pass

    # 5. Product Name Extraction
    # Look for conduit / fittings mentions (e.g. "25mm conduit", "20mm elbow", "32mm conduit pipe")
    prod_match = re.search(
        r"(\b(?:\d+\s*mm|\d+\s*inch)\s+[a-z0-9\s\(\)/-]{0,30}?\b(?:conduit|pipe|pipes|elbow|elbows|bend|bends|coupling|couplings|tee|tees|junction box|junction boxes|saddle|saddles|fitting|fittings|adaptor|adaptors|socket|sockets)\b(?:\s+(?:light\s+duty|heavy\s+duty|medium\s+duty|pvc))?)",
        t_lower
    )
    if prod_match:
        raw_p = prod_match.group(1).strip()
        # Clean up filler words like "of your", "of", "the"
        raw_p = re.sub(r"^(?:of\s+your|of\s+our|of|the|this)\s+", "", raw_p)
        result["product_name"] = raw_p.title()
    else:
        # Broader search for "25mm conduit", "20mm elbow"
        broader_match = re.search(r"(\b\d+\s*mm\s+[a-z]+(?:\s+[a-z]+)?)", t_lower)
        if broader_match:
            cand = broader_match.group(1).title()
            cand = re.sub(r"\s+(?:Every|Each|Per|Month|Now|Pcs|Pcs/Month)$", "", cand, flags=re.IGNORECASE)
            result["product_name"] = cand

    # 6. Customer Urgency / Willingness
    if any(k in t_lower for k in ["ready to buy", "ready to purchase", "will buy", "would buy", "willing to buy", "cash ready"]):
        result["customer_urgency"] = "Ready to purchase"
    elif any(k in t_lower for k in ["urgent", "urgently", "asap", "emergency", "immediately"]):
        result["customer_urgency"] = "Immediate need"
    elif any(k in t_lower for k in ["exploring", "inquiring", "just asking", "checking prices"]):
        result["customer_urgency"] = "Exploring options"

    # 7. Competitor Supplier Extraction
    comp_match = re.search(
        r"(?:buying from|buys from|competitor(?:\s+is)?|currently buying from|supplied by|supplier is)\s+([A-Z][A-Za-z0-9\s&'-]+?(?:Ltd|Limited|Plastics|Pipes|Industries|Co|Corp|Hardware)?)\b",
        t_clean
    )
    if comp_match:
        result["competitor_supplier"] = comp_match.group(1).strip()

    # 8. Market Price Extraction
    price_match = re.search(
        r"(?:\$|usd|rs\.?|inr|price(?:\s+is)?\s*:?\s*|paying\s+|at\s+)?(\d+(?:\.\d{1,2}))\s*(?:\/|\s*(?:per\s+piece|per\s+pc|per\s+meter|each|\$))?",
        t_lower
    )
    if price_match:
        try:
            p_val = float(price_match.group(1))
            if 0.1 <= p_val <= 500.0 and "." in price_match.group(1):
                result["current_market_price"] = p_val
        except ValueError:
            pass

    return result

async def extract_requirement_entities(text: str) -> Dict[str, Any]:
    """
    Main entity extraction entrypoint.
    Runs fast deterministic regex/rule extraction first.
    If Gemini API key is configured and input is complex, can invoke Gemini to augment.
    """
    extracted = rule_based_extract(text)

    # Optional Gemini LLM enhancement if key present and text is complex
    api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if api_key and len(text.split()) > 10 and (not extracted["customer_name"] or not extracted["product_name"]):
        try:
            import httpx
            prompt = (
                f"Extract structured product requirement from this salesperson text message:\n\n"
                f"\"{text}\"\n\n"
                f"Return valid JSON ONLY with these keys (use null if not explicitly mentioned, do not guess):\n"
                f"- customer_name: string or null\n"
                f"- product_name: string or null\n"
                f"- requirement_type: 'EXISTING_UNAVAILABLE' or 'NEW_PRODUCT' or null\n"
                f"- required_quantity: integer or null\n"
                f"- monthly_demand: integer or null\n"
                f"- customer_urgency: 'Ready to purchase' or 'Exploring options' or 'Immediate need' or null\n"
                f"- competitor_supplier: string or null\n"
                f"- current_market_price: float or null\n"
            )
            url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={api_key}"
            payload = {
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {"response_mime_type": "application/json"}
            }
            async with httpx.AsyncClient(timeout=8.0) as client:
                res = await client.post(url, json=payload)
                if res.status_code == 200:
                    resp_data = res.json()
                    candidates = resp_data.get("candidates", [])
                    if candidates:
                        raw_json = candidates[0].get("content", {}).get("parts", [{}])[0].get("text", "")
                        llm_parsed = json.loads(raw_json)
                        # Merge without overwriting validated fields with null
                        for k, v in llm_parsed.items():
                            if v is not None and not extracted.get(k):
                                extracted[k] = v
        except Exception as e:
            logger.debug(f"LLM fallback note: {e}")

    return extracted

def get_missing_fields(data: Dict[str, Any]) -> list:
    """
    Returns list of critical missing fields needed to complete the requirement.
    Required: customer_name, product_name, required_quantity (or monthly_demand).
    """
    missing = []
    if not data.get("requirement_type"):
        missing.append("requirement_type")
    if not data.get("customer_name"):
        missing.append("customer_name")
    if not data.get("product_name"):
        missing.append("product_name")
    if not data.get("required_quantity") and not data.get("monthly_demand"):
        missing.append("quantity")
    return missing


async def extract_odometer_from_image(image_bytes: bytes) -> Optional[float]:
    """
    Extracts vehicle odometer reading from a photo of the dashboard instrument cluster
    using Gemini multimodal vision.
    Returns float (e.g. 145280.0) or None if undetectable.
    Does not save images to disk or database.
    """
    if not image_bytes:
        return None

    import base64
    import httpx

    api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if not api_key:
        logger.warning("No GEMINI_API_KEY or GOOGLE_API_KEY found for odometer vision extraction.")
        return None

    try:
        b64_img = base64.b64encode(image_bytes).decode("utf-8")

        prompt = (
            "You are an expert vehicle fleet inspection AI. "
            "Analyze this photo of a vehicle's dashboard / instrument cluster and extract the total odometer mileage reading. "
            "Instructions:\n"
            "1. Locate the digital or mechanical odometer display (typically 5 to 7 digits, e.g. 145280 km or 89312).\n"
            "2. DO NOT confuse the odometer with Trip A / Trip B meters (which have decimals like 14.5 or small numbers), "
            "speedometer (0-200 km/h), tachometer (RPM x 1000), clock time (e.g. 14:30), temperature (e.g. 24°C), or fuel range.\n"
            "3. Return valid JSON ONLY with the exact key 'odometer' containing the numeric value (integer or float), "
            "or null if no odometer is visible or readable.\n"
            "Example: {\"odometer\": 145280.0}"
        )

        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={api_key}"
        payload = {
            "contents": [{
                "parts": [
                    {"text": prompt},
                    {
                        "inline_data": {
                            "mime_type": "image/jpeg",
                            "data": b64_img
                        }
                    }
                ]
            }],
            "generationConfig": {
                "response_mime_type": "application/json",
                "temperature": 0.1
            }
        }

        async with httpx.AsyncClient(timeout=15.0) as client:
            res = await client.post(url, json=payload)
            if res.status_code == 200:
                resp_data = res.json()
                candidates = resp_data.get("candidates", [])
                if candidates:
                    raw_text = candidates[0].get("content", {}).get("parts", [{}])[0].get("text", "")
                    parsed = json.loads(raw_text)
                    val = parsed.get("odometer")
                    if val is not None:
                        val_float = float(val)
                        if val_float > 0:
                            logger.info(f"Successfully extracted odometer from image: {val_float}")
                            return val_float
            else:
                logger.warning(f"Gemini Vision API error ({res.status_code}): {res.text}")
    except Exception as e:
        logger.error(f"Error during odometer extraction from image: {e}", exc_info=True)

    return None
