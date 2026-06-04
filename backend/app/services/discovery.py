"""
Discovery service — orchestrates all scrapers in parallel for a model number.
Phase 1: Run all discovery scrapers concurrently → deduplicated retailer list
Phase 2: Post-discovery crawl — scrape each found URL for price/stock/screenshot
"""
import asyncio
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models.product import Product, ProductRetailer, PricePoint
from app.models.job import DiscoveryJob, JobStatus
from app.scrapers.base import ScrapedRetailer
from app.scrapers.heureka import HeurekaScraper
from app.scrapers.idealo import IdealoScraper
from app.scrapers.google_shopping import GoogleShoppingScraper, GoogleOrganicScraper
from app.scrapers.price_comparators import ZboziScraper, GeizhalsScraper, BingShoppingScraper, CeneoPLScraper
from app.scrapers.product_page import ProductPageScraper
from datetime import datetime, timezone
import structlog

log = structlog.get_logger()


async def run_discovery(
    model_number: str,
    job_id: int,
    db: AsyncSession,
    post_crawl: bool = True,
) -> list[ProductRetailer]:
    """
    Full discovery pipeline:
    1. Run all scrapers in parallel
    2. Deduplicate by (retailer_domain, country_code)
    3. Upsert into DB
    4. Post-crawl each URL for price/stock/screenshot (if post_crawl=True)
    5. Record price point in TimescaleDB hypertable
    """
    # Update job status
    job = await db.get(DiscoveryJob, job_id)
    if job:
        job.status = JobStatus.RUNNING
        job.started_at = datetime.now(timezone.utc)
        await db.commit()

    # Phase 1: Run all discovery scrapers concurrently
    log.info("discovery.start", model=model_number)
    raw_results: list[ScrapedRetailer] = []
    sources_completed: list[str] = []

    scrapers = [
        ("heureka",         HeurekaScraper()),
        ("idealo",          IdealoScraper()),
        ("google_shopping", GoogleShoppingScraper()),
        ("google_organic",  GoogleOrganicScraper()),
        ("zbozi",           ZboziScraper()),
        ("geizhals",        GeizhalsScraper()),
        ("bing_shopping",   BingShoppingScraper()),
        ("ceneo",           CeneoPLScraper()),
    ]

    async def run_scraper(name: str, scraper) -> tuple[str, list[ScrapedRetailer]]:
        try:
            results = await scraper.discover(model_number)
            log.info("discovery.scraper_done", name=name, count=len(results))
            return name, results
        except Exception as e:
            log.error("discovery.scraper_error", name=name, error=str(e))
            return name, []

    # Limit to 1 concurrent scraper to stay within 512MB RAM (Render free tier)
    semaphore = asyncio.Semaphore(1)
    async def bounded_scraper(name: str, scraper):
        async with semaphore:
            return await run_scraper(name, scraper)

    tasks = [bounded_scraper(name, scraper) for name, scraper in scrapers]
    scraper_results = await asyncio.gather(*tasks)

    for name, results in scraper_results:
        raw_results.extend(results)
        if results:
            sources_completed.append(name)

    log.info("discovery.phase1_done", model=model_number, total_raw=len(raw_results))

    # Deduplicate by (domain, country_code)
    seen: dict[tuple[str, str], ScrapedRetailer] = {}
    for r in raw_results:
        key = (r.retailer_domain.lower(), r.country_code)
        if key not in seen:
            seen[key] = r
        elif seen[key].price is None and r.price is not None:
            seen[key] = r  # prefer result with price

    deduplicated = list(seen.values())
    log.info("discovery.deduplication", unique_retailers=len(deduplicated))

    # Upsert Product
    product = await _upsert_product(db, model_number)

    # Upsert ProductRetailer records
    saved_retailers: list[ProductRetailer] = []
    for r in deduplicated:
        retailer = await _upsert_retailer(db, product.id, r)
        saved_retailers.append(retailer)

    await db.commit()

    # Phase 2: Post-crawl for missing prices/screenshots
    if post_crawl:
        log.info("discovery.post_crawl_start", count=len(saved_retailers))
        page_scraper = ProductPageScraper()
        crawl_tasks = []
        for retailer in saved_retailers:
            if retailer.current_price is None:
                crawl_tasks.append(_crawl_and_update(db, retailer, page_scraper))

        # Run crawls with concurrency limit (5 at a time to avoid rate limits)
        semaphore = asyncio.Semaphore(5)
        async def bounded_crawl(task):
            async with semaphore:
                return await task

        await asyncio.gather(*[bounded_crawl(t) for t in crawl_tasks])
        await db.commit()

    # Update job record
    if job:
        job.status = JobStatus.COMPLETED
        job.completed_at = datetime.now(timezone.utc)
        job.retailers_found = len(saved_retailers)
        job.sources_completed = sources_completed
        job.product_id = product.id
        await db.commit()

    log.info("discovery.complete", model=model_number, retailers=len(saved_retailers))
    return saved_retailers


async def _upsert_product(db: AsyncSession, model_number: str) -> Product:
    stmt = select(Product).where(Product.model_number == model_number)
    result = await db.execute(stmt)
    product = result.scalar_one_or_none()
    if not product:
        product = Product(model_number=model_number)
        db.add(product)
        await db.flush()
    return product


async def _upsert_retailer(db: AsyncSession, product_id: int, r: ScrapedRetailer) -> ProductRetailer:
    stmt = select(ProductRetailer).where(
        ProductRetailer.product_id == product_id,
        ProductRetailer.retailer_domain == r.retailer_domain,
        ProductRetailer.country_code == r.country_code,
    )
    result = await db.execute(stmt)
    retailer = result.scalar_one_or_none()

    now = datetime.now(timezone.utc)
    if not retailer:
        retailer = ProductRetailer(
            product_id=product_id,
            retailer_name=r.retailer_name,
            retailer_domain=r.retailer_domain,
            country_code=r.country_code,
            product_url=r.product_url,
            currency=r.currency,
            current_price=r.price,
            in_stock=r.in_stock,
            source=r.source,
            last_scraped_at=now,
        )
        db.add(retailer)
        await db.flush()
    else:
        # Update with latest data if better
        retailer.product_url = r.product_url
        if r.price is not None:
            retailer.current_price = r.price
        if r.in_stock is not None:
            retailer.in_stock = r.in_stock
        retailer.last_scraped_at = now

    # Record price point
    if r.price is not None:
        db.add(PricePoint(
            retailer_id=retailer.id,
            price=r.price,
            currency=r.currency,
            in_stock=r.in_stock,
            observed_at=now,
        ))

    return retailer


async def _crawl_and_update(db: AsyncSession, retailer: ProductRetailer, scraper: ProductPageScraper):
    try:
        result = await scraper.scrape_price(retailer.product_url, retailer.country_code)
        if result and result.price:
            now = datetime.now(timezone.utc)
            retailer.current_price = result.price
            retailer.in_stock = result.in_stock
            retailer.rating = result.rating
            retailer.review_count = result.review_count
            retailer.last_scraped_at = now
            db.add(PricePoint(
                retailer_id=retailer.id,
                price=result.price,
                currency=retailer.currency,
                in_stock=result.in_stock,
                observed_at=now,
            ))
    except Exception as e:
        log.warning("discovery.crawl_error", url=retailer.product_url, error=str(e))
