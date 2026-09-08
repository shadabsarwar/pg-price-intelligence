from models.product import Product
from services.product_matching import match_products, RULES


def find_competitors(master: Product, candidates: list[Product], approved: set[int] | None = None) -> list[tuple[Product, dict]]:
    from services.matches import candidate_score
    approved = approved or set()
    matches = []
    for candidate in candidates:
        match = candidate_score(master, candidate) if candidate.id in approved else match_products(master, candidate)
        threshold = RULES['minimum_score'] if candidate.id in approved else RULES['automatic_score']
        if match and match['confidence'] >= threshold:
            matches.append((candidate, match))
    return sorted([(candidate, match) for candidate, match in matches if match is not None],
                  key=lambda pair: (-pair[1]["confidence"], pair[0].id))
