import hmac
import json
import os
from typing import Literal

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel, Field

from services.database import now
from services.imports import read_rows
from services.price_normalization import normalize_price


def require_admin(x_admin_token: str | None = Header(default=None)):
    expected = os.environ.get('INTELLIGENCE_ADMIN_TOKEN', '')
    if not expected:
        raise HTTPException(503, 'Admin writes are disabled; configure INTELLIGENCE_ADMIN_TOKEN on the backend.')
    if not x_admin_token or not hmac.compare_digest(x_admin_token, expected):
        raise HTTPException(401, 'Admin token required')


class ImportRequest(BaseModel):
    format: Literal['csv', 'json'] = 'csv'
    content: str = Field(max_length=20_000_000)
    dry_run: bool = True
    source_state: Literal['IMPORTED', 'MANUAL', 'DEMO'] = 'IMPORTED'


class CollectionRequest(BaseModel):
    retailers: list[str] = Field(min_length=1, max_length=20)
    query: str = Field(min_length=2, max_length=200)
    category: str | None = Field(default=None, max_length=100)


class MatchRequest(BaseModel):
    product_ids: list[int] | None = Field(default=None, max_length=1000)


class ReviewRequest(BaseModel):
    decision: Literal['approved', 'rejected', 'pending']


def make_router(repository, importer, jobs, matches):
    router = APIRouter(tags=['Persistent intelligence'])
    database = repository.database
    writes = [Depends(require_admin)]

    def product(id):
        try:
            return repository.get(id)
        except KeyError:
            raise HTTPException(404, 'Product not found') from None

    @router.get('/products/{id}/prices')
    def prices(id: int, limit: int = Query(200, ge=1, le=1000), offset: int = Query(0, ge=0)):
        master = product(id)
        listings = repository.history(id, limit, offset)
        for listing in listings:
            listing['unit_price'], listing['unit'] = normalize_price(master, listing['latest_price'])
        return {'product_id': id, 'listings': listings, 'quality_flags': master.quality_flags}

    @router.get('/retailers')
    def retailers():
        rows = database.rows('SELECT * FROM retailers ORDER BY name')
        for row in rows:
            row['connector'] = next((key for key, value in jobs.connectors.items() if value.platform == row['name']), None)
        return rows

    @router.get('/retailers/{id}/products')
    def retailer_products(id: str, limit: int = Query(100, ge=1, le=1000), offset: int = Query(0, ge=0)):
        if not database.rows('SELECT 1 FROM retailers WHERE id=?', (id,)):
            raise HTTPException(404, 'Retailer not found')
        return database.rows('''SELECT rp.* FROM retailer_products rp JOIN product_variants v ON v.id=rp.product_variant_id
         WHERE rp.retailer_id=? AND v.archived=0 AND (? OR v.source_state<>'DEMO') ORDER BY rp.id LIMIT ? OFFSET ?''', (id, repository.include_demo, limit, offset))

    @router.get('/collection-status')
    def collection_status(limit: int = Query(100, ge=1, le=1000), offset: int = Query(0, ge=0)):
        return database.rows('SELECT * FROM data_collection_runs ORDER BY rowid DESC LIMIT ? OFFSET ?', (limit, offset))

    @router.get('/collection-status/{id}')
    def collection_detail(id: str):
        rows = database.rows('SELECT * FROM data_collection_runs WHERE id=?', (id,))
        if not rows:
            raise HTTPException(404, 'Collection run not found')
        return rows[0] | {'errors': database.rows('SELECT * FROM data_collection_errors WHERE collection_run_id=?', (id,))}

    @router.post('/collection/run', status_code=202, dependencies=writes)
    def collect(request: CollectionRequest):
        try:
            return {'run_ids': jobs.enqueue(request.retailers, request.query, {'category': request.category})}
        except ValueError as error:
            raise HTTPException(422, str(error)) from None

    @router.post('/collection/{id}/retry', status_code=202, dependencies=writes)
    def retry(id: str):
        rows = database.rows('SELECT * FROM data_collection_runs WHERE id=?', (id,))
        if not rows:
            raise HTTPException(404, 'Collection run not found')
        row = rows[0]
        if row['status'] not in {'ERROR', 'UNAVAILABLE', 'PARTIAL'}:
            raise HTTPException(409, 'Only failed or partial jobs can be retried')
        context = json.loads(row['context'])
        return {'run_ids': jobs.enqueue([context['connector']], row['query'], context)}

    def run_import(request, kind):
        try:
            result = importer.run(read_rows(request.content, request.format), kind, request.source_state, request.dry_run)
        except (ValueError, TypeError) as error:
            raise HTTPException(422, str(error)) from None
        if not request.dry_run:
            matches.recalculate()
        return result

    @router.post('/imports/products', dependencies=writes)
    def import_products(request: ImportRequest):
        return run_import(request, 'pg')

    @router.post('/imports/competitors', dependencies=writes)
    def import_competitors(request: ImportRequest):
        return run_import(request, 'competitor')

    @router.get('/imports', dependencies=writes)
    def imports(limit: int = Query(50, ge=1, le=1000)):
        return [dict(row, summary=json.loads(row['summary'])) for row in database.rows('SELECT * FROM import_runs ORDER BY created_at DESC LIMIT ?', (limit,))]

    @router.post('/matches/recalculate', dependencies=writes)
    def recalculate(request: MatchRequest):
        for id in request.product_ids or []:
            product(id)
        return matches.recalculate(request.product_ids)

    @router.get('/matches')
    def match_list(product_id: int | None = None, review_only: bool = False, limit: int = Query(200, ge=1, le=1000), offset: int = Query(0, ge=0)):
        return matches.relationships(product_id, review_only, limit, offset)

    @router.post('/matches/{source}/{candidate}/review', dependencies=writes)
    def review(source: int, candidate: int, request: ReviewRequest):
        try:
            matches.review(source, candidate, request.decision)
        except KeyError:
            raise HTTPException(404, 'Match not found') from None
        return {'status': request.decision}

    @router.post('/products/{id}/verify', dependencies=writes)
    def verify(id: int):
        item = product(id)
        if item.source_state == 'DEMO':
            raise HTTPException(422, 'Demo data cannot be verified; import real evidence separately')
        with database.connect() as db:
            db.execute('UPDATE product_variants SET verified=1,updated_at=? WHERE id=?', (now(), id))
        return product(id)

    @router.get('/quality')
    def quality(limit: int = Query(100, ge=1, le=1000), offset: int = Query(0, ge=0)):
        result = []
        for item in repository.products(limit=limit, offset=offset):
            flags = list(item.quality_flags)
            if item.company == 'P&G':
                relationships = [r for r in matches.relationships(item.id) if r['review_status'] != 'rejected']
                if not relationships:
                    flags.append('NO_COMPETITOR_FOUND')
                elif all(r['relationship_type'] == 'possible' for r in relationships):
                    flags.append('LOW_CONFIDENCE_MATCH')
            if flags:
                result.append({'id': item.id, 'product_name': item.product_name, 'source_state': item.source_state,
                               'verified': item.verified, 'flags': flags})
        return result

    @router.get('/discoveries', dependencies=writes)
    def discoveries(limit: int = Query(100, ge=1, le=1000), offset: int = Query(0, ge=0)):
        return database.rows("SELECT * FROM discoveries WHERE state<>'SAVED' ORDER BY id DESC LIMIT ? OFFSET ?", (limit, offset))

    return router
