from models.product import Product
from services.price_normalization import quantity
import json
from pathlib import Path
from services.normalization import clean

RULES = json.loads((Path(__file__).resolve().parents[1] / 'data' / 'matching_rules.json').read_text())
WEIGHTS = RULES['weights']

if sum(WEIGHTS.values()) != 100 or any(value < 0 for value in WEIGHTS.values()):
    raise ValueError('Matching weights must be nonnegative and sum to 100')


def match_products(master: Product, candidate: Product) -> dict | None:
    """Deterministic rule score, not a calibrated probability or an AI claim."""
    if master.id == candidate.id or clean(master.company) == clean(candidate.company) or clean(master.brand) == clean(candidate.brand):
        return None
    if master.company_id and master.company_id == candidate.company_id:
        return None
    for key in ('target_customer', 'product_type'):
        if master.attributes.get(key) and candidate.attributes.get(key) and clean(master.attributes[key]) != clean(candidate.attributes[key]):
            return None
    fields = {key: WEIGHTS[key] for key in ('category', 'subcategory', 'purpose')}
    if any(not clean(getattr(master, field)) or clean(getattr(master, field)) != clean(getattr(candidate, field)) for field in fields):
        return None
    left, right = quantity(master), quantity(candidate)
    if left is None or right is None or left[1] != right[1]:
        return None
    # Do not cross clinically/functionally different product groups, even with similar names.
    required = {"diaper": ["diaper_size", "form"], "razor": ["razor_type", "form"]}.get(left[1], ["form", "concentration"])
    if any(not master.attributes.get(key) or clean(master.attributes.get(key)) != clean(candidate.attributes.get(key)) for key in required):
        return None
    ratio = min(left[0], right[0]) / max(left[0], right[0])
    if ratio < RULES['minimum_size_ratio']:
        return None
    pack_ratio = min(master.pack_quantity, candidate.pack_quantity) / max(master.pack_quantity, candidate.pack_quantity)
    keys = set(master.attributes) | set(candidate.attributes)
    attribute_ratio = sum(clean(master.attributes.get(key)) == clean(candidate.attributes.get(key)) for key in keys) / len(keys) if keys else 0
    scores = dict(fields, size=round(WEIGHTS['size'] * ratio, 2), pack_quantity=round(WEIGHTS['pack_quantity'] * pack_ratio, 2),
                  attributes=round(WEIGHTS['attributes'] * attribute_ratio, 2),
                  variant=WEIGHTS['variant'] if clean(master.variant) and clean(master.variant) == clean(candidate.variant) else 0)
    return {"confidence": round(sum(scores.values()), 2), "breakdown": scores,
            "explanation": "Category, subcategory, purpose, unit dimension and essential attributes match; different company and brand. Score measures rule agreement, not probability."}
