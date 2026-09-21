import re
from typing import List, Optional, Tuple
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import Product

def normalize_product_text(text: str) -> str:
    """Normalizes text for matching by standardizing sizes and removing special characters."""
    if not text:
        return ""
    t = text.lower().strip()
    # Normalize e.g. "20 mm" -> "20mm"
    t = re.sub(r"(\d+)\s*mm\b", r"\1mm", t)
    # Remove non-alphanumeric except spaces
    t = re.sub(r"[^\w\s]", " ", t)
    # Collapse multiple spaces
    t = re.sub(r"\s+", " ", t).strip()
    return t

async def find_matching_products(session: AsyncSession, query: str, limit: int = 3) -> List[Product]:
    """
    Finds matching products from the Product Master catalog based on keywords and specs.
    e.g. "20mm elbow" -> matches "20mm PVC Conduit Elbow"
         "25mm conduit" -> matches "25mm PVC Conduit Pipe (Heavy Duty)", etc.
    """
    norm_q = normalize_product_text(query)
    if not norm_q or len(norm_q) < 2:
        return []

    tokens = [tok for tok in norm_q.split() if len(tok) > 1]
    if not tokens:
        return []

    # Fetch all active products
    stmt = select(Product).where(Product.active == True)
    res = await session.execute(stmt)
    all_products = res.scalars().all()

    scored = []
    for prod in all_products:
        prod_norm = normalize_product_text(f"{prod.product_name} {prod.category} {prod.size_spec or ''}")
        score = 0

        # Exact substring match
        if norm_q in prod_norm:
            score += 10

        # Token matching
        matched_tokens = 0
        for token in tokens:
            if token in prod_norm:
                matched_tokens += 1
                score += 3
                # High priority if matching size spec (e.g. 20mm, 25mm, 32mm)
                if re.match(r"^\d+mm$", token) and prod.size_spec and token == prod.size_spec.lower():
                    score += 5

        # Only consider if at least one token matched
        if matched_tokens > 0:
            if matched_tokens == len(tokens):
                score += 8
            scored.append((score, prod))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [p for _, p in scored[:limit]]

async def get_product_by_id(session: AsyncSession, product_id: int) -> Optional[Product]:
    """Fetches product by primary key."""
    if not product_id:
        return None
    return await session.get(Product, int(product_id))
