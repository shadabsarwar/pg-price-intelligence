import json

from services.database import now
from services.product_matching import match_products, RULES
from services.normalization import clean


def candidate_score(master, candidate):
    strict = match_products(master, candidate)
    if strict:
        return strict
    if master.id == candidate.id or clean(master.company) == clean(candidate.company) or clean(master.brand) == clean(candidate.brand):
        return None
    if clean(master.category) != clean(candidate.category):
        return None
    # Contradictory evidence is not a reviewable match. Missing evidence is.
    for field in ('subcategory', 'purpose'):
        left, right = clean(getattr(master, field)), clean(getattr(candidate, field))
        if left and right and left != right:
            return None
    for key in ('form', 'concentration', 'diaper_size', 'razor_type', 'target_customer'):
        left, right = clean(master.attributes.get(key)), clean(candidate.attributes.get(key))
        if left and right and left != right:
            return None
    from services.price_normalization import quantity
    left, right = quantity(master), quantity(candidate)
    if left and right and (left[1] != right[1] or min(left[0], right[0]) / max(left[0], right[0]) < RULES['minimum_size_ratio']):
        return None
    breakdown = {key: weight for key, weight in RULES['weights'].items()
                 if key in ('category', 'subcategory', 'purpose') and clean(getattr(master, key))
                 and clean(getattr(master, key)) == clean(getattr(candidate, key))}
    score = min(sum(breakdown.values()), RULES['automatic_score'] - 1)
    if score < RULES['minimum_score']:
        return None
    return dict(confidence=score, breakdown=breakdown,
                explanation='Possible competitor: identity attributes or quantity are incomplete. Requires review; not eligible for automatic price comparison.')


class MatchService:
    def __init__(self, repository):
        self.repository = repository

    def recalculate(self, ids=None):
        sources = [self.repository.get(id) for id in ids] if ids else self.repository.products('pg')
        count = 0
        by_category = {}
        for source in sources:
            if source.category not in by_category:
                by_category[source.category] = self.repository.products('competitor', category=source.category)
            candidates = by_category[source.category]
            with self.repository.database.connect() as db:
                db.execute('UPDATE competitor_relationships SET active=0 WHERE source_product_variant_id=?', (source.id,))
                for candidate in candidates:
                    if (source.source_state == 'DEMO') != (candidate.source_state == 'DEMO'):
                        continue
                    match = candidate_score(source, candidate)
                    if not match:
                        continue
                    score = match['confidence']
                    label = 'high' if score >= RULES['high_score'] else 'likely' if score >= RULES['automatic_score'] else 'possible'
                    db.execute('''INSERT INTO competitor_relationships(source_product_variant_id,competitor_product_variant_id,
                     relationship_type,match_score,match_reason,created_at,updated_at) VALUES (?,?,?,?,?,?,?)
                     ON CONFLICT(source_product_variant_id,competitor_product_variant_id) DO UPDATE SET
                     relationship_type=excluded.relationship_type,match_score=excluded.match_score,
                     match_reason=excluded.match_reason,updated_at=excluded.updated_at,active=1''',
                     (source.id, candidate.id, label, score / 100, json.dumps(match), now(), now()))
                    count += 1
        return {'sources': len(sources), 'relationships': count}

    def relationships(self, source_id=None, review_only=False, limit=200, offset=0):
        clauses, args = ['r.active=1', 's.archived=0', 'c.archived=0'], []
        if not self.repository.include_demo:
            clauses.extend(["s.source_state<>'DEMO'", "c.source_state<>'DEMO'"])
        if source_id is not None:
            clauses.append('source_product_variant_id=?')
            args.append(source_id)
        if review_only:
            clauses.append("relationship_type='possible' AND review_status='pending'")
        return self.repository.database.rows('SELECT r.* FROM competitor_relationships r JOIN product_variants s ON s.id=r.source_product_variant_id JOIN product_variants c ON c.id=r.competitor_product_variant_id WHERE ' + ' AND '.join(clauses) + ' ORDER BY match_score DESC LIMIT ? OFFSET ?', (*args, limit, offset))

    def review(self, source, candidate, decision):
        with self.repository.database.connect() as db:
            result = db.execute('UPDATE competitor_relationships SET review_status=?,verified=?,updated_at=? WHERE source_product_variant_id=? AND competitor_product_variant_id=? AND active=1',
                                (decision, int(decision == 'approved'), now(), source, candidate))
            if not result.rowcount:
                raise KeyError('Match not found')
