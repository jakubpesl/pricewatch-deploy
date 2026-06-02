from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.core.database import get_db, AsyncSessionLocal
from app.models.job import DiscoveryJob, JobStatus
from app.models.product import Product
from app.schemas.product import DiscoveryRequest, DiscoveryJobOut, ProductOut
from app.services.discovery import run_discovery
from datetime import datetime, timezone
import structlog

log = structlog.get_logger()
router = APIRouter()


async def _run_discovery_bg(model_number: str, job_id: int):
    try:
        async with AsyncSessionLocal() as db:
            await run_discovery(model_number, job_id, db)
    except Exception as e:
        log.error("discovery.failed", model=model_number, job_id=job_id, error=str(e))
        async with AsyncSessionLocal() as db:
            job = await db.get(DiscoveryJob, job_id)
            if job:
                job.status = JobStatus.FAILED
                job.error_message = str(e)
                job.completed_at = datetime.now(timezone.utc)
                await db.commit()


@router.post("/discover", response_model=DiscoveryJobOut, status_code=202)
async def start_discovery(
    body: DiscoveryRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    """Start a product discovery job. Returns immediately with job ID. Poll /jobs/{job_id} for status."""
    job = DiscoveryJob(
        model_number=body.model_number,
        status=JobStatus.PENDING,
        sources_requested=body.markets,
        created_at=datetime.now(timezone.utc),
    )
    db.add(job)
    await db.commit()
    await db.refresh(job)

    background_tasks.add_task(_run_discovery_bg, body.model_number, job.id)
    return job


@router.get("/jobs/{job_id}", response_model=DiscoveryJobOut)
async def get_job(job_id: int, db: AsyncSession = Depends(get_db)):
    """Poll discovery job status."""
    job = await db.get(DiscoveryJob, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@router.get("/products/{model_number}", response_model=ProductOut)
async def get_product(model_number: str, db: AsyncSession = Depends(get_db)):
    """Get product with all discovered retailers and their current prices."""
    stmt = (
        select(Product)
        .where(Product.model_number == model_number)
        .options()  # retailers loaded via relationship
    )
    result = await db.execute(stmt)
    product = result.scalar_one_or_none()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    return product


@router.get("/products/{model_number}/prices")
async def get_price_history(
    model_number: str,
    retailer_id: int | None = None,
    days: int = 30,
    db: AsyncSession = Depends(get_db),
):
    """Get price history for a product (optionally filtered by retailer)."""
    from sqlalchemy import select, text
    from app.models.product import PricePoint, ProductRetailer

    stmt = (
        select(PricePoint, ProductRetailer.retailer_name, ProductRetailer.country_code)
        .join(ProductRetailer, PricePoint.retailer_id == ProductRetailer.id)
        .join(Product, ProductRetailer.product_id == Product.id)
        .where(Product.model_number == model_number)
        .where(PricePoint.observed_at >= text(f"NOW() - INTERVAL '{days} days'"))
    )
    if retailer_id:
        stmt = stmt.where(PricePoint.retailer_id == retailer_id)

    result = await db.execute(stmt)
    rows = result.all()
    return [
        {
            "retailer_id": row[0].retailer_id,
            "retailer_name": row[1],
            "country_code": row[2],
            "price": row[0].price,
            "currency": row[0].currency,
            "in_stock": row[0].in_stock,
            "observed_at": row[0].observed_at,
        }
        for row in rows
    ]
