"""Celery tasks for scheduled price monitoring."""
import asyncio
from sqlalchemy import select
from app.workers.celery_app import celery_app
from app.core.database import AsyncSessionLocal
from app.models.product import ProductRetailer, PricePoint
from app.models.monitor import Monitor, Alert, AlertType
from app.scrapers.product_page import ProductPageScraper
from datetime import datetime, timezone
import structlog

log = structlog.get_logger()


@celery_app.task(name="app.workers.scrape_tasks.scrape_all_active_monitors")
def scrape_all_active_monitors():
    """Periodic task: scrape all retailers that have active monitors."""
    asyncio.run(_scrape_all())


async def _scrape_all():
    async with AsyncSessionLocal() as db:
        # Get all unique retailer_ids being monitored
        stmt = (
            select(Monitor)
            .where(Monitor.is_active == True)  # noqa: E712
        )
        result = await db.execute(stmt)
        monitors = result.scalars().all()

        retailer_ids: set[int] = set()
        for m in monitors:
            if m.retailer_ids:
                retailer_ids.update(m.retailer_ids)
            else:
                # Monitor all retailers for this product
                stmt2 = select(ProductRetailer).where(
                    ProductRetailer.product_id == m.product_id,
                    ProductRetailer.is_active == True,  # noqa: E712
                )
                r2 = await db.execute(stmt2)
                for retailer in r2.scalars().all():
                    retailer_ids.add(retailer.id)

        log.info("scrape_all.start", retailer_count=len(retailer_ids))

        scraper = ProductPageScraper()
        semaphore = asyncio.Semaphore(5)

        async def scrape_one(rid: int):
            async with semaphore:
                await _scrape_retailer(db, rid, scraper)

        await asyncio.gather(*[scrape_one(rid) for rid in retailer_ids])
        await db.commit()


async def _scrape_retailer(db: AsyncSession, retailer_id: int, scraper: ProductPageScraper):
    retailer = await db.get(ProductRetailer, retailer_id)
    if not retailer:
        return

    result = await scraper.scrape_price(retailer.product_url, retailer.country_code)
    if not result or result.price is None:
        return

    old_price = retailer.current_price
    new_price = result.price
    now = datetime.now(timezone.utc)

    # Record price point
    db.add(PricePoint(
        retailer_id=retailer.id,
        price=new_price,
        currency=retailer.currency,
        in_stock=result.in_stock,
        observed_at=now,
    ))

    # Update retailer
    retailer.current_price = new_price
    retailer.in_stock = result.in_stock
    retailer.last_scraped_at = now

    # Check monitors for alerts
    await _check_alerts(db, retailer, old_price, new_price, result.in_stock)


async def _check_alerts(
    db: AsyncSession,
    retailer: ProductRetailer,
    old_price: float | None,
    new_price: float,
    in_stock: bool | None,
):
    stmt = select(Monitor).where(
        Monitor.product_id == retailer.product_id,
        Monitor.is_active == True,  # noqa: E712
    )
    result = await db.execute(stmt)
    monitors = result.scalars().all()

    for monitor in monitors:
        # Skip if this retailer not in the monitor's scope
        if monitor.retailer_ids and retailer.id not in monitor.retailer_ids:
            continue

        alerts_to_create: list[Alert] = []

        # Price drop
        if old_price and monitor.alert_on_price_drop:
            change_pct = (new_price - old_price) / old_price * 100
            if change_pct <= -monitor.price_change_threshold_pct:
                alerts_to_create.append(Alert(
                    monitor_id=monitor.id,
                    retailer_id=retailer.id,
                    alert_type=AlertType.PRICE_DROP,
                    old_price=old_price,
                    new_price=new_price,
                    price_change_pct=change_pct,
                    message=f"Cena klesla o {abs(change_pct):.1f}% u {retailer.retailer_name} ({retailer.country_code}): {old_price} → {new_price} {retailer.currency}",
                ))

        # Price increase
        if old_price and monitor.alert_on_price_increase:
            change_pct = (new_price - old_price) / old_price * 100
            if change_pct >= monitor.price_change_threshold_pct:
                alerts_to_create.append(Alert(
                    monitor_id=monitor.id,
                    retailer_id=retailer.id,
                    alert_type=AlertType.PRICE_INCREASE,
                    old_price=old_price,
                    new_price=new_price,
                    price_change_pct=change_pct,
                    message=f"Cena vzrostla o {change_pct:.1f}% u {retailer.retailer_name}: {old_price} → {new_price} {retailer.currency}",
                ))

        # Target price reached
        if monitor.target_price and new_price <= monitor.target_price:
            alerts_to_create.append(Alert(
                monitor_id=monitor.id,
                retailer_id=retailer.id,
                alert_type=AlertType.PRICE_BELOW_TARGET,
                new_price=new_price,
                message=f"Cena u {retailer.retailer_name} je {new_price} {retailer.currency} — pod vaším cílem {monitor.target_price}!",
            ))

        for alert in alerts_to_create:
            db.add(alert)


from sqlalchemy.ext.asyncio import AsyncSession  # noqa: E402
