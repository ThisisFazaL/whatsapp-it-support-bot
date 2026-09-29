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
            url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={api_key}"
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


async def extract_odometer_with_claude(image_bytes: bytes, api_key: str) -> Optional[float]:
    """
    Extracts vehicle odometer reading using Anthropic Claude 3.5 Sonnet multimodal vision.
    Industry benchmark for reading noisy, low-contrast 7-segment LCDs and mechanical counters.
    """
    import base64
    import httpx

    b64_img = base64.b64encode(image_bytes).decode("utf-8")
    headers = {
        "x-api-key": api_key.strip(),
        "anthropic-version": "2023-06-01",
        "content-type": "application/json"
    }

    prompt = (
        "You are an expert vehicle fleet inspection AI. "
        "Analyze this photo of a vehicle's dashboard / instrument cluster and extract the total vehicle mileage odometer reading.\n\n"
        "Instructions:\n"
        "1. Locate the digital LCD screen or mechanical rolling drum display showing the vehicle's total mileage (e.g. 057612, 145280, 89312, 58000).\n"
        "2. If a digital screen shows a 5 to 7 digit mileage counter, extract it as the odometer even if 'HOLD TO RESET' or similar text is printed near the screen.\n"
        "3. DO NOT confuse the odometer with trip distance (Trip A / Trip B, e.g. 14.5 or 120.3 km), speedometer dial numbers (0 to 160), tachometer/RPM, clock (e.g. 14:30), outside temperature, or battery voltage.\n"
        "4. Return valid JSON ONLY with the exact key 'odometer' containing the integer or float numeric value, "
        "or null if no odometer is visible or readable.\n"
        "Example output: {\"odometer\": 58000}"
    )

    models_to_try = [
        "claude-3-5-sonnet-20241022",
        "claude-3-5-haiku-20241022",
        "claude-3-haiku-20240307"
    ]

    async with httpx.AsyncClient(timeout=25.0) as client:
        for model in models_to_try:
            payload = {
                "model": model,
                "max_tokens": 150,
                "temperature": 0.0,
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image",
                                "source": {
                                    "type": "base64",
                                    "media_type": "image/jpeg",
                                    "data": b64_img
                                }
                            },
                            {
                                "type": "text",
                                "text": prompt
                            }
                        ]
                    }
                ]
            }
            try:
                res = await client.post("https://api.anthropic.com/v1/messages", headers=headers, json=payload)
                if res.status_code == 200:
                    resp_data = res.json()
                    content = resp_data.get("content", [])
                    raw_text = "".join(part.get("text", "") for part in content if part.get("type") == "text")
                    parsed = {}
                    try:
                        parsed = json.loads(raw_text)
                    except Exception:
                        json_match = re.search(r"\{.*?\}", raw_text, re.DOTALL)
                        if json_match:
                            try:
                                parsed = json.loads(json_match.group(0))
                            except Exception:
                                pass

                    val = parsed.get("odometer") or parsed.get("mileage") or parsed.get("reading") or parsed.get("km")
                    if val is None and parsed:
                        for v in parsed.values():
                            if v is not None:
                                val = v
                                break

                    if val is not None:
                        clean_str = re.sub(r"[^\d.]", "", str(val))
                        if clean_str:
                            try:
                                val_float = float(clean_str)
                                if val_float > 0:
                                    logger.info(f"Successfully extracted odometer using Anthropic {model}: {val_float:,.0f} KM")
                                    return val_float
                            except ValueError:
                                pass
                    logger.info(f"Anthropic {model} response could not be parsed: {raw_text[:200]}")
                else:
                    logger.warning(f"Anthropic {model} returned HTTP {res.status_code}: {res.text[:200]}")
            except Exception as e:
                logger.warning(f"Error calling Anthropic {model}: {e}")

    return None


