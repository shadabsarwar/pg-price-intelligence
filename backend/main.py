import asyncio
import os
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI, HTTPException, Response, status, Depends
from fastapi.middleware.cors import CORSMiddleware

from config import load_environment

load_environment()

from collectors.scraperapi import ProviderStatus, ScraperAPIProvider

from models.product import PlatformListing, PriceSummary, Product, ProductComparison, ProductCreate
from services.comparison import compare_product
from services.market_analysis import analyze_market
from services.market_refresh import MarketRefresher
from collectors.carrefour_qatar import CarrefourQatarCollector
from collectors.lulu_qatar import LuluQatarCollector
from collectors.other_platforms import OtherPlatformsCollector
from models.company import Company
from models.brand import Brand
from models.intelligence import CompetitorComparison, CompetitorMatch, MarketPosition
from collectors.base import CollectorSearchRequest, CollectorSearchResponse, ConnectorStatus
from services.lulu_collection import LuluCollectionService
from collectors.retailers import retailer_registry
from collectors.retailers.base_retailer import RetailerSearchResult
from services.provider_test import ProviderTestRequest, ProviderTestResult, ProviderTestService
from services.live_comparison import build_live_comparison
from services.database import Database
from services.repository import Repository, CatalogueView
from services.imports import Importer
from services.matches import MatchService
from services.collection_jobs import CollectionJobs
from pipeline_api import make_router, require_admin


@asynccontextmanager
async def lifespan(app: FastAPI):
    worker = asyncio.create_task(collection_jobs.run())
    try:
        yield
    finally:
        worker.cancel()
        with suppress(asyncio.CancelledError):
            await worker


app = FastAPI(title="P&G Price Intelligence API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["Content-Type", "X-Admin-Token"],
)


database = Database()
demo_enabled = os.environ.get('INTELLIGENCE_DEMO') == '1'
if demo_enabled:
    from services.demo_migration import migrate_demo
    migrate_demo(database)
repository = Repository(database, include_demo=demo_enabled)
products = CatalogueView(repository, 'pg')
competitors = CatalogueView(repository, 'competitor')
companies, brands = repository.companies(), repository.brands()
importer = Importer(database)
match_service = MatchService(repository)
lulu_collector = LuluQatarCollector()
scraperapi_provider = ScraperAPIProvider()
public_test_service = ProviderTestService()
retailers = retailer_registry()
retailers['lulu_qatar'].collector = lulu_collector
collection_jobs = CollectionJobs(repository, retailers, match_service)
lulu_service = LuluCollectionService(lulu_collector)
market_refresher = MarketRefresher([CarrefourQatarCollector(), lulu_collector, OtherPlatformsCollector()])
app.include_router(make_router(repository, importer, collection_jobs, match_service))


@app.get("/")
def home():
    return {"message": "P&G Price Intelligence API is running"}


@app.get("/products", response_model=list[Product], tags=["Products"])
async def get_products(limit: int = 10000, offset: int = 0, category: str | None = None, q: str | None = None):
    if not 1 <= limit <= 10000 or offset < 0:
        raise HTTPException(422, 'Invalid pagination')
    return repository.products('pg', limit=limit, offset=offset, category=category, query=q)


@app.post("/products", response_model=Product, status_code=status.HTTP_201_CREATED, tags=["Products"], dependencies=[Depends(require_admin)])
async def create_product(product: ProductCreate):
    # Legacy package price has no retailer identity and is deliberately not an offer.
    from services.imports import prepare, save_row
    raw = product.model_dump(exclude={'price'})
    raw.update(size=product.size_value or product.size, pack_count=product.pack_quantity,
               variant_name=product.variant)
    try:
        row = prepare(raw, 'pg' if product.company == 'P&G' else 'competitor', 'MANUAL')
        with database.connect() as db:
            id, _ = save_row(db, row, 'manual-create')
        return repository.get(id)
    except ValueError as error:
        raise HTTPException(422, str(error)) from None


@app.get("/products/{product_id}", response_model=Product, tags=["Products"])
async def get_product(product_id: int):
    try:
        return repository.get(product_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Product not found")


@app.delete("/products/{product_id}", status_code=status.HTTP_204_NO_CONTENT, tags=["Products"], dependencies=[Depends(require_admin)])
async def delete_product(product_id: int):
    await get_product(product_id)
    repository.archive(product_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@app.get("/products/{product_id}/listings", response_model=list[PlatformListing], tags=["Comparison"])
async def get_listings(product_id: int):
    product = await get_product(product_id)
    return product.listings


@app.get("/products/{product_id}/comparison", response_model=ProductComparison, tags=["Comparison"])
async def get_comparison(product_id: int):
    product = await get_product(product_id)
    return compare_product(product)


@app.get("/products/{product_id}/best-price", response_model=PriceSummary, tags=["Comparison"])
async def get_best_price(product_id: int):
    product = await get_product(product_id)
    return compare_product(product)


@app.get("/competitors", response_model=list[Product], tags=["Competitor intelligence"])
async def get_competitor_catalogue():
    return list(competitors.values())


@app.get("/companies", response_model=list[Company], tags=["Competitor intelligence"])
async def get_companies():
    return list(repository.companies().values())


@app.get("/brands", response_model=list[Brand], tags=["Competitor intelligence"])
async def get_brands():
    return list(repository.brands().values())


@app.get("/collectors", tags=["Competitor intelligence"])
async def get_collectors():
    lulu = await asyncio.to_thread(lulu_collector.status)
    return [state if platform != lulu_collector.platform else {
        "platform": platform, "status": lulu.status, "message": lulu.message,
        "last_successful_update": lulu.last_successful_collection,
    } for platform, state in market_refresher.statuses.items()]


@app.post("/collectors/lulu/search", response_model=CollectorSearchResponse, tags=["Retailer collection"],
          responses={503: {"model": CollectorSearchResponse}, 429: {"model": CollectorSearchResponse}})
async def search_lulu(request: CollectorSearchRequest, response: Response):
    result = await lulu_service.search(request.query, [*products.values(), *competitors.values()])
    await asyncio.to_thread(collection_jobs.record_search, 'lulu_qatar', request.query,
                            retailers['lulu_qatar'].from_result(result))
    if result.data_status == "ERROR":
        deferred = any(error.code in {"RATE_LIMITED", "COLLECTION_BUSY"} for error in result.errors)
        response.status_code = 429 if deferred else 503
        if deferred:
            response.headers["Retry-After"] = "60"
    return result


@app.get("/collectors/status", response_model=list[ConnectorStatus], tags=["Retailer collection"])
def get_collector_status():
    states = [lulu_collector.status()]
    for platform, state in market_refresher.statuses.items():
        if platform != lulu_collector.platform:
            states.append(ConnectorStatus(connector_name=platform.casefold().replace(" ", "_"),
                                          source_platform=platform,
                                          status="UNAVAILABLE" if state["status"] == "NOT_CONFIGURED" else state["status"],
                                          data_access_status="APPROVED_SOURCE_REQUIRED" if state["status"] == "NOT_CONFIGURED" else "CONFIGURED",
                                          reason="No approved API, product feed, or permitted data source has been configured." if state["status"] == "NOT_CONFIGURED" else state["message"],
                                          last_successful_collection=state["last_successful_update"]))
    return states


@app.get("/collectors/providers/status", response_model=ProviderStatus, tags=["Retailer collection"])
def get_provider_status():
    return scraperapi_provider.status()


@app.post("/collectors/test", response_model=ProviderTestResult, tags=["Live collection"],
          responses={403: {"model": ProviderTestResult}, 429: {"model": ProviderTestResult},
                     502: {"model": ProviderTestResult}, 503: {"model": ProviderTestResult},
                     504: {"model": ProviderTestResult}})
def test_provider(request: ProviderTestRequest, response: Response):
    result, response.status_code = public_test_service.test(request.url)
    if response.status_code == 429:
        response.headers["Retry-After"] = "60"
    return result


@app.post("/collectors/{retailer}/search", response_model=RetailerSearchResult, tags=["Live collection"])
def search_retailer(retailer: str, request: CollectorSearchRequest):
    connector = retailers.get(retailer)
    if connector is None:
        raise HTTPException(404, "Unknown retailer. Use lulu_qatar, carrefour_qatar, or noon_qatar.")
    result = connector.search(request.query)
    collection_jobs.record_search(retailer, request.query, result)
    return result


@app.get("/products/{product_id}/live-comparison", tags=["Live collection"])
async def get_live_comparison(product_id: int):
    product = await get_product(product_id)
    # Reading the dashboard never triggers a retailer request or refreshes an observation timestamp.
    sources = []
    for connector in retailers.values():
        rows = database.rows('''SELECT run.* FROM data_collection_runs run JOIN retailers r ON r.id=run.retailer_id
          WHERE r.name=? ORDER BY run.rowid DESC LIMIT 1''', (connector.platform,))
        from datetime import datetime, timezone
        source_status = 'UNAVAILABLE'
        if rows and rows[0]['records_saved'] and rows[0]['status'] in {'COMPLETED', 'PARTIAL'}:
            source_status = 'LIVE' if (datetime.now(timezone.utc) - datetime.fromisoformat(rows[0]['completed_at'])).total_seconds() <= 900 else 'STALE'
        sources.append({'platform': connector.platform, 'data_status': source_status,
                        'reason': f"Latest collection: {rows[0]['status']}. See Administration for details." if rows else 'No collection has run. Queue an approved source in Administration.'})
    return build_live_comparison(product, list(competitors.values()), sources)


@app.get("/products/{product_id}/competitor-comparison", response_model=CompetitorComparison, tags=["Competitor intelligence"])
async def get_competitor_comparison(product_id: int):
    product = await get_product(product_id)
    candidates = repository.products('competitor', category=product.category)
    rejected = {r['competitor_product_variant_id'] for r in database.rows("SELECT competitor_product_variant_id FROM competitor_relationships WHERE source_product_variant_id=? AND review_status='rejected'", (product_id,))}
    candidates = [p for p in candidates if p.id not in rejected and (p.source_state == 'DEMO') == (product.source_state == 'DEMO')]
    approved = {r['competitor_product_variant_id'] for r in database.rows("SELECT competitor_product_variant_id FROM competitor_relationships WHERE source_product_variant_id=? AND review_status='approved' AND active=1", (product_id,))}
    return analyze_market(product, candidates, repository.companies(), approved)


@app.get("/products/{product_id}/competitors", response_model=list[CompetitorMatch], tags=["Competitor intelligence"])
async def get_product_competitors(product_id: int):
    return (await get_competitor_comparison(product_id)).competitors


@app.get("/products/{product_id}/market-position", response_model=MarketPosition, tags=["Competitor intelligence"])
async def get_market_position(product_id: int):
    return (await get_competitor_comparison(product_id)).market_position