async def extract_odometer_with_gemini(image_bytes: bytes, api_key: str) -> Optional[float]:
    """
    Extracts odometer digits using Google Gemini multimodal vision.
    Uses valid production model endpoints (gemini-1.5-pro, gemini-2.0-flash, gemini-1.5-flash).
    """
    import base64
    import httpx

    b64_img = base64.b64encode(image_bytes).decode("utf-8")
    prompt = (
        "You are an expert vehicle fleet inspection AI. "
        "Analyze this photo of a vehicle's dashboard / instrument cluster and extract the vehicle mileage odometer reading.\n\n"
        "Instructions:\n"
        "1. Locate the digital LCD screen or mechanical odometer display showing the mileage digits (e.g. 057612, 145280, 89312, 58000).\n"
        "2. If a digital display shows a 5 to 7 digit mileage counter, extract it as the odometer even if 'HOLD TO RESET' or similar text is printed next to or on the screen.\n"
        "3. DO NOT confuse the odometer with small decimal numbers (e.g. 14.5), speedometer dial numbers (0 to 160), tachometer/RPM, clock (e.g. 14:30), temperature, or battery voltage.\n"
        "4. Return valid JSON ONLY with the exact key 'odometer' containing the numeric value (integer or float), "
        "or null if no odometer is visible or readable.\n"
        "Example: {\"odometer\": 58000}"
    )

    models_to_try = [
        "gemini-3.8-flash",
        "gemini-3.1-pro-preview",
        "gemini-3.1-flash-lite",
        "gemini-3.1-flash-image",
        "gemini-3.7-flash",
        "gemini-3.6-flash",
        "gemini-3.5-flash-lite",
        "gemini-flash-latest"
    ]
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
            "temperature": 0.0
        }
    }

    async with httpx.AsyncClient(timeout=20.0) as client:
        for model_name in models_to_try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={api_key.strip()}"
            try:
                res = await client.post(url, json=payload)
                if res.status_code == 200:
                    resp_data = res.json()
                    candidates = resp_data.get("candidates", [])
                    if candidates:
                        raw_text = candidates[0].get("content", {}).get("parts", [{}])[0].get("text", "")
                        parsed = {}
                        try:
                            parsed = json.loads(raw_text)
                        except Exception:
                            json_match = re.search(r"\{.*?\}", raw_text, re.DOTALL)
                            if json_match:
                                try:
                                    parsed = json.loads(json_match.group(0))
                                except Exception:
                                    pass

                        val = parsed.get("odometer") or parsed.get("mileage") or parsed.get("reading") or parsed.get("km")
                        if val is None and parsed:
                            for v in parsed.values():
                                if v is not None:
                                    val = v
                                    break

                        # Fallback: regex search for 4-7 digit odometer in raw text
                        if val is None:
                            digit_candidates = re.findall(r"\b([0-9]{4,7})\b", raw_text)
                            for cand in digit_candidates:
                                try:
                                    c_int = int(cand)
                                    # Filter out impossible years or clock numbers
                                    if 1000 <= c_int <= 9999999 and c_int not in {2024, 2025, 2026, 2027}:
                                        val = c_int
                                        break
                                except ValueError:
                                    pass

                        if val is not None:
                            clean_str = re.sub(r"[^\d.]", "", str(val))
                            if clean_str:
                                try:
                                    val_float = float(clean_str)
                                    if val_float > 0:
                                        logger.info(f"Successfully extracted odometer using Gemini {model_name}: {val_float:,.0f} KM")
                                        return val_float
                                except ValueError:
                                    pass
                        logger.info(f"Gemini {model_name} response could not be parsed: {raw_text[:200]}")
                else:
                    logger.warning(f"Gemini {model_name} returned HTTP {res.status_code}: {res.text[:200]}")
            except Exception as e:
                logger.warning(f"Error calling Gemini {model_name}: {e}")

    return None


async def extract_odometer_from_image(image_bytes: bytes) -> Optional[float]:
    """
    Extracts vehicle odometer reading from a photo of the dashboard instrument cluster.
    Primary engine: Google Gemini 1.5 Flash / 2.0 Flash / 1.5 Pro (Free tier via Google AI Studio).
    Secondary fallback: Anthropic Claude 3.5 Sonnet (if ANTHROPIC_API_KEY is configured).
    Returns float (e.g. 145280.0) or None if undetectable.
    Does not save images to disk or database.
    """
    if not image_bytes:
        return None

    from app.config import settings

    # 1. Primary Free Engine: Google Gemini (0$ cost with Google AI Studio key)
    gemini_key = (
        getattr(settings, "gemini_api_key", None)
        or os.getenv("GEMINI_API_KEY")
        or os.getenv("GOOGLE_API_KEY")
    )
    if gemini_key:
        try:
            val = await extract_odometer_with_gemini(image_bytes, gemini_key)
            if val and val > 0:
                return val
        except Exception as e:
            logger.error(f"Error in Gemini odometer extraction: {e}", exc_info=True)

    # 2. Secondary Engine: Claude 3.5 Sonnet (if user configures an Anthropic key)
    claude_key = (
        getattr(settings, "anthropic_api_key", None)
        or os.getenv("ANTHROPIC_API_KEY")
        or os.getenv("CLAUDE_API_KEY")
    )
    if claude_key:
        try:
            val = await extract_odometer_with_claude(image_bytes, claude_key)
            if val and val > 0:
                return val
        except Exception as e:
            logger.error(f"Error in Claude odometer extraction: {e}", exc_info=True)

    if not gemini_key and not claude_key:
        logger.warning("Neither GEMINI_API_KEY nor ANTHROPIC_API_KEY is configured for odometer extraction.")

    return None

